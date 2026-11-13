# src/agent_factory.py
import json
import logging
import os
import time
import yaml
from crewai import Agent, Task, Crew
from src.rag_engine import RAGEngine, ScopedKnowledgeTool
from src.output_cleanup import clean_conditional_code_section
from src.proposal_processor import ProposalProcessor, ProposalSearchTool
from src.solution_architect_triage import SolutionArchitectTriageAgent, TriageDecision


logger = logging.getLogger(__name__)

_CORE_SPECIALIST_KEYS = {
    "ddd_specialist",
    "clean_arch_specialist",
    "cqrs_specialist",
    "eda_specialist",
    "nfr_specialist",
}


class AgentFactory:
    """Programmatically loads configurations from YAML files and assembles 
    interchangeable CrewAI Agents and Tasks at runtime."""
    
    # Define relative paths to your declarative configurations
    _AGENTS_CONFIG_PATH = os.path.join("config", "agents.yaml")
    _TASKS_CONFIG_PATH = os.path.join("config", "tasks.yaml")

    ALL_AGENTS_LABEL = "Smart Panel (Auto-Select Relevant Specialists)"

    @classmethod
    def get_individual_profiles(cls) -> list[str]:
        """Returns only the individual specialist profiles from agents.yaml."""
        return cls.get_available_profiles()
        
    @classmethod
    def _load_yaml(cls, file_path: str) -> dict:
        """Internal helper to safely read structural YAML files from disk."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Configuration file missing at: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    @classmethod
    def get_available_profiles(cls) -> list[str]:
        """Scans the agents.yaml keys to dynamically populate the UI dropdown."""
        configs = cls._load_yaml(cls._AGENTS_CONFIG_PATH)
        return [
            key.replace("_", " ").title()
            for key, config in configs.items()
            if not config.get("internal_only")
        ]

    @classmethod
    def create_agent(
        cls, profile_id: str, llm, proposal_uploaded: bool = False
    ) -> "AgentRunner | SmartPanelRunner":
        """Instantiates an operational runtime runner by extracting metadata 
        profiles and binding them to the active compute engine."""
        
        agents_metadata = cls._load_yaml(cls._AGENTS_CONFIG_PATH)
        tasks_metadata = cls._load_yaml(cls._TASKS_CONFIG_PATH)

        if profile_id == cls.ALL_AGENTS_LABEL:
            return SmartPanelRunner(
                agents_metadata=agents_metadata,
                tasks_metadata=tasks_metadata,
                llm_instance=llm,
                proposal_uploaded=proposal_uploaded
            )

        # Match the label shown in the UI to its source YAML key.
        profile_lookup = {
            key.replace("_", " ").title(): key
            for key, config in agents_metadata.items()
            if not config.get("internal_only")
        }
        config_key = profile_id if profile_id in agents_metadata else profile_lookup.get(profile_id)
        
        if config_key is None:
            raise ValueError(f"Agent profile '{profile_id}' not defined in agents.yaml")

        agent_config = agents_metadata[config_key]
        if agent_config.get("internal_only"):
            raise ValueError(f"Agent profile '{profile_id}' is reserved for internal orchestration.")
            
        task_key = agent_config.get("task_key", "review_task")
        
        if task_key not in tasks_metadata:
            raise ValueError(f"Task context '{task_key}' not defined in tasks.yaml")

        # 3. Package configurations into a standalone runtime executor class
        return AgentRunner(
            agent_config=agents_metadata[config_key],
            task_config=tasks_metadata[task_key],
            llm_instance=llm,
            proposal_uploaded=proposal_uploaded
        )

class SmartPanelRunner:
    """Runs a bounded set of relevant specialists configured in agents.yaml."""

    MAX_SPECIALISTS = 4

    def __init__(
        self,
        agents_metadata: dict,
        tasks_metadata: dict,
        llm_instance,
        proposal_uploaded: bool = False
    ):
        self.agents_metadata = agents_metadata
        self.tasks_metadata = tasks_metadata
        self.llm = llm_instance
        self.proposal_uploaded = proposal_uploaded

    def _select_additional_specialists(self, routing_text: str) -> list[tuple[str, dict]]:
        routing_text = routing_text.casefold()
        selected = [
            (profile_key, agent_config)
            for profile_key, agent_config in self.agents_metadata.items()
            if profile_key not in _CORE_SPECIALIST_KEYS
            and not agent_config.get("internal_only")
            and (
                agent_config.get("always_include")
                or (
                    not agent_config.get("routing_keywords")
                    and not agent_config.get("conditional_routing")
                )
                or any(
                    keyword.casefold() in routing_text
                    for keyword in agent_config.get("routing_keywords", [])
                )
            )
        ]
        return selected

    def _select_specialists(
        self,
        routing_text: str,
        triage_selected: tuple[str, ...] | None = None,
        additional_selected: list[tuple[str, dict]] | None = None,
    ) -> list[tuple[str, dict]]:
        if triage_selected is None:
            selected = [
                (profile_key, agent_config)
                for profile_key, agent_config in self.agents_metadata.items()
                if not agent_config.get("internal_only")
                and (
                    agent_config.get("always_include")
                    or (
                        not agent_config.get("routing_keywords")
                        and not agent_config.get("conditional_routing")
                    )
                    or any(
                        keyword.casefold() in routing_text.casefold()
                        for keyword in agent_config.get("routing_keywords", [])
                    )
                )
            ]
        else:
            selected_keys = set(triage_selected)
            selected = [
                (profile_key, agent_config)
                for profile_key, agent_config in self.agents_metadata.items()
                if profile_key in selected_keys
            ]
            selected.extend(additional_selected or [])

        if len(selected) > self.MAX_SPECIALISTS:
            names = ", ".join(config["role"] for _, config in selected)
            logger.warning(
                "Smart Panel selection exceeded safety limit selected=%d limit=%d",
                len(selected),
                self.MAX_SPECIALISTS,
            )
            raise ValueError(
                f"Smart Panel selected {len(selected)} specialists, exceeding the "
                f"safety limit of {self.MAX_SPECIALISTS}: {names}. Narrow the request "
                "or use Single Specialist Review."
            )
        return selected

    def run(self, user_request: str):
        panel_started = time.perf_counter()
        yield "⏳ Solution Architect is classifying the solution and selecting relevant specialist reviews..."
        if self.proposal_uploaded:
            routing_text = ProposalProcessor.get_indexed_proposal_text()
        else:
            routing_text = user_request

        additional_candidates = self._select_additional_specialists(routing_text)
        always_included = [
            candidate for candidate in additional_candidates
            if candidate[1].get("always_include")
        ]
        optional_candidates = [
            candidate for candidate in additional_candidates
            if not candidate[1].get("always_include")
        ]
        available_additional_slots = self.MAX_SPECIALISTS - 1
        if len(always_included) > available_additional_slots:
            raise ValueError(
                "Always-included specialists exceed the Smart Panel safety limit "
                "while reserving a slot for solution-specific triage."
            )
        selected_optional_count = max(
            0,
            available_additional_slots - len(always_included),
        )
        omitted_additional = optional_candidates[selected_optional_count:]
        additional_candidates = (
            always_included + optional_candidates[:selected_optional_count]
        )
        available_core_slots = self.MAX_SPECIALISTS - len(additional_candidates)
        triage = SolutionArchitectTriageAgent(
            agents_metadata=self.agents_metadata,
            max_specialists=self.MAX_SPECIALISTS,
        ).assess(
            llm=self.llm,
            user_request=user_request,
            proposal_uploaded=self.proposal_uploaded,
            available_agent_slots=available_core_slots,
        )
        triage_report = self._format_triage_report(
            triage,
            additional_candidates,
            omitted_additional,
        )
        if not triage.solution_related:
            yield (
                f"{triage_report}\n\n"
                "⛔ Smart Panel review not started: the supplied content is unrelated "
                "to software or a digital solution."
            )
            return

        selected_specialists = self._select_specialists(
            routing_text,
            triage_selected=triage.selected_agent_keys,
            additional_selected=additional_candidates,
        )
        if not selected_specialists:
            yield (
                f"{triage_report}\n\n"
                "No specialist reviews were selected for this solution."
            )
            return

        logger.info(
            "Smart Panel started specialist_count=%d proposal_uploaded=%s specialists=%s",
            len(selected_specialists),
            self.proposal_uploaded,
            ", ".join(config["role"] for _, config in selected_specialists),
        )
        results = []
        completed_agents = []
        testing_review = ""
        total_stages = len(selected_specialists) + 3
        for index, (profile_key, agent_config) in enumerate(selected_specialists, start=1):
            yield (
                f"{triage_report}\n\n---\n\n"
                f"⏳ Smart Panel: running specialist {index}/"
                f"{len(selected_specialists)} — {agent_config['role']}.\n\n"
                f"Completed: {', '.join(completed_agents) or 'None'}"
            )
            task_key = agent_config.get("task_key", "review_task")
            if task_key not in self.tasks_metadata:
                raise ValueError(f"Task context '{task_key}' not defined in tasks.yaml")

            runner = AgentRunner(
                agent_config=agent_config,
                task_config=self.tasks_metadata[task_key],
                llm_instance=self.llm,
                proposal_uploaded=self.proposal_uploaded
            )
            stage_started = time.perf_counter()
            logger.info("Smart Panel specialist started role=%s", agent_config["role"])
            result = "\n".join(runner.run(user_request))
            results.append(f"### {agent_config['role']}\n\n{result}")
            if profile_key == "testing_specialist":
                testing_review = result
            completed_agents.append(agent_config["role"])
            logger.info(
                "Smart Panel specialist completed role=%s duration_seconds=%.2f "
                "succeeded=%s",
                agent_config["role"],
                time.perf_counter() - stage_started,
                "⚠️ Agent Automation Runtime Error:" not in result,
            )

        original_feedback = "\n\n---\n\n".join(results)
        yield (
            f"{triage_report}\n\n---\n\n"
            f"⏳ Smart Panel: running reconciliation ({len(completed_agents) + 1}/"
            f"{total_stages}).\n\n"
            f"Completed: {', '.join(completed_agents)}"
        )
        technical_review = self._run_review_agent(
            "technical_reconciliation_agent",
            self.tasks_metadata,
            (
                "--- REVIEW REQUEST ---\n"
                f"{user_request}\n\n"
                "--- ORIGINAL SPECIALIST FEEDBACK ---\n"
                f"{original_feedback}"
            )
        )
        if technical_review.startswith("⚠️ Technical Feedback Reconciliation Reviewer failed:"):
            technical_review = (
                f"{technical_review}\n\n"
                "### Specialist Feedback (Unchanged)\n\n"
                f"{original_feedback}"
            )

        completed_agents.append("Technical Feedback Reconciliation Reviewer")
        yield (
            f"{triage_report}\n\n---\n\n"
            f"⏳ Smart Panel: reviewing the solution document "
            f"({len(completed_agents) + 1}/{total_stages}).\n\n"
            f"Completed: {', '.join(completed_agents)}"
        )
        document_review = self._run_review_agent(
            "solution_document_review_agent",
            self.tasks_metadata,
            (
                "--- REVIEW REQUEST AND PROPOSAL CONTEXT ---\n"
                f"{user_request}\n\n"
                "--- RECONCILED TECHNICAL FEEDBACK ---\n"
                f"{technical_review}\n\n"
                "Review the uploaded solution document itself against the general "
                "architecture principles. Identify specific documentation changes "
                "needed to align it with the reconciled technical recommendations. "
                "Use the uploaded-proposal search tool when a document is available."
            ),
            proposal_uploaded=self.proposal_uploaded
        )

        completed_agents.append("Solution Document Architecture Peer Reviewer")
        yield (
            f"{triage_report}\n\n---\n\n"
            f"⏳ Smart Panel: preparing the final review "
            f"({len(completed_agents) + 1}/{total_stages}).\n\n"
            f"Completed: {', '.join(completed_agents)}"
        )
        overall_review = self._run_review_agent(
            "final_review_agent",
            self.tasks_metadata,
            (
                "--- TECHNICAL RECONCILIATION ---\n"
                f"{technical_review}\n\n"
                "--- SOLUTION DOCUMENT PEER REVIEW ---\n"
                f"{document_review}\n\n"
                "--- TESTING & VERIFICATION REVIEW "
                "(ADVISORY; MUST NOT CHANGE IMPLEMENTATION DECISION) ---\n"
                f"{testing_review or 'Testing specialist feedback was unavailable.'}"
            )
        )

        yield (
            f"{triage_report}\n\n---\n\n"
            f"## Overall Solution Review\n\n{overall_review}"
            "\n\n---\n\n## Specialist Feedback\n\n"
            f"{technical_review}"
        )
        logger.info(
            "Smart Panel completed specialist_count=%d duration_seconds=%.2f",
            len(selected_specialists),
            time.perf_counter() - panel_started,
        )

    def _format_triage_report(
        self,
        triage: TriageDecision,
        additional_selected: list[tuple[str, dict]],
        omitted_additional: list[tuple[str, dict]],
    ) -> str:
        selected_keys = set(triage.selected_agent_keys)
        assessment_by_key = {
            assessment.agent_key: assessment
            for assessment in triage.agent_assessments
        }
        selected_lines = [
            f"- **{self.agents_metadata[key]['role']}** — "
            f"{assessment_by_key[key].reason}"
            for key in triage.selected_agent_keys
        ]
        selected_lines.extend(
            f"- **{config['role']}** — selected by the existing specialist-routing rules."
            for _, config in additional_selected
        )
        not_selected_lines = [
            f"- **{self.agents_metadata[key]['role']}** — "
            f"{assessment_by_key[key].reason}"
            for key in assessment_by_key
            if key not in selected_keys
        ]
        not_selected_lines.extend(
            f"- **{config['role']}** — not selected because the Smart Panel "
            "specialist safety limit was reached."
            for _, config in omitted_additional
        )
        selected_text = "\n".join(selected_lines) if selected_lines else "- None"
        not_selected_text = "\n".join(not_selected_lines) if not_selected_lines else "- None"
        return (
            "## Solution Classification\n\n"
            f"**Classification:** {triage.classification}\n\n"
            f"{triage.classification_reason}\n\n"
            "### Specialists Selected\n\n"
            f"{selected_text}\n\n"
            "### Specialists Not Selected\n\n"
            f"{not_selected_text}"
        )

    def _run_review_agent(
        self,
        agent_key: str,
        tasks_metadata: dict,
        user_request: str,
        proposal_uploaded: bool = False
    ) -> str:
        agent_config = self.agents_metadata.get(agent_key)
        if agent_config is None:
            raise ValueError(f"Internal review agent '{agent_key}' is missing from agents.yaml.")

        task_key = agent_config.get("task_key")
        if task_key not in tasks_metadata:
            raise ValueError(
                f"Task context '{task_key}' for '{agent_key}' is not defined in tasks.yaml."
            )

        runner = AgentRunner(
            agent_config=agent_config,
            task_config=tasks_metadata[task_key],
            llm_instance=self.llm,
            proposal_uploaded=proposal_uploaded
        )
        try:
            started = time.perf_counter()
            logger.info("Internal review started role=%s", agent_config["role"])
            result = runner.execute_sync(user_request)
            logger.info(
                "Internal review completed role=%s duration_seconds=%.2f",
                agent_config["role"],
                time.perf_counter() - started,
            )
            return result
        except Exception as error:
            logger.error(
                "Internal review failed role=%s error_type=%s",
                agent_config["role"],
                type(error).__name__,
            )
            return f"⚠️ {agent_config['role']} failed: {error}"

class AgentRunner:
    """Executes a single specialist agent scoped to its assigned knowledge base 
    and equipped to query the uploaded solution proposal."""
    
    def __init__(
        self,
        agent_config: dict,
        task_config: dict,
        llm_instance,
        proposal_uploaded: bool = False
    ):
        self.agent_config = agent_config
        self.task_config = task_config
        self.llm = llm_instance
        self.proposal_uploaded = proposal_uploaded
        self.proposal_evidence_retrieved = False

    def execute_sync(self, user_request: str) -> str:
        started = time.perf_counter()
        target_doc = self.agent_config.get("knowledge_source")
        retrieved_context = []
        if target_doc:
            knowledge_context = RAGEngine.query_knowledge_base(
                user_request,
                source_filter=target_doc,
            )
            if knowledge_context.startswith("Error executing context retrieval logic:"):
                raise RuntimeError(
                    f"Could not retrieve specialist guidance from {target_doc}."
                )
            retrieved_context.append(
                f"--- SPECIALIST KNOWLEDGE ({target_doc}) ---\n{knowledge_context}"
            )
            logger.info(
                "Agent knowledge context retrieved role=%s source=%s output_chars=%d",
                self.agent_config["role"],
                target_doc,
                len(knowledge_context),
            )

        if self.proposal_uploaded:
            proposal_context = ProposalProcessor.query_proposal(
                f"{self.agent_config['role']}: {user_request}"
            )
            if proposal_context.startswith("Error querying uploaded proposal:"):
                raise RuntimeError("Could not retrieve evidence from the uploaded proposal.")
            self.proposal_evidence_retrieved = proposal_context.startswith(
                "[Proposal Section:"
            )
            retrieved_context.append(
                f"--- UPLOADED PROPOSAL EVIDENCE ---\n{proposal_context}"
            )
            logger.info(
                "Agent proposal context retrieved role=%s evidence_found=%s output_chars=%d",
                self.agent_config["role"],
                self.proposal_evidence_retrieved,
                len(proposal_context),
            )

        task_input = user_request
        if retrieved_context:
            task_input += (
                "\n\n--- PRE-RETRIEVED REVIEW EVIDENCE ---\n"
                + "\n\n".join(retrieved_context)
            )

        tools = []
        if target_doc:
            tools.append(ScopedKnowledgeTool(source_filter=target_doc))

        if self.proposal_uploaded:
            tools.append(ProposalSearchTool())

        agent_llm = self.llm
        local_max_output_tokens = self.agent_config.get("local_max_output_tokens")
        if (
            local_max_output_tokens is not None
            and getattr(self.llm, "provider", None) == "ollama"
        ):
            agent_llm = self.llm.model_copy(
                update={"max_tokens": local_max_output_tokens}
            )

        crew_agent = Agent(
            role=self.agent_config["role"],
            goal=self.agent_config["goal"],
            backstory=self.agent_config["backstory"],
            llm=agent_llm,
            verbose=False,
            allow_delegation=False,
            tools=tools,
            max_iter=3,
            max_execution_time=180,
        )
        
        crew_task = Task(
            description=self.task_config["description"].format(user_request=task_input),
            expected_output=self.task_config["expected_output"],
            agent=crew_agent
        )
        
        crew = Crew(
            agents=[crew_agent],
            tasks=[crew_task],
            verbose=False
        )
        
        logger.info(
            "Agent execution started role=%s tool_count=%d proposal_uploaded=%s",
            self.agent_config["role"],
            len(tools),
            self.proposal_uploaded,
        )
        try:
            raw_response = str(crew.kickoff()).strip()
        except RuntimeError as error:
            if not (
                self._is_local_qwen()
                and "provider returned no content" in str(error).casefold()
            ):
                raise
            logger.warning(
                "Local Qwen returned no content role=%s; retrying once with a "
                "short, tool-free response",
                self.agent_config["role"],
            )
            retry_llm = self.llm.model_copy(
                update={
                    "reasoning_effort": "none",
                    "max_tokens": 768,
                    "timeout": 60,
                }
            )
            raw_response = self._retry_without_tools(
                task_description=self.task_config["description"].format(
                    user_request=task_input
                ),
                llm_instance=retry_llm,
                retry_instruction=(
                    "The previous attempt returned no review content. Use only "
                    "the evidence already provided, do not call tools, and give "
                    "a concise review in the requested format."
                ),
                max_execution_time=60,
            )
        if self._is_unexecuted_tool_call(raw_response):
            logger.warning(
                "Agent returned unexecuted tool-call JSON role=%s; retrying without tools",
                self.agent_config["role"],
            )
            raw_response = self._retry_without_tools(
                task_description=self.task_config["description"].format(
                    user_request=task_input
                ),
                llm_instance=self.llm,
                retry_instruction=(
                    "Your previous response was an unexecuted tool-call payload, "
                    "not a review. Do not call tools or return JSON. Use the "
                    "pre-retrieved evidence above and produce the requested review "
                    "in its specified format."
                ),
                max_execution_time=180,
            )
            if self._is_unexecuted_tool_call(raw_response):
                raise RuntimeError(
                    "The model returned tool-call JSON instead of a review, even after "
                    "a retry without tools. Try a model with reliable instruction following."
                )

        response = clean_conditional_code_section(raw_response)
        logger.info(
            "Agent execution completed role=%s duration_seconds=%.2f output_chars=%d",
            self.agent_config["role"],
            time.perf_counter() - started,
            len(response),
        )
        if self.proposal_uploaded:
            self.proposal_evidence_retrieved = (
                self.proposal_evidence_retrieved or tools[-1].retrieved_evidence
            )
        return response

    def _retry_without_tools(
        self,
        task_description: str,
        llm_instance,
        retry_instruction: str,
        max_execution_time: int,
    ) -> str:
        retry_agent = Agent(
            role=self.agent_config["role"],
            goal=self.agent_config["goal"],
            backstory=self.agent_config["backstory"],
            llm=llm_instance,
            verbose=False,
            allow_delegation=False,
            tools=[],
            max_iter=1,
            max_execution_time=max_execution_time,
        )
        retry_task = Task(
            description=f"{task_description}\n\n{retry_instruction}",
            expected_output=self.task_config["expected_output"],
            agent=retry_agent,
        )
        return str(
            Crew(
                agents=[retry_agent],
                tasks=[retry_task],
                verbose=False,
            ).kickoff()
        ).strip()

    def _is_local_qwen(self) -> bool:
        return (
            getattr(self.llm, "provider", None) == "ollama"
            and "qwen" in str(getattr(self.llm, "model", "")).casefold()
        )

    @staticmethod
    def _is_unexecuted_tool_call(response: str) -> bool:
        candidate = response.strip()
        if candidate.startswith("```") and candidate.endswith("```"):
            candidate = "\n".join(candidate.splitlines()[1:-1]).strip()
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            return False
        if not isinstance(payload, dict):
            return False

        keys = set(payload)
        if keys.intersection({"tool_call", "tool_calls"}):
            return True
        if keys.intersection({"tool", "tool_name"}) and keys.intersection(
            {"query", "arguments", "input", "parameters"}
        ):
            return True
        if "action" in keys and keys.intersection({"action_input", "input"}):
            return True
        return keys == {"query"} and isinstance(payload["query"], str)

    def run(self, user_request: str):
        try:
            response = self.execute_sync(user_request)
        except Exception as e:
            logger.error(
                "Agent execution failed role=%s error_type=%s",
                self.agent_config["role"],
                type(e).__name__,
            )
            response = f"⚠️ Agent Automation Runtime Error: {str(e)}"

        if self.proposal_uploaded:
            document_status = (
                "✅ Proposal evidence retrieved"
                if self.proposal_evidence_retrieved
                else "⚠️ No proposal evidence retrieved"
            )
        else:
            document_status = "ℹ️ No proposal uploaded"

        yield (
            f"**Review coverage:** ✅ Prompt supplied · {document_status}\n\n"
            f"{response}"
        )

# src/agent_factory.py
import logging
import os
import time
import yaml
from crewai import Agent, Task, Crew
from src.rag_engine import ScopedKnowledgeTool
from src.proposal_processor import ProposalProcessor, ProposalSearchTool


logger = logging.getLogger(__name__)



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
        try:
            configs = cls._load_yaml(cls._AGENTS_CONFIG_PATH)
            return [
                key.replace("_", " ").title()
                for key, config in configs.items()
                if not config.get("internal_only")
            ]
        except Exception as error:
            logger.error(
                "Unable to load individual agent profiles error_type=%s",
                type(error).__name__,
            )
            return []
        
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
        try:
            configs = cls._load_yaml(cls._AGENTS_CONFIG_PATH)
            # Map raw snake_case keys into human-readable Title Case labels for the UI
            return [
                key.replace("_", " ").title()
                for key, config in configs.items()
                if not config.get("internal_only")
            ]
        except Exception as error:
            logger.error(
                "Unable to load available agent profiles error_type=%s",
                type(error).__name__,
            )
            return []

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

    def _select_specialists(self, routing_text: str) -> list[tuple[str, dict]]:
        routing_text = routing_text.casefold()
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
                    keyword.casefold() in routing_text
                    for keyword in agent_config.get("routing_keywords", [])
                )
            )
        ]
        if not selected:
            raise ValueError(
                "No specialist profiles matched the request in agents.yaml."
            )
        if len(selected) > self.MAX_SPECIALISTS:
            names = ", ".join(config["role"] for _, config in selected)
            logger.warning(
                "Smart Panel selection exceeded safety limit selected=%d limit=%d",
                len(selected),
                self.MAX_SPECIALISTS,
            )
            raise ValueError(
                f"Smart Panel matched {len(selected)} specialists, exceeding the "
                f"safety limit of {self.MAX_SPECIALISTS}: {names}. Narrow the request "
                "or use Single Specialist Review."
            )

        return selected

    def run(self, user_request: str):
        panel_started = time.perf_counter()
        if self.proposal_uploaded:
            routing_text = ProposalProcessor.get_indexed_proposal_text()
        else:
            routing_text = user_request

        selected_specialists = self._select_specialists(routing_text)
        logger.info(
            "Smart Panel started specialist_count=%d proposal_uploaded=%s specialists=%s",
            len(selected_specialists),
            self.proposal_uploaded,
            ", ".join(config["role"] for _, config in selected_specialists),
        )
        results = []
        completed_agents = []
        total_stages = len(selected_specialists) + 3
        for index, (_, agent_config) in enumerate(selected_specialists, start=1):
            yield (
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
                f"{document_review}"
            )
        )

        yield (
            f"## Overall Solution Review\n\n{overall_review}"
            "\n\n---\n\n## Specialist Feedback\n\n"
            f"{technical_review}"
            "\n\n---\n\n## Solution Document Peer Review\n\n"
            f"{document_review}"
        )
        logger.info(
            "Smart Panel completed specialist_count=%d duration_seconds=%.2f",
            len(selected_specialists),
            time.perf_counter() - panel_started,
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
        tools = []
        if target_doc:
            tools.append(ScopedKnowledgeTool(source_filter=target_doc))

        if self.proposal_uploaded:
            tools.append(ProposalSearchTool())

        crew_agent = Agent(
            role=self.agent_config["role"],
            goal=self.agent_config["goal"],
            backstory=self.agent_config["backstory"],
            llm=self.llm,
            verbose=False,
            allow_delegation=False,
            tools=tools,
            max_iter=3,
            max_execution_time=180,
        )
        
        crew_task = Task(
            description=self.task_config["description"].format(user_request=user_request),
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
        response = str(crew.kickoff())
        logger.info(
            "Agent execution completed role=%s duration_seconds=%.2f output_chars=%d",
            self.agent_config["role"],
            time.perf_counter() - started,
            len(response),
        )
        if self.proposal_uploaded:
            self.proposal_evidence_retrieved = tools[-1].retrieved_evidence
        return response

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

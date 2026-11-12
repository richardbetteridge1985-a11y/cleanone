# src/agent_factory.py
import os
import yaml
from crewai import Agent, Task, Crew
from src.rag_engine import ScopedKnowledgeTool
from src.proposal_processor import ProposalProcessor, ProposalSearchTool




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
        except Exception:
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
        except Exception:
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
    """Runs every specialist configured in agents.yaml."""

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
                not agent_config.get("conditional_routing")
                or any(
                    keyword.casefold() in routing_text
                    for keyword in agent_config.get("routing_keywords", [])
                )
            )
        ]
        if not selected:
            raise ValueError(
                "No agent profiles are configured in agents.yaml."
            )

        return selected

    def run(self, user_request: str):
        if self.proposal_uploaded:
            routing_text = ProposalProcessor.get_indexed_proposal_text()
        else:
            routing_text = user_request

        results = []
        for _, agent_config in self._select_specialists(routing_text):
            task_key = agent_config.get("task_key", "review_task")
            if task_key not in self.tasks_metadata:
                raise ValueError(f"Task context '{task_key}' not defined in tasks.yaml")

            runner = AgentRunner(
                agent_config=agent_config,
                task_config=self.tasks_metadata[task_key],
                llm_instance=self.llm,
                proposal_uploaded=self.proposal_uploaded
            )
            result = "\n".join(runner.run(user_request))
            results.append(f"### {agent_config['role']}\n\n{result}")

        original_feedback = "\n\n---\n\n".join(results)
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
            return runner.execute_sync(user_request)
        except Exception as error:
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
            verbose=True,
            allow_delegation=False,
            tools=tools
        )
        
        crew_task = Task(
            description=self.task_config["description"].format(user_request=user_request),
            expected_output=self.task_config["expected_output"],
            agent=crew_agent
        )
        
        crew = Crew(
            agents=[crew_agent],
            tasks=[crew_task],
            verbose=True
        )
        
        response = str(crew.kickoff())
        if self.proposal_uploaded:
            self.proposal_evidence_retrieved = tools[-1].retrieved_evidence
        return response

    def run(self, user_request: str):
        try:
            response = self.execute_sync(user_request)
        except Exception as e:
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

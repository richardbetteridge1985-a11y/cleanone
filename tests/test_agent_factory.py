from unittest.mock import patch
from pathlib import Path

from src.agent_factory import AgentFactory, AgentRunner, SmartPanelRunner
from src.proposal_processor import ProposalProcessor, ProposalSearchTool


def test_smart_panel_routes_to_specialist_runner():
    runner = AgentFactory.create_agent(
        profile_id=AgentFactory.ALL_AGENTS_LABEL,
        llm=object()
    )

    assert isinstance(runner, SmartPanelRunner)


def test_internal_judges_are_not_selectable_specialists():
    profiles = AgentFactory.get_individual_profiles()
    runner = AgentFactory.create_agent(
        profile_id=AgentFactory.ALL_AGENTS_LABEL,
        llm=object()
    )

    assert "Technical Reconciliation Agent" not in profiles
    assert "Solution Document Review Agent" not in profiles
    assert "Final Review Agent" not in profiles
    assert not {
        "technical_reconciliation_agent",
        "solution_document_review_agent",
        "final_review_agent",
    }.intersection(
        profile_key for profile_key, _ in runner._select_specialists("review")
    )


def test_document_review_agent_uses_general_knowledge_source():
    agents = AgentFactory._load_yaml(AgentFactory._AGENTS_CONFIG_PATH)
    tasks = AgentFactory._load_yaml(AgentFactory._TASKS_CONFIG_PATH)
    config = agents["solution_document_review_agent"]
    runner = AgentRunner(
        agent_config=config,
        task_config=tasks[config["task_key"]],
        llm_instance=object(),
        proposal_uploaded=True
    )

    with (
        patch("src.agent_factory.ScopedKnowledgeTool") as knowledge_tool,
        patch("src.agent_factory.ProposalSearchTool") as proposal_tool,
        patch("src.agent_factory.Agent"),
        patch("src.agent_factory.Task"),
        patch("src.agent_factory.Crew") as crew_factory,
    ):
        crew_factory.return_value.kickoff.return_value = "Synthesis"
        assert runner.execute_sync("Original specialist feedback") == "Synthesis"

    knowledge_tool.assert_called_once_with(source_filter="00_general.md")
    assert proposal_tool.called


def test_document_review_task_requires_pass_fail_for_all_general_attributes():
    tasks = AgentFactory._load_yaml(AgentFactory._TASKS_CONFIG_PATH)
    review_task = tasks["solution_document_review_task"]
    standards = Path("knowledge_base/00_general.md").read_text(encoding="utf-8")

    assert "exactly PASS or FAIL" in review_task["expected_output"]
    assert "Each FAIL row must give a specific" in review_task["expected_output"]
    assert "Assess all 12 attributes in 00_general.md" in review_task["description"]

    attribute_names = [
        "Architecture Vision & Strategic Alignment",
        "Stakeholder & Concern Mapping",
        "Business Capability & Process Impact",
        "Options Analysis & Architecture Decision Records",
        "Cost, Commercials & Resource Viability",
        "Delivery Roadmap, Risks & Governance",
        "Multi-Level Visual Clarity & Diagram Consistency",
        "Data Architecture & Lifecycle Governance",
        "Integration Contracts & Interface Specifications",
        "Quantified Non-Functional Requirements",
        "Security, Identity & Trust Boundaries",
        "Deployment Topology, Operability & Verification",
    ]
    assert all(name in standards for name in attribute_names)
    assert all(name in review_task["expected_output"] for name in attribute_names)


def test_smart_panel_selects_all_non_cloud_specialists_without_cloud_mentions():
    runner = AgentFactory.create_agent(
        profile_id=AgentFactory.ALL_AGENTS_LABEL,
        llm=object()
    )

    selected = [
        profile_key
        for profile_key, _ in runner._select_specialists("Review the proposal.")
    ]

    assert selected == [
        profile_key
        for profile_key, config in runner.agents_metadata.items()
        if not config.get("conditional_routing") and not config.get("internal_only")
    ]


def test_smart_panel_runs_all_non_cloud_specialists_by_default():
    runner = AgentFactory.create_agent(
        profile_id=AgentFactory.ALL_AGENTS_LABEL,
        llm=object()
    )

    def fake_execute(agent, _):
        if agent.agent_config.get("internal_only"):
            if agent.agent_config["role"] == "Technical Feedback Reconciliation Reviewer":
                return "\n\n".join(
                    f"### {config['role']}\nFeedback from {config['role']}."
                    for config in runner.agents_metadata.values()
                    if not config.get("internal_only")
                    and not config.get("conditional_routing")
                )
            return agent.agent_config["role"]
        return f"Feedback from {agent.agent_config['role']}."

    with patch(
        "src.agent_factory.AgentRunner.execute_sync",
        autospec=True,
        side_effect=fake_execute
    ):
        report = next(runner.run("Review the solution."))

    for agent_config in runner.agents_metadata.values():
        if agent_config.get("conditional_routing") or agent_config.get("internal_only"):
            assert f"### {agent_config['role']}" not in report
            continue
        assert f"### {agent_config['role']}" in report
    assert "## Overall Solution Review" in report
    assert "## Specialist Feedback" in report
    assert "## Technical Feedback Reconciliation" not in report
    assert "## Solution Document Peer Review" in report


def test_smart_panel_reconciles_feedback_and_appends_only_changed_originals():
    runner = AgentFactory.create_agent(
        profile_id=AgentFactory.ALL_AGENTS_LABEL,
        llm=object()
    )

    def fake_execute(agent, request):
        agent_key = next(
            key for key, config in runner.agents_metadata.items()
            if config is agent.agent_config
        )
        if agent_key == "technical_reconciliation_agent":
            assert "--- REVIEW REQUEST ---" in request
            assert "Original advice from" in request
            return (
                "### Clean Architecture Reviewer\n\n"
                "Revised advice.\n\n"
                "**Reconciliation note:** Combined conflicting proposals.\n\n"
                "## Appendix: Original Feedback Changed by Reconciliation\n\n"
                "### Clean Architecture Reviewer — Original Feedback\n\n"
                "Original advice from Clean Architecture Reviewer."
            )
        if agent_key == "solution_document_review_agent":
            assert "Revised advice." in request
            return "Document peer review recommendations."
        if agent_key == "final_review_agent":
            assert "Revised advice." in request
            assert "Document peer review recommendations." in request
            return "Overall ranked judgment."
        return f"Original advice from {agent.agent_config['role']}."

    with patch(
        "src.agent_factory.AgentRunner.execute_sync",
        autospec=True,
        side_effect=fake_execute
    ):
        report = next(runner.run("Review the solution."))

    assert "Revised advice." in report
    assert "**Reconciliation note:** Combined conflicting proposals." in report
    assert "Document peer review recommendations." in report
    assert "Overall ranked judgment." in report
    assert "## Technical Feedback Reconciliation" not in report
    appendix = report.split("## Appendix: Original Feedback Changed by Reconciliation", 1)[1]
    assert "Original advice from Clean Architecture Reviewer." in appendix
    assert "Original advice from CQRS & Data Flow Architect." not in appendix
    assert "Original advice from Testing & Verification Strategist." not in appendix


def test_smart_panel_preserves_originals_if_technical_reconciliation_fails():
    runner = AgentFactory.create_agent(
        profile_id=AgentFactory.ALL_AGENTS_LABEL,
        llm=object()
    )

    def fail_reconciliation(agent, _):
        if agent.agent_config["role"] == "Technical Feedback Reconciliation Reviewer":
            raise RuntimeError("synthesis unavailable")
        if agent.agent_config["role"] == "Solution Document Architecture Peer Reviewer":
            return "Document peer review."
        if agent.agent_config["role"] == "Overall Solution Review Judge":
            return "Overall review."
        return f"Original advice from {agent.agent_config['role']}."

    with patch(
        "src.agent_factory.AgentRunner.execute_sync",
        autospec=True,
        side_effect=fail_reconciliation
    ):
        report = next(runner.run("Review the solution."))

    assert "⚠️ Technical Feedback Reconciliation Reviewer failed" in report
    assert "### Specialist Feedback (Unchanged)" in report
    assert "Original advice from" in report


def test_smart_panel_includes_only_clouds_mentioned_in_request():
    runner = AgentFactory.create_agent(
        profile_id=AgentFactory.ALL_AGENTS_LABEL,
        llm=object()
    )

    selected = [
        profile_key
        for profile_key, _ in runner._select_specialists(
            "The solution deploys to AWS S3 and Azure Cosmos DB."
        )
    ]

    assert "aws_specialist" in selected
    assert "azure_specialist" in selected
    assert "gcp_specialist" not in selected


def test_smart_panel_routes_cloud_agents_using_uploaded_document_content():
    runner = AgentFactory.create_agent(
        profile_id=AgentFactory.ALL_AGENTS_LABEL,
        llm=object(),
        proposal_uploaded=True
    )

    executed_specialists = []

    def fake_execute(agent, _):
        if agent.agent_config.get("internal_only"):
            if agent.agent_config["role"] == "Technical Feedback Reconciliation Reviewer":
                return "\n\n".join(
                    f"### {config['role']}\nFeedback from {config['role']}."
                    for config in executed_specialists
                )
            return agent.agent_config["role"]

        executed_specialists.append(agent.agent_config)
        return f"Feedback from {agent.agent_config['role']}."

    with (
        patch(
            "src.agent_factory.ProposalProcessor.get_indexed_proposal_text",
            return_value="The production workload runs on Google Cloud Run."
        ),
        patch(
            "src.agent_factory.AgentRunner.execute_sync",
            autospec=True,
            side_effect=fake_execute
        ),
    ):
        report = next(runner.run("Review this design and compare AWS options."))

    assert "### GCP Cloud Infrastructure Architect" in report
    assert "### AWS Cloud Infrastructure Architect" not in report
    assert "### Azure Cloud Infrastructure Architect" not in report


def test_single_specialist_label_still_resolves():
    runner = AgentFactory.create_agent(
        profile_id="Aws Specialist",
        llm=object()
    )

    assert runner.agent_config["role"] == "AWS Cloud Infrastructure Architect"


def test_agent_task_uses_shared_concise_response_format():
    runner = AgentFactory.create_agent(
        profile_id="Aws Specialist",
        llm=object()
    )

    with (
        patch("src.agent_factory.Agent"),
        patch("src.agent_factory.Task") as task_factory,
        patch("src.agent_factory.Crew"),
    ):
        runner.execute_sync("Review this proposal.")
    task_arguments = task_factory.call_args.kwargs
    assert "Review this proposal." in task_arguments["description"]
    assert "Assign exactly ONE rating" in task_arguments["description"]
    assert "**Not Applicable**" in task_arguments["description"]
    assert "ONLY IF your rating is **Fair** or **Bad**" in task_arguments["description"]
    assert "#### Overall Rating: [Good | Fair | Bad | Not Applicable]" in task_arguments["expected_output"]
    assert "without conversational filler" in task_arguments["expected_output"]
    assert "Before every code or configuration snippet, state its target" in task_arguments["description"]
    assert "Create new file: <generic-filename>" in task_arguments["description"]
    assert "**Location:**" in task_arguments["expected_output"]


def test_proposal_search_tool_tracks_retrieved_evidence():
    tool = ProposalSearchTool()

    with patch.object(
        ProposalProcessor,
        "query_proposal",
        return_value="[Proposal Section: Overview]\nArchitecture content."
    ):
        tool._run("architecture")

    assert tool.retrieved_evidence


def test_proposal_search_tool_marks_empty_results_as_not_retrieved():
    tool = ProposalSearchTool()

    with patch.object(
        ProposalProcessor,
        "query_proposal",
        return_value="No matching sections found in proposal."
    ):
        tool._run("architecture")

    assert not tool.retrieved_evidence


def test_runner_displays_prompt_and_missing_document_indicators():
    runner = AgentFactory.create_agent(
        profile_id="Aws Specialist",
        llm=object(),
        proposal_uploaded=True
    )

    with patch.object(runner, "execute_sync", return_value="Review feedback."):
        response = next(runner.run("Assess the proposal."))

    assert "✅ Prompt supplied" in response
    assert "⚠️ No proposal evidence retrieved" in response


def test_runner_displays_retrieved_document_indicator():
    runner = AgentFactory.create_agent(
        profile_id="Aws Specialist",
        llm=object(),
        proposal_uploaded=True
    )
    runner.proposal_evidence_retrieved = True

    with patch.object(runner, "execute_sync", return_value="Review feedback."):
        response = next(runner.run("Assess the proposal."))

    assert "✅ Proposal evidence retrieved" in response


def test_runner_displays_coverage_when_execution_fails():
    runner = AgentFactory.create_agent(
        profile_id="Aws Specialist",
        llm=object(),
        proposal_uploaded=True
    )

    with patch.object(runner, "execute_sync", side_effect=RuntimeError("LLM unavailable")):
        response = next(runner.run("Assess the proposal."))

    assert "⚠️ No proposal evidence retrieved" in response
    assert "Agent Automation Runtime Error: LLM unavailable" in response

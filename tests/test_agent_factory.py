from unittest.mock import Mock, patch
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.agent_factory import (
    AgentFactory,
    AgentRunner,
    SmartPanelRunner,
)
from src.llm_router import LLMRouter
from src.proposal_processor import ProposalProcessor, ProposalSearchTool
from src.solution_architect_triage import AgentAssessment, TriageDecision


_CORE_AGENT_KEYS = (
    "ddd_specialist",
    "clean_arch_specialist",
    "cqrs_specialist",
    "eda_specialist",
    "nfr_specialist",
)


def _triage_decision(selected_keys, solution_related=True):
    selected_keys = set(selected_keys)
    return TriageDecision(
        solution_related=solution_related,
        classification="A business software solution.",
        classification_reason="The request describes a software workflow.",
        agent_assessments=tuple(
            AgentAssessment(
                agent_key=key,
                selected=key in selected_keys,
                reason=(
                    "The described solution benefits from this lens."
                    if key in selected_keys
                    else "The current evidence does not justify this lens."
                ),
            )
            for key in _CORE_AGENT_KEYS
        ),
    )


def _final_review_response():
    return (
        "**Implementation Decision:** Pass\n\n"
        "**Solution Summary**\nThe proposed solution is reviewed.\n\n"
        "**Solution Document Rating:** Good\n\n"
        "**Documentation Summary**\nThe document is reviewed.\n\n"
        "**Testing Plan Coverage:** Good\n\n"
        "**Testing Summary**\nThe testing plan is reviewed."
    )


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


def test_architecture_specialists_treat_existing_state_examples_as_context_only():
    agents = AgentFactory._load_yaml(AgentFactory._AGENTS_CONFIG_PATH)
    tasks = AgentFactory._load_yaml(AgentFactory._TASKS_CONFIG_PATH)
    specialist_keys = {
        "ddd_specialist",
        "clean_arch_specialist",
        "cqrs_specialist",
        "nfr_specialist",
        "eda_specialist",
        "testing_specialist",
        "aws_specialist",
        "azure_specialist",
        "gcp_specialist",
    }

    assert all(agents[key]["task_key"] == "review_task" for key in specialist_keys)
    assert all(
        "Treat clearly identified existing-state examples as context only"
        in agents[key]["backstory"]
        and "do not treat them as the target design"
        in agents[key]["backstory"]
        for key in specialist_keys
    )
    assert "Treat clearly identified existing-state material as context" in tasks[
        "review_task"
    ]["description"]


def test_cloud_agents_apply_well_architected_guidance_proportionately():
    agents = AgentFactory._load_yaml(AgentFactory._AGENTS_CONFIG_PATH)
    cloud_frameworks = {
        "aws_specialist": "AWS Well-Architected Framework",
        "azure_specialist": "Azure Well-Architected Framework",
        "gcp_specialist": "Google Cloud Well-Architected Framework",
    }
    cloud_guidance_files = (
        "knowledge_base/07_cloud_aws.md",
        "knowledge_base/08_cloud_azure.md",
        "knowledge_base/09_cloud_gcp.md",
    )

    for agent_key, framework_name in cloud_frameworks.items():
        backstory = agents[agent_key]["backstory"]
        assert framework_name in backstory
        assert "pragmatically" in backstory or "decision support" in backstory
        assert "data sensitivity" in backstory
        assert "Blocking, Recommended, or Optional" in backstory
        assert "personal project" in backstory

    for guidance_file in cloud_guidance_files:
        guidance = Path(guidance_file).read_text(encoding="utf-8")
        assert guidance.strip()
        assert "not a" in guidance.lower()
        assert "data sensitivity" in guidance.lower()


def test_specialist_recommendations_require_document_locations_and_priorities():
    tasks = AgentFactory._load_yaml(AgentFactory._TASKS_CONFIG_PATH)
    review_task = tasks["review_task"]
    description = review_task["description"]

    assert "priority (Blocking, Recommended, or Optional)" in description
    assert "exact retrieved heading, page, figure" in description
    assert "For an image-only design" in description
    assert "test plan for the solution" in description
    assert "This assessment is advisory" in description
    assert "**Design location:**" in review_task["expected_output"]
    assert "Code location:" in review_task["expected_output"]
    reconciliation = tasks["technical_reconciliation_task"]["description"]
    assert "Preserve the design-document location" in reconciliation
    document_review = tasks["solution_document_review_task"]
    assert "priority (Blocking, Recommended, or Optional)" in document_review["description"]
    assert "**Priority:**" in document_review["expected_output"]


def test_core_specialists_have_knowledge_sources_for_triage():
    agents = AgentFactory._load_yaml(AgentFactory._AGENTS_CONFIG_PATH)
    expected_patterns = {
        "ddd_specialist": "Domain-Driven Design (DDD)",
        "clean_arch_specialist": "Clean Architecture",
        "cqrs_specialist": "Command Query Responsibility Segregation (CQRS)",
        "eda_specialist": "Event-Driven Architecture (EDA)",
        "nfr_specialist": "Non-Functional Requirements (NFR)",
    }

    for agent_key, pattern_name in expected_patterns.items():
        config = agents[agent_key]
        assert config["pattern_name"] == pattern_name
        assert config["knowledge_source"]


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
        patch(
            "src.agent_factory.RAGEngine.query_knowledge_base",
            return_value="[Source: 00_general.md]\nReview principles.",
        ) as knowledge_search,
        patch.object(
            ProposalProcessor,
            "query_proposal",
            return_value="[Architectural Diagram: Overview]\nArchitecture content.",
        ) as proposal_search,
        patch("src.agent_factory.ScopedKnowledgeTool") as knowledge_tool,
        patch("src.agent_factory.ProposalSearchTool") as proposal_tool,
        patch("src.agent_factory.Agent"),
        patch("src.agent_factory.Task") as task_factory,
        patch("src.agent_factory.Crew") as crew_factory,
    ):
        crew_factory.return_value.kickoff.return_value = "Synthesis"
        assert runner.execute_sync("Original specialist feedback") == "Synthesis"

    knowledge_search.assert_called_once_with(
        "Original specialist feedback",
        source_filter="00_general.md",
    )
    proposal_search.assert_called_once()
    knowledge_tool.assert_called_once_with(source_filter="00_general.md")
    assert proposal_tool.called
    assert "Review principles." in task_factory.call_args.kwargs["description"]
    assert "Architecture content." in task_factory.call_args.kwargs["description"]
    assert runner.proposal_evidence_retrieved


def test_agent_execution_uses_iteration_and_time_limits():
    agents = AgentFactory._load_yaml(AgentFactory._AGENTS_CONFIG_PATH)
    tasks = AgentFactory._load_yaml(AgentFactory._TASKS_CONFIG_PATH)
    config = agents["aws_specialist"]
    runner = AgentRunner(
        agent_config=config,
        task_config=tasks[config["task_key"]],
        llm_instance=object()
    )

    with (
        patch(
            "src.agent_factory.RAGEngine.query_knowledge_base",
            return_value="AWS guidance.",
        ),
        patch("src.agent_factory.Agent") as agent_factory,
        patch("src.agent_factory.Task") as task_factory,
        patch("src.agent_factory.Crew") as crew_factory,
    ):
        crew_factory.return_value.kickoff.return_value = "Review"
        runner.execute_sync("Review the proposal.")

    assert agent_factory.call_args.kwargs["max_iter"] == 3
    assert agent_factory.call_args.kwargs["max_execution_time"] == 180
    assert agent_factory.call_args.kwargs["verbose"] is False
    assert crew_factory.call_args.kwargs["verbose"] is False
    task_description = task_factory.call_args.kwargs["description"]
    assert (
        "References to existing-state examples in these instructions are not evidence"
        in task_description
    )
    assert (
        "AI-generated diagram descriptions are fallible interpretations"
        in task_description
    )


def test_agent_retries_unexecuted_tool_json_without_tools():
    agents = AgentFactory._load_yaml(AgentFactory._AGENTS_CONFIG_PATH)
    tasks = AgentFactory._load_yaml(AgentFactory._TASKS_CONFIG_PATH)
    config = agents["aws_specialist"]
    runner = AgentRunner(
        agent_config=config,
        task_config=tasks[config["task_key"]],
        llm_instance=object(),
    )
    with (
        patch(
            "src.agent_factory.RAGEngine.query_knowledge_base",
            return_value="AWS guidance.",
        ),
        patch("src.agent_factory.Agent") as agent_factory,
        patch("src.agent_factory.Task"),
        patch("src.agent_factory.Crew") as crew_factory,
    ):
        crew_factory.return_value.kickoff.side_effect = [
            '{"query": "aws rules"}',
            "A formatted review.",
        ]
        result = runner.execute_sync("Review the proposal.")

    assert result == "A formatted review."
    assert crew_factory.call_count == 2
    assert agent_factory.call_args.kwargs["tools"] == []


def test_local_qwen_retries_no_content_once_with_bounded_tool_free_call():
    agents = AgentFactory._load_yaml(AgentFactory._AGENTS_CONFIG_PATH)
    tasks = AgentFactory._load_yaml(AgentFactory._TASKS_CONFIG_PATH)
    config = agents["aws_specialist"]
    retry_llm = object()
    llm = SimpleNamespace(
        provider="ollama",
        model="qwen3.5:9b",
        model_copy=lambda *, update: retry_llm,
    )
    runner = AgentRunner(
        agent_config=config,
        task_config=tasks[config["task_key"]],
        llm_instance=llm,
    )

    with (
        patch(
            "src.agent_factory.RAGEngine.query_knowledge_base",
            return_value="AWS guidance.",
        ),
        patch("src.agent_factory.Agent") as agent_factory,
        patch("src.agent_factory.Task"),
        patch("src.agent_factory.Crew") as crew_factory,
    ):
        crew_factory.return_value.kickoff.side_effect = [
            RuntimeError("The provider returned no content for model 'qwen3.5:9b'."),
            "Recovered review.",
        ]
        result = runner.execute_sync("Review the proposal.")

    assert result == "Recovered review."
    assert crew_factory.call_count == 2
    assert agent_factory.call_args.kwargs["llm"] is retry_llm
    assert agent_factory.call_args.kwargs["tools"] == []
    assert agent_factory.call_args.kwargs["max_iter"] == 1
    assert agent_factory.call_args.kwargs["max_execution_time"] == 60


def test_non_local_qwen_no_content_error_is_not_retried():
    agents = AgentFactory._load_yaml(AgentFactory._AGENTS_CONFIG_PATH)
    tasks = AgentFactory._load_yaml(AgentFactory._TASKS_CONFIG_PATH)
    config = agents["aws_specialist"]
    runner = AgentRunner(
        agent_config=config,
        task_config=tasks[config["task_key"]],
        llm_instance=SimpleNamespace(provider="bedrock", model="qwen3.5:9b"),
    )

    with (
        patch(
            "src.agent_factory.RAGEngine.query_knowledge_base",
            return_value="AWS guidance.",
        ),
        patch("src.agent_factory.Agent"),
        patch("src.agent_factory.Task"),
        patch("src.agent_factory.Crew") as crew_factory,
    ):
        crew_factory.return_value.kickoff.side_effect = RuntimeError(
            "The provider returned no content for model 'qwen3.5:9b'."
        )
        with pytest.raises(RuntimeError, match="provider returned no content"):
            runner.execute_sync("Review the proposal.")

    crew_factory.assert_called_once()


@pytest.mark.parametrize(
    ("provider", "should_override"),
    [("ollama", True), ("bedrock", False)],
)
def test_final_review_token_override_is_local_only(provider, should_override):
    agents = AgentFactory._load_yaml(AgentFactory._AGENTS_CONFIG_PATH)
    tasks = AgentFactory._load_yaml(AgentFactory._TASKS_CONFIG_PATH)
    config = agents["final_review_agent"]
    llm_with_override = object()
    llm = SimpleNamespace(
        provider=provider,
        model_copy=Mock(return_value=llm_with_override),
    )
    runner = AgentRunner(
        agent_config=config,
        task_config=tasks[config["task_key"]],
        llm_instance=llm,
    )

    with (
        patch("src.agent_factory.Agent") as agent_factory,
        patch("src.agent_factory.Task"),
        patch("src.agent_factory.Crew") as crew_factory,
    ):
        crew_factory.return_value.kickoff.return_value = "Overall review."
        runner.execute_sync("Summarize the completed reviews.")

    if should_override:
        llm.model_copy.assert_called_once_with(update={"max_tokens": 2048})
        assert agent_factory.call_args.kwargs["llm"] is llm_with_override
    else:
        llm.model_copy.assert_not_called()
        assert agent_factory.call_args.kwargs["llm"] is llm


def test_agent_runner_removes_code_section_when_rating_is_good():
    agents = AgentFactory._load_yaml(AgentFactory._AGENTS_CONFIG_PATH)
    tasks = AgentFactory._load_yaml(AgentFactory._TASKS_CONFIG_PATH)
    config = agents["ddd_specialist"]
    runner = AgentRunner(
        agent_config=config,
        task_config=tasks[config["task_key"]],
        llm_instance=object()
    )
    model_response = (
        "#### Overall Rating: Good\n\n"
        "**General Assessment**\nNo structural rework is needed.\n\n"
        "**Recommended Code / Structural Changes**\n"
        "*(Include this section ONLY if Rating is Fair or Bad.)*"
    )

    with (
        patch(
            "src.agent_factory.RAGEngine.query_knowledge_base",
            return_value="DDD guidance.",
        ),
        patch("src.agent_factory.Agent"),
        patch("src.agent_factory.Task"),
        patch("src.agent_factory.Crew") as crew_factory,
    ):
        crew_factory.return_value.kickoff.return_value = model_response
        response = runner.execute_sync("Review the proposal.")

    assert "General Assessment" in response
    assert "Recommended Code / Structural Changes" not in response


def test_local_llm_has_bounded_output_and_request_time():
    with patch("src.llm_router.LLM") as llm_factory:
        LLMRouter.create_backend(LLMRouter.get_supported_backends()[0])

    assert llm_factory.call_args.kwargs["max_tokens"] == 1024
    assert llm_factory.call_args.kwargs["timeout"] == 90
    assert "num_ctx" not in llm_factory.call_args.kwargs


def test_document_review_task_reports_evidence_for_all_general_attributes():
    tasks = AgentFactory._load_yaml(AgentFactory._TASKS_CONFIG_PATH)
    review_task = tasks["solution_document_review_task"]
    standards = Path("knowledge_base/00_general.md").read_text(encoding="utf-8")
    expected_output = review_task["expected_output"]

    assert all(
        status in expected_output
        for status in ("Found", "Not found", "Unable to assess")
    )
    assert "exactly one row for each of the 12 checklist" in expected_output
    assert "Assess all 12 attributes in 00_general.md" in review_task["description"]
    assert "#### Solution Document Peer Review" in expected_output
    assert "#### Checklist Coverage" in expected_output
    assert "#### Solution Complexity, Unknowns & Risk" in expected_output
    assert "#### Documentation Errors & Contradictions" in expected_output
    assert "#### Alignment with Reconciled Technical Feedback" in expected_output

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
    assert all(name in expected_output for name in attribute_names)


def test_final_review_task_lists_blocking_changes_only_for_fail():
    tasks = AgentFactory._load_yaml(AgentFactory._TASKS_CONFIG_PATH)
    review_task = tasks["final_review_task"]
    expected_output = review_task["expected_output"]

    assert "likely to work" in review_task["description"]
    assert "meet the functional requirements stated" in review_task["description"]
    assert "architectural anti-pattern" in review_task["description"]
    assert "ordinary improvement recommendation alone" in review_task["description"]
    assert "following sections in this exact order" in expected_output
    assert "**Implementation Decision:** [Pass or Fail]" in expected_output
    assert "**Changes Required for Pass**" in expected_output
    assert "only when the decision is Fail" in expected_output
    assert "single word Pass or Fail" in expected_output
    assert "highest to lowest priority" in expected_output
    assert "source specialist" in review_task["description"]
    assert "exact design-document area to update" in review_task["description"]
    assert "Do not list recommended or optional improvements as approval blockers." in review_task["description"]
    assert "**Solution Summary**" in expected_output
    assert "**Solution Document Rating:** Good / Fair / Bad" in expected_output
    assert "**Documentation Summary**" in expected_output
    assert "**Testing Plan Coverage:** Good / Fair / Bad" in expected_output
    assert "**Testing Summary**" in expected_output
    section_labels = [
        "**Implementation Decision:**",
        "**Changes Required for Pass**",
        "**Solution Summary**",
        "**Solution Document Rating:**",
        "**Documentation Summary**",
        "**Testing Plan Coverage:**",
        "**Testing Summary**",
    ]
    assert [expected_output.index(label) for label in section_labels] == sorted(
        expected_output.index(label) for label in section_labels
    )
    assert "Needs Revision" not in expected_output
    assert "Unable to assess" not in expected_output
    assert "covers most important areas" in review_task["description"]
    assert "adequately explains the project concept" in review_task["description"]
    assert "vital information is missing" in review_task["description"]
    assert "must not affect the implementation decision" in review_task["description"]


def test_smart_panel_selects_triaged_domains_and_always_runs_testing():
    runner = AgentFactory.create_agent(
        profile_id=AgentFactory.ALL_AGENTS_LABEL,
        llm=object()
    )
    additional = runner._select_additional_specialists(
        "The target deploys to AWS using S3 and Lambda, with bounded contexts."
    )

    selected = [
        profile_key
        for profile_key, _ in runner._select_specialists(
            "The target deploys to AWS using S3 and Lambda, with bounded contexts.",
            triage_selected=("ddd_specialist", "cqrs_specialist"),
            additional_selected=additional,
        )
    ]

    assert selected == [
        "ddd_specialist",
        "cqrs_specialist",
        "testing_specialist",
        "aws_specialist",
    ]


def test_smart_panel_can_select_more_than_four_relevant_specialists():
    runner = AgentFactory.create_agent(
        profile_id=AgentFactory.ALL_AGENTS_LABEL,
        llm=object()
    )
    routing_text = (
        "The target deploys to AWS using S3 and Lambda, Azure using Cosmos DB, "
        "and Google Cloud using GKE and Cloud Run."
    )
    additional = runner._select_additional_specialists(routing_text)
    selected = runner._select_specialists(
        routing_text,
        triage_selected=_CORE_AGENT_KEYS,
        additional_selected=additional,
    )

    assert len(selected) > 4
    assert set(_CORE_AGENT_KEYS).issubset({key for key, _ in selected})


def test_smart_panel_runs_triage_selected_specialists_and_streams_progress():
    runner = AgentFactory.create_agent(
        profile_id=AgentFactory.ALL_AGENTS_LABEL,
        llm=object()
    )
    triage = _triage_decision(("clean_arch_specialist", "cqrs_specialist"))
    additional = runner._select_additional_specialists("Review the solution.")
    selected_specialists = runner._select_specialists(
        "Review the solution.",
        triage_selected=triage.selected_agent_keys,
        additional_selected=additional,
    )

    def fake_execute(agent, _):
        if agent.agent_config.get("internal_only"):
            if agent.agent_config["role"] == "Technical Feedback Reconciliation Reviewer":
                return "\n\n".join(
                    f"### {config['role']}\nFeedback from {config['role']}."
                    for _, config in selected_specialists
                )
            if agent.agent_config["role"] == "Overall Solution Review Judge":
                return _final_review_response()
            return agent.agent_config["role"]
        return f"Feedback from {agent.agent_config['role']}."

    with (
        patch(
            "src.agent_factory.SolutionArchitectTriageAgent.assess",
            return_value=triage,
        ),
        patch(
            "src.agent_factory.AgentRunner.execute_sync",
            autospec=True,
            side_effect=fake_execute
        ),
    ):
        output = list(runner.run("Review the solution."))
        report = output[-1]

    for agent_config in runner.agents_metadata.values():
        if agent_config.get("internal_only"):
            assert f"### {agent_config['role']}" not in report
            continue
        if any(config is agent_config for _, config in selected_specialists):
            assert f"### {agent_config['role']}" in report
        else:
            assert f"### {agent_config['role']}" not in report
    assert any("running specialist" in item for item in output[:-1])
    assert "## Solution Classification" in report
    assert "Specialists Selected" in report
    assert "Clean Architecture Reviewer" in report
    assert "CQRS & Data Flow Architect" in report
    assert "Testing & Verification Strategist" in report
    assert "Domain-Driven Design Specialist" in report
    assert "## Overall Solution Review" in report
    assert "## Specialist Feedback" in report
    assert "## Technical Feedback Reconciliation" not in report
    assert "## Solution Document Peer Review" not in report


def test_smart_panel_synthesizes_document_review_into_final_output():
    runner = AgentFactory.create_agent(
        profile_id=AgentFactory.ALL_AGENTS_LABEL,
        llm=object()
    )
    triage = _triage_decision(("clean_arch_specialist", "cqrs_specialist"))

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
        if agent_key == "testing_specialist":
            return (
                "**Testing Plan Coverage**\n"
                "**Coverage:** Fair\n"
                "**Key Areas to Test**\n"
                "* Verify event retries are idempotent and failures reach a dead-letter queue."
            )
        if agent_key == "final_review_agent":
            assert "Revised advice." in request
            assert "Document peer review recommendations." in request
            assert "TESTING & VERIFICATION REVIEW (ADVISORY" in request
            assert "dead-letter queue" in request
            return (
                "**Implementation Decision:** Pass\n\n"
                "**Changes Required for Pass**\n"
                "None — no blocking changes are required.\n\n"
                "**Solution Summary**\n"
                "The booking design appears workable.\n\n"
                "**Solution Document Rating:** Fair\n\n"
                "**Documentation Summary**\n"
                "The proposal is understandable but omits important decisions.\n"
                "- Clarify service ownership and persistence.\n\n"
                "**Testing Plan Coverage:** Fair\n\n"
                "**Testing Summary**\n"
                "Test retries, idempotency, and dead-letter handling."
            )
        return f"Original advice from {agent.agent_config['role']}."

    with (
        patch(
            "src.agent_factory.SolutionArchitectTriageAgent.assess",
            return_value=triage,
        ),
        patch(
            "src.agent_factory.AgentRunner.execute_sync",
            autospec=True,
            side_effect=fake_execute
        ),
    ):
        report = list(runner.run("Review the solution."))[-1]

    assert "Revised advice." in report
    assert "**Reconciliation note:** Combined conflicting proposals." in report
    assert "Document peer review recommendations." not in report
    assert "**Solution Document Rating:**\nFair" in report
    assert "**Documentation Summary**" in report
    assert "- Clarify service ownership and persistence." in report
    assert "**Solution Summary**" in report
    assert "**Changes Required for Pass**" not in report
    assert "**Implementation Decision:**\nPass" in report
    assert "no architectural anti-pattern or severe direct violation" not in report
    assert "**Testing Plan Coverage:**\nFair" in report
    assert "**Testing Summary**" in report
    assert "Test retries, idempotency, and dead-letter handling." in report
    assert "Document peer review recommendations." not in report
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
    triage = _triage_decision(("clean_arch_specialist", "cqrs_specialist"))

    def fail_reconciliation(agent, _):
        if agent.agent_config["role"] == "Technical Feedback Reconciliation Reviewer":
            raise RuntimeError("synthesis unavailable")
        if agent.agent_config["role"] == "Solution Document Architecture Peer Reviewer":
            return "Document peer review."
        if agent.agent_config["role"] == "Overall Solution Review Judge":
            return (
                "**Implementation Decision:** Pass\n\n"
                "**Solution Summary**\nThe review package was assessed.\n\n"
                "**Solution Document Rating:** Good\n\n"
                "**Documentation Summary**\nThe proposal is documented.\n\n"
                "**Testing Plan Coverage:** Good\n\n"
                "**Testing Summary**\nThe test plan was reviewed."
            )
        return f"Original advice from {agent.agent_config['role']}."

    with (
        patch(
            "src.agent_factory.SolutionArchitectTriageAgent.assess",
            return_value=triage,
        ),
        patch(
            "src.agent_factory.AgentRunner.execute_sync",
            autospec=True,
            side_effect=fail_reconciliation
        ),
    ):
        report = list(runner.run("Review the solution."))[-1]

    assert "⚠️ Technical Feedback Reconciliation Reviewer failed" in report
    assert "### Specialist Feedback (Unchanged)" in report
    assert "Original advice from" in report


def test_smart_panel_includes_only_clouds_mentioned_in_request():
    runner = AgentFactory.create_agent(
        profile_id=AgentFactory.ALL_AGENTS_LABEL,
        llm=object()
    )
    additional = runner._select_additional_specialists(
        "The solution deploys to AWS using S3 and to Azure using Cosmos DB."
    )

    selected = [
        profile_key
        for profile_key, _ in runner._select_specialists(
            "The solution deploys to AWS using S3 and to Azure using Cosmos DB.",
            triage_selected=("clean_arch_specialist",),
            additional_selected=additional,
        )
    ]

    assert "aws_specialist" in selected
    assert "azure_specialist" in selected
    assert "gcp_specialist" not in selected


def test_cloud_specialists_ignore_incidental_mentions_and_comparisons():
    runner = AgentFactory.create_agent(
        profile_id=AgentFactory.ALL_AGENTS_LABEL,
        llm=object(),
    )
    routing_text = (
        "Compare AWS Lambda, Azure Cosmos DB, and Google Cloud Run as possible options. "
        "No target platform has been selected."
    )

    cloud_specialists = {
        profile_key
        for profile_key, _ in runner._select_additional_specialists(routing_text)
        if profile_key in {"aws_specialist", "azure_specialist", "gcp_specialist"}
    }

    assert cloud_specialists == set()


def test_cloud_specialists_route_on_clear_usage_or_diagram_services():
    runner = AgentFactory.create_agent(
        profile_id=AgentFactory.ALL_AGENTS_LABEL,
        llm=object(),
    )
    routing_text = (
        "The workload runs on AWS in us-east-1. Azure hosts the identity service "
        "with Entra ID. The architecture diagram contains GKE and Cloud Run."
    )

    cloud_specialists = {
        profile_key
        for profile_key, _ in runner._select_additional_specialists(routing_text)
        if profile_key in {"aws_specialist", "azure_specialist", "gcp_specialist"}
    }

    assert cloud_specialists == {
        "aws_specialist",
        "azure_specialist",
        "gcp_specialist",
    }


def test_smart_panel_routes_cloud_agents_using_uploaded_document_content():
    runner = AgentFactory.create_agent(
        profile_id=AgentFactory.ALL_AGENTS_LABEL,
        llm=object(),
        proposal_uploaded=True
    )
    triage = _triage_decision(("clean_arch_specialist", "cqrs_specialist"))

    executed_specialists = []

    def fake_execute(agent, _):
        if agent.agent_config.get("internal_only"):
            if agent.agent_config["role"] == "Technical Feedback Reconciliation Reviewer":
                return "\n\n".join(
                    f"### {config['role']}\nFeedback from {config['role']}."
                    for config in executed_specialists
                )
            if agent.agent_config["role"] == "Overall Solution Review Judge":
                return _final_review_response()
            return agent.agent_config["role"]

        executed_specialists.append(agent.agent_config)
        return f"Feedback from {agent.agent_config['role']}."

    with (
        patch(
            "src.agent_factory.ProposalProcessor.get_indexed_proposal_text",
            return_value="The production workload runs on Google Cloud Run."
        ),
        patch(
            "src.agent_factory.SolutionArchitectTriageAgent.assess",
            return_value=triage,
        ),
        patch(
            "src.agent_factory.AgentRunner.execute_sync",
            autospec=True,
            side_effect=fake_execute
        ),
    ):
        report = list(runner.run("Review this design and compare AWS options."))[-1]

    assert "### GCP Cloud Infrastructure Architect" in report
    assert "### AWS Cloud Infrastructure Architect" not in report
    assert "### Azure Cloud Infrastructure Architect" not in report


def test_smart_panel_rejects_unrelated_content_before_running_specialists():
    runner = AgentFactory.create_agent(
        profile_id=AgentFactory.ALL_AGENTS_LABEL,
        llm=object(),
    )
    triage = _triage_decision((), solution_related=False)

    with (
        patch(
            "src.agent_factory.SolutionArchitectTriageAgent.assess",
            return_value=triage,
        ),
        patch("src.agent_factory.AgentRunner.execute_sync") as execute,
    ):
        output = list(runner.run("Tell me about sourdough bread."))

    assert len(output) == 2
    assert "⛔ Smart Panel review not started" in output[-1]
    assert "## Solution Classification" in output[-1]
    execute.assert_not_called()


def test_smart_panel_runs_more_than_four_specialists_without_limiting_triage():
    runner = AgentFactory.create_agent(
        profile_id=AgentFactory.ALL_AGENTS_LABEL,
        llm=object(),
    )
    user_request = (
        "Review domain modeling, production, async, and testing. The target deploys "
        "to AWS using S3 and Lambda, Azure using Cosmos DB, and Google Cloud using "
        "GKE and Cloud Run."
    )
    triage = _triage_decision(_CORE_AGENT_KEYS)
    routing_text = user_request.casefold()
    additional = runner._select_additional_specialists(routing_text)
    expected_specialists = runner._select_specialists(
        routing_text,
        triage_selected=triage.selected_agent_keys,
        additional_selected=additional,
    )
    executed_specialists = []

    def fake_execute(agent, _):
        if agent.agent_config.get("internal_only"):
            if agent.agent_config["role"] == "Overall Solution Review Judge":
                return _final_review_response()
            return f"Review from {agent.agent_config['role']}."
        executed_specialists.append(agent.agent_config["role"])
        return f"Review from {agent.agent_config['role']}."

    with (
        patch(
            "src.agent_factory.SolutionArchitectTriageAgent.assess",
            return_value=triage,
        ) as assess,
        patch(
            "src.agent_factory.AgentRunner.execute_sync",
            autospec=True,
            side_effect=fake_execute,
        ),
    ):
        list(runner.run(user_request))

    assert len(expected_specialists) > 4
    assert len(executed_specialists) == len(expected_specialists)
    assert "available_agent_slots" not in assess.call_args.kwargs


def test_single_specialist_label_still_resolves():
    runner = AgentFactory.create_agent(
        profile_id="Aws Specialist",
        llm=object()
    )

    assert runner.agent_config["role"] == "AWS Cloud Infrastructure Architect"
    assert runner.single_specialist


def test_single_gcp_review_runs_only_gcp_and_omits_testing_scope():
    runner = AgentFactory.create_agent(
        profile_id="Gcp Specialist",
        llm=object(),
    )

    with (
        patch(
            "src.agent_factory.RAGEngine.query_knowledge_base",
            return_value="Google Cloud guidance.",
        ),
        patch("src.agent_factory.Agent") as agent_factory,
        patch("src.agent_factory.Task") as task_factory,
        patch("src.agent_factory.Crew") as crew_factory,
    ):
        crew_factory.return_value.kickoff.return_value = "GCP review."
        runner.execute_sync("Review this solution, including testing.")

    assert agent_factory.call_count == 1
    assert agent_factory.call_args.kwargs["role"] == "GCP Cloud Infrastructure Architect"
    assert len(crew_factory.call_args.kwargs["agents"]) == 1
    task_arguments = task_factory.call_args.kwargs
    assert "SINGLE-SPECIALIST SCOPE" in task_arguments["description"]
    assert "Do not assess test-plan coverage" in task_arguments["description"]
    assert "Testing Plan Coverage" not in task_arguments["expected_output"]
    assert "Key Areas to Test" not in task_arguments["expected_output"]


def test_single_testing_specialist_retains_testing_assessment():
    runner = AgentFactory.create_agent(
        profile_id="Testing Specialist",
        llm=object(),
    )

    with (
        patch(
            "src.agent_factory.RAGEngine.query_knowledge_base",
            return_value="Testing guidance.",
        ),
        patch("src.agent_factory.Agent"),
        patch("src.agent_factory.Task") as task_factory,
        patch("src.agent_factory.Crew") as crew_factory,
    ):
        crew_factory.return_value.kickoff.return_value = "Testing review."
        runner.execute_sync("Review this solution.")

    task_arguments = task_factory.call_args.kwargs
    assert "Testing Plan Coverage" in task_arguments["expected_output"]
    assert "Key Areas to Test" in task_arguments["expected_output"]
    assert "cover testing only" in task_arguments["description"]


def test_agent_task_uses_shared_concise_response_format():
    runner = AgentFactory.create_agent(
        profile_id="Aws Specialist",
        llm=object()
    )

    with (
        patch(
            "src.agent_factory.RAGEngine.query_knowledge_base",
            return_value="AWS guidance.",
        ),
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
    assert "Before every code or configuration snippet, also state its code target" in task_arguments["description"]
    assert "Create new file: <generic-filename>" in task_arguments["description"]
    assert "**Design location:**" in task_arguments["expected_output"]


def test_proposal_search_tool_tracks_retrieved_evidence():
    tool = ProposalSearchTool()

    with patch.object(
        ProposalProcessor,
        "query_proposal",
        return_value="[Architectural Diagram: Overview]\nArchitecture content."
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


def test_proposal_search_tool_discloses_generated_diagram_description_limits():
    description = ProposalSearchTool().description
    assert "not verbatim OCR" in description
    assert "does not show the original image" in description


def test_internal_review_prompts_do_not_treat_vision_descriptions_as_ocr():
    tasks = AgentFactory._load_yaml(AgentFactory._TASKS_CONFIG_PATH)

    for task_key in (
        "technical_reconciliation_task",
        "solution_document_review_task",
        "final_review_task",
    ):
        assert "AI-generated diagram descriptions" in tasks[task_key]["description"]
        assert "not verified OCR" in tasks[task_key]["description"]


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

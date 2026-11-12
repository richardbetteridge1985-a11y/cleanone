import json
from unittest.mock import patch

import pytest

from src.agent_factory import AgentFactory
from src.proposal_processor import ProposalProcessor
from src.rag_engine import RAGEngine
from src.solution_architect_triage import SolutionArchitectTriageAgent


_CORE_AGENT_KEYS = (
    "ddd_specialist",
    "clean_arch_specialist",
    "cqrs_specialist",
    "eda_specialist",
    "nfr_specialist",
)


def _response(selected_keys=(), solution_related=True):
    selected_keys = set(selected_keys)
    return json.dumps({
        "solution_related": solution_related,
        "classification": "An appointment-booking application.",
        "classification_reason": "The material describes a software booking workflow.",
        "agent_assessments": [
            {
                "agent_key": key,
                "selected": key in selected_keys,
                "reason": (
                    "The described solution supports this domain."
                    if key in selected_keys
                    else "The described solution does not require this domain."
                ),
            }
            for key in _CORE_AGENT_KEYS
        ],
    })


class FakeLLM:
    def __init__(self, response):
        self.responses = response if isinstance(response, list) else [response]
        self.messages = None
        self.call_count = 0

    def call(self, messages):
        self.messages = messages
        self.call_count += 1
        return self.responses.pop(0)


def test_assesses_all_domains_with_proposal_and_knowledge_evidence():
    agents = AgentFactory._load_yaml(AgentFactory._AGENTS_CONFIG_PATH)
    triage = SolutionArchitectTriageAgent(agents, max_specialists=4)
    llm = FakeLLM(_response(("ddd_specialist", "nfr_specialist")))
    proposal_evidence = (
        "[Proposal Section: Overview]\n"
        "A web application lets customers book appointments."
    )

    with (
        patch.object(
            ProposalProcessor,
            "query_proposal",
            return_value=proposal_evidence,
        ) as proposal_query,
        patch.object(
            RAGEngine,
            "query_knowledge_base",
            return_value="Applicability guidance for this domain.",
        ) as knowledge_query,
    ):
        decision = triage.assess(
            llm=llm,
            user_request="Review the booking application.",
            proposal_uploaded=True,
            available_agent_slots=2,
        )

    assert decision.solution_related
    assert decision.classification == "An appointment-booking application."
    assert decision.selected_agent_keys == ("ddd_specialist", "nfr_specialist")
    assert proposal_query.call_args.kwargs["n_results"] == 6
    assert knowledge_query.call_count == len(_CORE_AGENT_KEYS)
    assert [
        call.kwargs["source_filter"]
        for call in knowledge_query.call_args_list
    ] == [agents[key]["knowledge_source"] for key in _CORE_AGENT_KEYS]
    assert all(
        call.kwargs["n_results"] == 2
        for call in knowledge_query.call_args_list
    )
    evidence = llm.messages[1]["content"]
    assert proposal_evidence in evidence
    for key in _CORE_AGENT_KEYS:
        assert agents[key]["knowledge_source"] in evidence


def test_rejects_selection_over_available_slots():
    with pytest.raises(ValueError, match="safe run limit"):
        SolutionArchitectTriageAgent._parse_response(
            _response(("ddd_specialist", "nfr_specialist")),
            available_agent_slots=1,
        )


def test_retries_once_when_model_omits_a_core_assessment():
    agents = AgentFactory._load_yaml(AgentFactory._AGENTS_CONFIG_PATH)
    triage = SolutionArchitectTriageAgent(agents, max_specialists=4)
    incomplete = json.loads(_response(("ddd_specialist",)))
    incomplete["agent_assessments"].pop()
    llm = FakeLLM([
        json.dumps(incomplete),
        _response(("ddd_specialist",)),
    ])

    with patch.object(
        RAGEngine,
        "query_knowledge_base",
        return_value="Applicability guidance.",
    ):
        decision = triage.assess(
            llm=llm,
            user_request="Review an appointment booking application.",
            proposal_uploaded=False,
            available_agent_slots=4,
        )

    assert llm.call_count == 2
    assert len(decision.agent_assessments) == 5
    assert decision.selected_agent_keys == ("ddd_specialist",)


def test_unrelated_material_cannot_select_specialists():
    with pytest.raises(ValueError, match="Unrelated material"):
        SolutionArchitectTriageAgent._parse_response(
            _response(("ddd_specialist",), solution_related=False),
            available_agent_slots=2,
        )


def test_propagates_knowledge_retrieval_errors():
    agents = AgentFactory._load_yaml(AgentFactory._AGENTS_CONFIG_PATH)
    triage = SolutionArchitectTriageAgent(agents, max_specialists=4)

    with patch.object(
        RAGEngine,
        "query_knowledge_base",
        return_value="Error executing context retrieval logic: unavailable",
    ):
        with pytest.raises(RuntimeError, match="Could not retrieve triage guidance"):
            triage.assess(
                llm=FakeLLM(_response()),
                user_request="An appointment booking app.",
                proposal_uploaded=False,
                available_agent_slots=4,
            )

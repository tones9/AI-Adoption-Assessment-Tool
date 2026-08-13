from ai_adoption_engine.decision.capabilities import map_capabilities
from ai_adoption_engine.models.enums import Capability
from ai_adoption_engine.models.process import CapabilitySignals


def test_mapper_returns_canonical_capabilities_in_stable_order() -> None:
    signals = CapabilitySignals(
        creates_new_content=True,
        searches_reference_knowledge=True,
        routes_or_orchestrates_work=True,
    )
    assert map_capabilities(signals) == [
        Capability.GENERATIVE_AI,
        Capability.KNOWLEDGE_RETRIEVAL,
        Capability.WORKFLOW_AUTOMATION,
    ]


def test_workflow_automation_is_mapped_without_claiming_it_is_ai() -> None:
    capabilities = map_capabilities(
        CapabilitySignals(routes_or_orchestrates_work=True)
    )
    assert capabilities == [Capability.WORKFLOW_AUTOMATION]


def test_no_signals_produce_no_capability() -> None:
    assert map_capabilities(CapabilitySignals()) == []


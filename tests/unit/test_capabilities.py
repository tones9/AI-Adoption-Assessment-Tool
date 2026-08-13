from ai_adoption_engine.decision.capabilities import map_capabilities
from ai_adoption_engine.models.enums import Capability, KnowledgeState
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


def test_omitted_signals_are_explicitly_unknown() -> None:
    signal = CapabilitySignals().categorises_items
    assert signal.value is None
    assert signal.knowledge_state is KnowledgeState.UNKNOWN
    assert signal.evidence_ids == []


def test_legacy_booleans_are_migrated_as_explicit_known_values() -> None:
    signals = CapabilitySignals(categorises_items=False, creates_new_content=True)
    assert signals.categorises_items.value is False
    assert signals.categorises_items.knowledge_state is KnowledgeState.KNOWN
    assert signals.creates_new_content.value is True
    assert signals.creates_new_content.knowledge_state is KnowledgeState.KNOWN
    assert signals.creates_new_content.evidence_ids == []
    assert "legacy explicit boolean" in signals.creates_new_content.rationale


def test_only_explicitly_true_signals_map_to_capabilities() -> None:
    signals = CapabilitySignals(
        categorises_items={
            "value": False,
            "knowledge_state": "inferred",
            "rationale": "The source suggests no categorisation activity.",
            "confidence": 0.7,
        },
        creates_new_content={
            "value": True,
            "knowledge_state": "inferred",
            "rationale": "Drafting is described indirectly.",
            "confidence": 0.8,
        },
    )
    assert map_capabilities(signals) == [Capability.GENERATIVE_AI]

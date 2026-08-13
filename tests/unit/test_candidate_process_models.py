import pytest
from pydantic import ValidationError

from ai_adoption_engine.models.candidate_process import (
    CapabilitySignalName,
    CandidateAssertion,
    CandidateCapabilitySignal,
    CandidateCharacteristic,
    CandidateOrdinalAssertion,
    CandidateTaskCharacteristics,
)
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState


def _unknown(assertion_type: type[CandidateAssertion] = CandidateAssertion):
    return assertion_type(
        value=None,
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale="Not stated.",
        evidence=[],
    )


def test_unknown_assertion_cannot_receive_a_default_value() -> None:
    with pytest.raises(ValidationError, match="null value"):
        CandidateOrdinalAssertion(
            value=3,
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="Not stated.",
            evidence=[],
        )


def test_inferred_assertion_requires_confidence_and_resolved_evidence() -> None:
    with pytest.raises(ValidationError, match="resolved evidence"):
        CandidateAssertion[str](
            value="Agent",
            knowledge_state=KnowledgeState.INFERRED,
            rationale="Implied by the source.",
            evidence=[],
            confidence=0.7,
        )


def test_task_characteristics_require_every_criterion_explicitly() -> None:
    criteria = [
        CandidateCharacteristic(name=name, assertion=_unknown(CandidateOrdinalAssertion))
        for name in CriterionName
        if name is not CriterionName.REPETITION
    ]
    signals = [
        CandidateCapabilitySignal(name=name, assertion=_unknown())
        for name in CapabilitySignalName
    ]
    with pytest.raises(ValidationError, match="explicitly represented"):
        CandidateTaskCharacteristics(
            criteria=criteria,
            human_accountability_required=_unknown(),
            capability_signals=signals,
        )

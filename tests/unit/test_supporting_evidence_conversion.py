from ai_adoption_engine.models.formal_evidence import ReadinessStatus
from ai_adoption_engine.supporting_evidence.conversion import (
    MappingQueueStatus,
    SupportingEvidencePreparationState,
)


def test_mapping_queue_statuses_are_explicit_and_closed() -> None:
    assert {item.value for item in MappingQueueStatus} == {
        "AWAITING_REVIEW",
        "AWAITING_MAPPING",
        "MAPPED",
        "CONTEXT_ONLY",
        "UNRESOLVED",
        "REJECTED_AUDIT_ONLY",
        "STALE_HISTORICAL",
    }


def test_preparation_state_exposes_readiness_not_formal_sufficiency() -> None:
    fields = SupportingEvidencePreparationState.__dataclass_fields__
    assert "effective_status" in fields
    assert set(ReadinessStatus) == {
        ReadinessStatus.NOT_READY,
        ReadinessStatus.READY_TO_ATTEMPT,
    }
    forbidden = {
        "evidence_sufficient",
        "gate_passed",
        "formal_outcome",
        "approved",
        "decision_package",
    }
    assert forbidden.isdisjoint(fields)

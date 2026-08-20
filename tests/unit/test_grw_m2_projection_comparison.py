from __future__ import annotations

from ai_adoption_engine.grw.m2.models import M2ArtifactReference
from tests.integration.test_grw_m2_m1_lifecycle import _full_lifecycle


def test_successor_projection_changes_only_data_readiness_and_comparison_is_repeatable(tmp_path) -> None:
    baseline, assessment_id, service, _, run_id, baseline_ref, gap, _, successor, _, package, comparison = _full_lifecycle(tmp_path)
    base = service._load_baseline_artifact(baseline_ref.approved_review).payload.business_process
    changed = successor.successor_process
    assert len(changed.evidence) == len(base.evidence) + 1
    for old, new in zip(base.steps, changed.steps, strict=True):
        old_payload, new_payload = old.model_dump(mode="json"), new.model_dump(mode="json")
        old_payload["characteristics"].pop("data_readiness")
        new_payload["characteristics"].pop("data_readiness")
        assert old_payload == new_payload
    again = service.repository.load_artifact_reference(run_id, __import__("ai_adoption_engine.grw.m2.models", fromlist=["M2ArtifactType"]).M2ArtifactType.BASELINE_SUCCESSOR_COMPARISON)
    assert again is not None
    assert service.repository.load_artifact(again.artifact_id) == comparison


def test_phase5_successor_adapter_rejects_a_forged_non_target_change(tmp_path) -> None:
    _, _, service, _, _, _, _, _, successor, _, _, _ = _full_lifecycle(tmp_path)
    forged = successor.model_copy(deep=True)
    forged.successor_process.steps[0].activity = "Forged activity"
    result = service.assessment_service.assess_successor(
        forged, reassessment_repository=service.repository
    )
    assert result.status == "failed"
    assert result.errors[0].code.value == "approval-required"


def test_phase5_successor_adapter_rejects_forged_or_cross_run_references(tmp_path) -> None:
    _, _, service, _, _, _, _, _, successor, _, _, _ = _full_lifecycle(tmp_path)
    forged_ref = M2ArtifactReference(artifact_id="forged", artifact_revision=1, payload_sha256="0" * 64)
    forged = successor.model_copy(update={"approval_artifact": forged_ref})
    result = service.assessment_service.assess_successor(forged, reassessment_repository=service.repository)
    assert result.status == "failed"
    foreign_run = successor.model_copy(update={"run_id": "reassessment-run-foreign"})
    foreign_result = service.assessment_service.assess_successor(
        foreign_run, reassessment_repository=service.repository
    )
    assert foreign_result.status == "failed"
    no_repository = service.assessment_service.assess_successor(successor)
    assert no_repository.status == "failed"

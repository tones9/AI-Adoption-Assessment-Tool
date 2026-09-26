from __future__ import annotations

import sqlite3

import pytest

from ai_adoption_engine.decision.four_gate_policy import load_four_gate_policy
from ai_adoption_engine.grw.four_gate_m2.models import (
    SCHEMA_VERSION,
    FourGateM2ArtifactType,
    FourGateM2ConflictStatus,
    FourGateM2DocumentLocator,
    FourGateM2EvidencePermission,
    FourGateM2RunStage,
)
from ai_adoption_engine.grw.four_gate_m2.projection import (
    FourGateM2ProjectionError,
    assert_one_field_projection,
)
from ai_adoption_engine.grw.four_gate_m2.service import (
    FourGateM2Error,
    FourGateM2Service,
)
from ai_adoption_engine.models.enums import CriterionName
from ai_adoption_engine.persistence.four_gate_reassessment import (
    SQLiteFourGateReassessmentRepository,
)
from ai_adoption_engine.persistence.four_gate_reassessment_serialization import (
    deserialize_four_gate_m2_artifact,
    serialize_four_gate_m2_artifact,
)
from ai_adoption_engine.persistence.base import ArtifactCorruptionError
from ai_adoption_engine.workspace.models import ArtifactType
from tests.fakes.four_gate_m2 import (
    DOCUMENT_BYTES,
    actor,
    complete_lifecycle,
    successor_m2_service,
)
from tests.fakes.four_gate_workspace import (
    POLICY_PATH,
    persisted_four_gate_baseline,
)
from tests.fakes.m2_reassessment import package_ready_m2_baseline


def _run_count(path) -> int:
    connection = sqlite3.connect(path)
    try:
        return connection.execute(
            "SELECT COUNT(*) FROM four_gate_reassessment_runs"
        ).fetchone()[0]
    finally:
        connection.close()


def test_eligibility_is_exact_and_run_creation_is_idempotent(tmp_path) -> None:
    state = successor_m2_service(tmp_path / "eligible")
    service = state["service"]

    context = service.open_context(state["assessment_id"], state["target_step_id"])
    first = service.create_run(state["assessment_id"], state["target_step_id"])
    second = service.create_run(state["assessment_id"], state["target_step_id"])

    assert context is not None
    baseline, gap = context
    assert baseline.framework_id == "four-gate-framework.v0.1"
    assert baseline.phase1_contract_version == "phase1-v0.4"
    assert baseline.phase5_schema_version == "phase5-v0.2"
    assert baseline.phase6_schema_version == "phase6-v0.2"
    assert baseline.decision_policy_id == "decision_policy.v0.3"
    assert gap.information_gap.gate.value == "IS_IT_READY"
    assert gap.information_gap.field_name == "data_readiness"
    assert first == second
    assert _run_count(state["baseline_repository"].path) == 1


def test_non_gate_two_successor_baseline_is_unavailable_without_run_writes(
    tmp_path,
) -> None:
    baseline, assessment_id, _, package, _ = persisted_four_gate_baseline(
        tmp_path / "ineligible"
    )
    repository = SQLiteFourGateReassessmentRepository(baseline.path)
    service = FourGateM2Service(
        baseline,
        repository,
        policy_loader=lambda: load_four_gate_policy(POLICY_PATH),
    )
    target = package.package.portfolio.items[0].step_id

    assert service.open_context(assessment_id, target) is None
    with pytest.raises(FourGateM2Error, match="Gate 2 data_readiness"):
        service.create_run(assessment_id, target)
    assert _run_count(baseline.path) == 0


def test_legacy_baseline_cannot_create_successor_family_run(tmp_path) -> None:
    baseline, assessment_id = package_ready_m2_baseline(tmp_path / "legacy")
    repository = SQLiteFourGateReassessmentRepository(baseline.path)
    service = FourGateM2Service(
        baseline,
        repository,
        policy_loader=lambda: load_four_gate_policy(POLICY_PATH),
    )

    with pytest.raises(FourGateM2Error, match="Gate 2 data_readiness"):
        service.create_run(assessment_id, "any-step")
    assert _run_count(baseline.path) == 0


def test_policy_pin_and_document_hash_changes_fail_closed(tmp_path) -> None:
    policy = load_four_gate_policy(POLICY_PATH).model_copy(
        update={"description": "A different but structurally valid policy payload."}
    )
    state = successor_m2_service(
        tmp_path / "policy", policy_loader=lambda: policy
    )
    with pytest.raises(FourGateM2Error, match="fingerprint changed"):
        state["service"].create_run(state["assessment_id"], state["target_step_id"])
    assert _run_count(state["baseline_repository"].path) == 0

    state = successor_m2_service(tmp_path / "document")
    manifest = state["service"].create_run(
        state["assessment_id"], state["target_step_id"]
    )
    state["service"].submit_supporting_document(
        manifest.run_id,
        content_bytes=DOCUMENT_BYTES,
        filename="evidence.txt",
        source_label="Data owner report",
        submitter=actor(),
    )
    connection = sqlite3.connect(state["baseline_repository"].path)
    try:
        connection.execute(
            "UPDATE four_gate_reassessment_documents SET content_bytes=?",
            (b"tampered",),
        )
        connection.commit()
    finally:
        connection.close()
    text = DOCUMENT_BYTES.decode()
    locator = FourGateM2DocumentLocator(
        start_offset=0,
        end_offset=len(text),
        line_start=1,
        line_end=1,
        exact_excerpt=text,
    )
    with pytest.raises(FourGateM2Error, match="hash changed"):
        state["service"].review_document_evidence(
            manifest.run_id,
            reviewer=actor(),
            locator=locator,
            scope_statement="Target only.",
            period_statement="Current.",
            source_authority="Declared owner.",
            applicability_statement="Applies to target.",
            semantic_rationale="Maps to readiness.",
            limitations="Locally declared.",
            conflict_status=FourGateM2ConflictStatus.CONSISTENT,
            conflict_rationale="None found.",
            permission=(
                FourGateM2EvidencePermission.CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE
            ),
        )


@pytest.mark.parametrize(
    ("conflict", "permission", "expected_stage"),
    [
        (
            FourGateM2ConflictStatus.CONTRADICTORY,
            FourGateM2EvidencePermission.REJECTED,
            FourGateM2RunStage.BLOCKED_CONFLICT,
        ),
        (
            FourGateM2ConflictStatus.CONSISTENT,
            FourGateM2EvidencePermission.INSUFFICIENT_FOR_THIS_USE,
            FourGateM2RunStage.INSUFFICIENT,
        ),
    ],
)
def test_conflict_and_insufficient_evidence_end_without_projection(
    tmp_path, conflict, permission, expected_stage
) -> None:
    state = successor_m2_service(tmp_path / expected_stage.value.lower())
    service = state["service"]
    manifest = service.create_run(state["assessment_id"], state["target_step_id"])
    service.submit_supporting_document(
        manifest.run_id,
        content_bytes=DOCUMENT_BYTES,
        filename="evidence.txt",
        source_label="Data report",
        submitter=actor(),
    )
    text = DOCUMENT_BYTES.decode()
    service.review_document_evidence(
        manifest.run_id,
        reviewer=actor(),
        locator=FourGateM2DocumentLocator(
            start_offset=0,
            end_offset=len(text),
            line_start=1,
            line_end=1,
            exact_excerpt=text,
        ),
        scope_statement="Target only.",
        period_statement="Current.",
        source_authority="Declared owner.",
        applicability_statement="Reviewed for the target.",
        semantic_rationale="Reviewed for data readiness.",
        limitations="Locally declared.",
        conflict_status=conflict,
        conflict_rationale="Recorded human conflict finding.",
        permission=permission,
    )

    assert state["repository"].load_run(manifest.run_id)["stage"] == expected_stage
    with pytest.raises(FourGateM2Error):
        service.build_successor_review(manifest.run_id)


def test_projection_is_one_field_plus_evidence_and_rejects_other_changes(
    tmp_path,
) -> None:
    state = successor_m2_service(tmp_path)
    lifecycle = complete_lifecycle(state)
    resolution, projection = lifecycle[3], lifecycle[6]
    baseline = state["baseline_repository"].load_workspace(
        state["assessment_id"]
    ).active_artifacts[ArtifactType.APPROVED_REVIEW].payload

    assert_one_field_projection(
        baseline,
        projection.approved_review,
        target_step_id=state["target_step_id"],
        evidence_id=projection.evidence_id,
        resolution=resolution,
    )
    target = next(
        step
        for step in projection.approved_review.business_process.steps
        if step.step_id == state["target_step_id"]
    )
    assert target.characteristics.data_readiness.value == 4
    assert target.characteristics.data_readiness.evidence_ids == [projection.evidence_id]
    assert projection.approved_review.approval == baseline.approval
    assert projection.approved_review.review.updated_at == baseline.review.updated_at
    assert projection.approved_review.review.events == baseline.review.events
    tampered = projection.approved_review.model_copy(deep=True)
    tampered.business_process.steps[1].activity = "Changed outside scope"
    with pytest.raises(FourGateM2ProjectionError, match="non-target"):
        assert_one_field_projection(
            baseline,
            tampered,
            target_step_id=state["target_step_id"],
            evidence_id=projection.evidence_id,
            resolution=resolution,
        )


def test_exact_serialization_dispatch_rejects_unknown_contract_version(tmp_path) -> None:
    state = successor_m2_service(tmp_path)
    manifest = state["service"].create_run(
        state["assessment_id"], state["target_step_id"]
    )
    payload_json, digest = serialize_four_gate_m2_artifact(
        FourGateM2ArtifactType.RUN_MANIFEST,
        SCHEMA_VERSION,
        manifest,
    )
    assert deserialize_four_gate_m2_artifact(
        FourGateM2ArtifactType.RUN_MANIFEST,
        SCHEMA_VERSION,
        payload_json,
        digest,
    ) == manifest
    with pytest.raises(ArtifactCorruptionError, match="Unsupported"):
        deserialize_four_gate_m2_artifact(
            FourGateM2ArtifactType.RUN_MANIFEST,
            "grw-m2-four-gate-v9.9",
            payload_json,
            digest,
        )

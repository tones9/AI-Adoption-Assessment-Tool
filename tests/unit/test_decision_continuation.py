from __future__ import annotations

import hashlib
import sqlite3

from ai_adoption_engine.application.decision_continuation import (
    DecisionContinuationService,
)
from ai_adoption_engine.grw.m2.service import M2ReassessmentService
from ai_adoption_engine.grw.m2.models import M2ArtifactType
from ai_adoption_engine.persistence.reassessment import SQLiteReassessmentRepository
from ai_adoption_engine.workspace.models import ArtifactType
from ai_adoption_engine.workspace.service import AssessmentWorkspaceService
from tests.fakes.m2_reassessment import package_ready_m2_baseline


def _active_snapshot(repository, assessment_id: str) -> tuple[dict, dict]:
    workspace = repository.load_workspace(assessment_id)
    return (
        workspace.assessment.model_dump(mode="json"),
        {
            kind.value: (
                artifact.artifact_id,
                artifact.artifact_revision,
                artifact.parent_artifact_id,
                artifact.payload_sha256,
            )
            for kind, artifact in workspace.active_artifacts.items()
        },
    )


def _service(repository) -> DecisionContinuationService:
    reassessment = SQLiteReassessmentRepository(repository.path)
    workspace = AssessmentWorkspaceService(
        repository, extraction_service_factory=lambda *_args: None
    )
    return DecisionContinuationService(
        workspace,
        M2ReassessmentService(repository, reassessment),
    )


def test_dcw_view_is_read_only_and_uses_the_active_baseline(tmp_path) -> None:
    repository, assessment_id = package_ready_m2_baseline(tmp_path)
    service = _service(repository)
    before_bytes = hashlib.sha256(repository.path.read_bytes()).hexdigest()
    before_workspace = _active_snapshot(repository, assessment_id)

    view = service.open(assessment_id)

    active = repository.load_workspace(assessment_id).active_artifacts
    assert view.baseline.assessment_id == assessment_id
    assert view.baseline.package.artifact_id == active[ArtifactType.DECISION_PACKAGE_RESULT].artifact_id
    assert view.baseline.approved_review.artifact_id == active[ArtifactType.APPROVED_REVIEW].artifact_id
    assert view.baseline.integrated_assessment.artifact_id == active[ArtifactType.INTEGRATED_ASSESSMENT_RESULT].artifact_id
    assert view.baseline.recommendations
    assert view.m2_context is not None
    assert view.m2_runs == ()
    assert hashlib.sha256(repository.path.read_bytes()).hexdigest() == before_bytes
    assert _active_snapshot(repository, assessment_id) == before_workspace


def test_dcw_discovers_a_persisted_run_after_a_fresh_service_instance(tmp_path) -> None:
    repository, assessment_id = package_ready_m2_baseline(tmp_path)
    reassessment = SQLiteReassessmentRepository(repository.path)
    m2 = M2ReassessmentService(repository, reassessment)
    run_id, _, _ = m2.create_run(assessment_id)

    reopened = _service(repository)
    view = reopened.open(assessment_id)

    assert [run.run_id for run in view.m2_runs] == [run_id]
    assert reopened.resumable_run(assessment_id, run_id) == view.m2_runs[0]


def test_dcw_resumption_rejects_a_foreign_run(tmp_path) -> None:
    first, first_assessment_id = package_ready_m2_baseline(tmp_path)
    second, second_assessment_id = package_ready_m2_baseline(tmp_path)
    reassessment = SQLiteReassessmentRepository(first.path)
    foreign_run, _, _ = M2ReassessmentService(second, reassessment).create_run(
        second_assessment_id
    )

    service = _service(first)

    assert service.resumable_run(first_assessment_id, foreign_run) is None


def test_dcw_fails_closed_for_a_cross_run_active_manifest_pointer(tmp_path) -> None:
    repository, assessment_id = package_ready_m2_baseline(tmp_path)
    reassessment = SQLiteReassessmentRepository(repository.path)
    m2 = M2ReassessmentService(repository, reassessment)
    original_run, baseline_ref, _ = m2.create_run(assessment_id)
    manifest = reassessment.load_artifact_reference(
        original_run, M2ArtifactType.RUN_MANIFEST
    )
    assert manifest is not None
    forged_run = "forged-cross-run-pointer"
    connection = sqlite3.connect(repository.path)
    source = connection.execute(
        "SELECT assessment_id, baseline_package_artifact_id, baseline_package_sha256, created_at, updated_at FROM reassessment_runs WHERE run_id=?",
        (original_run,),
    ).fetchone()
    connection.execute(
        "INSERT INTO reassessment_runs(run_id, assessment_id, baseline_package_artifact_id, baseline_package_sha256, creation_idempotency_key, stage, created_at, updated_at, row_version) VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?, 1)",
        (
            forged_run,
            source[0],
            source[1],
            source[2],
            "forged-cross-run-key",
            source[3],
            source[4],
        ),
    )
    connection.execute(
        "INSERT INTO active_reassessment_artifacts(run_id, artifact_type, artifact_id) VALUES (?, 'RUN_MANIFEST', ?)",
        (forged_run, manifest.artifact_id),
    )
    connection.commit()
    connection.close()

    service = _service(repository)
    view = service.open(assessment_id)

    assert view.m2_discovery_error is not None
    assert forged_run not in {run.run_id for run in view.m2_runs}
    assert service.resumable_run(assessment_id, forged_run) is None
    assert baseline_ref.decision_package.artifact_id == view.baseline.package.artifact_id


def test_dcw_keeps_exact_baseline_history_when_current_m2_route_is_unavailable(
    tmp_path, monkeypatch
) -> None:
    repository, assessment_id = package_ready_m2_baseline(tmp_path)
    run_id, _, _ = M2ReassessmentService(
        repository, SQLiteReassessmentRepository(repository.path)
    ).create_run(assessment_id)
    service = _service(repository)
    monkeypatch.setattr(service.m2_service, "open_m2_m1_context", lambda _: None)

    view = service.open(assessment_id)

    assert view.m2_context is None
    assert [run.run_id for run in view.m2_runs] == [run_id]
    assert service.resumable_run(assessment_id, run_id) is None


def test_dcw_keeps_stale_exact_baseline_history_when_current_m2_route_is_unavailable(
    tmp_path, monkeypatch
) -> None:
    repository, assessment_id = package_ready_m2_baseline(tmp_path)
    run_id, _, _ = M2ReassessmentService(
        repository, SQLiteReassessmentRepository(repository.path)
    ).create_run(assessment_id)
    connection = sqlite3.connect(repository.path)
    connection.execute(
        "UPDATE reassessment_runs SET stage='STALE' WHERE run_id=?", (run_id,)
    )
    connection.commit()
    connection.close()
    service = _service(repository)
    monkeypatch.setattr(service.m2_service, "open_m2_m1_context", lambda _: None)

    view = service.open(assessment_id)

    assert view.m2_context is None
    assert [run.run_id for run in view.m2_runs] == [run_id]
    assert view.m2_runs[0].is_terminal is True
    assert service.resumable_run(assessment_id, run_id) is None

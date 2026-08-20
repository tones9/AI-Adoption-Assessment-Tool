from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime

import pytest

from ai_adoption_engine.grw.m2.models import (
    M2ActorDeclaration,
    M2ArtifactType,
)
from ai_adoption_engine.grw.m2.service import M2ReassessmentService
from ai_adoption_engine.persistence.reassessment import (
    M2FrozenWorkspaceError,
    M2PersistenceError,
    SQLiteReassessmentRepository,
)
from ai_adoption_engine.persistence.reassessment_serialization import serialize_m2_artifact
from tests.fakes.m2_reassessment import package_ready_m2_baseline


def _actor(label: str) -> M2ActorDeclaration:
    return M2ActorDeclaration(
        label=label,
        declared_role="synthetic test role",
        acknowledged_local_role_limitation=True,
        declared_at=datetime.now(UTC),
    )


def _document_submitted_run(
    tmp_path, *, content_bytes: bytes = b"Synthetic documented data fields and access constraints."
):
    baseline, assessment_id = package_ready_m2_baseline(tmp_path)
    repository = SQLiteReassessmentRepository(baseline.path)
    service = M2ReassessmentService(baseline, repository)
    run_id, baseline_ref, _ = service.create_run(assessment_id)
    service.submit_supporting_document(
        run_id,
        content_bytes=content_bytes,
        filename="support.txt",
        source_label="Synthetic source authority",
        submitter=_actor("submitter"),
    )
    manifest = repository.load_artifact_reference(run_id, M2ArtifactType.RUN_MANIFEST)
    submission = repository.load_artifact_reference(
        run_id, M2ArtifactType.DOCUMENT_SUBMISSION
    )
    assert manifest is not None and submission is not None
    return baseline, assessment_id, repository, service, run_id, baseline_ref, manifest, submission


def test_reassessment_repository_uses_separate_tables_and_does_not_change_baseline_row(tmp_path) -> None:
    baseline, assessment_id = package_ready_m2_baseline(tmp_path)
    before = baseline.load_workspace(assessment_id).assessment
    service = M2ReassessmentService(baseline, SQLiteReassessmentRepository(baseline.path))
    service.create_run(assessment_id)
    assert baseline.load_workspace(assessment_id).assessment == before


def test_create_run_replays_the_atomic_manifest_root(tmp_path) -> None:
    baseline, assessment_id = package_ready_m2_baseline(tmp_path)
    service = M2ReassessmentService(baseline, SQLiteReassessmentRepository(baseline.path))
    first, _, _ = service.create_run(assessment_id)
    second, _, _ = service.create_run(assessment_id)
    assert second == first
    assert (
        service.repository.load_artifact_reference(first, M2ArtifactType.RUN_MANIFEST)
        is not None
    )
    with pytest.raises(Exception):
        service.repository.load_run("missing")


def test_every_m2_repository_write_refuses_a_frozen_portfolio_path(tmp_path) -> None:
    """Every persistence write guard runs before a protected database is opened."""

    protected = tmp_path / "evaluation" / "portfolio" / "PORT-004" / "workspace.db"
    protected.parent.mkdir(parents=True)
    protected.write_bytes(b"frozen evaluation database bytes")
    before = hashlib.sha256(protected.read_bytes()).hexdigest()
    repository = object.__new__(SQLiteReassessmentRepository)
    repository.path = protected

    write_attempts = (
        lambda: repository.create_run_with_manifest("assessment", "package", "0" * 64, creation_idempotency_key="key", manifest_payload={}),
        lambda: repository.begin_operation("run", "kind", "key"),
        lambda: repository.complete_operation("operation"),
        lambda: repository.fail_operation("operation", "failure"),
        lambda: repository.save_document_and_submission("run", None, b"bytes", None, None),
        lambda: repository.save_artifact_and_advance("run", M2ArtifactType.EVIDENCE_REVIEW, None, "parent", None),
    )
    for attempt in write_attempts:
        with pytest.raises(M2FrozenWorkspaceError):
            attempt()
        assert hashlib.sha256(protected.read_bytes()).hexdigest() == before


def test_run_manifest_creation_rolls_back_atomically_if_root_persistence_fails(
    tmp_path, monkeypatch
) -> None:
    baseline, assessment_id = package_ready_m2_baseline(tmp_path)
    repository = SQLiteReassessmentRepository(baseline.path)
    service = M2ReassessmentService(baseline, repository)

    def fail_manifest(*_args, **_kwargs):
        raise sqlite3.OperationalError("injected manifest persistence failure")

    monkeypatch.setattr(repository, "_save_artifact", fail_manifest)
    with pytest.raises(sqlite3.OperationalError, match="manifest persistence"):
        service.create_run(assessment_id)
    connection = sqlite3.connect(baseline.path)
    count = connection.execute("SELECT COUNT(*) FROM reassessment_runs").fetchone()[0]
    connection.close()
    assert count == 0


def test_document_and_submission_roll_back_together_on_persistence_failure(
    tmp_path, monkeypatch
) -> None:
    baseline, assessment_id = package_ready_m2_baseline(tmp_path)
    repository = SQLiteReassessmentRepository(baseline.path)
    service = M2ReassessmentService(baseline, repository)
    run_id, _, _ = service.create_run(assessment_id)

    def fail_submission(*_args, **_kwargs):
        raise sqlite3.OperationalError("injected submission persistence failure")

    monkeypatch.setattr(repository, "_save_artifact", fail_submission)
    with pytest.raises(sqlite3.OperationalError, match="submission persistence"):
        service.submit_supporting_document(
            run_id,
            content_bytes=b"synthetic document",
            filename="synthetic.txt",
            source_label="owner",
            submitter=M2ActorDeclaration(
                label="submitter",
                declared_role="synthetic",
                acknowledged_local_role_limitation=True,
                declared_at=datetime.now(UTC),
            ),
        )
    connection = sqlite3.connect(baseline.path)
    document_count = connection.execute(
        "SELECT COUNT(*) FROM reassessment_documents WHERE run_id=?", (run_id,)
    ).fetchone()[0]
    connection.close()
    assert document_count == 0
    assert repository.load_run(run_id)["stage"] == "FAILED"


def test_list_runs_for_baseline_requires_all_roots_and_does_not_write(tmp_path) -> None:
    first, first_assessment_id = package_ready_m2_baseline(tmp_path)
    second, second_assessment_id = package_ready_m2_baseline(tmp_path)
    repository = SQLiteReassessmentRepository(first.path)
    first_service = M2ReassessmentService(first, repository)
    second_service = M2ReassessmentService(second, repository)
    first_run, first_baseline, _ = first_service.create_run(first_assessment_id)
    second_run, second_baseline, _ = second_service.create_run(second_assessment_id)
    before = hashlib.sha256(first.path.read_bytes()).hexdigest()

    listings = repository.list_runs_for_baseline(
        first_assessment_id,
        first_baseline.decision_package.artifact_id,
        first_baseline.decision_package.payload_sha256,
    )

    assert [listing.run_id for listing in listings] == [first_run]
    assert listings[0].baseline == first_baseline
    assert listings[0].gap.step_id
    assert second_run not in {listing.run_id for listing in listings}
    assert not repository.list_runs_for_baseline(
        first_assessment_id,
        first_baseline.decision_package.artifact_id,
        second_baseline.decision_package.payload_sha256,
    )
    assert hashlib.sha256(first.path.read_bytes()).hexdigest() == before


def test_list_runs_for_baseline_fails_closed_for_manifest_baseline_mismatch(tmp_path) -> None:
    baseline, assessment_id = package_ready_m2_baseline(tmp_path)
    repository = SQLiteReassessmentRepository(baseline.path)
    service = M2ReassessmentService(baseline, repository)
    run_id, baseline_ref, _ = service.create_run(assessment_id)
    manifest_ref = repository.load_artifact_reference(run_id, M2ArtifactType.RUN_MANIFEST)
    assert manifest_ref is not None
    tampered = repository.load_artifact(manifest_ref.artifact_id)
    tampered["baseline"]["decision_package"]["payload_sha256"] = "0" * 64
    payload_json, payload_sha256 = serialize_m2_artifact("RUN_MANIFEST", tampered)
    connection = sqlite3.connect(baseline.path)
    connection.execute(
        "UPDATE reassessment_artifacts SET payload_json=?, payload_sha256=? WHERE artifact_id=?",
        (payload_json, payload_sha256, manifest_ref.artifact_id),
    )
    connection.commit()
    connection.close()

    with pytest.raises(M2PersistenceError, match="does not match"):
        repository.list_runs_for_baseline(
            assessment_id,
            baseline_ref.decision_package.artifact_id,
            baseline_ref.decision_package.payload_sha256,
            expected_baseline=baseline_ref,
        )


def test_list_runs_for_baseline_rejects_wrong_manifest_revision(tmp_path) -> None:
    baseline, assessment_id = package_ready_m2_baseline(tmp_path)
    repository = SQLiteReassessmentRepository(baseline.path)
    service = M2ReassessmentService(baseline, repository)
    run_id, baseline_ref, _ = service.create_run(assessment_id)
    manifest_ref = repository.load_artifact_reference(run_id, M2ArtifactType.RUN_MANIFEST)
    assert manifest_ref is not None
    tampered = repository.load_artifact(manifest_ref.artifact_id)
    tampered["baseline"]["decision_package"]["artifact_revision"] += 1
    payload_json, payload_sha256 = serialize_m2_artifact("RUN_MANIFEST", tampered)
    connection = sqlite3.connect(baseline.path)
    connection.execute(
        "UPDATE reassessment_artifacts SET payload_json=?, payload_sha256=? WHERE artifact_id=?",
        (payload_json, payload_sha256, manifest_ref.artifact_id),
    )
    connection.commit()
    connection.close()

    with pytest.raises(M2PersistenceError, match="does not match"):
        repository.list_runs_for_baseline(
            assessment_id,
            baseline_ref.decision_package.artifact_id,
            baseline_ref.decision_package.payload_sha256,
            expected_baseline=baseline_ref,
        )


def test_list_runs_for_baseline_rejects_cross_run_active_manifest_pointer(tmp_path) -> None:
    _, first_assessment_id, repository, _, first_run, first_baseline, _, _ = (
        _document_submitted_run(tmp_path)
    )
    second, second_assessment_id = package_ready_m2_baseline(tmp_path)
    M2ReassessmentService(second, repository).create_run(second_assessment_id)
    second_run = next(
        row[0]
        for row in sqlite3.connect(repository.path).execute(
            "SELECT run_id FROM reassessment_runs WHERE assessment_id=?", (second_assessment_id,)
        )
    )
    foreign_manifest = repository.load_artifact_reference(
        second_run, M2ArtifactType.RUN_MANIFEST
    )
    assert foreign_manifest is not None
    connection = sqlite3.connect(repository.path)
    connection.execute(
        "UPDATE active_reassessment_artifacts SET artifact_id=? WHERE run_id=? AND artifact_type='RUN_MANIFEST'",
        (foreign_manifest.artifact_id, first_run),
    )
    connection.commit()
    connection.close()

    with pytest.raises(M2PersistenceError, match="does not belong"):
        repository.list_runs_for_baseline(
            first_assessment_id,
            first_baseline.decision_package.artifact_id,
            first_baseline.decision_package.payload_sha256,
            expected_baseline=first_baseline,
        )


def test_list_runs_for_baseline_rejects_wrong_active_artifact_type(tmp_path) -> None:
    _, assessment_id, repository, _, run_id, baseline_ref, _, submission = (
        _document_submitted_run(tmp_path)
    )
    connection = sqlite3.connect(repository.path)
    connection.execute(
        "UPDATE active_reassessment_artifacts SET artifact_id=? WHERE run_id=? AND artifact_type='RUN_MANIFEST'",
        (submission.artifact_id, run_id),
    )
    connection.commit()
    connection.close()

    with pytest.raises(M2PersistenceError, match="declared run and type"):
        repository.list_runs_for_baseline(
            assessment_id,
            baseline_ref.decision_package.artifact_id,
            baseline_ref.decision_package.payload_sha256,
            expected_baseline=baseline_ref,
        )


def test_list_runs_for_baseline_rejects_foreign_or_wrong_document_parent(tmp_path) -> None:
    first, first_assessment_id, repository, _, _, first_baseline, _, submission = (
        _document_submitted_run(tmp_path)
    )
    second, second_assessment_id, _, _, _, _, foreign_manifest, _ = (
        _document_submitted_run(
            tmp_path,
            content_bytes=b"Separate synthetic source text for a distinct supporting document.",
        )
    )
    assert first.path == second.path
    connection = sqlite3.connect(first.path)
    connection.execute(
        "UPDATE reassessment_artifacts SET parent_artifact_id=? WHERE artifact_id=?",
        (foreign_manifest.artifact_id, submission.artifact_id),
    )
    connection.commit()
    connection.close()

    with pytest.raises(M2PersistenceError, match="foreign"):
        repository.list_runs_for_baseline(
            first_assessment_id,
            first_baseline.decision_package.artifact_id,
            first_baseline.decision_package.payload_sha256,
            expected_baseline=first_baseline,
        )


def test_list_runs_for_baseline_rejects_skipped_expected_parent(tmp_path) -> None:
    from tests.integration.test_grw_m2_m1_lifecycle import _full_lifecycle

    baseline, assessment_id, service, _, run_id, baseline_ref, _, _, _, _, _, _ = (
        _full_lifecycle(tmp_path)
    )
    repository = service.repository
    connection = sqlite3.connect(baseline.path)
    connection.execute(
        "DELETE FROM active_reassessment_artifacts WHERE run_id=? AND artifact_type='DATA_READINESS_RESOLUTION'",
        (run_id,),
    )
    connection.commit()
    connection.close()

    with pytest.raises(M2PersistenceError, match="incomplete"):
        repository.list_runs_for_baseline(
            assessment_id,
            baseline_ref.decision_package.artifact_id,
            baseline_ref.decision_package.payload_sha256,
            expected_baseline=baseline_ref,
        )


def test_list_runs_for_baseline_rejects_wrong_immediate_parent(tmp_path) -> None:
    from tests.integration.test_grw_m2_m1_lifecycle import _full_lifecycle

    baseline, assessment_id, service, _, run_id, baseline_ref, _, _, _, _, _, _ = (
        _full_lifecycle(tmp_path)
    )
    repository = service.repository
    manifest = repository.load_artifact_reference(run_id, M2ArtifactType.RUN_MANIFEST)
    request = repository.load_artifact_reference(run_id, M2ArtifactType.REASSESSMENT_REQUEST)
    assert manifest is not None and request is not None
    connection = sqlite3.connect(baseline.path)
    connection.execute(
        "UPDATE reassessment_artifacts SET parent_artifact_id=? WHERE artifact_id=?",
        (manifest.artifact_id, request.artifact_id),
    )
    connection.commit()
    connection.close()

    with pytest.raises(M2PersistenceError, match="incomplete"):
        repository.list_runs_for_baseline(
            assessment_id,
            baseline_ref.decision_package.artifact_id,
            baseline_ref.decision_package.payload_sha256,
            expected_baseline=baseline_ref,
        )


def test_list_runs_for_baseline_rejects_dangling_tampered_active_reference(tmp_path) -> None:
    _, assessment_id, repository, _, run_id, baseline_ref, _, _ = (
        _document_submitted_run(tmp_path)
    )
    connection = sqlite3.connect(repository.path)
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute(
        "UPDATE active_reassessment_artifacts SET artifact_id='missing-artifact' WHERE run_id=? AND artifact_type='RUN_MANIFEST'",
        (run_id,),
    )
    connection.commit()
    connection.close()

    with pytest.raises(M2PersistenceError, match="declared run and type"):
        repository.list_runs_for_baseline(
            assessment_id,
            baseline_ref.decision_package.artifact_id,
            baseline_ref.decision_package.payload_sha256,
            expected_baseline=baseline_ref,
        )

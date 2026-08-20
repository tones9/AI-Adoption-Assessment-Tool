from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime

import pytest

from ai_adoption_engine.grw.m2.models import M2ActorDeclaration, M2ArtifactType
from ai_adoption_engine.grw.m2.service import M2ReassessmentService
from ai_adoption_engine.persistence.reassessment import (
    M2FrozenWorkspaceError,
    SQLiteReassessmentRepository,
)
from tests.fakes.m2_reassessment import package_ready_m2_baseline


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

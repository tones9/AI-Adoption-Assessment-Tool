from __future__ import annotations

import hashlib
import shutil
import sqlite3
import stat
from pathlib import Path

import pytest

from ai_adoption_engine.persistence.migrations import MIGRATIONS
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.persistence.workspace_protection import (
    FrozenEvaluationWorkspaceCompatibilityError,
    FrozenEvaluationWorkspaceError,
    is_frozen_evaluation_portfolio_path,
)
from ai_adoption_engine.workspace.composition import build_workspace_service
from ai_adoption_engine.workspace.demo_extraction import demo_text
from ai_adoption_engine.workspace.models import (
    ArtifactType,
    ExecutionMode,
    OperationKind,
    WorkflowStage,
)
from ai_adoption_engine.workspace.service import AssessmentWorkspaceService


def _snapshot(path: Path) -> dict[str, object]:
    file_stat = path.stat()
    content = path.read_bytes()
    return {
        "bytes": content,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": file_stat.st_size,
        "mode": stat.S_IMODE(file_stat.st_mode),
        "mtime_ns": file_stat.st_mtime_ns,
        "entries": tuple(sorted(item.name for item in path.parent.iterdir())),
    }


def _protected_copy(source: Path, tmp_path: Path, name: str = "workspace.db") -> Path:
    protected = tmp_path / "evaluation" / "portfolio" / "PORT-F1" / name
    protected.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, protected)
    return protected


def _approved_workspace(path: Path, *, package: bool = True):
    service = build_workspace_service(path)
    assessment = service.repository.create_assessment(
        "F1 protected workspace", ExecutionMode.OFFLINE_DEMO
    )
    service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    service.extract(assessment.assessment_id)
    review = service.start_review(assessment.assessment_id)
    service.review_service.accept_assertion(
        review, review.process_name, "process.name"
    )
    for step in review.steps:
        service.review_service.accept_assertion(
            review, step.activity, f"steps.{step.candidate_step_id}.activity"
        )
    service.review_service.accept_step_order(review)
    service.save_review(assessment.assessment_id, review)
    assert service.approve(assessment.assessment_id).approved is not None
    if package:
        assert service.assess(assessment.assessment_id).status == "success"
        assert service.generate_package(assessment.assessment_id).status == "success"
    return service, assessment.assessment_id


def _version_one_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(MIGRATIONS[0][1])
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (1, '2026-08-21T00:00:00+00:00')"
        )
        connection.commit()
    finally:
        connection.close()


def test_protected_repository_construction_and_reads_are_byte_invariant(
    tmp_path: Path,
) -> None:
    ordinary = tmp_path / "ordinary.db"
    service, assessment_id = _approved_workspace(ordinary)
    expected_title = service.repository.get_assessment(assessment_id).title
    protected = _protected_copy(ordinary, tmp_path)
    before = _snapshot(protected)

    repository = SQLiteAssessmentRepository(protected)

    assert repository.get_assessment(assessment_id).title == expected_title
    assert repository.load_workspace(assessment_id).assessment.assessment_id == assessment_id
    with repository._read() as connection:
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            connection.execute(
                "DELETE FROM assessments WHERE assessment_id = ?", (assessment_id,)
            )
    assert _snapshot(protected) == before
    assert not any(
        item.name.endswith(("-journal", "-wal", "-shm"))
        for item in protected.parent.iterdir()
    )


def test_every_ordinary_repository_mutation_family_refuses_before_connecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ordinary = tmp_path / "ordinary.db"
    _, assessment_id = _approved_workspace(ordinary)
    protected = _protected_copy(ordinary, tmp_path)
    repository = SQLiteAssessmentRepository(protected)
    workspace = repository.load_workspace(assessment_id)
    ingestion = workspace.active_artifacts[ArtifactType.INGESTION_RESULT]
    before = _snapshot(protected)

    def unexpected_connect():
        raise AssertionError("write fence must refuse before opening a connection")

    monkeypatch.setattr(repository, "_connect", unexpected_connect)
    attempts = (
        lambda: repository.create_assessment("Blocked", ExecutionMode.OFFLINE_DEMO),
        lambda: repository.save_artifact_and_advance(
            assessment_id,
            ArtifactType.INGESTION_RESULT,
            ingestion.payload,
            artifact_schema_version="phase2-v0.1",
            stage=WorkflowStage.INGESTED,
        ),
        lambda: repository.activate_artifact_and_advance(
            assessment_id,
            ingestion.artifact_id,
            stage=WorkflowStage.INGESTED,
        ),
        lambda: repository.invalidate_active_artifacts(
            assessment_id,
            [ArtifactType.DECISION_PACKAGE_RESULT],
            stage=WorkflowStage.ASSESSED,
        ),
        lambda: repository.begin_operation(
            assessment_id, OperationKind.INGEST, "blocked-operation"
        ),
        lambda: repository.fail_operation("operation-does-not-matter", "blocked"),
        lambda: repository.delete_assessment(assessment_id, confirmed=True),
        repository._migrate,
    )

    for attempt in attempts:
        with pytest.raises(
            FrozenEvaluationWorkspaceError,
            match="Writes are refused for frozen evaluation portfolio workspaces",
        ):
            attempt()
        assert _snapshot(protected) == before


def test_protected_workspace_service_mutations_fail_without_computation(
    tmp_path: Path,
) -> None:
    ordinary = tmp_path / "ordinary.db"
    _, assessment_id = _approved_workspace(ordinary)
    protected = _protected_copy(ordinary, tmp_path)
    repository = SQLiteAssessmentRepository(protected)
    review = repository.load_workspace(assessment_id).active_artifacts[
        ArtifactType.REVIEW_SESSION
    ].payload
    before = _snapshot(protected)

    class ExtractionSpy:
        class Provider:
            provider_name = "f1-spy"
            model_name = "f1-spy"

        provider = Provider()
        schema_version = "phase3-v0.1"
        prompt_version = "f1-spy"
        calls = 0

        def extract(self, _document):
            self.calls += 1
            raise AssertionError("protected extraction must not call the provider")

    class AssessmentSpy:
        calls = 0

        def assess(self, _approved):
            self.calls += 1
            raise AssertionError("protected assessment must not be computed")

    class PackageSpy:
        calls = 0

        def generate(self, _integrated):
            self.calls += 1
            raise AssertionError("protected package must not be computed")

    extraction = ExtractionSpy()
    assessment = AssessmentSpy()
    package = PackageSpy()
    service = AssessmentWorkspaceService(
        repository,
        extraction_service_factory=lambda *_args: extraction,
        assessment_service=assessment,
        package_service=package,
    )
    attempts = (
        lambda: service.ingest_upload(
            assessment_id,
            raw_text=demo_text() + "\nChanged source",
            replace_existing=True,
        ),
        lambda: service.extract(assessment_id),
        lambda: service.start_review(assessment_id),
        lambda: service.save_review(assessment_id, review),
        lambda: service.approve(assessment_id),
        lambda: service.assess(assessment_id),
        lambda: service.generate_package(assessment_id),
        lambda: service.reset_to_review(assessment_id),
    )

    for attempt in attempts:
        with pytest.raises(FrozenEvaluationWorkspaceError):
            attempt()
        assert _snapshot(protected) == before
    assert extraction.calls == 0
    assert assessment.calls == 0
    assert package.calls == 0


def test_missing_protected_database_fails_without_creating_parent_or_file(
    tmp_path: Path,
) -> None:
    protected = tmp_path / "evaluation" / "portfolio" / "missing" / "workspace.db"

    with pytest.raises(
        FrozenEvaluationWorkspaceCompatibilityError,
        match="must already exist",
    ):
        SQLiteAssessmentRepository(protected)

    assert not protected.parent.exists()
    assert not protected.exists()


def test_old_schema_protected_database_is_not_migrated(tmp_path: Path) -> None:
    old = tmp_path / "old.db"
    _version_one_database(old)
    protected = _protected_copy(old, tmp_path)
    before = _snapshot(protected)

    with pytest.raises(
        FrozenEvaluationWorkspaceCompatibilityError,
        match="will not be migrated in place",
    ):
        SQLiteAssessmentRepository(protected)

    assert _snapshot(protected) == before


def test_symlink_resolving_to_protected_database_is_protected(tmp_path: Path) -> None:
    ordinary = tmp_path / "ordinary.db"
    _approved_workspace(ordinary, package=False)
    protected = _protected_copy(ordinary, tmp_path)
    link = tmp_path / "workspace-link.db"
    try:
        link.symlink_to(protected)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")

    assert is_frozen_evaluation_portfolio_path(link)
    repository = SQLiteAssessmentRepository(link)
    before = _snapshot(protected)
    with pytest.raises(FrozenEvaluationWorkspaceError):
        repository.create_assessment("Blocked", ExecutionMode.OFFLINE_DEMO)
    assert _snapshot(protected) == before


def test_normal_workspace_creation_migration_and_mutation_are_unchanged(
    tmp_path: Path,
) -> None:
    empty = tmp_path / "new" / "normal.db"
    repository = SQLiteAssessmentRepository(empty)
    assessment = repository.create_assessment("Normal F1 control", ExecutionMode.OFFLINE_DEMO)
    assert repository.get_assessment(assessment.assessment_id).title == "Normal F1 control"
    repository.delete_assessment(assessment.assessment_id, confirmed=True)
    assert repository.list_assessments() == []

    old = tmp_path / "normal-old.db"
    _version_one_database(old)
    SQLiteAssessmentRepository(old)
    connection = sqlite3.connect(old)
    try:
        versions = [
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
    finally:
        connection.close()
    assert versions == [version for version, _script in MIGRATIONS]

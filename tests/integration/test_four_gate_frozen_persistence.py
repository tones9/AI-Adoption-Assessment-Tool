from __future__ import annotations

import hashlib
import shutil
import sqlite3
import stat
from pathlib import Path

import pytest

from ai_adoption_engine.ingestion.text import ingest_raw_text
from ai_adoption_engine.persistence.contract_pins import (
    LEGACY_CONTRACT_PIN,
    successor_contract_pin,
)
from ai_adoption_engine.persistence.migrations import MIGRATIONS
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.persistence.workspace_protection import (
    FrozenEvaluationWorkspaceCompatibilityError,
    FrozenEvaluationWorkspaceError,
)
from ai_adoption_engine.workspace.models import (
    ArtifactType,
    ExecutionMode,
    OperationKind,
    WorkflowStage,
)


def _create_schema(path: Path, versions: int) -> None:
    connection = sqlite3.connect(path)
    try:
        for version, script in MIGRATIONS[:versions]:
            connection.executescript(script)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, "2026-09-05T00:00:00+00:00"),
            )
        connection.execute(
            """INSERT INTO assessments(
                   assessment_id, title, execution_mode, current_stage,
                   created_at, updated_at, row_version
               ) VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (
                "frozen-legacy-assessment",
                "Frozen legacy assessment",
                "offline-demo",
                "new",
                "2026-09-05T00:00:00+00:00",
                "2026-09-05T00:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _protected_copy(source: Path, tmp_path: Path, name: str) -> Path:
    target = tmp_path / "evaluation" / "portfolio" / "frozen" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def _snapshot(path: Path) -> dict[str, object]:
    metadata = path.stat()
    content = path.read_bytes()
    return {
        "bytes": content,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": metadata.st_size,
        "mode": stat.S_IMODE(metadata.st_mode),
        "mtime_ns": metadata.st_mtime_ns,
        "entries": tuple(sorted(item.name for item in path.parent.iterdir())),
    }


def _migration_versions(path: Path) -> list[int]:
    connection = sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=ro&immutable=1",
        uri=True,
    )
    try:
        return [
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
    finally:
        connection.close()


def test_migration_three_frozen_workspace_uses_only_a_virtual_legacy_pin(
    tmp_path: Path,
) -> None:
    source = tmp_path / "migration-three.db"
    _create_schema(source, 3)
    protected = _protected_copy(source, tmp_path, "workspace.db")
    before = _snapshot(protected)

    repository = SQLiteAssessmentRepository(protected)
    record = repository.get_assessment("frozen-legacy-assessment")
    workspace = repository.load_workspace("frozen-legacy-assessment")

    assert record.contract_pin == LEGACY_CONTRACT_PIN.model_copy(
        update={"virtual": True}
    )
    assert record.contract_pin.virtual is True
    assert workspace.assessment.contract_pin.virtual is True
    assert _migration_versions(protected) == [1, 2, 3]
    with repository._read() as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(assessments)")
        }
        assert "decision_contract_version" not in columns
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1

    assert _snapshot(protected) == before
    assert not any(
        path.name.endswith(("-journal", "-wal", "-shm"))
        for path in protected.parent.iterdir()
    )


def test_every_migration_three_frozen_write_and_migration_is_refused(
    tmp_path: Path,
) -> None:
    source = tmp_path / "migration-three.db"
    _create_schema(source, 3)
    protected = _protected_copy(source, tmp_path, "read-only.db")
    repository = SQLiteAssessmentRepository(protected)
    before = _snapshot(protected)
    ingestion = ingest_raw_text("Frozen workspace write refusal.")

    attempts = (
        lambda: repository.create_assessment(
            "Blocked",
            ExecutionMode.OFFLINE_DEMO,
        ),
        lambda: repository.pin_decision_contract(
            "frozen-legacy-assessment",
            successor_contract_pin("a" * 64),
        ),
        lambda: repository.save_artifact_and_advance(
            "frozen-legacy-assessment",
            ArtifactType.INGESTION_RESULT,
            ingestion,
            artifact_schema_version="phase2-v0.1",
            stage=WorkflowStage.INGESTED,
        ),
        lambda: repository.begin_operation(
            "frozen-legacy-assessment",
            OperationKind.ASSESS,
            "blocked",
        ),
        repository._migrate,
    )
    for attempt in attempts:
        with pytest.raises(FrozenEvaluationWorkspaceError):
            attempt()
        assert _snapshot(protected) == before
        assert _migration_versions(protected) == [1, 2, 3]
        assert not any(
            path.name.endswith(("-journal", "-wal", "-shm"))
            for path in protected.parent.iterdir()
        )


def test_unsupported_protected_schema_fails_without_any_file_change(
    tmp_path: Path,
) -> None:
    source = tmp_path / "migration-two.db"
    _create_schema(source, 2)
    protected = _protected_copy(source, tmp_path, "unsupported.db")
    before = _snapshot(protected)

    with pytest.raises(
        FrozenEvaluationWorkspaceCompatibilityError,
        match="will not be migrated in place",
    ):
        SQLiteAssessmentRepository(protected)

    assert _snapshot(protected) == before
    assert _migration_versions(protected) == [1, 2]
    assert not any(
        path.name.endswith(("-journal", "-wal", "-shm"))
        for path in protected.parent.iterdir()
    )


def test_structurally_modified_migration_three_schema_is_refused_unchanged(
    tmp_path: Path,
) -> None:
    source = tmp_path / "modified-migration-three.db"
    _create_schema(source, 3)
    connection = sqlite3.connect(source)
    try:
        connection.execute("ALTER TABLE assessments ADD COLUMN unexpected TEXT")
        connection.commit()
    finally:
        connection.close()
    protected = _protected_copy(source, tmp_path, "modified.db")
    before = _snapshot(protected)

    with pytest.raises(
        FrozenEvaluationWorkspaceCompatibilityError,
        match="will not be migrated in place",
    ):
        SQLiteAssessmentRepository(protected)

    assert _snapshot(protected) == before
    assert _migration_versions(protected) == [1, 2, 3]
    assert not any(
        path.name.endswith(("-journal", "-wal", "-shm"))
        for path in protected.parent.iterdir()
    )

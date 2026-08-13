"""Transactional, versioned SQLite assessment repository."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from pydantic import BaseModel

from ai_adoption_engine.workspace.models import (
    ArtifactReference,
    ArtifactType,
    AssessmentRecord,
    ExecutionMode,
    OperationKind,
    OperationRecord,
    OperationStatus,
    StoredArtifact,
    WorkflowStage,
    WorkspaceSnapshot,
)
from ai_adoption_engine.persistence.base import (
    ArtifactNotFoundError,
    OperationAlreadyStartedError,
    PersistenceError,
)
from ai_adoption_engine.persistence.migrations import MIGRATIONS
from ai_adoption_engine.persistence.serialization import (
    deserialize_artifact,
    serialize_artifact,
    validate_schema_version,
)


Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]

_EXPECTED_PARENT_TYPE = {
    ArtifactType.CANDIDATE_EXTRACTION_RESULT: ArtifactType.INGESTION_RESULT,
    ArtifactType.REVIEW_SESSION: ArtifactType.CANDIDATE_EXTRACTION_RESULT,
    ArtifactType.APPROVED_REVIEW: ArtifactType.REVIEW_SESSION,
    ArtifactType.INTEGRATED_ASSESSMENT_RESULT: ArtifactType.APPROVED_REVIEW,
    ArtifactType.DECISION_PACKAGE_RESULT: ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
}
_REQUIRED_PARENT_TYPES = {
    ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
    ArtifactType.DECISION_PACKAGE_RESULT,
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


class SQLiteAssessmentRepository:
    """Local single-user adapter; milestone payloads are append-only."""

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        self.path = Path(path)
        self.clock = clock or _utc_now
        self.id_factory = id_factory or _id
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: sqlite3.Connection | None = None
        self._migrate()
        if str(self.path) != ":memory:" and self.path.exists():
            self.path.chmod(0o600)

    def _connect(self) -> sqlite3.Connection:
        if str(self.path) == ":memory:":
            if self._connection is None:
                self._connection = sqlite3.connect(":memory:")
                self._configure(self._connection)
            return self._connection
        connection = sqlite3.connect(self.path)
        self._configure(connection)
        return connection

    @staticmethod
    def _configure(connection: sqlite3.Connection) -> None:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def _migrate(self) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            applied = {
                row[0]
                for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for version, script in MIGRATIONS:
                if version in applied:
                    continue
                connection.executescript(script)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (version, self.clock().isoformat()),
                )
            connection.commit()
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def create_assessment(
        self, title: str, mode: ExecutionMode
    ) -> AssessmentRecord:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Assessment title must be non-empty")
        now = self.clock()
        assessment_id = self.id_factory("assessment")
        with self._transaction() as connection:
            connection.execute(
                """INSERT INTO assessments(
                    assessment_id, title, execution_mode, current_stage,
                    created_at, updated_at, row_version
                ) VALUES (?, ?, ?, ?, ?, ?, 1)""",
                (
                    assessment_id,
                    clean_title,
                    mode.value,
                    WorkflowStage.NEW.value,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
        return self.get_assessment(assessment_id)

    def list_assessments(self) -> list[AssessmentRecord]:
        with self._read() as connection:
            rows = connection.execute(
                "SELECT * FROM assessments ORDER BY updated_at DESC"
            ).fetchall()
        return [self._assessment(row) for row in rows]

    def get_assessment(self, assessment_id: str) -> AssessmentRecord:
        with self._read() as connection:
            row = connection.execute(
                "SELECT * FROM assessments WHERE assessment_id = ?",
                (assessment_id,),
            ).fetchone()
        if row is None:
            raise ArtifactNotFoundError("Assessment does not exist")
        return self._assessment(row)

    @staticmethod
    def _assessment(row: sqlite3.Row) -> AssessmentRecord:
        return AssessmentRecord(
            assessment_id=row["assessment_id"],
            title=row["title"],
            execution_mode=ExecutionMode(row["execution_mode"]),
            current_stage=WorkflowStage(row["current_stage"]),
            source_filename=row["source_filename"],
            source_input_type=row["source_input_type"],
            document_id=row["document_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            row_version=row["row_version"],
        )

    def save_artifact_and_advance(
        self,
        assessment_id: str,
        artifact_type: ArtifactType,
        payload: BaseModel,
        *,
        artifact_schema_version: str,
        stage: WorkflowStage,
        parent_artifact_id: str | None = None,
        replace_current_review: bool = False,
        source_filename: str | None = None,
        source_input_type: str | None = None,
        document_id: str | None = None,
        operation_id: str | None = None,
        deactivate_types: Iterable[ArtifactType] = (),
    ) -> ArtifactReference:
        validate_schema_version(artifact_type, artifact_schema_version)
        payload_json, payload_sha = serialize_artifact(artifact_type, payload)
        now = self.clock()
        with self._transaction() as connection:
            self._require_assessment(connection, assessment_id)
            connection.executemany(
                "DELETE FROM active_artifacts WHERE assessment_id = ? AND artifact_type = ?",
                ((assessment_id, item.value) for item in deactivate_types),
            )
            if parent_artifact_id is not None:
                parent_type = self._require_owned_artifact(
                    connection, assessment_id, parent_artifact_id
                )
                expected_parent = _EXPECTED_PARENT_TYPE.get(artifact_type)
                if expected_parent is not None and parent_type is not expected_parent:
                    raise PersistenceError(
                        f"{artifact_type.value} requires parent {expected_parent.value}"
                    )
            elif artifact_type in _REQUIRED_PARENT_TYPES:
                raise PersistenceError(
                    f"{artifact_type.value} requires an exact parent artifact"
                )
            current = connection.execute(
                """SELECT a.* FROM active_artifacts aa
                   JOIN assessment_artifacts a ON a.artifact_id = aa.artifact_id
                   WHERE aa.assessment_id = ? AND aa.artifact_type = ?""",
                (assessment_id, artifact_type.value),
            ).fetchone()
            can_replace = (
                replace_current_review
                and artifact_type is ArtifactType.REVIEW_SESSION
                and current is not None
            )
            if replace_current_review and artifact_type is not ArtifactType.REVIEW_SESSION:
                raise PersistenceError("Only the active review snapshot may be replaced")
            if can_replace:
                artifact_id = current["artifact_id"]
                revision = current["artifact_revision"]
                connection.execute(
                    """UPDATE assessment_artifacts
                       SET payload_json = ?, payload_sha256 = ?, updated_at = ?
                       WHERE artifact_id = ?""",
                    (payload_json, payload_sha, now.isoformat(), artifact_id),
                )
            else:
                revision = connection.execute(
                    """SELECT COALESCE(MAX(artifact_revision), 0) + 1
                       FROM assessment_artifacts
                       WHERE assessment_id = ? AND artifact_type = ?""",
                    (assessment_id, artifact_type.value),
                ).fetchone()[0]
                artifact_id = self.id_factory("artifact")
                connection.execute(
                    """INSERT INTO assessment_artifacts(
                        artifact_id, assessment_id, artifact_type, artifact_revision,
                        artifact_schema_version, payload_json, payload_sha256,
                        parent_artifact_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        artifact_id,
                        assessment_id,
                        artifact_type.value,
                        revision,
                        artifact_schema_version,
                        payload_json,
                        payload_sha,
                        parent_artifact_id,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
            connection.execute(
                """INSERT INTO active_artifacts(assessment_id, artifact_type, artifact_id)
                   VALUES (?, ?, ?)
                   ON CONFLICT(assessment_id, artifact_type)
                   DO UPDATE SET artifact_id = excluded.artifact_id""",
                (assessment_id, artifact_type.value, artifact_id),
            )
            connection.execute(
                """UPDATE assessments
                   SET current_stage = ?, source_filename = COALESCE(?, source_filename),
                       source_input_type = COALESCE(?, source_input_type),
                       document_id = COALESCE(?, document_id), updated_at = ?,
                       row_version = row_version + 1
                   WHERE assessment_id = ?""",
                (
                    stage.value,
                    source_filename,
                    source_input_type,
                    document_id,
                    now.isoformat(),
                    assessment_id,
                ),
            )
            if operation_id is not None:
                updated = connection.execute(
                    """UPDATE assessment_operations
                       SET status = ?, produced_artifact_id = ?, completed_at = ?
                       WHERE operation_id = ? AND assessment_id = ? AND status = ?""",
                    (
                        OperationStatus.COMPLETED.value,
                        artifact_id,
                        now.isoformat(),
                        operation_id,
                        assessment_id,
                        OperationStatus.STARTED.value,
                    ),
                ).rowcount
                if updated != 1:
                    raise PersistenceError("Operation was not in a completable state")
        return ArtifactReference(
            artifact_id=artifact_id,
            assessment_id=assessment_id,
            artifact_type=artifact_type,
            artifact_revision=revision,
        )

    def activate_artifact_and_advance(
        self,
        assessment_id: str,
        artifact_id: str,
        *,
        stage: WorkflowStage,
        deactivate_types: Iterable[ArtifactType] = (),
        source_filename: str | None = None,
        source_input_type: str | None = None,
        document_id: str | None = None,
    ) -> None:
        """Reactivate an immutable historical revision without rewriting it."""

        now = self.clock()
        with self._transaction() as connection:
            self._require_assessment(connection, assessment_id)
            row = connection.execute(
                """SELECT artifact_type FROM assessment_artifacts
                   WHERE artifact_id = ? AND assessment_id = ?""",
                (artifact_id, assessment_id),
            ).fetchone()
            if row is None:
                raise ArtifactNotFoundError("Artifact does not belong to assessment")
            artifact_type = ArtifactType(row["artifact_type"])
            connection.executemany(
                "DELETE FROM active_artifacts WHERE assessment_id = ? AND artifact_type = ?",
                ((assessment_id, item.value) for item in deactivate_types),
            )
            connection.execute(
                """INSERT INTO active_artifacts(assessment_id, artifact_type, artifact_id)
                   VALUES (?, ?, ?)
                   ON CONFLICT(assessment_id, artifact_type)
                   DO UPDATE SET artifact_id = excluded.artifact_id""",
                (assessment_id, artifact_type.value, artifact_id),
            )
            connection.execute(
                """UPDATE assessments SET current_stage = ?,
                   source_filename = COALESCE(?, source_filename),
                   source_input_type = COALESCE(?, source_input_type),
                   document_id = COALESCE(?, document_id), updated_at = ?,
                   row_version = row_version + 1 WHERE assessment_id = ?""",
                (
                    stage.value,
                    source_filename,
                    source_input_type,
                    document_id,
                    now.isoformat(),
                    assessment_id,
                ),
            )

    def load_active_artifact(
        self, assessment_id: str, artifact_type: ArtifactType
    ) -> StoredArtifact | None:
        with self._read() as connection:
            row = connection.execute(
                """SELECT a.* FROM active_artifacts aa
                   JOIN assessment_artifacts a ON a.artifact_id = aa.artifact_id
                   WHERE aa.assessment_id = ? AND aa.artifact_type = ?""",
                (assessment_id, artifact_type.value),
            ).fetchone()
        return None if row is None else self._stored(row)

    def load_artifact(self, artifact_id: str) -> StoredArtifact:
        with self._read() as connection:
            row = connection.execute(
                "SELECT * FROM assessment_artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
        if row is None:
            raise ArtifactNotFoundError("Artifact does not exist")
        return self._stored(row)

    def load_artifact_revision(
        self,
        assessment_id: str,
        artifact_type: ArtifactType,
        revision: int,
    ) -> StoredArtifact:
        with self._read() as connection:
            row = connection.execute(
                """SELECT * FROM assessment_artifacts
                   WHERE assessment_id = ? AND artifact_type = ? AND artifact_revision = ?""",
                (assessment_id, artifact_type.value, revision),
            ).fetchone()
        if row is None:
            raise ArtifactNotFoundError("Artifact revision does not exist")
        return self._stored(row)

    def list_artifact_revisions(
        self, assessment_id: str, artifact_type: ArtifactType
    ) -> list[StoredArtifact]:
        with self._read() as connection:
            rows = connection.execute(
                """SELECT * FROM assessment_artifacts
                   WHERE assessment_id = ? AND artifact_type = ?
                   ORDER BY artifact_revision""",
                (assessment_id, artifact_type.value),
            ).fetchall()
        return [self._stored(row) for row in rows]

    @staticmethod
    def _stored(row: sqlite3.Row) -> StoredArtifact:
        try:
            artifact_type = ArtifactType(row["artifact_type"])
        except ValueError as exc:
            raise PersistenceError("Stored artifact type is unsupported") from exc
        validate_schema_version(artifact_type, row["artifact_schema_version"])
        payload = deserialize_artifact(
            artifact_type, row["payload_json"], row["payload_sha256"]
        )
        return StoredArtifact(
            artifact_id=row["artifact_id"],
            assessment_id=row["assessment_id"],
            artifact_type=artifact_type,
            artifact_revision=row["artifact_revision"],
            artifact_schema_version=row["artifact_schema_version"],
            payload_sha256=row["payload_sha256"],
            parent_artifact_id=row["parent_artifact_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            payload=payload,
        )

    def load_workspace(self, assessment_id: str) -> WorkspaceSnapshot:
        assessment = self.get_assessment(assessment_id)
        active: dict[ArtifactType, StoredArtifact] = {}
        with self._read() as connection:
            rows = connection.execute(
                """SELECT a.* FROM active_artifacts aa
                   JOIN assessment_artifacts a ON a.artifact_id = aa.artifact_id
                   WHERE aa.assessment_id = ?""",
                (assessment_id,),
            ).fetchall()
        for row in rows:
            stored = self._stored(row)
            active[stored.artifact_type] = stored
        self._validate_active_chain(assessment, active)
        return WorkspaceSnapshot(assessment=assessment, active_artifacts=active)

    @staticmethod
    def _validate_active_chain(
        assessment: AssessmentRecord, active: dict[ArtifactType, StoredArtifact]
    ) -> None:
        integrated = active.get(ArtifactType.INTEGRATED_ASSESSMENT_RESULT)
        approved = active.get(ArtifactType.APPROVED_REVIEW)
        package = active.get(ArtifactType.DECISION_PACKAGE_RESULT)
        if integrated and (approved is None or integrated.parent_artifact_id != approved.artifact_id):
            raise PersistenceError("Active assessment is not linked to the active approval")
        if package and (integrated is None or package.parent_artifact_id != integrated.artifact_id):
            raise PersistenceError("Active package is not linked to the active assessment")
        requirements = {
            WorkflowStage.INGESTED: ArtifactType.INGESTION_RESULT,
            WorkflowStage.CANDIDATE_READY: ArtifactType.CANDIDATE_EXTRACTION_RESULT,
            WorkflowStage.IN_REVIEW: ArtifactType.REVIEW_SESSION,
            WorkflowStage.APPROVED: ArtifactType.APPROVED_REVIEW,
            WorkflowStage.ASSESSED: ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
            WorkflowStage.PACKAGE_READY: ArtifactType.DECISION_PACKAGE_RESULT,
        }
        required = requirements.get(assessment.current_stage)
        if required and required not in active:
            raise PersistenceError("Workflow stage has no matching active artifact")

    def invalidate_active_artifacts(
        self,
        assessment_id: str,
        artifact_types: Iterable[ArtifactType],
        *,
        stage: WorkflowStage,
    ) -> None:
        values = list(dict.fromkeys(item.value for item in artifact_types))
        now = self.clock()
        with self._transaction() as connection:
            self._require_assessment(connection, assessment_id)
            connection.executemany(
                "DELETE FROM active_artifacts WHERE assessment_id = ? AND artifact_type = ?",
                ((assessment_id, value) for value in values),
            )
            connection.execute(
                """UPDATE assessments SET current_stage = ?, updated_at = ?,
                   row_version = row_version + 1 WHERE assessment_id = ?""",
                (stage.value, now.isoformat(), assessment_id),
            )

    def begin_operation(
        self,
        assessment_id: str,
        kind: OperationKind,
        idempotency_key: str,
    ) -> OperationRecord:
        now = self.clock()
        with self._transaction() as connection:
            self._require_assessment(connection, assessment_id)
            existing = connection.execute(
                """SELECT * FROM assessment_operations
                   WHERE assessment_id = ? AND operation_kind = ? AND idempotency_key = ?""",
                (assessment_id, kind.value, idempotency_key),
            ).fetchone()
            if existing:
                record = self._operation(existing)
                if record.status is OperationStatus.STARTED:
                    raise OperationAlreadyStartedError(
                        "Operation already started; explicit recovery is required"
                    )
                if record.status is OperationStatus.FAILED:
                    connection.execute(
                        """UPDATE assessment_operations
                           SET status = ?, produced_artifact_id = NULL,
                               sanitised_error_code = NULL, started_at = ?,
                               completed_at = NULL WHERE operation_id = ?""",
                        (
                            OperationStatus.STARTED.value,
                            now.isoformat(),
                            record.operation_id,
                        ),
                    )
                    return record.model_copy(
                        update={
                            "status": OperationStatus.STARTED,
                            "started_at": now,
                            "completed_at": None,
                            "sanitised_error_code": None,
                        }
                    )
                return record
            operation_id = self.id_factory("operation")
            connection.execute(
                """INSERT INTO assessment_operations(
                    operation_id, assessment_id, operation_kind, idempotency_key,
                    status, started_at
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    operation_id,
                    assessment_id,
                    kind.value,
                    idempotency_key,
                    OperationStatus.STARTED.value,
                    now.isoformat(),
                ),
            )
        return OperationRecord(
            operation_id=operation_id,
            assessment_id=assessment_id,
            operation_kind=kind,
            idempotency_key=idempotency_key,
            status=OperationStatus.STARTED,
            started_at=now,
        )

    def fail_operation(self, operation_id: str, error_code: str) -> None:
        now = self.clock()
        with self._transaction() as connection:
            changed = connection.execute(
                """UPDATE assessment_operations SET status = ?, sanitised_error_code = ?,
                   completed_at = ? WHERE operation_id = ? AND status = ?""",
                (
                    OperationStatus.FAILED.value,
                    error_code,
                    now.isoformat(),
                    operation_id,
                    OperationStatus.STARTED.value,
                ),
            ).rowcount
            if changed != 1:
                raise PersistenceError("Operation was not in a fail-able state")

    @staticmethod
    def _operation(row: sqlite3.Row) -> OperationRecord:
        return OperationRecord(
            operation_id=row["operation_id"],
            assessment_id=row["assessment_id"],
            operation_kind=OperationKind(row["operation_kind"]),
            idempotency_key=row["idempotency_key"],
            status=OperationStatus(row["status"]),
            produced_artifact_id=row["produced_artifact_id"],
            sanitised_error_code=row["sanitised_error_code"],
            started_at=datetime.fromisoformat(row["started_at"]),
            completed_at=(
                datetime.fromisoformat(row["completed_at"])
                if row["completed_at"]
                else None
            ),
        )

    def delete_assessment(self, assessment_id: str, *, confirmed: bool) -> None:
        if not confirmed:
            raise ValueError("Assessment deletion requires explicit confirmation")
        with self._transaction() as connection:
            self._require_assessment(connection, assessment_id)
            connection.execute(
                "DELETE FROM assessments WHERE assessment_id = ?", (assessment_id,)
            )

    @staticmethod
    def _require_assessment(connection: sqlite3.Connection, assessment_id: str) -> None:
        if connection.execute(
            "SELECT 1 FROM assessments WHERE assessment_id = ?", (assessment_id,)
        ).fetchone() is None:
            raise ArtifactNotFoundError("Assessment does not exist")

    @staticmethod
    def _require_owned_artifact(
        connection: sqlite3.Connection, assessment_id: str, artifact_id: str
    ) -> ArtifactType:
        row = connection.execute(
            """SELECT artifact_type FROM assessment_artifacts
               WHERE artifact_id = ? AND assessment_id = ?""",
            (artifact_id, assessment_id),
        ).fetchone()
        if row is None:
            raise ArtifactNotFoundError("Parent artifact does not belong to assessment")
        return ArtifactType(row["artifact_type"])

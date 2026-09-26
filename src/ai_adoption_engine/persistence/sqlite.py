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
    AssessmentContractPin,
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
from ai_adoption_engine.persistence.contract_pins import (
    LEGACY_CONTRACT_PIN,
    VIRTUAL_LEGACY_CONTRACT_PIN,
    contract_operation_identity,
)
from ai_adoption_engine.persistence.serialization import (
    deserialize_artifact_versioned,
    serialize_artifact_versioned,
    validate_schema_version,
)
from ai_adoption_engine.persistence.workspace_protection import (
    FrozenEvaluationWorkspaceCompatibilityError,
    assert_workspace_write_target_allowed,
    is_frozen_evaluation_portfolio_path,
)


Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]

_EXPECTED_PARENT_TYPE = {
    ArtifactType.CANDIDATE_EXTRACTION_RESULT: ArtifactType.INGESTION_RESULT,
    ArtifactType.REVIEW_SESSION: ArtifactType.CANDIDATE_EXTRACTION_RESULT,
    ArtifactType.APPROVED_REVIEW: ArtifactType.REVIEW_SESSION,
    ArtifactType.INTEGRATED_ASSESSMENT_RESULT: ArtifactType.APPROVED_REVIEW,
    ArtifactType.DECISION_PACKAGE_RESULT: ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
    ArtifactType.GRW_EVIDENCE_SUBMISSION: ArtifactType.DECISION_PACKAGE_RESULT,
    ArtifactType.GRW_EVIDENCE_REVIEW: ArtifactType.GRW_EVIDENCE_SUBMISSION,
}
_REQUIRED_PARENT_TYPES = {
    ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
    ArtifactType.DECISION_PACKAGE_RESULT,
    ArtifactType.GRW_EVIDENCE_SUBMISSION,
    ArtifactType.GRW_EVIDENCE_REVIEW,
}

_PROTECTED_SCHEMA_SETS = {
    frozenset({1, 2, 3}),
    frozenset({1, 2, 3, 4}),
}
_CONTRACT_AWARE_OPERATION_KINDS = {
    OperationKind.ASSESS,
    OperationKind.GENERATE_PACKAGE,
}
_ASSESSMENT_SCHEMA_BY_CONTRACT = {
    "phase1-v0.3": "phase5-v0.1",
    "phase1-v0.4": "phase5-v0.2",
}
_PACKAGE_SCHEMA_BY_CONTRACT = {
    "phase1-v0.3": "phase6-v0.1",
    "phase1-v0.4": "phase6-v0.2",
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
        protected = is_frozen_evaluation_portfolio_path(self.path)
        if protected:
            if not self.path.is_file():
                raise FrozenEvaluationWorkspaceCompatibilityError(
                    "Frozen evaluation portfolio database must already exist and be a regular file"
                )
        elif str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: sqlite3.Connection | None = None
        if protected:
            self._assert_protected_schema_compatible()
        else:
            self._migrate()
        if not protected and str(self.path) != ":memory:" and self.path.exists():
            self.path.chmod(0o600)

    def _connect(self) -> sqlite3.Connection:
        if str(self.path) == ":memory:":
            if self._connection is None:
                self._connection = sqlite3.connect(":memory:")
                self._configure(self._connection)
            return self._connection
        protected = is_frozen_evaluation_portfolio_path(self.path)
        if protected:
            uri = f"{self.path.resolve(strict=True).as_uri()}?mode=ro&immutable=1"
            connection = sqlite3.connect(uri, uri=True)
        else:
            connection = sqlite3.connect(self.path)
        self._configure(connection, query_only=protected)
        return connection

    @staticmethod
    def _configure(
        connection: sqlite3.Connection, *, query_only: bool = False
    ) -> None:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        if query_only:
            connection.execute("PRAGMA query_only = ON")

    def _assert_protected_schema_compatible(self) -> None:
        try:
            with self._read() as connection:
                applied = {
                    row[0]
                    for row in connection.execute(
                        "SELECT version FROM schema_migrations"
                    )
                }
                actual_signature = self._schema_signature(connection)
        except (OSError, sqlite3.Error) as exc:
            raise FrozenEvaluationWorkspaceCompatibilityError(
                "Frozen evaluation portfolio database could not be opened safely in read-only mode"
            ) from exc
        if frozenset(applied) not in _PROTECTED_SCHEMA_SETS:
            raise FrozenEvaluationWorkspaceCompatibilityError(
                "Frozen evaluation portfolio database schema is incompatible with the current application; it will not be migrated in place"
            )
        if actual_signature != self._expected_schema_signature(applied):
            raise FrozenEvaluationWorkspaceCompatibilityError(
                "Frozen evaluation portfolio database schema is incompatible with the current application; it will not be migrated in place"
            )

    @staticmethod
    def _schema_signature(
        connection: sqlite3.Connection,
    ) -> tuple[tuple[str, str, str, str], ...]:
        objects = tuple(
            tuple(row)
            for row in connection.execute(
                """SELECT type, name, tbl_name, sql
                   FROM sqlite_master
                   WHERE sql IS NOT NULL
                     AND name NOT LIKE 'sqlite_%'
                     AND name != 'schema_migrations'
                   ORDER BY type, name"""
            )
        )
        migration_columns = repr(
            tuple(
                tuple(row[1:6])
                for row in connection.execute(
                    "PRAGMA table_info(schema_migrations)"
                )
            )
        )
        return objects + (
            ("table", "schema_migrations", "schema_migrations", migration_columns),
        )

    @classmethod
    def _expected_schema_signature(
        cls,
        applied: set[int],
    ) -> tuple[tuple[str, str, str, str], ...]:
        expected = sqlite3.connect(":memory:")
        try:
            for version, script in MIGRATIONS:
                if version in applied:
                    expected.executescript(script)
            return cls._schema_signature(expected)
        finally:
            expected.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        assert_workspace_write_target_allowed(self.path)
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
        assert_workspace_write_target_allowed(self.path)
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
        self,
        title: str,
        mode: ExecutionMode,
        *,
        contract_pin: AssessmentContractPin | None = None,
    ) -> AssessmentRecord:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Assessment title must be non-empty")
        now = self.clock()
        assessment_id = self.id_factory("assessment")
        pin = contract_pin or LEGACY_CONTRACT_PIN
        if pin.virtual:
            raise ValueError("A writable assessment cannot use a virtual contract pin")
        with self._transaction() as connection:
            connection.execute(
                """INSERT INTO assessments(
                    assessment_id, title, execution_mode, current_stage,
                    created_at, updated_at, row_version,
                    decision_contract_version, decision_policy_id,
                    decision_policy_version, decision_policy_fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
                (
                    assessment_id,
                    clean_title,
                    mode.value,
                    WorkflowStage.NEW.value,
                    now.isoformat(),
                    now.isoformat(),
                    pin.decision_contract_version,
                    pin.policy_id,
                    pin.policy_version,
                    pin.decision_policy_fingerprint,
                ),
            )
        return self.get_assessment(assessment_id)

    def pin_decision_contract(
        self,
        assessment_id: str,
        contract_pin: AssessmentContractPin,
    ) -> AssessmentRecord:
        """Set an explicit pin before approval; persisted decision history locks it."""

        if contract_pin.virtual:
            raise ValueError("A writable assessment cannot use a virtual contract pin")
        now = self.clock()
        with self._transaction() as connection:
            assessment_row = self._require_assessment(connection, assessment_id)
            current = self._assessment(assessment_row)
            if current.contract_pin == contract_pin:
                return current
            locked = connection.execute(
                """SELECT 1 FROM assessment_artifacts
                   WHERE assessment_id = ? AND artifact_type IN (?, ?, ?)
                   LIMIT 1""",
                (
                    assessment_id,
                    ArtifactType.APPROVED_REVIEW.value,
                    ArtifactType.INTEGRATED_ASSESSMENT_RESULT.value,
                    ArtifactType.DECISION_PACKAGE_RESULT.value,
                ),
            ).fetchone()
            if locked is not None:
                raise PersistenceError(
                    "Assessment contract pin is immutable after approval"
                )
            connection.execute(
                """UPDATE assessments
                   SET decision_contract_version = ?, decision_policy_id = ?,
                       decision_policy_version = ?, decision_policy_fingerprint = ?,
                       updated_at = ?, row_version = row_version + 1
                   WHERE assessment_id = ?""",
                (
                    contract_pin.decision_contract_version,
                    contract_pin.policy_id,
                    contract_pin.policy_version,
                    contract_pin.decision_policy_fingerprint,
                    now.isoformat(),
                    assessment_id,
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
        if "decision_contract_version" in row.keys():
            contract_pin = AssessmentContractPin(
                decision_contract_version=row["decision_contract_version"],
                policy_id=row["decision_policy_id"],
                policy_version=row["decision_policy_version"],
                decision_policy_fingerprint=row[
                    "decision_policy_fingerprint"
                ],
            )
        else:
            contract_pin = VIRTUAL_LEGACY_CONTRACT_PIN
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
            contract_pin=contract_pin,
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
        payload_json, payload_sha = serialize_artifact_versioned(
            artifact_type,
            artifact_schema_version,
            payload,
        )
        validated_payload = deserialize_artifact_versioned(
            artifact_type,
            artifact_schema_version,
            payload_json,
            payload_sha,
        )
        now = self.clock()
        with self._transaction() as connection:
            assessment_row = self._require_assessment(connection, assessment_id)
            pin = self._assessment(assessment_row).contract_pin
            self._validate_artifact_contract_pin(
                artifact_type,
                artifact_schema_version,
                pin,
            )
            self._validate_payload_contract_pin(
                artifact_type,
                artifact_schema_version,
                validated_payload,
                pin,
            )
            connection.executemany(
                "DELETE FROM active_artifacts WHERE assessment_id = ? AND artifact_type = ?",
                ((assessment_id, item.value) for item in deactivate_types),
            )
            if parent_artifact_id is not None:
                parent_type, parent_schema_version = self._require_owned_artifact(
                    connection, assessment_id, parent_artifact_id
                )
                expected_parent = _EXPECTED_PARENT_TYPE.get(artifact_type)
                if expected_parent is not None and parent_type is not expected_parent:
                    raise PersistenceError(
                        f"{artifact_type.value} requires parent {expected_parent.value}"
                    )
                self._validate_parent_contract_family(
                    artifact_type,
                    artifact_schema_version,
                    parent_type,
                    parent_schema_version,
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
                """SELECT * FROM assessment_artifacts
                   WHERE artifact_id = ? AND assessment_id = ?""",
                (artifact_id, assessment_id),
            ).fetchone()
            if row is None:
                raise ArtifactNotFoundError("Artifact does not belong to assessment")
            artifact_type = ArtifactType(row["artifact_type"])
            self._validate_row_parent_contract(connection, row)
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
            if row is None:
                return None
            pin = self._validate_row_parent_contract(connection, row)
            return self._stored(row, pin)

    def load_artifact(self, artifact_id: str) -> StoredArtifact:
        with self._read() as connection:
            row = connection.execute(
                "SELECT * FROM assessment_artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
            if row is None:
                raise ArtifactNotFoundError("Artifact does not exist")
            pin = self._validate_row_parent_contract(connection, row)
            return self._stored(row, pin)

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
            pin = self._validate_row_parent_contract(connection, row)
            return self._stored(row, pin)

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
            pins = [
                self._validate_row_parent_contract(connection, row)
                for row in rows
            ]
            return [
                self._stored(row, pin)
                for row, pin in zip(rows, pins, strict=True)
            ]

    @classmethod
    def _validate_row_parent_contract(
        cls,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> AssessmentContractPin:
        assessment_row = connection.execute(
            "SELECT * FROM assessments WHERE assessment_id = ?",
            (row["assessment_id"],),
        ).fetchone()
        if assessment_row is None:
            raise PersistenceError("Stored artifact has no owning assessment")
        pin = cls._assessment(assessment_row).contract_pin
        try:
            artifact_type = ArtifactType(row["artifact_type"])
        except ValueError as exc:
            raise PersistenceError("Stored artifact type is unsupported") from exc
        cls._validate_artifact_contract_pin(
            artifact_type,
            row["artifact_schema_version"],
            pin,
        )
        parent_id = row["parent_artifact_id"]
        expected_parent = _EXPECTED_PARENT_TYPE.get(artifact_type)
        if expected_parent is not None and parent_id is not None:
            parent = connection.execute(
                """SELECT artifact_type, artifact_schema_version
                   FROM assessment_artifacts
                   WHERE artifact_id = ? AND assessment_id = ?""",
                (parent_id, row["assessment_id"]),
            ).fetchone()
            try:
                parent_type = (
                    ArtifactType(parent["artifact_type"])
                    if parent is not None
                    else None
                )
            except ValueError as exc:
                raise PersistenceError(
                    "Stored artifact parent type is unsupported"
                ) from exc
            if parent is None or parent_type is not expected_parent:
                raise PersistenceError("Stored artifact parent chain is invalid")
            cls._validate_parent_contract_family(
                artifact_type,
                row["artifact_schema_version"],
                expected_parent,
                parent["artifact_schema_version"],
            )
        elif artifact_type in _REQUIRED_PARENT_TYPES:
            raise PersistenceError("Stored artifact is missing its required parent")
        return pin

    @staticmethod
    def _stored(
        row: sqlite3.Row,
        pin: AssessmentContractPin,
    ) -> StoredArtifact:
        try:
            artifact_type = ArtifactType(row["artifact_type"])
        except ValueError as exc:
            raise PersistenceError("Stored artifact type is unsupported") from exc
        validate_schema_version(artifact_type, row["artifact_schema_version"])
        payload = deserialize_artifact_versioned(
            artifact_type,
            row["artifact_schema_version"],
            row["payload_json"],
            row["payload_sha256"],
        )
        SQLiteAssessmentRepository._validate_payload_contract_pin(
            artifact_type,
            row["artifact_schema_version"],
            payload,
            pin,
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
                pin = self._validate_row_parent_contract(connection, row)
                stored = self._stored(row, pin)
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
        grw_submission = active.get(ArtifactType.GRW_EVIDENCE_SUBMISSION)
        grw_review = active.get(ArtifactType.GRW_EVIDENCE_REVIEW)
        if integrated and (approved is None or integrated.parent_artifact_id != approved.artifact_id):
            raise PersistenceError("Active assessment is not linked to the active approval")
        if package and (integrated is None or package.parent_artifact_id != integrated.artifact_id):
            raise PersistenceError("Active package is not linked to the active assessment")
        if grw_submission and (
            package is None or grw_submission.parent_artifact_id != package.artifact_id
        ):
            raise PersistenceError("Active GRW submission is not linked to the active package")
        if grw_review and (
            grw_submission is None
            or grw_review.parent_artifact_id != grw_submission.artifact_id
        ):
            raise PersistenceError("Active GRW review is not linked to the active submission")
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
            assessment_row = self._require_assessment(connection, assessment_id)
            pin = self._assessment(assessment_row).contract_pin
            contract_key = (
                contract_operation_identity(idempotency_key, pin)
                if kind in _CONTRACT_AWARE_OPERATION_KINDS
                else None
            )
            if contract_key is None:
                existing = connection.execute(
                    """SELECT * FROM assessment_operations
                       WHERE assessment_id = ? AND operation_kind = ?
                         AND idempotency_key = ?""",
                    (assessment_id, kind.value, idempotency_key),
                ).fetchone()
            else:
                existing = connection.execute(
                    """SELECT * FROM assessment_operations
                       WHERE assessment_id = ? AND operation_kind = ?
                         AND contract_idempotency_key = ?""",
                    (assessment_id, kind.value, contract_key),
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
            stored_idempotency_key = (
                contract_key
                if contract_key is not None
                and pin.decision_contract_version == "phase1-v0.4"
                else idempotency_key
            )
            connection.execute(
                """INSERT INTO assessment_operations(
                    operation_id, assessment_id, operation_kind, idempotency_key,
                    status, started_at, decision_contract_version,
                    decision_policy_fingerprint, contract_idempotency_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    operation_id,
                    assessment_id,
                    kind.value,
                    stored_idempotency_key,
                    OperationStatus.STARTED.value,
                    now.isoformat(),
                    (
                        pin.decision_contract_version
                        if contract_key is not None
                        else None
                    ),
                    (
                        pin.decision_policy_fingerprint
                        if contract_key is not None
                        else None
                    ),
                    contract_key,
                ),
            )
        return OperationRecord(
            operation_id=operation_id,
            assessment_id=assessment_id,
            operation_kind=kind,
            idempotency_key=idempotency_key,
            status=OperationStatus.STARTED,
            started_at=now,
            decision_contract_version=(
                pin.decision_contract_version if contract_key is not None else None
            ),
            decision_policy_fingerprint=(
                pin.decision_policy_fingerprint if contract_key is not None else None
            ),
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
        contract_columns = "decision_contract_version" in row.keys()
        stored_idempotency_key = row["idempotency_key"]
        decision_contract_version = (
            row["decision_contract_version"] if contract_columns else None
        )
        contract_idempotency_key = (
            row["contract_idempotency_key"]
            if contract_columns
            and "contract_idempotency_key" in row.keys()
            else None
        )
        if (
            decision_contract_version == "phase1-v0.4"
            and contract_idempotency_key == stored_idempotency_key
        ):
            prefix = (
                f"{decision_contract_version}:"
                f"{row['decision_policy_fingerprint']}:"
            )
            idempotency_key = stored_idempotency_key.removeprefix(prefix)
        else:
            idempotency_key = stored_idempotency_key
        return OperationRecord(
            operation_id=row["operation_id"],
            assessment_id=row["assessment_id"],
            operation_kind=OperationKind(row["operation_kind"]),
            idempotency_key=idempotency_key,
            status=OperationStatus(row["status"]),
            produced_artifact_id=row["produced_artifact_id"],
            sanitised_error_code=row["sanitised_error_code"],
            started_at=datetime.fromisoformat(row["started_at"]),
            completed_at=(
                datetime.fromisoformat(row["completed_at"])
                if row["completed_at"]
                else None
            ),
            decision_contract_version=(
                decision_contract_version
            ),
            decision_policy_fingerprint=(
                row["decision_policy_fingerprint"] if contract_columns else None
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
    def _require_assessment(
        connection: sqlite3.Connection,
        assessment_id: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM assessments WHERE assessment_id = ?", (assessment_id,)
        ).fetchone()
        if row is None:
            raise ArtifactNotFoundError("Assessment does not exist")
        return row

    @staticmethod
    def _require_owned_artifact(
        connection: sqlite3.Connection, assessment_id: str, artifact_id: str
    ) -> tuple[ArtifactType, str]:
        row = connection.execute(
            """SELECT artifact_type, artifact_schema_version
               FROM assessment_artifacts
               WHERE artifact_id = ? AND assessment_id = ?""",
            (artifact_id, assessment_id),
        ).fetchone()
        if row is None:
            raise ArtifactNotFoundError("Parent artifact does not belong to assessment")
        return ArtifactType(row["artifact_type"]), row["artifact_schema_version"]

    @staticmethod
    def _validate_artifact_contract_pin(
        artifact_type: ArtifactType,
        artifact_schema_version: str,
        pin: AssessmentContractPin,
    ) -> None:
        if artifact_type is ArtifactType.INTEGRATED_ASSESSMENT_RESULT:
            expected = _ASSESSMENT_SCHEMA_BY_CONTRACT[
                pin.decision_contract_version
            ]
            if artifact_schema_version != expected:
                raise PersistenceError(
                    "Integrated assessment schema does not match the workspace pin"
                )
        elif artifact_type is ArtifactType.DECISION_PACKAGE_RESULT:
            expected = _PACKAGE_SCHEMA_BY_CONTRACT[pin.decision_contract_version]
            if artifact_schema_version != expected:
                raise PersistenceError(
                    "Decision package schema does not match the workspace pin"
                )

    @staticmethod
    def _validate_payload_contract_pin(
        artifact_type: ArtifactType,
        artifact_schema_version: str,
        payload: Any,
        pin: AssessmentContractPin,
    ) -> None:
        if artifact_type is ArtifactType.INTEGRATED_ASSESSMENT_RESULT:
            metadata = getattr(payload, "metadata", None)
            if (
                metadata is not None
                and metadata.phase1_contract_version
                != pin.decision_contract_version
            ):
                raise PersistenceError(
                    "Integrated assessment contract does not match the workspace pin"
                )
            policy = getattr(payload, "policy", None)
        elif artifact_type is ArtifactType.DECISION_PACKAGE_RESULT:
            package = getattr(payload, "package", None)
            source = getattr(package, "source", None)
            if (
                artifact_schema_version == "phase6-v0.2"
                and source is not None
                and source.phase1_contract_version
                != pin.decision_contract_version
            ):
                raise PersistenceError(
                    "Decision package contract does not match the workspace pin"
                )
            policy = getattr(source, "policy", None)
        else:
            return
        if policy is not None and (
            policy.policy_id != pin.policy_id
            or policy.policy_version != pin.policy_version
            or policy.decision_policy_fingerprint
            != pin.decision_policy_fingerprint
        ):
            raise PersistenceError(
                "Persisted policy identity does not match the workspace pin"
            )

    @staticmethod
    def _validate_parent_contract_family(
        artifact_type: ArtifactType,
        artifact_schema_version: str,
        parent_type: ArtifactType,
        parent_schema_version: str,
    ) -> None:
        if (
            artifact_type is ArtifactType.DECISION_PACKAGE_RESULT
            and parent_type is ArtifactType.INTEGRATED_ASSESSMENT_RESULT
        ):
            expected_parent = {
                "phase6-v0.1": "phase5-v0.1",
                "phase6-v0.2": "phase5-v0.2",
            }[artifact_schema_version]
            if parent_schema_version != expected_parent:
                raise PersistenceError(
                    "Mixed legacy/successor Phase 5/6 parent chains are refused"
                )

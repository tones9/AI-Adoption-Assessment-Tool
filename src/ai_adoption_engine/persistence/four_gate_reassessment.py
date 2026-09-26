"""Additive SQLite repository for ``grw-m2-four-gate-v0.1``."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from ai_adoption_engine.grw.four_gate_m2.models import (
    SCHEMA_VERSION,
    FourGateM2ArtifactReference,
    FourGateM2ArtifactType,
    FourGateM2RunManifest,
    FourGateM2RunStage,
)
from ai_adoption_engine.persistence.base import ArtifactNotFoundError, PersistenceError
from ai_adoption_engine.persistence.four_gate_reassessment_serialization import (
    deserialize_four_gate_m2_artifact,
    serialize_four_gate_m2_artifact,
)


class FourGateM2FrozenWorkspaceError(PermissionError):
    pass


class FourGateM2PersistenceError(PersistenceError):
    pass


def assert_four_gate_m2_write_target_allowed(path: str | Path) -> None:
    candidate = Path(path)
    if str(candidate) == ":memory:":
        return
    parts = candidate.resolve(strict=False).parts
    if "evaluation" in parts and "portfolio" in parts:
        raise FourGateM2FrozenWorkspaceError(
            "Successor GRW/M2 writes are refused for frozen portfolio workspaces"
        )


_PARENTS: dict[FourGateM2ArtifactType, FourGateM2ArtifactType | None] = {
    FourGateM2ArtifactType.RUN_MANIFEST: None,
    FourGateM2ArtifactType.DOCUMENT_SUBMISSION: FourGateM2ArtifactType.RUN_MANIFEST,
    FourGateM2ArtifactType.EVIDENCE_REVIEW: FourGateM2ArtifactType.DOCUMENT_SUBMISSION,
    FourGateM2ArtifactType.DATA_READINESS_RESOLUTION: FourGateM2ArtifactType.EVIDENCE_REVIEW,
    FourGateM2ArtifactType.REASSESSMENT_REQUEST: FourGateM2ArtifactType.DATA_READINESS_RESOLUTION,
    FourGateM2ArtifactType.REASSESSMENT_APPROVAL: FourGateM2ArtifactType.REASSESSMENT_REQUEST,
    FourGateM2ArtifactType.SUCCESSOR_APPROVED_REVIEW: FourGateM2ArtifactType.REASSESSMENT_APPROVAL,
    FourGateM2ArtifactType.SUCCESSOR_INTEGRATED_ASSESSMENT: FourGateM2ArtifactType.SUCCESSOR_APPROVED_REVIEW,
    FourGateM2ArtifactType.SUCCESSOR_DECISION_PACKAGE: FourGateM2ArtifactType.SUCCESSOR_INTEGRATED_ASSESSMENT,
    FourGateM2ArtifactType.BASELINE_SUCCESSOR_COMPARISON: FourGateM2ArtifactType.SUCCESSOR_DECISION_PACKAGE,
}


_DDL = """
CREATE TABLE IF NOT EXISTS four_gate_reassessment_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS four_gate_reassessment_runs (
    run_id TEXT PRIMARY KEY,
    assessment_id TEXT NOT NULL REFERENCES assessments(assessment_id),
    family TEXT NOT NULL CHECK (family = 'grw-m2-four-gate-v0.1'),
    baseline_package_artifact_id TEXT NOT NULL REFERENCES assessment_artifacts(artifact_id),
    baseline_package_sha256 TEXT NOT NULL,
    creation_idempotency_key TEXT NOT NULL,
    stage TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (assessment_id, baseline_package_artifact_id, creation_idempotency_key)
);
CREATE TABLE IF NOT EXISTS four_gate_reassessment_documents (
    document_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES four_gate_reassessment_runs(run_id),
    content_sha256 TEXT NOT NULL,
    filename TEXT NOT NULL,
    source_label TEXT NOT NULL,
    content_bytes BLOB NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (run_id),
    UNIQUE (run_id, content_sha256)
);
CREATE TABLE IF NOT EXISTS four_gate_reassessment_artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES four_gate_reassessment_runs(run_id),
    artifact_type TEXT NOT NULL,
    artifact_revision INTEGER NOT NULL CHECK (artifact_revision >= 1),
    artifact_schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    parent_artifact_id TEXT REFERENCES four_gate_reassessment_artifacts(artifact_id),
    created_at TEXT NOT NULL,
    UNIQUE (run_id, artifact_type, artifact_revision)
);
CREATE TABLE IF NOT EXISTS active_four_gate_reassessment_artifacts (
    run_id TEXT NOT NULL REFERENCES four_gate_reassessment_runs(run_id),
    artifact_type TEXT NOT NULL,
    artifact_id TEXT NOT NULL REFERENCES four_gate_reassessment_artifacts(artifact_id),
    PRIMARY KEY (run_id, artifact_type)
);
CREATE TABLE IF NOT EXISTS four_gate_reassessment_operations (
    operation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES four_gate_reassessment_runs(run_id),
    operation_kind TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    produced_artifact_id TEXT REFERENCES four_gate_reassessment_artifacts(artifact_id),
    created_at TEXT NOT NULL,
    UNIQUE (run_id, operation_kind, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_four_gate_runs_baseline
    ON four_gate_reassessment_runs(assessment_id, baseline_package_artifact_id);
CREATE INDEX IF NOT EXISTS idx_four_gate_artifacts_run
    ON four_gate_reassessment_artifacts(run_id, artifact_type, artifact_revision);
"""


class SQLiteFourGateReassessmentRepository:
    """Append-only successor run store with no baseline mutation API."""

    def __init__(self, path: str | Path, *, clock=None, id_factory=None) -> None:
        assert_four_gate_m2_write_target_allowed(path)
        self.path = Path(path)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.id_factory = id_factory or (lambda prefix: f"{prefix}-{uuid4().hex}")
        self._memory_connection: sqlite3.Connection | None = None
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        if str(self.path) == ":memory:":
            if self._memory_connection is None:
                self._memory_connection = sqlite3.connect(":memory:")
                self._memory_connection.row_factory = sqlite3.Row
                self._memory_connection.execute("PRAGMA foreign_keys = ON")
            return self._memory_connection
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _migrate(self) -> None:
        assert_four_gate_m2_write_target_allowed(self.path)
        with self._transaction() as connection:
            connection.executescript(_DDL)
            connection.execute(
                "INSERT OR IGNORE INTO four_gate_reassessment_schema_migrations "
                "VALUES (1, ?)",
                (self.clock().isoformat(),),
            )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        assert_four_gate_m2_write_target_allowed(self.path)
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

    def create_run_with_manifest(
        self, manifest: FourGateM2RunManifest
    ) -> tuple[str, FourGateM2ArtifactReference, bool]:
        baseline = manifest.baseline
        with self._transaction() as connection:
            existing = connection.execute(
                """SELECT run_id FROM four_gate_reassessment_runs
                   WHERE assessment_id=? AND baseline_package_artifact_id=?
                     AND creation_idempotency_key=?""",
                (
                    baseline.assessment_id,
                    baseline.decision_package.artifact_id,
                    manifest.creation_idempotency_key,
                ),
            ).fetchone()
            if existing is not None:
                reference = self._active_ref(
                    connection,
                    str(existing["run_id"]),
                    FourGateM2ArtifactType.RUN_MANIFEST,
                )
                if reference is None:
                    raise FourGateM2PersistenceError(
                        "Existing successor run has no manifest"
                    )
                return str(existing["run_id"]), reference, True
            row = connection.execute(
                """SELECT a.payload_sha256, a.artifact_schema_version,
                          a.artifact_revision,
                          s.decision_contract_version, s.decision_policy_id,
                          s.decision_policy_version, s.decision_policy_fingerprint
                   FROM assessment_artifacts a JOIN assessments s
                     ON s.assessment_id=a.assessment_id
                   WHERE a.artifact_id=? AND a.assessment_id=?""",
                (
                    baseline.decision_package.artifact_id,
                    baseline.assessment_id,
                ),
            ).fetchone()
            if row is None or (
                row["payload_sha256"] != baseline.decision_package.payload_sha256
                or row["artifact_revision"]
                != baseline.decision_package.artifact_revision
                or row["artifact_schema_version"] != "phase6-v0.2"
                or row["decision_contract_version"] != "phase1-v0.4"
                or row["decision_policy_id"] != "decision_policy.v0.3"
                or row["decision_policy_version"] != "0.3.0"
                or row["decision_policy_fingerprint"]
                != baseline.decision_policy_fingerprint
            ):
                raise FourGateM2PersistenceError(
                    "Pinned successor baseline is unavailable or inconsistent"
                )
            pinned = (
                (baseline.approved_review, "APPROVED_REVIEW", "phase4-v0.1", None),
                (
                    baseline.integrated_assessment,
                    "INTEGRATED_ASSESSMENT_RESULT",
                    "phase5-v0.2",
                    baseline.approved_review.artifact_id,
                ),
                (
                    baseline.decision_package,
                    "DECISION_PACKAGE_RESULT",
                    "phase6-v0.2",
                    baseline.integrated_assessment.artifact_id,
                ),
            )
            for reference, artifact_type, schema_version, parent_id in pinned:
                artifact = connection.execute(
                    """SELECT a.artifact_revision, a.payload_sha256,
                              a.artifact_schema_version, a.parent_artifact_id
                       FROM assessment_artifacts a
                       JOIN active_artifacts aa ON aa.artifact_id=a.artifact_id
                       WHERE a.artifact_id=? AND a.assessment_id=?
                         AND a.artifact_type=? AND aa.assessment_id=a.assessment_id
                         AND aa.artifact_type=a.artifact_type""",
                    (reference.artifact_id, baseline.assessment_id, artifact_type),
                ).fetchone()
                if artifact is None or (
                    artifact["artifact_revision"] != reference.artifact_revision
                    or artifact["payload_sha256"] != reference.payload_sha256
                    or artifact["artifact_schema_version"] != schema_version
                    or (
                        parent_id is not None
                        and artifact["parent_artifact_id"] != parent_id
                    )
                ):
                    raise FourGateM2PersistenceError(
                        "Pinned successor baseline chain changed before run creation"
                    )
            now = self.clock().isoformat()
            connection.execute(
                """INSERT INTO four_gate_reassessment_runs
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    manifest.run_id,
                    baseline.assessment_id,
                    SCHEMA_VERSION,
                    baseline.decision_package.artifact_id,
                    baseline.decision_package.payload_sha256,
                    manifest.creation_idempotency_key,
                    FourGateM2RunStage.OPEN.value,
                    now,
                    now,
                ),
            )
            reference = self._save_artifact(
                connection,
                manifest.run_id,
                FourGateM2ArtifactType.RUN_MANIFEST,
                manifest,
                parent=None,
            )
            self._record_operation(
                connection,
                manifest.run_id,
                "CREATE_RUN",
                manifest.creation_idempotency_key,
                reference.artifact_id,
            )
            return manifest.run_id, reference, False

    def save_document_and_submission(
        self,
        run_id: str,
        document,
        content_bytes: bytes,
        submission,
        *,
        parent: FourGateM2ArtifactReference,
        idempotency_key: str,
    ) -> FourGateM2ArtifactReference:
        with self._transaction() as connection:
            self._require_stage(connection, run_id, FourGateM2RunStage.OPEN)
            connection.execute(
                """INSERT INTO four_gate_reassessment_documents
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    document.document_id,
                    run_id,
                    document.content_sha256,
                    document.filename,
                    document.source_label,
                    content_bytes,
                    self.clock().isoformat(),
                ),
            )
            reference = self._save_artifact(
                connection,
                run_id,
                FourGateM2ArtifactType.DOCUMENT_SUBMISSION,
                submission,
                parent=parent,
            )
            self._advance(connection, run_id, FourGateM2RunStage.DOCUMENT_SUBMITTED)
            self._record_operation(
                connection,
                run_id,
                "SUBMIT_DOCUMENT",
                idempotency_key,
                reference.artifact_id,
            )
            return reference

    def save_artifact_and_advance(
        self,
        run_id: str,
        artifact_type: FourGateM2ArtifactType,
        payload,
        *,
        parent: FourGateM2ArtifactReference,
        expected_stage: FourGateM2RunStage,
        stage: FourGateM2RunStage,
        idempotency_key: str,
    ) -> FourGateM2ArtifactReference:
        with self._transaction() as connection:
            self._require_stage(connection, run_id, expected_stage)
            reference = self._save_artifact(
                connection, run_id, artifact_type, payload, parent=parent
            )
            self._advance(connection, run_id, stage)
            self._record_operation(
                connection,
                run_id,
                artifact_type.value,
                idempotency_key,
                reference.artifact_id,
            )
            return reference

    def load_run(self, run_id: str) -> dict:
        with self._read() as connection:
            row = connection.execute(
                "SELECT * FROM four_gate_reassessment_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise ArtifactNotFoundError("Successor reassessment run does not exist")
        if row["family"] != SCHEMA_VERSION:
            raise FourGateM2PersistenceError("Successor reassessment family changed")
        return dict(row)

    def list_runs(self, assessment_id: str) -> list[dict]:
        with self._read() as connection:
            rows = connection.execute(
                """SELECT * FROM four_gate_reassessment_runs
                   WHERE assessment_id=? AND family=?
                   ORDER BY created_at, run_id""",
                (assessment_id, SCHEMA_VERSION),
            ).fetchall()
        return [dict(row) for row in rows]

    def load_artifact_reference(
        self, run_id: str, artifact_type: FourGateM2ArtifactType
    ) -> FourGateM2ArtifactReference | None:
        with self._read() as connection:
            return self._active_ref(connection, run_id, artifact_type)

    def load_artifact(self, artifact_id: str):
        with self._read() as connection:
            row = connection.execute(
                "SELECT * FROM four_gate_reassessment_artifacts WHERE artifact_id=?",
                (artifact_id,),
            ).fetchone()
        if row is None:
            raise ArtifactNotFoundError("Successor reassessment artifact does not exist")
        return deserialize_four_gate_m2_artifact(
            FourGateM2ArtifactType(row["artifact_type"]),
            row["artifact_schema_version"],
            row["payload_json"],
            row["payload_sha256"],
        )

    def load_document_bytes(self, document_id: str) -> bytes:
        with self._read() as connection:
            row = connection.execute(
                "SELECT content_bytes FROM four_gate_reassessment_documents "
                "WHERE document_id=?",
                (document_id,),
            ).fetchone()
        if row is None:
            raise ArtifactNotFoundError("Successor supporting document does not exist")
        return bytes(row["content_bytes"])

    def _save_artifact(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        artifact_type: FourGateM2ArtifactType,
        payload,
        *,
        parent: FourGateM2ArtifactReference | None,
    ) -> FourGateM2ArtifactReference:
        expected_parent = _PARENTS[artifact_type]
        if expected_parent is None:
            if parent is not None:
                raise FourGateM2PersistenceError("Manifest cannot have a parent")
        else:
            if parent is None:
                raise FourGateM2PersistenceError("Successor artifact requires a parent")
            parent_row = connection.execute(
                """SELECT artifact_type, artifact_revision, payload_sha256 FROM
                   four_gate_reassessment_artifacts
                   WHERE artifact_id=? AND run_id=?""",
                (parent.artifact_id, run_id),
            ).fetchone()
            if (
                parent_row is None
                or parent_row["artifact_type"] != expected_parent.value
                or parent_row["artifact_revision"] != parent.artifact_revision
                or parent_row["payload_sha256"] != parent.payload_sha256
            ):
                raise FourGateM2PersistenceError(
                    "Successor reassessment parent chain is invalid"
                )
        payload_json, payload_sha = serialize_four_gate_m2_artifact(
            artifact_type, SCHEMA_VERSION, payload
        )
        revision = connection.execute(
            """SELECT COALESCE(MAX(artifact_revision), 0) + 1
               FROM four_gate_reassessment_artifacts
               WHERE run_id=? AND artifact_type=?""",
            (run_id, artifact_type.value),
        ).fetchone()[0]
        artifact_id = self.id_factory("four-gate-reassessment-artifact")
        connection.execute(
            """INSERT INTO four_gate_reassessment_artifacts
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                artifact_id,
                run_id,
                artifact_type.value,
                revision,
                SCHEMA_VERSION,
                payload_json,
                payload_sha,
                parent.artifact_id if parent else None,
                self.clock().isoformat(),
            ),
        )
        connection.execute(
            """INSERT INTO active_four_gate_reassessment_artifacts
               VALUES (?, ?, ?)
               ON CONFLICT(run_id, artifact_type)
               DO UPDATE SET artifact_id=excluded.artifact_id""",
            (run_id, artifact_type.value, artifact_id),
        )
        return FourGateM2ArtifactReference(
            artifact_id=artifact_id,
            artifact_revision=revision,
            payload_sha256=payload_sha,
        )

    @staticmethod
    def _active_ref(
        connection: sqlite3.Connection,
        run_id: str,
        artifact_type: FourGateM2ArtifactType,
    ) -> FourGateM2ArtifactReference | None:
        row = connection.execute(
            """SELECT a.artifact_id, a.artifact_revision, a.payload_sha256
               FROM active_four_gate_reassessment_artifacts aa
               JOIN four_gate_reassessment_artifacts a
                 ON a.artifact_id=aa.artifact_id
                AND a.run_id=aa.run_id AND a.artifact_type=aa.artifact_type
               WHERE aa.run_id=? AND aa.artifact_type=?""",
            (run_id, artifact_type.value),
        ).fetchone()
        return FourGateM2ArtifactReference(**dict(row)) if row is not None else None

    @staticmethod
    def _require_stage(
        connection: sqlite3.Connection,
        run_id: str,
        expected: FourGateM2RunStage,
    ) -> None:
        row = connection.execute(
            "SELECT stage FROM four_gate_reassessment_runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row is None or row["stage"] != expected.value:
            raise FourGateM2PersistenceError(
                f"Successor run must be at {expected.value}"
            )

    def _advance(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        stage: FourGateM2RunStage,
    ) -> None:
        connection.execute(
            "UPDATE four_gate_reassessment_runs SET stage=?, updated_at=? WHERE run_id=?",
            (stage.value, self.clock().isoformat(), run_id),
        )

    def _record_operation(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        operation_kind: str,
        idempotency_key: str,
        artifact_id: str,
    ) -> None:
        connection.execute(
            """INSERT INTO four_gate_reassessment_operations
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                self.id_factory("four-gate-reassessment-operation"),
                run_id,
                operation_kind,
                idempotency_key,
                artifact_id,
                self.clock().isoformat(),
            ),
        )

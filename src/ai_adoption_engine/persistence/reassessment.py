"""Dedicated append-only SQLite persistence for GRW M2 reassessment runs."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from ai_adoption_engine.grw.m2.models import (
    M2ArtifactReference,
    M2ArtifactType,
    M2BaselineReference,
    M2EvidenceClass,
    M2EvidencePermission,
    M2RunStage,
)
from ai_adoption_engine.persistence.base import ArtifactNotFoundError, PersistenceError
from ai_adoption_engine.persistence.reassessment_serialization import (
    deserialize_m2_artifact,
    serialize_m2_artifact,
)


def assert_m2_write_target_allowed(database_path: str | Path) -> None:
    """Refuse a frozen portfolio location before opening or migrating it."""

    path = Path(database_path)
    if str(path) == ":memory:":
        return
    parts = path.resolve(strict=False).parts
    if "evaluation" in parts and "portfolio" in parts:
        raise M2FrozenWorkspaceError(
            "GRW M2 writes are refused for frozen evaluation portfolio workspaces"
        )


class M2FrozenWorkspaceError(PermissionError):
    pass


class M2PersistenceError(PersistenceError):
    pass


_PARENTS: dict[M2ArtifactType, M2ArtifactType | None] = {
    M2ArtifactType.RUN_MANIFEST: None,
    M2ArtifactType.DOCUMENT_SUBMISSION: M2ArtifactType.RUN_MANIFEST,
    M2ArtifactType.EVIDENCE_REVIEW: M2ArtifactType.DOCUMENT_SUBMISSION,
    M2ArtifactType.DATA_READINESS_RESOLUTION: M2ArtifactType.EVIDENCE_REVIEW,
    M2ArtifactType.REASSESSMENT_REQUEST: M2ArtifactType.DATA_READINESS_RESOLUTION,
    M2ArtifactType.REASSESSMENT_APPROVAL: M2ArtifactType.REASSESSMENT_REQUEST,
    M2ArtifactType.SUCCESSOR_APPROVED_REVIEW: M2ArtifactType.REASSESSMENT_APPROVAL,
    M2ArtifactType.SUCCESSOR_INTEGRATED_ASSESSMENT: M2ArtifactType.SUCCESSOR_APPROVED_REVIEW,
    M2ArtifactType.SUCCESSOR_DECISION_PACKAGE: M2ArtifactType.SUCCESSOR_INTEGRATED_ASSESSMENT,
    M2ArtifactType.BASELINE_SUCCESSOR_COMPARISON: M2ArtifactType.SUCCESSOR_DECISION_PACKAGE,
}

_EXPECTED_PRIOR_STAGES: dict[M2ArtifactType, M2RunStage] = {
    M2ArtifactType.RUN_MANIFEST: M2RunStage.OPEN,
    M2ArtifactType.DOCUMENT_SUBMISSION: M2RunStage.OPEN,
    M2ArtifactType.EVIDENCE_REVIEW: M2RunStage.DOCUMENT_SUBMITTED,
    M2ArtifactType.DATA_READINESS_RESOLUTION: M2RunStage.EVIDENCE_REVIEWED,
    M2ArtifactType.REASSESSMENT_REQUEST: M2RunStage.RESOLUTION_PROPOSED,
    M2ArtifactType.REASSESSMENT_APPROVAL: M2RunStage.REQUESTED,
    M2ArtifactType.SUCCESSOR_APPROVED_REVIEW: M2RunStage.APPROVED,
    M2ArtifactType.SUCCESSOR_INTEGRATED_ASSESSMENT: M2RunStage.SUCCESSOR_REVIEW_READY,
    M2ArtifactType.SUCCESSOR_DECISION_PACKAGE: M2RunStage.ASSESSED,
    M2ArtifactType.BASELINE_SUCCESSOR_COMPARISON: M2RunStage.PACKAGE_READY,
}


def _now() -> datetime:
    return datetime.now(UTC)


class SQLiteReassessmentRepository:
    """M2-only immutable tables, pointers, and operation records.

    This repository has no baseline mutation API. Its active-pointer namespace is
    deliberately disjoint from ``active_artifacts``.
    """

    def __init__(self, path: str | Path, *, clock=_now, id_factory=None) -> None:
        assert_m2_write_target_allowed(path)
        self.path = Path(path)
        self.clock = clock
        self.id_factory = id_factory or (lambda prefix: f"{prefix}-{uuid4().hex}")
        self._connection: sqlite3.Connection | None = None
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        if str(self.path) == ":memory:":
            if self._connection is None:
                self._connection = sqlite3.connect(":memory:")
                self._connection.row_factory = sqlite3.Row
                self._connection.execute("PRAGMA foreign_keys = ON")
            return self._connection
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _migrate(self) -> None:
        from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository

        SQLiteAssessmentRepository(self.path, clock=self.clock, id_factory=self.id_factory)

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        assert_m2_write_target_allowed(self.path)
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
        self,
        assessment_id: str,
        package_artifact_id: str,
        package_sha256: str,
        *,
        creation_idempotency_key: str,
        manifest_payload: dict[str, Any],
    ) -> tuple[str, M2ArtifactReference, bool]:
        """Atomically create a run, root manifest, and completed create operation."""

        assert_m2_write_target_allowed(self.path)
        with self._transaction() as c:
            existing = c.execute(
                """SELECT run_id FROM reassessment_runs
                   WHERE assessment_id=? AND baseline_package_artifact_id=?
                     AND creation_idempotency_key=?""",
                (assessment_id, package_artifact_id, creation_idempotency_key),
            ).fetchone()
            if existing is not None:
                run_id = str(existing["run_id"])
                reference = self._active_ref_in_tx(c, run_id, M2ArtifactType.RUN_MANIFEST)
                if reference is None:
                    raise M2PersistenceError("Existing M2 run is missing its immutable manifest")
                return run_id, reference, True

            baseline = c.execute(
                """SELECT artifact_id, payload_sha256 FROM assessment_artifacts
                   WHERE artifact_id=? AND assessment_id=?""",
                (package_artifact_id, assessment_id),
            ).fetchone()
            if baseline is None or baseline["payload_sha256"] != package_sha256:
                raise M2PersistenceError("The pinned baseline package is unavailable")
            run_id = self.id_factory("reassessment-run")
            now = self.clock().isoformat()
            c.execute(
                """INSERT INTO reassessment_runs(
                       run_id, assessment_id, baseline_package_artifact_id,
                       baseline_package_sha256, creation_idempotency_key, stage,
                       created_at, updated_at, row_version
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    run_id,
                    assessment_id,
                    package_artifact_id,
                    package_sha256,
                    creation_idempotency_key,
                    M2RunStage.OPEN.value,
                    now,
                    now,
                ),
            )
            operation_id = self._begin_operation_in_tx(
                c, run_id, "CREATE_RUN", creation_idempotency_key
            )
            manifest = self._save_artifact(
                c,
                run_id,
                M2ArtifactType.RUN_MANIFEST,
                manifest_payload,
                None,
                M2RunStage.OPEN,
            )
            self._complete_operation_in_tx(c, operation_id, manifest.artifact_id)
            return run_id, manifest, False

    def load_run(self, run_id: str) -> dict[str, Any]:
        with self._read() as c:
            row = c.execute(
                "SELECT * FROM reassessment_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise ArtifactNotFoundError("Reassessment run does not exist")
            self._validate_parent_chain_in_tx(c, run_id)
            return dict(row)

    def begin_operation(
        self, run_id: str, operation_kind: str, idempotency_key: str
    ) -> dict[str, Any]:
        assert_m2_write_target_allowed(self.path)
        with self._transaction() as c:
            self._require_run(c, run_id)
            row = c.execute(
                """SELECT * FROM reassessment_operations
                   WHERE run_id=? AND operation_kind=? AND idempotency_key=?""",
                (run_id, operation_kind, idempotency_key),
            ).fetchone()
            if row is not None:
                return dict(row)
            operation_id = self._begin_operation_in_tx(
                c, run_id, operation_kind, idempotency_key
            )
            return {
                "operation_id": operation_id,
                "run_id": run_id,
                "operation_kind": operation_kind,
                "idempotency_key": idempotency_key,
                "status": "PENDING",
                "produced_artifact_id": None,
                "sanitised_error_code": None,
            }

    def complete_operation(self, operation_id: str, artifact_id: str | None = None) -> None:
        assert_m2_write_target_allowed(self.path)
        with self._transaction() as c:
            self._complete_operation_in_tx(c, operation_id, artifact_id)

    def fail_operation(
        self,
        operation_id: str,
        sanitised_error_code: str,
        *,
        terminal_stage: M2RunStage | None = None,
    ) -> None:
        assert_m2_write_target_allowed(self.path)
        with self._transaction() as c:
            row = c.execute(
                "SELECT run_id, status FROM reassessment_operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if row is None:
                raise ArtifactNotFoundError("M2 operation does not exist")
            if row["status"] == "COMPLETED":
                raise M2PersistenceError("A completed M2 operation cannot be failed")
            now = self.clock().isoformat()
            c.execute(
                """UPDATE reassessment_operations
                   SET status='FAILED', sanitised_error_code=?, completed_at=?
                   WHERE operation_id=?""",
                (sanitised_error_code, now, operation_id),
            )
            if terminal_stage is not None:
                c.execute(
                    """UPDATE reassessment_runs
                       SET stage=?, updated_at=?, row_version=row_version+1
                       WHERE run_id=?""",
                    (terminal_stage.value, now, row["run_id"]),
                )

    def save_document_and_submission(
        self,
        run_id: str,
        document: Any,
        content_bytes: bytes,
        submission: Any,
        parent: M2ArtifactReference,
        *,
        operation_id: str | None = None,
    ) -> M2ArtifactReference:
        assert_m2_write_target_allowed(self.path)
        with self._transaction() as c:
            self._require_stage(c, run_id, M2RunStage.OPEN)
            c.execute(
                """INSERT INTO reassessment_documents(
                       document_id, run_id, content_sha256, content_type, filename,
                       source_label, content_bytes, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    document.document_id,
                    run_id,
                    document.content_sha256,
                    document.content_type,
                    document.filename,
                    document.source_label,
                    content_bytes,
                    document.received_at.isoformat(),
                ),
            )
            reference = self._save_artifact(
                c,
                run_id,
                M2ArtifactType.DOCUMENT_SUBMISSION,
                submission,
                parent.artifact_id,
                M2RunStage.DOCUMENT_SUBMITTED,
            )
            if operation_id is not None:
                self._complete_operation_in_tx(c, operation_id, reference.artifact_id)
            return reference

    def save_artifact_and_advance(
        self,
        run_id: str,
        artifact_type: M2ArtifactType,
        payload: Any,
        parent_artifact_id: str,
        stage: M2RunStage,
        *,
        operation_id: str | None = None,
    ) -> M2ArtifactReference:
        assert_m2_write_target_allowed(self.path)
        with self._transaction() as c:
            reference = self._save_artifact(
                c, run_id, artifact_type, payload, parent_artifact_id, stage
            )
            if operation_id is not None:
                self._complete_operation_in_tx(c, operation_id, reference.artifact_id)
            return reference

    def load_artifact(self, artifact_id: str) -> Any:
        with self._read() as c:
            row = c.execute(
                "SELECT * FROM reassessment_artifacts WHERE artifact_id=?", (artifact_id,)
            ).fetchone()
        if row is None:
            raise ArtifactNotFoundError("M2 artifact does not exist")
        return deserialize_m2_artifact(
            row["artifact_type"], row["payload_json"], row["payload_sha256"]
        )

    def load_artifact_reference(
        self, run_id: str, artifact_type: M2ArtifactType
    ) -> M2ArtifactReference | None:
        with self._read() as c:
            return self._active_ref_in_tx(c, run_id, artifact_type)

    def load_document_bytes(self, document_id: str) -> bytes:
        with self._read() as c:
            row = c.execute(
                "SELECT content_bytes FROM reassessment_documents WHERE document_id=?",
                (document_id,),
            ).fetchone()
        if row is None:
            raise ArtifactNotFoundError("M2 supporting document does not exist")
        return bytes(row["content_bytes"])

    def verify_successor_for_phase5(self, successor: Any) -> bool:
        """Verify persisted M2 approval lineage before Phase 5 accepts a successor."""

        try:
            from ai_adoption_engine.grw.m2.instrument import load_instrument_reference
            from ai_adoption_engine.grw.m2.policy import load_policy_reference

            run_id = successor.run_id
            with self._read() as c:
                run = self._require_run(c, run_id)
                if run["stage"] != M2RunStage.SUCCESSOR_REVIEW_READY.value:
                    return False
                successor_ref = self._active_ref_in_tx(
                    c, run_id, M2ArtifactType.SUCCESSOR_APPROVED_REVIEW
                )
                if successor_ref is None:
                    return False
                stored = self._load_artifact_in_tx(c, successor_ref)
                if stored != successor:
                    return False
                refs = {
                    kind: self._active_ref_in_tx(c, run_id, kind)
                    for kind in (
                        M2ArtifactType.RUN_MANIFEST,
                        M2ArtifactType.DOCUMENT_SUBMISSION,
                        M2ArtifactType.EVIDENCE_REVIEW,
                        M2ArtifactType.DATA_READINESS_RESOLUTION,
                        M2ArtifactType.REASSESSMENT_REQUEST,
                        M2ArtifactType.REASSESSMENT_APPROVAL,
                    )
                }
                if any(reference is None for reference in refs.values()):
                    return False
                manifest = self._load_artifact_in_tx(c, refs[M2ArtifactType.RUN_MANIFEST])
                manifest_baseline = M2BaselineReference.model_validate(manifest["baseline"])
                submission = self._load_artifact_in_tx(c, refs[M2ArtifactType.DOCUMENT_SUBMISSION])
                review = self._load_artifact_in_tx(c, refs[M2ArtifactType.EVIDENCE_REVIEW])
                resolution = self._load_artifact_in_tx(c, refs[M2ArtifactType.DATA_READINESS_RESOLUTION])
                request = self._load_artifact_in_tx(c, refs[M2ArtifactType.REASSESSMENT_REQUEST])
                approval = self._load_artifact_in_tx(c, refs[M2ArtifactType.REASSESSMENT_APPROVAL])
                ordered = (
                    (successor_ref, refs[M2ArtifactType.REASSESSMENT_APPROVAL]),
                    (refs[M2ArtifactType.REASSESSMENT_APPROVAL], refs[M2ArtifactType.REASSESSMENT_REQUEST]),
                    (refs[M2ArtifactType.REASSESSMENT_REQUEST], refs[M2ArtifactType.DATA_READINESS_RESOLUTION]),
                    (refs[M2ArtifactType.DATA_READINESS_RESOLUTION], refs[M2ArtifactType.EVIDENCE_REVIEW]),
                    (refs[M2ArtifactType.EVIDENCE_REVIEW], refs[M2ArtifactType.DOCUMENT_SUBMISSION]),
                    (refs[M2ArtifactType.DOCUMENT_SUBMISSION], refs[M2ArtifactType.RUN_MANIFEST]),
                )
                if any(not self._parent_is(c, child.artifact_id, parent.artifact_id) for child, parent in ordered):
                    return False
                if successor.baseline_approved_review != manifest_baseline.approved_review:
                    return False
                if successor.request_artifact != refs[M2ArtifactType.REASSESSMENT_REQUEST]:
                    return False
                if successor.approval_artifact != refs[M2ArtifactType.REASSESSMENT_APPROVAL]:
                    return False
                if successor.evidence_review_artifact != refs[M2ArtifactType.EVIDENCE_REVIEW]:
                    return False
                if successor.resolution_artifact != refs[M2ArtifactType.DATA_READINESS_RESOLUTION]:
                    return False
                if successor.data_readiness_resolution != resolution:
                    return False
                if review.submission_artifact != refs[M2ArtifactType.DOCUMENT_SUBMISSION]:
                    return False
                if resolution.evidence_review_artifact != refs[M2ArtifactType.EVIDENCE_REVIEW]:
                    return False
                if request.evidence_review_artifact != refs[M2ArtifactType.EVIDENCE_REVIEW] or request.resolution_artifact != refs[M2ArtifactType.DATA_READINESS_RESOLUTION]:
                    return False
                if approval.request_artifact != refs[M2ArtifactType.REASSESSMENT_REQUEST]:
                    return False
                if request.baseline != manifest_baseline:
                    return False
                if review.permission is not M2EvidencePermission.CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE:
                    return False
                if review.evidence_class is not M2EvidenceClass.DOCUMENT_SUPPORTED:
                    return False
                if submission.evidence_class is not M2EvidenceClass.DOCUMENT_SUPPORTED_CANDIDATE:
                    return False
                document_row = c.execute(
                    "SELECT content_bytes, run_id FROM reassessment_documents WHERE document_id=?",
                    (submission.document.document_id,),
                ).fetchone()
                if document_row is None or document_row["run_id"] != run_id:
                    return False
                if hashlib.sha256(bytes(document_row["content_bytes"])).hexdigest() != submission.document.content_sha256:
                    return False
                _, policy = load_policy_reference()
                _, instrument = load_instrument_reference()
                if not (
                    review.admissibility_policy == policy
                    and resolution.admissibility_policy == policy
                    and request.admissibility_policy == policy
                    and resolution.instrument == instrument
                    and request.instrument == instrument
                ):
                    return False
                normal = self._normal_baseline_refs_in_tx(c, str(run["assessment_id"]))
                baseline = manifest_baseline.model_dump(mode="json")
                if (
                    normal.get("APPROVED_REVIEW") != baseline["approved_review"]
                    or normal.get("INTEGRATED_ASSESSMENT_RESULT") != baseline["integrated_assessment"]
                    or normal.get("DECISION_PACKAGE_RESULT") != baseline["decision_package"]
                ):
                    return False
                return True
        except Exception:
            return False

    def _save_artifact(
        self,
        c: sqlite3.Connection,
        run_id: str,
        artifact_type: M2ArtifactType,
        payload: Any,
        parent_artifact_id: str | None,
        stage: M2RunStage,
    ) -> M2ArtifactReference:
        self._require_stage(c, run_id, _EXPECTED_PRIOR_STAGES[artifact_type])
        current = c.execute(
            "SELECT artifact_id FROM active_reassessment_artifacts WHERE run_id=? AND artifact_type=?",
            (run_id, artifact_type.value),
        ).fetchone()
        if current is not None:
            raise M2PersistenceError(f"M2 {artifact_type.value} is immutable and already exists")
        expected_parent = _PARENTS[artifact_type]
        if expected_parent is None:
            if parent_artifact_id is not None:
                raise M2PersistenceError("M2 run manifest cannot have a parent")
        else:
            parent = c.execute(
                "SELECT artifact_type, run_id FROM reassessment_artifacts WHERE artifact_id=?",
                (parent_artifact_id,),
            ).fetchone()
            if (
                parent is None
                or parent["run_id"] != run_id
                or parent["artifact_type"] != expected_parent.value
            ):
                raise M2PersistenceError(f"{artifact_type.value} requires its exact M2 parent")
        payload_json, digest = serialize_m2_artifact(artifact_type.value, payload)
        revision = c.execute(
            """SELECT COALESCE(MAX(artifact_revision), 0) + 1
               FROM reassessment_artifacts WHERE run_id=? AND artifact_type=?""",
            (run_id, artifact_type.value),
        ).fetchone()[0]
        artifact_id = self.id_factory("reassessment-artifact")
        now = self.clock().isoformat()
        c.execute(
            """INSERT INTO reassessment_artifacts(
                   artifact_id, run_id, artifact_type, artifact_revision,
                   artifact_schema_version, payload_json, payload_sha256,
                   parent_artifact_id, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                artifact_id,
                run_id,
                artifact_type.value,
                revision,
                "grw-m2-m1-v0.1",
                payload_json,
                digest,
                parent_artifact_id,
                now,
            ),
        )
        c.execute(
            "INSERT INTO active_reassessment_artifacts(run_id, artifact_type, artifact_id) VALUES (?, ?, ?)",
            (run_id, artifact_type.value, artifact_id),
        )
        c.execute(
            """UPDATE reassessment_runs SET stage=?, updated_at=?, row_version=row_version+1
               WHERE run_id=?""",
            (stage.value, now, run_id),
        )
        return M2ArtifactReference(
            artifact_id=artifact_id, artifact_revision=revision, payload_sha256=digest
        )

    def _begin_operation_in_tx(
        self, c: sqlite3.Connection, run_id: str, operation_kind: str, idempotency_key: str
    ) -> str:
        operation_id = self.id_factory("reassessment-operation")
        now = self.clock().isoformat()
        c.execute(
            """INSERT INTO reassessment_operations(
                   operation_id, run_id, operation_kind, idempotency_key, status,
                   produced_artifact_id, sanitised_error_code, started_at, completed_at
               ) VALUES (?, ?, ?, ?, 'PENDING', NULL, NULL, ?, NULL)""",
            (operation_id, run_id, operation_kind, idempotency_key, now),
        )
        return operation_id

    def _complete_operation_in_tx(
        self, c: sqlite3.Connection, operation_id: str, artifact_id: str | None
    ) -> None:
        row = c.execute(
            "SELECT status FROM reassessment_operations WHERE operation_id=?", (operation_id,)
        ).fetchone()
        if row is None:
            raise ArtifactNotFoundError("M2 operation does not exist")
        if row["status"] != "PENDING":
            raise M2PersistenceError("Only a pending M2 operation can complete")
        c.execute(
            """UPDATE reassessment_operations
               SET status='COMPLETED', produced_artifact_id=?, completed_at=?
               WHERE operation_id=?""",
            (artifact_id, self.clock().isoformat(), operation_id),
        )

    def _validate_parent_chain_in_tx(self, c: sqlite3.Connection, run_id: str) -> None:
        previous: M2ArtifactReference | None = None
        for artifact_type in M2ArtifactType:
            reference = self._active_ref_in_tx(c, run_id, artifact_type)
            if reference is None:
                continue
            expected = _PARENTS[artifact_type]
            if expected is None:
                previous = reference
                continue
            if previous is None or not self._parent_is(c, reference.artifact_id, previous.artifact_id):
                raise M2PersistenceError("M2 active artefact chain is incomplete or corrupted")
            previous = reference

    @staticmethod
    def _parent_is(c: sqlite3.Connection, child_id: str, parent_id: str) -> bool:
        row = c.execute(
            "SELECT parent_artifact_id FROM reassessment_artifacts WHERE artifact_id=?",
            (child_id,),
        ).fetchone()
        return row is not None and row["parent_artifact_id"] == parent_id

    @staticmethod
    def _require_run(c: sqlite3.Connection, run_id: str) -> sqlite3.Row:
        row = c.execute(
            "SELECT * FROM reassessment_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if row is None:
            raise ArtifactNotFoundError("Reassessment run does not exist")
        return row

    @classmethod
    def _require_stage(
        cls, c: sqlite3.Connection, run_id: str, stage: M2RunStage
    ) -> None:
        row = cls._require_run(c, run_id)
        if row["stage"] != stage.value:
            raise M2PersistenceError(f"M2 run must be at {stage.value}")

    @staticmethod
    def _active_ref_in_tx(
        c: sqlite3.Connection, run_id: str, artifact_type: M2ArtifactType
    ) -> M2ArtifactReference | None:
        row = c.execute(
            """SELECT a.* FROM active_reassessment_artifacts aa
               JOIN reassessment_artifacts a ON a.artifact_id=aa.artifact_id
               WHERE aa.run_id=? AND aa.artifact_type=?""",
            (run_id, artifact_type.value),
        ).fetchone()
        if row is None:
            return None
        return M2ArtifactReference(
            artifact_id=row["artifact_id"],
            artifact_revision=row["artifact_revision"],
            payload_sha256=row["payload_sha256"],
        )

    def _load_artifact_in_tx(
        self, c: sqlite3.Connection, reference: M2ArtifactReference | None
    ) -> Any:
        if reference is None:
            raise ArtifactNotFoundError("M2 artifact reference is missing")
        row = c.execute(
            "SELECT artifact_type, payload_json, payload_sha256 FROM reassessment_artifacts WHERE artifact_id=?",
            (reference.artifact_id,),
        ).fetchone()
        if row is None or row["payload_sha256"] != reference.payload_sha256:
            raise M2PersistenceError("M2 artifact reference is stale or corrupted")
        return deserialize_m2_artifact(
            row["artifact_type"], row["payload_json"], row["payload_sha256"]
        )

    @staticmethod
    def _normal_baseline_refs_in_tx(
        c: sqlite3.Connection, assessment_id: str
    ) -> dict[str, dict[str, Any]]:
        rows = c.execute(
            """SELECT a.artifact_type, a.artifact_id, a.artifact_revision, a.payload_sha256,
                      a.parent_artifact_id
               FROM active_artifacts aa
               JOIN assessment_artifacts a ON a.artifact_id=aa.artifact_id
               WHERE aa.assessment_id=?""",
            (assessment_id,),
        ).fetchall()
        values = {
            row["artifact_type"]: {
                "artifact_id": row["artifact_id"],
                "artifact_revision": row["artifact_revision"],
                "payload_sha256": row["payload_sha256"],
                "parent_artifact_id": row["parent_artifact_id"],
            }
            for row in rows
        }
        approved = values.get("APPROVED_REVIEW")
        integrated = values.get("INTEGRATED_ASSESSMENT_RESULT")
        package = values.get("DECISION_PACKAGE_RESULT")
        if not approved or not integrated or not package:
            return {}
        if (
            integrated["parent_artifact_id"] != approved["artifact_id"]
            or package["parent_artifact_id"] != integrated["artifact_id"]
        ):
            return {}
        for value in values.values():
            value.pop("parent_artifact_id", None)
        return values

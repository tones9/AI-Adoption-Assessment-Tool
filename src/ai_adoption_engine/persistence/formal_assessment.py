"""Explicit SQLite persistence for frozen formal-assessment run records.

This boundary applies isolated migration 8 and stores already constructed domain
records.  It performs no authorization, projection, assessment, result, guidance,
approval, or presentation orchestration.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from ai_adoption_engine.models.formal_assessment import (
    FORMAL_ASSESSMENT_RUN_STORE_ID,
    FORMAL_ASSESSMENT_RUN_STORE_VERSION,
    FormalAssessmentAuthorization,
    FormalAssessmentInputChoice,
    FormalAssessmentInputProjection,
    FormalAssessmentResult,
    FormalAssessmentResultSupersession,
    FormalAssessmentRunEvent,
    FormalAssessmentRunManifest,
    FormalAssessmentRunRequest,
    FormalAssessmentRunState,
    FormalAssessmentTerminalFailure,
    FormalEvidenceGuidance,
    FormalInputConflictResolution,
    FormalRunOperation,
    FormalRunStatus,
)
from ai_adoption_engine.models.formal_evidence import (
    FormalEvidenceLineage,
    RequestIdentity,
)
from ai_adoption_engine.persistence.base import (
    ArtifactCorruptionError,
    ArtifactNotFoundError,
    PersistenceError,
)
from ai_adoption_engine.persistence.formal_assessment_migration import (
    FORMAL_ASSESSMENT_MIGRATION,
)
from ai_adoption_engine.persistence.formal_assessment_serialization import (
    deserialize_formal_assessment_record,
    serialize_formal_assessment_record,
)
from ai_adoption_engine.persistence.formal_evidence import (
    SQLiteFormalEvidenceRepository,
)
from ai_adoption_engine.persistence.workspace_protection import (
    assert_workspace_write_target_allowed,
)


_FailureInjector = Callable[[str], None]


class FormalAssessmentPersistenceError(PersistenceError):
    """A formal-assessment persistence operation failed closed."""


class FormalAssessmentIdempotencyError(FormalAssessmentPersistenceError):
    """A request token was reused for a different immutable operation."""


class FormalAssessmentLineageError(FormalAssessmentPersistenceError):
    """A record does not match exact persisted formal lifecycle lineage."""


class FormalAssessmentIntegrityError(FormalAssessmentPersistenceError):
    """Immutable formal-assessment history is incomplete or inconsistent."""


class FormalAssessmentConcurrencyError(FormalAssessmentPersistenceError):
    """A concurrent append lost without changing persisted history."""


@dataclass(frozen=True)
class FormalAssessmentWriteResult:
    record: BaseModel
    replayed: bool


@dataclass(frozen=True)
class FormalAssessmentRunHistory:
    manifests: tuple[FormalAssessmentRunManifest, ...]
    events: tuple[FormalAssessmentRunEvent, ...]
    states: tuple[FormalAssessmentRunState, ...]
    terminal_records: tuple[
        FormalAssessmentResult | FormalAssessmentTerminalFailure, ...
    ]


def _sha_sequence(*values: str) -> str:
    encoded = json.dumps(
        values,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _target_key(resolution: FormalInputConflictResolution) -> str:
    return json.dumps(
        resolution.target.model_dump(mode="json"),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


class SQLiteFormalAssessmentRepository:
    """Explicit migration-8 repository for immutable formal-run history."""

    store_id = FORMAL_ASSESSMENT_RUN_STORE_ID
    store_version = FORMAL_ASSESSMENT_RUN_STORE_VERSION

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
        failure_injector: _FailureInjector | None = None,
        read_only: bool = False,
    ) -> None:
        self.path = Path(path)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.failure_injector = failure_injector
        self.read_only = read_only
        if str(self.path) == ":memory:" or not self.path.is_file():
            raise FormalAssessmentPersistenceError(
                "Formal-assessment persistence requires an existing assessment database"
            )
        if read_only:
            self._require_supported_history(require_migration_eight=True)
            return
        assert_workspace_write_target_allowed(self.path)
        self._require_supported_history(require_migration_eight=False)
        # Explicit construction is the only path that advances compatible stores
        # through the already-approved isolated migrations 1-7.
        SQLiteFormalEvidenceRepository(self.path, clock=self.clock)
        self._require_supported_history(require_migration_eight=False)
        self._migrate()
        self.path.chmod(0o600)

    def _inject(self, stage: str) -> None:
        if self.failure_injector is not None:
            self.failure_injector(stage)

    def _connect(self, *, write: bool = False) -> sqlite3.Connection:
        if self.read_only or not write:
            connection = sqlite3.connect(
                f"file:{self.path.resolve()}?mode=ro&immutable=1",
                uri=True,
                timeout=30,
            )
        else:
            assert_workspace_write_target_allowed(self.path)
            connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        if self.read_only:
            connection.execute("PRAGMA query_only = ON")
        return connection

    def _migration_versions_read_only(self) -> tuple[int, ...]:
        connection = self._connect()
        try:
            exists = connection.execute(
                """SELECT 1 FROM sqlite_master
                   WHERE type = 'table'
                     AND name = 'preliminary_journey_schema_migrations'"""
            ).fetchone()
            if exists is None:
                return ()
            return tuple(
                row[0]
                for row in connection.execute(
                    """SELECT version FROM preliminary_journey_schema_migrations
                       ORDER BY version"""
                )
            )
        finally:
            connection.close()

    def _require_supported_history(self, *, require_migration_eight: bool) -> None:
        versions = self._migration_versions_read_only()
        if versions != tuple(range(1, len(versions) + 1)) or any(
            item > 8 for item in versions
        ):
            raise FormalAssessmentPersistenceError(
                "Formal-assessment repository rejected an unsupported migration history"
            )
        if require_migration_eight and versions != tuple(range(1, 9)):
            raise FormalAssessmentPersistenceError(
                "Read-only formal-assessment inspection requires migration 8"
            )

    def _migrate(self) -> None:
        version, script = FORMAL_ASSESSMENT_MIGRATION
        connection = self._connect(write=True)
        try:
            applied = {
                row[0]
                for row in connection.execute(
                    "SELECT version FROM preliminary_journey_schema_migrations"
                )
            }
            if version in applied:
                return
            if applied != set(range(1, 8)):
                raise FormalAssessmentPersistenceError(
                    "Migration 8 requires exact compatible migrations 1-7"
                )
            connection.executescript("BEGIN IMMEDIATE;\n" + script)
            self._inject("MIGRATION_8_BEFORE_HISTORY")
            connection.execute(
                """INSERT INTO preliminary_journey_schema_migrations(
                       version, store_id, store_version, applied_at
                   ) VALUES (?, ?, ?, ?)""",
                (
                    version,
                    "preliminary-journey-store.v0.1",
                    "0.1.0",
                    self.clock().isoformat(),
                ),
            )
            connection.commit()
        except FormalAssessmentPersistenceError:
            connection.rollback()
            raise
        except Exception as exc:
            connection.rollback()
            raise FormalAssessmentPersistenceError(
                "Formal-assessment migration 8 failed safely"
            ) from exc
        finally:
            connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        if self.read_only:
            raise FormalAssessmentPersistenceError(
                "Read-only formal-assessment repository cannot mutate history"
            )
        connection = self._connect(write=True)
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def migration_versions(self) -> tuple[int, ...]:
        return self._migration_versions_read_only()

    def assert_writable(self) -> None:
        """Fail before a caller performs projection or engine work for a write."""

        if self.read_only:
            raise FormalAssessmentPersistenceError(
                "Read-only formal-assessment repository cannot execute a run"
            )
        assert_workspace_write_target_allowed(self.path)

    @staticmethod
    def _lineage_tuple(lineage: FormalEvidenceLineage) -> tuple[object, ...]:
        return (
            lineage.formal_lifecycle_id,
            lineage.formal_lifecycle_schema,
            lineage.journey_id,
            lineage.source_assessment_id,
            lineage.approved_review_artifact_id,
            lineage.approved_review_schema_version,
            lineage.approved_review_revision,
            lineage.approved_review_payload_sha256,
            lineage.source_document_id,
            lineage.source_document_sha256,
            lineage.validated_process_id,
            lineage.validated_process_fingerprint,
        )

    def _ensure_lineage(
        self,
        connection: sqlite3.Connection,
        lineage: FormalEvidenceLineage,
    ) -> None:
        row = connection.execute(
            """SELECT formal_lifecycle_id, formal_lifecycle_schema, journey_id,
                      source_assessment_id, approved_review_artifact_id,
                      approved_review_schema_version, approved_review_revision,
                      approved_review_payload_sha256, source_document_id,
                      source_document_sha256, validated_process_id,
                      validated_process_fingerprint
               FROM preliminary_formal_assessment_lineages
               WHERE formal_lifecycle_id = ?""",
            (lineage.formal_lifecycle_id,),
        ).fetchone()
        expected = self._lineage_tuple(lineage)
        if row is not None:
            if tuple(row) != expected:
                raise FormalAssessmentLineageError(
                    "Formal lifecycle already has different assessment lineage"
                )
            return
        try:
            connection.execute(
                """INSERT INTO preliminary_formal_assessment_lineages
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                expected,
            )
        except sqlite3.IntegrityError as exc:
            raise FormalAssessmentLineageError(
                "Formal-assessment lineage does not match persisted lifecycle"
            ) from exc

    @staticmethod
    def _operation_row(
        connection: sqlite3.Connection, request_token: str
    ) -> sqlite3.Row | None:
        return connection.execute(
            """SELECT * FROM preliminary_formal_assessment_operation_requests
               WHERE request_token = ?""",
            (request_token,),
        ).fetchone()

    def _check_replay(
        self,
        connection: sqlite3.Connection,
        *,
        request: RequestIdentity,
        operation_type: str,
        operation_payload_sha256: str,
        result_schema_version: str,
        result_identity: str,
    ) -> bool:
        row = self._operation_row(connection, request.request_token)
        if row is None:
            return False
        expected = (
            request.canonical_request_sha256,
            operation_type,
            operation_payload_sha256,
            result_schema_version,
            result_identity,
        )
        actual = tuple(
            row[name]
            for name in (
                "canonical_request_sha256",
                "operation_type",
                "operation_payload_sha256",
                "result_schema_version",
                "result_identity",
            )
        )
        if actual != expected:
            raise FormalAssessmentIdempotencyError(
                "Request token was reused for a different formal-assessment operation"
            )
        return True

    def _record_operation(
        self,
        connection: sqlite3.Connection,
        *,
        request: RequestIdentity,
        operation_type: str,
        operation_payload_sha256: str,
        result_schema_version: str,
        result_identity: str,
    ) -> None:
        connection.execute(
            """INSERT INTO preliminary_formal_assessment_operation_requests(
                   request_token, canonical_request_sha256, operation_type,
                   operation_payload_sha256, result_schema_version,
                   result_identity, recorded_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                request.request_token,
                request.canonical_request_sha256,
                operation_type,
                operation_payload_sha256,
                result_schema_version,
                result_identity,
                self.clock().isoformat(),
            ),
        )

    @staticmethod
    def _insert_exact(
        connection: sqlite3.Connection,
        *,
        table: str,
        where_sql: str,
        where_values: tuple[object, ...],
        insert_sql: str,
        insert_values: tuple[object, ...],
        payload_json: str,
        payload_sha256: str,
    ) -> None:
        existing = connection.execute(
            f"SELECT payload_json, payload_sha256 FROM {table} WHERE {where_sql}",
            where_values,
        ).fetchone()
        if existing is not None:
            if tuple(existing) != (payload_json, payload_sha256):
                raise FormalAssessmentIntegrityError(
                    "Immutable formal-assessment identity has different payload bytes"
                )
            return
        connection.execute(insert_sql, insert_values)

    @staticmethod
    def _deserialize_row(row: sqlite3.Row) -> BaseModel:
        return deserialize_formal_assessment_record(
            row["schema_version"], row["payload_json"], row["payload_sha256"]
        )

    def _insert_input_choice(
        self,
        connection: sqlite3.Connection,
        choice: FormalAssessmentInputChoice,
    ) -> tuple[str, str, str]:
        payload_json, payload_sha = serialize_formal_assessment_record(choice)
        identity = choice.request.request_token
        candidate = choice.supporting_candidate
        self._insert_exact(
            connection,
            table="preliminary_formal_assessment_input_choices",
            where_sql="input_choice_id = ?",
            where_values=(identity,),
            insert_sql="""INSERT INTO preliminary_formal_assessment_input_choices(
                input_choice_id, formal_lifecycle_id, schema_version, store_contract,
                mode, disposition, candidate_set_id, candidate_set_payload_sha256,
                readiness_id, readiness_payload_sha256, request_token,
                payload_json, payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            insert_values=(
                identity,
                choice.lineage.formal_lifecycle_id,
                choice.schema_version,
                choice.store_contract,
                choice.mode.value,
                choice.supporting_evidence_disposition.value,
                None if candidate is None else candidate.candidate_set_id,
                None if candidate is None else candidate.candidate_set_payload_sha256,
                None if candidate is None else candidate.readiness_id,
                None if candidate is None else candidate.readiness_payload_sha256,
                choice.request.request_token,
                payload_json,
                payload_sha,
            ),
            payload_json=payload_json,
            payload_sha256=payload_sha,
        )
        return identity, payload_json, payload_sha

    def _insert_authorization_bundle(
        self,
        connection: sqlite3.Connection,
        authorization: FormalAssessmentAuthorization,
    ) -> tuple[str, str]:
        lineage = authorization.approved_process.lineage
        self._ensure_lineage(connection, lineage)
        choice_id, _, _ = self._insert_input_choice(
            connection, authorization.input_choice
        )
        payload_json, payload_sha = serialize_formal_assessment_record(authorization)
        compatibility = authorization.compatibility
        rl = authorization.run_lineage
        self._insert_exact(
            connection,
            table="preliminary_formal_assessment_authorizations",
            where_sql="authorization_id = ?",
            where_values=(authorization.authorization_id,),
            insert_sql="""INSERT INTO preliminary_formal_assessment_authorizations(
                authorization_id, formal_lifecycle_id, input_choice_id,
                projection_id, run_id, input_mode, schema_version, store_contract,
                adapter_id, adapter_version, adapter_rules_id,
                adapter_rules_fingerprint, policy_id, policy_version,
                policy_fingerprint, engine_id, engine_version, framework_id,
                framework_version, output_contract, guidance_catalogue_id,
                guidance_catalogue_fingerprint, request_token,
                payload_json, payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            insert_values=(
                authorization.authorization_id,
                lineage.formal_lifecycle_id,
                choice_id,
                rl.projection_id,
                rl.run_id,
                authorization.input_choice.mode.value,
                authorization.schema_version,
                authorization.store_contract,
                compatibility.adapter_id,
                compatibility.adapter_version,
                compatibility.adapter_rules_id,
                compatibility.adapter_rules_fingerprint,
                compatibility.policy_id,
                compatibility.policy_version,
                compatibility.policy_fingerprint,
                compatibility.engine_id,
                compatibility.engine_version,
                compatibility.framework_id,
                compatibility.framework_version,
                compatibility.output_contract,
                compatibility.guidance_catalogue_id,
                compatibility.guidance_catalogue_fingerprint,
                authorization.request.request_token,
                payload_json,
                payload_sha,
            ),
            payload_json=payload_json,
            payload_sha256=payload_sha,
        )
        for resolution in authorization.conflict_resolutions:
            self._insert_resolution(connection, resolution)
        return payload_json, payload_sha

    def _insert_resolution(
        self,
        connection: sqlite3.Connection,
        resolution: FormalInputConflictResolution,
    ) -> tuple[str, str]:
        payload_json, payload_sha = serialize_formal_assessment_record(resolution)
        rl = resolution.run_lineage
        self._insert_exact(
            connection,
            table="preliminary_formal_input_conflict_resolutions",
            where_sql="resolution_id = ?",
            where_values=(resolution.resolution_id,),
            insert_sql="""INSERT INTO preliminary_formal_input_conflict_resolutions(
                resolution_id, formal_lifecycle_id, authorization_id,
                projection_id, run_id, activity_id, target_key,
                schema_version, store_contract, request_token,
                payload_json, payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            insert_values=(
                resolution.resolution_id,
                resolution.lineage.formal_lifecycle_id,
                rl.authorization_id,
                rl.projection_id,
                rl.run_id,
                resolution.activity_id,
                _target_key(resolution),
                resolution.schema_version,
                resolution.store_contract,
                resolution.request.request_token,
                payload_json,
                payload_sha,
            ),
            payload_json=payload_json,
            payload_sha256=payload_sha,
        )
        return payload_json, payload_sha

    def _insert_projection(
        self,
        connection: sqlite3.Connection,
        projection: FormalAssessmentInputProjection,
    ) -> tuple[str, str]:
        self._insert_authorization_bundle(connection, projection.authorization)
        payload_json, payload_sha = serialize_formal_assessment_record(projection)
        rl = projection.run_lineage
        self._insert_exact(
            connection,
            table="preliminary_formal_assessment_projections",
            where_sql="projection_id = ?",
            where_values=(projection.projection_id,),
            insert_sql="""INSERT INTO preliminary_formal_assessment_projections(
                projection_id, formal_lifecycle_id, authorization_id, run_id,
                projection_fingerprint, schema_version, store_contract,
                payload_json, payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            insert_values=(
                projection.projection_id,
                rl.formal_lifecycle_id,
                rl.authorization_id,
                rl.run_id,
                projection.projection_fingerprint,
                projection.schema_version,
                projection.store_contract,
                payload_json,
                payload_sha,
            ),
            payload_json=payload_json,
            payload_sha256=payload_sha,
        )
        return payload_json, payload_sha

    def _insert_run_request(
        self,
        connection: sqlite3.Connection,
        request: FormalAssessmentRunRequest,
    ) -> tuple[str, str]:
        payload_json, payload_sha = serialize_formal_assessment_record(request)
        self._insert_exact(
            connection,
            table="preliminary_formal_assessment_run_requests",
            where_sql="request_token = ?",
            where_values=(request.request.request_token,),
            insert_sql="""INSERT INTO preliminary_formal_assessment_run_requests(
                request_token, formal_lifecycle_id, run_id, operation,
                canonical_request_sha256, canonical_operation_payload_sha256,
                schema_version, store_contract, payload_json, payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            insert_values=(
                request.request.request_token,
                request.run_lineage.formal_lifecycle_id,
                request.run_lineage.run_id,
                request.operation.value,
                request.request.canonical_request_sha256,
                request.canonical_operation_payload_sha256,
                request.schema_version,
                request.store_contract,
                payload_json,
                payload_sha,
            ),
            payload_json=payload_json,
            payload_sha256=payload_sha,
        )
        return payload_json, payload_sha

    def _insert_manifest(
        self,
        connection: sqlite3.Connection,
        manifest: FormalAssessmentRunManifest,
    ) -> tuple[str, str]:
        self._insert_projection(connection, manifest.projection)
        self._insert_run_request(connection, manifest.request)
        payload_json, payload_sha = serialize_formal_assessment_record(manifest)
        rl = manifest.run_lineage
        self._insert_exact(
            connection,
            table="preliminary_formal_assessment_run_manifests",
            where_sql="run_id = ? AND attempt_number = ?",
            where_values=(rl.run_id, manifest.attempt_number),
            insert_sql="""INSERT INTO preliminary_formal_assessment_run_manifests(
                run_id, attempt_number, formal_lifecycle_id, authorization_id,
                projection_id, projection_fingerprint, input_mode,
                predecessor_attempt_number, request_token, schema_version,
                store_contract, payload_json, payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            insert_values=(
                rl.run_id,
                manifest.attempt_number,
                rl.formal_lifecycle_id,
                rl.authorization_id,
                rl.projection_id,
                manifest.projection.projection_fingerprint,
                manifest.authorization.input_choice.mode.value,
                None
                if manifest.recovery is None
                else manifest.recovery.predecessor_attempt_number,
                manifest.request.request.request_token,
                manifest.schema_version,
                manifest.store_contract,
                payload_json,
                payload_sha,
            ),
            payload_json=payload_json,
            payload_sha256=payload_sha,
        )
        initial_state = FormalAssessmentRunState(
            schema_version="formal-assessment-run-state.v0.1",
            store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
            manifest=manifest,
            events=(),
            current_status=FormalRunStatus.AUTHORIZED,
            projected_at=manifest.created_at,
        )
        self._insert_state(connection, initial_state)
        return payload_json, payload_sha

    def _insert_state(
        self,
        connection: sqlite3.Connection,
        state: FormalAssessmentRunState,
    ) -> tuple[str, str]:
        payload_json, payload_sha = serialize_formal_assessment_record(state)
        manifest = state.manifest
        self._insert_exact(
            connection,
            table="preliminary_formal_assessment_run_states",
            where_sql="run_id = ? AND attempt_number = ? AND event_count = ?",
            where_values=(
                manifest.run_lineage.run_id,
                manifest.attempt_number,
                len(state.events),
            ),
            insert_sql="""INSERT INTO preliminary_formal_assessment_run_states(
                run_id, attempt_number, event_count, current_status,
                schema_version, store_contract, payload_json, payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            insert_values=(
                manifest.run_lineage.run_id,
                manifest.attempt_number,
                len(state.events),
                state.current_status.value,
                state.schema_version,
                state.store_contract,
                payload_json,
                payload_sha,
            ),
            payload_json=payload_json,
            payload_sha256=payload_sha,
        )
        return payload_json, payload_sha

    def append_input_choice(
        self, choice: FormalAssessmentInputChoice
    ) -> FormalAssessmentWriteResult:
        payload_json, payload_sha = serialize_formal_assessment_record(choice)
        del payload_json
        identity = choice.request.request_token
        try:
            with self._transaction() as connection:
                if self._check_replay(
                    connection,
                    request=choice.request,
                    operation_type="APPEND_INPUT_CHOICE",
                    operation_payload_sha256=payload_sha,
                    result_schema_version=choice.schema_version,
                    result_identity=identity,
                ):
                    return FormalAssessmentWriteResult(
                        self._load_input_choice(connection, identity), True
                    )
                self._ensure_lineage(connection, choice.lineage)
                self._insert_input_choice(connection, choice)
                self._inject("APPEND_INPUT_CHOICE")
                self._record_operation(
                    connection,
                    request=choice.request,
                    operation_type="APPEND_INPUT_CHOICE",
                    operation_payload_sha256=payload_sha,
                    result_schema_version=choice.schema_version,
                    result_identity=identity,
                )
                return FormalAssessmentWriteResult(choice, False)
        except FormalAssessmentPersistenceError:
            raise
        except sqlite3.IntegrityError as exc:
            raise FormalAssessmentIntegrityError(
                "Input-choice append violated immutable persistence integrity"
            ) from exc

    def append_conflict_resolution(
        self, resolution: FormalInputConflictResolution
    ) -> FormalAssessmentWriteResult:
        _, payload_sha = serialize_formal_assessment_record(resolution)
        try:
            with self._transaction() as connection:
                if self._check_replay(
                    connection,
                    request=resolution.request,
                    operation_type="APPEND_CONFLICT_RESOLUTION",
                    operation_payload_sha256=payload_sha,
                    result_schema_version=resolution.schema_version,
                    result_identity=resolution.resolution_id,
                ):
                    return FormalAssessmentWriteResult(
                        self._load_resolution(connection, resolution.resolution_id),
                        True,
                    )
                self._insert_resolution(connection, resolution)
                self._inject("APPEND_CONFLICT_RESOLUTION")
                self._record_operation(
                    connection,
                    request=resolution.request,
                    operation_type="APPEND_CONFLICT_RESOLUTION",
                    operation_payload_sha256=payload_sha,
                    result_schema_version=resolution.schema_version,
                    result_identity=resolution.resolution_id,
                )
                return FormalAssessmentWriteResult(resolution, False)
        except FormalAssessmentPersistenceError:
            raise
        except sqlite3.IntegrityError as exc:
            raise FormalAssessmentIntegrityError(
                "Conflict-resolution append violated immutable integrity"
            ) from exc

    def append_authorization(
        self, authorization: FormalAssessmentAuthorization
    ) -> FormalAssessmentWriteResult:
        _, payload_sha = serialize_formal_assessment_record(authorization)
        try:
            with self._transaction() as connection:
                if self._check_replay(
                    connection,
                    request=authorization.request,
                    operation_type="APPEND_AUTHORIZATION",
                    operation_payload_sha256=payload_sha,
                    result_schema_version=authorization.schema_version,
                    result_identity=authorization.authorization_id,
                ):
                    return FormalAssessmentWriteResult(
                        self._load_authorization(
                            connection, authorization.authorization_id
                        ),
                        True,
                    )
                self._insert_authorization_bundle(connection, authorization)
                self._inject("APPEND_AUTHORIZATION")
                self._record_operation(
                    connection,
                    request=authorization.request,
                    operation_type="APPEND_AUTHORIZATION",
                    operation_payload_sha256=payload_sha,
                    result_schema_version=authorization.schema_version,
                    result_identity=authorization.authorization_id,
                )
                return FormalAssessmentWriteResult(authorization, False)
        except FormalAssessmentPersistenceError:
            raise
        except sqlite3.IntegrityError as exc:
            raise FormalAssessmentIntegrityError(
                "Authorization append violated immutable persistence integrity"
            ) from exc

    def append_projection(
        self,
        projection: FormalAssessmentInputProjection,
        *,
        request: RequestIdentity,
    ) -> FormalAssessmentWriteResult:
        _, payload_sha = serialize_formal_assessment_record(projection)
        try:
            with self._transaction() as connection:
                if self._check_replay(
                    connection,
                    request=request,
                    operation_type="APPEND_PROJECTION",
                    operation_payload_sha256=payload_sha,
                    result_schema_version=projection.schema_version,
                    result_identity=projection.projection_id,
                ):
                    return FormalAssessmentWriteResult(
                        self._load_projection(connection, projection.projection_id),
                        True,
                    )
                self._insert_projection(connection, projection)
                self._inject("APPEND_PROJECTION")
                self._record_operation(
                    connection,
                    request=request,
                    operation_type="APPEND_PROJECTION",
                    operation_payload_sha256=payload_sha,
                    result_schema_version=projection.schema_version,
                    result_identity=projection.projection_id,
                )
                return FormalAssessmentWriteResult(projection, False)
        except FormalAssessmentPersistenceError:
            raise
        except sqlite3.IntegrityError as exc:
            raise FormalAssessmentIntegrityError(
                "Projection append violated immutable persistence integrity"
            ) from exc

    def append_run_request(
        self, request: FormalAssessmentRunRequest
    ) -> FormalAssessmentWriteResult:
        _, payload_sha = serialize_formal_assessment_record(request)
        identity = request.request.request_token
        try:
            with self._transaction() as connection:
                if self._check_replay(
                    connection,
                    request=request.request,
                    operation_type="APPEND_RUN_REQUEST",
                    operation_payload_sha256=payload_sha,
                    result_schema_version=request.schema_version,
                    result_identity=identity,
                ):
                    return FormalAssessmentWriteResult(
                        self._load_run_request(connection, identity), True
                    )
                self._insert_run_request(connection, request)
                self._inject("APPEND_RUN_REQUEST")
                self._record_operation(
                    connection,
                    request=request.request,
                    operation_type="APPEND_RUN_REQUEST",
                    operation_payload_sha256=payload_sha,
                    result_schema_version=request.schema_version,
                    result_identity=identity,
                )
                return FormalAssessmentWriteResult(request, False)
        except FormalAssessmentPersistenceError:
            raise
        except sqlite3.IntegrityError as exc:
            raise FormalAssessmentIntegrityError(
                "Run-request append violated immutable persistence integrity"
            ) from exc

    def create_manifest(
        self, manifest: FormalAssessmentRunManifest
    ) -> FormalAssessmentWriteResult:
        _, payload_sha = serialize_formal_assessment_record(manifest)
        identity = f"{manifest.run_lineage.run_id}:{manifest.attempt_number}"
        request = manifest.request.request
        try:
            with self._transaction() as connection:
                if self._check_replay(
                    connection,
                    request=request,
                    operation_type="CREATE_MANIFEST",
                    operation_payload_sha256=payload_sha,
                    result_schema_version=manifest.schema_version,
                    result_identity=identity,
                ):
                    return FormalAssessmentWriteResult(
                        self._load_manifest(
                            connection,
                            manifest.run_lineage.run_id,
                            manifest.attempt_number,
                        ),
                        True,
                    )
                self._insert_manifest(connection, manifest)
                self._inject("CREATE_MANIFEST")
                self._record_operation(
                    connection,
                    request=request,
                    operation_type="CREATE_MANIFEST",
                    operation_payload_sha256=payload_sha,
                    result_schema_version=manifest.schema_version,
                    result_identity=identity,
                )
                return FormalAssessmentWriteResult(manifest, False)
        except FormalAssessmentPersistenceError:
            raise
        except sqlite3.IntegrityError as exc:
            raise FormalAssessmentIntegrityError(
                "Manifest creation violated immutable persistence integrity"
            ) from exc

    def create_manifest_and_start(
        self,
        manifest: FormalAssessmentRunManifest,
        start_event: FormalAssessmentRunEvent,
        running_state: FormalAssessmentRunState,
    ) -> FormalAssessmentWriteResult:
        """Atomically record one manifest and its initial running transition.

        This is intentionally a narrow mechanical boundary for the explicit run
        service.  A failed start must not leave an authorized manifest that could
        be mistaken for an engine invocation boundary.
        """

        _, manifest_sha = serialize_formal_assessment_record(manifest)
        _, event_sha = serialize_formal_assessment_record(start_event)
        _, state_sha = serialize_formal_assessment_record(running_state)
        start_operation_sha = _sha_sequence(event_sha, state_sha, "")
        manifest_identity = f"{manifest.run_lineage.run_id}:{manifest.attempt_number}"
        try:
            with self._transaction() as connection:
                manifest_replayed = self._check_replay(
                    connection,
                    request=manifest.request.request,
                    operation_type="CREATE_MANIFEST",
                    operation_payload_sha256=manifest_sha,
                    result_schema_version=manifest.schema_version,
                    result_identity=manifest_identity,
                )
                start_replayed = self._check_replay(
                    connection,
                    request=start_event.request.request,
                    operation_type="APPEND_RUN_EVENT",
                    operation_payload_sha256=start_operation_sha,
                    result_schema_version=start_event.schema_version,
                    result_identity=start_event.event_id,
                )
                if manifest_replayed or start_replayed:
                    if not (manifest_replayed and start_replayed):
                        raise FormalAssessmentIntegrityError(
                            "Manifest and start replay history is incomplete"
                        )
                    return FormalAssessmentWriteResult(
                        self._load_event(connection, start_event.event_id), True
                    )
                self._insert_manifest(connection, manifest)
                self._validate_state_extension(
                    connection,
                    start_event,
                    running_state,
                    manifest.attempt_number,
                )
                self._insert_event(connection, start_event, manifest.attempt_number)
                self._insert_state(connection, running_state)
                self._inject("CREATE_MANIFEST_AND_START")
                self._record_operation(
                    connection,
                    request=manifest.request.request,
                    operation_type="CREATE_MANIFEST",
                    operation_payload_sha256=manifest_sha,
                    result_schema_version=manifest.schema_version,
                    result_identity=manifest_identity,
                )
                self._record_operation(
                    connection,
                    request=start_event.request.request,
                    operation_type="APPEND_RUN_EVENT",
                    operation_payload_sha256=start_operation_sha,
                    result_schema_version=start_event.schema_version,
                    result_identity=start_event.event_id,
                )
                return FormalAssessmentWriteResult(start_event, False)
        except FormalAssessmentPersistenceError:
            raise
        except sqlite3.IntegrityError as exc:
            raise FormalAssessmentIntegrityError(
                "Manifest/start creation violated immutable persistence integrity"
            ) from exc

    def _validate_state_extension(
        self,
        connection: sqlite3.Connection,
        event: FormalAssessmentRunEvent,
        state: FormalAssessmentRunState,
        attempt_number: int,
    ) -> None:
        manifest = self._load_manifest(
            connection, event.run_lineage.run_id, attempt_number
        )
        if state.manifest != manifest or state.events[-1:] != (event,):
            raise FormalAssessmentIntegrityError(
                "Derived state must extend the exact manifest with the appended event"
            )
        existing = self._load_events(
            connection, event.run_lineage.run_id, attempt_number
        )
        if state.events[:-1] != existing:
            raise FormalAssessmentIntegrityError(
                "Derived state must contain the complete immutable event history"
            )

    def _insert_event(
        self,
        connection: sqlite3.Connection,
        event: FormalAssessmentRunEvent,
        attempt_number: int,
    ) -> tuple[str, str]:
        self._insert_run_request(connection, event.request)
        payload_json, payload_sha = serialize_formal_assessment_record(event)
        rl = event.run_lineage
        self._insert_exact(
            connection,
            table="preliminary_formal_assessment_run_events",
            where_sql="event_id = ?",
            where_values=(event.event_id,),
            insert_sql="""INSERT INTO preliminary_formal_assessment_run_events(
                event_id, run_id, attempt_number, sequence, operation,
                from_status, to_status, authorization_id, projection_id,
                projection_fingerprint, request_token, schema_version,
                store_contract, payload_json, payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            insert_values=(
                event.event_id,
                rl.run_id,
                attempt_number,
                event.sequence,
                event.operation.value,
                event.from_status.value,
                event.to_status.value,
                event.authorization_id,
                event.projection_id,
                event.projection_fingerprint,
                event.request.request.request_token,
                event.schema_version,
                event.store_contract,
                payload_json,
                payload_sha,
            ),
            payload_json=payload_json,
            payload_sha256=payload_sha,
        )
        return payload_json, payload_sha

    def _insert_terminal(
        self,
        connection: sqlite3.Connection,
        record: FormalAssessmentResult | FormalAssessmentTerminalFailure,
    ) -> tuple[str, str, str]:
        payload_json, payload_sha = serialize_formal_assessment_record(record)
        manifest = record.manifest
        if isinstance(record, FormalAssessmentResult):
            identity = record.result_id
            result_id: str | None = record.result_id
            kind = "SUCCESS"
        else:
            identity = record.terminal_record_id
            result_id = None
            kind = "FAILURE"
        self._insert_exact(
            connection,
            table="preliminary_formal_assessment_terminal_records",
            where_sql="terminal_record_id = ?",
            where_values=(identity,),
            insert_sql="""INSERT INTO preliminary_formal_assessment_terminal_records(
                terminal_record_id, result_id, run_id, attempt_number,
                formal_lifecycle_id, record_kind, status, schema_version,
                store_contract, payload_json, payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            insert_values=(
                identity,
                result_id,
                manifest.run_lineage.run_id,
                manifest.attempt_number,
                manifest.run_lineage.formal_lifecycle_id,
                kind,
                record.status.value,
                record.schema_version,
                record.store_contract,
                payload_json,
                payload_sha,
            ),
            payload_json=payload_json,
            payload_sha256=payload_sha,
        )
        return identity, payload_json, payload_sha

    def append_event(
        self,
        event: FormalAssessmentRunEvent,
        state: FormalAssessmentRunState,
        *,
        attempt_number: int,
        terminal_record: FormalAssessmentResult
        | FormalAssessmentTerminalFailure
        | None = None,
    ) -> FormalAssessmentWriteResult:
        event_json, event_sha = serialize_formal_assessment_record(event)
        del event_json
        _, state_sha = serialize_formal_assessment_record(state)
        terminal_sha = ""
        if terminal_record is not None:
            _, terminal_sha = serialize_formal_assessment_record(terminal_record)
        operation_sha = _sha_sequence(event_sha, state_sha, terminal_sha)
        request = event.request.request
        try:
            with self._transaction() as connection:
                if self._check_replay(
                    connection,
                    request=request,
                    operation_type="APPEND_RUN_EVENT",
                    operation_payload_sha256=operation_sha,
                    result_schema_version=event.schema_version,
                    result_identity=event.event_id,
                ):
                    return FormalAssessmentWriteResult(
                        self._load_event(connection, event.event_id), True
                    )
                self._validate_state_extension(
                    connection, event, state, attempt_number
                )
                existing_terminal = connection.execute(
                    """SELECT 1 FROM preliminary_formal_assessment_terminal_records
                       WHERE run_id = ? AND attempt_number = ?""",
                    (event.run_lineage.run_id, attempt_number),
                ).fetchone()
                terminal_required = event.operation in {
                    FormalRunOperation.COMPLETE,
                    FormalRunOperation.FAIL,
                } or (
                    event.operation is FormalRunOperation.ABANDON
                    and existing_terminal is None
                )
                if terminal_required != (terminal_record is not None):
                    raise FormalAssessmentIntegrityError(
                        "This transition requires exactly the permitted immutable terminal record"
                    )
                if terminal_record is not None:
                    if terminal_record.manifest != state.manifest:
                        raise FormalAssessmentIntegrityError(
                            "Terminal record must pin the exact state manifest"
                        )
                    if terminal_record.status is not state.current_status:
                        raise FormalAssessmentIntegrityError(
                            "Terminal record status must equal the derived state"
                        )
                    if (
                        event.operation is FormalRunOperation.COMPLETE
                    ) != isinstance(terminal_record, FormalAssessmentResult):
                        raise FormalAssessmentIntegrityError(
                            "Completion requires a result and failure terminals require failure"
                        )
                self._insert_event(connection, event, attempt_number)
                self._insert_state(connection, state)
                if terminal_record is not None:
                    self._insert_terminal(connection, terminal_record)
                self._inject("APPEND_RUN_EVENT")
                self._record_operation(
                    connection,
                    request=request,
                    operation_type="APPEND_RUN_EVENT",
                    operation_payload_sha256=operation_sha,
                    result_schema_version=event.schema_version,
                    result_identity=event.event_id,
                )
                return FormalAssessmentWriteResult(event, False)
        except FormalAssessmentPersistenceError:
            raise
        except sqlite3.IntegrityError as exc:
            message = str(exc).lower()
            error_type = (
                FormalAssessmentConcurrencyError
                if "sequence" in message or "unique" in message
                else FormalAssessmentIntegrityError
            )
            raise error_type(
                "Run event append lost or violated immutable persistence integrity"
            ) from exc

    def append_terminal_record(
        self,
        event: FormalAssessmentRunEvent,
        state: FormalAssessmentRunState,
        record: FormalAssessmentResult | FormalAssessmentTerminalFailure,
        *,
        attempt_number: int,
    ) -> FormalAssessmentWriteResult:
        return self.append_event(
            event,
            state,
            attempt_number=attempt_number,
            terminal_record=record,
        )

    def append_result_supersession(
        self, supersession: FormalAssessmentResultSupersession
    ) -> FormalAssessmentWriteResult:
        payload_json, payload_sha = serialize_formal_assessment_record(supersession)
        del payload_json
        try:
            with self._transaction() as connection:
                if self._check_replay(
                    connection,
                    request=supersession.request,
                    operation_type="APPEND_RESULT_SUPERSESSION",
                    operation_payload_sha256=payload_sha,
                    result_schema_version=supersession.schema_version,
                    result_identity=supersession.supersession_id,
                ):
                    return FormalAssessmentWriteResult(
                        self._load_supersession(
                            connection, supersession.supersession_id
                        ),
                        True,
                    )
                encoded, digest = serialize_formal_assessment_record(supersession)
                self._insert_exact(
                    connection,
                    table="preliminary_formal_assessment_result_supersessions",
                    where_sql="supersession_id = ?",
                    where_values=(supersession.supersession_id,),
                    insert_sql="""INSERT INTO preliminary_formal_assessment_result_supersessions(
                        supersession_id, formal_lifecycle_id,
                        superseded_result_id, successor_result_id,
                        superseded_run_id, successor_run_id, request_token,
                        schema_version, store_contract, payload_json, payload_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    insert_values=(
                        supersession.supersession_id,
                        supersession.formal_lifecycle_id,
                        supersession.superseded_result_id,
                        supersession.successor_result_id,
                        supersession.superseded_run_id,
                        supersession.successor_run_id,
                        supersession.request.request_token,
                        supersession.schema_version,
                        supersession.store_contract,
                        encoded,
                        digest,
                    ),
                    payload_json=encoded,
                    payload_sha256=digest,
                )
                self._inject("APPEND_RESULT_SUPERSESSION")
                self._record_operation(
                    connection,
                    request=supersession.request,
                    operation_type="APPEND_RESULT_SUPERSESSION",
                    operation_payload_sha256=payload_sha,
                    result_schema_version=supersession.schema_version,
                    result_identity=supersession.supersession_id,
                )
                return FormalAssessmentWriteResult(supersession, False)
        except FormalAssessmentPersistenceError:
            raise
        except sqlite3.IntegrityError as exc:
            raise FormalAssessmentIntegrityError(
                "Result supersession violated immutable persistence integrity"
            ) from exc

    def append_evidence_guidance(
        self,
        guidance: FormalEvidenceGuidance,
        *,
        request: RequestIdentity,
    ) -> FormalAssessmentWriteResult:
        encoded, digest = serialize_formal_assessment_record(guidance)
        source = guidance.source_result
        lineage_id = source.manifest.run_lineage.formal_lifecycle_id
        try:
            with self._transaction() as connection:
                if self._check_replay(
                    connection,
                    request=request,
                    operation_type="APPEND_EVIDENCE_GUIDANCE",
                    operation_payload_sha256=digest,
                    result_schema_version=guidance.schema_version,
                    result_identity=guidance.guidance_id,
                ):
                    return FormalAssessmentWriteResult(
                        self._load_guidance(connection, guidance.guidance_id), True
                    )
                persisted = self._load_terminal(connection, source.result_id)
                if persisted != source:
                    raise FormalAssessmentIntegrityError(
                        "Guidance source result does not equal persisted result bytes"
                    )
                self._insert_exact(
                    connection,
                    table="preliminary_formal_evidence_guidance",
                    where_sql="guidance_id = ?",
                    where_values=(guidance.guidance_id,),
                    insert_sql="""INSERT INTO preliminary_formal_evidence_guidance(
                        guidance_id, formal_lifecycle_id, source_result_id,
                        catalogue_id, catalogue_fingerprint, schema_version,
                        store_contract, payload_json, payload_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    insert_values=(
                        guidance.guidance_id,
                        lineage_id,
                        source.result_id,
                        guidance.catalogue_id,
                        guidance.catalogue_fingerprint,
                        guidance.schema_version,
                        guidance.store_contract,
                        encoded,
                        digest,
                    ),
                    payload_json=encoded,
                    payload_sha256=digest,
                )
                self._inject("APPEND_EVIDENCE_GUIDANCE")
                self._record_operation(
                    connection,
                    request=request,
                    operation_type="APPEND_EVIDENCE_GUIDANCE",
                    operation_payload_sha256=digest,
                    result_schema_version=guidance.schema_version,
                    result_identity=guidance.guidance_id,
                )
                return FormalAssessmentWriteResult(guidance, False)
        except FormalAssessmentPersistenceError:
            raise
        except sqlite3.IntegrityError as exc:
            raise FormalAssessmentIntegrityError(
                "Evidence-guidance append violated immutable persistence integrity"
            ) from exc

    @staticmethod
    def _load_one(
        connection: sqlite3.Connection,
        table: str,
        where_sql: str,
        values: tuple[object, ...],
    ) -> BaseModel:
        row = connection.execute(
            f"""SELECT schema_version, payload_json, payload_sha256
                FROM {table} WHERE {where_sql}""",
            values,
        ).fetchone()
        if row is None:
            raise ArtifactNotFoundError("Formal-assessment record does not exist")
        return SQLiteFormalAssessmentRepository._deserialize_row(row)

    def _load_input_choice(
        self, connection: sqlite3.Connection, identity: str
    ) -> FormalAssessmentInputChoice:
        record = self._load_one(
            connection,
            "preliminary_formal_assessment_input_choices",
            "input_choice_id = ?",
            (identity,),
        )
        if not isinstance(record, FormalAssessmentInputChoice):
            raise ArtifactCorruptionError("Stored input choice has wrong type")
        return record

    def _load_resolution(
        self, connection: sqlite3.Connection, identity: str
    ) -> FormalInputConflictResolution:
        record = self._load_one(
            connection,
            "preliminary_formal_input_conflict_resolutions",
            "resolution_id = ?",
            (identity,),
        )
        if not isinstance(record, FormalInputConflictResolution):
            raise ArtifactCorruptionError("Stored resolution has wrong type")
        return record

    def _load_authorization(
        self, connection: sqlite3.Connection, identity: str
    ) -> FormalAssessmentAuthorization:
        record = self._load_one(
            connection,
            "preliminary_formal_assessment_authorizations",
            "authorization_id = ?",
            (identity,),
        )
        if not isinstance(record, FormalAssessmentAuthorization):
            raise ArtifactCorruptionError("Stored authorization has wrong type")
        return record

    def _load_projection(
        self, connection: sqlite3.Connection, identity: str
    ) -> FormalAssessmentInputProjection:
        record = self._load_one(
            connection,
            "preliminary_formal_assessment_projections",
            "projection_id = ?",
            (identity,),
        )
        if not isinstance(record, FormalAssessmentInputProjection):
            raise ArtifactCorruptionError("Stored projection has wrong type")
        return record

    def _load_run_request(
        self, connection: sqlite3.Connection, identity: str
    ) -> FormalAssessmentRunRequest:
        record = self._load_one(
            connection,
            "preliminary_formal_assessment_run_requests",
            "request_token = ?",
            (identity,),
        )
        if not isinstance(record, FormalAssessmentRunRequest):
            raise ArtifactCorruptionError("Stored run request has wrong type")
        return record

    def _load_manifest(
        self, connection: sqlite3.Connection, run_id: str, attempt_number: int
    ) -> FormalAssessmentRunManifest:
        record = self._load_one(
            connection,
            "preliminary_formal_assessment_run_manifests",
            "run_id = ? AND attempt_number = ?",
            (run_id, attempt_number),
        )
        if not isinstance(record, FormalAssessmentRunManifest):
            raise ArtifactCorruptionError("Stored manifest has wrong type")
        return record

    def _load_event(
        self, connection: sqlite3.Connection, event_id: str
    ) -> FormalAssessmentRunEvent:
        record = self._load_one(
            connection,
            "preliminary_formal_assessment_run_events",
            "event_id = ?",
            (event_id,),
        )
        if not isinstance(record, FormalAssessmentRunEvent):
            raise ArtifactCorruptionError("Stored event has wrong type")
        return record

    def _load_events(
        self, connection: sqlite3.Connection, run_id: str, attempt_number: int
    ) -> tuple[FormalAssessmentRunEvent, ...]:
        rows = connection.execute(
            """SELECT schema_version, payload_json, payload_sha256
               FROM preliminary_formal_assessment_run_events
               WHERE run_id = ? AND attempt_number = ? ORDER BY sequence""",
            (run_id, attempt_number),
        ).fetchall()
        records = tuple(self._deserialize_row(row) for row in rows)
        if not all(isinstance(item, FormalAssessmentRunEvent) for item in records):
            raise ArtifactCorruptionError("Stored event history has wrong type")
        return records  # type: ignore[return-value]

    def _load_terminal(
        self, connection: sqlite3.Connection, identity: str
    ) -> FormalAssessmentResult | FormalAssessmentTerminalFailure:
        record = self._load_one(
            connection,
            "preliminary_formal_assessment_terminal_records",
            "terminal_record_id = ? OR result_id = ?",
            (identity, identity),
        )
        if not isinstance(
            record, (FormalAssessmentResult, FormalAssessmentTerminalFailure)
        ):
            raise ArtifactCorruptionError("Stored terminal record has wrong type")
        return record

    def _load_supersession(
        self, connection: sqlite3.Connection, identity: str
    ) -> FormalAssessmentResultSupersession:
        record = self._load_one(
            connection,
            "preliminary_formal_assessment_result_supersessions",
            "supersession_id = ?",
            (identity,),
        )
        if not isinstance(record, FormalAssessmentResultSupersession):
            raise ArtifactCorruptionError("Stored supersession has wrong type")
        return record

    def _load_guidance(
        self, connection: sqlite3.Connection, identity: str
    ) -> FormalEvidenceGuidance:
        record = self._load_one(
            connection,
            "preliminary_formal_evidence_guidance",
            "guidance_id = ?",
            (identity,),
        )
        if not isinstance(record, FormalEvidenceGuidance):
            raise ArtifactCorruptionError("Stored guidance has wrong type")
        return record

    def load_input_choice(self, identity: str) -> FormalAssessmentInputChoice:
        with self._read() as connection:
            return self._load_input_choice(connection, identity)

    def load_conflict_resolution(
        self, identity: str
    ) -> FormalInputConflictResolution:
        with self._read() as connection:
            return self._load_resolution(connection, identity)

    def load_authorization(self, identity: str) -> FormalAssessmentAuthorization:
        with self._read() as connection:
            return self._load_authorization(connection, identity)

    def load_projection(self, identity: str) -> FormalAssessmentInputProjection:
        with self._read() as connection:
            return self._load_projection(connection, identity)

    def load_run_request(self, request_token: str) -> FormalAssessmentRunRequest:
        with self._read() as connection:
            return self._load_run_request(connection, request_token)

    def load_manifest(
        self, run_id: str, attempt_number: int = 1
    ) -> FormalAssessmentRunManifest:
        with self._read() as connection:
            return self._load_manifest(connection, run_id, attempt_number)

    def load_run_events(
        self, run_id: str, attempt_number: int = 1
    ) -> tuple[FormalAssessmentRunEvent, ...]:
        with self._read() as connection:
            return self._load_events(connection, run_id, attempt_number)

    def load_run_state(
        self, run_id: str, attempt_number: int = 1
    ) -> FormalAssessmentRunState:
        with self._read() as connection:
            row = connection.execute(
                """SELECT schema_version, payload_json, payload_sha256
                   FROM preliminary_formal_assessment_run_states
                   WHERE run_id = ? AND attempt_number = ?
                   ORDER BY event_count DESC LIMIT 1""",
                (run_id, attempt_number),
            ).fetchone()
            if row is None:
                raise ArtifactNotFoundError("Formal run state does not exist")
            record = self._deserialize_row(row)
            if not isinstance(record, FormalAssessmentRunState):
                raise ArtifactCorruptionError("Stored run state has wrong type")
            return record

    def load_terminal_record(
        self, identity: str
    ) -> FormalAssessmentResult | FormalAssessmentTerminalFailure:
        with self._read() as connection:
            return self._load_terminal(connection, identity)

    def load_result_supersession(
        self, identity: str
    ) -> FormalAssessmentResultSupersession:
        with self._read() as connection:
            return self._load_supersession(connection, identity)

    def load_evidence_guidance(self, identity: str) -> FormalEvidenceGuidance:
        with self._read() as connection:
            return self._load_guidance(connection, identity)

    def run_history(self, run_id: str) -> FormalAssessmentRunHistory:
        with self._read() as connection:
            manifest_rows = connection.execute(
                """SELECT schema_version, payload_json, payload_sha256
                   FROM preliminary_formal_assessment_run_manifests
                   WHERE run_id = ? ORDER BY attempt_number""",
                (run_id,),
            ).fetchall()
            event_rows = connection.execute(
                """SELECT schema_version, payload_json, payload_sha256
                   FROM preliminary_formal_assessment_run_events
                   WHERE run_id = ? ORDER BY attempt_number, sequence""",
                (run_id,),
            ).fetchall()
            state_rows = connection.execute(
                """SELECT schema_version, payload_json, payload_sha256
                   FROM preliminary_formal_assessment_run_states
                   WHERE run_id = ? ORDER BY attempt_number, event_count""",
                (run_id,),
            ).fetchall()
            terminal_rows = connection.execute(
                """SELECT schema_version, payload_json, payload_sha256
                   FROM preliminary_formal_assessment_terminal_records
                   WHERE run_id = ? ORDER BY attempt_number""",
                (run_id,),
            ).fetchall()
            manifests = tuple(self._deserialize_row(row) for row in manifest_rows)
            events = tuple(self._deserialize_row(row) for row in event_rows)
            states = tuple(self._deserialize_row(row) for row in state_rows)
            terminals = tuple(self._deserialize_row(row) for row in terminal_rows)
            if not all(isinstance(item, FormalAssessmentRunManifest) for item in manifests):
                raise ArtifactCorruptionError("Manifest history is corrupt")
            if not all(isinstance(item, FormalAssessmentRunEvent) for item in events):
                raise ArtifactCorruptionError("Event history is corrupt")
            if not all(isinstance(item, FormalAssessmentRunState) for item in states):
                raise ArtifactCorruptionError("State history is corrupt")
            if not all(
                isinstance(item, (FormalAssessmentResult, FormalAssessmentTerminalFailure))
                for item in terminals
            ):
                raise ArtifactCorruptionError("Terminal history is corrupt")
            return FormalAssessmentRunHistory(
                manifests=manifests,  # type: ignore[arg-type]
                events=events,  # type: ignore[arg-type]
                states=states,  # type: ignore[arg-type]
                terminal_records=terminals,  # type: ignore[arg-type]
            )

    def lifecycle_authorizations(
        self, formal_lifecycle_id: str
    ) -> tuple[FormalAssessmentAuthorization, ...]:
        with self._read() as connection:
            rows = connection.execute(
                """SELECT schema_version, payload_json, payload_sha256
                   FROM preliminary_formal_assessment_authorizations
                   WHERE formal_lifecycle_id = ? ORDER BY rowid""",
                (formal_lifecycle_id,),
            ).fetchall()
            records = tuple(self._deserialize_row(row) for row in rows)
            if not all(isinstance(item, FormalAssessmentAuthorization) for item in records):
                raise ArtifactCorruptionError("Authorization history is corrupt")
            return records  # type: ignore[return-value]

    def projections_for_authorization(
        self, authorization_id: str
    ) -> tuple[FormalAssessmentInputProjection, ...]:
        with self._read() as connection:
            rows = connection.execute(
                """SELECT schema_version, payload_json, payload_sha256
                   FROM preliminary_formal_assessment_projections
                   WHERE authorization_id = ? ORDER BY rowid""",
                (authorization_id,),
            ).fetchall()
            records = tuple(self._deserialize_row(row) for row in rows)
            if not all(isinstance(item, FormalAssessmentInputProjection) for item in records):
                raise ArtifactCorruptionError("Projection history is corrupt")
            return records  # type: ignore[return-value]

    def successful_result_heads(
        self, formal_lifecycle_id: str
    ) -> tuple[FormalAssessmentResult, ...]:
        """Return immutable unsuperseded successful-result heads only."""

        with self._read() as connection:
            rows = connection.execute(
                """SELECT terminal.schema_version, terminal.payload_json,
                          terminal.payload_sha256
                   FROM preliminary_formal_assessment_terminal_records terminal
                   WHERE terminal.formal_lifecycle_id = ?
                     AND terminal.record_kind = 'SUCCESS'
                     AND NOT EXISTS (
                         SELECT 1
                         FROM preliminary_formal_assessment_result_supersessions link
                         WHERE link.superseded_result_id = terminal.result_id
                     )
                   ORDER BY terminal.rowid""",
                (formal_lifecycle_id,),
            ).fetchall()
            records = tuple(self._deserialize_row(row) for row in rows)
            if not all(isinstance(item, FormalAssessmentResult) for item in records):
                raise ArtifactCorruptionError("Successful result heads are corrupt")
            return records  # type: ignore[return-value]

    def current_successful_result(
        self, formal_lifecycle_id: str
    ) -> FormalAssessmentResult | None:
        records = self.successful_result_heads(formal_lifecycle_id)
        if not records:
            return None
        if len(records) != 1:
            raise FormalAssessmentIntegrityError(
                "Formal lifecycle has ambiguous current successful result heads"
            )
        return records[0]

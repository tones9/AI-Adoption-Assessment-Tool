"""Explicit SQLite persistence for ``preliminary-formal-evidence.v0.1``.

The repository is intentionally not constructed by application composition.  It
owns migration 7, immutable bytes, append-only records, and idempotent write
transactions only; it performs no upload, parsing, extraction, review, conversion,
readiness orchestration, or assessment execution.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from ai_adoption_engine.models.formal_evidence import (
    AttemptStatus,
    ContextNote,
    EvidenceClassification,
    ExternalProviderConsent,
    FormalEvidenceLineage,
    FormalEvidenceReadiness,
    FormalEvidenceWorkflowEvent,
    FormalInputCandidateSet,
    FormalInputMapping,
    MappingDisposition,
    RequestIdentity,
    ReviewAction,
    ReviewedEvidenceReference,
    SourceBlobState,
    SupportingDocument,
    SupportingDocumentIngestionAttempt,
    SupportingDocumentMetadataRevision,
    SupportingEvidenceExtractionAttempt,
    SupportingEvidenceProposal,
    SupportingEvidenceReviewRevision,
    SupportingSourceBlob,
)
from ai_adoption_engine.persistence.base import (
    ArtifactCorruptionError,
    ArtifactNotFoundError,
    PersistenceError,
)
from ai_adoption_engine.persistence.formal_evidence_serialization import (
    deserialize_formal_evidence_record,
    serialize_formal_evidence_record,
)
from ai_adoption_engine.persistence.preliminary import SQLitePreliminaryJourneyStore
from ai_adoption_engine.persistence.preliminary_migrations import (
    SUPPORTING_EVIDENCE_MIGRATION,
)
from ai_adoption_engine.persistence.workspace_protection import (
    assert_workspace_write_target_allowed,
    is_frozen_evaluation_portfolio_path,
)


FORMAL_EVIDENCE_OPERATION_REQUEST_SCHEMA = (
    "formal-evidence-operation-request.v0.1"
)

T = TypeVar("T", bound=BaseModel)


class FormalEvidencePersistenceError(PersistenceError):
    """A supporting-evidence persistence operation failed closed."""


class FormalEvidenceIdempotencyError(FormalEvidencePersistenceError):
    """A request token was reused for a different immutable operation."""


class FormalEvidenceLineageError(FormalEvidencePersistenceError):
    """A record did not match the persisted formal/approved-process lineage."""


class FormalEvidenceStaleWriteError(FormalEvidencePersistenceError):
    """An append attempted to build on a stale predecessor."""


class FormalEvidenceIntegrityError(FormalEvidencePersistenceError):
    """Cross-record evidence integrity could not be established."""


@dataclass(frozen=True)
class FormalEvidenceWriteResult(Generic[T]):
    record: T
    replayed: bool


@dataclass(frozen=True)
class FormalEvidenceOperationReplay:
    request_token: str
    canonical_request_sha256: str
    operation_type: str
    formal_lifecycle_id: str
    target_identity: str
    result_schema_version: str
    result_identity: str
    result_payload_sha256: str
    record: BaseModel


_RecordWriter = Callable[[sqlite3.Connection], None]
_FailureInjector = Callable[[str], None]


_TABLE_BY_SCHEMA = {
    "supporting-source-blob.v0.1": (
        "preliminary_supporting_source_blobs",
        "source_blob_id",
    ),
    "supporting-document.v0.1": (
        "preliminary_supporting_documents",
        "document_id",
    ),
    "supporting-document-metadata-revision.v0.1": (
        "preliminary_supporting_document_metadata_revisions",
        "revision_id",
    ),
    "supporting-document-ingestion-attempt.v0.1": (
        "preliminary_supporting_ingestion_attempts",
        "attempt_id",
    ),
    "supporting-evidence-extraction-attempt.v0.1": (
        "preliminary_supporting_extraction_attempts",
        "attempt_id",
    ),
    "supporting-evidence-proposal.v0.1": (
        "preliminary_supporting_evidence_proposals",
        "proposal_id",
    ),
    "supporting-evidence-review-revision.v0.1": (
        "preliminary_supporting_evidence_review_revisions",
        "revision_id",
    ),
    "formal-input-mapping.v0.1": (
        "preliminary_supporting_formal_input_mappings",
        "mapping_id",
    ),
    "formal-input-candidate-set.v0.1": (
        "preliminary_supporting_formal_input_candidate_sets",
        "candidate_set_id",
    ),
    "formal-evidence-readiness.v0.1": (
        "preliminary_supporting_formal_evidence_readiness",
        "readiness_id",
    ),
    "formal-evidence-workflow-event.v0.1": (
        "preliminary_supporting_formal_evidence_workflow_events",
        "event_id",
    ),
    "external-provider-consent.v0.1": (
        "preliminary_supporting_provider_consents",
        "consent_record_id",
    ),
    "context-note.v0.1": (
        "preliminary_supporting_context_notes",
        "context_note_id",
    ),
}


class SQLiteFormalEvidenceRepository:
    """Explicit migration-7 repository for immutable supporting evidence."""

    store_id = "preliminary-journey-store.v0.1"
    store_version = "0.1.0"

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
        failure_injector: _FailureInjector | None = None,
    ) -> None:
        self.path = Path(path)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.failure_injector = failure_injector
        assert_workspace_write_target_allowed(self.path)
        if str(self.path) == ":memory:":
            raise FormalEvidencePersistenceError(
                "Formal-evidence persistence requires an existing assessment database"
            )
        if not self.path.is_file():
            raise FormalEvidencePersistenceError(
                "Formal-evidence persistence requires an existing assessment database"
            )
        # Explicit construction is the sole activation point for migrations 1-7.
        SQLitePreliminaryJourneyStore(self.path, clock=self.clock)
        self._migrate_supporting_evidence()
        self.path.chmod(0o600)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _migrate_supporting_evidence(self) -> None:
        assert_workspace_write_target_allowed(self.path)
        version, script = SUPPORTING_EVIDENCE_MIGRATION
        connection = self._connect()
        try:
            applied = {
                row[0]
                for row in connection.execute(
                    "SELECT version FROM preliminary_journey_schema_migrations"
                )
            }
            if version in applied:
                return
            connection.executescript("BEGIN IMMEDIATE;\n" + script)
            connection.execute(
                """INSERT INTO preliminary_journey_schema_migrations(
                       version, store_id, store_version, applied_at
                   ) VALUES (?, ?, ?, ?)""",
                (version, self.store_id, self.store_version, self.clock().isoformat()),
            )
            connection.commit()
        except Exception as exc:
            connection.rollback()
            raise FormalEvidencePersistenceError(
                "Supporting-evidence migration 7 failed safely"
            ) from exc
        finally:
            connection.close()

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
            connection.close()

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        if is_frozen_evaluation_portfolio_path(self.path):
            connection = sqlite3.connect(
                f"file:{self.path.resolve()}?mode=ro&immutable=1",
                uri=True,
                timeout=30,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
        else:
            connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _operation_payload_sha256(payload_hashes: Iterable[str]) -> str:
        encoded = json.dumps(
            tuple(payload_hashes),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _lineage_values(lineage: FormalEvidenceLineage) -> tuple[Any, ...]:
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
               FROM preliminary_formal_evidence_lineages
               WHERE formal_lifecycle_id = ?""",
            (lineage.formal_lifecycle_id,),
        ).fetchone()
        expected = self._lineage_values(lineage)
        if row is not None:
            if tuple(row) != expected:
                raise FormalEvidenceLineageError(
                    "Formal lifecycle already has a different evidence lineage"
                )
            return
        try:
            connection.execute(
                """INSERT INTO preliminary_formal_evidence_lineages VALUES (
                       ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                   )""",
                expected,
            )
        except sqlite3.IntegrityError as exc:
            raise FormalEvidenceLineageError(
                "Formal-evidence lineage does not match persisted history"
            ) from exc

    def _request_row(
        self, connection: sqlite3.Connection, request_token: str
    ) -> sqlite3.Row | None:
        return connection.execute(
            """SELECT * FROM preliminary_supporting_operation_requests
               WHERE request_token = ?""",
            (request_token,),
        ).fetchone()

    def _write_idempotently(
        self,
        *,
        lineage: FormalEvidenceLineage,
        request: RequestIdentity,
        operation_type: str,
        target_identity: str,
        result_schema_version: str,
        result_identity: str,
        result_payload_sha256: str,
        operation_payload_sha256: str,
        writer: _RecordWriter,
    ) -> tuple[BaseModel, bool]:
        try:
            with self._transaction() as connection:
                existing = self._request_row(connection, request.request_token)
                if existing is not None:
                    expected = (
                        request.canonical_request_sha256,
                        operation_payload_sha256,
                        operation_type,
                        lineage.formal_lifecycle_id,
                        target_identity,
                        result_schema_version,
                        result_identity,
                        result_payload_sha256,
                    )
                    actual = tuple(
                        existing[name]
                        for name in (
                            "canonical_request_sha256",
                            "operation_payload_sha256",
                            "operation_type",
                            "formal_lifecycle_id",
                            "target_identity",
                            "result_schema_version",
                            "result_identity",
                            "result_payload_sha256",
                        )
                    )
                    if actual != expected:
                        raise FormalEvidenceIdempotencyError(
                            "Request token was reused for a different formal-evidence operation"
                        )
                    record = self._load_record(
                        connection, result_schema_version, result_identity
                    )
                    return record, True

                self._ensure_lineage(connection, lineage)
                writer(connection)
                if self.failure_injector is not None:
                    self.failure_injector(operation_type)
                connection.execute(
                    """INSERT INTO preliminary_supporting_operation_requests(
                           request_token, schema_version,
                           canonical_request_sha256, operation_payload_sha256,
                           operation_type, formal_lifecycle_id, target_identity,
                           result_schema_version, result_identity,
                           result_payload_sha256, recorded_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        request.request_token,
                        FORMAL_EVIDENCE_OPERATION_REQUEST_SCHEMA,
                        request.canonical_request_sha256,
                        operation_payload_sha256,
                        operation_type,
                        lineage.formal_lifecycle_id,
                        target_identity,
                        result_schema_version,
                        result_identity,
                        result_payload_sha256,
                        self.clock().isoformat(),
                    ),
                )
                record = self._load_record(
                    connection, result_schema_version, result_identity
                )
                return record, False
        except (
            FormalEvidencePersistenceError,
            ArtifactCorruptionError,
            ArtifactNotFoundError,
        ):
            raise
        except sqlite3.IntegrityError as exc:
            raise FormalEvidenceIntegrityError(
                "Formal-evidence append violated immutable persistence integrity"
            ) from exc
        except sqlite3.Error as exc:
            raise FormalEvidencePersistenceError(
                "Formal-evidence transaction failed safely"
            ) from exc

    def _load_record(
        self,
        connection: sqlite3.Connection,
        schema_version: str,
        record_identity: str,
    ) -> BaseModel:
        try:
            table, identity_column = _TABLE_BY_SCHEMA[schema_version]
        except KeyError as exc:
            raise ArtifactCorruptionError(
                f"Unsupported stored formal-evidence schema: {schema_version}"
            ) from exc
        row = connection.execute(
            f"""SELECT schema_version, payload_json, payload_sha256
                FROM {table} WHERE {identity_column} = ?""",
            (record_identity,),
        ).fetchone()
        if row is None:
            raise ArtifactNotFoundError("Formal-evidence record does not exist")
        if row["schema_version"] != schema_version:
            raise ArtifactCorruptionError(
                "Stored formal-evidence schema identity is inconsistent"
            )
        return deserialize_formal_evidence_record(
            schema_version,
            row["payload_json"],
            row["payload_sha256"],
        )

    def load_record(self, schema_version: str, record_identity: str) -> BaseModel:
        with self._read() as connection:
            return self._load_record(connection, schema_version, record_identity)

    def migration_versions(self) -> tuple[int, ...]:
        with self._read() as connection:
            return tuple(
                row[0]
                for row in connection.execute(
                    """SELECT version FROM preliminary_journey_schema_migrations
                       ORDER BY version"""
                )
            )

    def assert_writable(self) -> None:
        """Fail before parsing or provider work when the workspace is frozen."""

        assert_workspace_write_target_allowed(self.path)

    def load_operation_replay(
        self, request_token: str
    ) -> FormalEvidenceOperationReplay | None:
        with self._read() as connection:
            row = self._request_row(connection, request_token)
            if row is None:
                return None
            record = self._load_record(
                connection,
                row["result_schema_version"],
                row["result_identity"],
            )
            return FormalEvidenceOperationReplay(
                request_token=row["request_token"],
                canonical_request_sha256=row["canonical_request_sha256"],
                operation_type=row["operation_type"],
                formal_lifecycle_id=row["formal_lifecycle_id"],
                target_identity=row["target_identity"],
                result_schema_version=row["result_schema_version"],
                result_identity=row["result_identity"],
                result_payload_sha256=row["result_payload_sha256"],
                record=record,
            )

    def validate_active_lineage(self, lineage: FormalEvidenceLineage) -> None:
        """Validate the exact awaiting-inputs formal lineage without writing it."""

        with self._read() as connection:
            row = connection.execute(
                """SELECT lifecycle.schema_version, lifecycle.formal_lifecycle_id,
                          lifecycle.journey_id, lifecycle.source_assessment_id,
                          lifecycle.approved_review_artifact_id,
                          artifact.artifact_schema_version,
                          artifact.artifact_revision, artifact.payload_sha256,
                          lifecycle.source_document_id,
                          lifecycle.validated_process_id,
                          lifecycle.validated_process_fingerprint,
                          lifecycle.status
                   FROM preliminary_formal_lifecycles lifecycle
                   JOIN assessment_artifacts artifact
                     ON artifact.artifact_id = lifecycle.approved_review_artifact_id
                    AND artifact.assessment_id = lifecycle.source_assessment_id
                   WHERE lifecycle.formal_lifecycle_id = ?""",
                (lineage.formal_lifecycle_id,),
            ).fetchone()
            expected = (
                lineage.formal_lifecycle_schema,
                lineage.formal_lifecycle_id,
                lineage.journey_id,
                lineage.source_assessment_id,
                lineage.approved_review_artifact_id,
                lineage.approved_review_schema_version,
                lineage.approved_review_revision,
                lineage.approved_review_payload_sha256,
                lineage.source_document_id,
                lineage.validated_process_id,
                lineage.validated_process_fingerprint,
                "AWAITING_FORMAL_INPUTS",
            )
            if row is None or tuple(row) != expected:
                raise FormalEvidenceLineageError(
                    "Formal-evidence lineage is stale or does not identify the active awaiting-inputs lifecycle"
                )
            if lineage.source_document_id != f"doc-{lineage.source_document_sha256}":
                raise FormalEvidenceLineageError(
                    "Formal-evidence source document identity is inconsistent"
                )

    def load_active_lineage(
        self, formal_lifecycle_id: str
    ) -> FormalEvidenceLineage:
        """Reconstruct and validate the exact active formal lineage read-only."""

        with self._read() as connection:
            row = connection.execute(
                """SELECT lifecycle.schema_version AS formal_lifecycle_schema,
                          lifecycle.formal_lifecycle_id, lifecycle.journey_id,
                          lifecycle.source_assessment_id,
                          lifecycle.approved_review_artifact_id,
                          artifact.artifact_schema_version,
                          artifact.artifact_revision, artifact.payload_sha256,
                          lifecycle.source_document_id,
                          lifecycle.validated_process_id,
                          lifecycle.validated_process_fingerprint,
                          lifecycle.status
                   FROM preliminary_formal_lifecycles lifecycle
                   JOIN assessment_artifacts artifact
                     ON artifact.artifact_id = lifecycle.approved_review_artifact_id
                    AND artifact.assessment_id = lifecycle.source_assessment_id
                   WHERE lifecycle.formal_lifecycle_id = ?""",
                (formal_lifecycle_id,),
            ).fetchone()
            if row is None or row["status"] != "AWAITING_FORMAL_INPUTS":
                raise FormalEvidenceLineageError(
                    "Formal lifecycle is missing or is not awaiting formal inputs"
                )
            source_document_id = row["source_document_id"]
            source_hash = source_document_id.removeprefix("doc-")
            try:
                lineage = FormalEvidenceLineage(
                    formal_lifecycle_schema=row["formal_lifecycle_schema"],
                    formal_lifecycle_id=row["formal_lifecycle_id"],
                    journey_id=row["journey_id"],
                    source_assessment_id=row["source_assessment_id"],
                    approved_review_artifact_id=row[
                        "approved_review_artifact_id"
                    ],
                    approved_review_schema_version=row[
                        "artifact_schema_version"
                    ],
                    approved_review_revision=row["artifact_revision"],
                    approved_review_payload_sha256=row["payload_sha256"],
                    source_document_id=source_document_id,
                    source_document_sha256=source_hash,
                    validated_process_id=row["validated_process_id"],
                    validated_process_fingerprint=row[
                        "validated_process_fingerprint"
                    ],
                )
            except Exception as exc:
                raise ArtifactCorruptionError(
                    "Persisted formal lifecycle cannot reconstruct exact evidence lineage"
                ) from exc
        self.validate_active_lineage(lineage)
        return lineage

    def approved_activity_catalog(
        self, lineage: FormalEvidenceLineage
    ) -> tuple[tuple[str, str], ...]:
        self.validate_active_lineage(lineage)
        with self._read() as connection:
            row = connection.execute(
                """SELECT payload_json FROM assessment_artifacts
                   WHERE artifact_id = ? AND assessment_id = ?
                     AND artifact_schema_version = ? AND artifact_revision = ?
                     AND payload_sha256 = ?""",
                (
                    lineage.approved_review_artifact_id,
                    lineage.source_assessment_id,
                    lineage.approved_review_schema_version,
                    lineage.approved_review_revision,
                    lineage.approved_review_payload_sha256,
                ),
            ).fetchone()
            if row is None:
                raise FormalEvidenceLineageError(
                    "Approved activity catalogue no longer matches formal lineage"
                )
            try:
                payload = json.loads(row[0])
                return tuple(
                    (step["step_id"], step["activity"])
                    for step in payload["business_process"]["steps"]
                )
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise ArtifactCorruptionError(
                    "Approved activity catalogue is corrupt"
                ) from exc

    def find_document_by_content(
        self,
        *,
        formal_lifecycle_id: str,
        content_sha256: str,
    ) -> SupportingDocument | None:
        with self._read() as connection:
            row = connection.execute(
                """SELECT document_id FROM preliminary_supporting_documents
                   WHERE formal_lifecycle_id = ? AND source_blob_sha256 = ?
                   ORDER BY rowid LIMIT 1""",
                (formal_lifecycle_id, content_sha256),
            ).fetchone()
            if row is None:
                return None
            record = self._load_record(
                connection, "supporting-document.v0.1", row["document_id"]
            )
            if not isinstance(record, SupportingDocument):
                raise ArtifactCorruptionError("Stored supporting document type is invalid")
            return record

    def current_documents(
        self, formal_lifecycle_id: str
    ) -> tuple[SupportingDocument, ...]:
        with self._read() as connection:
            rows = connection.execute(
                """SELECT current.document_id
                   FROM preliminary_supporting_documents current
                   WHERE current.formal_lifecycle_id = ?
                     AND NOT EXISTS (
                         SELECT 1 FROM preliminary_supporting_documents newer
                         WHERE newer.formal_lifecycle_id = current.formal_lifecycle_id
                           AND newer.superseded_document_id = current.document_id
                     )
                   ORDER BY current.rowid""",
                (formal_lifecycle_id,),
            ).fetchall()
            records = tuple(
                self._load_record(
                    connection, "supporting-document.v0.1", row["document_id"]
                )
                for row in rows
            )
            if not all(isinstance(item, SupportingDocument) for item in records):
                raise ArtifactCorruptionError("Current supporting-document history is corrupt")
            return records  # type: ignore[return-value]

    def documents_for_lifecycle(
        self, formal_lifecycle_id: str
    ) -> tuple[SupportingDocument, ...]:
        with self._read() as connection:
            rows = connection.execute(
                """SELECT document_id FROM preliminary_supporting_documents
                   WHERE formal_lifecycle_id = ? ORDER BY rowid""",
                (formal_lifecycle_id,),
            ).fetchall()
            records = tuple(
                self._load_record(
                    connection, "supporting-document.v0.1", row["document_id"]
                )
                for row in rows
            )
            if not all(isinstance(item, SupportingDocument) for item in records):
                raise ArtifactCorruptionError(
                    "Stored supporting-document history is corrupt"
                )
            return records  # type: ignore[return-value]

    def is_current_document(
        self, *, formal_lifecycle_id: str, document_id: str
    ) -> bool:
        return any(
            item.document_id == document_id
            for item in self.current_documents(formal_lifecycle_id)
        )

    def latest_provider_consent(
        self,
        *,
        formal_lifecycle_id: str,
        document_id: str,
        provider_id: str,
    ) -> ExternalProviderConsent | None:
        with self._read() as connection:
            row = connection.execute(
                """SELECT consent_record_id
                   FROM preliminary_supporting_provider_consents
                   WHERE formal_lifecycle_id = ? AND document_id = ?
                     AND provider_id = ?
                   ORDER BY rowid DESC LIMIT 1""",
                (formal_lifecycle_id, document_id, provider_id),
            ).fetchone()
            if row is None:
                return None
            record = self._load_record(
                connection,
                "external-provider-consent.v0.1",
                row["consent_record_id"],
            )
            if not isinstance(record, ExternalProviderConsent):
                raise ArtifactCorruptionError("Stored provider consent type is invalid")
            return record

    def latest_ingestion_attempt(
        self, *, formal_lifecycle_id: str, document_id: str
    ) -> SupportingDocumentIngestionAttempt | None:
        return self._latest_attempt(
            table="preliminary_supporting_ingestion_attempts",
            schema_version="supporting-document-ingestion-attempt.v0.1",
            formal_lifecycle_id=formal_lifecycle_id,
            document_id=document_id,
        )  # type: ignore[return-value]

    def latest_extraction_attempt(
        self, *, formal_lifecycle_id: str, document_id: str
    ) -> SupportingEvidenceExtractionAttempt | None:
        return self._latest_attempt(
            table="preliminary_supporting_extraction_attempts",
            schema_version="supporting-evidence-extraction-attempt.v0.1",
            formal_lifecycle_id=formal_lifecycle_id,
            document_id=document_id,
        )  # type: ignore[return-value]

    def extraction_attempts_for_document(
        self, *, formal_lifecycle_id: str, document_id: str
    ) -> tuple[SupportingEvidenceExtractionAttempt, ...]:
        with self._read() as connection:
            rows = connection.execute(
                """SELECT attempt_id
                   FROM preliminary_supporting_extraction_attempts
                   WHERE formal_lifecycle_id = ? AND document_id = ?
                   ORDER BY attempt_number""",
                (formal_lifecycle_id, document_id),
            ).fetchall()
            records = tuple(
                self._load_record(
                    connection,
                    "supporting-evidence-extraction-attempt.v0.1",
                    row["attempt_id"],
                )
                for row in rows
            )
            if not all(
                isinstance(item, SupportingEvidenceExtractionAttempt)
                for item in records
            ):
                raise ArtifactCorruptionError(
                    "Stored supporting extraction history is corrupt"
                )
            return records  # type: ignore[return-value]

    def _latest_attempt(
        self,
        *,
        table: str,
        schema_version: str,
        formal_lifecycle_id: str,
        document_id: str,
    ) -> BaseModel | None:
        with self._read() as connection:
            row = connection.execute(
                f"""SELECT attempt_id FROM {table}
                    WHERE formal_lifecycle_id = ? AND document_id = ?
                    ORDER BY attempt_number DESC LIMIT 1""",
                (formal_lifecycle_id, document_id),
            ).fetchone()
            if row is None:
                return None
            return self._load_record(connection, schema_version, row["attempt_id"])

    def proposals_for_attempt(
        self, attempt_id: str
    ) -> tuple[SupportingEvidenceProposal, ...]:
        with self._read() as connection:
            rows = connection.execute(
                """SELECT proposal_id
                   FROM preliminary_supporting_evidence_proposals
                   WHERE extraction_attempt_id = ? ORDER BY rowid""",
                (attempt_id,),
            ).fetchall()
            records = tuple(
                self._load_record(
                    connection, "supporting-evidence-proposal.v0.1", row[0]
                )
                for row in rows
            )
            if not all(isinstance(item, SupportingEvidenceProposal) for item in records):
                raise ArtifactCorruptionError("Stored extraction proposals are corrupt")
            return records  # type: ignore[return-value]

    def review_revisions_for_proposal(
        self, proposal_id: str
    ) -> tuple[SupportingEvidenceReviewRevision, ...]:
        with self._read() as connection:
            rows = connection.execute(
                """SELECT revision_id
                   FROM preliminary_supporting_evidence_review_revisions
                   WHERE proposal_id = ? ORDER BY revision_number""",
                (proposal_id,),
            ).fetchall()
            records = tuple(
                self._load_record(
                    connection,
                    "supporting-evidence-review-revision.v0.1",
                    row["revision_id"],
                )
                for row in rows
            )
            if not all(
                isinstance(item, SupportingEvidenceReviewRevision)
                for item in records
            ):
                raise ArtifactCorruptionError("Stored review history is corrupt")
            return records  # type: ignore[return-value]

    def latest_review_revision(
        self, proposal_id: str
    ) -> SupportingEvidenceReviewRevision | None:
        revisions = self.review_revisions_for_proposal(proposal_id)
        return None if not revisions else revisions[-1]

    def context_notes_for_lifecycle(
        self, formal_lifecycle_id: str
    ) -> tuple[ContextNote, ...]:
        with self._read() as connection:
            rows = connection.execute(
                """SELECT context_note_id
                   FROM preliminary_supporting_context_notes
                   WHERE formal_lifecycle_id = ? ORDER BY rowid""",
                (formal_lifecycle_id,),
            ).fetchall()
            records = tuple(
                self._load_record(
                    connection, "context-note.v0.1", row["context_note_id"]
                )
                for row in rows
            )
            if not all(isinstance(item, ContextNote) for item in records):
                raise ArtifactCorruptionError("Stored context-note history is corrupt")
            return records  # type: ignore[return-value]

    def metadata_revisions_for_document(
        self,
        formal_lifecycle_id: str,
        document_id: str,
    ) -> tuple[SupportingDocumentMetadataRevision, ...]:
        with self._read() as connection:
            rows = connection.execute(
                """SELECT revision_id
                   FROM preliminary_supporting_document_metadata_revisions
                   WHERE formal_lifecycle_id = ? AND document_id = ?
                   ORDER BY revision_number""",
                (formal_lifecycle_id, document_id),
            ).fetchall()
            records = tuple(
                self._load_record(
                    connection,
                    "supporting-document-metadata-revision.v0.1",
                    row["revision_id"],
                )
                for row in rows
            )
            if not all(
                isinstance(item, SupportingDocumentMetadataRevision)
                for item in records
            ):
                raise ArtifactCorruptionError("Stored metadata history is corrupt")
            return records  # type: ignore[return-value]

    def formal_mappings_for_lifecycle(
        self, formal_lifecycle_id: str
    ) -> tuple[FormalInputMapping, ...]:
        return self.list_records(
            "formal-input-mapping.v0.1",
            formal_lifecycle_id=formal_lifecycle_id,
        )  # type: ignore[return-value]

    def candidate_sets_for_lifecycle(
        self, formal_lifecycle_id: str
    ) -> tuple[FormalInputCandidateSet, ...]:
        return self.list_records(
            "formal-input-candidate-set.v0.1",
            formal_lifecycle_id=formal_lifecycle_id,
        )  # type: ignore[return-value]

    def readiness_for_lifecycle(
        self, formal_lifecycle_id: str
    ) -> tuple[FormalEvidenceReadiness, ...]:
        return self.list_records(
            "formal-evidence-readiness.v0.1",
            formal_lifecycle_id=formal_lifecycle_id,
        )  # type: ignore[return-value]

    def latest_workflow_event(
        self, formal_lifecycle_id: str
    ) -> FormalEvidenceWorkflowEvent | None:
        with self._read() as connection:
            row = connection.execute(
                """SELECT event_id
                   FROM preliminary_supporting_formal_evidence_workflow_events
                   WHERE formal_lifecycle_id = ?
                   ORDER BY lifecycle_sequence DESC LIMIT 1""",
                (formal_lifecycle_id,),
            ).fetchone()
            if row is None:
                return None
            record = self._load_record(
                connection, "formal-evidence-workflow-event.v0.1", row[0]
            )
            if not isinstance(record, FormalEvidenceWorkflowEvent):
                raise ArtifactCorruptionError("Stored workflow-event type is invalid")
            return record

    def load_source_bytes(self, source_blob_id: str) -> bytes | None:
        with self._read() as connection:
            row = connection.execute(
                """SELECT content_bytes, content_sha256, byte_size
                   FROM preliminary_supporting_source_blob_bytes
                   WHERE source_blob_id = ?""",
                (source_blob_id,),
            ).fetchone()
            if row is None:
                return None
            content = bytes(row["content_bytes"])
            if len(content) != row["byte_size"] or (
                hashlib.sha256(content).hexdigest() != row["content_sha256"]
            ):
                raise ArtifactCorruptionError(
                    "Stored supporting source bytes failed integrity validation"
                )
            return content

    def store_source_blob(
        self,
        blob: SupportingSourceBlob,
        *,
        lineage: FormalEvidenceLineage,
        request: RequestIdentity,
        content_bytes: bytes | None,
    ) -> FormalEvidenceWriteResult[SupportingSourceBlob]:
        if blob.state is SourceBlobState.ACCEPTED:
            if content_bytes is None:
                raise FormalEvidenceIntegrityError(
                    "Accepted supporting blobs require immutable source bytes"
                )
            if len(content_bytes) != blob.byte_size:
                raise FormalEvidenceIntegrityError(
                    "Supporting source byte length does not match blob metadata"
                )
            if hashlib.sha256(content_bytes).hexdigest() != blob.content_sha256:
                raise FormalEvidenceIntegrityError(
                    "Supporting source bytes do not match the declared SHA-256"
                )
        elif content_bytes is not None:
            raise FormalEvidenceIntegrityError(
                "Rejected supporting blobs cannot retain source bytes"
            )
        payload_json, payload_sha = serialize_formal_evidence_record(blob)
        operation_sha = self._operation_payload_sha256((payload_sha, blob.content_sha256))

        def writer(connection: sqlite3.Connection) -> None:
            existing = connection.execute(
                """SELECT payload_sha256 FROM preliminary_supporting_source_blobs
                   WHERE source_blob_id = ?""",
                (blob.source_blob_id,),
            ).fetchone()
            if existing is not None:
                if existing[0] != payload_sha:
                    raise FormalEvidenceIntegrityError(
                        "Content-derived blob identity already has different metadata"
                    )
                if blob.state is SourceBlobState.ACCEPTED:
                    stored = connection.execute(
                        """SELECT content_bytes
                           FROM preliminary_supporting_source_blob_bytes
                           WHERE source_blob_id = ?""",
                        (blob.source_blob_id,),
                    ).fetchone()
                    if stored is None or bytes(stored[0]) != content_bytes:
                        raise FormalEvidenceIntegrityError(
                            "Stored immutable source bytes do not match replayed content"
                        )
                return
            connection.execute(
                """INSERT INTO preliminary_supporting_source_blobs(
                       source_blob_id, schema_version, contract_family,
                       content_sha256, byte_size, state, rejection_code,
                       payload_json, payload_sha256
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    blob.source_blob_id,
                    blob.schema_version,
                    blob.contract_family,
                    blob.content_sha256,
                    blob.byte_size,
                    blob.state.value,
                    None if blob.rejection_code is None else blob.rejection_code.value,
                    payload_json,
                    payload_sha,
                ),
            )
            if content_bytes is not None:
                connection.execute(
                    """INSERT INTO preliminary_supporting_source_blob_bytes(
                           source_blob_id, content_sha256, byte_size, content_bytes
                       ) VALUES (?, ?, ?, ?)""",
                    (
                        blob.source_blob_id,
                        blob.content_sha256,
                        blob.byte_size,
                        content_bytes,
                    ),
                )

        record, replayed = self._write_idempotently(
            lineage=lineage,
            request=request,
            operation_type="STORE_SOURCE_BLOB",
            target_identity=blob.source_blob_id,
            result_schema_version=blob.schema_version,
            result_identity=blob.source_blob_id,
            result_payload_sha256=payload_sha,
            operation_payload_sha256=operation_sha,
            writer=writer,
        )
        return FormalEvidenceWriteResult(record=record, replayed=replayed)  # type: ignore[arg-type]

    def store_document_intake(
        self,
        blob: SupportingSourceBlob,
        document: SupportingDocument,
        initial_metadata: SupportingDocumentMetadataRevision,
        *,
        request: RequestIdentity,
        content_bytes: bytes,
    ) -> FormalEvidenceWriteResult[SupportingDocument]:
        """Atomically retain accepted bytes and create one contextual document."""

        if blob.state is not SourceBlobState.ACCEPTED:
            raise FormalEvidenceIntegrityError(
                "A contextual supporting document requires an accepted source blob"
            )
        if len(content_bytes) != blob.byte_size:
            raise FormalEvidenceIntegrityError(
                "Supporting source byte length does not match blob metadata"
            )
        if hashlib.sha256(content_bytes).hexdigest() != blob.content_sha256:
            raise FormalEvidenceIntegrityError(
                "Supporting source bytes do not match the declared SHA-256"
            )
        if (
            document.source_blob_id != blob.source_blob_id
            or document.source_blob_sha256 != blob.content_sha256
            or document.byte_size != blob.byte_size
        ):
            raise FormalEvidenceIntegrityError(
                "Supporting document does not match its immutable source blob"
            )
        if document.lineage != initial_metadata.lineage:
            raise FormalEvidenceLineageError("Document and metadata lineage must match")
        if initial_metadata.document_id != document.document_id:
            raise FormalEvidenceIntegrityError("Initial metadata document is inconsistent")
        if initial_metadata.revision_id != document.initial_metadata_revision_id:
            raise FormalEvidenceIntegrityError("Initial metadata identity is inconsistent")
        if initial_metadata.revision_number != 1 or initial_metadata.prior_revision_id:
            raise FormalEvidenceIntegrityError("Initial metadata must be revision 1")
        if initial_metadata.request != request:
            raise FormalEvidenceIdempotencyError(
                "Document operation request must match initial metadata request"
            )
        blob_json, blob_sha = serialize_formal_evidence_record(blob)
        document_json, document_sha = serialize_formal_evidence_record(document)
        metadata_json, metadata_sha = serialize_formal_evidence_record(initial_metadata)
        operation_sha = self._operation_payload_sha256(
            (blob_sha, document_sha, metadata_sha, blob.content_sha256)
        )

        def writer(connection: sqlite3.Connection) -> None:
            existing_blob = connection.execute(
                """SELECT content_sha256, byte_size, state
                   FROM preliminary_supporting_source_blobs
                   WHERE source_blob_id = ?""",
                (blob.source_blob_id,),
            ).fetchone()
            if existing_blob is None:
                connection.execute(
                    """INSERT INTO preliminary_supporting_source_blobs(
                           source_blob_id, schema_version, contract_family,
                           content_sha256, byte_size, state, rejection_code,
                           payload_json, payload_sha256
                       ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
                    (
                        blob.source_blob_id,
                        blob.schema_version,
                        blob.contract_family,
                        blob.content_sha256,
                        blob.byte_size,
                        blob.state.value,
                        blob_json,
                        blob_sha,
                    ),
                )
                connection.execute(
                    """INSERT INTO preliminary_supporting_source_blob_bytes(
                           source_blob_id, content_sha256, byte_size, content_bytes
                       ) VALUES (?, ?, ?, ?)""",
                    (
                        blob.source_blob_id,
                        blob.content_sha256,
                        blob.byte_size,
                        content_bytes,
                    ),
                )
            else:
                if tuple(existing_blob) != (
                    blob.content_sha256,
                    blob.byte_size,
                    SourceBlobState.ACCEPTED.value,
                ):
                    raise FormalEvidenceIntegrityError(
                        "Content-derived source identity has conflicting metadata"
                    )
                stored_bytes = connection.execute(
                    """SELECT content_bytes
                       FROM preliminary_supporting_source_blob_bytes
                       WHERE source_blob_id = ?""",
                    (blob.source_blob_id,),
                ).fetchone()
                if stored_bytes is None or bytes(stored_bytes[0]) != content_bytes:
                    raise FormalEvidenceIntegrityError(
                        "Stored immutable source bytes do not match the accepted content"
                    )

            if document.superseded_document is not None:
                previous = self._load_record(
                    connection,
                    document.schema_version,
                    document.superseded_document.document_id,
                )
                if not isinstance(previous, SupportingDocument) or (
                    previous.lineage != document.lineage
                    or previous.source_blob_sha256
                    != document.superseded_document.content_sha256
                ):
                    raise FormalEvidenceLineageError(
                        "Superseded document reference does not match persisted history"
                    )
            connection.execute(
                """INSERT INTO preliminary_supporting_document_metadata_revisions(
                       revision_id, formal_lifecycle_id, document_id,
                       schema_version, contract_family, revision_number,
                       prior_revision_id, request_token, payload_json, payload_sha256
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    initial_metadata.revision_id,
                    document.lineage.formal_lifecycle_id,
                    document.document_id,
                    initial_metadata.schema_version,
                    initial_metadata.contract_family,
                    1,
                    None,
                    request.request_token,
                    metadata_json,
                    metadata_sha,
                ),
            )
            connection.execute(
                """INSERT INTO preliminary_supporting_documents(
                       document_id, formal_lifecycle_id, schema_version,
                       contract_family, source_blob_id, source_blob_sha256,
                       byte_size, initial_metadata_revision_id,
                       superseded_document_id, payload_json, payload_sha256
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    document.document_id,
                    document.lineage.formal_lifecycle_id,
                    document.schema_version,
                    document.contract_family,
                    document.source_blob_id,
                    document.source_blob_sha256,
                    document.byte_size,
                    document.initial_metadata_revision_id,
                    None
                    if document.superseded_document is None
                    else document.superseded_document.document_id,
                    document_json,
                    document_sha,
                ),
            )

        record, replayed = self._write_idempotently(
            lineage=document.lineage,
            request=request,
            operation_type="STORE_DOCUMENT",
            target_identity=document.document_id,
            result_schema_version=document.schema_version,
            result_identity=document.document_id,
            result_payload_sha256=document_sha,
            operation_payload_sha256=operation_sha,
            writer=writer,
        )
        return FormalEvidenceWriteResult(record=record, replayed=replayed)  # type: ignore[arg-type]

    def record_document_reuse(
        self,
        document: SupportingDocument,
        *,
        request: RequestIdentity,
    ) -> FormalEvidenceWriteResult[SupportingDocument]:
        """Bind a new exact request token to an existing same-lineage document."""

        _, payload_sha = serialize_formal_evidence_record(document)

        def writer(connection: sqlite3.Connection) -> None:
            stored = self._load_record(
                connection, document.schema_version, document.document_id
            )
            if stored != document:
                raise FormalEvidenceIntegrityError(
                    "Reused supporting document does not match immutable history"
                )

        record, replayed = self._write_idempotently(
            lineage=document.lineage,
            request=request,
            operation_type="STORE_DOCUMENT",
            target_identity=document.document_id,
            result_schema_version=document.schema_version,
            result_identity=document.document_id,
            result_payload_sha256=payload_sha,
            operation_payload_sha256=self._operation_payload_sha256(
                (payload_sha, request.canonical_request_sha256)
            ),
            writer=writer,
        )
        return FormalEvidenceWriteResult(record=record, replayed=replayed)  # type: ignore[arg-type]

    def store_document(
        self,
        document: SupportingDocument,
        initial_metadata: SupportingDocumentMetadataRevision,
        *,
        request: RequestIdentity,
    ) -> FormalEvidenceWriteResult[SupportingDocument]:
        if document.lineage != initial_metadata.lineage:
            raise FormalEvidenceLineageError("Document and metadata lineage must match")
        if initial_metadata.document_id != document.document_id:
            raise FormalEvidenceIntegrityError("Initial metadata document is inconsistent")
        if initial_metadata.revision_id != document.initial_metadata_revision_id:
            raise FormalEvidenceIntegrityError("Initial metadata identity is inconsistent")
        if initial_metadata.revision_number != 1 or initial_metadata.prior_revision_id:
            raise FormalEvidenceIntegrityError("Initial metadata must be revision 1")
        if initial_metadata.request != request:
            raise FormalEvidenceIdempotencyError(
                "Document operation request must match initial metadata request"
            )
        document_json, document_sha = serialize_formal_evidence_record(document)
        metadata_json, metadata_sha = serialize_formal_evidence_record(initial_metadata)
        operation_sha = self._operation_payload_sha256((document_sha, metadata_sha))

        def writer(connection: sqlite3.Connection) -> None:
            if document.superseded_document is not None:
                previous = self._load_record(
                    connection,
                    document.schema_version,
                    document.superseded_document.document_id,
                )
                if not isinstance(previous, SupportingDocument) or (
                    previous.lineage != document.lineage
                    or previous.source_blob_sha256
                    != document.superseded_document.content_sha256
                ):
                    raise FormalEvidenceLineageError(
                        "Superseded document reference does not match persisted history"
                    )
            connection.execute(
                """INSERT INTO preliminary_supporting_document_metadata_revisions(
                       revision_id, formal_lifecycle_id, document_id,
                       schema_version, contract_family, revision_number,
                       prior_revision_id, request_token, payload_json, payload_sha256
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    initial_metadata.revision_id,
                    document.lineage.formal_lifecycle_id,
                    document.document_id,
                    initial_metadata.schema_version,
                    initial_metadata.contract_family,
                    initial_metadata.revision_number,
                    initial_metadata.prior_revision_id,
                    request.request_token,
                    metadata_json,
                    metadata_sha,
                ),
            )
            connection.execute(
                """INSERT INTO preliminary_supporting_documents(
                       document_id, formal_lifecycle_id, schema_version,
                       contract_family, source_blob_id, source_blob_sha256,
                       byte_size, initial_metadata_revision_id,
                       superseded_document_id, payload_json, payload_sha256
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    document.document_id,
                    document.lineage.formal_lifecycle_id,
                    document.schema_version,
                    document.contract_family,
                    document.source_blob_id,
                    document.source_blob_sha256,
                    document.byte_size,
                    document.initial_metadata_revision_id,
                    None
                    if document.superseded_document is None
                    else document.superseded_document.document_id,
                    document_json,
                    document_sha,
                ),
            )

        record, replayed = self._write_idempotently(
            lineage=document.lineage,
            request=request,
            operation_type="STORE_DOCUMENT",
            target_identity=document.document_id,
            result_schema_version=document.schema_version,
            result_identity=document.document_id,
            result_payload_sha256=document_sha,
            operation_payload_sha256=operation_sha,
            writer=writer,
        )
        return FormalEvidenceWriteResult(record=record, replayed=replayed)  # type: ignore[arg-type]

    def append_metadata_revision(
        self, revision: SupportingDocumentMetadataRevision
    ) -> FormalEvidenceWriteResult[SupportingDocumentMetadataRevision]:
        payload_json, payload_sha = serialize_formal_evidence_record(revision)

        def writer(connection: sqlite3.Connection) -> None:
            latest = connection.execute(
                """SELECT revision_id, revision_number
                   FROM preliminary_supporting_document_metadata_revisions
                   WHERE formal_lifecycle_id = ? AND document_id = ?
                   ORDER BY revision_number DESC LIMIT 1""",
                (revision.lineage.formal_lifecycle_id, revision.document_id),
            ).fetchone()
            if latest is None or (
                revision.prior_revision_id != latest["revision_id"]
                or revision.revision_number != latest["revision_number"] + 1
            ):
                raise FormalEvidenceStaleWriteError(
                    "Metadata append does not extend the current revision"
                )
            connection.execute(
                """INSERT INTO preliminary_supporting_document_metadata_revisions(
                       revision_id, formal_lifecycle_id, document_id,
                       schema_version, contract_family, revision_number,
                       prior_revision_id, request_token, payload_json, payload_sha256
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    revision.revision_id,
                    revision.lineage.formal_lifecycle_id,
                    revision.document_id,
                    revision.schema_version,
                    revision.contract_family,
                    revision.revision_number,
                    revision.prior_revision_id,
                    revision.request.request_token,
                    payload_json,
                    payload_sha,
                ),
            )

        record, replayed = self._write_idempotently(
            lineage=revision.lineage,
            request=revision.request,
            operation_type="APPEND_METADATA_REVISION",
            target_identity=revision.revision_id,
            result_schema_version=revision.schema_version,
            result_identity=revision.revision_id,
            result_payload_sha256=payload_sha,
            operation_payload_sha256=self._operation_payload_sha256((payload_sha,)),
            writer=writer,
        )
        return FormalEvidenceWriteResult(record=record, replayed=replayed)  # type: ignore[arg-type]

    @staticmethod
    def _require_document(
        connection: sqlite3.Connection,
        *,
        formal_lifecycle_id: str,
        document_id: str,
        content_sha256: str | None = None,
    ) -> sqlite3.Row:
        row = connection.execute(
            """SELECT * FROM preliminary_supporting_documents
               WHERE formal_lifecycle_id = ? AND document_id = ?""",
            (formal_lifecycle_id, document_id),
        ).fetchone()
        if row is None:
            raise FormalEvidenceIntegrityError(
                "Supporting record references an unknown same-lineage document"
            )
        if content_sha256 is not None and row["source_blob_sha256"] != content_sha256:
            raise FormalEvidenceIntegrityError(
                "Supporting record document hash does not match persisted bytes"
            )
        return row

    def store_provider_consent(
        self,
        consent: ExternalProviderConsent,
        *,
        request: RequestIdentity,
    ) -> FormalEvidenceWriteResult[ExternalProviderConsent]:
        payload_json, payload_sha = serialize_formal_evidence_record(consent)
        record_id = "|".join(
            (
                consent.document_id,
                consent.provider_id,
                consent.declared_at.isoformat(),
            )
        )

        def writer(connection: sqlite3.Connection) -> None:
            self._require_document(
                connection,
                formal_lifecycle_id=consent.lineage.formal_lifecycle_id,
                document_id=consent.document_id,
            )
            connection.execute(
                """INSERT INTO preliminary_supporting_provider_consents(
                       consent_record_id, formal_lifecycle_id, document_id,
                       schema_version, contract_family, provider_id,
                       explicit_consent, payload_json, payload_sha256
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record_id,
                    consent.lineage.formal_lifecycle_id,
                    consent.document_id,
                    consent.schema_version,
                    consent.contract_family,
                    consent.provider_id,
                    int(consent.explicit_consent),
                    payload_json,
                    payload_sha,
                ),
            )

        record, replayed = self._write_idempotently(
            lineage=consent.lineage,
            request=request,
            operation_type="STORE_PROVIDER_CONSENT",
            target_identity=record_id,
            result_schema_version=consent.schema_version,
            result_identity=record_id,
            result_payload_sha256=payload_sha,
            operation_payload_sha256=self._operation_payload_sha256((payload_sha,)),
            writer=writer,
        )
        return FormalEvidenceWriteResult(record=record, replayed=replayed)  # type: ignore[arg-type]

    def append_ingestion_attempt(
        self,
        attempt: SupportingDocumentIngestionAttempt,
        *,
        terminal_event: FormalEvidenceWorkflowEvent | None = None,
    ) -> FormalEvidenceWriteResult[SupportingDocumentIngestionAttempt]:
        payload_json, payload_sha = serialize_formal_evidence_record(attempt)
        event_payload: tuple[str, str] | None = None
        if terminal_event is not None:
            if (
                terminal_event.lineage != attempt.lineage
                or terminal_event.subject_id != attempt.attempt_id
                or terminal_event.payload_sha256 != payload_sha
            ):
                raise FormalEvidenceIntegrityError(
                    "Ingestion terminal event does not match its immutable attempt"
                )
            event_payload = serialize_formal_evidence_record(terminal_event)

        def writer(connection: sqlite3.Connection) -> None:
            self._require_document(
                connection,
                formal_lifecycle_id=attempt.lineage.formal_lifecycle_id,
                document_id=attempt.document_id,
                content_sha256=attempt.document_content_sha256,
            )
            latest = connection.execute(
                """SELECT attempt_id, attempt_number, status
                   FROM preliminary_supporting_ingestion_attempts
                   WHERE formal_lifecycle_id = ? AND document_id = ?
                   ORDER BY attempt_number DESC LIMIT 1""",
                (attempt.lineage.formal_lifecycle_id, attempt.document_id),
            ).fetchone()
            if attempt.attempt_number == 1:
                if latest is not None:
                    raise FormalEvidenceStaleWriteError(
                        "Initial ingestion attempt already exists"
                    )
            elif latest is None or (
                attempt.predecessor_attempt_id != latest["attempt_id"]
                or attempt.attempt_number != latest["attempt_number"] + 1
                or latest["status"] == AttemptStatus.STARTED.value
            ):
                raise FormalEvidenceStaleWriteError(
                    "Ingestion retry does not extend the exact terminal predecessor"
                )
            connection.execute(
                """INSERT INTO preliminary_supporting_ingestion_attempts(
                       attempt_id, formal_lifecycle_id, document_id,
                       document_content_sha256, schema_version, contract_family,
                       attempt_number, predecessor_attempt_id, status,
                       request_token, payload_json, payload_sha256
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    attempt.attempt_id,
                    attempt.lineage.formal_lifecycle_id,
                    attempt.document_id,
                    attempt.document_content_sha256,
                    attempt.schema_version,
                    attempt.contract_family,
                    attempt.attempt_number,
                    attempt.predecessor_attempt_id,
                    attempt.status.value,
                    attempt.request.request_token,
                    payload_json,
                    payload_sha,
                ),
            )
            if terminal_event is not None and event_payload is not None:
                self._insert_workflow_event(
                    connection,
                    terminal_event,
                    payload_json=event_payload[0],
                    payload_sha=event_payload[1],
                )

        record, replayed = self._write_idempotently(
            lineage=attempt.lineage,
            request=attempt.request,
            operation_type="APPEND_INGESTION_ATTEMPT",
            target_identity=attempt.attempt_id,
            result_schema_version=attempt.schema_version,
            result_identity=attempt.attempt_id,
            result_payload_sha256=payload_sha,
            operation_payload_sha256=self._operation_payload_sha256(
                (
                    payload_sha,
                    *(() if event_payload is None else (event_payload[1],)),
                )
            ),
            writer=writer,
        )
        return FormalEvidenceWriteResult(record=record, replayed=replayed)  # type: ignore[arg-type]

    def store_extraction_bundle(
        self,
        attempt: SupportingEvidenceExtractionAttempt,
        proposals: Iterable[SupportingEvidenceProposal],
        *,
        terminal_event: FormalEvidenceWorkflowEvent | None = None,
    ) -> FormalEvidenceWriteResult[SupportingEvidenceExtractionAttempt]:
        proposal_tuple = tuple(proposals)
        proposal_ids = tuple(item.proposal_id for item in proposal_tuple)
        if proposal_ids != attempt.proposal_ids:
            raise FormalEvidenceIntegrityError(
                "Extraction bundle proposals must exactly match the attempt order"
            )
        for proposal in proposal_tuple:
            if (
                proposal.lineage != attempt.lineage
                or proposal.extraction_attempt_id != attempt.attempt_id
                or proposal.document_id != attempt.document_id
                or proposal.document_content_sha256
                != attempt.document_content_sha256
            ):
                raise FormalEvidenceLineageError(
                    "Extraction proposal does not match its attempt lineage"
                )
        attempt_json, attempt_sha = serialize_formal_evidence_record(attempt)
        proposal_payloads = [
            (*serialize_formal_evidence_record(item), item) for item in proposal_tuple
        ]
        event_payload: tuple[str, str] | None = None
        if terminal_event is not None:
            if (
                terminal_event.lineage != attempt.lineage
                or terminal_event.subject_id != attempt.attempt_id
                or terminal_event.payload_sha256 != attempt_sha
            ):
                raise FormalEvidenceIntegrityError(
                    "Extraction terminal event does not match its immutable attempt"
                )
            event_payload = serialize_formal_evidence_record(terminal_event)
        operation_sha = self._operation_payload_sha256(
            (
                attempt_sha,
                *(payload[1] for payload in proposal_payloads),
                *(() if event_payload is None else (event_payload[1],)),
            )
        )

        def writer(connection: sqlite3.Connection) -> None:
            self._require_document(
                connection,
                formal_lifecycle_id=attempt.lineage.formal_lifecycle_id,
                document_id=attempt.document_id,
                content_sha256=attempt.document_content_sha256,
            )
            ingestion = connection.execute(
                """SELECT formal_lifecycle_id, document_id,
                          document_content_sha256, status
                   FROM preliminary_supporting_ingestion_attempts
                   WHERE attempt_id = ?""",
                (attempt.ingestion_attempt_id,),
            ).fetchone()
            if ingestion is None or tuple(ingestion[:3]) != (
                attempt.lineage.formal_lifecycle_id,
                attempt.document_id,
                attempt.document_content_sha256,
            ) or ingestion["status"] not in {
                AttemptStatus.SUCCEEDED.value,
                AttemptStatus.PARTIAL.value,
            }:
                raise FormalEvidenceIntegrityError(
                    "Extraction requires matching terminal parsed ingestion"
                )
            latest = connection.execute(
                """SELECT attempt_id, attempt_number, status
                   FROM preliminary_supporting_extraction_attempts
                   WHERE formal_lifecycle_id = ? AND document_id = ?
                   ORDER BY attempt_number DESC LIMIT 1""",
                (attempt.lineage.formal_lifecycle_id, attempt.document_id),
            ).fetchone()
            if attempt.attempt_number == 1:
                if latest is not None:
                    raise FormalEvidenceStaleWriteError(
                        "Initial extraction attempt already exists"
                    )
            elif latest is None or (
                attempt.predecessor_attempt_id != latest["attempt_id"]
                or attempt.attempt_number != latest["attempt_number"] + 1
                or latest["status"] == AttemptStatus.STARTED.value
            ):
                raise FormalEvidenceStaleWriteError(
                    "Extraction retry does not extend the exact terminal predecessor"
                )
            for proposal_json, proposal_sha, proposal in proposal_payloads:
                connection.execute(
                    """INSERT INTO preliminary_supporting_evidence_proposals(
                           proposal_id, formal_lifecycle_id,
                           extraction_attempt_id, document_id,
                           document_content_sha256, schema_version,
                           contract_family, payload_json, payload_sha256
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        proposal.proposal_id,
                        proposal.lineage.formal_lifecycle_id,
                        proposal.extraction_attempt_id,
                        proposal.document_id,
                        proposal.document_content_sha256,
                        proposal.schema_version,
                        proposal.contract_family,
                        proposal_json,
                        proposal_sha,
                    ),
                )
            connection.execute(
                """INSERT INTO preliminary_supporting_extraction_attempts(
                       attempt_id, formal_lifecycle_id, document_id,
                       document_content_sha256, ingestion_attempt_id,
                       schema_version, contract_family, attempt_number,
                       predecessor_attempt_id, status, request_token,
                       payload_json, payload_sha256
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    attempt.attempt_id,
                    attempt.lineage.formal_lifecycle_id,
                    attempt.document_id,
                    attempt.document_content_sha256,
                    attempt.ingestion_attempt_id,
                    attempt.schema_version,
                    attempt.contract_family,
                    attempt.attempt_number,
                    attempt.predecessor_attempt_id,
                    attempt.status.value,
                    attempt.request.request_token,
                    attempt_json,
                    attempt_sha,
                ),
            )
            if terminal_event is not None and event_payload is not None:
                self._insert_workflow_event(
                    connection,
                    terminal_event,
                    payload_json=event_payload[0],
                    payload_sha=event_payload[1],
                )

        record, replayed = self._write_idempotently(
            lineage=attempt.lineage,
            request=attempt.request,
            operation_type="STORE_EXTRACTION_BUNDLE",
            target_identity=attempt.attempt_id,
            result_schema_version=attempt.schema_version,
            result_identity=attempt.attempt_id,
            result_payload_sha256=attempt_sha,
            operation_payload_sha256=operation_sha,
            writer=writer,
        )
        return FormalEvidenceWriteResult(record=record, replayed=replayed)  # type: ignore[arg-type]

    def _require_review_reference(
        self,
        connection: sqlite3.Connection,
        reference: ReviewedEvidenceReference,
    ) -> SupportingEvidenceReviewRevision:
        stored = self._load_record(
            connection,
            "supporting-evidence-review-revision.v0.1",
            reference.review_revision_id,
        )
        if not isinstance(stored, SupportingEvidenceReviewRevision):
            raise FormalEvidenceIntegrityError("Stored review type is invalid")
        expected = ReviewedEvidenceReference(
            lineage=stored.lineage,
            review_revision_id=stored.revision_id,
            proposal_id=stored.proposal_id,
            action=stored.action,
            classification=stored.approved_classification,
        )
        if expected != reference:
            raise FormalEvidenceIntegrityError(
                "Reviewed evidence reference does not match immutable history"
            )
        latest = connection.execute(
            """SELECT revision_id
               FROM preliminary_supporting_evidence_review_revisions
               WHERE formal_lifecycle_id = ? AND proposal_id = ?
               ORDER BY revision_number DESC LIMIT 1""",
            (stored.lineage.formal_lifecycle_id, stored.proposal_id),
        ).fetchone()
        if latest is None or latest["revision_id"] != stored.revision_id:
            raise FormalEvidenceStaleWriteError(
                "Reviewed evidence reference is not the current revision"
            )
        self._require_current_proposal(connection, stored.original_proposal)
        return stored

    @staticmethod
    def _require_current_proposal(
        connection: sqlite3.Connection,
        proposal: SupportingEvidenceProposal,
    ) -> None:
        row = connection.execute(
            """SELECT proposal.formal_lifecycle_id,
                      proposal.extraction_attempt_id, proposal.document_id,
                      proposal.document_content_sha256
               FROM preliminary_supporting_evidence_proposals proposal
               JOIN preliminary_supporting_extraction_attempts extraction
                 ON extraction.attempt_id = proposal.extraction_attempt_id
               JOIN preliminary_supporting_documents document
                 ON document.document_id = proposal.document_id
               WHERE proposal.proposal_id = ?
                 AND extraction.status IN ('SUCCEEDED', 'PARTIAL')
                 AND NOT EXISTS (
                     SELECT 1 FROM preliminary_supporting_documents newer_document
                     WHERE newer_document.formal_lifecycle_id = document.formal_lifecycle_id
                       AND newer_document.superseded_document_id = document.document_id
                 )
                 AND NOT EXISTS (
                     SELECT 1 FROM preliminary_supporting_extraction_attempts newer_extraction
                     WHERE newer_extraction.formal_lifecycle_id = extraction.formal_lifecycle_id
                       AND newer_extraction.document_id = extraction.document_id
                       AND newer_extraction.attempt_number > extraction.attempt_number
                       AND newer_extraction.status IN ('SUCCEEDED', 'PARTIAL')
                 )""",
            (proposal.proposal_id,),
        ).fetchone()
        expected = (
            proposal.lineage.formal_lifecycle_id,
            proposal.extraction_attempt_id,
            proposal.document_id,
            proposal.document_content_sha256,
        )
        if row is None or tuple(row) != expected:
            raise FormalEvidenceStaleWriteError(
                "Review proposal is no longer current for its document"
            )

    def append_review_revision(
        self,
        revision: SupportingEvidenceReviewRevision,
        *,
        terminal_event: FormalEvidenceWorkflowEvent | None = None,
    ) -> FormalEvidenceWriteResult[SupportingEvidenceReviewRevision]:
        payload_json, payload_sha = serialize_formal_evidence_record(revision)
        event_payload: tuple[str, str] | None = None
        if terminal_event is not None:
            if (
                terminal_event.lineage != revision.lineage
                or terminal_event.subject_id != revision.revision_id
                or terminal_event.payload_sha256 != payload_sha
            ):
                raise FormalEvidenceIntegrityError(
                    "Review terminal event does not match its immutable revision"
                )
            event_payload = serialize_formal_evidence_record(terminal_event)

        def writer(connection: sqlite3.Connection) -> None:
            proposal = self._load_record(
                connection,
                "supporting-evidence-proposal.v0.1",
                revision.proposal_id,
            )
            if proposal != revision.original_proposal:
                raise FormalEvidenceIntegrityError(
                    "Review must preserve the exact persisted original proposal"
                )
            self._require_current_proposal(connection, proposal)
            latest = connection.execute(
                """SELECT revision_id, revision_number
                   FROM preliminary_supporting_evidence_review_revisions
                   WHERE formal_lifecycle_id = ? AND proposal_id = ?
                   ORDER BY revision_number DESC LIMIT 1""",
                (revision.lineage.formal_lifecycle_id, revision.proposal_id),
            ).fetchone()
            if revision.revision_number == 1:
                if latest is not None or revision.expected_prior_revision_id is not None:
                    raise FormalEvidenceStaleWriteError(
                        "Initial review revision already exists"
                    )
            elif latest is None or (
                revision.prior_revision_id != latest["revision_id"]
                or revision.expected_prior_revision_id != latest["revision_id"]
                or revision.revision_number != latest["revision_number"] + 1
            ):
                raise FormalEvidenceStaleWriteError(
                    "Review append does not extend the expected current revision"
                )
            for reference in revision.inference_documented_facts:
                stored = self._require_review_reference(connection, reference)
                if (
                    stored.action not in {ReviewAction.ACCEPT, ReviewAction.CORRECT}
                    or stored.approved_classification
                    is not EvidenceClassification.DOCUMENTED_FACT
                ):
                    raise FormalEvidenceIntegrityError(
                        "Reviewed inference fact link is not an approved documented fact"
                    )
            for reference in revision.competing_evidence:
                stored = self._require_review_reference(connection, reference)
                if stored.action not in {ReviewAction.ACCEPT, ReviewAction.CORRECT}:
                    raise FormalEvidenceIntegrityError(
                        "Conflict links must reference accepted or corrected evidence"
                    )
            connection.execute(
                """INSERT INTO preliminary_supporting_evidence_review_revisions(
                       revision_id, formal_lifecycle_id, proposal_id,
                       schema_version, contract_family, revision_number,
                       prior_revision_id, action, approved_classification,
                       request_token, payload_json, payload_sha256
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    revision.revision_id,
                    revision.lineage.formal_lifecycle_id,
                    revision.proposal_id,
                    revision.schema_version,
                    revision.contract_family,
                    revision.revision_number,
                    revision.prior_revision_id,
                    revision.action.value,
                    None
                    if revision.approved_classification is None
                    else revision.approved_classification.value,
                    revision.request.request_token,
                    payload_json,
                    payload_sha,
                ),
            )
            if terminal_event is not None and event_payload is not None:
                self._insert_workflow_event(
                    connection,
                    terminal_event,
                    payload_json=event_payload[0],
                    payload_sha=event_payload[1],
                )

        record, replayed = self._write_idempotently(
            lineage=revision.lineage,
            request=revision.request,
            operation_type="APPEND_REVIEW_REVISION",
            target_identity=revision.revision_id,
            result_schema_version=revision.schema_version,
            result_identity=revision.revision_id,
            result_payload_sha256=payload_sha,
            operation_payload_sha256=self._operation_payload_sha256(
                (
                    payload_sha,
                    *(() if event_payload is None else (event_payload[1],)),
                )
            ),
            writer=writer,
        )
        return FormalEvidenceWriteResult(record=record, replayed=replayed)  # type: ignore[arg-type]

    def append_context_note(
        self,
        note: ContextNote,
        *,
        terminal_event: FormalEvidenceWorkflowEvent | None = None,
    ) -> FormalEvidenceWriteResult[ContextNote]:
        payload_json, payload_sha = serialize_formal_evidence_record(note)
        event_payload: tuple[str, str] | None = None
        if terminal_event is not None:
            if (
                terminal_event.lineage != note.lineage
                or terminal_event.subject_id != note.context_note_id
                or terminal_event.payload_sha256 != payload_sha
            ):
                raise FormalEvidenceIntegrityError(
                    "Context-note event does not match its immutable note"
                )
            event_payload = serialize_formal_evidence_record(terminal_event)

        def writer(connection: sqlite3.Connection) -> None:
            connection.execute(
                """INSERT INTO preliminary_supporting_context_notes(
                       context_note_id, formal_lifecycle_id, schema_version,
                       contract_family, request_token, payload_json, payload_sha256
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    note.context_note_id,
                    note.lineage.formal_lifecycle_id,
                    note.schema_version,
                    note.contract_family,
                    note.request.request_token,
                    payload_json,
                    payload_sha,
                ),
            )
            if terminal_event is not None and event_payload is not None:
                self._insert_workflow_event(
                    connection,
                    terminal_event,
                    payload_json=event_payload[0],
                    payload_sha=event_payload[1],
                )

        record, replayed = self._write_idempotently(
            lineage=note.lineage,
            request=note.request,
            operation_type="APPEND_CONTEXT_NOTE",
            target_identity=note.context_note_id,
            result_schema_version=note.schema_version,
            result_identity=note.context_note_id,
            result_payload_sha256=payload_sha,
            operation_payload_sha256=self._operation_payload_sha256(
                (
                    payload_sha,
                    *(() if event_payload is None else (event_payload[1],)),
                )
            ),
            writer=writer,
        )
        return FormalEvidenceWriteResult(record=record, replayed=replayed)  # type: ignore[arg-type]

    @staticmethod
    def _approved_activity_ids(
        connection: sqlite3.Connection,
        lineage: FormalEvidenceLineage,
    ) -> set[str]:
        row = connection.execute(
            """SELECT payload_json FROM assessment_artifacts
               WHERE artifact_id = ? AND assessment_id = ?
                 AND artifact_schema_version = ? AND artifact_revision = ?
                 AND payload_sha256 = ?""",
            (
                lineage.approved_review_artifact_id,
                lineage.source_assessment_id,
                lineage.approved_review_schema_version,
                lineage.approved_review_revision,
                lineage.approved_review_payload_sha256,
            ),
        ).fetchone()
        if row is None:
            raise FormalEvidenceLineageError(
                "Approved process artifact no longer matches formal lineage"
            )
        try:
            payload = json.loads(row[0])
            return {
                step["step_id"] for step in payload["business_process"]["steps"]
            }
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ArtifactCorruptionError(
                "Approved process activity lineage is corrupt"
            ) from exc

    def append_formal_mapping(
        self,
        mapping: FormalInputMapping,
        *,
        expected_prior_mapping_id: str | None = None,
        terminal_event: FormalEvidenceWorkflowEvent | None = None,
    ) -> FormalEvidenceWriteResult[FormalInputMapping]:
        payload_json, payload_sha = serialize_formal_evidence_record(mapping)
        event_payload: tuple[str, str] | None = None
        if terminal_event is not None:
            if (
                terminal_event.lineage != mapping.lineage
                or terminal_event.subject_id != mapping.mapping_id
                or terminal_event.payload_sha256 != payload_sha
            ):
                raise FormalEvidenceIntegrityError(
                    "Formal-mapping event does not match its immutable mapping"
                )
            event_payload = serialize_formal_evidence_record(terminal_event)

        def writer(connection: sqlite3.Connection) -> None:
            if mapping.activity_id not in self._approved_activity_ids(
                connection, mapping.lineage
            ):
                raise FormalEvidenceIntegrityError(
                    "Formal mapping activity is not in the exact approved process"
                )
            for reference in mapping.supporting_reviews:
                stored = self._require_review_reference(connection, reference)
                if stored.action is ReviewAction.REJECT:
                    raise FormalEvidenceIntegrityError(
                        "Rejected review cannot support a formal mapping"
                    )
            for revision_id in mapping.supporting_documented_fact_review_ids:
                stored = self._load_record(
                    connection,
                    "supporting-evidence-review-revision.v0.1",
                    revision_id,
                )
                if not isinstance(stored, SupportingEvidenceReviewRevision) or (
                    stored.lineage != mapping.lineage
                    or stored.action
                    not in {ReviewAction.ACCEPT, ReviewAction.CORRECT}
                    or stored.approved_classification
                    is not EvidenceClassification.DOCUMENTED_FACT
                ):
                    raise FormalEvidenceIntegrityError(
                        "Mapping fact support is not an approved same-lineage fact"
                    )
                self._require_review_reference(
                    connection,
                    ReviewedEvidenceReference(
                        lineage=stored.lineage,
                        review_revision_id=stored.revision_id,
                        proposal_id=stored.proposal_id,
                        action=stored.action,
                        classification=stored.approved_classification,
                    ),
                )
            if len(mapping.supporting_reviews) != 1:
                raise FormalEvidenceIntegrityError(
                    "A formal mapping must identify exactly one primary reviewed item"
                )
            primary_revision_id = mapping.supporting_reviews[0].review_revision_id
            latest_mapping = connection.execute(
                """SELECT mapping_id
                   FROM preliminary_supporting_formal_input_mappings
                   WHERE formal_lifecycle_id = ?
                     AND json_extract(
                         payload_json,
                         '$.supporting_reviews[0].review_revision_id'
                     ) = ?
                   ORDER BY rowid DESC LIMIT 1""",
                (
                    mapping.lineage.formal_lifecycle_id,
                    primary_revision_id,
                ),
            ).fetchone()
            actual_prior_mapping_id = (
                None if latest_mapping is None else latest_mapping["mapping_id"]
            )
            if actual_prior_mapping_id != expected_prior_mapping_id:
                raise FormalEvidenceStaleWriteError(
                    "Formal mapping does not extend the expected current mapping"
                )
            connection.execute(
                """INSERT INTO preliminary_supporting_formal_input_mappings(
                       mapping_id, formal_lifecycle_id, schema_version,
                       contract_family, activity_id, disposition,
                       request_token, payload_json, payload_sha256
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    mapping.mapping_id,
                    mapping.lineage.formal_lifecycle_id,
                    mapping.schema_version,
                    mapping.contract_family,
                    mapping.activity_id,
                    mapping.disposition.value,
                    mapping.request.request_token,
                    payload_json,
                    payload_sha,
                ),
            )
            if terminal_event is not None and event_payload is not None:
                self._insert_workflow_event(
                    connection,
                    terminal_event,
                    payload_json=event_payload[0],
                    payload_sha=event_payload[1],
                )

        record, replayed = self._write_idempotently(
            lineage=mapping.lineage,
            request=mapping.request,
            operation_type="APPEND_FORMAL_MAPPING",
            target_identity=mapping.mapping_id,
            result_schema_version=mapping.schema_version,
            result_identity=mapping.mapping_id,
            result_payload_sha256=payload_sha,
            operation_payload_sha256=self._operation_payload_sha256(
                (
                    payload_sha,
                    *(() if event_payload is None else (event_payload[1],)),
                )
            ),
            writer=writer,
        )
        return FormalEvidenceWriteResult(record=record, replayed=replayed)  # type: ignore[arg-type]

    def _validate_candidate_snapshot(
        self,
        connection: sqlite3.Connection,
        candidate: FormalInputCandidateSet,
    ) -> None:
        lifecycle_id = candidate.lineage.formal_lifecycle_id
        current_rows = connection.execute(
            """SELECT document_id, source_blob_sha256, byte_size
               FROM preliminary_supporting_documents current
               WHERE formal_lifecycle_id = ?
                 AND NOT EXISTS (
                     SELECT 1 FROM preliminary_supporting_documents newer
                     WHERE newer.formal_lifecycle_id = current.formal_lifecycle_id
                       AND newer.superseded_document_id = current.document_id
                 )""",
            (lifecycle_id,),
        ).fetchall()
        persisted_documents: dict[str, tuple[str, int, str]] = {}
        for row in current_rows:
            metadata = connection.execute(
                """SELECT revision_id
                   FROM preliminary_supporting_document_metadata_revisions
                   WHERE formal_lifecycle_id = ? AND document_id = ?
                   ORDER BY revision_number DESC LIMIT 1""",
                (lifecycle_id, row["document_id"]),
            ).fetchone()
            if metadata is None:
                raise ArtifactCorruptionError(
                    "Current supporting document has no metadata history"
                )
            persisted_documents[row["document_id"]] = (
                row["source_blob_sha256"],
                row["byte_size"],
                metadata["revision_id"],
            )
        expected_documents = {
            item.document_id: (
                item.content_sha256,
                item.byte_size,
                item.metadata_revision_id,
            )
            for item in candidate.current_documents
        }
        if persisted_documents != expected_documents:
            raise FormalEvidenceStaleWriteError(
                "Candidate documents do not match the current immutable snapshot"
            )

        persisted_extractions: dict[str, tuple[str, str, tuple[str, ...]]] = {}
        for document_id in persisted_documents:
            row = connection.execute(
                """SELECT schema_version, payload_json, payload_sha256
                   FROM preliminary_supporting_extraction_attempts
                   WHERE formal_lifecycle_id = ? AND document_id = ?
                   ORDER BY attempt_number DESC LIMIT 1""",
                (lifecycle_id, document_id),
            ).fetchone()
            if row is None:
                continue
            attempt = deserialize_formal_evidence_record(
                row["schema_version"], row["payload_json"], row["payload_sha256"]
            )
            if not isinstance(attempt, SupportingEvidenceExtractionAttempt):
                raise ArtifactCorruptionError("Current extraction type is invalid")
            persisted_extractions[attempt.attempt_id] = (
                attempt.document_id,
                attempt.status.value,
                attempt.proposal_ids,
            )
        expected_extractions = {
            item.extraction_attempt_id: (
                item.document_id,
                item.status.value,
                item.proposal_ids,
            )
            for item in candidate.current_extractions
        }
        if persisted_extractions != expected_extractions:
            raise FormalEvidenceStaleWriteError(
                "Candidate extractions do not match the current immutable snapshot"
            )

        current_proposal_ids = {
            proposal_id
            for item in candidate.current_extractions
            for proposal_id in item.proposal_ids
        }
        persisted_reviews: dict[str, ReviewedEvidenceReference] = {}
        for proposal_id in current_proposal_ids:
            row = connection.execute(
                """SELECT schema_version, payload_json, payload_sha256
                   FROM preliminary_supporting_evidence_review_revisions
                   WHERE formal_lifecycle_id = ? AND proposal_id = ?
                   ORDER BY revision_number DESC LIMIT 1""",
                (lifecycle_id, proposal_id),
            ).fetchone()
            if row is None:
                continue
            review = deserialize_formal_evidence_record(
                row["schema_version"], row["payload_json"], row["payload_sha256"]
            )
            if not isinstance(review, SupportingEvidenceReviewRevision):
                raise ArtifactCorruptionError("Current review type is invalid")
            persisted_reviews[review.revision_id] = ReviewedEvidenceReference(
                lineage=review.lineage,
                review_revision_id=review.revision_id,
                proposal_id=review.proposal_id,
                action=review.action,
                classification=review.approved_classification,
            )
        expected_reviews = {
            item.review_revision_id: item for item in candidate.current_reviews
        }
        if persisted_reviews != expected_reviews:
            raise FormalEvidenceStaleWriteError(
                "Candidate reviews do not match every current review revision"
            )

        for revision_id in candidate.context_only_review_revision_ids:
            reference = persisted_reviews.get(revision_id)
            if reference is None or reference.action not in {
                ReviewAction.ACCEPT,
                ReviewAction.CORRECT,
            }:
                raise FormalEvidenceIntegrityError(
                    "Context-only candidate item must be an approved current review"
                )
            mapping_row = connection.execute(
                """SELECT mapping_id
                   FROM preliminary_supporting_formal_input_mappings
                   WHERE formal_lifecycle_id = ?
                     AND json_extract(
                         payload_json,
                         '$.supporting_reviews[0].review_revision_id'
                     ) = ?
                   ORDER BY rowid DESC LIMIT 1""",
                (lifecycle_id, revision_id),
            ).fetchone()
            if mapping_row is None:
                raise FormalEvidenceIntegrityError(
                    "Context-only candidate item has no persisted decision"
                )
            context_mapping = self._load_record(
                connection,
                "formal-input-mapping.v0.1",
                mapping_row["mapping_id"],
            )
            if (
                not isinstance(context_mapping, FormalInputMapping)
                or context_mapping.disposition is not MappingDisposition.CONTEXT_ONLY
            ):
                raise FormalEvidenceIntegrityError(
                    "Context-only candidate item is not the current mapping decision"
                )
        for revision_id in candidate.retained_unknown_review_revision_ids:
            reference = persisted_reviews.get(revision_id)
            if reference is None or (
                reference.classification is not EvidenceClassification.UNKNOWN
            ):
                raise FormalEvidenceIntegrityError(
                    "Retained unknown candidate identity has the wrong classification"
                )
        for revision_id in candidate.retained_conflict_review_revision_ids:
            reference = persisted_reviews.get(revision_id)
            if reference is None or (
                reference.classification is not EvidenceClassification.CONFLICT
            ):
                raise FormalEvidenceIntegrityError(
                    "Retained conflict candidate identity has the wrong classification"
                )

        for mapping in candidate.ordered_formal_mappings:
            stored = self._load_record(
                connection, mapping.schema_version, mapping.mapping_id
            )
            if stored != mapping:
                raise FormalEvidenceIntegrityError(
                    "Candidate mapping does not match immutable persisted mapping"
                )
            if len(mapping.supporting_reviews) != 1:
                raise FormalEvidenceIntegrityError(
                    "Candidate mapping must identify one primary reviewed item"
                )
            latest_mapping = connection.execute(
                """SELECT mapping_id
                   FROM preliminary_supporting_formal_input_mappings
                   WHERE formal_lifecycle_id = ?
                     AND json_extract(
                         payload_json,
                         '$.supporting_reviews[0].review_revision_id'
                     ) = ?
                   ORDER BY rowid DESC LIMIT 1""",
                (
                    lifecycle_id,
                    mapping.supporting_reviews[0].review_revision_id,
                ),
            ).fetchone()
            if latest_mapping is None or latest_mapping["mapping_id"] != mapping.mapping_id:
                raise FormalEvidenceStaleWriteError(
                    "Candidate mapping is no longer the current mapping"
                )
        for excluded in candidate.rejected_or_excluded_proposals:
            stored = self._load_record(
                connection, "supporting-evidence-proposal.v0.1", excluded.proposal_id
            )
            if not isinstance(stored, SupportingEvidenceProposal) or (
                stored.lineage != candidate.lineage
            ):
                raise FormalEvidenceLineageError(
                    "Candidate exclusion is not a same-lineage proposal"
                )
            current_review = next(
                (
                    item
                    for item in candidate.current_reviews
                    if item.proposal_id == excluded.proposal_id
                ),
                None,
            )
            explicitly_excluded = (
                stored.document_id in candidate.explicitly_excluded_document_ids
            )
            rejected_by_review = (
                current_review is not None
                and current_review.action is ReviewAction.REJECT
            )
            if not explicitly_excluded and not rejected_by_review:
                raise FormalEvidenceIntegrityError(
                    "Candidate proposal exclusions require rejection or explicit document exclusion"
                )
        if candidate.prior_candidate_set_id is not None:
            prior = self._load_record(
                connection,
                candidate.schema_version,
                candidate.prior_candidate_set_id,
            )
            if not isinstance(prior, FormalInputCandidateSet) or (
                prior.lineage != candidate.lineage
            ):
                raise FormalEvidenceLineageError(
                    "Candidate predecessor does not share exact formal lineage"
                )

    def validate_candidate_current(
        self, candidate: FormalInputCandidateSet
    ) -> None:
        """Validate a persisted candidate against current immutable history."""

        with self._read() as connection:
            latest = connection.execute(
                """SELECT candidate_set_id
                   FROM preliminary_supporting_formal_input_candidate_sets
                   WHERE formal_lifecycle_id = ?
                   ORDER BY rowid DESC LIMIT 1""",
                (candidate.lineage.formal_lifecycle_id,),
            ).fetchone()
            if latest is None or latest["candidate_set_id"] != candidate.candidate_set_id:
                raise FormalEvidenceStaleWriteError(
                    "Candidate set is not the current immutable snapshot"
                )
            stored = self._load_record(
                connection,
                candidate.schema_version,
                candidate.candidate_set_id,
            )
            if stored != candidate:
                raise FormalEvidenceIntegrityError(
                    "Candidate set does not match immutable persisted history"
                )
            self._validate_candidate_snapshot(connection, candidate)

    def append_candidate_set(
        self,
        candidate: FormalInputCandidateSet,
        *,
        terminal_event: FormalEvidenceWorkflowEvent | None = None,
    ) -> FormalEvidenceWriteResult[FormalInputCandidateSet]:
        payload_json, payload_sha = serialize_formal_evidence_record(candidate)
        event_payload: tuple[str, str] | None = None
        if terminal_event is not None:
            if (
                terminal_event.lineage != candidate.lineage
                or terminal_event.subject_id != candidate.candidate_set_id
                or terminal_event.payload_sha256 != payload_sha
            ):
                raise FormalEvidenceIntegrityError(
                    "Candidate-set event does not match its immutable snapshot"
                )
            event_payload = serialize_formal_evidence_record(terminal_event)

        def writer(connection: sqlite3.Connection) -> None:
            latest = connection.execute(
                """SELECT candidate_set_id
                   FROM preliminary_supporting_formal_input_candidate_sets
                   WHERE formal_lifecycle_id = ?
                   ORDER BY rowid DESC LIMIT 1""",
                (candidate.lineage.formal_lifecycle_id,),
            ).fetchone()
            expected_prior = None if latest is None else latest["candidate_set_id"]
            if candidate.prior_candidate_set_id != expected_prior:
                raise FormalEvidenceStaleWriteError(
                    "Candidate set does not extend the current immutable predecessor"
                )
            self._validate_candidate_snapshot(connection, candidate)
            connection.execute(
                """INSERT INTO preliminary_supporting_formal_input_candidate_sets(
                       candidate_set_id, formal_lifecycle_id, schema_version,
                       contract_family, prior_candidate_set_id, request_token,
                       payload_json, payload_sha256
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    candidate.candidate_set_id,
                    candidate.lineage.formal_lifecycle_id,
                    candidate.schema_version,
                    candidate.contract_family,
                    candidate.prior_candidate_set_id,
                    candidate.conversion_request.request_token,
                    payload_json,
                    payload_sha,
                ),
            )
            if terminal_event is not None and event_payload is not None:
                self._insert_workflow_event(
                    connection,
                    terminal_event,
                    payload_json=event_payload[0],
                    payload_sha=event_payload[1],
                )

        record, replayed = self._write_idempotently(
            lineage=candidate.lineage,
            request=candidate.conversion_request,
            operation_type="APPEND_CANDIDATE_SET",
            target_identity=candidate.candidate_set_id,
            result_schema_version=candidate.schema_version,
            result_identity=candidate.candidate_set_id,
            result_payload_sha256=payload_sha,
            operation_payload_sha256=self._operation_payload_sha256(
                (
                    payload_sha,
                    *(() if event_payload is None else (event_payload[1],)),
                )
            ),
            writer=writer,
        )
        return FormalEvidenceWriteResult(record=record, replayed=replayed)  # type: ignore[arg-type]

    def append_readiness(
        self,
        readiness: FormalEvidenceReadiness,
        *,
        request: RequestIdentity,
        terminal_event: FormalEvidenceWorkflowEvent | None = None,
    ) -> FormalEvidenceWriteResult[FormalEvidenceReadiness]:
        payload_json, payload_sha = serialize_formal_evidence_record(readiness)
        event_payload: tuple[str, str] | None = None
        if terminal_event is not None:
            if (
                terminal_event.lineage != readiness.lineage
                or terminal_event.subject_id != readiness.readiness_id
                or terminal_event.payload_sha256 != payload_sha
            ):
                raise FormalEvidenceIntegrityError(
                    "Readiness event does not match its immutable evaluation"
                )
            event_payload = serialize_formal_evidence_record(terminal_event)

        def writer(connection: sqlite3.Connection) -> None:
            stored = self._load_record(
                connection,
                readiness.candidate_set.schema_version,
                readiness.candidate_set.candidate_set_id,
            )
            if stored != readiness.candidate_set:
                raise FormalEvidenceIntegrityError(
                    "Readiness must reference the exact persisted candidate set"
                )
            latest = connection.execute(
                """SELECT candidate_set_id
                   FROM preliminary_supporting_formal_input_candidate_sets
                   WHERE formal_lifecycle_id = ?
                   ORDER BY rowid DESC LIMIT 1""",
                (readiness.lineage.formal_lifecycle_id,),
            ).fetchone()
            if (
                latest is None
                or latest["candidate_set_id"]
                != readiness.candidate_set.candidate_set_id
            ):
                raise FormalEvidenceStaleWriteError(
                    "Readiness candidate set is no longer current"
                )
            self._validate_candidate_snapshot(connection, readiness.candidate_set)
            connection.execute(
                """INSERT INTO preliminary_supporting_formal_evidence_readiness(
                       readiness_id, formal_lifecycle_id, candidate_set_id,
                       schema_version, contract_family, status,
                       payload_json, payload_sha256
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    readiness.readiness_id,
                    readiness.lineage.formal_lifecycle_id,
                    readiness.candidate_set.candidate_set_id,
                    readiness.schema_version,
                    readiness.contract_family,
                    readiness.status.value,
                    payload_json,
                    payload_sha,
                ),
            )
            if terminal_event is not None and event_payload is not None:
                self._insert_workflow_event(
                    connection,
                    terminal_event,
                    payload_json=event_payload[0],
                    payload_sha=event_payload[1],
                )

        record, replayed = self._write_idempotently(
            lineage=readiness.lineage,
            request=request,
            operation_type="APPEND_READINESS",
            target_identity=readiness.readiness_id,
            result_schema_version=readiness.schema_version,
            result_identity=readiness.readiness_id,
            result_payload_sha256=payload_sha,
            operation_payload_sha256=self._operation_payload_sha256(
                (
                    payload_sha,
                    *(() if event_payload is None else (event_payload[1],)),
                )
            ),
            writer=writer,
        )
        return FormalEvidenceWriteResult(record=record, replayed=replayed)  # type: ignore[arg-type]

    def append_workflow_event(
        self, event: FormalEvidenceWorkflowEvent
    ) -> FormalEvidenceWriteResult[FormalEvidenceWorkflowEvent]:
        payload_json, payload_sha = serialize_formal_evidence_record(event)

        def writer(connection: sqlite3.Connection) -> None:
            self._insert_workflow_event(
                connection,
                event,
                payload_json=payload_json,
                payload_sha=payload_sha,
            )

        record, replayed = self._write_idempotently(
            lineage=event.lineage,
            request=event.request,
            operation_type="APPEND_WORKFLOW_EVENT",
            target_identity=event.event_id,
            result_schema_version=event.schema_version,
            result_identity=event.event_id,
            result_payload_sha256=payload_sha,
            operation_payload_sha256=self._operation_payload_sha256((payload_sha,)),
            writer=writer,
        )
        return FormalEvidenceWriteResult(record=record, replayed=replayed)  # type: ignore[arg-type]

    @staticmethod
    def _insert_workflow_event(
        connection: sqlite3.Connection,
        event: FormalEvidenceWorkflowEvent,
        *,
        payload_json: str,
        payload_sha: str,
    ) -> None:
        latest = connection.execute(
            """SELECT event_id, lifecycle_sequence
               FROM preliminary_supporting_formal_evidence_workflow_events
               WHERE formal_lifecycle_id = ?
               ORDER BY lifecycle_sequence DESC LIMIT 1""",
            (event.lineage.formal_lifecycle_id,),
        ).fetchone()
        if event.lifecycle_sequence == 1:
            if latest is not None:
                raise FormalEvidenceStaleWriteError(
                    "Initial formal-evidence workflow event already exists"
                )
        elif latest is None or (
            event.prior_event_id != latest["event_id"]
            or event.lifecycle_sequence != latest["lifecycle_sequence"] + 1
        ):
            raise FormalEvidenceStaleWriteError(
                "Workflow event does not extend the exact current sequence"
            )
        connection.execute(
            """INSERT INTO preliminary_supporting_formal_evidence_workflow_events(
                   event_id, formal_lifecycle_id, lifecycle_sequence,
                   prior_event_id, schema_version, contract_family,
                   event_type, subject_id, request_token,
                   payload_json, payload_sha256
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.event_id,
                event.lineage.formal_lifecycle_id,
                event.lifecycle_sequence,
                event.prior_event_id,
                event.schema_version,
                event.contract_family,
                event.event_type.value,
                event.subject_id,
                event.request.request_token,
                payload_json,
                payload_sha,
            ),
        )

    def list_records(
        self,
        schema_version: str,
        *,
        formal_lifecycle_id: str | None = None,
    ) -> tuple[BaseModel, ...]:
        try:
            table, identity_column = _TABLE_BY_SCHEMA[schema_version]
        except KeyError as exc:
            raise ArtifactCorruptionError(
                f"Unsupported stored formal-evidence schema: {schema_version}"
            ) from exc
        if schema_version == "supporting-source-blob.v0.1":
            query = f"SELECT {identity_column} FROM {table} ORDER BY {identity_column}"
            parameters: tuple[Any, ...] = ()
        else:
            if formal_lifecycle_id is None:
                raise FormalEvidenceLineageError(
                    "Contextual formal-evidence reads require a formal lifecycle"
                )
            query = (
                f"SELECT {identity_column} FROM {table} "
                f"WHERE formal_lifecycle_id = ? ORDER BY rowid"
            )
            parameters = (formal_lifecycle_id,)
        with self._read() as connection:
            identities = [row[0] for row in connection.execute(query, parameters)]
            return tuple(
                self._load_record(connection, schema_version, identity)
                for identity in identities
            )

"""Explicit deterministic ingestion for retained supporting-document bytes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from ai_adoption_engine.ingestion.pdf import ingest_pdf_bytes
from ai_adoption_engine.ingestion.text import ingest_text_bytes
from ai_adoption_engine.models.document import (
    IngestedDocument,
    IngestionIssue,
    IngestionResult,
    IngestionStatus,
    IssueSeverity,
)
from ai_adoption_engine.models.formal_evidence import (
    FORMAL_EVIDENCE_FAMILY,
    MAX_EXTRACTED_CHARACTERS,
    SUPPORTING_DOCUMENT_INGESTION_ATTEMPT_SCHEMA,
    AttemptStatus,
    FormalEvidenceLineage,
    FormalEvidenceWorkflowEvent,
    ParsedDocumentIdentity,
    RequestIdentity,
    SupportingDocument,
    SupportingDocumentIngestionAttempt,
    WorkflowEventType,
)
from ai_adoption_engine.persistence.formal_evidence import (
    FormalEvidenceStaleWriteError,
    SQLiteFormalEvidenceRepository,
)
from ai_adoption_engine.persistence.formal_evidence_serialization import (
    serialize_formal_evidence_record,
)
from ai_adoption_engine.supporting_evidence.common import (
    Clock,
    IdFactory,
    canonical_sha256,
    new_id,
    next_workflow_event,
    replay_for_request,
    request_identity,
    require_lineage,
    utc_now,
)
from ai_adoption_engine.supporting_evidence.errors import (
    SupportingEvidenceConcurrentAttemptError,
    SupportingEvidenceFinalizationError,
    SupportingEvidenceInterruptedError,
    SupportingEvidenceLineageError,
    SupportingEvidenceRequestConflictError,
)


SupportingParser = Callable[[bytes, str], IngestionResult]


@dataclass(frozen=True)
class PendingSupportingIngestion:
    lineage: FormalEvidenceLineage
    document: SupportingDocument
    request: RequestIdentity
    attempt_id: str
    attempt_number: int
    predecessor_attempt_id: str | None
    started_at: datetime
    start_event: FormalEvidenceWorkflowEvent


@dataclass(frozen=True)
class SupportingIngestionResult:
    attempt: SupportingDocumentIngestionAttempt
    ingested_document: IngestedDocument | None
    replayed: bool


class SupportingDocumentIngestionService:
    def __init__(
        self,
        repository: SQLiteFormalEvidenceRepository,
        *,
        pdf_parser: SupportingParser = ingest_pdf_bytes,
        text_parser: SupportingParser = ingest_text_bytes,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        self.repository = repository
        self.pdf_parser = pdf_parser
        self.text_parser = text_parser
        self.clock = clock or utc_now
        self.id_factory = id_factory or new_id

    def _document(
        self,
        lineage: FormalEvidenceLineage,
        document_id: str,
        *,
        require_current: bool,
    ) -> SupportingDocument:
        require_lineage(self.repository, lineage)
        record = self.repository.load_record("supporting-document.v0.1", document_id)
        if not isinstance(record, SupportingDocument) or record.lineage != lineage:
            raise SupportingEvidenceLineageError(
                "The supporting document does not belong to this formal lifecycle."
            )
        if require_current and not self.repository.is_current_document(
            formal_lifecycle_id=lineage.formal_lifecycle_id,
            document_id=document_id,
        ):
            raise SupportingEvidenceLineageError(
                "A superseded supporting document cannot start new ingestion work."
            )
        return record

    def _request(
        self,
        *,
        lineage: FormalEvidenceLineage,
        document: SupportingDocument,
        request_token: str,
        predecessor_attempt_id: str | None,
    ) -> RequestIdentity:
        return request_identity(
            request_token,
            {
                "operation": "supporting-document-ingestion.v0.1",
                "lineage": lineage.model_dump(mode="json"),
                "document_id": document.document_id,
                "document_content_sha256": document.source_blob_sha256,
                "predecessor_attempt_id": predecessor_attempt_id,
            },
        )

    def _replay(
        self,
        *,
        lineage: FormalEvidenceLineage,
        request: RequestIdentity,
    ) -> SupportingIngestionResult | None:
        replay = replay_for_request(
            self.repository,
            request=request,
            operation_type="APPEND_INGESTION_ATTEMPT",
            lineage=lineage,
        )
        if replay is None:
            return None
        if not isinstance(replay.record, SupportingDocumentIngestionAttempt):
            raise SupportingEvidenceRequestConflictError(
                "The request token does not identify a supporting ingestion attempt."
            )
        return SupportingIngestionResult(
            attempt=replay.record,
            ingested_document=None,
            replayed=True,
        )

    def begin(
        self,
        *,
        lineage: FormalEvidenceLineage,
        document_id: str,
        request_token: str,
        predecessor_attempt_id: str | None = None,
    ) -> PendingSupportingIngestion | SupportingIngestionResult:
        document = self._document(lineage, document_id, require_current=False)
        request = self._request(
            lineage=lineage,
            document=document,
            request_token=request_token,
            predecessor_attempt_id=predecessor_attempt_id,
        )
        replay = self._replay(lineage=lineage, request=request)
        if replay is not None:
            return replay
        if not self.repository.is_current_document(
            formal_lifecycle_id=lineage.formal_lifecycle_id,
            document_id=document_id,
        ):
            raise SupportingEvidenceLineageError(
                "A superseded supporting document cannot start new ingestion work."
            )

        latest = self.repository.latest_ingestion_attempt(
            formal_lifecycle_id=lineage.formal_lifecycle_id,
            document_id=document_id,
        )
        if predecessor_attempt_id is None:
            if latest is not None:
                raise SupportingEvidenceConcurrentAttemptError(
                    "A later ingestion attempt already exists for this document."
                )
            attempt_number = 1
        else:
            if (
                latest is None
                or latest.attempt_id != predecessor_attempt_id
                or latest.status not in {AttemptStatus.FAILED, AttemptStatus.ABANDONED}
            ):
                raise SupportingEvidenceConcurrentAttemptError(
                    "Ingestion retry requires the exact latest failed or abandoned attempt."
                )
            attempt_number = latest.attempt_number + 1

        start_request = request_identity(
            f"{request_token}:ingestion-start",
            {
                "request": request.model_dump(mode="json"),
                "predecessor_attempt_id": predecessor_attempt_id,
            },
        )
        start_replay = replay_for_request(
            self.repository,
            request=start_request,
            operation_type="APPEND_WORKFLOW_EVENT",
            lineage=lineage,
        )
        if start_replay is not None:
            if not isinstance(start_replay.record, FormalEvidenceWorkflowEvent):
                raise SupportingEvidenceRequestConflictError(
                    "The ingestion start token has an incompatible history record."
                )
            pending = PendingSupportingIngestion(
                lineage=lineage,
                document=document,
                request=request,
                attempt_id=start_replay.record.subject_id,
                attempt_number=attempt_number,
                predecessor_attempt_id=predecessor_attempt_id,
                started_at=start_replay.record.occurred_at,
                start_event=start_replay.record,
            )
            raise SupportingEvidenceInterruptedError(
                "This ingestion request has an unfinished start and requires explicit abandonment.",
                pending=pending,
            )

        now = self.clock()
        attempt_id = self.id_factory("supporting-ingestion")
        start_event = next_workflow_event(
            self.repository,
            lineage=lineage,
            event_type=WorkflowEventType.INGESTION_ATTEMPT_RECORDED,
            subject_id=attempt_id,
            request=start_request,
            payload_sha256=canonical_sha256(
                {
                    "attempt_id": attempt_id,
                    "attempt_number": attempt_number,
                    "document_id": document_id,
                    "document_content_sha256": document.source_blob_sha256,
                    "predecessor_attempt_id": predecessor_attempt_id,
                    "state": "STARTED",
                }
            ),
            occurred_at=now,
            event_id=self.id_factory("supporting-event"),
        )
        try:
            self.repository.append_workflow_event(start_event)
        except Exception as exc:
            raise SupportingEvidenceConcurrentAttemptError(
                "The ingestion start raced with another lifecycle operation."
            ) from exc
        return PendingSupportingIngestion(
            lineage=lineage,
            document=document,
            request=request,
            attempt_id=attempt_id,
            attempt_number=attempt_number,
            predecessor_attempt_id=predecessor_attempt_id,
            started_at=now,
            start_event=start_event,
        )

    def ingest(
        self,
        *,
        lineage: FormalEvidenceLineage,
        document_id: str,
        request_token: str,
        predecessor_attempt_id: str | None = None,
    ) -> SupportingIngestionResult:
        started = self.begin(
            lineage=lineage,
            document_id=document_id,
            request_token=request_token,
            predecessor_attempt_id=predecessor_attempt_id,
        )
        if isinstance(started, SupportingIngestionResult):
            return started
        return self.complete(started)

    def complete(
        self, pending: PendingSupportingIngestion
    ) -> SupportingIngestionResult:
        self.repository.assert_writable()
        content = self.repository.load_source_bytes(pending.document.source_blob_id)
        if content is None:
            raise SupportingEvidenceLineageError(
                "The accepted supporting-document bytes are unavailable."
            )
        parser = (
            self.pdf_parser
            if pending.document.media_type == "application/pdf"
            else self.text_parser
        )
        try:
            parsed = parser(content, pending.document.original_filename)
        except Exception:
            parsed = IngestionResult(
                status=IngestionStatus.FAILED,
                issues=[
                    IngestionIssue(
                        severity=IssueSeverity.ERROR,
                        code="supporting-parser-failed",
                        message="The supporting document could not be parsed safely.",
                    )
                ],
            )
        issue_codes = tuple(dict.fromkeys(item.code for item in parsed.issues))
        document = parsed.document
        if document is not None and len(document.canonical_text) > MAX_EXTRACTED_CHARACTERS:
            document = None
            issue_codes = (*issue_codes, "extracted-character-limit-exceeded")
            status = AttemptStatus.FAILED
        else:
            status = {
                IngestionStatus.SUCCESS: AttemptStatus.SUCCEEDED,
                IngestionStatus.PARTIAL: AttemptStatus.PARTIAL,
                IngestionStatus.FAILED: AttemptStatus.FAILED,
            }[parsed.status]
        parsed_identity = None
        if status in {AttemptStatus.SUCCEEDED, AttemptStatus.PARTIAL}:
            if document is None:
                status = AttemptStatus.FAILED
                issue_codes = (*issue_codes, "missing-parsed-document")
            else:
                parsed_sha = canonical_sha256(document.model_dump(mode="json"))
                parsed_identity = ParsedDocumentIdentity(
                    parsed_document_id=f"parsed-{parsed_sha}",
                    parsed_document_sha256=parsed_sha,
                    page_count=document.metadata.page_count,
                    extracted_character_count=len(document.canonical_text),
                )
        completed_at = self.clock()
        attempt = SupportingDocumentIngestionAttempt(
            schema_version=SUPPORTING_DOCUMENT_INGESTION_ATTEMPT_SCHEMA,
            contract_family=FORMAL_EVIDENCE_FAMILY,
            lineage=pending.lineage,
            attempt_id=pending.attempt_id,
            attempt_number=pending.attempt_number,
            document_id=pending.document.document_id,
            document_content_sha256=pending.document.source_blob_sha256,
            predecessor_attempt_id=pending.predecessor_attempt_id,
            request=pending.request,
            status=status,
            parsed_document=parsed_identity,
            issue_codes=tuple(dict.fromkeys(issue_codes)),
            started_at=pending.started_at,
            completed_at=completed_at,
        )
        _, attempt_sha = serialize_formal_evidence_record(attempt)
        terminal_event = next_workflow_event(
            self.repository,
            lineage=pending.lineage,
            event_type=WorkflowEventType.INGESTION_ATTEMPT_RECORDED,
            subject_id=attempt.attempt_id,
            request=request_identity(
                f"{pending.request.request_token}:ingestion-terminal",
                {"attempt_sha256": attempt_sha},
            ),
            payload_sha256=attempt_sha,
            occurred_at=completed_at,
            event_id=self.id_factory("supporting-event"),
        )
        try:
            stored = self.repository.append_ingestion_attempt(
                attempt,
                terminal_event=terminal_event,
            )
        except FormalEvidenceStaleWriteError as exc:
            raise SupportingEvidenceConcurrentAttemptError(
                "The ingestion attempt became stale before finalization."
            ) from exc
        except Exception as exc:
            raise SupportingEvidenceFinalizationError(
                "The ingestion result could not be finalized atomically."
            ) from exc
        return SupportingIngestionResult(
            attempt=stored.record,
            ingested_document=document if parsed_identity is not None else None,
            replayed=stored.replayed,
        )

    def abandon(
        self,
        pending: PendingSupportingIngestion,
        *,
        abandonment_token: str,
    ) -> SupportingIngestionResult:
        self.repository.assert_writable()
        request = request_identity(
            abandonment_token,
            {
                "operation": "abandon-supporting-ingestion.v0.1",
                "attempt_id": pending.attempt_id,
                "start_event_id": pending.start_event.event_id,
            },
        )
        replay = self._replay(lineage=pending.lineage, request=request)
        if replay is not None:
            return replay
        completed_at = self.clock()
        attempt = SupportingDocumentIngestionAttempt(
            schema_version=SUPPORTING_DOCUMENT_INGESTION_ATTEMPT_SCHEMA,
            contract_family=FORMAL_EVIDENCE_FAMILY,
            lineage=pending.lineage,
            attempt_id=pending.attempt_id,
            attempt_number=pending.attempt_number,
            document_id=pending.document.document_id,
            document_content_sha256=pending.document.source_blob_sha256,
            predecessor_attempt_id=pending.predecessor_attempt_id,
            request=request,
            status=AttemptStatus.ABANDONED,
            issue_codes=("explicitly-abandoned",),
            started_at=pending.started_at,
            completed_at=completed_at,
        )
        _, attempt_sha = serialize_formal_evidence_record(attempt)
        event = next_workflow_event(
            self.repository,
            lineage=pending.lineage,
            event_type=WorkflowEventType.INGESTION_ATTEMPT_RECORDED,
            subject_id=attempt.attempt_id,
            request=request_identity(
                f"{abandonment_token}:ingestion-terminal",
                {"attempt_sha256": attempt_sha},
            ),
            payload_sha256=attempt_sha,
            occurred_at=completed_at,
            event_id=self.id_factory("supporting-event"),
        )
        try:
            stored = self.repository.append_ingestion_attempt(
                attempt,
                terminal_event=event,
            )
        except Exception as exc:
            raise SupportingEvidenceFinalizationError(
                "The abandoned ingestion attempt could not be finalized atomically."
            ) from exc
        return SupportingIngestionResult(stored.record, None, stored.replayed)

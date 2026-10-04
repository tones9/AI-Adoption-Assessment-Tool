"""Dedicated supporting-evidence extraction and deterministic source resolution."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError

from ai_adoption_engine.extraction.chunking import ChunkingConfig, DocumentChunk, plan_chunks
from ai_adoption_engine.extraction.errors import (
    ExtractionProviderError,
    ExtractionProviderInvalidOutput,
)
from ai_adoption_engine.ingestion.pdf import ingest_pdf_bytes
from ai_adoption_engine.ingestion.text import ingest_text_bytes
from ai_adoption_engine.models.document import IngestedDocument, IngestionStatus
from ai_adoption_engine.models.formal_evidence import (
    EXTERNAL_PROVIDER_CONSENT_SCHEMA,
    FORMAL_EVIDENCE_FAMILY,
    SUPPORTING_EVIDENCE_EXTRACTION_ATTEMPT_SCHEMA,
    AttemptStatus,
    ExternalProviderConsent,
    FormalEvidenceLineage,
    FormalEvidenceWorkflowEvent,
    RequestIdentity,
    SupportingDocument,
    SupportingEvidenceExtractionAttempt,
    SupportingEvidenceProposal,
    SupportingSourceSpan,
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
    SupportingEvidenceCitationError,
    SupportingEvidenceConcurrentAttemptError,
    SupportingEvidenceConsentRequiredError,
    SupportingEvidenceFinalizationError,
    SupportingEvidenceInterruptedError,
    SupportingEvidenceInvalidProviderOutputError,
    SupportingEvidenceLineageError,
    SupportingEvidenceProviderFailure,
    SupportingEvidenceRequestConflictError,
)
from ai_adoption_engine.supporting_evidence.provider import (
    ApprovedActivity,
    RawSupportingCitation,
    RawSupportingEvidenceBatch,
    RawSupportingEvidenceItem,
    SupportingEvidenceProvider,
    SupportingEvidenceProviderInterrupted,
    SupportingEvidenceProviderRequest,
)


SUPPORTING_EVIDENCE_PROVIDER_DISCLOSURE = (
    "The supporting document text will be transmitted to the configured "
    "external provider for candidate evidence extraction."
)
SUPPORTING_EVIDENCE_PROVIDER_DISCLOSURE_VERSION = (
    "supporting-evidence-disclosure.v0.1"
)


@dataclass(frozen=True)
class PendingSupportingExtraction:
    lineage: FormalEvidenceLineage
    document: SupportingDocument
    ingestion_attempt_id: str
    request: RequestIdentity
    attempt_id: str
    attempt_number: int
    predecessor_attempt_id: str | None
    started_at: datetime
    start_event: FormalEvidenceWorkflowEvent


@dataclass(frozen=True)
class SupportingExtractionResult:
    attempt: SupportingEvidenceExtractionAttempt
    proposals: tuple[SupportingEvidenceProposal, ...]
    replayed: bool


class SupportingEvidenceExtractionService:
    def __init__(
        self,
        repository: SQLiteFormalEvidenceRepository,
        provider: SupportingEvidenceProvider,
        *,
        disclosure_text: str = SUPPORTING_EVIDENCE_PROVIDER_DISCLOSURE,
        disclosure_version: str = SUPPORTING_EVIDENCE_PROVIDER_DISCLOSURE_VERSION,
        chunking: ChunkingConfig | None = None,
        pdf_parser: Callable = ingest_pdf_bytes,
        text_parser: Callable = ingest_text_bytes,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        self.repository = repository
        self.provider = provider
        self.disclosure_text = disclosure_text
        self.disclosure_version = disclosure_version
        self.chunking = chunking or ChunkingConfig()
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
                "A superseded supporting document cannot start evidence extraction."
            )
        return record

    def record_provider_consent(
        self,
        *,
        lineage: FormalEvidenceLineage,
        document_id: str,
        request_token: str,
        explicit_consent: bool,
        declarant_name: str | None = None,
        local_session_identity: str | None = None,
    ) -> ExternalProviderConsent:
        document = self._document(lineage, document_id, require_current=True)
        identity = self.provider.extractor_identity
        request = request_identity(
            request_token,
            {
                "operation": "supporting-evidence-provider-consent.v0.1",
                "lineage": lineage.model_dump(mode="json"),
                "document_id": document.document_id,
                "document_content_sha256": document.source_blob_sha256,
                "provider_id": identity.provider_id,
                "provider_version": identity.provider_version,
                "disclosure_text": self.disclosure_text,
                "disclosure_version": self.disclosure_version,
                "explicit_consent": explicit_consent,
                "declarant_name": declarant_name,
                "local_session_identity": local_session_identity,
            },
        )
        replay = replay_for_request(
            self.repository,
            request=request,
            operation_type="STORE_PROVIDER_CONSENT",
            lineage=lineage,
        )
        if replay is not None:
            if not isinstance(replay.record, ExternalProviderConsent):
                raise SupportingEvidenceRequestConflictError(
                    "The consent token identifies an incompatible record."
                )
            return replay.record
        consent = ExternalProviderConsent(
            schema_version=EXTERNAL_PROVIDER_CONSENT_SCHEMA,
            contract_family=FORMAL_EVIDENCE_FAMILY,
            lineage=lineage,
            document_id=document.document_id,
            provider_id=identity.provider_id,
            provider_version=identity.provider_version,
            disclosure_text=self.disclosure_text,
            disclosure_version=self.disclosure_version,
            explicit_consent=explicit_consent,
            declarant_name=declarant_name,
            local_session_identity=local_session_identity,
            declared_at=self.clock(),
        )
        try:
            stored = self.repository.store_provider_consent(
                consent,
                request=request,
            )
        except Exception as exc:
            raise SupportingEvidenceFinalizationError(
                "The provider-consent declaration could not be recorded."
            ) from exc
        return stored.record

    def _require_consent(
        self,
        lineage: FormalEvidenceLineage,
        document: SupportingDocument,
    ) -> None:
        if not self.provider.is_external:
            return
        identity = self.provider.extractor_identity
        consent = self.repository.latest_provider_consent(
            formal_lifecycle_id=lineage.formal_lifecycle_id,
            document_id=document.document_id,
            provider_id=identity.provider_id,
        )
        if (
            consent is None
            or consent.lineage != lineage
            or not consent.explicit_consent
            or consent.provider_version != identity.provider_version
            or consent.disclosure_version != self.disclosure_version
            or consent.disclosure_text != self.disclosure_text
            or not self.repository.is_current_document(
                formal_lifecycle_id=lineage.formal_lifecycle_id,
                document_id=document.document_id,
            )
        ):
            raise SupportingEvidenceConsentRequiredError(
                "Explicit consent for this document and configured provider is required."
            )

    def _request(
        self,
        *,
        lineage: FormalEvidenceLineage,
        document: SupportingDocument,
        ingestion_attempt_id: str,
        request_token: str,
        predecessor_attempt_id: str | None,
    ) -> RequestIdentity:
        return request_identity(
            request_token,
            {
                "operation": "supporting-evidence-extraction.v0.1",
                "lineage": lineage.model_dump(mode="json"),
                "document_id": document.document_id,
                "document_content_sha256": document.source_blob_sha256,
                "ingestion_attempt_id": ingestion_attempt_id,
                "predecessor_attempt_id": predecessor_attempt_id,
                "extractor": self.provider.extractor_identity.model_dump(mode="json"),
            },
        )

    def _replay(
        self,
        *,
        lineage: FormalEvidenceLineage,
        request: RequestIdentity,
    ) -> SupportingExtractionResult | None:
        replay = replay_for_request(
            self.repository,
            request=request,
            operation_type="STORE_EXTRACTION_BUNDLE",
            lineage=lineage,
        )
        if replay is None:
            return None
        if not isinstance(replay.record, SupportingEvidenceExtractionAttempt):
            raise SupportingEvidenceRequestConflictError(
                "The request token does not identify a supporting extraction attempt."
            )
        return SupportingExtractionResult(
            attempt=replay.record,
            proposals=self.repository.proposals_for_attempt(replay.record.attempt_id),
            replayed=True,
        )

    def begin(
        self,
        *,
        lineage: FormalEvidenceLineage,
        document_id: str,
        ingestion_attempt_id: str,
        request_token: str,
        predecessor_attempt_id: str | None = None,
    ) -> PendingSupportingExtraction | SupportingExtractionResult:
        document = self._document(lineage, document_id, require_current=False)
        request = self._request(
            lineage=lineage,
            document=document,
            ingestion_attempt_id=ingestion_attempt_id,
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
                "A superseded supporting document cannot start evidence extraction."
            )
        ingestion = self.repository.load_record(
            "supporting-document-ingestion-attempt.v0.1",
            ingestion_attempt_id,
        )
        if (
            not hasattr(ingestion, "document_id")
            or ingestion.document_id != document_id
            or ingestion.lineage != lineage
            or ingestion.document_content_sha256 != document.source_blob_sha256
            or ingestion.status not in {AttemptStatus.SUCCEEDED, AttemptStatus.PARTIAL}
            or ingestion.parsed_document is None
        ):
            raise SupportingEvidenceLineageError(
                "Evidence extraction requires a successful exact-document ingestion."
            )
        self._require_consent(lineage, document)

        latest = self.repository.latest_extraction_attempt(
            formal_lifecycle_id=lineage.formal_lifecycle_id,
            document_id=document_id,
        )
        if predecessor_attempt_id is None:
            if latest is not None:
                raise SupportingEvidenceConcurrentAttemptError(
                    "A later extraction attempt already exists for this document."
                )
            attempt_number = 1
        else:
            if (
                latest is None
                or latest.attempt_id != predecessor_attempt_id
                or latest.status not in {AttemptStatus.FAILED, AttemptStatus.ABANDONED}
            ):
                raise SupportingEvidenceConcurrentAttemptError(
                    "Extraction retry requires the exact latest failed or abandoned attempt."
                )
            attempt_number = latest.attempt_number + 1

        start_request = request_identity(
            f"{request_token}:extraction-start",
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
                    "The extraction start token has incompatible history."
                )
            pending = PendingSupportingExtraction(
                lineage=lineage,
                document=document,
                ingestion_attempt_id=ingestion_attempt_id,
                request=request,
                attempt_id=start_replay.record.subject_id,
                attempt_number=attempt_number,
                predecessor_attempt_id=predecessor_attempt_id,
                started_at=start_replay.record.occurred_at,
                start_event=start_replay.record,
            )
            raise SupportingEvidenceInterruptedError(
                "This extraction request has an unfinished start and requires explicit abandonment.",
                pending=pending,
            )

        now = self.clock()
        attempt_id = self.id_factory("supporting-extraction")
        start_event = next_workflow_event(
            self.repository,
            lineage=lineage,
            event_type=WorkflowEventType.EXTRACTION_ATTEMPT_RECORDED,
            subject_id=attempt_id,
            request=start_request,
            payload_sha256=canonical_sha256(
                {
                    "attempt_id": attempt_id,
                    "attempt_number": attempt_number,
                    "document_id": document_id,
                    "document_content_sha256": document.source_blob_sha256,
                    "ingestion_attempt_id": ingestion_attempt_id,
                    "predecessor_attempt_id": predecessor_attempt_id,
                    "extractor": self.provider.extractor_identity.model_dump(mode="json"),
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
                "The extraction start raced with another lifecycle operation."
            ) from exc
        return PendingSupportingExtraction(
            lineage=lineage,
            document=document,
            ingestion_attempt_id=ingestion_attempt_id,
            request=request,
            attempt_id=attempt_id,
            attempt_number=attempt_number,
            predecessor_attempt_id=predecessor_attempt_id,
            started_at=now,
            start_event=start_event,
        )

    def extract(
        self,
        *,
        lineage: FormalEvidenceLineage,
        document_id: str,
        ingestion_attempt_id: str,
        request_token: str,
        predecessor_attempt_id: str | None = None,
    ) -> SupportingExtractionResult:
        started = self.begin(
            lineage=lineage,
            document_id=document_id,
            ingestion_attempt_id=ingestion_attempt_id,
            request_token=request_token,
            predecessor_attempt_id=predecessor_attempt_id,
        )
        if isinstance(started, SupportingExtractionResult):
            return started
        return self.complete(started)

    def _reparse(
        self, pending: PendingSupportingExtraction
    ) -> tuple[IngestedDocument, object]:
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
            result = parser(content, pending.document.original_filename)
        except Exception as exc:
            raise SupportingEvidenceCitationError(
                "The retained supporting document could not be reparsed safely."
            ) from exc
        if result.status is IngestionStatus.FAILED or result.document is None:
            raise SupportingEvidenceCitationError(
                "The retained supporting document no longer produces usable canonical text."
            )
        ingestion = self.repository.load_record(
            "supporting-document-ingestion-attempt.v0.1",
            pending.ingestion_attempt_id,
        )
        parsed_sha = canonical_sha256(result.document.model_dump(mode="json"))
        if ingestion.parsed_document is None or (
            ingestion.parsed_document.parsed_document_sha256 != parsed_sha
            or ingestion.parsed_document.extracted_character_count
            != len(result.document.canonical_text)
            or ingestion.parsed_document.page_count != result.document.metadata.page_count
        ):
            raise SupportingEvidenceLineageError(
                "Reparsed supporting-document identity does not match persisted ingestion."
            )
        return result.document, ingestion

    @staticmethod
    def _resolve_citation(
        *,
        citation: RawSupportingCitation,
        document: SupportingDocument,
        ingested: IngestedDocument,
        parsed_document_id: str,
        chunk: DocumentChunk,
        lineage: FormalEvidenceLineage,
    ) -> SupportingSourceSpan:
        if citation.document_id != document.document_id:
            raise ValueError("citation-document-mismatch")
        block = next(
            (item for item in ingested.blocks if item.block_id == citation.block_id),
            None,
        )
        if block is None:
            raise ValueError("citation-block-missing")
        if citation.block_id not in chunk.block_ids:
            raise ValueError("citation-block-outside-chunk")
        text = block.extracted_text
        if citation.block_character_start is not None:
            start = citation.block_character_start
            end = citation.block_character_end_exclusive
            assert end is not None
            if end > len(text) or text[start:end] != citation.exact_excerpt:
                raise ValueError("citation-offset-mismatch")
        else:
            starts: list[int] = []
            search = 0
            while True:
                found = text.find(citation.exact_excerpt, search)
                if found < 0:
                    break
                starts.append(found)
                search = found + 1
            if not starts:
                raise ValueError("citation-excerpt-missing")
            if len(starts) != 1:
                raise ValueError("citation-excerpt-ambiguous")
            start = starts[0]
            end = start + len(citation.exact_excerpt)
        if not any(
            start >= item.block_start_offset and end <= item.block_end_offset
            for item in chunk.slices
            if item.block_id == block.block_id
        ):
            raise ValueError("citation-outside-provider-chunk")
        document_start = block.document_start_offset + start
        document_end = block.document_start_offset + end
        if ingested.canonical_text[document_start:document_end] != citation.exact_excerpt:
            raise ValueError("citation-document-offset-mismatch")
        return SupportingSourceSpan(
            lineage=lineage,
            document_id=document.document_id,
            document_content_sha256=document.source_blob_sha256,
            parsed_document_id=parsed_document_id,
            block_id=block.block_id,
            page_number=block.page_number,
            line_start=block.line_start,
            line_end_exclusive=(
                None if block.line_end is None else block.line_end + 1
            ),
            document_character_start=document_start,
            document_character_end_exclusive=document_end,
            block_character_start=start,
            block_character_end_exclusive=end,
            exact_excerpt=citation.exact_excerpt,
            excerpt_sha256=hashlib.sha256(
                citation.exact_excerpt.encode("utf-8")
            ).hexdigest(),
            locator=block.source_locator,
        )

    def _proposal(
        self,
        *,
        raw: RawSupportingEvidenceItem,
        document: SupportingDocument,
        ingested: IngestedDocument,
        parsed_document_id: str,
        chunk: DocumentChunk,
        lineage: FormalEvidenceLineage,
        attempt_id: str,
        approved_activity_ids: frozenset[str],
    ) -> SupportingEvidenceProposal:
        if not set(raw.suggested_activity_ids) <= approved_activity_ids:
            raise ValueError("suggested-activity-not-approved")
        spans = tuple(
            self._resolve_citation(
                citation=item,
                document=document,
                ingested=ingested,
                parsed_document_id=parsed_document_id,
                chunk=chunk,
                lineage=lineage,
            )
            for item in (raw.primary_citation, *raw.related_citations)
        )
        return SupportingEvidenceProposal(
            schema_version="supporting-evidence-proposal.v0.1",
            contract_family=FORMAL_EVIDENCE_FAMILY,
            lineage=lineage,
            extraction_attempt_id=attempt_id,
            document_id=document.document_id,
            document_content_sha256=document.source_blob_sha256,
            proposed_claim=raw.proposed_claim,
            proposed_classification=raw.proposed_classification,
            primary_source_span=spans[0],
            related_source_spans=spans[1:],
            proposed_category=raw.proposed_category,
            suggested_activity_ids=raw.suggested_activity_ids,
            suggested_formal_targets=raw.suggested_formal_targets,
            explanatory_gate_relevance=raw.explanatory_gate_relevance,
            ambiguity_indicated=raw.ambiguity_indicated,
            conflict_indicated=raw.conflict_indicated,
            relevance_explanation=raw.relevance_explanation,
            extraction_confidence=raw.extraction_confidence,
            extractor=self.provider.extractor_identity,
        )

    def complete(
        self, pending: PendingSupportingExtraction
    ) -> SupportingExtractionResult:
        self.repository.assert_writable()
        self._require_consent(pending.lineage, pending.document)
        ingested, ingestion = self._reparse(pending)
        parsed_document_id = ingestion.parsed_document.parsed_document_id
        activities = tuple(
            ApprovedActivity(activity_id=item[0], activity_name=item[1])
            for item in self.repository.approved_activity_catalog(pending.lineage)
        )
        approved_activity_ids = frozenset(item.activity_id for item in activities)
        chunks = plan_chunks(ingested, self.chunking)
        proposals: dict[str, SupportingEvidenceProposal] = {}
        issue_codes: list[str] = []
        provider_failure: ExtractionProviderError | None = None
        invalid_output = False
        for chunk in chunks:
            request = SupportingEvidenceProviderRequest(
                document_id=pending.document.document_id,
                document_content_sha256=pending.document.source_blob_sha256,
                chunk=chunk,
                approved_activities=activities,
            )
            try:
                raw_response = self.provider.extract(request)
                batch = (
                    raw_response
                    if isinstance(raw_response, RawSupportingEvidenceBatch)
                    else RawSupportingEvidenceBatch.model_validate(raw_response)
                )
            except SupportingEvidenceProviderInterrupted as exc:
                raise SupportingEvidenceInterruptedError(
                    "Supporting-evidence extraction was interrupted and requires explicit abandonment.",
                    pending=pending,
                ) from exc
            except ExtractionProviderInvalidOutput as exc:
                invalid_output = True
                provider_failure = exc
                issue_codes.append(exc.code)
                continue
            except ExtractionProviderError as exc:
                provider_failure = exc
                issue_codes.append(exc.code)
                continue
            except (ValidationError, TypeError, ValueError):
                invalid_output = True
                issue_codes.append("provider-invalid-structured-output")
                continue
            except Exception:
                issue_codes.append("provider-error")
                provider_failure = ExtractionProviderError(
                    "The supporting-evidence provider failed safely.",
                    provider_name=self.provider.extractor_identity.provider_id,
                )
                continue

            for raw_item in batch.items:
                try:
                    proposal = self._proposal(
                        raw=raw_item,
                        document=pending.document,
                        ingested=ingested,
                        parsed_document_id=parsed_document_id,
                        chunk=chunk,
                        lineage=pending.lineage,
                        attempt_id=pending.attempt_id,
                        approved_activity_ids=approved_activity_ids,
                    )
                except (ValueError, ValidationError) as exc:
                    issue_codes.append(str(exc) or "invalid-provider-item")
                    continue
                assert proposal.proposal_id is not None
                proposals.setdefault(proposal.proposal_id, proposal)

        ordered = tuple(
            sorted(
                proposals.values(),
                key=lambda item: (
                    item.primary_source_span.document_character_start,
                    item.proposed_claim,
                    item.proposal_id or "",
                ),
            )
        )
        unique_issues = tuple(dict.fromkeys(issue_codes))
        if not ordered:
            status = AttemptStatus.FAILED
            if not unique_issues:
                unique_issues = ("no-valid-evidence-proposals",)
        elif unique_issues:
            status = AttemptStatus.PARTIAL
        else:
            status = AttemptStatus.SUCCEEDED
        completed_at = self.clock()
        attempt = SupportingEvidenceExtractionAttempt(
            schema_version=SUPPORTING_EVIDENCE_EXTRACTION_ATTEMPT_SCHEMA,
            contract_family=FORMAL_EVIDENCE_FAMILY,
            lineage=pending.lineage,
            attempt_id=pending.attempt_id,
            attempt_number=pending.attempt_number,
            document_id=pending.document.document_id,
            document_content_sha256=pending.document.source_blob_sha256,
            ingestion_attempt_id=pending.ingestion_attempt_id,
            predecessor_attempt_id=pending.predecessor_attempt_id,
            extractor=self.provider.extractor_identity,
            request=pending.request,
            status=status,
            proposal_ids=tuple(item.proposal_id for item in ordered),
            issue_codes=unique_issues,
            started_at=pending.started_at,
            completed_at=completed_at,
        )
        _, attempt_sha = serialize_formal_evidence_record(attempt)
        terminal_event = next_workflow_event(
            self.repository,
            lineage=pending.lineage,
            event_type=WorkflowEventType.EXTRACTION_ATTEMPT_RECORDED,
            subject_id=attempt.attempt_id,
            request=request_identity(
                f"{pending.request.request_token}:extraction-terminal",
                {"attempt_sha256": attempt_sha},
            ),
            payload_sha256=attempt_sha,
            occurred_at=completed_at,
            event_id=self.id_factory("supporting-event"),
        )
        try:
            stored = self.repository.store_extraction_bundle(
                attempt,
                ordered,
                terminal_event=terminal_event,
            )
        except FormalEvidenceStaleWriteError as exc:
            raise SupportingEvidenceConcurrentAttemptError(
                "The extraction attempt became stale before finalization."
            ) from exc
        except Exception as exc:
            raise SupportingEvidenceFinalizationError(
                "The extraction result could not be finalized atomically."
            ) from exc
        result = SupportingExtractionResult(
            attempt=stored.record,
            proposals=ordered,
            replayed=stored.replayed,
        )
        if status is AttemptStatus.FAILED:
            if invalid_output:
                raise SupportingEvidenceInvalidProviderOutputError(
                    "The provider returned invalid structured evidence output.",
                    provider_code="provider-invalid-structured-output",
                    result=result,
                )
            if provider_failure is not None:
                raise SupportingEvidenceProviderFailure(
                    "The supporting-evidence provider could not complete extraction.",
                    provider_code=provider_failure.code,
                    result=result,
                )
            raise SupportingEvidenceCitationError(
                "No provider citation could be resolved into trusted evidence.",
                result=result,
            )
        return result

    def abandon(
        self,
        pending: PendingSupportingExtraction,
        *,
        abandonment_token: str,
    ) -> SupportingExtractionResult:
        self.repository.assert_writable()
        request = request_identity(
            abandonment_token,
            {
                "operation": "abandon-supporting-extraction.v0.1",
                "attempt_id": pending.attempt_id,
                "start_event_id": pending.start_event.event_id,
            },
        )
        replay = self._replay(lineage=pending.lineage, request=request)
        if replay is not None:
            return replay
        completed_at = self.clock()
        attempt = SupportingEvidenceExtractionAttempt(
            schema_version=SUPPORTING_EVIDENCE_EXTRACTION_ATTEMPT_SCHEMA,
            contract_family=FORMAL_EVIDENCE_FAMILY,
            lineage=pending.lineage,
            attempt_id=pending.attempt_id,
            attempt_number=pending.attempt_number,
            document_id=pending.document.document_id,
            document_content_sha256=pending.document.source_blob_sha256,
            ingestion_attempt_id=pending.ingestion_attempt_id,
            predecessor_attempt_id=pending.predecessor_attempt_id,
            extractor=self.provider.extractor_identity,
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
            event_type=WorkflowEventType.EXTRACTION_ATTEMPT_RECORDED,
            subject_id=attempt.attempt_id,
            request=request_identity(
                f"{abandonment_token}:extraction-terminal",
                {"attempt_sha256": attempt_sha},
            ),
            payload_sha256=attempt_sha,
            occurred_at=completed_at,
            event_id=self.id_factory("supporting-event"),
        )
        try:
            stored = self.repository.store_extraction_bundle(
                attempt,
                (),
                terminal_event=event,
            )
        except Exception as exc:
            raise SupportingEvidenceFinalizationError(
                "The abandoned extraction attempt could not be finalized atomically."
            ) from exc
        return SupportingExtractionResult(stored.record, (), stored.replayed)

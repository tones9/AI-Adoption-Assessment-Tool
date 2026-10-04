from __future__ import annotations

import hashlib
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.formal_evidence import (
    CONTEXT_NOTE_SCHEMA,
    EXTERNAL_PROVIDER_CONSENT_SCHEMA,
    FORMAL_EVIDENCE_FAMILY,
    FORMAL_EVIDENCE_READINESS_SCHEMA,
    FORMAL_EVIDENCE_WORKFLOW_EVENT_SCHEMA,
    FORMAL_INPUT_CANDIDATE_SET_SCHEMA,
    FORMAL_INPUT_MAPPING_SCHEMA,
    SUPPORTING_DOCUMENT_INGESTION_ATTEMPT_SCHEMA,
    SUPPORTING_DOCUMENT_METADATA_REVISION_SCHEMA,
    SUPPORTING_DOCUMENT_SCHEMA,
    SUPPORTING_EVIDENCE_EXTRACTION_ATTEMPT_SCHEMA,
    SUPPORTING_EVIDENCE_PROPOSAL_SCHEMA,
    SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
    SUPPORTING_SOURCE_BLOB_SCHEMA,
    AttemptStatus,
    CandidateDocumentIdentity,
    CandidateExtractionIdentity,
    ContextNote,
    CriterionFormalTarget,
    DocumentCategory,
    EvidenceClassification,
    ExternalProviderConsent,
    ExtractorIdentity,
    FormalEvidenceLineage,
    FormalEvidenceReadiness,
    FormalEvidenceWorkflowEvent,
    FormalInputCandidateSet,
    FormalInputMapping,
    FormalTargetKind,
    MappingDisposition,
    ParsedDocumentIdentity,
    ReadinessStatus,
    RequestIdentity,
    ReviewAction,
    ReviewedEvidenceReference,
    ReviewerDeclaration,
    SourceBlobState,
    SupportingDocument,
    SupportingDocumentIngestionAttempt,
    SupportingDocumentMetadataRevision,
    SupportingDocumentReference,
    SupportingEvidenceExtractionAttempt,
    SupportingEvidenceProposal,
    SupportingEvidenceReviewRevision,
    SupportingSourceBlob,
    SupportingSourceSpan,
    WorkflowEventType,
)
from ai_adoption_engine.persistence.base import ArtifactCorruptionError
from ai_adoption_engine.persistence.formal_evidence import (
    FormalEvidenceIdempotencyError,
    FormalEvidenceIntegrityError,
    FormalEvidenceLineageError,
    FormalEvidenceStaleWriteError,
    SQLiteFormalEvidenceRepository,
)
from ai_adoption_engine.persistence.formal_evidence_serialization import (
    FORMAL_EVIDENCE_ADAPTERS,
    deserialize_formal_evidence_record,
    serialize_formal_evidence_record,
)
from ai_adoption_engine.persistence.preliminary import SQLitePreliminaryJourneyStore
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.persistence.workspace_protection import (
    FrozenEvaluationWorkspaceError,
)
from tests.unit.test_preliminary_formal_start_service import (
    _formal_service,
    _select_formal,
    _start,
)
from tests.unit.test_preliminary_journey_service import _context


NOW = datetime(2026, 10, 4, 15, 0, tzinfo=UTC)


@dataclass(frozen=True)
class EvidenceContext:
    path: Path
    repository: SQLiteFormalEvidenceRepository
    lineage: FormalEvidenceLineage
    activity_id: str


def _request(token: str) -> RequestIdentity:
    return RequestIdentity(
        request_token=token,
        canonical_request_sha256=hashlib.sha256(token.encode()).hexdigest(),
    )


def _reviewer() -> ReviewerDeclaration:
    return ReviewerDeclaration(
        schema_version="reviewer-declaration.v0.1",
        contract_family=FORMAL_EVIDENCE_FAMILY,
        reviewer_display_name="Alex Reviewer",
        declared_organisational_role="Process owner",
        identity_and_authority_locally_declared_not_authenticated=True,
        declared_at=NOW,
    )


def _prepare(tmp_path: Path, **repository_kwargs: object) -> EvidenceContext:
    preliminary = _context(tmp_path)
    route = _select_formal(preliminary)
    formal = _start(_formal_service(preliminary), preliminary, route).lifecycle
    connection = sqlite3.connect(preliminary.path)
    connection.row_factory = sqlite3.Row
    try:
        artifact = connection.execute(
            """SELECT artifact_revision, artifact_schema_version
               FROM assessment_artifacts WHERE artifact_id = ?""",
            (formal.source.approved_review_artifact_id,),
        ).fetchone()
    finally:
        connection.close()

    assert artifact is not None
    source_hash = formal.source.source_document_id.removeprefix("doc-")
    lineage = FormalEvidenceLineage(
        formal_lifecycle_schema=formal.schema_version,
        formal_lifecycle_id=formal.formal_lifecycle_id,
        journey_id=formal.journey_id,
        source_assessment_id=formal.source.source_assessment_id,
        approved_review_artifact_id=formal.source.approved_review_artifact_id,
        approved_review_schema_version=artifact["artifact_schema_version"],
        approved_review_revision=artifact["artifact_revision"],
        approved_review_payload_sha256=(
            formal.source.approved_review_payload_sha256
        ),
        source_document_id=formal.source.source_document_id,
        source_document_sha256=source_hash,
        validated_process_id=formal.source.validated_process_id,
        validated_process_fingerprint=formal.source.validated_process_fingerprint,
    )
    repository = SQLiteFormalEvidenceRepository(
        preliminary.path,
        clock=lambda: NOW,
        **repository_kwargs,
    )
    return EvidenceContext(
        path=preliminary.path,
        repository=repository,
        lineage=lineage,
        activity_id=preliminary.approved.business_process.steps[0].step_id,
    )


def _blob(content: bytes = b"Monthly volume is 100.") -> SupportingSourceBlob:
    digest = hashlib.sha256(content).hexdigest()
    return SupportingSourceBlob(
        schema_version=SUPPORTING_SOURCE_BLOB_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        source_blob_id=f"blob-{digest}",
        content_sha256=digest,
        byte_size=len(content),
        detected_media_type="text/plain",
        original_filename="evidence.txt",
        state=SourceBlobState.ACCEPTED,
        created_at=NOW,
    )


def _document_bundle(
    lineage: FormalEvidenceLineage,
    blob: SupportingSourceBlob,
    *,
    document_id: str = "supporting-document-1",
    request_token: str = "document-1",
) -> tuple[SupportingDocument, SupportingDocumentMetadataRevision]:
    request = _request(request_token)
    document = SupportingDocument(
        schema_version=SUPPORTING_DOCUMENT_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        document_id=document_id,
        lineage=lineage,
        source_blob_id=blob.source_blob_id,
        source_blob_sha256=blob.content_sha256,
        original_filename=blob.original_filename,
        media_type="text/plain",
        byte_size=blob.byte_size,
        initial_metadata_revision_id=f"metadata-{document_id}-1",
        submitter=_reviewer(),
        created_at=NOW,
    )
    metadata = SupportingDocumentMetadataRevision(
        schema_version=SUPPORTING_DOCUMENT_METADATA_REVISION_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=lineage,
        document_id=document_id,
        revision_id=document.initial_metadata_revision_id,
        revision_number=1,
        description="Monthly operating volume evidence",
        primary_category=DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
        request=request,
        revised_at=NOW,
    )
    return document, metadata


def _store_document(context: EvidenceContext) -> tuple[bytes, SupportingDocument]:
    content = b"Monthly volume is 100."
    blob = _blob(content)
    context.repository.store_source_blob(
        blob,
        lineage=context.lineage,
        request=_request("blob-1"),
        content_bytes=content,
    )
    document, metadata = _document_bundle(context.lineage, blob)
    context.repository.store_document(
        document, metadata, request=metadata.request
    )
    return content, document


def _ingestion(
    context: EvidenceContext,
    document: SupportingDocument,
) -> SupportingDocumentIngestionAttempt:
    attempt = SupportingDocumentIngestionAttempt(
        schema_version=SUPPORTING_DOCUMENT_INGESTION_ATTEMPT_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=context.lineage,
        attempt_id="ingestion-1",
        attempt_number=1,
        document_id=document.document_id,
        document_content_sha256=document.source_blob_sha256,
        request=_request("ingestion-1"),
        status=AttemptStatus.SUCCEEDED,
        parsed_document=ParsedDocumentIdentity(
            parsed_document_id="parsed-1",
            parsed_document_sha256="a" * 64,
            extracted_character_count=document.byte_size,
        ),
        started_at=NOW,
        completed_at=NOW,
    )
    context.repository.append_ingestion_attempt(attempt)
    return attempt


def _proposal(
    context: EvidenceContext,
    document: SupportingDocument,
    extraction_attempt_id: str = "extraction-1",
) -> SupportingEvidenceProposal:
    excerpt = "Monthly volume is 100."
    span = SupportingSourceSpan(
        lineage=context.lineage,
        document_id=document.document_id,
        document_content_sha256=document.source_blob_sha256,
        parsed_document_id="parsed-1",
        block_id="block-1",
        line_start=1,
        line_end_exclusive=2,
        document_character_start=0,
        document_character_end_exclusive=len(excerpt),
        block_character_start=0,
        block_character_end_exclusive=len(excerpt),
        exact_excerpt=excerpt,
        excerpt_sha256=hashlib.sha256(excerpt.encode()).hexdigest(),
        locator="line 1",
    )
    return SupportingEvidenceProposal(
        schema_version=SUPPORTING_EVIDENCE_PROPOSAL_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=context.lineage,
        extraction_attempt_id=extraction_attempt_id,
        document_id=document.document_id,
        document_content_sha256=document.source_blob_sha256,
        proposed_claim="Monthly volume is 100.",
        proposed_classification=EvidenceClassification.DOCUMENTED_FACT,
        primary_source_span=span,
        proposed_category=DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
        suggested_activity_ids=(context.activity_id,),
        suggested_formal_targets=(
            CriterionFormalTarget(
                kind=FormalTargetKind.CRITERION,
                criterion=CriterionName.REPETITION,
            ),
        ),
        ambiguity_indicated=False,
        conflict_indicated=False,
        relevance_explanation="The volume may support a repetition score.",
        extractor=ExtractorIdentity(
            extractor_id="extractor",
            extractor_version="0.1.0",
            provider_id="provider",
            provider_version="1",
            output_schema_id="supporting-evidence-proposal.v0.1",
            output_schema_version="0.1.0",
            prompt_id="evidence",
            prompt_version="0.1.0",
        ),
    )


def _extraction(
    context: EvidenceContext,
    document: SupportingDocument,
    ingestion: SupportingDocumentIngestionAttempt,
) -> tuple[SupportingEvidenceExtractionAttempt, SupportingEvidenceProposal]:
    proposal = _proposal(context, document)
    attempt = SupportingEvidenceExtractionAttempt(
        schema_version=SUPPORTING_EVIDENCE_EXTRACTION_ATTEMPT_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=context.lineage,
        attempt_id="extraction-1",
        attempt_number=1,
        document_id=document.document_id,
        document_content_sha256=document.source_blob_sha256,
        ingestion_attempt_id=ingestion.attempt_id,
        extractor=proposal.extractor,
        request=_request("extraction-1"),
        status=AttemptStatus.SUCCEEDED,
        proposal_ids=(proposal.proposal_id,),
        started_at=NOW,
        completed_at=NOW,
    )
    context.repository.store_extraction_bundle(attempt, (proposal,))
    return attempt, proposal


def _review(
    context: EvidenceContext,
    proposal: SupportingEvidenceProposal,
) -> SupportingEvidenceReviewRevision:
    review = SupportingEvidenceReviewRevision(
        schema_version=SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=context.lineage,
        proposal_id=proposal.proposal_id,
        revision_id="review-1",
        revision_number=1,
        action=ReviewAction.ACCEPT,
        original_proposal=proposal,
        approved_claim=proposal.proposed_claim,
        source_spans=(proposal.primary_source_span,),
        selected_category=proposal.proposed_category,
        approved_classification=EvidenceClassification.DOCUMENTED_FACT,
        claim_directly_supported_by_excerpt=True,
        candidate_eligible=True,
        reviewer=_reviewer(),
        rationale="The exact excerpt states the reviewed fact.",
        reviewed_at=NOW,
        request=_request("review-1"),
    )
    context.repository.append_review_revision(review)
    return review


def _review_reference(
    context: EvidenceContext,
    review: SupportingEvidenceReviewRevision,
) -> ReviewedEvidenceReference:
    return ReviewedEvidenceReference(
        lineage=context.lineage,
        review_revision_id=review.revision_id,
        proposal_id=review.proposal_id,
        action=review.action,
        classification=review.approved_classification,
    )


def _mapping(
    context: EvidenceContext,
    review: SupportingEvidenceReviewRevision,
) -> FormalInputMapping:
    mapping = FormalInputMapping(
        schema_version=FORMAL_INPUT_MAPPING_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        mapping_id="mapping-1",
        lineage=context.lineage,
        activity_id=context.activity_id,
        target=CriterionFormalTarget(
            kind=FormalTargetKind.CRITERION,
            criterion=CriterionName.REPETITION,
        ),
        disposition=MappingDisposition.MAPPED_FORMAL_INPUT,
        value=4,
        knowledge_state=KnowledgeState.KNOWN,
        approved_evidence_classification=EvidenceClassification.DOCUMENTED_FACT,
        supporting_reviews=(_review_reference(context, review),),
        mapping_rationale="The reviewed volume supports the approved score.",
        reviewer=_reviewer(),
        mapped_at=NOW,
        request=_request("mapping-1"),
    )
    context.repository.append_formal_mapping(mapping)
    return mapping


def _candidate(
    context: EvidenceContext,
    document: SupportingDocument,
    extraction: SupportingEvidenceExtractionAttempt,
    review: SupportingEvidenceReviewRevision,
    mapping: FormalInputMapping,
) -> FormalInputCandidateSet:
    candidate = FormalInputCandidateSet(
        schema_version=FORMAL_INPUT_CANDIDATE_SET_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        candidate_set_id="candidate-1",
        lineage=context.lineage,
        current_documents=(
            CandidateDocumentIdentity(
                document_id=document.document_id,
                content_sha256=document.source_blob_sha256,
                byte_size=document.byte_size,
                metadata_revision_id=document.initial_metadata_revision_id,
            ),
        ),
        current_extractions=(
            CandidateExtractionIdentity(
                extraction_attempt_id=extraction.attempt_id,
                document_id=document.document_id,
                status=extraction.status,
                proposal_ids=extraction.proposal_ids,
            ),
        ),
        current_reviews=(_review_reference(context, review),),
        ordered_formal_mappings=(mapping,),
        created_at=NOW,
        conversion_request=_request("candidate-1"),
    )
    context.repository.append_candidate_set(candidate)
    return candidate


def test_migration_seven_is_explicit_additive_and_preserves_existing_rows(
    tmp_path: Path,
) -> None:
    preliminary = _context(tmp_path)
    ordinary = SQLitePreliminaryJourneyStore(preliminary.path)
    assert ordinary.migration_versions() == (1, 2, 3, 4, 5, 6)

    route = _select_formal(preliminary)
    _start(_formal_service(preliminary), preliminary, route)
    existing_tables = (
        "assessments",
        "assessment_artifacts",
        "active_artifacts",
        "preliminary_journeys",
        "preliminary_journey_events",
        "preliminary_formal_lifecycles",
        "preliminary_formal_start_requests",
    )
    before = sqlite3.connect(preliminary.path)
    try:
        snapshots = {
            table: before.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
            for table in existing_tables
        }
    finally:
        before.close()
    repository = SQLiteFormalEvidenceRepository(preliminary.path)
    assert repository.migration_versions() == (1, 2, 3, 4, 5, 6, 7)

    connection = sqlite3.connect(preliminary.path)
    try:
        for table in existing_tables:
            assert connection.execute(
                f"SELECT * FROM {table} ORDER BY rowid"
            ).fetchall() == snapshots[table]
        supporting_tables = {
            row[0]
            for row in connection.execute(
                """SELECT name FROM sqlite_master
                   WHERE type = 'table' AND name LIKE 'preliminary_supporting_%'"""
            )
        }
        assert len(supporting_tables) == 15
    finally:
        connection.close()


def test_explicit_repository_migrates_a_strict_only_writable_database(
    tmp_path: Path,
) -> None:
    path = tmp_path / "strict-only.db"
    SQLiteAssessmentRepository(path)
    connection = sqlite3.connect(path)
    try:
        strict_versions = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        assert connection.execute(
            """SELECT 1 FROM sqlite_master
               WHERE type = 'table'
                 AND name = 'preliminary_journey_schema_migrations'"""
        ).fetchone() is None
    finally:
        connection.close()

    repository = SQLiteFormalEvidenceRepository(path)
    assert repository.migration_versions() == (1, 2, 3, 4, 5, 6, 7)
    connection = sqlite3.connect(path)
    try:
        assert connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == strict_versions
    finally:
        connection.close()


def test_every_contextual_record_round_trips_and_history_remains_append_only(
    tmp_path: Path,
) -> None:
    context = _prepare(tmp_path)
    content, document = _store_document(context)
    consent = ExternalProviderConsent(
        schema_version=EXTERNAL_PROVIDER_CONSENT_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=context.lineage,
        document_id=document.document_id,
        provider_id="provider",
        provider_version="1",
        disclosure_text="The document may be sent to the named provider.",
        disclosure_version="1",
        explicit_consent=False,
        declarant_name="Alex Reviewer",
        declared_at=NOW,
    )
    context.repository.store_provider_consent(
        consent, request=_request("consent-1")
    )
    ingestion = _ingestion(context, document)
    extraction, proposal = _extraction(context, document, ingestion)
    review = _review(context, proposal)
    note = ContextNote(
        schema_version=CONTEXT_NOTE_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        context_note_id="context-1",
        lineage=context.lineage,
        activity_id=context.activity_id,
        statement="The team expects volume to increase.",
        origin="HUMAN_SUPPLIED_CONTEXT_ONLY",
        reviewer=_reviewer(),
        created_at=NOW,
        request=_request("context-1"),
    )
    context.repository.append_context_note(note)
    mapping = _mapping(context, review)
    candidate = _candidate(context, document, extraction, review, mapping)
    readiness = FormalEvidenceReadiness(
        schema_version=FORMAL_EVIDENCE_READINESS_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        readiness_id="readiness-1",
        lineage=context.lineage,
        candidate_set=candidate,
        current_review_revision_ids=(review.revision_id,),
        processing_complete_or_explicitly_excluded=True,
        every_current_proposal_terminally_reviewed=True,
        every_accepted_or_corrected_item_mapped_or_context_only=True,
        candidate_set_includes_every_current_review_revision=True,
        lineage_and_integrity_valid=True,
        retained_unknown_count=0,
        retained_conflict_count=0,
        status=ReadinessStatus.READY_TO_ATTEMPT,
        evaluated_at=NOW,
    )
    context.repository.append_readiness(
        readiness, request=_request("readiness-1")
    )
    event = FormalEvidenceWorkflowEvent(
        schema_version=FORMAL_EVIDENCE_WORKFLOW_EVENT_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        event_id="workflow-1",
        lineage=context.lineage,
        lifecycle_sequence=1,
        event_type=WorkflowEventType.CANDIDATE_SET_CREATED,
        subject_id=candidate.candidate_set_id,
        request=_request("workflow-1"),
        payload_sha256=serialize_formal_evidence_record(candidate)[1],
        occurred_at=NOW,
    )
    context.repository.append_workflow_event(event)
    initial_metadata = context.repository.load_record(
        SUPPORTING_DOCUMENT_METADATA_REVISION_SCHEMA,
        document.initial_metadata_revision_id,
    )

    records = (
        _blob(content),
        document,
        initial_metadata,
        consent,
        ingestion,
        extraction,
        proposal,
        review,
        note,
        mapping,
        candidate,
        readiness,
        event,
        _reviewer(),
    )
    for record in records:
        payload_json, payload_sha = serialize_formal_evidence_record(record)
        assert deserialize_formal_evidence_record(
            record.schema_version, payload_json, payload_sha
        ) == record
    assert set(FORMAL_EVIDENCE_ADAPTERS) == {
        SUPPORTING_SOURCE_BLOB_SCHEMA,
        SUPPORTING_DOCUMENT_SCHEMA,
        SUPPORTING_DOCUMENT_METADATA_REVISION_SCHEMA,
        SUPPORTING_DOCUMENT_INGESTION_ATTEMPT_SCHEMA,
        SUPPORTING_EVIDENCE_EXTRACTION_ATTEMPT_SCHEMA,
        SUPPORTING_EVIDENCE_PROPOSAL_SCHEMA,
        SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
        FORMAL_INPUT_MAPPING_SCHEMA,
        FORMAL_INPUT_CANDIDATE_SET_SCHEMA,
        FORMAL_EVIDENCE_READINESS_SCHEMA,
        FORMAL_EVIDENCE_WORKFLOW_EVENT_SCHEMA,
        "reviewer-declaration.v0.1",
        EXTERNAL_PROVIDER_CONSENT_SCHEMA,
        CONTEXT_NOTE_SCHEMA,
    }

    metadata_two = SupportingDocumentMetadataRevision(
        schema_version=SUPPORTING_DOCUMENT_METADATA_REVISION_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=context.lineage,
        document_id=document.document_id,
        revision_id="metadata-supporting-document-1-2",
        revision_number=2,
        prior_revision_id=document.initial_metadata_revision_id,
        description="Updated description only; prior candidate remains immutable.",
        primary_category=DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
        request=_request("metadata-2"),
        revised_at=NOW,
    )
    context.repository.append_metadata_revision(metadata_two)
    assert context.repository.load_record(
        candidate.schema_version, candidate.candidate_set_id
    ) == candidate
    assert context.repository.load_record(
        readiness.schema_version, readiness.readiness_id
    ) == readiness
    stale_candidate = candidate.model_copy(
        update={
            "candidate_set_id": "candidate-stale",
            "prior_candidate_set_id": candidate.candidate_set_id,
            "conversion_request": _request("candidate-stale"),
        }
    )
    with pytest.raises(FormalEvidenceStaleWriteError, match="documents"):
        context.repository.append_candidate_set(stale_candidate)

    connection = sqlite3.connect(context.path)
    try:
        immutable_tables = {
            "preliminary_formal_evidence_lineages": "journey_id",
            "preliminary_supporting_source_blobs": "payload_json",
            "preliminary_supporting_source_blob_bytes": "byte_size",
            "preliminary_supporting_documents": "payload_json",
            "preliminary_supporting_document_metadata_revisions": "payload_json",
            "preliminary_supporting_provider_consents": "payload_json",
            "preliminary_supporting_ingestion_attempts": "payload_json",
            "preliminary_supporting_extraction_attempts": "payload_json",
            "preliminary_supporting_evidence_proposals": "payload_json",
            "preliminary_supporting_evidence_review_revisions": "payload_json",
            "preliminary_supporting_context_notes": "payload_json",
            "preliminary_supporting_formal_input_mappings": "payload_json",
            "preliminary_supporting_formal_input_candidate_sets": "payload_json",
            "preliminary_supporting_formal_evidence_readiness": "payload_json",
            "preliminary_supporting_formal_evidence_workflow_events": "payload_json",
            "preliminary_supporting_operation_requests": "target_identity",
        }
        for table, column in immutable_tables.items():
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(f"UPDATE {table} SET {column} = {column}")
            connection.rollback()
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(f"DELETE FROM {table}")
            connection.rollback()
    finally:
        connection.close()


def test_raw_bytes_are_exact_immutable_deduplicated_and_rejected_bytes_are_refused(
    tmp_path: Path,
) -> None:
    context = _prepare(tmp_path)
    content = b"same immutable bytes"
    blob = _blob(content)
    first = context.repository.store_source_blob(
        blob,
        lineage=context.lineage,
        request=_request("blob-first"),
        content_bytes=content,
    )
    second = context.repository.store_source_blob(
        blob,
        lineage=context.lineage,
        request=_request("blob-second"),
        content_bytes=content,
    )
    assert first.record == second.record == blob
    assert context.repository.load_source_bytes(blob.source_blob_id) == content
    for document_id, token in (("document-a", "document-a"), ("document-b", "document-b")):
        document, metadata = _document_bundle(
            context.lineage,
            blob,
            document_id=document_id,
            request_token=token,
        )
        context.repository.store_document(document, metadata, request=metadata.request)
    connection = sqlite3.connect(context.path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_source_blob_bytes"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_documents"
        ).fetchone()[0] == 2
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                """UPDATE preliminary_supporting_source_blob_bytes
                   SET content_bytes = ? WHERE source_blob_id = ?""",
                (b"replacement", blob.source_blob_id),
            )
    finally:
        connection.close()

    with pytest.raises(FormalEvidenceIntegrityError, match="length"):
        context.repository.store_source_blob(
            blob,
            lineage=context.lineage,
            request=_request("blob-wrong-size"),
            content_bytes=b"wrong",
        )
    corrupt_same_size = b"x" * len(content)
    with pytest.raises(FormalEvidenceIntegrityError, match="SHA-256"):
        context.repository.store_source_blob(
            blob,
            lineage=context.lineage,
            request=_request("blob-wrong-hash"),
            content_bytes=corrupt_same_size,
        )
    rejected_digest = "f" * 64
    rejected = SupportingSourceBlob(
        schema_version=SUPPORTING_SOURCE_BLOB_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        source_blob_id=f"blob-{rejected_digest}",
        content_sha256=rejected_digest,
        byte_size=12,
        detected_media_type="application/msword",
        original_filename="unsupported.doc",
        state=SourceBlobState.REJECTED,
        rejection_code="WORD_DOCUMENT",
        created_at=NOW,
    )
    with pytest.raises(FormalEvidenceIntegrityError, match="cannot retain"):
        context.repository.store_source_blob(
            rejected,
            lineage=context.lineage,
            request=_request("rejected-with-bytes"),
            content_bytes=b"not retained",
        )
    context.repository.store_source_blob(
        rejected,
        lineage=context.lineage,
        request=_request("rejected-metadata"),
        content_bytes=None,
    )
    assert context.repository.load_source_bytes(rejected.source_blob_id) is None


def test_document_supersession_is_same_lineage_immutable_and_current_snapshot_aware(
    tmp_path: Path,
) -> None:
    context = _prepare(tmp_path)
    content, first = _store_document(context)
    replacement_blob = _blob(b"Replacement evidence text")
    context.repository.store_source_blob(
        replacement_blob,
        lineage=context.lineage,
        request=_request("replacement-blob"),
        content_bytes=b"Replacement evidence text",
    )
    replacement, metadata = _document_bundle(
        context.lineage,
        replacement_blob,
        document_id="supporting-document-2",
        request_token="replacement-document",
    )
    replacement = replacement.model_copy(
        update={
            "superseded_document": SupportingDocumentReference(
                lineage=context.lineage,
                document_id=first.document_id,
                content_sha256=first.source_blob_sha256,
            )
        }
    )
    context.repository.store_document(replacement, metadata, request=metadata.request)
    connection = sqlite3.connect(context.path)
    try:
        current = connection.execute(
            """SELECT document_id FROM preliminary_supporting_documents document
               WHERE NOT EXISTS (
                   SELECT 1 FROM preliminary_supporting_documents newer
                   WHERE newer.superseded_document_id = document.document_id
               )"""
        ).fetchall()
        assert current == [(replacement.document_id,)]
    finally:
        connection.close()
    assert context.repository.load_source_bytes(first.source_blob_id) == content


def test_request_replay_conflict_concurrency_and_transaction_rollback(
    tmp_path: Path,
) -> None:
    context = _prepare(tmp_path)
    content = b"idempotent bytes"
    blob = _blob(content)
    request = _request("same-token")
    first = context.repository.store_source_blob(
        blob,
        lineage=context.lineage,
        request=request,
        content_bytes=content,
    )
    replay = context.repository.store_source_blob(
        blob,
        lineage=context.lineage,
        request=request,
        content_bytes=content,
    )
    assert first.replayed is False
    assert replay.replayed is True
    restarted = SQLiteFormalEvidenceRepository(context.path, clock=lambda: NOW)
    restarted_replay = restarted.store_source_blob(
        blob,
        lineage=context.lineage,
        request=request,
        content_bytes=content,
    )
    assert restarted_replay.replayed is True
    conflicting_document, conflicting_metadata = _document_bundle(
        context.lineage,
        blob,
        document_id="cross-operation-document",
        request_token="same-token",
    )
    with pytest.raises(FormalEvidenceIdempotencyError):
        restarted.store_document(
            conflicting_document,
            conflicting_metadata,
            request=conflicting_metadata.request,
        )
    different = _blob(b"different bytes")
    with pytest.raises(FormalEvidenceIdempotencyError):
        context.repository.store_source_blob(
            different,
            lineage=context.lineage,
            request=request,
            content_bytes=b"different bytes",
        )

    concurrent_blob = _blob(b"concurrent bytes")
    concurrent_request = _request("concurrent-token")

    def duplicate_write():
        return context.repository.store_source_blob(
            concurrent_blob,
            lineage=context.lineage,
            request=concurrent_request,
            content_bytes=b"concurrent bytes",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: duplicate_write(), range(2)))
    assert sorted(item.replayed for item in outcomes) == [False, True]

    conflict_request = _request("concurrent-conflict")
    conflict_blobs = (_blob(b"conflict-a"), _blob(b"conflict-b"))

    def conflicting_write(item: SupportingSourceBlob):
        content_value = (
            b"conflict-a" if item is conflict_blobs[0] else b"conflict-b"
        )
        try:
            return context.repository.store_source_blob(
                item,
                lineage=context.lineage,
                request=conflict_request,
                content_bytes=content_value,
            )
        except FormalEvidenceIdempotencyError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        conflicting = list(pool.map(conflicting_write, conflict_blobs))
    assert sum(hasattr(item, "record") for item in conflicting) == 1
    assert sum(isinstance(item, FormalEvidenceIdempotencyError) for item in conflicting) == 1

    injected_path = tmp_path / "injected"
    injected_path.mkdir()
    baseline = _prepare(
        injected_path,
        failure_injector=lambda operation: (_ for _ in ()).throw(
            RuntimeError(f"injected after {operation}")
        ),
    )
    rollback_blob = _blob(b"rollback bytes")
    with pytest.raises(RuntimeError, match="injected"):
        baseline.repository.store_source_blob(
            rollback_blob,
            lineage=baseline.lineage,
            request=_request("rollback-token"),
            content_bytes=b"rollback bytes",
        )
    connection = sqlite3.connect(baseline.path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_source_blobs"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_source_blob_bytes"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_operation_requests"
        ).fetchone()[0] == 0
    finally:
        connection.close()

    bundle_path = tmp_path / "bundle-rollback"
    bundle_path.mkdir()

    def fail_bundle(operation: str) -> None:
        if operation == "STORE_EXTRACTION_BUNDLE":
            raise RuntimeError("injected bundle failure")

    bundle_context = _prepare(bundle_path, failure_injector=fail_bundle)
    _, bundle_document = _store_document(bundle_context)
    bundle_ingestion = _ingestion(bundle_context, bundle_document)
    bundle_proposal = _proposal(bundle_context, bundle_document)
    bundle_attempt = SupportingEvidenceExtractionAttempt(
        schema_version=SUPPORTING_EVIDENCE_EXTRACTION_ATTEMPT_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=bundle_context.lineage,
        attempt_id="extraction-1",
        attempt_number=1,
        document_id=bundle_document.document_id,
        document_content_sha256=bundle_document.source_blob_sha256,
        ingestion_attempt_id=bundle_ingestion.attempt_id,
        extractor=bundle_proposal.extractor,
        request=_request("extraction-1"),
        status=AttemptStatus.SUCCEEDED,
        proposal_ids=(bundle_proposal.proposal_id,),
        started_at=NOW,
        completed_at=NOW,
    )
    with pytest.raises(RuntimeError, match="bundle failure"):
        bundle_context.repository.store_extraction_bundle(
            bundle_attempt, (bundle_proposal,)
        )
    connection = sqlite3.connect(bundle_context.path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_extraction_attempts"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_evidence_proposals"
        ).fetchone()[0] == 0
        assert connection.execute(
            """SELECT COUNT(*) FROM preliminary_supporting_operation_requests
               WHERE request_token = 'extraction-1'"""
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_cross_lineage_mixed_process_and_unknown_contracts_fail_closed(
    tmp_path: Path,
) -> None:
    context = _prepare(tmp_path)
    content, document = _store_document(context)
    invalid_lineage = context.lineage.model_copy(
        update={"journey_id": "different-journey"}
    )
    other_blob = _blob(b"cross-lineage")
    with pytest.raises(FormalEvidenceLineageError):
        context.repository.store_source_blob(
            other_blob,
            lineage=invalid_lineage,
            request=_request("cross-lineage"),
            content_bytes=b"cross-lineage",
        )

    ingestion = _ingestion(context, document)
    _, proposal = _extraction(context, document, ingestion)
    review = _review(context, proposal)
    invalid_mapping = FormalInputMapping(
        schema_version=FORMAL_INPUT_MAPPING_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        mapping_id="mapping-invalid-activity",
        lineage=context.lineage,
        activity_id="not-in-approved-process",
        target=CriterionFormalTarget(
            kind=FormalTargetKind.CRITERION,
            criterion=CriterionName.REPETITION,
        ),
        disposition=MappingDisposition.MAPPED_FORMAL_INPUT,
        value=4,
        knowledge_state=KnowledgeState.KNOWN,
        approved_evidence_classification=EvidenceClassification.DOCUMENTED_FACT,
        supporting_reviews=(_review_reference(context, review),),
        mapping_rationale="Invalid activity should fail before persistence.",
        reviewer=_reviewer(),
        mapped_at=NOW,
        request=_request("invalid-activity"),
    )
    with pytest.raises(FormalEvidenceIntegrityError, match="approved process"):
        context.repository.append_formal_mapping(invalid_mapping)

    payload_json, payload_sha = serialize_formal_evidence_record(document)
    with pytest.raises(ArtifactCorruptionError, match="Unsupported"):
        deserialize_formal_evidence_record(
            "supporting-document.v9.9", payload_json, payload_sha
        )
    assert content == context.repository.load_source_bytes(document.source_blob_id)


def test_candidate_and_readiness_failures_leave_no_partial_history(
    tmp_path: Path,
) -> None:
    context = _prepare(tmp_path)
    _, document = _store_document(context)
    ingestion = _ingestion(context, document)
    extraction, proposal = _extraction(context, document, ingestion)
    review = _review(context, proposal)
    mapping = _mapping(context, review)
    candidate = FormalInputCandidateSet(
        schema_version=FORMAL_INPUT_CANDIDATE_SET_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        candidate_set_id="candidate-rollback",
        lineage=context.lineage,
        current_documents=(
            CandidateDocumentIdentity(
                document_id=document.document_id,
                content_sha256=document.source_blob_sha256,
                byte_size=document.byte_size,
                metadata_revision_id=document.initial_metadata_revision_id,
            ),
        ),
        current_extractions=(
            CandidateExtractionIdentity(
                extraction_attempt_id=extraction.attempt_id,
                document_id=document.document_id,
                status=extraction.status,
                proposal_ids=extraction.proposal_ids,
            ),
        ),
        current_reviews=(_review_reference(context, review),),
        ordered_formal_mappings=(mapping,),
        created_at=NOW,
        conversion_request=_request("candidate-rollback"),
    )

    def fail_candidate(operation: str) -> None:
        if operation == "APPEND_CANDIDATE_SET":
            raise RuntimeError("injected candidate failure")

    context.repository.failure_injector = fail_candidate
    with pytest.raises(RuntimeError, match="candidate failure"):
        context.repository.append_candidate_set(candidate)
    connection = sqlite3.connect(context.path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_formal_input_candidate_sets"
        ).fetchone()[0] == 0
        assert connection.execute(
            """SELECT COUNT(*) FROM preliminary_supporting_operation_requests
               WHERE request_token = 'candidate-rollback'"""
        ).fetchone()[0] == 0
    finally:
        connection.close()

    context.repository.failure_injector = None
    context.repository.append_candidate_set(candidate)
    readiness = FormalEvidenceReadiness(
        schema_version=FORMAL_EVIDENCE_READINESS_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        readiness_id="readiness-rollback",
        lineage=context.lineage,
        candidate_set=candidate,
        current_review_revision_ids=(review.revision_id,),
        processing_complete_or_explicitly_excluded=True,
        every_current_proposal_terminally_reviewed=True,
        every_accepted_or_corrected_item_mapped_or_context_only=True,
        candidate_set_includes_every_current_review_revision=True,
        lineage_and_integrity_valid=True,
        retained_unknown_count=0,
        retained_conflict_count=0,
        status=ReadinessStatus.READY_TO_ATTEMPT,
        evaluated_at=NOW,
    )

    def fail_readiness(operation: str) -> None:
        if operation == "APPEND_READINESS":
            raise RuntimeError("injected readiness failure")

    context.repository.failure_injector = fail_readiness
    with pytest.raises(RuntimeError, match="readiness failure"):
        context.repository.append_readiness(
            readiness,
            request=_request("readiness-rollback"),
        )
    connection = sqlite3.connect(context.path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_formal_evidence_readiness"
        ).fetchone()[0] == 0
        assert connection.execute(
            """SELECT COUNT(*) FROM preliminary_supporting_operation_requests
               WHERE request_token = 'readiness-rollback'"""
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_attempt_and_revision_predecessors_are_exact_and_stale_writes_fail(
    tmp_path: Path,
) -> None:
    context = _prepare(tmp_path)
    _, document = _store_document(context)
    first = _ingestion(context, document)
    retry = SupportingDocumentIngestionAttempt(
        schema_version=SUPPORTING_DOCUMENT_INGESTION_ATTEMPT_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=context.lineage,
        attempt_id="ingestion-2",
        attempt_number=2,
        document_id=document.document_id,
        document_content_sha256=document.source_blob_sha256,
        predecessor_attempt_id=first.attempt_id,
        request=_request("ingestion-2"),
        status=AttemptStatus.STARTED,
        started_at=NOW,
    )
    context.repository.append_ingestion_attempt(retry)
    stale_retry = retry.model_copy(
        update={
            "attempt_id": "ingestion-stale",
            "attempt_number": 3,
            "predecessor_attempt_id": first.attempt_id,
            "request": _request("ingestion-stale"),
        }
    )
    with pytest.raises(FormalEvidenceStaleWriteError, match="predecessor"):
        context.repository.append_ingestion_attempt(stale_retry)

    extraction, proposal = _extraction(context, document, first)
    retry_proposal = _proposal(context, document, "extraction-2")
    extraction_retry = SupportingEvidenceExtractionAttempt(
        schema_version=SUPPORTING_EVIDENCE_EXTRACTION_ATTEMPT_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=context.lineage,
        attempt_id="extraction-2",
        attempt_number=2,
        document_id=document.document_id,
        document_content_sha256=document.source_blob_sha256,
        ingestion_attempt_id=first.attempt_id,
        predecessor_attempt_id=extraction.attempt_id,
        extractor=retry_proposal.extractor,
        request=_request("extraction-2"),
        status=AttemptStatus.SUCCEEDED,
        proposal_ids=(retry_proposal.proposal_id,),
        started_at=NOW,
        completed_at=NOW,
    )
    with pytest.raises(FormalEvidenceIntegrityError, match="exactly match"):
        context.repository.store_extraction_bundle(extraction_retry, ())
    review = _review(context, proposal)
    corrected = SupportingEvidenceReviewRevision(
        schema_version=SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=context.lineage,
        proposal_id=proposal.proposal_id,
        revision_id="review-2",
        revision_number=2,
        prior_revision_id=review.revision_id,
        expected_prior_revision_id=review.revision_id,
        action=ReviewAction.CORRECT,
        original_proposal=proposal,
        approved_claim="The recorded monthly volume is 100.",
        source_spans=(proposal.primary_source_span,),
        selected_category=proposal.proposed_category,
        approved_classification=EvidenceClassification.DOCUMENTED_FACT,
        claim_directly_supported_by_excerpt=True,
        candidate_eligible=True,
        reviewer=_reviewer(),
        rationale="Wording clarified without changing the source excerpt.",
        reviewed_at=NOW,
        request=_request("review-2"),
    )
    context.repository.append_review_revision(corrected)
    stale = corrected.model_copy(
        update={
            "revision_id": "review-stale",
            "revision_number": 3,
            "request": _request("review-stale"),
        }
    )
    with pytest.raises(FormalEvidenceStaleWriteError, match="expected"):
        context.repository.append_review_revision(stale)

    event_one = FormalEvidenceWorkflowEvent(
        schema_version=FORMAL_EVIDENCE_WORKFLOW_EVENT_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        event_id="event-1",
        lineage=context.lineage,
        lifecycle_sequence=1,
        event_type=WorkflowEventType.EXTRACTION_ATTEMPT_RECORDED,
        subject_id=extraction.attempt_id,
        request=_request("event-1"),
        payload_sha256="a" * 64,
        occurred_at=NOW,
    )
    context.repository.append_workflow_event(event_one)
    stale_event = FormalEvidenceWorkflowEvent(
        schema_version=FORMAL_EVIDENCE_WORKFLOW_EVENT_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        event_id="event-3",
        lineage=context.lineage,
        lifecycle_sequence=3,
        prior_event_id=event_one.event_id,
        event_type=WorkflowEventType.REVIEW_REVISION_RECORDED,
        subject_id=corrected.revision_id,
        request=_request("event-3"),
        payload_sha256="b" * 64,
        occurred_at=NOW,
    )
    with pytest.raises(FormalEvidenceStaleWriteError, match="sequence"):
        context.repository.append_workflow_event(stale_event)


def test_inference_conflict_and_rejection_links_are_persisted_without_promotion(
    tmp_path: Path,
) -> None:
    context = _prepare(tmp_path)
    _, document = _store_document(context)
    ingestion = _ingestion(context, document)

    def distinct_proposal(
        claim: str,
        classification: EvidenceClassification,
    ) -> SupportingEvidenceProposal:
        base = _proposal(context, document, "extraction-many")
        values = base.model_dump(exclude={"proposal_id"})
        values["proposed_claim"] = claim
        values["proposed_classification"] = classification
        return SupportingEvidenceProposal(**values)

    fact_a = distinct_proposal(
        "Monthly volume is 100.", EvidenceClassification.DOCUMENTED_FACT
    )
    fact_b = distinct_proposal(
        "Monthly volume is reported every month.",
        EvidenceClassification.DOCUMENTED_FACT,
    )
    inferred = distinct_proposal(
        "The activity is highly repetitive.",
        EvidenceClassification.REVIEWED_INFERENCE,
    )
    conflicted = distinct_proposal(
        "The volume figure is disputed.", EvidenceClassification.CONFLICT
    )
    rejected_proposal = distinct_proposal(
        "The process is fully automated.", EvidenceClassification.REVIEWED_INFERENCE
    )
    proposals = (fact_a, fact_b, inferred, conflicted, rejected_proposal)
    attempt = SupportingEvidenceExtractionAttempt(
        schema_version=SUPPORTING_EVIDENCE_EXTRACTION_ATTEMPT_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=context.lineage,
        attempt_id="extraction-many",
        attempt_number=1,
        document_id=document.document_id,
        document_content_sha256=document.source_blob_sha256,
        ingestion_attempt_id=ingestion.attempt_id,
        extractor=fact_a.extractor,
        request=_request("extraction-many"),
        status=AttemptStatus.SUCCEEDED,
        proposal_ids=tuple(item.proposal_id for item in proposals),
        started_at=NOW,
        completed_at=NOW,
    )
    context.repository.store_extraction_bundle(attempt, proposals)

    def fact_review(
        proposal: SupportingEvidenceProposal, revision_id: str
    ) -> SupportingEvidenceReviewRevision:
        record = SupportingEvidenceReviewRevision(
            schema_version=SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
            contract_family=FORMAL_EVIDENCE_FAMILY,
            lineage=context.lineage,
            proposal_id=proposal.proposal_id,
            revision_id=revision_id,
            revision_number=1,
            action=ReviewAction.ACCEPT,
            original_proposal=proposal,
            approved_claim=proposal.proposed_claim,
            source_spans=(proposal.primary_source_span,),
            selected_category=proposal.proposed_category,
            approved_classification=EvidenceClassification.DOCUMENTED_FACT,
            claim_directly_supported_by_excerpt=True,
            candidate_eligible=True,
            reviewer=_reviewer(),
            rationale="Accepted as directly documented.",
            reviewed_at=NOW,
            request=_request(revision_id),
        )
        context.repository.append_review_revision(record)
        return record

    reviewed_a = fact_review(fact_a, "fact-a")
    reviewed_b = fact_review(fact_b, "fact-b")
    ref_a = _review_reference(context, reviewed_a)
    ref_b = _review_reference(context, reviewed_b)
    inference_review = SupportingEvidenceReviewRevision(
        schema_version=SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=context.lineage,
        proposal_id=inferred.proposal_id,
        revision_id="inference-review",
        revision_number=1,
        action=ReviewAction.ACCEPT,
        original_proposal=inferred,
        approved_claim=inferred.proposed_claim,
        source_spans=(inferred.primary_source_span,),
        selected_category=inferred.proposed_category,
        approved_classification=EvidenceClassification.REVIEWED_INFERENCE,
        claim_directly_supported_by_excerpt=False,
        inference_confidence=0.7,
        inference_documented_facts=(ref_a, ref_b),
        candidate_eligible=True,
        reviewer=_reviewer(),
        rationale="The two accepted facts support this reviewed inference.",
        reviewed_at=NOW,
        request=_request("inference-review"),
    )
    context.repository.append_review_revision(inference_review)
    conflict_review = SupportingEvidenceReviewRevision(
        schema_version=SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=context.lineage,
        proposal_id=conflicted.proposal_id,
        revision_id="conflict-review",
        revision_number=1,
        action=ReviewAction.MARK_UNRESOLVED,
        original_proposal=conflicted,
        approved_claim=conflicted.proposed_claim,
        source_spans=(conflicted.primary_source_span,),
        selected_category=conflicted.proposed_category,
        approved_classification=EvidenceClassification.CONFLICT,
        competing_evidence=(ref_a, ref_b),
        candidate_eligible=False,
        reviewer=_reviewer(),
        rationale="Two accepted records remain in conflict.",
        reviewed_at=NOW,
        request=_request("conflict-review"),
    )
    context.repository.append_review_revision(conflict_review)
    rejected = SupportingEvidenceReviewRevision(
        schema_version=SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=context.lineage,
        proposal_id=rejected_proposal.proposal_id,
        revision_id="rejected-review",
        revision_number=1,
        action=ReviewAction.REJECT,
        original_proposal=rejected_proposal,
        reviewer=_reviewer(),
        rationale="The proposal is not supported by the excerpt.",
        reviewed_at=NOW,
        request=_request("rejected-review"),
    )
    context.repository.append_review_revision(rejected)
    assert context.repository.load_record(
        inference_review.schema_version, inference_review.revision_id
    ) == inference_review
    assert context.repository.load_record(
        conflict_review.schema_version, conflict_review.revision_id
    ) == conflict_review
    stored_rejected = context.repository.load_record(
        rejected.schema_version, rejected.revision_id
    )
    assert stored_rejected == rejected
    assert rejected.approved_classification is None
    assert rejected.candidate_eligible is False


def test_frozen_workspace_rejection_preserves_database_bytes_and_sidecars(
    tmp_path: Path,
) -> None:
    context = _prepare(tmp_path / "writable")
    frozen_directory = tmp_path / "evaluation" / "portfolio" / "case"
    frozen_directory.mkdir(parents=True)
    frozen_path = frozen_directory / "workspace.db"
    shutil.copy2(context.path, frozen_path)

    def snapshot() -> dict[str, bytes]:
        return {
            item.name: item.read_bytes()
            for item in sorted(frozen_directory.iterdir())
            if item.is_file()
        }

    before = snapshot()
    with pytest.raises(FrozenEvaluationWorkspaceError):
        SQLiteFormalEvidenceRepository(frozen_path)
    assert snapshot() == before

    original_path = context.repository.path
    context.repository.path = frozen_path
    try:
        content = b"must never be written"
        blob = _blob(content)
        with pytest.raises(FrozenEvaluationWorkspaceError):
            context.repository.store_source_blob(
                blob,
                lineage=context.lineage,
                request=_request("frozen-write"),
                content_bytes=content,
            )
    finally:
        context.repository.path = original_path
    assert snapshot() == before

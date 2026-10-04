from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.formal_evidence import (
    CONTEXT_NOTE_SCHEMA,
    EXTERNAL_PROVIDER_CONSENT_SCHEMA,
    FORMAL_EVIDENCE_FAMILY,
    FORMAL_EVIDENCE_READINESS_SCHEMA,
    FORMAL_EVIDENCE_VERSION,
    FORMAL_EVIDENCE_WORKFLOW_EVENT_SCHEMA,
    FORMAL_INPUT_CANDIDATE_SET_SCHEMA,
    FORMAL_INPUT_MAPPING_SCHEMA,
    MAX_CURRENT_DOCUMENTS,
    MAX_EXTRACTED_CHARACTERS,
    MAX_FORMAL_LIFECYCLE_BYTES,
    MAX_PDF_PAGES,
    MAX_SUPPORTING_FILE_BYTES,
    REVIEWER_DECLARATION_SCHEMA,
    SUPPORTING_DOCUMENT_INGESTION_ATTEMPT_SCHEMA,
    SUPPORTING_DOCUMENT_METADATA_REVISION_SCHEMA,
    SUPPORTING_DOCUMENT_SCHEMA,
    SUPPORTING_EVIDENCE_EXTRACTION_ATTEMPT_SCHEMA,
    SUPPORTING_EVIDENCE_PROPOSAL_SCHEMA,
    SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
    SUPPORTING_SOURCE_BLOB_SCHEMA,
    ActivityEvidenceFormalTarget,
    AttemptStatus,
    CandidateDocumentIdentity,
    CandidateExtractionIdentity,
    CapabilitySignalFormalTarget,
    ContextNote,
    CoveredPeriod,
    CriterionFormalTarget,
    DocumentCategory,
    EvidenceClassification,
    ExcludedProposalReference,
    ExternalProviderConsent,
    ExtractorIdentity,
    FormalEvidenceLineage,
    FormalEvidenceReadiness,
    FormalEvidenceWorkflowEvent,
    FormalInputCandidateSet,
    FormalInputMapping,
    FormalTargetKind,
    HumanAccountabilityFormalTarget,
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
    SupportingFileRejectionCode,
    SupportingSourceBlob,
    SupportingSourceSpan,
    WorkflowEventType,
)
from ai_adoption_engine.models.four_gate_assessment import CapabilitySignalName


NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def lineage(**changes: object) -> FormalEvidenceLineage:
    values: dict[str, object] = {
        "formal_lifecycle_schema": "preliminary-formal-lifecycle.v0.1",
        "formal_lifecycle_id": "formal-1",
        "journey_id": "journey-1",
        "source_assessment_id": "assessment-1",
        "approved_review_artifact_id": "approved-review-1",
        "approved_review_schema_version": "phase4-v0.1",
        "approved_review_revision": 1,
        "approved_review_payload_sha256": HASH_A,
        "source_document_id": f"doc-{HASH_B}",
        "source_document_sha256": HASH_B,
        "validated_process_id": "process-1",
        "validated_process_fingerprint": HASH_C,
    }
    values.update(changes)
    return FormalEvidenceLineage(**values)


def request(token: str = "request-1") -> RequestIdentity:
    return RequestIdentity(request_token=token, canonical_request_sha256=HASH_A)


def reviewer() -> ReviewerDeclaration:
    return ReviewerDeclaration(
        schema_version=REVIEWER_DECLARATION_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        reviewer_display_name="Alex Reviewer",
        declared_organisational_role="Process owner",
        identity_and_authority_locally_declared_not_authenticated=True,
        declared_at=NOW,
    )


def extractor() -> ExtractorIdentity:
    return ExtractorIdentity(
        extractor_id="evidence-extractor",
        extractor_version="0.1.0",
        provider_id="provider",
        provider_version="2026-10",
        output_schema_id="proposal-output",
        output_schema_version="0.1.0",
        prompt_id="supporting-evidence",
        prompt_version="0.1.0",
    )


def span(**changes: object) -> SupportingSourceSpan:
    excerpt = "Monthly volume is 100."
    values: dict[str, object] = {
        "lineage": lineage(),
        "document_id": "supporting-doc-1",
        "document_content_sha256": HASH_A,
        "parsed_document_id": "parsed-1",
        "block_id": "block-1",
        "page_number": 1,
        "line_start": 4,
        "line_end_exclusive": 5,
        "document_character_start": 20,
        "document_character_end_exclusive": 20 + len(excerpt),
        "block_character_start": 0,
        "block_character_end_exclusive": len(excerpt),
        "exact_excerpt": excerpt,
        "excerpt_sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
        "locator": "page 1, line 4",
    }
    values.update(changes)
    return SupportingSourceSpan(**values)


def proposal(**changes: object) -> SupportingEvidenceProposal:
    values: dict[str, object] = {
        "schema_version": SUPPORTING_EVIDENCE_PROPOSAL_SCHEMA,
        "contract_family": FORMAL_EVIDENCE_FAMILY,
        "lineage": lineage(),
        "extraction_attempt_id": "extraction-1",
        "document_id": "supporting-doc-1",
        "document_content_sha256": HASH_A,
        "proposed_claim": "The monthly volume is 100.",
        "proposed_classification": EvidenceClassification.DOCUMENTED_FACT,
        "primary_source_span": span(),
        "proposed_category": DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
        "suggested_activity_ids": ("activity-1",),
        "suggested_formal_targets": (
            CriterionFormalTarget(
                kind=FormalTargetKind.CRITERION,
                criterion=CriterionName.REPETITION,
            ),
        ),
        "explanatory_gate_relevance": "SHOULD_WE_CHANGE",
        "ambiguity_indicated": False,
        "conflict_indicated": False,
        "relevance_explanation": "Volume may inform repetition after human review.",
        "extraction_confidence": 0.8,
        "extractor": extractor(),
    }
    values.update(changes)
    return SupportingEvidenceProposal(**values)


def fact_review(**changes: object) -> SupportingEvidenceReviewRevision:
    original = proposal()
    values: dict[str, object] = {
        "schema_version": SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
        "contract_family": FORMAL_EVIDENCE_FAMILY,
        "lineage": lineage(),
        "proposal_id": original.proposal_id,
        "revision_id": "review-1",
        "revision_number": 1,
        "action": ReviewAction.ACCEPT,
        "original_proposal": original,
        "approved_claim": original.proposed_claim,
        "source_spans": (original.primary_source_span,),
        "selected_category": DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
        "approved_classification": EvidenceClassification.DOCUMENTED_FACT,
        "claim_directly_supported_by_excerpt": True,
        "candidate_eligible": True,
        "reviewer": reviewer(),
        "rationale": "The excerpt states this fact directly.",
        "reviewed_at": NOW,
        "request": request(),
    }
    values.update(changes)
    return SupportingEvidenceReviewRevision(**values)


def fact_reference(review_id: str = "review-1") -> ReviewedEvidenceReference:
    return ReviewedEvidenceReference(
        lineage=lineage(),
        review_revision_id=review_id,
        proposal_id=proposal().proposal_id,
        action=ReviewAction.ACCEPT,
        classification=EvidenceClassification.DOCUMENTED_FACT,
    )


def mapping(**changes: object) -> FormalInputMapping:
    values: dict[str, object] = {
        "schema_version": FORMAL_INPUT_MAPPING_SCHEMA,
        "contract_family": FORMAL_EVIDENCE_FAMILY,
        "mapping_id": "mapping-1",
        "lineage": lineage(),
        "activity_id": "activity-1",
        "target": CriterionFormalTarget(
            kind=FormalTargetKind.CRITERION,
            criterion=CriterionName.REPETITION,
        ),
        "disposition": MappingDisposition.MAPPED_FORMAL_INPUT,
        "value": 4,
        "knowledge_state": KnowledgeState.KNOWN,
        "approved_evidence_classification": EvidenceClassification.DOCUMENTED_FACT,
        "supporting_reviews": (fact_reference(),),
        "mapping_rationale": "The reviewed fact supports the approved score.",
        "reviewer": reviewer(),
        "mapped_at": NOW,
        "request": request("mapping-request"),
    }
    values.update(changes)
    return FormalInputMapping(**values)


def candidate_set(**changes: object) -> FormalInputCandidateSet:
    values: dict[str, object] = {
        "schema_version": FORMAL_INPUT_CANDIDATE_SET_SCHEMA,
        "contract_family": FORMAL_EVIDENCE_FAMILY,
        "candidate_set_id": "candidate-1",
        "lineage": lineage(),
        "current_documents": (
            CandidateDocumentIdentity(
                document_id="supporting-doc-1",
                content_sha256=HASH_A,
                byte_size=100,
                metadata_revision_id="metadata-1",
            ),
        ),
        "current_extractions": (
            CandidateExtractionIdentity(
                extraction_attempt_id="extraction-1",
                document_id="supporting-doc-1",
                status=AttemptStatus.SUCCEEDED,
                proposal_ids=(proposal().proposal_id,),
            ),
        ),
        "current_reviews": (fact_reference(),),
        "ordered_formal_mappings": (mapping(),),
        "created_at": NOW,
        "conversion_request": request("conversion-request"),
    }
    values.update(changes)
    return FormalInputCandidateSet(**values)


def test_contract_identity_catalogue_and_limits_are_exact() -> None:
    assert FORMAL_EVIDENCE_FAMILY == "preliminary-formal-evidence.v0.1"
    assert FORMAL_EVIDENCE_VERSION == "0.1.0"
    assert {
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
        REVIEWER_DECLARATION_SCHEMA,
        EXTERNAL_PROVIDER_CONSENT_SCHEMA,
        CONTEXT_NOTE_SCHEMA,
    } == {
        "supporting-source-blob.v0.1",
        "supporting-document.v0.1",
        "supporting-document-metadata-revision.v0.1",
        "supporting-document-ingestion-attempt.v0.1",
        "supporting-evidence-extraction-attempt.v0.1",
        "supporting-evidence-proposal.v0.1",
        "supporting-evidence-review-revision.v0.1",
        "formal-input-mapping.v0.1",
        "formal-input-candidate-set.v0.1",
        "formal-evidence-readiness.v0.1",
        "formal-evidence-workflow-event.v0.1",
        "reviewer-declaration.v0.1",
        "external-provider-consent.v0.1",
        "context-note.v0.1",
    }
    assert MAX_SUPPORTING_FILE_BYTES == 10 * 1024 * 1024
    assert MAX_PDF_PAGES == 200
    assert MAX_EXTRACTED_CHARACTERS == 1_000_000
    assert MAX_CURRENT_DOCUMENTS == 20
    assert MAX_FORMAL_LIFECYCLE_BYTES == 50 * 1024 * 1024
    assert {item.value for item in DocumentCategory} == {
        "process volumes and frequency",
        "systems and integrations",
        "data availability and quality",
        "risks and controls",
        "ownership and accountability",
        "legal, policy, security, or operational constraints",
        "cost, effort, service-level, or performance information",
        "other organisational evidence",
    }


def test_contracts_are_frozen_extra_forbidden_canonical_and_utc_only() -> None:
    model = reviewer()
    assert model.model_config["frozen"] is True
    assert model.model_config["extra"] == "forbid"
    assert model.canonical_json_bytes() == model.canonical_json_bytes()
    with pytest.raises(ValidationError):
        ReviewerDeclaration(**{**model.model_dump(), "unexpected": True})
    with pytest.raises(ValidationError):
        model.reviewer_display_name = "Changed"  # type: ignore[misc]
    with pytest.raises(ValidationError, match="UTC"):
        ReviewerDeclaration(**{**model.model_dump(), "declared_at": NOW.replace(tzinfo=None)})
    with pytest.raises(ValidationError, match="UTC"):
        ReviewerDeclaration(
            **{
                **model.model_dump(),
                "declared_at": NOW.astimezone(timezone(timedelta(hours=1))),
            }
        )


def test_lineage_is_exact_content_pinned_and_evaluator_independent() -> None:
    exact = lineage()
    assert "evaluator" not in type(exact).model_fields
    with pytest.raises(ValidationError):
        lineage(formal_lifecycle_schema="preliminary-formal-lifecycle.v0.2")
    with pytest.raises(ValidationError, match="must match"):
        lineage(source_document_id=f"doc-{HASH_A}")
    with pytest.raises(ValidationError):
        lineage(approved_review_payload_sha256="not-a-hash")
    with pytest.raises(ValidationError, match="exact lineage"):
        proposal(
            primary_source_span=span(
                lineage=lineage(journey_id="different-journey")
            )
        )


def test_blob_acceptance_and_closed_rejection_codes() -> None:
    accepted = SupportingSourceBlob(
        schema_version=SUPPORTING_SOURCE_BLOB_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        source_blob_id=f"blob-{HASH_A}",
        content_sha256=HASH_A,
        byte_size=MAX_SUPPORTING_FILE_BYTES,
        detected_media_type="application/pdf",
        original_filename="evidence.pdf",
        state=SourceBlobState.ACCEPTED,
        created_at=NOW,
    )
    assert accepted.rejection_code is None
    assert {item.value for item in SupportingFileRejectionCode} >= {
        "UNSUPPORTED_FILE_TYPE",
        "FILE_TOO_LARGE",
        "ENCRYPTED",
        "SCANNED_OR_NO_TEXT",
        "ACTIVE_CONTENT",
        "MALFORMED",
        "EXECUTABLE",
        "ARCHIVE",
        "WORD_DOCUMENT",
        "SPREADSHEET",
        "PRESENTATION",
    }
    with pytest.raises(ValidationError):
        SupportingSourceBlob(
            **{
                **accepted.model_dump(),
                "byte_size": MAX_SUPPORTING_FILE_BYTES + 1,
            }
        )
    with pytest.raises(ValidationError):
        SupportingSourceBlob(**{**accepted.model_dump(), "detected_media_type": "image/png"})
    rejected = SupportingSourceBlob(
        **{
            **accepted.model_dump(),
            "state": SourceBlobState.REJECTED,
            "rejection_code": SupportingFileRejectionCode.ENCRYPTED,
        }
    )
    assert rejected.state is SourceBlobState.REJECTED


def test_document_supersession_and_metadata_revision_are_immutable_snapshots() -> None:
    previous = SupportingDocumentReference(
        lineage=lineage(), document_id="document-0", content_sha256=HASH_C
    )
    document = SupportingDocument(
        schema_version=SUPPORTING_DOCUMENT_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        document_id="document-1",
        lineage=lineage(),
        source_blob_id=f"blob-{HASH_A}",
        source_blob_sha256=HASH_A,
        original_filename="evidence.txt",
        media_type="text/plain",
        byte_size=100,
        initial_metadata_revision_id="metadata-1",
        superseded_document=previous,
        submitter=reviewer(),
        created_at=NOW,
    )
    assert document.superseded_document.document_id == "document-0"
    with pytest.raises(ValidationError, match="cannot supersede itself"):
        SupportingDocument(
            **{
                **document.model_dump(),
                "superseded_document": {
                    **previous.model_dump(),
                    "document_id": "document-1",
                },
            }
        )
    revision = SupportingDocumentMetadataRevision(
        schema_version=SUPPORTING_DOCUMENT_METADATA_REVISION_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=lineage(),
        document_id="document-1",
        revision_id="metadata-1",
        revision_number=1,
        description="Monthly operating report",
        primary_category=DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
        additional_categories=(DocumentCategory.SYSTEMS_AND_INTEGRATIONS,),
        covered_period=CoveredPeriod(
            starts_on=date(2026, 1, 1), ends_on=date(2026, 9, 30)
        ),
        request=request(),
        revised_at=NOW,
    )
    assert revision.prior_revision_id is None
    with pytest.raises(ValidationError):
        SupportingDocumentMetadataRevision(
            **{**revision.model_dump(), "revision_number": 2}
        )


def test_reviewer_declaration_and_external_consent_are_explicit() -> None:
    with pytest.raises(ValidationError):
        ReviewerDeclaration(
            **{
                **reviewer().model_dump(),
                "identity_and_authority_locally_declared_not_authenticated": False,
            }
        )
    with pytest.raises(ValidationError, match="blank"):
        ReviewerDeclaration(**{**reviewer().model_dump(), "reviewer_display_name": "  "})
    denied = ExternalProviderConsent(
        schema_version=EXTERNAL_PROVIDER_CONSENT_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=lineage(),
        document_id="document-1",
        provider_id="provider",
        provider_version="1",
        disclosure_text="This document would be sent to provider.",
        disclosure_version="1",
        explicit_consent=False,
        declarant_name="Alex Reviewer",
        declared_at=NOW,
    )
    assert denied.external_transmission_permitted is False
    with pytest.raises(ValidationError):
        ExternalProviderConsent(**{**denied.model_dump(), "explicit_consent": "yes"})
    with pytest.raises(ValidationError, match="declarant"):
        ExternalProviderConsent(
            **{
                **denied.model_dump(),
                "declarant_name": None,
                "local_session_identity": None,
            }
        )
    approved = ExternalProviderConsent(
        **{**denied.model_dump(), "explicit_consent": True}
    )
    assert approved.external_transmission_permitted is True


@pytest.mark.parametrize(
    ("status", "parsed", "completed"),
    [
        (AttemptStatus.STARTED, None, None),
        (AttemptStatus.SUCCEEDED, "parsed", NOW),
        (AttemptStatus.PARTIAL, "parsed", NOW),
        (AttemptStatus.FAILED, None, NOW),
        (AttemptStatus.INTERRUPTED, None, NOW),
        (AttemptStatus.ABANDONED, None, NOW),
    ],
)
def test_ingestion_attempt_states(
    status: AttemptStatus, parsed: str | None, completed: datetime | None
) -> None:
    parsed_document = None
    if parsed:
        parsed_document = ParsedDocumentIdentity(
            parsed_document_id=parsed,
            parsed_document_sha256=HASH_A,
            page_count=MAX_PDF_PAGES,
            extracted_character_count=MAX_EXTRACTED_CHARACTERS,
        )
    attempt = SupportingDocumentIngestionAttempt(
        schema_version=SUPPORTING_DOCUMENT_INGESTION_ATTEMPT_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=lineage(),
        attempt_id="ingestion-1",
        attempt_number=1,
        document_id="document-1",
        document_content_sha256=HASH_A,
        request=request(),
        status=status,
        parsed_document=parsed_document,
        started_at=NOW,
        completed_at=completed,
    )
    assert attempt.status is status


@pytest.mark.parametrize("status", list(AttemptStatus))
def test_extraction_attempt_states_and_retry_lineage(status: AttemptStatus) -> None:
    terminal = status is not AttemptStatus.STARTED
    proposals = (proposal().proposal_id,) if status is AttemptStatus.SUCCEEDED else ()
    attempt = SupportingEvidenceExtractionAttempt(
        schema_version=SUPPORTING_EVIDENCE_EXTRACTION_ATTEMPT_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=lineage(),
        attempt_id="extraction-1",
        attempt_number=2,
        predecessor_attempt_id="extraction-0",
        document_id="document-1",
        document_content_sha256=HASH_A,
        ingestion_attempt_id="ingestion-1",
        extractor=extractor(),
        request=request(),
        status=status,
        proposal_ids=proposals,
        started_at=NOW,
        completed_at=NOW if terminal else None,
    )
    assert attempt.predecessor_attempt_id == "extraction-0"


def test_exact_source_span_requires_hash_and_consistent_half_open_offsets() -> None:
    valid = span()
    assert valid.document_character_end_exclusive - valid.document_character_start == len(
        valid.exact_excerpt
    )
    with pytest.raises(ValidationError, match="offset length"):
        span(document_character_end_exclusive=999)
    with pytest.raises(ValidationError, match="excerpt_sha256"):
        span(excerpt_sha256=HASH_A)
    with pytest.raises(ValidationError, match="line range"):
        span(line_start=5, line_end_exclusive=5)


def test_proposal_id_is_content_derived_and_formal_values_are_forbidden() -> None:
    first = proposal()
    second = proposal()
    assert first.proposal_id == second.proposal_id
    assert first.canonical_json_bytes() == second.canonical_json_bytes()
    changed = proposal(proposed_claim="The monthly volume is approximately 100.")
    assert changed.proposal_id != first.proposal_id
    with pytest.raises(ValidationError):
        SupportingEvidenceProposal(**{**first.model_dump(), "formal_value": 4})
    with pytest.raises(ValidationError, match="derived"):
        SupportingEvidenceProposal(**{**first.model_dump(), "proposal_id": f"proposal-{HASH_A}"})


def test_review_actions_fact_correction_inference_unknown_conflict_and_rejection() -> None:
    assert fact_review().approved_classification is EvidenceClassification.DOCUMENTED_FACT
    corrected = fact_review(
        action=ReviewAction.CORRECT,
        approved_claim="Monthly volume is exactly 100.",
    )
    assert corrected.source_spans == fact_review().source_spans
    with pytest.raises(ValidationError, match="directly supported"):
        fact_review(
            action=ReviewAction.CORRECT,
            approved_claim="Monthly volume exceeds 100.",
            claim_directly_supported_by_excerpt=False,
        )
    inference = fact_review(
        revision_id="review-inference",
        approved_classification=EvidenceClassification.REVIEWED_INFERENCE,
        claim_directly_supported_by_excerpt=False,
        inference_confidence=0.7,
        inference_documented_facts=(fact_reference(),),
    )
    assert inference.inference_confidence == 0.7
    with pytest.raises(ValidationError, match="documented-fact links"):
        fact_review(
            approved_classification=EvidenceClassification.REVIEWED_INFERENCE,
            claim_directly_supported_by_excerpt=False,
            inference_confidence=0.7,
        )
    unresolved_unknown = fact_review(
        revision_id="review-unknown",
        action=ReviewAction.MARK_UNRESOLVED,
        approved_classification=EvidenceClassification.UNKNOWN,
        claim_directly_supported_by_excerpt=None,
        candidate_eligible=False,
    )
    assert unresolved_unknown.inference_confidence is None
    conflict = fact_review(
        revision_id="review-conflict",
        action=ReviewAction.MARK_UNRESOLVED,
        approved_classification=EvidenceClassification.CONFLICT,
        claim_directly_supported_by_excerpt=None,
        competing_evidence=(fact_reference("fact-a"), fact_reference("fact-b")),
        candidate_eligible=False,
    )
    assert len(conflict.competing_evidence) == 2
    rejected = fact_review(
        revision_id="review-rejected",
        action=ReviewAction.REJECT,
        approved_claim=None,
        source_spans=(),
        selected_category=None,
        approved_classification=None,
        claim_directly_supported_by_excerpt=None,
        candidate_eligible=False,
    )
    assert (
        rejected.original_proposal.proposed_classification
        is EvidenceClassification.DOCUMENTED_FACT
    )
    with pytest.raises(ValidationError, match="audit-only"):
        fact_review(action=ReviewAction.REJECT)


def test_context_note_can_never_claim_documentary_or_formal_evidence() -> None:
    note = ContextNote(
        schema_version=CONTEXT_NOTE_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        context_note_id="context-1",
        lineage=lineage(),
        activity_id="activity-1",
        statement="The team expects demand to grow.",
        origin="HUMAN_SUPPLIED_CONTEXT_ONLY",
        reviewer=reviewer(),
        created_at=NOW,
        request=request(),
    )
    assert note.source_spans == ()
    assert note.formal_value is None
    assert note.candidate_eligible is False
    with pytest.raises(ValidationError):
        ContextNote(**{**note.model_dump(), "formal_value": 3})


@pytest.mark.parametrize("criterion", list(CriterionName))
def test_every_existing_criterion_is_an_exact_closed_target(criterion: CriterionName) -> None:
    target = CriterionFormalTarget(kind=FormalTargetKind.CRITERION, criterion=criterion)
    assert target.criterion is criterion


@pytest.mark.parametrize("signal", list(CapabilitySignalName))
def test_every_existing_capability_signal_is_an_exact_closed_target(
    signal: CapabilitySignalName,
) -> None:
    target = CapabilitySignalFormalTarget(
        kind=FormalTargetKind.CAPABILITY_SIGNAL, capability_signal=signal
    )
    assert target.capability_signal is signal


def test_mapping_target_value_combinations_are_strict() -> None:
    assert mapping().value == 4
    accountability = mapping(
        target=HumanAccountabilityFormalTarget(
            kind=FormalTargetKind.HUMAN_ACCOUNTABILITY_REQUIRED
        ),
        value=True,
    )
    assert accountability.value is True
    capability = mapping(
        target=CapabilitySignalFormalTarget(
            kind=FormalTargetKind.CAPABILITY_SIGNAL,
            capability_signal=CapabilitySignalName.CATEGORISES_ITEMS,
        ),
        value=False,
    )
    assert capability.value is False
    activity = mapping(
        target=ActivityEvidenceFormalTarget(kind=FormalTargetKind.ACTIVITY_EVIDENCE),
        value=None,
    )
    assert activity.value is None
    with pytest.raises(ValidationError, match="strict integers"):
        mapping(value=True)
    with pytest.raises(ValidationError, match="strict booleans"):
        mapping(
            target=HumanAccountabilityFormalTarget(
                kind=FormalTargetKind.HUMAN_ACCOUNTABILITY_REQUIRED
            ),
            value=1,
        )
    with pytest.raises(ValidationError, match="scalar"):
        mapping(
            target=ActivityEvidenceFormalTarget(kind=FormalTargetKind.ACTIVITY_EVIDENCE),
            value=2,
        )
    inference = mapping(
        knowledge_state=KnowledgeState.INFERRED,
        approved_evidence_classification=EvidenceClassification.REVIEWED_INFERENCE,
        supporting_reviews=(
            ReviewedEvidenceReference(
                lineage=lineage(),
                review_revision_id="review-inference",
                proposal_id=proposal().proposal_id,
                action=ReviewAction.ACCEPT,
                classification=EvidenceClassification.REVIEWED_INFERENCE,
            ),
        ),
        supporting_documented_fact_review_ids=("review-1",),
        inference_confidence=0.6,
    )
    assert inference.inference_confidence == 0.6
    unknown = mapping(
        value=None,
        knowledge_state=KnowledgeState.UNKNOWN,
        approved_evidence_classification=EvidenceClassification.UNKNOWN,
        supporting_reviews=(
            ReviewedEvidenceReference(
                lineage=lineage(),
                review_revision_id="review-unknown",
                proposal_id=proposal().proposal_id,
                action=ReviewAction.ACCEPT,
                classification=EvidenceClassification.UNKNOWN,
            ),
        ),
    )
    assert unknown.value is None
    context = mapping(
        target=None,
        disposition=MappingDisposition.CONTEXT_ONLY,
        value=None,
        knowledge_state=KnowledgeState.UNKNOWN,
        approved_evidence_classification=None,
        inference_confidence=None,
    )
    assert context.target is None
    rejected = ReviewedEvidenceReference(
        lineage=lineage(),
        review_revision_id="review-rejected",
        proposal_id=proposal().proposal_id,
        action=ReviewAction.REJECT,
    )
    with pytest.raises(ValidationError, match="Rejected|rejected"):
        mapping(supporting_reviews=(rejected,))


def test_candidate_snapshot_enforces_lineage_uniqueness_limits_and_staleness_inputs() -> None:
    snapshot = candidate_set()
    assert snapshot.current_documents[0].metadata_revision_id == "metadata-1"
    changed = candidate_set(
        candidate_set_id="candidate-2",
        prior_candidate_set_id="candidate-1",
        current_documents=(
            CandidateDocumentIdentity(
                document_id="supporting-doc-1",
                content_sha256=HASH_A,
                byte_size=100,
                metadata_revision_id="metadata-2",
            ),
        ),
    )
    assert changed.canonical_json_bytes() != snapshot.canonical_json_bytes()
    with pytest.raises(ValidationError, match="unique"):
        candidate_set(current_reviews=(fact_reference(), fact_reference()))
    oversized_documents = tuple(
        CandidateDocumentIdentity(
            document_id=f"doc-{index}",
            content_sha256=HASH_A,
            byte_size=1,
            metadata_revision_id=f"metadata-{index}",
        )
        for index in range(MAX_CURRENT_DOCUMENTS + 1)
    )
    with pytest.raises(ValidationError, match="current-document limit"):
        candidate_set(current_documents=oversized_documents, current_extractions=())
    too_many_bytes = tuple(
        CandidateDocumentIdentity(
            document_id=f"doc-{index}",
            content_sha256=HASH_A,
            byte_size=MAX_SUPPORTING_FILE_BYTES,
            metadata_revision_id=f"metadata-{index}",
        )
        for index in range(6)
    )
    with pytest.raises(ValidationError, match="lifecycle byte limit"):
        candidate_set(
            current_documents=too_many_bytes,
            current_extractions=(),
            current_reviews=(),
            ordered_formal_mappings=(),
        )


def test_readiness_is_deterministic_and_category_gaps_are_warnings_only() -> None:
    ready = FormalEvidenceReadiness(
        schema_version=FORMAL_EVIDENCE_READINESS_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        readiness_id="readiness-1",
        lineage=lineage(),
        candidate_set=candidate_set(),
        current_review_revision_ids=("review-1",),
        processing_complete_or_explicitly_excluded=True,
        every_current_proposal_terminally_reviewed=True,
        every_accepted_or_corrected_item_mapped_or_context_only=True,
        candidate_set_includes_every_current_review_revision=True,
        lineage_and_integrity_valid=True,
        uncovered_document_categories=tuple(DocumentCategory),
        retained_unknown_count=0,
        retained_conflict_count=0,
        status=ReadinessStatus.READY_TO_ATTEMPT,
        evaluated_at=NOW,
    )
    assert ready.status is ReadinessStatus.READY_TO_ATTEMPT
    with pytest.raises(ValidationError, match="processing-complete"):
        FormalEvidenceReadiness(
            **{
                **ready.model_dump(),
                "processing_complete_or_explicitly_excluded": False,
            }
        )
    incomplete_candidate = candidate_set(
        current_extractions=(), current_reviews=(), ordered_formal_mappings=()
    )
    not_ready = FormalEvidenceReadiness(
        **{
            **ready.model_dump(),
            "candidate_set": incomplete_candidate.model_dump(),
            "current_review_revision_ids": (),
            "processing_complete_or_explicitly_excluded": False,
            "status": ReadinessStatus.NOT_READY,
            "reasons": ("processing is incomplete",),
        }
    )
    assert not_ready.reasons
    with pytest.raises(ValidationError, match="mapping-coverage|deterministic"):
        FormalEvidenceReadiness(
            **{
                **ready.model_dump(),
                "candidate_set": candidate_set(ordered_formal_mappings=()).model_dump(),
            }
        )


def test_each_readiness_condition_can_independently_keep_a_snapshot_not_ready() -> None:
    def not_ready(
        snapshot: FormalInputCandidateSet,
        *,
        current_review_ids: tuple[str, ...],
        processing: bool,
        terminal: bool,
        mapping_coverage: bool,
        review_coverage: bool,
        integrity: bool,
        reason: str,
    ) -> FormalEvidenceReadiness:
        return FormalEvidenceReadiness(
            schema_version=FORMAL_EVIDENCE_READINESS_SCHEMA,
            contract_family=FORMAL_EVIDENCE_FAMILY,
            readiness_id=f"readiness-{reason}",
            lineage=lineage(),
            candidate_set=snapshot,
            current_review_revision_ids=current_review_ids,
            processing_complete_or_explicitly_excluded=processing,
            every_current_proposal_terminally_reviewed=terminal,
            every_accepted_or_corrected_item_mapped_or_context_only=mapping_coverage,
            candidate_set_includes_every_current_review_revision=review_coverage,
            lineage_and_integrity_valid=integrity,
            retained_unknown_count=0,
            retained_conflict_count=0,
            status=ReadinessStatus.NOT_READY,
            reasons=(reason,),
            evaluated_at=NOW,
        )

    unprocessed = candidate_set(
        current_extractions=(), current_reviews=(), ordered_formal_mappings=()
    )
    assert not_ready(
        unprocessed,
        current_review_ids=(),
        processing=False,
        terminal=True,
        mapping_coverage=True,
        review_coverage=True,
        integrity=True,
        reason="processing",
    ).status is ReadinessStatus.NOT_READY

    unreviewed = candidate_set(current_reviews=(), ordered_formal_mappings=())
    assert not_ready(
        unreviewed,
        current_review_ids=(),
        processing=True,
        terminal=False,
        mapping_coverage=True,
        review_coverage=True,
        integrity=True,
        reason="terminal-review",
    ).status is ReadinessStatus.NOT_READY

    unmapped = candidate_set(ordered_formal_mappings=())
    assert not_ready(
        unmapped,
        current_review_ids=("review-1",),
        processing=True,
        terminal=True,
        mapping_coverage=False,
        review_coverage=True,
        integrity=True,
        reason="mapping-coverage",
    ).status is ReadinessStatus.NOT_READY

    no_positive_value = candidate_set(
        ordered_formal_mappings=(),
        context_only_review_revision_ids=("review-1",),
    )
    assert not_ready(
        no_positive_value,
        current_review_ids=("review-1",),
        processing=True,
        terminal=True,
        mapping_coverage=True,
        review_coverage=True,
        integrity=True,
        reason="positive-mapped-value",
    ).status is ReadinessStatus.NOT_READY

    assert not_ready(
        candidate_set(),
        current_review_ids=(),
        processing=True,
        terminal=True,
        mapping_coverage=True,
        review_coverage=False,
        integrity=True,
        reason="current-review-coverage",
    ).status is ReadinessStatus.NOT_READY
    assert not_ready(
        candidate_set(),
        current_review_ids=("review-1",),
        processing=True,
        terminal=True,
        mapping_coverage=True,
        review_coverage=True,
        integrity=False,
        reason="lineage-integrity",
    ).status is ReadinessStatus.NOT_READY


def test_workflow_event_uses_lifecycle_local_sequence_and_request_identity() -> None:
    event = FormalEvidenceWorkflowEvent(
        schema_version=FORMAL_EVIDENCE_WORKFLOW_EVENT_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        event_id="event-1",
        lineage=lineage(),
        lifecycle_sequence=1,
        event_type=WorkflowEventType.DOCUMENT_CREATED,
        subject_id="document-1",
        request=request(),
        payload_sha256=HASH_A,
        occurred_at=NOW,
    )
    assert event.prior_event_id is None
    with pytest.raises(ValidationError, match="first"):
        FormalEvidenceWorkflowEvent(
            **{**event.model_dump(), "lifecycle_sequence": 2}
        )


def test_rejected_and_excluded_proposals_remain_separate_snapshot_audit_items() -> None:
    excluded = ExcludedProposalReference(
        proposal_id=proposal().proposal_id,
        reason="Reviewer rejected the proposal.",
    )
    snapshot = candidate_set(
        current_reviews=(),
        ordered_formal_mappings=(),
        rejected_or_excluded_proposals=(excluded,),
    )
    assert snapshot.rejected_or_excluded_proposals == (excluded,)

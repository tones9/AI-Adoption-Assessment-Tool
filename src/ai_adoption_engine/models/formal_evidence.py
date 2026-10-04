"""Frozen, persistence-free contracts for reviewed formal supporting evidence.

These contracts describe data and invariants only.  They deliberately contain no
storage, extraction, provider, review-workflow, conversion, or engine behaviour.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.four_gate_assessment import (
    CapabilitySignalName,
    FourGateName,
)


FORMAL_EVIDENCE_FAMILY = "preliminary-formal-evidence.v0.1"
FORMAL_EVIDENCE_VERSION = "0.1.0"

SUPPORTING_SOURCE_BLOB_SCHEMA = "supporting-source-blob.v0.1"
SUPPORTING_DOCUMENT_SCHEMA = "supporting-document.v0.1"
SUPPORTING_DOCUMENT_METADATA_REVISION_SCHEMA = (
    "supporting-document-metadata-revision.v0.1"
)
SUPPORTING_DOCUMENT_INGESTION_ATTEMPT_SCHEMA = (
    "supporting-document-ingestion-attempt.v0.1"
)
SUPPORTING_EVIDENCE_EXTRACTION_ATTEMPT_SCHEMA = (
    "supporting-evidence-extraction-attempt.v0.1"
)
SUPPORTING_EVIDENCE_PROPOSAL_SCHEMA = "supporting-evidence-proposal.v0.1"
SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA = (
    "supporting-evidence-review-revision.v0.1"
)
FORMAL_INPUT_MAPPING_SCHEMA = "formal-input-mapping.v0.1"
FORMAL_INPUT_CANDIDATE_SET_SCHEMA = "formal-input-candidate-set.v0.1"
FORMAL_EVIDENCE_READINESS_SCHEMA = "formal-evidence-readiness.v0.1"
FORMAL_EVIDENCE_WORKFLOW_EVENT_SCHEMA = "formal-evidence-workflow-event.v0.1"
REVIEWER_DECLARATION_SCHEMA = "reviewer-declaration.v0.1"
EXTERNAL_PROVIDER_CONSENT_SCHEMA = "external-provider-consent.v0.1"
CONTEXT_NOTE_SCHEMA = "context-note.v0.1"

FORMAL_LIFECYCLE_SCHEMA = "preliminary-formal-lifecycle.v0.1"
MAX_SUPPORTING_FILE_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 200
MAX_EXTRACTED_CHARACTERS = 1_000_000
MAX_CURRENT_DOCUMENTS = 20
MAX_FORMAL_LIFECYCLE_BYTES = 50 * 1024 * 1024
SUPPORTED_MEDIA_TYPES = frozenset({"application/pdf", "text/plain"})

_SHA256_PATTERN = r"^[0-9a-f]{64}$"


def _canonical_json_bytes(value: Any) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _content_id(prefix: str, value: Any) -> str:
    return f"{prefix}-{hashlib.sha256(_canonical_json_bytes(value)).hexdigest()}"


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def require_utc_timestamps(self) -> Self:
        for field_name in self.__class__.model_fields:
            value = getattr(self, field_name)
            if isinstance(value, datetime) and (
                value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
            ):
                raise ValueError(f"{field_name} must be an explicit UTC timestamp")
        return self

    def canonical_json_bytes(self) -> bytes:
        """Return stable semantic JSON bytes for hashing and persistence later."""

        return _canonical_json_bytes(self)


class FormalEvidenceLineage(_FrozenContract):
    formal_lifecycle_schema: Literal["preliminary-formal-lifecycle.v0.1"]
    formal_lifecycle_id: str = Field(min_length=1)
    journey_id: str = Field(min_length=1)
    source_assessment_id: str = Field(min_length=1)
    approved_review_artifact_id: str = Field(min_length=1)
    approved_review_schema_version: Literal["phase4-v0.1"]
    approved_review_revision: int = Field(ge=1)
    approved_review_payload_sha256: str = Field(pattern=_SHA256_PATTERN)
    source_document_id: str = Field(pattern=r"^doc-[0-9a-f]{64}$")
    source_document_sha256: str = Field(pattern=_SHA256_PATTERN)
    validated_process_id: str = Field(min_length=1)
    validated_process_fingerprint: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def require_content_derived_source_document_id(self) -> Self:
        if self.source_document_id != f"doc-{self.source_document_sha256}":
            raise ValueError("source_document_id must match source_document_sha256")
        return self


class RequestIdentity(_FrozenContract):
    request_token: str = Field(min_length=1)
    canonical_request_sha256: str = Field(pattern=_SHA256_PATTERN)


class ReviewerDeclaration(_FrozenContract):
    schema_version: Literal["reviewer-declaration.v0.1"]
    contract_family: Literal["preliminary-formal-evidence.v0.1"]
    reviewer_display_name: str = Field(min_length=1)
    declared_organisational_role: str = Field(min_length=1)
    identity_and_authority_locally_declared_not_authenticated: Literal[True]
    declared_at: datetime
    local_session_identity: str | None = Field(default=None, min_length=1)

    @field_validator("reviewer_display_name", "declared_organisational_role")
    @classmethod
    def reject_blank_declarations(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reviewer declarations cannot be blank")
        return value


class SourceBlobState(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class SupportingFileRejectionCode(StrEnum):
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    PDF_PAGE_LIMIT_EXCEEDED = "PDF_PAGE_LIMIT_EXCEEDED"
    EXTRACTED_CHARACTER_LIMIT_EXCEEDED = "EXTRACTED_CHARACTER_LIMIT_EXCEEDED"
    ENCRYPTED = "ENCRYPTED"
    SCANNED_OR_NO_TEXT = "SCANNED_OR_NO_TEXT"
    ACTIVE_CONTENT = "ACTIVE_CONTENT"
    MALFORMED = "MALFORMED"
    EXECUTABLE = "EXECUTABLE"
    ARCHIVE = "ARCHIVE"
    WORD_DOCUMENT = "WORD_DOCUMENT"
    SPREADSHEET = "SPREADSHEET"
    PRESENTATION = "PRESENTATION"


class SupportingSourceBlob(_FrozenContract):
    schema_version: Literal["supporting-source-blob.v0.1"]
    contract_family: Literal["preliminary-formal-evidence.v0.1"]
    source_blob_id: str = Field(pattern=r"^blob-[0-9a-f]{64}$")
    content_sha256: str = Field(pattern=_SHA256_PATTERN)
    byte_size: int = Field(ge=0)
    detected_media_type: str = Field(min_length=1)
    original_filename: str = Field(min_length=1)
    state: SourceBlobState
    rejection_code: SupportingFileRejectionCode | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_blob_state(self) -> Self:
        if self.source_blob_id != f"blob-{self.content_sha256}":
            raise ValueError("source_blob_id must be derived from content_sha256")
        if self.state is SourceBlobState.ACCEPTED:
            if self.rejection_code is not None:
                raise ValueError("accepted blobs cannot carry a rejection code")
            if self.detected_media_type not in SUPPORTED_MEDIA_TYPES:
                raise ValueError("accepted blobs must be text-native PDF or plain text")
            if self.byte_size > MAX_SUPPORTING_FILE_BYTES:
                raise ValueError("accepted blob exceeds the per-file byte limit")
        elif self.rejection_code is None:
            raise ValueError("rejected blobs require a closed rejection code")
        return self


class SupportingDocumentReference(_FrozenContract):
    lineage: FormalEvidenceLineage
    document_id: str = Field(min_length=1)
    content_sha256: str = Field(pattern=_SHA256_PATTERN)


class SupportingDocument(_FrozenContract):
    schema_version: Literal["supporting-document.v0.1"]
    contract_family: Literal["preliminary-formal-evidence.v0.1"]
    document_id: str = Field(min_length=1)
    lineage: FormalEvidenceLineage
    source_blob_id: str = Field(pattern=r"^blob-[0-9a-f]{64}$")
    source_blob_sha256: str = Field(pattern=_SHA256_PATTERN)
    original_filename: str = Field(min_length=1)
    media_type: Literal["application/pdf", "text/plain"]
    byte_size: int = Field(ge=0, le=MAX_SUPPORTING_FILE_BYTES)
    initial_metadata_revision_id: str = Field(min_length=1)
    superseded_document: SupportingDocumentReference | None = None
    submitter: ReviewerDeclaration
    created_at: datetime

    @model_validator(mode="after")
    def validate_document_identity(self) -> Self:
        if self.source_blob_id != f"blob-{self.source_blob_sha256}":
            raise ValueError("source blob ID and hash must match")
        if self.superseded_document is not None:
            if self.superseded_document.document_id == self.document_id:
                raise ValueError("a supporting document cannot supersede itself")
            if self.superseded_document.lineage != self.lineage:
                raise ValueError("document supersession must remain in one lineage")
        return self


class DocumentCategory(StrEnum):
    PROCESS_VOLUMES_AND_FREQUENCY = "process volumes and frequency"
    SYSTEMS_AND_INTEGRATIONS = "systems and integrations"
    DATA_AVAILABILITY_AND_QUALITY = "data availability and quality"
    RISKS_AND_CONTROLS = "risks and controls"
    OWNERSHIP_AND_ACCOUNTABILITY = "ownership and accountability"
    LEGAL_POLICY_SECURITY_OR_OPERATIONAL_CONSTRAINTS = (
        "legal, policy, security, or operational constraints"
    )
    COST_EFFORT_SERVICE_LEVEL_OR_PERFORMANCE_INFORMATION = (
        "cost, effort, service-level, or performance information"
    )
    OTHER_ORGANISATIONAL_EVIDENCE = "other organisational evidence"


class CoveredPeriod(_FrozenContract):
    starts_on: date
    ends_on: date

    @model_validator(mode="after")
    def require_ordered_period(self) -> Self:
        if self.ends_on < self.starts_on:
            raise ValueError("covered period must not end before it starts")
        return self


class SupportingDocumentMetadataRevision(_FrozenContract):
    schema_version: Literal["supporting-document-metadata-revision.v0.1"]
    contract_family: Literal["preliminary-formal-evidence.v0.1"]
    lineage: FormalEvidenceLineage
    document_id: str = Field(min_length=1)
    revision_id: str = Field(min_length=1)
    revision_number: int = Field(ge=1)
    prior_revision_id: str | None = Field(default=None, min_length=1)
    description: str = Field(min_length=1)
    primary_category: DocumentCategory
    additional_categories: tuple[DocumentCategory, ...] = ()
    source_organisation_or_owner: str | None = Field(default=None, min_length=1)
    covered_period: CoveredPeriod | None = None
    request: RequestIdentity
    revised_at: datetime

    @model_validator(mode="after")
    def validate_revision(self) -> Self:
        if (self.revision_number == 1) != (self.prior_revision_id is None):
            raise ValueError("only revision 1 may omit prior_revision_id")
        categories = (self.primary_category, *self.additional_categories)
        if len(categories) != len(set(categories)):
            raise ValueError("document categories must be unique")
        if not self.description.strip():
            raise ValueError("description cannot be blank")
        return self


class ExternalProviderConsent(_FrozenContract):
    schema_version: Literal["external-provider-consent.v0.1"]
    contract_family: Literal["preliminary-formal-evidence.v0.1"]
    lineage: FormalEvidenceLineage
    document_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    disclosure_text: str = Field(min_length=1)
    disclosure_version: str = Field(min_length=1)
    explicit_consent: StrictBool
    declarant_name: str | None = Field(default=None, min_length=1)
    local_session_identity: str | None = Field(default=None, min_length=1)
    declared_at: datetime

    @model_validator(mode="after")
    def require_declarant(self) -> Self:
        if self.declarant_name is None and self.local_session_identity is None:
            raise ValueError("provider consent requires a declarant identity")
        return self

    @property
    def external_transmission_permitted(self) -> bool:
        return self.explicit_consent


class AttemptStatus(StrEnum):
    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    ABANDONED = "ABANDONED"


TERMINAL_ATTEMPT_STATUSES = frozenset(
    {
        AttemptStatus.SUCCEEDED,
        AttemptStatus.PARTIAL,
        AttemptStatus.FAILED,
        AttemptStatus.INTERRUPTED,
        AttemptStatus.ABANDONED,
    }
)


class ParsedDocumentIdentity(_FrozenContract):
    parsed_document_id: str = Field(min_length=1)
    parsed_document_sha256: str = Field(pattern=_SHA256_PATTERN)
    page_count: int | None = Field(default=None, ge=1, le=MAX_PDF_PAGES)
    extracted_character_count: int = Field(ge=0, le=MAX_EXTRACTED_CHARACTERS)


class SupportingDocumentIngestionAttempt(_FrozenContract):
    schema_version: Literal["supporting-document-ingestion-attempt.v0.1"]
    contract_family: Literal["preliminary-formal-evidence.v0.1"]
    lineage: FormalEvidenceLineage
    attempt_id: str = Field(min_length=1)
    attempt_number: int = Field(ge=1)
    document_id: str = Field(min_length=1)
    document_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    predecessor_attempt_id: str | None = Field(default=None, min_length=1)
    request: RequestIdentity
    status: AttemptStatus
    parsed_document: ParsedDocumentIdentity | None = None
    issue_codes: tuple[str, ...] = ()
    started_at: datetime
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_attempt(self) -> Self:
        if (self.attempt_number == 1) != (self.predecessor_attempt_id is None):
            raise ValueError("retry lineage must match the attempt number")
        if self.status is AttemptStatus.STARTED:
            if self.completed_at is not None or self.parsed_document is not None:
                raise ValueError("started ingestion attempts cannot contain terminal output")
        else:
            if self.completed_at is None:
                raise ValueError("terminal ingestion attempts require completed_at")
            if self.completed_at < self.started_at:
                raise ValueError("completed_at cannot precede started_at")
            has_output = self.parsed_document is not None
            if self.status in {AttemptStatus.SUCCEEDED, AttemptStatus.PARTIAL}:
                if not has_output:
                    raise ValueError("successful or partial ingestion requires parsed output")
            elif has_output:
                raise ValueError("failed ingestion states cannot publish parsed output")
        if len(self.issue_codes) != len(set(self.issue_codes)):
            raise ValueError("ingestion issue codes must be unique")
        return self


class ExtractorIdentity(_FrozenContract):
    extractor_id: str = Field(min_length=1)
    extractor_version: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    output_schema_id: str = Field(min_length=1)
    output_schema_version: str = Field(min_length=1)
    prompt_id: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)


class SupportingEvidenceExtractionAttempt(_FrozenContract):
    schema_version: Literal["supporting-evidence-extraction-attempt.v0.1"]
    contract_family: Literal["preliminary-formal-evidence.v0.1"]
    lineage: FormalEvidenceLineage
    attempt_id: str = Field(min_length=1)
    attempt_number: int = Field(ge=1)
    document_id: str = Field(min_length=1)
    document_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    ingestion_attempt_id: str = Field(min_length=1)
    predecessor_attempt_id: str | None = Field(default=None, min_length=1)
    extractor: ExtractorIdentity
    request: RequestIdentity
    status: AttemptStatus
    proposal_ids: tuple[str, ...] = ()
    issue_codes: tuple[str, ...] = ()
    started_at: datetime
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_attempt(self) -> Self:
        if (self.attempt_number == 1) != (self.predecessor_attempt_id is None):
            raise ValueError("retry lineage must match the attempt number")
        if self.status is AttemptStatus.STARTED:
            if self.completed_at is not None or self.proposal_ids:
                raise ValueError("started extraction attempts cannot contain terminal output")
        else:
            if self.completed_at is None:
                raise ValueError("terminal extraction attempts require completed_at")
            if self.completed_at < self.started_at:
                raise ValueError("completed_at cannot precede started_at")
            if self.status not in {AttemptStatus.SUCCEEDED, AttemptStatus.PARTIAL}:
                if self.proposal_ids:
                    raise ValueError("failed extraction states cannot publish proposals")
        if len(self.proposal_ids) != len(set(self.proposal_ids)):
            raise ValueError("proposal identities must be unique and ordered")
        if len(self.issue_codes) != len(set(self.issue_codes)):
            raise ValueError("extraction issue codes must be unique")
        return self


class SupportingSourceSpan(_FrozenContract):
    lineage: FormalEvidenceLineage
    document_id: str = Field(min_length=1)
    document_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    parsed_document_id: str = Field(min_length=1)
    block_id: str = Field(min_length=1)
    page_number: int | None = Field(default=None, ge=1, le=MAX_PDF_PAGES)
    line_start: int | None = Field(default=None, ge=1)
    line_end_exclusive: int | None = Field(default=None, ge=2)
    document_character_start: int = Field(ge=0)
    document_character_end_exclusive: int = Field(ge=1)
    block_character_start: int = Field(ge=0)
    block_character_end_exclusive: int = Field(ge=1)
    exact_excerpt: str = Field(min_length=1)
    excerpt_sha256: str = Field(pattern=_SHA256_PATTERN)
    locator: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_exact_span(self) -> Self:
        if (self.line_start is None) != (self.line_end_exclusive is None):
            raise ValueError("line range endpoints must be supplied together")
        if self.line_start is not None and self.line_end_exclusive <= self.line_start:
            raise ValueError("line range must be non-empty and half-open")
        excerpt_length = len(self.exact_excerpt)
        if self.document_character_end_exclusive <= self.document_character_start:
            raise ValueError("document range must be non-empty and half-open")
        if self.block_character_end_exclusive <= self.block_character_start:
            raise ValueError("block range must be non-empty and half-open")
        if self.document_character_end_exclusive - self.document_character_start != excerpt_length:
            raise ValueError("document offset length must equal the exact excerpt length")
        if self.block_character_end_exclusive - self.block_character_start != excerpt_length:
            raise ValueError("block offset length must equal the exact excerpt length")
        actual_hash = hashlib.sha256(self.exact_excerpt.encode("utf-8")).hexdigest()
        if self.excerpt_sha256 != actual_hash:
            raise ValueError("excerpt_sha256 must match the exact excerpt")
        return self


class EvidenceClassification(StrEnum):
    DOCUMENTED_FACT = "documented fact"
    REVIEWED_INFERENCE = "reviewed inference"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"


class FormalTargetKind(StrEnum):
    CRITERION = "criterion"
    HUMAN_ACCOUNTABILITY_REQUIRED = "human_accountability_required"
    CAPABILITY_SIGNAL = "capability_signal"
    ACTIVITY_EVIDENCE = "activity_evidence"


class CriterionFormalTarget(_FrozenContract):
    kind: Literal[FormalTargetKind.CRITERION]
    criterion: CriterionName


class HumanAccountabilityFormalTarget(_FrozenContract):
    kind: Literal[FormalTargetKind.HUMAN_ACCOUNTABILITY_REQUIRED]


class CapabilitySignalFormalTarget(_FrozenContract):
    kind: Literal[FormalTargetKind.CAPABILITY_SIGNAL]
    capability_signal: CapabilitySignalName


class ActivityEvidenceFormalTarget(_FrozenContract):
    kind: Literal[FormalTargetKind.ACTIVITY_EVIDENCE]


FormalTarget = Annotated[
    CriterionFormalTarget
    | HumanAccountabilityFormalTarget
    | CapabilitySignalFormalTarget
    | ActivityEvidenceFormalTarget,
    Field(discriminator="kind"),
]


class SupportingEvidenceProposal(_FrozenContract):
    schema_version: Literal["supporting-evidence-proposal.v0.1"]
    contract_family: Literal["preliminary-formal-evidence.v0.1"]
    proposal_id: str | None = Field(default=None, pattern=r"^proposal-[0-9a-f]{64}$")
    lineage: FormalEvidenceLineage
    extraction_attempt_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    document_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    proposed_claim: str = Field(min_length=1)
    proposed_classification: EvidenceClassification
    primary_source_span: SupportingSourceSpan
    related_source_spans: tuple[SupportingSourceSpan, ...] = ()
    proposed_category: DocumentCategory
    suggested_activity_ids: tuple[str, ...] = ()
    suggested_formal_targets: tuple[FormalTarget, ...] = ()
    explanatory_gate_relevance: FourGateName | None = None
    ambiguity_indicated: StrictBool
    conflict_indicated: StrictBool
    relevance_explanation: str = Field(min_length=1)
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)
    extractor: ExtractorIdentity

    @model_validator(mode="after")
    def validate_proposal(self) -> Self:
        spans = (self.primary_source_span, *self.related_source_spans)
        for span in spans:
            if span.lineage != self.lineage:
                raise ValueError("proposal source spans must share exact lineage")
            if span.document_id != self.document_id:
                raise ValueError("proposal source spans must use the proposal document")
            if span.document_content_sha256 != self.document_content_sha256:
                raise ValueError("proposal source spans must use the proposal document hash")
        if len(self.suggested_activity_ids) != len(set(self.suggested_activity_ids)):
            raise ValueError("suggested activity identities must be unique and ordered")
        target_keys = [_canonical_json_bytes(item) for item in self.suggested_formal_targets]
        if len(target_keys) != len(set(target_keys)):
            raise ValueError("suggested formal targets must be unique and ordered")
        span_keys = [_canonical_json_bytes(item) for item in spans]
        if len(span_keys) != len(set(span_keys)):
            raise ValueError("proposal source spans must be unique and ordered")
        payload = self.model_dump(mode="json", exclude={"proposal_id"})
        expected_id = _content_id("proposal", payload)
        if self.proposal_id is None:
            object.__setattr__(self, "proposal_id", expected_id)
        elif self.proposal_id != expected_id:
            raise ValueError("proposal_id must be derived from proposal content")
        return self


class ReviewAction(StrEnum):
    ACCEPT = "ACCEPT"
    CORRECT = "CORRECT"
    REJECT = "REJECT"
    MARK_UNRESOLVED = "MARK_UNRESOLVED"


class ReviewedEvidenceReference(_FrozenContract):
    lineage: FormalEvidenceLineage
    review_revision_id: str = Field(min_length=1)
    proposal_id: str = Field(pattern=r"^proposal-[0-9a-f]{64}$")
    action: ReviewAction
    classification: EvidenceClassification | None = None

    @model_validator(mode="after")
    def validate_reference(self) -> Self:
        if self.action is ReviewAction.REJECT:
            if self.classification is not None:
                raise ValueError("rejected proposal references are audit-only")
        elif self.classification is None:
            raise ValueError("non-rejected review references require a classification")
        return self


class SupportingEvidenceReviewRevision(_FrozenContract):
    schema_version: Literal["supporting-evidence-review-revision.v0.1"]
    contract_family: Literal["preliminary-formal-evidence.v0.1"]
    lineage: FormalEvidenceLineage
    proposal_id: str = Field(pattern=r"^proposal-[0-9a-f]{64}$")
    revision_id: str = Field(min_length=1)
    revision_number: int = Field(ge=1)
    prior_revision_id: str | None = Field(default=None, min_length=1)
    action: ReviewAction
    original_proposal: SupportingEvidenceProposal
    approved_claim: str | None = Field(default=None, min_length=1)
    source_spans: tuple[SupportingSourceSpan, ...] = ()
    selected_category: DocumentCategory | None = None
    approved_classification: EvidenceClassification | None = None
    claim_directly_supported_by_excerpt: StrictBool | None = None
    inference_confidence: float | None = Field(default=None, ge=0, le=1)
    inference_documented_facts: tuple[ReviewedEvidenceReference, ...] = ()
    competing_evidence: tuple[ReviewedEvidenceReference, ...] = ()
    candidate_eligible: StrictBool = False
    reviewer: ReviewerDeclaration
    rationale: str = Field(min_length=1)
    reviewed_at: datetime
    request: RequestIdentity
    expected_prior_revision_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_review(self) -> Self:
        if self.lineage != self.original_proposal.lineage:
            raise ValueError("review and proposal lineage must match exactly")
        if self.proposal_id != self.original_proposal.proposal_id:
            raise ValueError("review proposal identity must match the original")
        if (self.revision_number == 1) != (self.prior_revision_id is None):
            raise ValueError("only revision 1 may omit prior_revision_id")
        if self.expected_prior_revision_id != self.prior_revision_id:
            raise ValueError("expected prior revision must match immutable lineage")

        approved_fields_present = any(
            (
                self.approved_claim is not None,
                bool(self.source_spans),
                self.selected_category is not None,
                self.approved_classification is not None,
                self.claim_directly_supported_by_excerpt is not None,
                self.inference_confidence is not None,
                bool(self.inference_documented_facts),
                bool(self.competing_evidence),
                self.candidate_eligible,
            )
        )
        if self.action is ReviewAction.REJECT:
            if approved_fields_present:
                raise ValueError("rejected proposals must remain audit-only")
            return self

        if self.approved_claim is None or self.selected_category is None:
            raise ValueError("reviewed evidence requires an approved claim and category")
        if self.approved_classification is None:
            raise ValueError("reviewed evidence requires an approved classification")
        proposal_spans = (
            self.original_proposal.primary_source_span,
            *self.original_proposal.related_source_spans,
        )
        if self.source_spans != proposal_spans:
            raise ValueError("review cannot alter the proposal source spans")
        if self.action is ReviewAction.ACCEPT:
            if self.approved_claim != self.original_proposal.proposed_claim:
                raise ValueError("ACCEPT must retain the proposed claim")
        elif self.action is ReviewAction.CORRECT:
            if self.approved_claim == self.original_proposal.proposed_claim:
                raise ValueError("CORRECT must record changed wording")
        elif self.approved_classification not in {
            EvidenceClassification.UNKNOWN,
            EvidenceClassification.CONFLICT,
        }:
            raise ValueError("MARK_UNRESOLVED permits only unknown or conflict")

        classification = self.approved_classification
        if classification is EvidenceClassification.DOCUMENTED_FACT:
            if self.claim_directly_supported_by_excerpt is not True:
                raise ValueError("documented facts must be directly supported by excerpts")
            if self.inference_confidence is not None or self.inference_documented_facts:
                raise ValueError("documented facts cannot claim inference provenance")
            if self.competing_evidence:
                raise ValueError("documented facts cannot contain competing evidence")
        elif classification is EvidenceClassification.REVIEWED_INFERENCE:
            if self.claim_directly_supported_by_excerpt is not False:
                raise ValueError("reviewed inference must be identified as indirect")
            if self.inference_confidence is None:
                raise ValueError("reviewed inference requires human-approved confidence")
            if not self.inference_documented_facts:
                raise ValueError("reviewed inference requires documented-fact links")
            for fact in self.inference_documented_facts:
                if fact.lineage != self.lineage:
                    raise ValueError("inference fact links must share exact lineage")
                if fact.classification is not EvidenceClassification.DOCUMENTED_FACT:
                    raise ValueError("inference links must reference documented facts")
                if fact.action not in {ReviewAction.ACCEPT, ReviewAction.CORRECT}:
                    raise ValueError("inference facts must be accepted or corrected")
            if self.competing_evidence:
                raise ValueError("reviewed inference cannot contain conflict links")
        elif classification is EvidenceClassification.UNKNOWN:
            if any(
                (
                    self.claim_directly_supported_by_excerpt is not None,
                    self.inference_confidence is not None,
                    bool(self.inference_documented_facts),
                    bool(self.competing_evidence),
                )
            ):
                raise ValueError("unknown evidence cannot claim value provenance or confidence")
        elif classification is EvidenceClassification.CONFLICT:
            if self.claim_directly_supported_by_excerpt is not None:
                raise ValueError("conflict evidence cannot claim direct support")
            if self.inference_confidence is not None or self.inference_documented_facts:
                raise ValueError("conflict evidence cannot claim inference confidence")
            if len(self.competing_evidence) < 2:
                raise ValueError("conflicts require at least two competing evidence links")
            if any(item.lineage != self.lineage for item in self.competing_evidence):
                raise ValueError("competing evidence must share exact lineage")

        for references, label in (
            (self.inference_documented_facts, "inference fact"),
            (self.competing_evidence, "competing evidence"),
        ):
            identities = [item.review_revision_id for item in references]
            if len(identities) != len(set(identities)):
                raise ValueError(f"{label} identities must be unique and ordered")

        if self.action in {ReviewAction.ACCEPT, ReviewAction.CORRECT}:
            if classification in {
                EvidenceClassification.DOCUMENTED_FACT,
                EvidenceClassification.REVIEWED_INFERENCE,
            } and not self.candidate_eligible:
                raise ValueError("accepted facts and inferences must be candidate eligible")
        elif self.candidate_eligible:
            raise ValueError("unresolved evidence cannot be candidate eligible")
        return self


class ContextNote(_FrozenContract):
    schema_version: Literal["context-note.v0.1"]
    contract_family: Literal["preliminary-formal-evidence.v0.1"]
    context_note_id: str = Field(min_length=1)
    lineage: FormalEvidenceLineage
    activity_id: str | None = Field(default=None, min_length=1)
    statement: str = Field(min_length=1)
    origin: Literal["HUMAN_SUPPLIED_CONTEXT_ONLY"]
    reviewer: ReviewerDeclaration
    created_at: datetime
    request: RequestIdentity
    source_spans: tuple[()] = ()
    formal_value: None = None
    candidate_eligible: Literal[False] = False


class MappingDisposition(StrEnum):
    MAPPED_FORMAL_INPUT = "MAPPED_FORMAL_INPUT"
    CONTEXT_ONLY = "CONTEXT_ONLY"


FormalScalar = StrictInt | StrictBool | None


class FormalInputMapping(_FrozenContract):
    schema_version: Literal["formal-input-mapping.v0.1"]
    contract_family: Literal["preliminary-formal-evidence.v0.1"]
    mapping_id: str = Field(min_length=1)
    lineage: FormalEvidenceLineage
    activity_id: str = Field(min_length=1)
    target: FormalTarget | None
    disposition: MappingDisposition
    value: FormalScalar
    knowledge_state: KnowledgeState
    approved_evidence_classification: EvidenceClassification | None
    supporting_reviews: tuple[ReviewedEvidenceReference, ...] = ()
    supporting_documented_fact_review_ids: tuple[str, ...] = ()
    mapping_rationale: str = Field(min_length=1)
    reviewer: ReviewerDeclaration
    mapped_at: datetime
    inference_confidence: float | None = Field(default=None, ge=0, le=1)
    request: RequestIdentity

    @model_validator(mode="after")
    def validate_mapping(self) -> Self:
        if len(self.supporting_documented_fact_review_ids) != len(
            set(self.supporting_documented_fact_review_ids)
        ):
            raise ValueError("documented-fact identities must be unique and ordered")
        if len(self.supporting_reviews) != len(
            {item.review_revision_id for item in self.supporting_reviews}
        ):
            raise ValueError("supporting review identities must be unique and ordered")
        if any(item.lineage != self.lineage for item in self.supporting_reviews):
            raise ValueError("supporting reviews must share exact lineage")
        if any(item.action is ReviewAction.REJECT for item in self.supporting_reviews):
            raise ValueError("rejected proposals cannot support formal mappings")

        if self.disposition is MappingDisposition.CONTEXT_ONLY:
            if any(
                (
                    self.target is not None,
                    self.value is not None,
                    self.approved_evidence_classification is not None,
                    self.inference_confidence is not None,
                    bool(self.supporting_documented_fact_review_ids),
                )
            ):
                raise ValueError("context-only mappings cannot claim formal evidence")
            if self.knowledge_state is not KnowledgeState.UNKNOWN:
                raise ValueError("context-only mappings must retain unknown knowledge state")
            return self

        if self.target is None or self.approved_evidence_classification is None:
            raise ValueError("formal mappings require an exact target and classification")
        if not self.supporting_reviews:
            raise ValueError("formal mappings require human-reviewed evidence")
        if not any(
            item.classification is self.approved_evidence_classification
            and item.action in {ReviewAction.ACCEPT, ReviewAction.CORRECT}
            for item in self.supporting_reviews
        ):
            raise ValueError(
                "formal mapping classification requires a matching approved review"
            )
        if self.target.kind is FormalTargetKind.CRITERION:
            if self.value is not None and (
                type(self.value) is not int or not 0 <= self.value <= 5
            ):
                raise ValueError("criterion values must be strict integers from 0 to 5")
        elif self.target.kind in {
            FormalTargetKind.HUMAN_ACCOUNTABILITY_REQUIRED,
            FormalTargetKind.CAPABILITY_SIGNAL,
        }:
            if self.value is not None and type(self.value) is not bool:
                raise ValueError("accountability and capability values must be strict booleans")
        elif self.value is not None:
            raise ValueError("activity evidence cannot contain a scalar value")

        classification = self.approved_evidence_classification
        if classification is EvidenceClassification.DOCUMENTED_FACT:
            if self.knowledge_state is not KnowledgeState.KNOWN:
                raise ValueError("documented facts require known knowledge state")
            if self.inference_confidence is not None:
                raise ValueError("documented facts cannot have inference confidence")
        elif classification is EvidenceClassification.REVIEWED_INFERENCE:
            if self.knowledge_state is not KnowledgeState.INFERRED:
                raise ValueError("reviewed inferences require inferred knowledge state")
            if self.inference_confidence is None:
                raise ValueError("reviewed inferences require reviewer-approved confidence")
            if not self.supporting_documented_fact_review_ids:
                raise ValueError("reviewed inferences require documented-fact support")
        else:
            if self.knowledge_state is not KnowledgeState.UNKNOWN:
                raise ValueError("unknown and conflict mappings require unknown state")
            if self.value is not None or self.inference_confidence is not None:
                raise ValueError("unknown and conflict mappings require null value/confidence")
        return self


class CandidateDocumentIdentity(_FrozenContract):
    document_id: str = Field(min_length=1)
    content_sha256: str = Field(pattern=_SHA256_PATTERN)
    byte_size: int = Field(ge=0, le=MAX_SUPPORTING_FILE_BYTES)
    metadata_revision_id: str = Field(min_length=1)


class CandidateExtractionIdentity(_FrozenContract):
    extraction_attempt_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    status: Literal[
        AttemptStatus.SUCCEEDED,
        AttemptStatus.PARTIAL,
        AttemptStatus.FAILED,
        AttemptStatus.INTERRUPTED,
        AttemptStatus.ABANDONED,
    ]
    proposal_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_unique_proposals(self) -> Self:
        if len(self.proposal_ids) != len(set(self.proposal_ids)):
            raise ValueError("candidate extraction proposal identities must be unique")
        if self.status not in {AttemptStatus.SUCCEEDED, AttemptStatus.PARTIAL}:
            if self.proposal_ids:
                raise ValueError("failed extraction states cannot publish proposals")
        return self


class ExcludedProposalReference(_FrozenContract):
    proposal_id: str = Field(pattern=r"^proposal-[0-9a-f]{64}$")
    reason: str = Field(min_length=1)


class FormalInputCandidateSet(_FrozenContract):
    schema_version: Literal["formal-input-candidate-set.v0.1"]
    contract_family: Literal["preliminary-formal-evidence.v0.1"]
    candidate_set_id: str = Field(min_length=1)
    lineage: FormalEvidenceLineage
    current_documents: tuple[CandidateDocumentIdentity, ...]
    current_extractions: tuple[CandidateExtractionIdentity, ...]
    current_reviews: tuple[ReviewedEvidenceReference, ...]
    ordered_formal_mappings: tuple[FormalInputMapping, ...]
    context_only_review_revision_ids: tuple[str, ...] = ()
    retained_unknown_review_revision_ids: tuple[str, ...] = ()
    retained_conflict_review_revision_ids: tuple[str, ...] = ()
    rejected_or_excluded_proposals: tuple[ExcludedProposalReference, ...] = ()
    explicitly_excluded_document_ids: tuple[str, ...] = ()
    prior_candidate_set_id: str | None = Field(default=None, min_length=1)
    created_at: datetime
    conversion_request: RequestIdentity

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        def require_unique(values: list[str], label: str) -> None:
            if len(values) != len(set(values)):
                raise ValueError(f"{label} identities must be unique and ordered")

        document_ids = [item.document_id for item in self.current_documents]
        require_unique(document_ids, "current document")
        if len(document_ids) > MAX_CURRENT_DOCUMENTS:
            raise ValueError("candidate set exceeds the current-document limit")
        extraction_ids = [item.extraction_attempt_id for item in self.current_extractions]
        require_unique(extraction_ids, "current extraction")
        extraction_document_ids = [item.document_id for item in self.current_extractions]
        require_unique(extraction_document_ids, "current extraction document")
        proposal_ids = [
            proposal_id
            for extraction in self.current_extractions
            for proposal_id in extraction.proposal_ids
        ]
        require_unique(proposal_ids, "current proposal")
        review_ids = [item.review_revision_id for item in self.current_reviews]
        require_unique(review_ids, "current review")
        review_proposal_ids = [item.proposal_id for item in self.current_reviews]
        require_unique(review_proposal_ids, "current reviewed proposal")
        mapping_ids = [item.mapping_id for item in self.ordered_formal_mappings]
        require_unique(mapping_ids, "formal mapping")
        require_unique(list(self.context_only_review_revision_ids), "context-only review")
        require_unique(list(self.retained_unknown_review_revision_ids), "unknown review")
        require_unique(list(self.retained_conflict_review_revision_ids), "conflict review")
        require_unique(
            [item.proposal_id for item in self.rejected_or_excluded_proposals],
            "rejected/excluded proposal",
        )
        require_unique(list(self.explicitly_excluded_document_ids), "excluded document")
        if not set(self.explicitly_excluded_document_ids) <= set(document_ids):
            raise ValueError("excluded documents must remain in the current snapshot")
        if {item.document_id for item in self.current_extractions} - set(document_ids):
            raise ValueError("current extractions must belong to current documents")
        if set(review_proposal_ids) - set(proposal_ids):
            raise ValueError("current reviews must belong to current proposals")
        if {
            item.proposal_id for item in self.rejected_or_excluded_proposals
        } - set(proposal_ids):
            raise ValueError("excluded proposal references must belong to current proposals")
        if any(item.lineage != self.lineage for item in self.current_reviews):
            raise ValueError("current reviews must share candidate-set lineage")
        if any(item.lineage != self.lineage for item in self.ordered_formal_mappings):
            raise ValueError("formal mappings must share candidate-set lineage")
        known_review_ids = set(review_ids)
        current_reviews_by_id = {
            item.review_revision_id: item for item in self.current_reviews
        }
        partition_ids = (
            set(self.context_only_review_revision_ids)
            | set(self.retained_unknown_review_revision_ids)
            | set(self.retained_conflict_review_revision_ids)
        )
        if not partition_ids <= known_review_ids:
            raise ValueError("candidate partitions must reference current reviews")
        groups = [
            set(self.context_only_review_revision_ids),
            set(self.retained_unknown_review_revision_ids),
            set(self.retained_conflict_review_revision_ids),
        ]
        if any(groups[i] & groups[j] for i in range(3) for j in range(i + 1, 3)):
            raise ValueError("candidate review partitions cannot overlap")
        for mapping in self.ordered_formal_mappings:
            supporting_ids = {
                item.review_revision_id for item in mapping.supporting_reviews
            }
            if supporting_ids - known_review_ids:
                raise ValueError("mapping evidence must be present in current reviews")
            if any(
                current_reviews_by_id[item.review_revision_id] != item
                for item in mapping.supporting_reviews
            ):
                raise ValueError("mapping evidence must match the current review identity")
            fact_ids = set(mapping.supporting_documented_fact_review_ids)
            if fact_ids - known_review_ids:
                raise ValueError("mapping fact support must be present in current reviews")
            if any(
                current_reviews_by_id[item_id].classification
                is not EvidenceClassification.DOCUMENTED_FACT
                or current_reviews_by_id[item_id].action
                not in {ReviewAction.ACCEPT, ReviewAction.CORRECT}
                for item_id in fact_ids
            ):
                raise ValueError("mapping fact support must be approved documented facts")
        total_bytes = sum(item.byte_size for item in self.current_documents)
        if total_bytes > MAX_FORMAL_LIFECYCLE_BYTES:
            raise ValueError("candidate set exceeds the lifecycle byte limit")
        return self


class ReadinessStatus(StrEnum):
    NOT_READY = "NOT_READY"
    READY_TO_ATTEMPT = "READY_TO_ATTEMPT"


class FormalEvidenceReadiness(_FrozenContract):
    schema_version: Literal["formal-evidence-readiness.v0.1"]
    contract_family: Literal["preliminary-formal-evidence.v0.1"]
    readiness_id: str = Field(min_length=1)
    lineage: FormalEvidenceLineage
    candidate_set: FormalInputCandidateSet
    current_review_revision_ids: tuple[str, ...]
    processing_complete_or_explicitly_excluded: StrictBool
    every_current_proposal_terminally_reviewed: StrictBool
    every_accepted_or_corrected_item_mapped_or_context_only: StrictBool
    candidate_set_includes_every_current_review_revision: StrictBool
    lineage_and_integrity_valid: StrictBool
    uncovered_document_categories: tuple[DocumentCategory, ...] = ()
    retained_unknown_count: int = Field(ge=0)
    retained_conflict_count: int = Field(ge=0)
    status: ReadinessStatus
    reasons: tuple[str, ...] = ()
    evaluated_at: datetime

    @model_validator(mode="after")
    def validate_readiness(self) -> Self:
        if self.candidate_set.lineage != self.lineage:
            raise ValueError("readiness and candidate-set lineage must match")
        if len(self.uncovered_document_categories) != len(
            set(self.uncovered_document_categories)
        ):
            raise ValueError("uncovered categories must be unique warnings")
        if self.retained_unknown_count != len(
            self.candidate_set.retained_unknown_review_revision_ids
        ):
            raise ValueError("retained unknown count must match the candidate snapshot")
        if self.retained_conflict_count != len(
            self.candidate_set.retained_conflict_review_revision_ids
        ):
            raise ValueError("retained conflict count must match the candidate snapshot")
        if len(self.current_review_revision_ids) != len(
            set(self.current_review_revision_ids)
        ):
            raise ValueError("current readiness review identities must be unique")

        document_ids = {
            item.document_id for item in self.candidate_set.current_documents
        }
        processed_or_excluded_document_ids = {
            item.document_id
            for item in self.candidate_set.current_extractions
            if item.status in {AttemptStatus.SUCCEEDED, AttemptStatus.PARTIAL}
        } | set(self.candidate_set.explicitly_excluded_document_ids)
        derived_processing_complete = document_ids == processed_or_excluded_document_ids
        if (
            self.processing_complete_or_explicitly_excluded
            != derived_processing_complete
        ):
            raise ValueError(
                "processing-complete flag must match current extraction/exclusion state"
            )

        current_proposal_ids = {
            proposal_id
            for extraction in self.candidate_set.current_extractions
            for proposal_id in extraction.proposal_ids
        }
        terminal_proposal_ids = {
            item.proposal_id for item in self.candidate_set.current_reviews
        } | {
            item.proposal_id
            for item in self.candidate_set.rejected_or_excluded_proposals
        }
        derived_terminal_review = current_proposal_ids <= terminal_proposal_ids
        if (
            self.every_current_proposal_terminally_reviewed
            != derived_terminal_review
        ):
            raise ValueError(
                "terminal-review flag must match the current proposal snapshot"
            )

        accepted_or_corrected_ids = {
            item.review_revision_id
            for item in self.candidate_set.current_reviews
            if item.action in {ReviewAction.ACCEPT, ReviewAction.CORRECT}
        }
        mapped_or_context_ids = {
            evidence.review_revision_id
            for mapping in self.candidate_set.ordered_formal_mappings
            for evidence in mapping.supporting_reviews
        } | {
            fact_id
            for mapping in self.candidate_set.ordered_formal_mappings
            for fact_id in mapping.supporting_documented_fact_review_ids
        } | set(self.candidate_set.context_only_review_revision_ids)
        derived_mapping_coverage = accepted_or_corrected_ids <= mapped_or_context_ids
        if (
            self.every_accepted_or_corrected_item_mapped_or_context_only
            != derived_mapping_coverage
        ):
            raise ValueError(
                "mapping-coverage flag must match the current review snapshot"
            )

        candidate_review_ids = {
            item.review_revision_id for item in self.candidate_set.current_reviews
        }
        derived_current_review_coverage = candidate_review_ids == set(
            self.current_review_revision_ids
        )
        if (
            self.candidate_set_includes_every_current_review_revision
            != derived_current_review_coverage
        ):
            raise ValueError(
                "current-review coverage flag must match the candidate snapshot"
            )
        positive_mappings = [
            item
            for item in self.candidate_set.ordered_formal_mappings
            if item.disposition is MappingDisposition.MAPPED_FORMAL_INPUT
            and item.approved_evidence_classification
            in {
                EvidenceClassification.DOCUMENTED_FACT,
                EvidenceClassification.REVIEWED_INFERENCE,
            }
            and item.value is not None
        ]
        conditions = (
            self.processing_complete_or_explicitly_excluded,
            self.every_current_proposal_terminally_reviewed,
            self.every_accepted_or_corrected_item_mapped_or_context_only,
            bool(positive_mappings),
            self.candidate_set_includes_every_current_review_revision,
            self.lineage_and_integrity_valid,
        )
        ready = all(conditions)
        if ready != (self.status is ReadinessStatus.READY_TO_ATTEMPT):
            raise ValueError("readiness status must be the deterministic result of all gates")
        if ready and self.reasons:
            raise ValueError("ready records cannot contain blocking reasons")
        if not ready and not self.reasons:
            raise ValueError("not-ready records require explicit reasons")
        return self


class WorkflowEventType(StrEnum):
    SOURCE_BLOB_RECORDED = "SOURCE_BLOB_RECORDED"
    DOCUMENT_CREATED = "DOCUMENT_CREATED"
    DOCUMENT_SUPERSEDED = "DOCUMENT_SUPERSEDED"
    METADATA_REVISED = "METADATA_REVISED"
    PROVIDER_CONSENT_DECLARED = "PROVIDER_CONSENT_DECLARED"
    INGESTION_ATTEMPT_RECORDED = "INGESTION_ATTEMPT_RECORDED"
    EXTRACTION_ATTEMPT_RECORDED = "EXTRACTION_ATTEMPT_RECORDED"
    PROPOSAL_RECORDED = "PROPOSAL_RECORDED"
    REVIEW_REVISION_RECORDED = "REVIEW_REVISION_RECORDED"
    FORMAL_MAPPING_RECORDED = "FORMAL_MAPPING_RECORDED"
    CONTEXT_NOTE_RECORDED = "CONTEXT_NOTE_RECORDED"
    CANDIDATE_SET_CREATED = "CANDIDATE_SET_CREATED"
    READINESS_EVALUATED = "READINESS_EVALUATED"


class FormalEvidenceWorkflowEvent(_FrozenContract):
    schema_version: Literal["formal-evidence-workflow-event.v0.1"]
    contract_family: Literal["preliminary-formal-evidence.v0.1"]
    event_id: str = Field(min_length=1)
    lineage: FormalEvidenceLineage
    lifecycle_sequence: int = Field(ge=1)
    event_type: WorkflowEventType
    subject_id: str = Field(min_length=1)
    request: RequestIdentity
    prior_event_id: str | None = Field(default=None, min_length=1)
    payload_sha256: str = Field(pattern=_SHA256_PATTERN)
    occurred_at: datetime

    @model_validator(mode="after")
    def validate_event_sequence(self) -> Self:
        if (self.lifecycle_sequence == 1) != (self.prior_event_id is None):
            raise ValueError("only the first lifecycle event may omit prior_event_id")
        return self

"""Explicit mandatory human-review orchestration for supporting evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import ValidationError

from ai_adoption_engine.models.formal_evidence import (
    CONTEXT_NOTE_SCHEMA,
    FORMAL_EVIDENCE_FAMILY,
    SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
    AttemptStatus,
    ContextNote,
    DocumentCategory,
    EvidenceClassification,
    FormalEvidenceLineage,
    ReviewAction,
    ReviewedEvidenceReference,
    ReviewerDeclaration,
    SupportingDocument,
    SupportingEvidenceExtractionAttempt,
    SupportingEvidenceProposal,
    SupportingEvidenceReviewRevision,
    WorkflowEventType,
)
from ai_adoption_engine.persistence.base import (
    ArtifactCorruptionError,
    ArtifactNotFoundError,
)
from ai_adoption_engine.persistence.formal_evidence import (
    FormalEvidenceIdempotencyError,
    FormalEvidenceIntegrityError,
    FormalEvidenceLineageError,
    FormalEvidenceStaleWriteError,
    SQLiteFormalEvidenceRepository,
)
from ai_adoption_engine.persistence.formal_evidence_serialization import (
    serialize_formal_evidence_record,
)
from ai_adoption_engine.supporting_evidence.common import (
    Clock,
    IdFactory,
    new_id,
    next_workflow_event,
    replay_for_request,
    request_identity,
    utc_now,
)
from ai_adoption_engine.supporting_evidence.errors import (
    SupportingEvidenceConcurrentReviewError,
    SupportingEvidenceFinalizationError,
    SupportingEvidenceInsufficientConflictError,
    SupportingEvidenceInvalidReferenceError,
    SupportingEvidenceInvalidReviewError,
    SupportingEvidenceInvalidReviewerError,
    SupportingEvidenceLineageError,
    SupportingEvidenceMissingFactLinkError,
    SupportingEvidenceRequestConflictError,
    SupportingEvidenceStaleProposalError,
    SupportingEvidenceStaleRevisionError,
    SupportingEvidenceUnknownProposalError,
)


class ReviewQueueScope(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    HISTORICAL = "HISTORICAL"


class ReviewQueueStatus(StrEnum):
    UNREVIEWED = "UNREVIEWED"
    ACCEPTED = "ACCEPTED"
    CORRECTED = "CORRECTED"
    REJECTED = "REJECTED"
    UNRESOLVED_UNKNOWN = "UNRESOLVED_UNKNOWN"
    UNRESOLVED_CONFLICT = "UNRESOLVED_CONFLICT"


@dataclass(frozen=True)
class SupportingEvidenceReviewQueueItem:
    proposal: SupportingEvidenceProposal
    extraction_attempt: SupportingEvidenceExtractionAttempt
    document: SupportingDocument
    scope: ReviewQueueScope
    review_status: ReviewQueueStatus
    current_revision: SupportingEvidenceReviewRevision | None
    revision_history: tuple[SupportingEvidenceReviewRevision, ...]
    references_current: bool


@dataclass(frozen=True)
class SupportingEvidenceReviewProgress:
    total_current_proposals: int
    unreviewed_proposals: int
    accepted_proposals: int
    corrected_proposals: int
    rejected_proposals: int
    unresolved_unknowns: int
    unresolved_conflicts: int
    review_complete: bool


@dataclass(frozen=True)
class SupportingEvidenceReviewQueue:
    lineage: FormalEvidenceLineage
    items: tuple[SupportingEvidenceReviewQueueItem, ...]
    audit_history: tuple[SupportingEvidenceReviewQueueItem, ...]
    progress: SupportingEvidenceReviewProgress


@dataclass(frozen=True)
class SupportingEvidenceReviewOperationResult:
    revision: SupportingEvidenceReviewRevision
    replayed: bool


@dataclass(frozen=True)
class ContextNoteOperationResult:
    note: ContextNote
    replayed: bool


def derive_review_progress(
    statuses: tuple[ReviewQueueStatus, ...],
) -> SupportingEvidenceReviewProgress:
    """Derive proposal-review progress only; never formal readiness."""

    return SupportingEvidenceReviewProgress(
        total_current_proposals=len(statuses),
        unreviewed_proposals=statuses.count(ReviewQueueStatus.UNREVIEWED),
        accepted_proposals=statuses.count(ReviewQueueStatus.ACCEPTED),
        corrected_proposals=statuses.count(ReviewQueueStatus.CORRECTED),
        rejected_proposals=statuses.count(ReviewQueueStatus.REJECTED),
        unresolved_unknowns=statuses.count(ReviewQueueStatus.UNRESOLVED_UNKNOWN),
        unresolved_conflicts=statuses.count(ReviewQueueStatus.UNRESOLVED_CONFLICT),
        review_complete=all(
            item is not ReviewQueueStatus.UNREVIEWED for item in statuses
        ),
    )


class SupportingEvidenceReviewService:
    def __init__(
        self,
        repository: SQLiteFormalEvidenceRepository,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or utc_now
        self.id_factory = id_factory or new_id

    def _lineage(self, formal_lifecycle_id: str) -> FormalEvidenceLineage:
        try:
            return self.repository.load_active_lineage(formal_lifecycle_id)
        except (FormalEvidenceLineageError, ArtifactCorruptionError) as exc:
            raise SupportingEvidenceLineageError(
                "The formal lifecycle or its approved-process lineage is unavailable."
            ) from exc

    def _lineage_for_change(
        self, formal_lifecycle_id: str
    ) -> FormalEvidenceLineage:
        self.repository.assert_writable()
        return self._lineage(formal_lifecycle_id)

    @staticmethod
    def _review_status(
        revision: SupportingEvidenceReviewRevision | None,
    ) -> ReviewQueueStatus:
        if revision is None:
            return ReviewQueueStatus.UNREVIEWED
        if revision.action is ReviewAction.ACCEPT:
            return ReviewQueueStatus.ACCEPTED
        if revision.action is ReviewAction.CORRECT:
            return ReviewQueueStatus.CORRECTED
        if revision.action is ReviewAction.REJECT:
            return ReviewQueueStatus.REJECTED
        if revision.approved_classification is EvidenceClassification.UNKNOWN:
            return ReviewQueueStatus.UNRESOLVED_UNKNOWN
        return ReviewQueueStatus.UNRESOLVED_CONFLICT

    def _validate_document(
        self,
        document: SupportingDocument,
        lineage: FormalEvidenceLineage,
    ) -> None:
        if document.lineage != lineage:
            raise SupportingEvidenceLineageError(
                "Supporting-document history contains mixed formal lineage."
            )

    def _validate_attempt(
        self,
        attempt: SupportingEvidenceExtractionAttempt,
        document: SupportingDocument,
        lineage: FormalEvidenceLineage,
    ) -> None:
        if (
            attempt.lineage != lineage
            or attempt.document_id != document.document_id
            or attempt.document_content_sha256 != document.source_blob_sha256
        ):
            raise SupportingEvidenceLineageError(
                "Supporting extraction history does not match its immutable document."
            )

    def _attempt_proposals(
        self,
        attempt: SupportingEvidenceExtractionAttempt,
        document: SupportingDocument,
        lineage: FormalEvidenceLineage,
    ) -> tuple[SupportingEvidenceProposal, ...]:
        proposals = self.repository.proposals_for_attempt(attempt.attempt_id)
        if tuple(item.proposal_id for item in proposals) != attempt.proposal_ids:
            raise SupportingEvidenceLineageError(
                "Extraction proposal history does not match the terminal attempt."
            )
        for proposal in proposals:
            if (
                proposal.lineage != lineage
                or proposal.extraction_attempt_id != attempt.attempt_id
                or proposal.document_id != document.document_id
                or proposal.document_content_sha256
                != document.source_blob_sha256
            ):
                raise SupportingEvidenceLineageError(
                    "A supporting proposal contains mixed immutable lineage."
                )
        return proposals

    def _revision_history(
        self,
        proposal: SupportingEvidenceProposal,
        lineage: FormalEvidenceLineage,
    ) -> tuple[SupportingEvidenceReviewRevision, ...]:
        revisions = self.repository.review_revisions_for_proposal(
            proposal.proposal_id
        )
        previous: str | None = None
        for number, revision in enumerate(revisions, start=1):
            if (
                revision.lineage != lineage
                or revision.proposal_id != proposal.proposal_id
                or revision.original_proposal != proposal
                or revision.revision_number != number
                or revision.prior_revision_id != previous
            ):
                raise SupportingEvidenceLineageError(
                    "Review revision history contains corrupt or mixed lineage."
                )
            previous = revision.revision_id
        return revisions

    def _reference_is_current(
        self,
        reference: ReviewedEvidenceReference,
        lineage: FormalEvidenceLineage,
        current_proposal_ids: frozenset[str],
    ) -> bool:
        try:
            stored = self.repository.load_record(
                SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
                reference.review_revision_id,
            )
        except ArtifactNotFoundError as exc:
            raise SupportingEvidenceLineageError(
                "Reviewed-evidence reference history is incomplete."
            ) from exc
        if not isinstance(stored, SupportingEvidenceReviewRevision):
            raise SupportingEvidenceLineageError(
                "Reviewed-evidence reference history has an invalid type."
            )
        expected = ReviewedEvidenceReference(
            lineage=stored.lineage,
            review_revision_id=stored.revision_id,
            proposal_id=stored.proposal_id,
            action=stored.action,
            classification=stored.approved_classification,
        )
        if expected != reference or stored.lineage != lineage:
            raise SupportingEvidenceLineageError(
                "Reviewed-evidence reference contains mixed lineage."
            )
        latest = self.repository.latest_review_revision(stored.proposal_id)
        return (
            latest is not None
            and latest.revision_id == stored.revision_id
            and stored.proposal_id in current_proposal_ids
        )

    def _build_review_queue(
        self,
        formal_lifecycle_id: str,
        *,
        document_id: str | None = None,
    ) -> SupportingEvidenceReviewQueue:
        lineage = self._lineage(formal_lifecycle_id)
        documents = self.repository.documents_for_lifecycle(formal_lifecycle_id)
        for document in documents:
            self._validate_document(document, lineage)
        if document_id is not None:
            if not any(item.document_id == document_id for item in documents):
                raise SupportingEvidenceLineageError(
                    "The requested supporting document is outside this lifecycle."
                )

        current_document_ids = {
            item.document_id
            for item in self.repository.current_documents(formal_lifecycle_id)
        }
        proposal_rows: list[
            tuple[
                SupportingDocument,
                SupportingEvidenceExtractionAttempt,
                SupportingEvidenceProposal,
                ReviewQueueScope,
            ]
        ] = []
        current_proposal_ids: set[str] = set()
        for document in documents:
            attempts = self.repository.extraction_attempts_for_document(
                formal_lifecycle_id=formal_lifecycle_id,
                document_id=document.document_id,
            )
            for attempt in attempts:
                self._validate_attempt(attempt, document, lineage)
            compatible = tuple(
                item
                for item in attempts
                if item.status in {AttemptStatus.SUCCEEDED, AttemptStatus.PARTIAL}
            )
            current_attempt = compatible[-1] if compatible else None
            for attempt in compatible:
                proposals = self._attempt_proposals(attempt, document, lineage)
                if document.document_id not in current_document_ids:
                    scope = ReviewQueueScope.HISTORICAL
                elif current_attempt is not None and (
                    attempt.attempt_id == current_attempt.attempt_id
                ):
                    scope = ReviewQueueScope.CURRENT
                else:
                    scope = ReviewQueueScope.STALE
                for proposal in proposals:
                    assert proposal.proposal_id is not None
                    proposal_rows.append((document, attempt, proposal, scope))
                    if scope is ReviewQueueScope.CURRENT:
                        current_proposal_ids.add(proposal.proposal_id)

        current_ids = frozenset(current_proposal_ids)
        current_items: list[SupportingEvidenceReviewQueueItem] = []
        history_items: list[SupportingEvidenceReviewQueueItem] = []
        for document, attempt, proposal, scope in proposal_rows:
            if document_id is not None and document.document_id != document_id:
                continue
            revisions = self._revision_history(proposal, lineage)
            current_revision = revisions[-1] if revisions else None
            references_current = True
            if current_revision is not None:
                references = (
                    *current_revision.inference_documented_facts,
                    *current_revision.competing_evidence,
                )
                references_current = all(
                    self._reference_is_current(item, lineage, current_ids)
                    for item in references
                )
            item = SupportingEvidenceReviewQueueItem(
                proposal=proposal,
                extraction_attempt=attempt,
                document=document,
                scope=scope,
                review_status=self._review_status(current_revision),
                current_revision=current_revision,
                revision_history=revisions,
                references_current=references_current,
            )
            if scope is ReviewQueueScope.CURRENT:
                current_items.append(item)
            else:
                history_items.append(item)

        statuses = tuple(item.review_status for item in current_items)
        progress = derive_review_progress(statuses)
        return SupportingEvidenceReviewQueue(
            lineage=lineage,
            items=tuple(current_items),
            audit_history=tuple(history_items),
            progress=progress,
        )

    def get_review_queue(
        self,
        formal_lifecycle_id: str,
        *,
        document_id: str | None = None,
    ) -> SupportingEvidenceReviewQueue:
        try:
            return self._build_review_queue(
                formal_lifecycle_id,
                document_id=document_id,
            )
        except SupportingEvidenceLineageError:
            raise
        except (
            ArtifactCorruptionError,
            ArtifactNotFoundError,
            FormalEvidenceIntegrityError,
            FormalEvidenceLineageError,
        ) as exc:
            raise SupportingEvidenceLineageError(
                "Supporting-evidence review history is corrupt or has mixed lineage."
            ) from exc

    @staticmethod
    def _validate_reviewer(reviewer: Any) -> ReviewerDeclaration:
        try:
            return ReviewerDeclaration.model_validate(reviewer)
        except (ValidationError, TypeError, ValueError) as exc:
            raise SupportingEvidenceInvalidReviewerError(
                "A complete locally declared reviewer identity is required."
            ) from exc

    @staticmethod
    def _coerce_action(action: ReviewAction | str) -> ReviewAction:
        try:
            return ReviewAction(action)
        except ValueError as exc:
            raise SupportingEvidenceInvalidReviewError(
                "The requested evidence-review action is not supported."
            ) from exc

    @staticmethod
    def _coerce_classification(
        classification: EvidenceClassification | str | None,
    ) -> EvidenceClassification | None:
        if classification is None:
            return None
        try:
            return EvidenceClassification(classification)
        except ValueError as exc:
            raise SupportingEvidenceInvalidReviewError(
                "The approved evidence classification is not supported."
            ) from exc

    @staticmethod
    def _coerce_category(
        category: DocumentCategory | str | None,
    ) -> DocumentCategory | None:
        if category is None:
            return None
        try:
            return DocumentCategory(category)
        except ValueError as exc:
            raise SupportingEvidenceInvalidReviewError(
                "The approved document category is not supported."
            ) from exc

    def _proposal(
        self,
        proposal_id: str,
        lineage: FormalEvidenceLineage,
    ) -> SupportingEvidenceProposal:
        try:
            proposal = self.repository.load_record(
                "supporting-evidence-proposal.v0.1", proposal_id
            )
        except ArtifactNotFoundError as exc:
            raise SupportingEvidenceUnknownProposalError(
                "The supporting-evidence proposal does not exist."
            ) from exc
        except ArtifactCorruptionError as exc:
            raise SupportingEvidenceLineageError(
                "The supporting-evidence proposal failed integrity validation."
            ) from exc
        if not isinstance(proposal, SupportingEvidenceProposal):
            raise SupportingEvidenceUnknownProposalError(
                "The supporting-evidence proposal has an invalid record type."
            )
        if proposal.lineage != lineage:
            raise SupportingEvidenceLineageError(
                "The proposal belongs to a different formal lifecycle."
            )
        return proposal

    def _current_proposal_ids(self, formal_lifecycle_id: str) -> frozenset[str]:
        return frozenset(
            item.proposal.proposal_id
            for item in self.get_review_queue(formal_lifecycle_id).items
            if item.proposal.proposal_id is not None
        )

    def _resolve_reference(
        self,
        revision_id: str,
        *,
        lineage: FormalEvidenceLineage,
        current_proposal_ids: frozenset[str],
        documented_fact_required: bool,
    ) -> ReviewedEvidenceReference:
        try:
            revision = self.repository.load_record(
                SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
                revision_id,
            )
        except ArtifactNotFoundError as exc:
            raise SupportingEvidenceInvalidReferenceError(
                "A reviewed-evidence reference does not exist."
            ) from exc
        except ArtifactCorruptionError as exc:
            raise SupportingEvidenceInvalidReferenceError(
                "A reviewed-evidence reference failed integrity validation."
            ) from exc
        if not isinstance(revision, SupportingEvidenceReviewRevision):
            raise SupportingEvidenceInvalidReferenceError(
                "A reviewed-evidence reference has an invalid record type."
            )
        if revision.lineage != lineage:
            raise SupportingEvidenceInvalidReferenceError(
                "A reviewed-evidence reference belongs to another lifecycle."
            )
        latest = self.repository.latest_review_revision(revision.proposal_id)
        if (
            latest is None
            or latest.revision_id != revision.revision_id
            or revision.proposal_id not in current_proposal_ids
        ):
            raise SupportingEvidenceInvalidReferenceError(
                "A reviewed-evidence reference is stale or historical."
            )
        if revision.action not in {ReviewAction.ACCEPT, ReviewAction.CORRECT}:
            raise SupportingEvidenceInvalidReferenceError(
                "A reviewed-evidence reference is not accepted or corrected."
            )
        if documented_fact_required and (
            revision.approved_classification
            is not EvidenceClassification.DOCUMENTED_FACT
        ):
            raise SupportingEvidenceInvalidReferenceError(
                "A reviewed-inference link is not a current documented fact."
            )
        return ReviewedEvidenceReference(
            lineage=lineage,
            review_revision_id=revision.revision_id,
            proposal_id=revision.proposal_id,
            action=revision.action,
            classification=revision.approved_classification,
        )

    def review_proposal(
        self,
        formal_lifecycle_id: str,
        proposal_id: str,
        *,
        request_token: str,
        expected_prior_revision_id: str | None,
        action: ReviewAction | str,
        reviewer: ReviewerDeclaration | dict[str, Any],
        approved_claim: str | None = None,
        selected_category: DocumentCategory | str | None = None,
        approved_classification: EvidenceClassification | str | None = None,
        claim_directly_supported_by_excerpt: bool | None = None,
        inference_confidence: float | None = None,
        documented_fact_review_ids: tuple[str, ...] = (),
        competing_review_ids: tuple[str, ...] = (),
        rationale: str,
    ) -> SupportingEvidenceReviewOperationResult:
        lineage = self._lineage_for_change(formal_lifecycle_id)
        proposal = self._proposal(proposal_id, lineage)
        reviewed_by = self._validate_reviewer(reviewer)
        review_action = self._coerce_action(action)
        classification = self._coerce_classification(approved_classification)
        category = self._coerce_category(selected_category)
        request = request_identity(
            request_token,
            {
                "operation": "supporting-evidence-review.v0.1",
                "lineage": lineage.model_dump(mode="json"),
                "proposal_id": proposal_id,
                "expected_prior_revision_id": expected_prior_revision_id,
                "action": review_action.value,
                "reviewer": reviewed_by.model_dump(mode="json"),
                "approved_claim": approved_claim,
                "selected_category": None if category is None else category.value,
                "approved_classification": (
                    None if classification is None else classification.value
                ),
                "claim_directly_supported_by_excerpt": (
                    claim_directly_supported_by_excerpt
                ),
                "inference_confidence": inference_confidence,
                "documented_fact_review_ids": documented_fact_review_ids,
                "competing_review_ids": competing_review_ids,
                "rationale": rationale,
            },
        )
        replay = replay_for_request(
            self.repository,
            request=request,
            operation_type="APPEND_REVIEW_REVISION",
            lineage=lineage,
        )
        if replay is not None:
            if not isinstance(replay.record, SupportingEvidenceReviewRevision):
                raise SupportingEvidenceRequestConflictError(
                    "The request token identifies an incompatible review record."
                )
            return SupportingEvidenceReviewOperationResult(replay.record, True)

        current_proposal_ids = self._current_proposal_ids(formal_lifecycle_id)
        if proposal_id not in current_proposal_ids:
            raise SupportingEvidenceStaleProposalError(
                "Historical or stale proposals cannot receive a new review revision."
            )
        latest = self.repository.latest_review_revision(proposal_id)
        actual_prior = None if latest is None else latest.revision_id
        if expected_prior_revision_id != actual_prior:
            raise SupportingEvidenceStaleRevisionError(
                "The expected review predecessor is no longer current."
            )
        if not rationale.strip():
            raise SupportingEvidenceInvalidReviewError(
                "Evidence review requires an explicit rationale."
            )

        fact_references: tuple[ReviewedEvidenceReference, ...] = ()
        competing_references: tuple[ReviewedEvidenceReference, ...] = ()
        candidate_eligible = False
        source_spans = ()
        resolved_claim = approved_claim
        if review_action is ReviewAction.REJECT:
            if any(
                (
                    approved_claim is not None,
                    category is not None,
                    classification is not None,
                    claim_directly_supported_by_excerpt is not None,
                    inference_confidence is not None,
                    bool(documented_fact_review_ids),
                    bool(competing_review_ids),
                )
            ):
                raise SupportingEvidenceInvalidReviewError(
                    "Rejected proposals must remain audit-only."
                )
        elif review_action in {ReviewAction.ACCEPT, ReviewAction.CORRECT}:
            if classification not in {
                EvidenceClassification.DOCUMENTED_FACT,
                EvidenceClassification.REVIEWED_INFERENCE,
            } or category is None:
                raise SupportingEvidenceInvalidReviewError(
                    "Accepted or corrected evidence requires an explicit fact or inference classification and category."
                )
            source_spans = (
                proposal.primary_source_span,
                *proposal.related_source_spans,
            )
            if review_action is ReviewAction.ACCEPT:
                if approved_claim not in {None, proposal.proposed_claim}:
                    raise SupportingEvidenceInvalidReviewError(
                        "Accepting evidence must preserve the proposed claim exactly."
                    )
                resolved_claim = proposal.proposed_claim
            elif (
                approved_claim is None
                or not approved_claim.strip()
                or approved_claim == proposal.proposed_claim
            ):
                raise SupportingEvidenceInvalidReviewError(
                    "Corrected evidence requires different non-blank wording."
                )
            if classification is EvidenceClassification.DOCUMENTED_FACT:
                if (
                    claim_directly_supported_by_excerpt is not True
                    or inference_confidence is not None
                    or documented_fact_review_ids
                    or competing_review_ids
                ):
                    raise SupportingEvidenceInvalidReviewError(
                        "A documented fact requires direct-excerpt affirmation and no inference or conflict links."
                    )
            else:
                if claim_directly_supported_by_excerpt is not False:
                    raise SupportingEvidenceInvalidReviewError(
                        "A reviewed inference must be declared indirect."
                    )
                if inference_confidence is None:
                    raise SupportingEvidenceInvalidReviewError(
                        "A reviewed inference requires numeric confidence."
                    )
                if not documented_fact_review_ids:
                    raise SupportingEvidenceMissingFactLinkError(
                        "A reviewed inference requires at least one current documented fact."
                    )
                if competing_review_ids:
                    raise SupportingEvidenceInvalidReviewError(
                        "A reviewed inference cannot contain conflict references."
                    )
                fact_references = tuple(
                    self._resolve_reference(
                        item,
                        lineage=lineage,
                        current_proposal_ids=current_proposal_ids,
                        documented_fact_required=True,
                    )
                    for item in documented_fact_review_ids
                )
                if any(item.proposal_id == proposal_id for item in fact_references):
                    raise SupportingEvidenceInvalidReferenceError(
                        "A reviewed inference cannot use its own prior review as a fact."
                    )
            candidate_eligible = True
        else:
            if classification not in {
                EvidenceClassification.UNKNOWN,
                EvidenceClassification.CONFLICT,
            } or category is None:
                raise SupportingEvidenceInvalidReviewError(
                    "Unresolved evidence requires an explicit unknown or conflict classification and category."
                )
            if approved_claim is None or not approved_claim.strip():
                raise SupportingEvidenceInvalidReviewError(
                    "Unresolved evidence requires a plain-English unresolved statement."
                )
            if any(
                (
                    claim_directly_supported_by_excerpt is not None,
                    inference_confidence is not None,
                    bool(documented_fact_review_ids),
                )
            ):
                raise SupportingEvidenceInvalidReviewError(
                    "Unresolved evidence cannot claim fact or inference provenance."
                )
            source_spans = (
                proposal.primary_source_span,
                *proposal.related_source_spans,
            )
            if classification is EvidenceClassification.UNKNOWN:
                if competing_review_ids:
                    raise SupportingEvidenceInvalidReviewError(
                        "Unknown evidence cannot contain competing references."
                    )
            else:
                if len(competing_review_ids) < 2 or len(
                    set(competing_review_ids)
                ) != len(competing_review_ids):
                    raise SupportingEvidenceInsufficientConflictError(
                        "Conflict evidence requires at least two unique current references."
                    )
                competing_references = tuple(
                    self._resolve_reference(
                        item,
                        lineage=lineage,
                        current_proposal_ids=current_proposal_ids,
                        documented_fact_required=False,
                    )
                    for item in competing_review_ids
                )
                if any(
                    item.proposal_id == proposal_id
                    for item in competing_references
                ):
                    raise SupportingEvidenceInvalidReferenceError(
                        "Conflict evidence cannot reference its own prior review."
                    )

        reviewed_at = self.clock()
        revision_id = self.id_factory("supporting-review")
        try:
            revision = SupportingEvidenceReviewRevision(
                schema_version=SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
                contract_family=FORMAL_EVIDENCE_FAMILY,
                lineage=lineage,
                proposal_id=proposal_id,
                revision_id=revision_id,
                revision_number=1 if latest is None else latest.revision_number + 1,
                prior_revision_id=actual_prior,
                action=review_action,
                original_proposal=proposal,
                approved_claim=resolved_claim,
                source_spans=source_spans,
                selected_category=category,
                approved_classification=classification,
                claim_directly_supported_by_excerpt=(
                    claim_directly_supported_by_excerpt
                ),
                inference_confidence=inference_confidence,
                inference_documented_facts=fact_references,
                competing_evidence=competing_references,
                candidate_eligible=candidate_eligible,
                reviewer=reviewed_by,
                rationale=rationale,
                reviewed_at=reviewed_at,
                request=request,
                expected_prior_revision_id=expected_prior_revision_id,
            )
        except ValidationError as exc:
            raise SupportingEvidenceInvalidReviewError(
                "The evidence review does not satisfy the frozen review contract."
            ) from exc
        _, payload_sha = serialize_formal_evidence_record(revision)
        event = next_workflow_event(
            self.repository,
            lineage=lineage,
            event_type=WorkflowEventType.REVIEW_REVISION_RECORDED,
            subject_id=revision.revision_id,
            request=request_identity(
                f"{request_token}:review-event",
                {"review_revision_sha256": payload_sha},
            ),
            payload_sha256=payload_sha,
            occurred_at=reviewed_at,
            event_id=self.id_factory("supporting-event"),
        )
        try:
            stored = self.repository.append_review_revision(
                revision,
                terminal_event=event,
            )
        except FormalEvidenceStaleWriteError as exc:
            raise SupportingEvidenceConcurrentReviewError(
                "Another review operation changed the current revision first."
            ) from exc
        except FormalEvidenceIdempotencyError as exc:
            raise SupportingEvidenceRequestConflictError(
                "This request token was already used for a different review."
            ) from exc
        except (
            FormalEvidenceIntegrityError,
            FormalEvidenceLineageError,
        ) as exc:
            raise SupportingEvidenceInvalidReferenceError(
                "The review no longer matches current immutable evidence history."
            ) from exc
        except Exception as exc:
            raise SupportingEvidenceFinalizationError(
                "The review revision could not be finalized atomically."
            ) from exc
        return SupportingEvidenceReviewOperationResult(stored.record, stored.replayed)

    def get_review_history(
        self,
        formal_lifecycle_id: str,
        proposal_id: str,
    ) -> tuple[SupportingEvidenceReviewRevision, ...]:
        lineage = self._lineage(formal_lifecycle_id)
        proposal = self._proposal(proposal_id, lineage)
        try:
            return self._revision_history(proposal, lineage)
        except (ArtifactCorruptionError, ArtifactNotFoundError) as exc:
            raise SupportingEvidenceLineageError(
                "Review revision history failed integrity validation."
            ) from exc

    def add_context_note(
        self,
        formal_lifecycle_id: str,
        *,
        request_token: str,
        statement: str,
        reviewer: ReviewerDeclaration | dict[str, Any],
        activity_id: str | None = None,
    ) -> ContextNoteOperationResult:
        lineage = self._lineage_for_change(formal_lifecycle_id)
        reviewed_by = self._validate_reviewer(reviewer)
        if not statement.strip():
            raise SupportingEvidenceInvalidReviewError(
                "A context note requires a non-blank statement."
            )
        if activity_id is not None:
            try:
                approved_activity_ids = {
                    item[0]
                    for item in self.repository.approved_activity_catalog(lineage)
                }
            except (ArtifactCorruptionError, FormalEvidenceLineageError) as exc:
                raise SupportingEvidenceLineageError(
                    "The approved process activity catalogue is unavailable."
                ) from exc
            if activity_id not in approved_activity_ids:
                raise SupportingEvidenceLineageError(
                    "The context-note activity is not in the exact approved process."
                )
        request = request_identity(
            request_token,
            {
                "operation": "supporting-evidence-context-note.v0.1",
                "lineage": lineage.model_dump(mode="json"),
                "activity_id": activity_id,
                "statement": statement,
                "reviewer": reviewed_by.model_dump(mode="json"),
            },
        )
        replay = replay_for_request(
            self.repository,
            request=request,
            operation_type="APPEND_CONTEXT_NOTE",
            lineage=lineage,
        )
        if replay is not None:
            if not isinstance(replay.record, ContextNote):
                raise SupportingEvidenceRequestConflictError(
                    "The request token identifies an incompatible context note."
                )
            return ContextNoteOperationResult(replay.record, True)
        created_at = self.clock()
        note = ContextNote(
            schema_version=CONTEXT_NOTE_SCHEMA,
            contract_family=FORMAL_EVIDENCE_FAMILY,
            context_note_id=self.id_factory("context-note"),
            lineage=lineage,
            activity_id=activity_id,
            statement=statement,
            origin="HUMAN_SUPPLIED_CONTEXT_ONLY",
            reviewer=reviewed_by,
            created_at=created_at,
            request=request,
        )
        _, payload_sha = serialize_formal_evidence_record(note)
        event = next_workflow_event(
            self.repository,
            lineage=lineage,
            event_type=WorkflowEventType.CONTEXT_NOTE_RECORDED,
            subject_id=note.context_note_id,
            request=request_identity(
                f"{request_token}:context-note-event",
                {"context_note_sha256": payload_sha},
            ),
            payload_sha256=payload_sha,
            occurred_at=created_at,
            event_id=self.id_factory("supporting-event"),
        )
        try:
            stored = self.repository.append_context_note(
                note,
                terminal_event=event,
            )
        except FormalEvidenceIdempotencyError as exc:
            raise SupportingEvidenceRequestConflictError(
                "This request token was already used for a different context note."
            ) from exc
        except Exception as exc:
            raise SupportingEvidenceFinalizationError(
                "The context note could not be finalized atomically."
            ) from exc
        return ContextNoteOperationResult(stored.record, stored.replayed)

    def get_context_notes(
        self,
        formal_lifecycle_id: str,
        *,
        activity_id: str | None = None,
    ) -> tuple[ContextNote, ...]:
        lineage = self._lineage(formal_lifecycle_id)
        try:
            notes = self.repository.context_notes_for_lifecycle(
                formal_lifecycle_id
            )
        except (ArtifactCorruptionError, ArtifactNotFoundError) as exc:
            raise SupportingEvidenceLineageError(
                "Context-note history failed integrity validation."
            ) from exc
        if any(item.lineage != lineage for item in notes):
            raise SupportingEvidenceLineageError(
                "Context-note history contains mixed formal lineage."
            )
        if activity_id is None:
            return notes
        return tuple(item for item in notes if item.activity_id == activity_id)

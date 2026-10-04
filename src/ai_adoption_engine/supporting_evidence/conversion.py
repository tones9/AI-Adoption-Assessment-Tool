"""Explicit formal-input conversion and readiness orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import TypeAdapter, ValidationError

from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.models.formal_evidence import (
    FORMAL_EVIDENCE_FAMILY,
    FORMAL_EVIDENCE_READINESS_SCHEMA,
    FORMAL_INPUT_CANDIDATE_SET_SCHEMA,
    FORMAL_INPUT_MAPPING_SCHEMA,
    AttemptStatus,
    CandidateDocumentIdentity,
    CandidateExtractionIdentity,
    DocumentCategory,
    EvidenceClassification,
    ExcludedProposalReference,
    FormalEvidenceLineage,
    FormalEvidenceReadiness,
    FormalInputCandidateSet,
    FormalInputMapping,
    FormalTarget,
    FormalTargetKind,
    MappingDisposition,
    ReadinessStatus,
    ReviewAction,
    ReviewedEvidenceReference,
    ReviewerDeclaration,
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
    SupportingEvidenceConcurrentPreparationError,
    SupportingEvidenceFinalizationError,
    SupportingEvidenceIncompletePreparationError,
    SupportingEvidenceInvalidMappingError,
    SupportingEvidenceInvalidReferenceError,
    SupportingEvidenceInvalidReviewerError,
    SupportingEvidenceLineageError,
    SupportingEvidenceRequestConflictError,
    SupportingEvidenceStaleCandidateSetError,
    SupportingEvidenceStaleMappingError,
)
from ai_adoption_engine.supporting_evidence.review import (
    ReviewQueueScope,
    SupportingEvidenceReviewQueueItem,
    SupportingEvidenceReviewService,
)


_FORMAL_TARGET_ADAPTER = TypeAdapter(FormalTarget)


class MappingQueueScope(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    HISTORICAL = "HISTORICAL"


class MappingQueueStatus(StrEnum):
    AWAITING_REVIEW = "AWAITING_REVIEW"
    AWAITING_MAPPING = "AWAITING_MAPPING"
    MAPPED = "MAPPED"
    CONTEXT_ONLY = "CONTEXT_ONLY"
    UNRESOLVED = "UNRESOLVED"
    REJECTED_AUDIT_ONLY = "REJECTED_AUDIT_ONLY"
    STALE_HISTORICAL = "STALE_HISTORICAL"


@dataclass(frozen=True)
class SupportingEvidenceMappingQueueItem:
    review_item: SupportingEvidenceReviewQueueItem
    review_revision: SupportingEvidenceReviewRevision | None
    scope: MappingQueueScope
    status: MappingQueueStatus
    current_mapping: FormalInputMapping | None
    mapping_history: tuple[FormalInputMapping, ...]


@dataclass(frozen=True)
class SupportingEvidenceMappingQueue:
    lineage: FormalEvidenceLineage
    items: tuple[SupportingEvidenceMappingQueueItem, ...]
    audit_history: tuple[SupportingEvidenceMappingQueueItem, ...]


@dataclass(frozen=True)
class FormalInputMappingOperationResult:
    mapping: FormalInputMapping
    replayed: bool


@dataclass(frozen=True)
class CandidateSetOperationResult:
    candidate_set: FormalInputCandidateSet
    replayed: bool


@dataclass(frozen=True)
class ReadinessOperationResult:
    readiness: FormalEvidenceReadiness
    replayed: bool


@dataclass(frozen=True)
class SupportingEvidencePreparationState:
    lineage: FormalEvidenceLineage
    mapping_queue: SupportingEvidenceMappingQueue
    current_candidate_set: FormalInputCandidateSet | None
    candidate_set_current: bool
    latest_readiness: FormalEvidenceReadiness | None
    effective_status: ReadinessStatus
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]


class SupportingEvidenceFormalInputService:
    """Non-default mapping, candidate conversion, and readiness service."""

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
        self.review_service = SupportingEvidenceReviewService(
            repository,
            clock=self.clock,
            id_factory=self.id_factory,
        )

    def _lineage(self, formal_lifecycle_id: str) -> FormalEvidenceLineage:
        try:
            return self.repository.load_active_lineage(formal_lifecycle_id)
        except (FormalEvidenceLineageError, ArtifactCorruptionError) as exc:
            raise SupportingEvidenceLineageError(
                "The formal lifecycle or approved-process lineage is unavailable."
            ) from exc

    def _lineage_for_change(
        self, formal_lifecycle_id: str
    ) -> FormalEvidenceLineage:
        self.repository.assert_writable()
        return self._lineage(formal_lifecycle_id)

    @staticmethod
    def _validate_reviewer(reviewer: Any) -> ReviewerDeclaration:
        try:
            return ReviewerDeclaration.model_validate(reviewer)
        except (ValidationError, TypeError, ValueError) as exc:
            raise SupportingEvidenceInvalidReviewerError(
                "A complete locally declared reviewer identity is required."
            ) from exc

    def _activities(self, lineage: FormalEvidenceLineage) -> frozenset[str]:
        try:
            return frozenset(
                item[0] for item in self.repository.approved_activity_catalog(lineage)
            )
        except (ArtifactCorruptionError, FormalEvidenceLineageError) as exc:
            raise SupportingEvidenceLineageError(
                "The approved process activity catalogue is unavailable."
            ) from exc

    def _mappings(
        self, lineage: FormalEvidenceLineage
    ) -> tuple[FormalInputMapping, ...]:
        try:
            mappings = self.repository.formal_mappings_for_lifecycle(
                lineage.formal_lifecycle_id
            )
        except (ArtifactCorruptionError, ArtifactNotFoundError) as exc:
            raise SupportingEvidenceLineageError(
                "Formal-input mapping history failed integrity validation."
            ) from exc
        for mapping in mappings:
            if mapping.lineage != lineage or len(mapping.supporting_reviews) != 1:
                raise SupportingEvidenceLineageError(
                    "Formal-input mapping history contains corrupt or mixed lineage."
                )
        return mappings

    @staticmethod
    def _mapping_indexes(
        mappings: tuple[FormalInputMapping, ...],
    ) -> tuple[
        dict[str, FormalInputMapping],
        dict[str, tuple[FormalInputMapping, ...]],
    ]:
        latest: dict[str, FormalInputMapping] = {}
        histories: dict[str, list[FormalInputMapping]] = {}
        for mapping in mappings:
            review_id = mapping.supporting_reviews[0].review_revision_id
            histories.setdefault(review_id, []).append(mapping)
            latest[review_id] = mapping
        return latest, {key: tuple(value) for key, value in histories.items()}

    @staticmethod
    def _reference(revision: SupportingEvidenceReviewRevision) -> ReviewedEvidenceReference:
        return ReviewedEvidenceReference(
            lineage=revision.lineage,
            review_revision_id=revision.revision_id,
            proposal_id=revision.proposal_id,
            action=revision.action,
            classification=revision.approved_classification,
        )

    @staticmethod
    def _scope(scope: ReviewQueueScope) -> MappingQueueScope:
        if scope is ReviewQueueScope.CURRENT:
            return MappingQueueScope.CURRENT
        if scope is ReviewQueueScope.STALE:
            return MappingQueueScope.STALE
        return MappingQueueScope.HISTORICAL

    @staticmethod
    def _status(
        revision: SupportingEvidenceReviewRevision | None,
        mapping: FormalInputMapping | None,
        *,
        current: bool,
    ) -> MappingQueueStatus:
        if not current:
            return MappingQueueStatus.STALE_HISTORICAL
        if revision is None:
            return MappingQueueStatus.AWAITING_REVIEW
        if revision.action is ReviewAction.REJECT:
            return MappingQueueStatus.REJECTED_AUDIT_ONLY
        if revision.approved_classification in {
            EvidenceClassification.UNKNOWN,
            EvidenceClassification.CONFLICT,
        }:
            return MappingQueueStatus.UNRESOLVED
        if mapping is None:
            return MappingQueueStatus.AWAITING_MAPPING
        if mapping.disposition is MappingDisposition.CONTEXT_ONLY:
            return MappingQueueStatus.CONTEXT_ONLY
        return MappingQueueStatus.MAPPED

    def get_mapping_queue(
        self, formal_lifecycle_id: str
    ) -> SupportingEvidenceMappingQueue:
        review_queue = self.review_service.get_review_queue(formal_lifecycle_id)
        mappings = self._mappings(review_queue.lineage)
        latest, histories = self._mapping_indexes(mappings)

        current: list[SupportingEvidenceMappingQueueItem] = []
        history: list[SupportingEvidenceMappingQueueItem] = []
        for review_item in (*review_queue.items, *review_queue.audit_history):
            revisions = review_item.revision_history or (None,)
            for revision in revisions:
                is_current = (
                    review_item.scope is ReviewQueueScope.CURRENT
                    and revision is review_item.current_revision
                )
                references_current = review_item.references_current
                mapping = None if revision is None else latest.get(revision.revision_id)
                item = SupportingEvidenceMappingQueueItem(
                    review_item=review_item,
                    review_revision=revision,
                    scope=(
                        MappingQueueScope.CURRENT
                        if is_current and references_current
                        else (
                            MappingQueueScope.STALE
                            if review_item.scope is ReviewQueueScope.CURRENT
                            else self._scope(review_item.scope)
                        )
                    ),
                    status=self._status(
                        revision,
                        mapping,
                        current=is_current and references_current,
                    ),
                    current_mapping=mapping,
                    mapping_history=(
                        () if revision is None else histories.get(revision.revision_id, ())
                    ),
                )
                (current if is_current else history).append(item)
        return SupportingEvidenceMappingQueue(
            lineage=review_queue.lineage,
            items=tuple(current),
            audit_history=tuple(history),
        )

    def _current_review(
        self,
        formal_lifecycle_id: str,
        review_revision_id: str,
    ) -> tuple[FormalEvidenceLineage, SupportingEvidenceReviewRevision]:
        queue = self.get_mapping_queue(formal_lifecycle_id)
        item = next(
            (
                entry
                for entry in queue.items
                if entry.review_revision is not None
                and entry.review_revision.revision_id == review_revision_id
            ),
            None,
        )
        if item is None or item.review_revision is None:
            raise SupportingEvidenceInvalidReferenceError(
                "The reviewed item is stale, historical, or outside this lifecycle."
            )
        if not item.review_item.references_current:
            raise SupportingEvidenceInvalidReferenceError(
                "The reviewed item contains stale evidence references."
            )
        return queue.lineage, item.review_revision

    def _write_mapping(
        self,
        formal_lifecycle_id: str,
        review_revision_id: str,
        *,
        request_token: str,
        expected_prior_mapping_id: str | None,
        activity_id: str,
        disposition: MappingDisposition,
        target: FormalTarget | dict[str, Any] | None,
        value: int | bool | None,
        knowledge_state: KnowledgeState | str,
        approved_evidence_classification: EvidenceClassification | str | None,
        inference_confidence: float | None,
        supporting_documented_fact_review_ids: tuple[str, ...],
        rationale: str,
        reviewer: ReviewerDeclaration | dict[str, Any],
    ) -> FormalInputMappingOperationResult:
        lineage = self._lineage_for_change(formal_lifecycle_id)
        reviewed_by = self._validate_reviewer(reviewer)
        if activity_id not in self._activities(lineage):
            raise SupportingEvidenceInvalidMappingError(
                "The selected activity is not in the exact approved process."
            )
        if not rationale.strip():
            raise SupportingEvidenceInvalidMappingError(
                "Formal-input mapping requires an explicit rationale."
            )
        try:
            state = KnowledgeState(knowledge_state)
            classification = (
                None
                if approved_evidence_classification is None
                else EvidenceClassification(approved_evidence_classification)
            )
            formal_target = (
                None if target is None else _FORMAL_TARGET_ADAPTER.validate_python(target)
            )
        except (ValidationError, TypeError, ValueError) as exc:
            raise SupportingEvidenceInvalidMappingError(
                "The formal target, classification, or knowledge state is invalid."
            ) from exc

        request = request_identity(
            request_token,
            {
                "operation": "supporting-evidence-formal-mapping.v0.1",
                "lineage": lineage.model_dump(mode="json"),
                "review_revision_id": review_revision_id,
                "expected_prior_mapping_id": expected_prior_mapping_id,
                "activity_id": activity_id,
                "disposition": disposition.value,
                "target": (
                    None if formal_target is None else formal_target.model_dump(mode="json")
                ),
                "value": value,
                "knowledge_state": state.value,
                "approved_evidence_classification": (
                    None if classification is None else classification.value
                ),
                "inference_confidence": inference_confidence,
                "supporting_documented_fact_review_ids": (
                    supporting_documented_fact_review_ids
                ),
                "rationale": rationale,
                "reviewer": reviewed_by.model_dump(mode="json"),
            },
        )
        replay = replay_for_request(
            self.repository,
            request=request,
            operation_type="APPEND_FORMAL_MAPPING",
            lineage=lineage,
        )
        if replay is not None:
            if not isinstance(replay.record, FormalInputMapping):
                raise SupportingEvidenceRequestConflictError(
                    "The request token identifies an incompatible mapping record."
                )
            return FormalInputMappingOperationResult(replay.record, True)

        current_lineage, revision = self._current_review(
            formal_lifecycle_id, review_revision_id
        )
        if current_lineage != lineage:
            raise SupportingEvidenceLineageError(
                "The reviewed item no longer matches the active formal lineage."
            )

        reference = self._reference(revision)
        if disposition is MappingDisposition.CONTEXT_ONLY:
            if revision.action not in {ReviewAction.ACCEPT, ReviewAction.CORRECT}:
                raise SupportingEvidenceInvalidMappingError(
                    "Only accepted or corrected evidence may be marked context only."
                )
            if any(
                (
                    formal_target is not None,
                    value is not None,
                    classification is not None,
                    inference_confidence is not None,
                    bool(supporting_documented_fact_review_ids),
                    state is not KnowledgeState.UNKNOWN,
                )
            ):
                raise SupportingEvidenceInvalidMappingError(
                    "Context-only decisions cannot claim a formal input or evidence value."
                )
        else:
            if revision.action is ReviewAction.REJECT:
                raise SupportingEvidenceInvalidMappingError(
                    "Rejected evidence is audit-only and cannot be mapped."
                )
            if classification is not revision.approved_classification:
                raise SupportingEvidenceInvalidMappingError(
                    "The approved mapping classification must match the current review."
                )
            if formal_target is None:
                raise SupportingEvidenceInvalidMappingError(
                    "A formal mapping requires an explicit closed formal target."
                )
            if classification is EvidenceClassification.DOCUMENTED_FACT:
                if (
                    state is not KnowledgeState.KNOWN
                    or inference_confidence is not None
                    or supporting_documented_fact_review_ids
                ):
                    raise SupportingEvidenceInvalidMappingError(
                        "Documented facts require KNOWN state and no inference provenance."
                    )
            elif classification is EvidenceClassification.REVIEWED_INFERENCE:
                expected_fact_ids = tuple(
                    item.review_revision_id
                    for item in revision.inference_documented_facts
                )
                if (
                    state is not KnowledgeState.INFERRED
                    or inference_confidence is None
                    or supporting_documented_fact_review_ids != expected_fact_ids
                ):
                    raise SupportingEvidenceInvalidMappingError(
                        "Reviewed inferences require INFERRED state, confidence, and their exact current fact links."
                    )
            else:
                if (
                    state is not KnowledgeState.UNKNOWN
                    or value is not None
                    or inference_confidence is not None
                    or supporting_documented_fact_review_ids
                ):
                    raise SupportingEvidenceInvalidMappingError(
                        "Unknown and conflict mappings must retain a null unresolved value."
                    )
            if formal_target.kind is FormalTargetKind.ACTIVITY_EVIDENCE and value is not None:
                raise SupportingEvidenceInvalidMappingError(
                    "Activity-level evidence cannot contain an invented scalar value."
                )

        mappings = self._mappings(lineage)
        latest, _ = self._mapping_indexes(mappings)
        actual_prior = latest.get(review_revision_id)
        if (
            None if actual_prior is None else actual_prior.mapping_id
        ) != expected_prior_mapping_id:
            raise SupportingEvidenceStaleMappingError(
                "The expected formal-input mapping predecessor is no longer current."
            )
        mapped_at = self.clock()
        try:
            mapping = FormalInputMapping(
                schema_version=FORMAL_INPUT_MAPPING_SCHEMA,
                contract_family=FORMAL_EVIDENCE_FAMILY,
                mapping_id=self.id_factory("formal-mapping"),
                lineage=lineage,
                activity_id=activity_id,
                target=formal_target,
                disposition=disposition,
                value=value,
                knowledge_state=state,
                approved_evidence_classification=classification,
                supporting_reviews=(reference,),
                supporting_documented_fact_review_ids=(
                    supporting_documented_fact_review_ids
                ),
                mapping_rationale=rationale,
                reviewer=reviewed_by,
                mapped_at=mapped_at,
                inference_confidence=inference_confidence,
                request=request,
            )
        except ValidationError as exc:
            raise SupportingEvidenceInvalidMappingError(
                "The mapping does not satisfy the frozen formal-input contract."
            ) from exc
        _, payload_sha = serialize_formal_evidence_record(mapping)
        event = next_workflow_event(
            self.repository,
            lineage=lineage,
            event_type=WorkflowEventType.FORMAL_MAPPING_RECORDED,
            subject_id=mapping.mapping_id,
            request=request_identity(
                f"{request_token}:mapping-event",
                {"formal_mapping_sha256": payload_sha},
            ),
            payload_sha256=payload_sha,
            occurred_at=mapped_at,
            event_id=self.id_factory("supporting-event"),
        )
        try:
            stored = self.repository.append_formal_mapping(
                mapping,
                expected_prior_mapping_id=expected_prior_mapping_id,
                terminal_event=event,
            )
        except FormalEvidenceStaleWriteError as exc:
            raise SupportingEvidenceConcurrentPreparationError(
                "Another mapping operation changed this reviewed item first."
            ) from exc
        except FormalEvidenceIdempotencyError as exc:
            raise SupportingEvidenceRequestConflictError(
                "This request token was already used for a different mapping."
            ) from exc
        except (FormalEvidenceIntegrityError, FormalEvidenceLineageError) as exc:
            raise SupportingEvidenceInvalidReferenceError(
                "The mapping no longer matches current immutable review history."
            ) from exc
        except Exception as exc:
            raise SupportingEvidenceFinalizationError(
                "The formal-input mapping could not be finalized atomically."
            ) from exc
        return FormalInputMappingOperationResult(stored.record, stored.replayed)

    def map_reviewed_evidence(
        self,
        formal_lifecycle_id: str,
        review_revision_id: str,
        *,
        request_token: str,
        expected_prior_mapping_id: str | None,
        activity_id: str,
        target: FormalTarget | dict[str, Any],
        value: int | bool | None,
        knowledge_state: KnowledgeState | str,
        approved_evidence_classification: EvidenceClassification | str,
        reviewer: ReviewerDeclaration | dict[str, Any],
        rationale: str,
        inference_confidence: float | None = None,
        supporting_documented_fact_review_ids: tuple[str, ...] = (),
    ) -> FormalInputMappingOperationResult:
        return self._write_mapping(
            formal_lifecycle_id,
            review_revision_id,
            request_token=request_token,
            expected_prior_mapping_id=expected_prior_mapping_id,
            activity_id=activity_id,
            disposition=MappingDisposition.MAPPED_FORMAL_INPUT,
            target=target,
            value=value,
            knowledge_state=knowledge_state,
            approved_evidence_classification=approved_evidence_classification,
            inference_confidence=inference_confidence,
            supporting_documented_fact_review_ids=(
                supporting_documented_fact_review_ids
            ),
            rationale=rationale,
            reviewer=reviewer,
        )

    def mark_reviewed_evidence_context_only(
        self,
        formal_lifecycle_id: str,
        review_revision_id: str,
        *,
        request_token: str,
        expected_prior_mapping_id: str | None,
        activity_id: str,
        reviewer: ReviewerDeclaration | dict[str, Any],
        rationale: str,
    ) -> FormalInputMappingOperationResult:
        return self._write_mapping(
            formal_lifecycle_id,
            review_revision_id,
            request_token=request_token,
            expected_prior_mapping_id=expected_prior_mapping_id,
            activity_id=activity_id,
            disposition=MappingDisposition.CONTEXT_ONLY,
            target=None,
            value=None,
            knowledge_state=KnowledgeState.UNKNOWN,
            approved_evidence_classification=None,
            inference_confidence=None,
            supporting_documented_fact_review_ids=(),
            rationale=rationale,
            reviewer=reviewer,
        )

    def get_mapping_history(
        self, formal_lifecycle_id: str
    ) -> tuple[FormalInputMapping, ...]:
        lineage = self._lineage(formal_lifecycle_id)
        return self._mappings(lineage)

    def prepare_candidate_set(
        self,
        formal_lifecycle_id: str,
        *,
        request_token: str,
        explicitly_excluded_document_ids: tuple[str, ...] = (),
    ) -> CandidateSetOperationResult:
        lineage = self._lineage_for_change(formal_lifecycle_id)
        request = request_identity(
            request_token,
            {
                "operation": "supporting-evidence-candidate-set.v0.1",
                "lineage": lineage.model_dump(mode="json"),
                "explicitly_excluded_document_ids": (
                    explicitly_excluded_document_ids
                ),
            },
        )
        replay = replay_for_request(
            self.repository,
            request=request,
            operation_type="APPEND_CANDIDATE_SET",
            lineage=lineage,
        )
        if replay is not None:
            if not isinstance(replay.record, FormalInputCandidateSet):
                raise SupportingEvidenceRequestConflictError(
                    "The request token identifies an incompatible candidate set."
                )
            return CandidateSetOperationResult(replay.record, True)

        current_documents = self.repository.current_documents(formal_lifecycle_id)
        current_ids = tuple(item.document_id for item in current_documents)
        excluded = tuple(explicitly_excluded_document_ids)
        blockers: list[str] = []
        if len(excluded) != len(set(excluded)):
            blockers.append("DUPLICATE_EXCLUDED_DOCUMENT_ID")
        for document_id in excluded:
            if document_id not in current_ids:
                blockers.append(f"UNKNOWN_EXCLUDED_DOCUMENT:{document_id}")
        excluded_set = set(excluded)
        ordered_excluded = tuple(
            document_id for document_id in current_ids if document_id in excluded_set
        )

        document_snapshots: list[CandidateDocumentIdentity] = []
        extraction_snapshots: list[CandidateExtractionIdentity] = []
        explicitly_excluded_proposals: list[ExcludedProposalReference] = []
        for document in current_documents:
            revisions = self.repository.metadata_revisions_for_document(
                formal_lifecycle_id, document.document_id
            )
            if not revisions:
                blockers.append(f"MISSING_DOCUMENT_METADATA:{document.document_id}")
                continue
            metadata = revisions[-1]
            document_snapshots.append(
                CandidateDocumentIdentity(
                    document_id=document.document_id,
                    content_sha256=document.source_blob_sha256,
                    byte_size=document.byte_size,
                    metadata_revision_id=metadata.revision_id,
                )
            )
            attempts = self.repository.extraction_attempts_for_document(
                formal_lifecycle_id=formal_lifecycle_id,
                document_id=document.document_id,
            )
            if document.document_id in excluded_set:
                if not attempts:
                    continue
                if attempts[-1].status is AttemptStatus.STARTED:
                    blockers.append(
                        f"EXCLUDED_DOCUMENT_HAS_NONTERMINAL_EXTRACTION:{document.document_id}"
                    )
                    continue
                attempt = attempts[-1]
                extraction_snapshots.append(
                    CandidateExtractionIdentity(
                        extraction_attempt_id=attempt.attempt_id,
                        document_id=document.document_id,
                        status=attempt.status,
                        proposal_ids=attempt.proposal_ids,
                    )
                )
                explicitly_excluded_proposals.extend(
                    ExcludedProposalReference(
                        proposal_id=proposal_id,
                        reason="Excluded through an explicit supporting-document decision.",
                    )
                    for proposal_id in attempt.proposal_ids
                )
                continue
            if not attempts or attempts[-1].status not in {
                AttemptStatus.SUCCEEDED,
                AttemptStatus.PARTIAL,
            }:
                blockers.append(
                    f"DOCUMENT_NOT_TERMINALLY_PROCESSED:{document.document_id}"
                )
                continue
            attempt = attempts[-1]
            extraction_snapshots.append(
                CandidateExtractionIdentity(
                    extraction_attempt_id=attempt.attempt_id,
                    document_id=document.document_id,
                    status=attempt.status,
                    proposal_ids=attempt.proposal_ids,
                )
            )

        mapping_queue = self.get_mapping_queue(formal_lifecycle_id)
        queue_by_proposal = {
            item.review_item.proposal.proposal_id: item
            for item in mapping_queue.items
        }
        mappings: list[FormalInputMapping] = []
        review_references: list[ReviewedEvidenceReference] = []
        context_only_ids: list[str] = []
        unknown_ids: list[str] = []
        conflict_ids: list[str] = []
        rejected: list[ExcludedProposalReference] = list(
            explicitly_excluded_proposals
        )
        for extraction in extraction_snapshots:
            if extraction.document_id in excluded_set:
                continue
            for proposal_id in extraction.proposal_ids:
                item = queue_by_proposal.get(proposal_id)
                if item is None or item.review_revision is None:
                    blockers.append(f"PROPOSAL_UNREVIEWED:{proposal_id}")
                    continue
                revision = item.review_revision
                reference = self._reference(revision)
                review_references.append(reference)
                if not item.review_item.references_current:
                    blockers.append(f"REVIEW_REFERENCES_STALE:{revision.revision_id}")
                    continue
                if revision.action is ReviewAction.REJECT:
                    rejected.append(
                        ExcludedProposalReference(
                            proposal_id=proposal_id,
                            reason="Rejected by mandatory human review.",
                        )
                    )
                elif revision.approved_classification is EvidenceClassification.UNKNOWN:
                    unknown_ids.append(revision.revision_id)
                    if (
                        item.current_mapping is not None
                        and item.current_mapping.disposition
                        is MappingDisposition.MAPPED_FORMAL_INPUT
                    ):
                        mappings.append(item.current_mapping)
                elif revision.approved_classification is EvidenceClassification.CONFLICT:
                    conflict_ids.append(revision.revision_id)
                    if (
                        item.current_mapping is not None
                        and item.current_mapping.disposition
                        is MappingDisposition.MAPPED_FORMAL_INPUT
                    ):
                        mappings.append(item.current_mapping)
                elif item.current_mapping is None:
                    blockers.append(f"REVIEW_AWAITING_MAPPING:{revision.revision_id}")
                elif (
                    item.current_mapping.disposition
                    is MappingDisposition.CONTEXT_ONLY
                ):
                    context_only_ids.append(revision.revision_id)
                else:
                    mappings.append(item.current_mapping)

        if blockers:
            raise SupportingEvidenceIncompletePreparationError(
                "Formal-input preparation is incomplete.",
                blockers=tuple(blockers),
            )
        prior_sets = self.repository.candidate_sets_for_lifecycle(formal_lifecycle_id)
        prior_id = None if not prior_sets else prior_sets[-1].candidate_set_id
        created_at = self.clock()
        try:
            candidate = FormalInputCandidateSet(
                schema_version=FORMAL_INPUT_CANDIDATE_SET_SCHEMA,
                contract_family=FORMAL_EVIDENCE_FAMILY,
                candidate_set_id=self.id_factory("formal-candidate-set"),
                lineage=lineage,
                current_documents=tuple(document_snapshots),
                current_extractions=tuple(extraction_snapshots),
                current_reviews=tuple(review_references),
                ordered_formal_mappings=tuple(mappings),
                context_only_review_revision_ids=tuple(context_only_ids),
                retained_unknown_review_revision_ids=tuple(unknown_ids),
                retained_conflict_review_revision_ids=tuple(conflict_ids),
                rejected_or_excluded_proposals=tuple(rejected),
                explicitly_excluded_document_ids=ordered_excluded,
                prior_candidate_set_id=prior_id,
                created_at=created_at,
                conversion_request=request,
            )
        except ValidationError as exc:
            raise SupportingEvidenceIncompletePreparationError(
                "The complete preparation snapshot failed frozen-contract validation.",
                blockers=("CANDIDATE_SNAPSHOT_INVALID",),
            ) from exc
        _, payload_sha = serialize_formal_evidence_record(candidate)
        event = next_workflow_event(
            self.repository,
            lineage=lineage,
            event_type=WorkflowEventType.CANDIDATE_SET_CREATED,
            subject_id=candidate.candidate_set_id,
            request=request_identity(
                f"{request_token}:candidate-event",
                {"candidate_set_sha256": payload_sha},
            ),
            payload_sha256=payload_sha,
            occurred_at=created_at,
            event_id=self.id_factory("supporting-event"),
        )
        try:
            stored = self.repository.append_candidate_set(
                candidate,
                terminal_event=event,
            )
        except FormalEvidenceStaleWriteError as exc:
            raise SupportingEvidenceConcurrentPreparationError(
                "Evidence history changed while the candidate set was being prepared."
            ) from exc
        except FormalEvidenceIdempotencyError as exc:
            raise SupportingEvidenceRequestConflictError(
                "This request token was already used for another candidate set."
            ) from exc
        except (FormalEvidenceIntegrityError, FormalEvidenceLineageError) as exc:
            raise SupportingEvidenceStaleCandidateSetError(
                "The candidate snapshot no longer matches current evidence history."
            ) from exc
        except Exception as exc:
            raise SupportingEvidenceFinalizationError(
                "The candidate set could not be finalized atomically."
            ) from exc
        return CandidateSetOperationResult(stored.record, stored.replayed)

    def evaluate_and_persist_readiness(
        self,
        formal_lifecycle_id: str,
        candidate_set_id: str,
        *,
        request_token: str,
    ) -> ReadinessOperationResult:
        lineage = self._lineage_for_change(formal_lifecycle_id)
        request = request_identity(
            request_token,
            {
                "operation": "supporting-evidence-readiness.v0.1",
                "lineage": lineage.model_dump(mode="json"),
                "candidate_set_id": candidate_set_id,
            },
        )
        replay = replay_for_request(
            self.repository,
            request=request,
            operation_type="APPEND_READINESS",
            lineage=lineage,
        )
        if replay is not None:
            if not isinstance(replay.record, FormalEvidenceReadiness):
                raise SupportingEvidenceRequestConflictError(
                    "The request token identifies an incompatible readiness record."
                )
            return ReadinessOperationResult(replay.record, True)
        try:
            candidate = self.repository.load_record(
                FORMAL_INPUT_CANDIDATE_SET_SCHEMA, candidate_set_id
            )
        except (ArtifactNotFoundError, ArtifactCorruptionError) as exc:
            raise SupportingEvidenceStaleCandidateSetError(
                "The candidate set is missing or failed integrity validation."
            ) from exc
        if not isinstance(candidate, FormalInputCandidateSet) or candidate.lineage != lineage:
            raise SupportingEvidenceStaleCandidateSetError(
                "The candidate set belongs to incompatible formal lineage."
            )
        try:
            self.repository.validate_candidate_current(candidate)
        except (
            ArtifactCorruptionError,
            FormalEvidenceIntegrityError,
            FormalEvidenceLineageError,
            FormalEvidenceStaleWriteError,
        ) as exc:
            raise SupportingEvidenceStaleCandidateSetError(
                "The candidate set is stale and must be prepared again."
            ) from exc

        positive = any(
            mapping.disposition is MappingDisposition.MAPPED_FORMAL_INPUT
            and mapping.approved_evidence_classification
            in {
                EvidenceClassification.DOCUMENTED_FACT,
                EvidenceClassification.REVIEWED_INFERENCE,
            }
            and mapping.target is not None
            and mapping.target.kind is not FormalTargetKind.ACTIVITY_EVIDENCE
            and mapping.value is not None
            for mapping in candidate.ordered_formal_mappings
        )
        reasons = () if positive else ("NO_POSITIVE_MAPPED_FORMAL_VALUE",)
        status = (
            ReadinessStatus.READY_TO_ATTEMPT
            if positive
            else ReadinessStatus.NOT_READY
        )

        covered_categories: set[DocumentCategory] = set()
        excluded_ids = set(candidate.explicitly_excluded_document_ids)
        for document in candidate.current_documents:
            if document.document_id in excluded_ids:
                continue
            revisions = self.repository.metadata_revisions_for_document(
                formal_lifecycle_id, document.document_id
            )
            if not revisions or revisions[-1].revision_id != document.metadata_revision_id:
                raise SupportingEvidenceStaleCandidateSetError(
                    "Candidate document metadata is no longer current."
                )
            covered_categories.add(revisions[-1].primary_category)
            covered_categories.update(revisions[-1].additional_categories)
        warnings = tuple(
            category
            for category in DocumentCategory
            if category not in covered_categories
        )
        evaluated_at = self.clock()
        readiness = FormalEvidenceReadiness(
            schema_version=FORMAL_EVIDENCE_READINESS_SCHEMA,
            contract_family=FORMAL_EVIDENCE_FAMILY,
            readiness_id=self.id_factory("formal-readiness"),
            lineage=lineage,
            candidate_set=candidate,
            current_review_revision_ids=tuple(
                item.review_revision_id for item in candidate.current_reviews
            ),
            processing_complete_or_explicitly_excluded=True,
            every_current_proposal_terminally_reviewed=True,
            every_accepted_or_corrected_item_mapped_or_context_only=True,
            candidate_set_includes_every_current_review_revision=True,
            lineage_and_integrity_valid=True,
            uncovered_document_categories=warnings,
            retained_unknown_count=len(
                candidate.retained_unknown_review_revision_ids
            ),
            retained_conflict_count=len(
                candidate.retained_conflict_review_revision_ids
            ),
            status=status,
            reasons=reasons,
            evaluated_at=evaluated_at,
        )
        _, payload_sha = serialize_formal_evidence_record(readiness)
        event = next_workflow_event(
            self.repository,
            lineage=lineage,
            event_type=WorkflowEventType.READINESS_EVALUATED,
            subject_id=readiness.readiness_id,
            request=request_identity(
                f"{request_token}:readiness-event",
                {"readiness_sha256": payload_sha},
            ),
            payload_sha256=payload_sha,
            occurred_at=evaluated_at,
            event_id=self.id_factory("supporting-event"),
        )
        try:
            stored = self.repository.append_readiness(
                readiness,
                request=request,
                terminal_event=event,
            )
        except FormalEvidenceStaleWriteError as exc:
            raise SupportingEvidenceConcurrentPreparationError(
                "Evidence history changed while readiness was being evaluated."
            ) from exc
        except FormalEvidenceIdempotencyError as exc:
            raise SupportingEvidenceRequestConflictError(
                "This request token was already used for another readiness operation."
            ) from exc
        except (FormalEvidenceIntegrityError, FormalEvidenceLineageError) as exc:
            raise SupportingEvidenceStaleCandidateSetError(
                "Readiness could not use the stale or incompatible candidate set."
            ) from exc
        except Exception as exc:
            raise SupportingEvidenceFinalizationError(
                "Readiness could not be finalized atomically."
            ) from exc
        return ReadinessOperationResult(stored.record, stored.replayed)

    def get_current_preparation_state(
        self, formal_lifecycle_id: str
    ) -> SupportingEvidencePreparationState:
        mapping_queue = self.get_mapping_queue(formal_lifecycle_id)
        lineage = mapping_queue.lineage
        try:
            candidates = self.repository.candidate_sets_for_lifecycle(
                formal_lifecycle_id
            )
            readiness_history = self.repository.readiness_for_lifecycle(
                formal_lifecycle_id
            )
        except (ArtifactCorruptionError, ArtifactNotFoundError) as exc:
            raise SupportingEvidenceLineageError(
                "Formal preparation history failed integrity validation."
            ) from exc
        if any(item.lineage != lineage for item in (*candidates, *readiness_history)):
            raise SupportingEvidenceLineageError(
                "Formal preparation history contains mixed lineage."
            )
        candidate = None if not candidates else candidates[-1]
        candidate_current = False
        blockers: tuple[str, ...] = ()
        if candidate is not None:
            try:
                self.repository.validate_candidate_current(candidate)
                candidate_current = True
            except (
                ArtifactCorruptionError,
                FormalEvidenceIntegrityError,
                FormalEvidenceLineageError,
                FormalEvidenceStaleWriteError,
            ):
                blockers = ("CANDIDATE_SET_STALE",)
        latest_readiness = next(
            (
                item
                for item in reversed(readiness_history)
                if candidate is not None
                and item.candidate_set.candidate_set_id == candidate.candidate_set_id
            ),
            None,
        )
        if candidate is None:
            blockers = ("CANDIDATE_SET_NOT_PREPARED",)
        elif candidate_current and latest_readiness is None:
            blockers = ("READINESS_NOT_EVALUATED",)
        elif candidate_current and latest_readiness is not None:
            blockers = latest_readiness.reasons
        effective = (
            latest_readiness.status
            if candidate_current and latest_readiness is not None
            else ReadinessStatus.NOT_READY
        )
        warnings = (
            ()
            if latest_readiness is None
            else tuple(
                f"UNCOVERED_DOCUMENT_CATEGORY:{item.value}"
                for item in latest_readiness.uncovered_document_categories
            )
        )
        return SupportingEvidencePreparationState(
            lineage=lineage,
            mapping_queue=mapping_queue,
            current_candidate_set=candidate,
            candidate_set_current=candidate_current,
            latest_readiness=latest_readiness,
            effective_status=effective,
            blockers=blockers,
            warnings=warnings,
        )

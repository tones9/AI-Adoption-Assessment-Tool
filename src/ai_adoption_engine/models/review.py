"""Provider-independent human-review and approval contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_adoption_engine.models.candidate_process import (
    CandidateAssertion,
    CandidateBusinessProcess,
    CandidateCollection,
    CandidateDecision,
    CandidateDependency,
    CandidateProcessStep,
    CollectionCompleteness,
    OrderBasis,
    ResolvedEvidenceReference,
)
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.extraction import ExtractionIssue
from ai_adoption_engine.models.process import BusinessProcess


class InformationOrigin(StrEnum):
    DOCUMENT_SUPPORTED = "DOCUMENT_SUPPORTED"
    MODEL_INFERRED = "MODEL_INFERRED"
    HUMAN_SUPPLIED = "HUMAN_SUPPLIED"
    UNKNOWN = "UNKNOWN"


class ReviewDisposition(StrEnum):
    UNREVIEWED = "unreviewed"
    ACCEPTED = "accepted"
    CORRECTED = "corrected"
    REJECTED = "rejected"
    UNKNOWN_RETAINED = "unknown-retained"


class ReviewStatus(StrEnum):
    IN_REVIEW = "in-review"
    APPROVED = "approved"


class ReviewAction(StrEnum):
    ACCEPT = "accept"
    CORRECT = "correct"
    REJECT = "reject"
    RESOLVE_UNKNOWN = "resolve-unknown"
    RETAIN_UNKNOWN = "retain-unknown"
    REORDER_STEPS = "reorder-steps"
    ACCEPT_STEP_ORDER = "accept-step-order"
    CORRECT_DEPENDENCY = "correct-dependency"
    SELECT_PRIMARY_ACTOR = "select-primary-actor"
    RESOLVE_CONFLICT = "resolve-conflict"
    APPROVE = "approve"


class ConflictStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class ReviewedAssertion(BaseModel):
    """Current review state while retaining the original Phase 3 assertion."""

    model_config = ConfigDict(extra="forbid")

    original: CandidateAssertion[Any]
    value: Any | None = None
    knowledge_state: KnowledgeState
    origin: InformationOrigin
    rationale: str = Field(min_length=1)
    evidence: list[ResolvedEvidenceReference] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    disposition: ReviewDisposition = ReviewDisposition.UNREVIEWED
    retained: bool = True

    @model_validator(mode="after")
    def validate_review_provenance(self) -> "ReviewedAssertion":
        if self.origin is InformationOrigin.HUMAN_SUPPLIED and self.evidence:
            raise ValueError("Human-supplied information cannot claim document evidence")
        if (
            self.origin is InformationOrigin.DOCUMENT_SUPPORTED
            and self.knowledge_state is not KnowledgeState.UNKNOWN
            and not self.evidence
        ):
            raise ValueError("Document-supported information requires document evidence")
        if self.knowledge_state is KnowledgeState.UNKNOWN:
            if self.value is not None or self.evidence or self.confidence is not None:
                raise ValueError("Unknown reviewed assertions cannot claim a value or evidence")
            if self.origin is not InformationOrigin.UNKNOWN:
                raise ValueError("Unknown reviewed assertions must use UNKNOWN origin")
        elif self.value is None:
            raise ValueError("Known or inferred reviewed assertions require a value")
        if self.knowledge_state is KnowledgeState.INFERRED:
            if self.origin is not InformationOrigin.MODEL_INFERRED:
                raise ValueError("Inferred reviewed assertions retain MODEL_INFERRED origin")
            if self.confidence is None:
                raise ValueError("Inferred reviewed assertions require confidence")
        return self


class ReviewedCollection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original: CandidateCollection[Any]
    completeness: CollectionCompleteness
    rationale: str = Field(min_length=1)
    items: list[ReviewedAssertion] = Field(default_factory=list)
    evidence: list[ResolvedEvidenceReference] = Field(default_factory=list)


class ReviewedCharacteristic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CriterionName
    assertion: ReviewedAssertion


class ReviewedCapabilitySignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    assertion: ReviewedAssertion


class ReviewedDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original: CandidateDecision
    condition: ReviewedAssertion
    branches: ReviewedCollection
    retained: bool = True


class ReviewedDependency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original: CandidateDependency
    target_label: ReviewedAssertion
    relationship: ReviewedAssertion
    target_candidate_step_id: str | None = None
    retained: bool = True


class ReviewedProcessStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original: CandidateProcessStep
    candidate_step_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    order_basis: OrderBasis
    document_order: ReviewedAssertion
    activity: ReviewedAssertion
    description: ReviewedAssertion
    actors: ReviewedCollection
    responsible_roles: ReviewedCollection
    systems: ReviewedCollection
    inputs: ReviewedCollection
    outputs: ReviewedCollection
    decisions: list[ReviewedDecision] = Field(default_factory=list)
    dependencies: list[ReviewedDependency] = Field(default_factory=list)
    exceptions: ReviewedCollection
    operational_characteristics: ReviewedCollection
    criteria: list[ReviewedCharacteristic]
    human_accountability_required: ReviewedAssertion
    capability_signals: list[ReviewedCapabilitySignal]
    primary_actor: str | None = None
    retained: bool = True


class ReviewConflict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conflict_id: str = Field(min_length=1)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    blocking: bool
    field_path: str | None = None
    status: ConflictStatus = ConflictStatus.OPEN
    resolution: str | None = None


class ReviewEvent(BaseModel):
    """Immutable audit event; snapshots prevent silent provenance replacement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    occurred_at: datetime
    action: ReviewAction
    field_path: str = Field(min_length=1)
    before_snapshot: str | None = None
    after_snapshot: str | None = None
    rationale: str | None = None


class ProcessReviewSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str = Field(min_length=1)
    status: ReviewStatus = ReviewStatus.IN_REVIEW
    created_at: datetime
    updated_at: datetime
    original_candidate: CandidateBusinessProcess
    extraction_issues: list[ExtractionIssue] = Field(default_factory=list)
    process_name: ReviewedAssertion
    process_description: ReviewedAssertion
    process_objective: ReviewedAssertion
    steps: list[ReviewedProcessStep]
    order_accepted: bool = False
    conflicts: list[ReviewConflict] = Field(default_factory=list)
    events: list[ReviewEvent] = Field(default_factory=list)


class ExplicitApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_statement: Literal["APPROVE CURRENT-STATE PROCESS"]
    approved_at: datetime
    rationale: str | None = None


class ApprovalError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    field_path: str | None = None


class ApprovedProcessReview(BaseModel):
    """Canonical rich review record plus the narrow Phase 1 projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    approval: ExplicitApproval
    review: ProcessReviewSession
    business_process: BusinessProcess


class ApprovalResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approved: ApprovedProcessReview | None = None
    errors: list[ApprovalError] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_one_outcome(self) -> "ApprovalResult":
        if (self.approved is None) == (not self.errors):
            raise ValueError("Approval result must contain an approval or validation errors")
        return self


def origin_for_candidate(assertion: CandidateAssertion[Any]) -> InformationOrigin:
    if assertion.knowledge_state is KnowledgeState.KNOWN:
        return InformationOrigin.DOCUMENT_SUPPORTED
    if assertion.knowledge_state is KnowledgeState.INFERRED:
        return InformationOrigin.MODEL_INFERRED
    return InformationOrigin.UNKNOWN


def reviewed_assertion(assertion: CandidateAssertion[Any]) -> ReviewedAssertion:
    return ReviewedAssertion(
        original=assertion,
        value=assertion.value,
        knowledge_state=assertion.knowledge_state,
        origin=origin_for_candidate(assertion),
        rationale=assertion.rationale,
        evidence=assertion.evidence,
        confidence=assertion.confidence,
    )


def reviewed_collection(collection: CandidateCollection[Any]) -> ReviewedCollection:
    return ReviewedCollection(
        original=collection,
        completeness=collection.completeness,
        rationale=collection.rationale,
        items=[reviewed_assertion(item) for item in collection.items],
        evidence=collection.evidence,
    )


def reviewed_step(step: CandidateProcessStep) -> ReviewedProcessStep:
    return ReviewedProcessStep(
        original=step,
        candidate_step_id=step.candidate_step_id,
        sequence=step.sequence,
        order_basis=step.order_basis,
        document_order=reviewed_assertion(step.document_order),
        activity=reviewed_assertion(step.activity),
        description=reviewed_assertion(step.description),
        actors=reviewed_collection(step.actors),
        responsible_roles=reviewed_collection(step.responsible_roles),
        systems=reviewed_collection(step.systems),
        inputs=reviewed_collection(step.inputs),
        outputs=reviewed_collection(step.outputs),
        decisions=[
            ReviewedDecision(
                original=item,
                condition=reviewed_assertion(item.condition),
                branches=reviewed_collection(item.branches),
            )
            for item in step.decisions
        ],
        dependencies=[
            ReviewedDependency(
                original=item,
                target_label=reviewed_assertion(item.target_label),
                relationship=reviewed_assertion(item.relationship),
                target_candidate_step_id=item.target_candidate_step_id,
            )
            for item in step.dependencies
        ],
        exceptions=reviewed_collection(step.exceptions),
        operational_characteristics=reviewed_collection(
            step.operational_characteristics
        ),
        criteria=[
            ReviewedCharacteristic(
                name=item.name, assertion=reviewed_assertion(item.assertion)
            )
            for item in step.characteristics.criteria
        ],
        human_accountability_required=reviewed_assertion(
            step.characteristics.human_accountability_required
        ),
        capability_signals=[
            ReviewedCapabilitySignal(
                name=item.name.value, assertion=reviewed_assertion(item.assertion)
            )
            for item in step.characteristics.capability_signals
        ],
    )

"""Immutable sidecar contracts for the non-decision GRW M1 lifecycle."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_adoption_engine.models.assessment import GateResult, PriorityScore
from ai_adoption_engine.models.decision_support import InformationGap
from ai_adoption_engine.models.enums import KnowledgeState, PriorityStatus, RecommendationMode


class GrwEvidenceClass(StrEnum):
    OPERATOR_PROVIDED_ESTIMATE = "OPERATOR_PROVIDED_ESTIMATE"
    UNKNOWN = "UNKNOWN"


class GrwSubmissionStatus(StrEnum):
    SUBMITTED = "SUBMITTED"


class GrwReviewDecision(StrEnum):
    ACCEPT_PRELIMINARY = "ACCEPT_PRELIMINARY"
    ACCEPT_RECORDED_ONLY = "ACCEPT_RECORDED_ONLY"
    REJECT = "REJECT"


class GrwAdmissibilityEffect(StrEnum):
    PRELIMINARY_UNDERSTANDING = "PRELIMINARY_UNDERSTANDING"
    RECORDED_ONLY = "RECORDED_ONLY"
    NONE = "NONE"


class GrwParseStatus(StrEnum):
    CANDIDATE_NEEDS_REVIEW = "CANDIDATE_NEEDS_REVIEW"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_PARSED = "NOT_PARSED"


class GrwArtifactReference(BaseModel):
    """Pinned immutable baseline artefact identity, independent of active pointers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(min_length=1)
    artifact_revision: int = Field(ge=1)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class GrwBaselineReference(BaseModel):
    """The exact Phase 4–6 baseline which M1 is prohibited from changing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    assessment_id: str = Field(min_length=1)
    package_id: str = Field(min_length=1)
    approved_review: GrwArtifactReference
    integrated_assessment: GrwArtifactReference
    decision_package: GrwArtifactReference


class GrwGapReference(BaseModel):
    """A snapshot of one original Phase 6 gap, bound to its package step."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    package_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    current_activity: str = Field(min_length=1)
    information_gap: InformationGap

    @model_validator(mode="after")
    def validate_gap_lineage(self) -> "GrwGapReference":
        if self.information_gap.step_id != self.step_id:
            raise ValueError("The InformationGap must belong to the pinned step")
        return self


class GrwQuestion(BaseModel):
    """One deterministic, customer-readable M1 question; never model-generated."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: Literal["grw-m1-repetition-typical-month-volume-v0.1"] = (
        "grw-m1-repetition-typical-month-volume-v0.1"
    )
    priority_category: Literal["DECISION_STRENGTHENING"] = "DECISION_STRENGTHENING"
    customer_question: str = Field(min_length=1)
    help_text: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)


class GrwParsedEstimateCandidate(BaseModel):
    """A non-authoritative observation candidate. It has no score or midpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    parser_version: Literal["grw-m1-range-parser-v0.1"] = "grw-m1-range-parser-v0.1"
    parse_status: GrwParseStatus
    lower_bound: int | None = Field(default=None, ge=0)
    upper_bound: int | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, min_length=1)
    period: str | None = Field(default=None, min_length=1)
    qualifiers: list[str] = Field(default_factory=list)
    ambiguity_note: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_candidate(self) -> "GrwParsedEstimateCandidate":
        if self.parse_status is GrwParseStatus.CANDIDATE_NEEDS_REVIEW:
            if None in (self.lower_bound, self.upper_bound, self.unit, self.period):
                raise ValueError("A recognised range requires bounds, unit and period")
            if self.lower_bound > self.upper_bound:
                raise ValueError("A range lower bound must not exceed its upper bound")
            if self.ambiguity_note is not None:
                raise ValueError("A recognised range must not carry an ambiguity note")
        elif any(
            value is not None
            for value in (self.lower_bound, self.upper_bound, self.unit, self.period)
        ):
            raise ValueError("Only a recognised range may carry parsed numeric fields")
        return self


class GrwM1Context(BaseModel):
    """Read-only package, gap and question context for the optional M1 UI."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline: GrwBaselineReference
    gap: GrwGapReference
    question: GrwQuestion


class GrwEvidenceSubmission(BaseModel):
    """Immutable customer-provided answer. It is never an assessment input in M1."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    submission_id: str = Field(min_length=1)
    status: Literal[GrwSubmissionStatus.SUBMITTED] = GrwSubmissionStatus.SUBMITTED
    submitted_at: datetime
    baseline: GrwBaselineReference
    gap: GrwGapReference
    question: GrwQuestion
    answer_text: str = Field(min_length=1, max_length=2000)
    evidence_class: GrwEvidenceClass
    parsed_candidate: GrwParsedEstimateCandidate | None = None

    @model_validator(mode="after")
    def validate_submission(self) -> "GrwEvidenceSubmission":
        if not self.answer_text.strip():
            raise ValueError("A submitted answer must contain non-whitespace text")
        if self.gap.package_id != self.baseline.package_id:
            raise ValueError("The gap must belong to the pinned decision package")
        if self.evidence_class is GrwEvidenceClass.UNKNOWN and self.parsed_candidate:
            raise ValueError("An explicit unknown must not carry a parsed estimate")
        return self


class GrwCriterionSnapshot(BaseModel):
    """The selected formal criterion state, retained solely as a non-change proof."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    criterion_name: Literal["repetition"] = "repetition"
    value: int | None
    knowledge_state: KnowledgeState
    rationale: str
    evidence_ids: list[str]
    confidence: float | None


class GrwNonChangeProof(BaseModel):
    """A compact snapshot proving M1 did not alter a formal decision artefact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline: GrwBaselineReference
    criterion: GrwCriterionSnapshot
    gate_results: list[GateResult]
    gate_results_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    recommendation_mode: RecommendationMode
    priority_status: PriorityStatus
    priority: PriorityScore | None
    roi_statement: str = Field(min_length=1)
    assessment_effect: Literal["NONE"] = "NONE"


class GrwEvidenceReview(BaseModel):
    """Immutable human review of a submitted M1 response, with no assessment effect."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    review_id: str = Field(min_length=1)
    reviewed_at: datetime
    submission_artifact_id: str = Field(min_length=1)
    submission_payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer_label: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=2000)
    decision: GrwReviewDecision
    admissibility_effect: GrwAdmissibilityEffect
    assessment_effect: Literal["NONE"] = "NONE"
    non_change_proof: GrwNonChangeProof

    @model_validator(mode="after")
    def validate_review_effect(self) -> "GrwEvidenceReview":
        expected = {
            GrwReviewDecision.ACCEPT_PRELIMINARY: GrwAdmissibilityEffect.PRELIMINARY_UNDERSTANDING,
            GrwReviewDecision.ACCEPT_RECORDED_ONLY: GrwAdmissibilityEffect.RECORDED_ONLY,
            GrwReviewDecision.REJECT: GrwAdmissibilityEffect.NONE,
        }[self.decision]
        if self.admissibility_effect is not expected:
            raise ValueError("Review decision and admissibility effect do not match")
        return self


class GrwM1Status(BaseModel):
    """Read-only rendering state; it does not create a mutable GRW workspace."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    context: GrwM1Context | None
    submission_artifact_id: str | None = None
    submission: GrwEvidenceSubmission | None = None
    review_artifact_id: str | None = None
    review: GrwEvidenceReview | None = None

    @model_validator(mode="after")
    def validate_status_links(self) -> "GrwM1Status":
        if (self.submission_artifact_id is None) != (self.submission is None):
            raise ValueError("Submission identity and payload must be present together")
        if (self.review_artifact_id is None) != (self.review is None):
            raise ValueError("Review identity and payload must be present together")
        if self.review and self.submission and self.review.submission_artifact_id != self.submission_artifact_id:
            raise ValueError("Review must reference the displayed submission")
        return self

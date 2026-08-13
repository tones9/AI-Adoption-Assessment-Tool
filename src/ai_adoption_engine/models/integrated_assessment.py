"""Phase 5 orchestration results and cross-phase traceability references."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_adoption_engine.models.assessment import ProcessAssessment
from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.models.review import InformationOrigin, ReviewDisposition


class IntegratedAssessmentStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class IntegrationFailureCode(StrEnum):
    APPROVAL_REQUIRED = "approval-required"
    INVALID_APPROVAL_ARTIFACT = "invalid-approval-artifact"
    BLOCKED_REVIEW = "blocked-review"
    PROJECTION_UNAVAILABLE = "projection-unavailable"
    INVALID_PROCESS_PROJECTION = "invalid-process-projection"
    POLICY_LOAD_FAILED = "policy-load-failed"
    ASSESSMENT_ENGINE_FAILED = "assessment-engine-failed"
    INVALID_ENGINE_OUTPUT = "invalid-engine-output"
    TRACEABILITY_BUILD_FAILED = "traceability-build-failed"


class AssessmentRunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    assessment_run_id: str = Field(min_length=1)
    assessed_at: datetime
    integration_schema_version: str = Field(min_length=1)
    phase1_contract_version: str = Field(min_length=1)


class AssessmentLineage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_document_id: str = Field(pattern=r"^doc-[0-9a-f]{64}$")
    extraction_run_id: str = Field(min_length=1)
    review_id: str = Field(min_length=1)
    approval_event_id: str = Field(min_length=1)
    approved_at: datetime
    validated_process_id: str = Field(min_length=1)
    validated_process_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class AssessedPolicyReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_status: str = Field(min_length=1)
    decision_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class EvidenceTraceReference(BaseModel):
    """Reference into trusted Phase 3 evidence retained by the Phase 4 record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1)
    document_id: str = Field(pattern=r"^doc-[0-9a-f]{64}$")
    block_id: str = Field(min_length=1)
    block_start_offset: int = Field(ge=0)
    block_end_offset: int = Field(gt=0)
    source_locator: str = Field(min_length=1)


class ReviewedValueTrace(BaseModel):
    """Minimal link from an assessed input to its canonical reviewed assertion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    validated_process_field_path: str = Field(min_length=1)
    review_field_path: str = Field(min_length=1)
    assessment_field_path: str | None = Field(default=None, min_length=1)
    origin: InformationOrigin
    knowledge_state: KnowledgeState
    review_disposition: ReviewDisposition
    evidence: list[EvidenceTraceReference] = Field(default_factory=list)


class StepAssessmentTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str = Field(min_length=1)
    assessment_step_path: str = Field(min_length=1)
    recommendation_path: str = Field(min_length=1)
    gate_results_path: str = Field(min_length=1)
    validated_step_path: str = Field(min_length=1)
    review_step_path: str = Field(min_length=1)
    activity: ReviewedValueTrace
    criteria: list[ReviewedValueTrace]
    human_accountability: ReviewedValueTrace
    capability_signals: list[ReviewedValueTrace]


class IntegrationError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: IntegrationFailureCode
    message: str = Field(min_length=1)
    field_path: str | None = None
    step_id: str | None = None


class IntegratedAssessmentSuccess(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal[IntegratedAssessmentStatus.SUCCESS] = IntegratedAssessmentStatus.SUCCESS
    metadata: AssessmentRunMetadata
    lineage: AssessmentLineage
    policy: AssessedPolicyReference
    process_assessment: ProcessAssessment
    step_traceability: list[StepAssessmentTrace]

    @model_validator(mode="after")
    def validate_complete_step_traceability(self) -> "IntegratedAssessmentSuccess":
        assessed_ids = [item.step_id for item in self.process_assessment.step_assessments]
        traced_ids = [item.step_id for item in self.step_traceability]
        if traced_ids != assessed_ids:
            raise ValueError("Every assessed step requires ordered traceability")
        if self.process_assessment.policy_id != self.policy.policy_id:
            raise ValueError("Assessment and policy reference IDs must match")
        if self.process_assessment.policy_version != self.policy.policy_version:
            raise ValueError("Assessment and policy reference versions must match")
        if self.process_assessment.policy_status != self.policy.policy_status:
            raise ValueError("Assessment and policy reference statuses must match")
        return self


class IntegratedAssessmentFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal[IntegratedAssessmentStatus.FAILED] = IntegratedAssessmentStatus.FAILED
    metadata: AssessmentRunMetadata
    lineage: AssessmentLineage | None = None
    policy: AssessedPolicyReference | None = None
    errors: list[IntegrationError] = Field(min_length=1)


IntegratedAssessmentResult = Annotated[
    IntegratedAssessmentSuccess | IntegratedAssessmentFailure,
    Field(discriminator="status"),
]

"""Phase 5 successor orchestration and traceability contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_adoption_engine.models.enums import CriterionName
from ai_adoption_engine.models.four_gate_assessment import (
    CapabilitySignalName,
    FourGateProcessAssessment,
)
from ai_adoption_engine.models.integrated_assessment import (
    AssessmentLineage,
    IntegratedAssessmentStatus,
    IntegrationError,
    ReviewedValueTrace,
)


class FourGateAssessmentRunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    assessment_run_id: str = Field(min_length=1)
    assessed_at: datetime
    integration_schema_version: Literal["phase5-v0.2"] = "phase5-v0.2"
    phase1_contract_version: Literal["phase1-v0.4"] = "phase1-v0.4"


class FourGateAssessedPolicyReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: Literal["decision_policy.v0.3"] = "decision_policy.v0.3"
    policy_version: Literal["0.3.0"] = "0.3.0"
    policy_status: str = Field(min_length=1)
    decision_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class FourGateStepAssessmentTrace(BaseModel):
    """Ordered links from one approved step to every successor decision field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str = Field(min_length=1)
    assessment_step_path: str = Field(min_length=1)
    decision_status_path: str = Field(min_length=1)
    change_disposition_path: str = Field(min_length=1)
    readiness_disposition_path: str = Field(min_length=1)
    selected_intervention_family_path: str = Field(min_length=1)
    autonomy_ceiling_path: str = Field(min_length=1)
    outcome_code_path: str = Field(min_length=1)
    gate_results_path: str = Field(min_length=1)
    validated_step_path: str = Field(min_length=1)
    review_step_path: str = Field(min_length=1)
    activity: ReviewedValueTrace
    criteria: list[ReviewedValueTrace]
    human_accountability: ReviewedValueTrace
    capability_signals: list[ReviewedValueTrace]

    @model_validator(mode="after")
    def validate_complete_paths(self) -> Self:
        assessed_base = (
            f"process_assessment.step_assessments[step_id={self.step_id}]"
        )
        process_base = f"business_process.steps[step_id={self.step_id}]"
        review_base = f"review.steps[candidate_step_id={self.step_id}]"
        expected_scalar_paths = {
            "assessment_step_path": assessed_base,
            "decision_status_path": f"{assessed_base}.decision_status",
            "change_disposition_path": f"{assessed_base}.change_disposition",
            "readiness_disposition_path": f"{assessed_base}.readiness_disposition",
            "selected_intervention_family_path": (
                f"{assessed_base}.selected_intervention_family"
            ),
            "autonomy_ceiling_path": f"{assessed_base}.autonomy_ceiling",
            "outcome_code_path": f"{assessed_base}.outcome_code",
            "gate_results_path": f"{assessed_base}.gate_results",
            "validated_step_path": process_base,
            "review_step_path": review_base,
        }
        for field_name, expected in expected_scalar_paths.items():
            if getattr(self, field_name) != expected:
                raise ValueError(f"Invalid successor trace path: {field_name}")

        if (
            self.activity.validated_process_field_path != f"{process_base}.activity"
            or self.activity.review_field_path != f"{review_base}.activity"
            or self.activity.assessment_field_path != f"{assessed_base}.activity"
        ):
            raise ValueError("Invalid successor activity trace")

        expected_criteria = list(CriterionName)
        if len(self.criteria) != len(expected_criteria):
            raise ValueError("Successor criteria trace must contain every criterion")
        for trace, criterion in zip(self.criteria, expected_criteria, strict=True):
            if (
                trace.validated_process_field_path
                != f"{process_base}.characteristics.{criterion.value}"
                or trace.review_field_path
                != f"{review_base}.criteria[name={criterion.value}]"
                or trace.assessment_field_path
                != f"{assessed_base}.criteria[criterion={criterion.value}]"
            ):
                raise ValueError("Successor criteria trace is incomplete or unordered")

        expected_accountability_paths = (
            f"{process_base}.characteristics.human_accountability_required",
            f"{review_base}.human_accountability_required",
            f"{assessed_base}.human_accountability",
        )
        actual_accountability_paths = (
            self.human_accountability.validated_process_field_path,
            self.human_accountability.review_field_path,
            self.human_accountability.assessment_field_path,
        )
        if actual_accountability_paths != expected_accountability_paths:
            raise ValueError("Invalid successor human-accountability trace")

        expected_signals = list(CapabilitySignalName)
        if len(self.capability_signals) != len(expected_signals):
            raise ValueError("Successor capability trace must contain every signal")
        for trace, signal in zip(
            self.capability_signals,
            expected_signals,
            strict=True,
        ):
            if (
                trace.validated_process_field_path
                != f"{process_base}.characteristics.capability_signals.{signal.value}"
                or trace.review_field_path
                != f"{review_base}.capability_signals[name={signal.value}]"
                or trace.assessment_field_path
                != f"{assessed_base}.capability_signals[signal={signal.value}]"
            ):
                raise ValueError(
                    "Successor capability trace is incomplete or unordered"
                )
        return self


class FourGateIntegratedAssessmentSuccess(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal[IntegratedAssessmentStatus.SUCCESS] = (
        IntegratedAssessmentStatus.SUCCESS
    )
    metadata: FourGateAssessmentRunMetadata
    lineage: AssessmentLineage
    policy: FourGateAssessedPolicyReference
    process_assessment: FourGateProcessAssessment
    step_traceability: list[FourGateStepAssessmentTrace]

    @model_validator(mode="after")
    def validate_complete_contract(self) -> Self:
        assessment = self.process_assessment
        assessed_ids = [item.step_id for item in assessment.step_assessments]
        traced_ids = [item.step_id for item in self.step_traceability]
        if traced_ids != assessed_ids or len(assessed_ids) != len(set(assessed_ids)):
            raise ValueError(
                "Every assessed step requires ordered successor traceability"
            )
        if self.lineage.validated_process_id != assessment.process_id:
            raise ValueError("Assessment and approved-process lineage IDs must match")
        if (
            self.metadata.phase1_contract_version
            != assessment.decision_contract_version
        ):
            raise ValueError("Phase 5 and embedded decision contracts must match")
        if (
            assessment.framework_id != "four-gate-framework.v0.1"
            or assessment.framework_version != "0.1"
        ):
            raise ValueError("Unexpected successor framework identity")
        if (
            assessment.policy_id != self.policy.policy_id
            or assessment.policy_version != self.policy.policy_version
            or assessment.policy_status != self.policy.policy_status
        ):
            raise ValueError("Assessment and successor policy reference must match")
        return self


class FourGateIntegratedAssessmentFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal[IntegratedAssessmentStatus.FAILED] = (
        IntegratedAssessmentStatus.FAILED
    )
    metadata: FourGateAssessmentRunMetadata
    lineage: AssessmentLineage | None = None
    policy: FourGateAssessedPolicyReference | None = None
    errors: list[IntegrationError] = Field(min_length=1)


FourGateIntegratedAssessmentResult = Annotated[
    FourGateIntegratedAssessmentSuccess | FourGateIntegratedAssessmentFailure,
    Field(discriminator="status"),
]

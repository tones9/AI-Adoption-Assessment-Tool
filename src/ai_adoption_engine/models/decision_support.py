"""Deterministic Phase 6 AI-adoption decision-support package contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_adoption_engine.models.assessment import GateResult, PriorityScore
from ai_adoption_engine.models.enums import (
    Capability,
    CriterionName,
    KnowledgeState,
    PriorityStatus,
    RecommendationMode,
)
from ai_adoption_engine.models.integrated_assessment import (
    AssessmentLineage,
    AssessedPolicyReference,
    EvidenceTraceReference,
    StepAssessmentTrace,
)
from ai_adoption_engine.models.review import InformationOrigin


class PackageCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    COMPLETE_WITH_INFORMATION_GAPS = "COMPLETE_WITH_INFORMATION_GAPS"


class PlanningOrigin(StrEnum):
    ASSESSMENT_FINDING = "ASSESSMENT_FINDING"
    DERIVED_PLANNING_GUIDANCE = "DERIVED_PLANNING_GUIDANCE"


class InformationGapKind(StrEnum):
    UNKNOWN_INPUT = "UNKNOWN_INPUT"
    INCOMPLETE_PRIORITY = "INCOMPLETE_PRIORITY"
    INVESTIGATION_REQUIRED = "INVESTIGATION_REQUIRED"
    INFERRED_REQUIRES_CONFIRMATION = "INFERRED_REQUIRES_CONFIRMATION"


class HumanRoleType(StrEnum):
    PRIMARY_OPERATOR = "primary-operator"
    REVIEWER = "reviewer"
    EXCEPTION_HANDLER = "exception-handler"
    APPROVER = "approver"
    DECISION_OWNER = "decision-owner"
    OVERSIGHT_ROLE = "oversight-role"
    PROCESS_OWNER = "process-owner"
    SUBJECT_MATTER_VALIDATOR = "subject-matter-validator"


class RoleConfirmationStatus(StrEnum):
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"


class FutureStateStatus(StrEnum):
    PROPOSED_NOT_DEPLOYED = "PROPOSED / NOT DEPLOYED"


class InterventionType(StrEnum):
    AI_ENABLED_EXECUTION = "AI_ENABLED_EXECUTION"
    AI_ASSISTED_HUMAN_EXECUTION = "AI_ASSISTED_HUMAN_EXECUTION"
    CURRENT_STEP_WITH_INVESTIGATION_MARKER = (
        "CURRENT_STEP_WITH_INVESTIGATION_MARKER"
    )
    CURRENT_OR_CONVENTIONAL_EXECUTION = "CURRENT_OR_CONVENTIONAL_EXECUTION"


class CapabilityUseStatus(StrEnum):
    PROPOSED = "PROPOSED"
    UNDER_INVESTIGATION = "UNDER_INVESTIGATION"
    NOT_APPLIED = "NOT_APPLIED"


class RoadmapStatus(StrEnum):
    QUALIFYING_OPPORTUNITY = "QUALIFYING_OPPORTUNITY"
    INVESTIGATION_ONLY = "INVESTIGATION_ONLY"
    AI_DEPLOYMENT_NOT_APPLICABLE = "AI_DEPLOYMENT_NOT_APPLICABLE"


class RoadmapStageType(StrEnum):
    OPPORTUNITY_VALIDATION = "OPPORTUNITY_VALIDATION"
    INFORMATION_GATHERING = "INFORMATION_GATHERING"
    DATA_READINESS_VALIDATION = "DATA_READINESS_VALIDATION"
    FEASIBILITY_VALIDATION = "FEASIBILITY_VALIDATION"
    PROOF_OF_CONCEPT = "PROOF_OF_CONCEPT"
    GO_REVISE_STOP_DECISION = "GO_REVISE_STOP_DECISION"
    CONTROLLED_PILOT = "CONTROLLED_PILOT"
    HUMAN_CONTROL_EVALUATION = "HUMAN_CONTROL_EVALUATION"
    GOVERNANCE_SECURITY_REVIEW = "GOVERNANCE_SECURITY_REVIEW"
    DEPLOYMENT_DECISION = "DEPLOYMENT_DECISION"
    INTEGRATION_PLANNING = "INTEGRATION_PLANNING"
    PRODUCTION_MONITORING = "PRODUCTION_MONITORING"


class GovernanceCategory(StrEnum):
    CONSEQUENCE_OF_ERROR = "CONSEQUENCE_OF_ERROR"
    HUMAN_JUDGEMENT = "HUMAN_JUDGEMENT"
    ACCOUNTABILITY = "ACCOUNTABILITY"
    DATA_READINESS = "DATA_READINESS"
    HUMAN_OVERSIGHT = "HUMAN_OVERSIGHT"
    PRIVACY_SECURITY = "PRIVACY_SECURITY"
    LEGAL_ORGANISATIONAL = "LEGAL_ORGANISATIONAL"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"


class ReportSectionId(StrEnum):
    EXECUTIVE_SUMMARY = "executive-summary"
    PROCESS_ASSESSED = "process-assessed"
    OPPORTUNITY_PORTFOLIO = "ai-opportunity-portfolio"
    HIGHEST_PRIORITY = "highest-priority-opportunities"
    REQUIRES_INVESTIGATION = "requires-further-investigation"
    NOT_RECOMMENDED = "ai-use-not-recommended"
    FUTURE_STATE = "proposed-future-state-workflow"
    HUMAN_ROLES = "human-roles-and-controls"
    RISKS_GOVERNANCE = "risks-and-governance"
    ADOPTION_ROADMAP = "adoption-roadmap"
    MISSING_INFORMATION = "missing-information"
    METHODOLOGY = "methodology-and-policy-disclosure"
    EVIDENCE_APPENDIX = "evidence-and-traceability-appendix"


class PlanningBasis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    origin: PlanningOrigin
    step_id: str = Field(min_length=1)
    assessment_paths: list[str] = Field(default_factory=list)
    review_paths: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    reviewed_origins: list[InformationOrigin] = Field(default_factory=list)


class InformationGap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gap_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    kind: InformationGapKind
    field_name: str = Field(min_length=1)
    knowledge_state: KnowledgeState | None = None
    message: str = Field(min_length=1)
    material_to_recommendation: bool = False
    material_to_priority: bool = False
    material_to_planning: bool = False
    basis: PlanningBasis


class HumanRoleGuidance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role_type: HumanRoleType
    confirmation_status: RoleConfirmationStatus = (
        RoleConfirmationStatus.NEEDS_CONFIRMATION
    )
    responsibility: str = Field(min_length=1)
    basis: PlanningBasis


class OpportunityPortfolioItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    step_id: str = Field(min_length=1)
    current_activity: str = Field(min_length=1)
    recommendation_mode: RecommendationMode
    capabilities: list[Capability]
    priority_status: PriorityStatus
    priority: PriorityScore | None = None
    priority_missing_criteria: list[CriterionName] = Field(default_factory=list)
    gate_results: list[GateResult]
    missing_information: list[InformationGap] = Field(default_factory=list)
    recommended_human_roles: list[HumanRoleGuidance]
    rationale: list[str]
    source_traceability: StepAssessmentTrace


class OpportunityPortfolio(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[OpportunityPortfolioItem]

    @model_validator(mode="after")
    def require_unique_ordered_steps(self) -> "OpportunityPortfolio":
        sequences = [item.sequence for item in self.items]
        if sequences != list(range(1, len(self.items) + 1)):
            raise ValueError("Portfolio items must retain contiguous process order")
        ids = [item.step_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Every assessed step must appear exactly once")
        return self


class FutureStateStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    source_step_id: str = Field(min_length=1)
    current_activity: str = Field(min_length=1)
    proposed_activity: str = Field(min_length=1)
    recommendation_mode: RecommendationMode
    intervention_type: InterventionType
    capabilities: list[Capability]
    capability_use_status: CapabilityUseStatus
    human_roles: list[HumanRoleGuidance]
    controls_and_constraints: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)
    basis: PlanningBasis


class ProposedFutureStateWorkflow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: FutureStateStatus = FutureStateStatus.PROPOSED_NOT_DEPLOYED
    current_state_process_id: str = Field(min_length=1)
    current_state_process_name: str = Field(min_length=1)
    steps: list[FutureStateStep]


class RoadmapStage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    stage_type: RoadmapStageType
    objective: str = Field(min_length=1)
    decision_point: bool = False
    possible_outcomes: list[str] = Field(default_factory=list)
    basis: PlanningBasis

    @model_validator(mode="after")
    def validate_decision_outcomes(self) -> "RoadmapStage":
        if self.decision_point and not self.possible_outcomes:
            raise ValueError("Decision points require possible outcomes")
        if not self.decision_point and self.possible_outcomes:
            raise ValueError("Only decision points may define possible outcomes")
        return self


class OpportunityRoadmap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str = Field(min_length=1)
    recommendation_mode: RecommendationMode
    status: RoadmapStatus
    stages: list[RoadmapStage] = Field(default_factory=list)
    rationale: str = Field(min_length=1)


class AdoptionRoadmap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    opportunities: list[OpportunityRoadmap]


class GovernanceConsideration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    consideration_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    category: GovernanceCategory
    statement: str = Field(min_length=1)
    requires_review: bool
    basis: PlanningBasis


class RiskGovernanceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    considerations: list[GovernanceConsideration]
    legal_conclusions_provided: Literal[False] = False
    security_approval_claimed: Literal[False] = False
    deployment_readiness_claimed: Literal[False] = False


class MethodologyDisclosure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_is_provisional: Literal[True] = True
    academically_validated: Literal[False] = False
    decision_support_only: Literal[True] = True
    proposed_future_state_deployed: Literal[False] = False
    disclosure_statements: list[str] = Field(min_length=1)


class ReportStatement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1)
    origin: PlanningOrigin
    step_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    reviewed_origins: list[InformationOrigin] = Field(default_factory=list)


class ReportSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    section_id: ReportSectionId
    title: str = Field(min_length=1)
    statements: list[ReportStatement]
    item_references: list[str] = Field(default_factory=list)


class DecisionReportContent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sections: list[ReportSection]

    @model_validator(mode="after")
    def require_all_sections_in_order(self) -> "DecisionReportContent":
        if [item.section_id for item in self.sections] != list(ReportSectionId):
            raise ValueError("Report content must contain all 13 sections in order")
        return self


class CurrentStateReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    process_id: str = Field(min_length=1)
    process_name: str = Field(min_length=1)
    review_id: str = Field(min_length=1)
    approval_event_id: str = Field(min_length=1)
    source_document_id: str = Field(min_length=1)
    ordered_step_ids: list[str]


class DecisionPackageSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    integrated_assessment_run_id: str = Field(min_length=1)
    lineage: AssessmentLineage
    policy: AssessedPolicyReference


class DecisionSupportPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    package_id: str = Field(pattern=r"^decision-package-[0-9a-f]{64}$")
    package_schema_version: str = Field(min_length=1)
    completeness: PackageCompleteness
    source: DecisionPackageSource
    current_state: CurrentStateReference
    portfolio: OpportunityPortfolio
    future_state: ProposedFutureStateWorkflow
    roadmap: AdoptionRoadmap
    governance: RiskGovernanceSummary
    missing_information: list[InformationGap]
    roi_statement: Literal[
        "ROI / quantified benefit unavailable with current evidence."
    ]
    methodology: MethodologyDisclosure
    evidence_appendix: list[EvidenceTraceReference]
    report_content: DecisionReportContent


class DecisionPackageFailureCode(StrEnum):
    INTEGRATED_SUCCESS_REQUIRED = "integrated-success-required"
    INVALID_INTEGRATED_ASSESSMENT = "invalid-integrated-assessment"
    INCOMPLETE_STEP_COVERAGE = "incomplete-step-coverage"
    INVALID_TRACEABILITY = "invalid-traceability"
    UNSUPPORTED_ASSESSMENT_CONTRACT = "unsupported-assessment-contract"
    FUTURE_STATE_RULE_CONFLICT = "future-state-rule-conflict"
    PACKAGE_GENERATION_FAILED = "package-generation-failed"


class DecisionPackageError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: DecisionPackageFailureCode
    message: str = Field(min_length=1)
    field_path: str | None = None
    step_id: str | None = None


class DecisionPackageSuccess(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["success"] = "success"
    package: DecisionSupportPackage


class DecisionPackageFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["failed"] = "failed"
    source_assessment_run_id: str | None = None
    errors: list[DecisionPackageError] = Field(min_length=1)


DecisionPackageGenerationResult = Annotated[
    DecisionPackageSuccess | DecisionPackageFailure,
    Field(discriminator="status"),
]

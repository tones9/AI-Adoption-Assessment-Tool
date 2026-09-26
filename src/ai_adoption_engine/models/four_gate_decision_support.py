"""Strict Phase 6 package contracts for the four-gate successor."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_adoption_engine.models.enums import Capability, CriterionName
from ai_adoption_engine.models.evidence import EvidenceReference
from ai_adoption_engine.models.four_gate_assessment import (
    AutonomyCeiling,
    BlockingEvidenceGap,
    ChangeDisposition,
    DecisionStatus,
    FourGateAccountabilityAssessment,
    FourGateCapabilitySignalAssessment,
    FourGateCriterionAssessment,
    FourGateName,
    FourGatePriorityScore,
    FourGatePriorityStatus,
    FourGateResult,
    FourGateStepAssessment,
    OutcomeCode,
    ReadinessDisposition,
    SelectedInterventionFamily,
)
from ai_adoption_engine.models.four_gate_integrated_assessment import (
    FourGateAssessedPolicyReference,
    FourGateStepAssessmentTrace,
)
from ai_adoption_engine.models.integrated_assessment import (
    AssessmentLineage,
    EvidenceTraceReference,
)


class FourGatePackageCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    COMPLETE_WITH_INFORMATION_GAPS = "COMPLETE_WITH_INFORMATION_GAPS"


class FourGateInformationGapKind(StrEnum):
    ACTIVE_DECISION_BLOCKER = "ACTIVE_DECISION_BLOCKER"
    CONTEXTUAL_UNKNOWN = "CONTEXTUAL_UNKNOWN"
    PRIORITY_ONLY = "PRIORITY_ONLY"


class FourGateCapabilityUseStatus(StrEnum):
    PROPOSED_NOT_DEPLOYED = "PROPOSED_NOT_DEPLOYED"
    REJECTED_AT_SAFETY_GATE = "REJECTED_AT_SAFETY_GATE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FourGateReportOrigin(StrEnum):
    ASSESSMENT_FINDING = "ASSESSMENT_FINDING"
    DERIVED_REPORT_GUIDANCE = "DERIVED_REPORT_GUIDANCE"
    DISCLOSURE = "DISCLOSURE"


class FourGateReportSectionId(StrEnum):
    EXECUTIVE_SUMMARY = "executive-summary"
    PROCESS_ASSESSED = "process-assessed"
    ACTIVITY_DECISION_PORTFOLIO = "activity-decision-portfolio"
    HIGHEST_PRIORITY_AI_OPPORTUNITIES = "highest-priority-ai-opportunities"
    DISCOVERY_REQUIRED = "discovery-required"
    OTHER_INTERVENTIONS_AND_NO_CHANGE = "other-interventions-and-no-change"
    PROPOSED_FUTURE_STATE_WORKFLOW = "proposed-future-state-workflow"
    HUMAN_ROLES_AND_CONTROLS = "human-roles-and-controls"
    RISKS_AND_GOVERNANCE = "risks-and-governance"
    ADOPTION_ROADMAP = "adoption-roadmap"
    MISSING_INFORMATION = "missing-information"
    METHODOLOGY_AND_POLICY_DISCLOSURE = "methodology-and-policy-disclosure"
    EVIDENCE_AND_TRACEABILITY_APPENDIX = "evidence-and-traceability-appendix"


class FourGatePackageSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    integrated_assessment_run_id: str = Field(min_length=1)
    integration_schema_version: Literal["phase5-v0.2"] = "phase5-v0.2"
    phase1_contract_version: Literal["phase1-v0.4"] = "phase1-v0.4"
    lineage: AssessmentLineage
    policy: FourGateAssessedPolicyReference


class FourGateCurrentStateReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    process_id: str = Field(min_length=1)
    process_name: str = Field(min_length=1)
    framework_id: Literal["four-gate-framework.v0.1"] = (
        "four-gate-framework.v0.1"
    )
    framework_version: Literal["0.1"] = "0.1"
    review_id: str = Field(min_length=1)
    approval_event_id: str = Field(min_length=1)
    source_document_id: str = Field(min_length=1)
    ordered_step_ids: list[str]


class FourGateInformationGap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gap_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    kind: FourGateInformationGapKind
    field_name: str = Field(min_length=1)
    message: str = Field(min_length=1)
    gate: FourGateName | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    assessment_paths: list[str] = Field(default_factory=list)
    review_paths: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_gap_classification(self) -> Self:
        if self.kind is FourGateInformationGapKind.ACTIVE_DECISION_BLOCKER:
            if self.gate is None or not self.assessment_paths:
                raise ValueError("Active blockers require a gate and assessment path")
        elif self.gate is not None:
            raise ValueError("Only active decision blockers identify a gate")
        return self


class FourGateDecisionPortfolioItem(BaseModel):
    """Lossless Phase 5 finding plus report-domain classification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    step_id: str = Field(min_length=1)
    activity: str = Field(min_length=1)
    decision_status: DecisionStatus
    change_disposition: ChangeDisposition
    readiness_disposition: ReadinessDisposition
    selected_intervention_family: SelectedInterventionFamily
    autonomy_ceiling: AutonomyCeiling
    outcome_code: OutcomeCode
    gate_results: list[FourGateResult] = Field(min_length=4, max_length=4)
    blocking_gaps: list[BlockingEvidenceGap] = Field(default_factory=list)
    capabilities: list[Capability] = Field(default_factory=list)
    capability_signals: list[FourGateCapabilitySignalAssessment]
    criteria: list[FourGateCriterionAssessment]
    human_accountability: FourGateAccountabilityAssessment
    priority_status: FourGatePriorityStatus
    priority: FourGatePriorityScore | None = None
    priority_missing_criteria: list[CriterionName] = Field(default_factory=list)
    priority_eligible: bool
    rationale: list[str]
    material_evidence: list[EvidenceReference]
    information_gaps: list[FourGateInformationGap]
    source_traceability: FourGateStepAssessmentTrace
    final_recommendation: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_item_contract(self) -> Self:
        FourGateStepAssessment(
            step_id=self.step_id,
            activity=self.activity,
            decision_status=self.decision_status,
            change_disposition=self.change_disposition,
            readiness_disposition=self.readiness_disposition,
            selected_intervention_family=self.selected_intervention_family,
            autonomy_ceiling=self.autonomy_ceiling,
            outcome_code=self.outcome_code,
            gate_results=self.gate_results,
            blocking_gaps=self.blocking_gaps,
            capabilities=self.capabilities,
            capability_signals=self.capability_signals,
            criteria=self.criteria,
            human_accountability=self.human_accountability,
            priority_status=self.priority_status,
            priority=self.priority,
            priority_missing_criteria=self.priority_missing_criteria,
            reasoning=self.rationale,
            evidence=self.material_evidence,
        )
        if [result.gate for result in self.gate_results] != list(FourGateName):
            raise ValueError("Portfolio items require exactly four ordered gates")
        if self.source_traceability.step_id != self.step_id:
            raise ValueError("Portfolio traceability must match its step")
        eligible = (
            self.decision_status is DecisionStatus.COMPLETE
            and self.outcome_code
            in {OutcomeCode.AI_AUTOMATION, OutcomeCode.AI_ASSISTED_WORK}
        )
        if self.priority_eligible is not eligible:
            raise ValueError("Priority eligibility must follow the final outcome")
        active = [
            gap
            for gap in self.information_gaps
            if gap.kind is FourGateInformationGapKind.ACTIVE_DECISION_BLOCKER
        ]
        if bool(active) != (
            self.decision_status is DecisionStatus.DISCOVERY_REQUIRED
        ):
            raise ValueError("Active blockers exist exactly for discovery decisions")
        if {gap.gap_id for gap in active} != {
            f"{self.step_id}:blocker:{index}"
            for index in range(1, len(self.blocking_gaps) + 1)
        }:
            raise ValueError("Active package blockers must preserve assessment gaps")
        for source, packaged in zip(self.blocking_gaps, active, strict=True):
            if (
                packaged.field_name != source.field_name
                or packaged.gate is not source.gate
                or packaged.message != source.blocking_question
                or packaged.evidence_ids != source.evidence_ids
            ):
                raise ValueError("Packaged blockers must match assessment blockers")
        return self


class FourGateDecisionPortfolio(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[FourGateDecisionPortfolioItem]

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if [item.sequence for item in self.items] != list(
            range(1, len(self.items) + 1)
        ):
            raise ValueError("Portfolio items must retain contiguous process order")
        step_ids = [item.step_id for item in self.items]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Every assessed step must appear exactly once")
        return self


class FourGateFutureStateStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    step_id: str = Field(min_length=1)
    current_activity: str = Field(min_length=1)
    proposed_activity: str = Field(min_length=1)
    final_outcome: OutcomeCode
    capability_use_status: FourGateCapabilityUseStatus
    capabilities: list[Capability]
    controls_and_constraints: list[str]
    status: Literal["PROPOSED / NOT DEPLOYED"] = "PROPOSED / NOT DEPLOYED"


class FourGateProposedFutureStateWorkflow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    process_id: str = Field(min_length=1)
    process_name: str = Field(min_length=1)
    status: Literal["PROPOSED / NOT DEPLOYED"] = "PROPOSED / NOT DEPLOYED"
    steps: list[FourGateFutureStateStep]


class FourGateRoadmapItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    step_id: str = Field(min_length=1)
    final_outcome: OutcomeCode
    priority_status: FourGatePriorityStatus
    ai_priority_eligible: bool
    guidance: str = Field(min_length=1)
    status: Literal["DECISION SUPPORT ONLY"] = "DECISION SUPPORT ONLY"


class FourGateGovernanceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str = Field(min_length=1)
    final_outcome: OutcomeCode
    statement: str = Field(min_length=1)
    evaluated_gate: FourGateName | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class FourGateMethodologyDisclosure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    framework_id: Literal["four-gate-framework.v0.1"]
    framework_version: Literal["0.1"]
    decision_contract_version: Literal["phase1-v0.4"]
    policy_id: Literal["decision_policy.v0.3"]
    policy_version: Literal["0.3.0"]
    policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_is_provisional: Literal[True] = True
    academically_validated: Literal[False] = False
    decision_support_only: Literal[True] = True
    proposed_future_state_deployed: Literal[False] = False
    disclosure_statements: list[str] = Field(min_length=1)


class FourGateReportStatement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1)
    origin: FourGateReportOrigin
    step_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    final_outcome: OutcomeCode | None = None
    selected_intervention_family: SelectedInterventionFamily | None = None
    autonomy_ceiling: AutonomyCeiling | None = None


class FourGateReportSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    section_id: FourGateReportSectionId
    title: str = Field(min_length=1)
    statements: list[FourGateReportStatement]
    item_references: list[str] = Field(default_factory=list)


class FourGateDecisionReportContent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sections: list[FourGateReportSection]

    @model_validator(mode="after")
    def require_all_sections_in_order(self) -> Self:
        if [section.section_id for section in self.sections] != list(
            FourGateReportSectionId
        ):
            raise ValueError("Successor report requires all 13 sections in order")
        return self


class FourGateDecisionSupportPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    package_id: str = Field(pattern=r"^four-gate-decision-package-[0-9a-f]{64}$")
    package_schema_version: Literal["phase6-v0.2"] = "phase6-v0.2"
    completeness: FourGatePackageCompleteness
    source: FourGatePackageSource
    current_state: FourGateCurrentStateReference
    portfolio: FourGateDecisionPortfolio
    future_state: FourGateProposedFutureStateWorkflow
    roadmap: list[FourGateRoadmapItem]
    governance: list[FourGateGovernanceItem]
    missing_information: list[FourGateInformationGap]
    methodology: FourGateMethodologyDisclosure
    evidence_appendix: list[EvidenceTraceReference]
    report_content: FourGateDecisionReportContent

    @model_validator(mode="after")
    def validate_package_links(self) -> Self:
        item_ids = [item.step_id for item in self.portfolio.items]
        if item_ids != self.current_state.ordered_step_ids:
            raise ValueError("Package step coverage must match current-state order")
        if [item.step_id for item in self.future_state.steps] != item_ids:
            raise ValueError("Future-state coverage must match the portfolio")
        if [item.step_id for item in self.roadmap] != item_ids:
            raise ValueError("Roadmap coverage must match the portfolio")
        if self.current_state.process_id != self.future_state.process_id:
            raise ValueError("Current and proposed process identities must match")
        if self.source.lineage.validated_process_id != self.current_state.process_id:
            raise ValueError("Source lineage must match the packaged process")
        if self.methodology.policy_fingerprint != (
            self.source.policy.decision_policy_fingerprint
        ):
            raise ValueError("Methodology and source policy fingerprints must match")
        for finding, future, roadmap in zip(
            self.portfolio.items,
            self.future_state.steps,
            self.roadmap,
            strict=True,
        ):
            safety_veto = (
                finding.selected_intervention_family
                is SelectedInterventionFamily.AI
                and finding.autonomy_ceiling is AutonomyCeiling.AI_NOT_PERMITTED
            )
            if finding.outcome_code in {
                OutcomeCode.AI_AUTOMATION,
                OutcomeCode.AI_ASSISTED_WORK,
            }:
                expected_capability_status = (
                    FourGateCapabilityUseStatus.PROPOSED_NOT_DEPLOYED
                )
            elif safety_veto:
                expected_capability_status = (
                    FourGateCapabilityUseStatus.REJECTED_AT_SAFETY_GATE
                )
            else:
                expected_capability_status = (
                    FourGateCapabilityUseStatus.NOT_APPLICABLE
                )
            if (
                future.final_outcome is not finding.outcome_code
                or future.capabilities != finding.capabilities
                or future.capability_use_status is not expected_capability_status
                or roadmap.final_outcome is not finding.outcome_code
                or roadmap.priority_status is not finding.priority_status
                or roadmap.ai_priority_eligible is not finding.priority_eligible
            ):
                raise ValueError("Planning projections must preserve source decisions")
        governance_by_step = {item.step_id: item for item in self.governance}
        if len(self.governance) != len(item_ids) or set(governance_by_step) != set(
            item_ids
        ) or any(
            governance_by_step[item.step_id].final_outcome is not item.outcome_code
            for item in self.portfolio.items
        ):
            raise ValueError("Governance projections must preserve final outcomes")
        evidence_ids = [item.evidence_id for item in self.evidence_appendix]
        if evidence_ids != sorted(set(evidence_ids)):
            raise ValueError("Evidence appendix must be ordered and deduplicated")
        traced_references = {}
        for item in self.portfolio.items:
            trace = item.source_traceability
            for value in [
                trace.activity,
                *trace.criteria,
                trace.human_accountability,
                *trace.capability_signals,
            ]:
                for reference in value.evidence:
                    traced_references[reference.evidence_id] = reference
        if self.evidence_appendix != [
            traced_references[key] for key in sorted(traced_references)
        ]:
            raise ValueError("Evidence appendix must preserve complete reviewed lineage")
        flattened_gaps = [
            gap for item in self.portfolio.items for gap in item.information_gaps
        ]
        if self.missing_information != flattened_gaps:
            raise ValueError("Package gaps must retain ordered portfolio gaps")
        expected_completeness = (
            FourGatePackageCompleteness.COMPLETE_WITH_INFORMATION_GAPS
            if flattened_gaps
            else FourGatePackageCompleteness.COMPLETE
        )
        if self.completeness is not expected_completeness:
            raise ValueError("Package completeness must reflect recorded gaps")
        outcome_by_step = {
            item.step_id: item.outcome_code for item in self.portfolio.items
        }
        candidate_by_step = {
            item.step_id: item.selected_intervention_family
            for item in self.portfolio.items
        }
        autonomy_by_step = {
            item.step_id: item.autonomy_ceiling for item in self.portfolio.items
        }
        for section in self.report_content.sections:
            if not set(section.item_references).issubset(outcome_by_step):
                raise ValueError("Report references an unknown activity")
            expected_references = list(
                dict.fromkeys(
                    step_id
                    for statement in section.statements
                    for step_id in statement.step_ids
                )
            )
            if section.item_references != expected_references:
                raise ValueError("Report item references must match its statements")
            for statement in section.statements:
                for step_id in statement.step_ids:
                    if step_id not in outcome_by_step:
                        raise ValueError("Report statement references an unknown activity")
                    if statement.final_outcome not in {
                        None,
                        outcome_by_step[step_id],
                    }:
                        raise ValueError("Report statement contradicts the final outcome")
                    if statement.selected_intervention_family not in {
                        None,
                        candidate_by_step[step_id],
                    }:
                        raise ValueError("Report statement contradicts the Gate 3 candidate")
                    if statement.autonomy_ceiling not in {
                        None,
                        autonomy_by_step[step_id],
                    }:
                        raise ValueError("Report statement contradicts the autonomy ceiling")
        return self


class FourGateDecisionPackageFailureCode(StrEnum):
    INTEGRATED_SUCCESS_REQUIRED = "integrated-success-required"
    INVALID_INTEGRATED_ASSESSMENT = "invalid-integrated-assessment"
    UNSUPPORTED_CONTRACT = "unsupported-contract"
    INCOMPLETE_STEP_COVERAGE = "incomplete-step-coverage"
    INVALID_TRACEABILITY = "invalid-traceability"
    INVALID_EVIDENCE_LINEAGE = "invalid-evidence-lineage"
    PACKAGE_GENERATION_FAILED = "package-generation-failed"


class FourGateDecisionPackageError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: FourGateDecisionPackageFailureCode
    message: str = Field(min_length=1)
    field_path: str | None = None
    step_id: str | None = None


class FourGateDecisionPackageSuccess(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["success"] = "success"
    package_schema_version: Literal["phase6-v0.2"] = "phase6-v0.2"
    package: FourGateDecisionSupportPackage


class FourGateDecisionPackageFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["failed"] = "failed"
    package_schema_version: Literal["phase6-v0.2"] = "phase6-v0.2"
    source_assessment_run_id: str | None = None
    errors: list[FourGateDecisionPackageError] = Field(min_length=1)


FourGateDecisionPackageResult = Annotated[
    FourGateDecisionPackageSuccess | FourGateDecisionPackageFailure,
    Field(discriminator="status"),
]

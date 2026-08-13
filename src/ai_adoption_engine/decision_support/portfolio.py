"""Canonical process-ordered opportunity portfolio generation."""

from __future__ import annotations

from ai_adoption_engine.models.assessment import StepAssessment
from ai_adoption_engine.models.enums import KnowledgeState, PriorityStatus, RecommendationMode
from ai_adoption_engine.models.integrated_assessment import StepAssessmentTrace
from ai_adoption_engine.models.review import InformationOrigin
from ai_adoption_engine.models.decision_support import (
    HumanRoleGuidance,
    HumanRoleType,
    InformationGap,
    InformationGapKind,
    OpportunityPortfolio,
    OpportunityPortfolioItem,
    PlanningBasis,
    PlanningOrigin,
)


def planning_basis(
    trace: StepAssessmentTrace,
    *,
    assessment_paths: list[str] | None = None,
    review_paths: list[str] | None = None,
    evidence_ids: list[str] | None = None,
) -> PlanningBasis:
    origins = {
        item.origin
        for item in [
            trace.activity,
            *trace.criteria,
            trace.human_accountability,
            *trace.capability_signals,
        ]
    }
    return PlanningBasis(
        origin=PlanningOrigin.DERIVED_PLANNING_GUIDANCE,
        step_id=trace.step_id,
        assessment_paths=assessment_paths
        or [trace.recommendation_path, trace.gate_results_path],
        review_paths=review_paths or [trace.review_step_path],
        evidence_ids=sorted(set(evidence_ids or [])),
        reviewed_origins=sorted(origins, key=lambda item: item.value),
    )


def _roles(
    assessment: StepAssessment, trace: StepAssessmentTrace
) -> list[HumanRoleGuidance]:
    role_specs: list[tuple[HumanRoleType, str]]
    if assessment.recommendation_mode is RecommendationMode.AUTOMATE:
        role_specs = [
            (
                HumanRoleType.EXCEPTION_HANDLER,
                "Handle exceptions, low-confidence cases, and process failures.",
            )
        ]
        if assessment.human_accountability.value is True:
            role_specs.append(
                (
                    HumanRoleType.OVERSIGHT_ROLE,
                    "Retain accountable oversight of the automated activity and controls.",
                )
            )
    elif assessment.recommendation_mode is RecommendationMode.AUGMENT:
        role_specs = [
            (
                HumanRoleType.PRIMARY_OPERATOR,
                "Perform the activity with AI assistance and retain material responsibility.",
            ),
            (
                HumanRoleType.REVIEWER,
                "Review AI-assisted output before consequential use.",
            ),
        ]
        if assessment.human_accountability.value is True:
            role_specs.append(
                (
                    HumanRoleType.DECISION_OWNER,
                    "Remain accountable for the final decision or external commitment.",
                )
            )
    elif assessment.recommendation_mode is RecommendationMode.INVESTIGATE_FURTHER:
        role_specs = [
            (
                HumanRoleType.PROCESS_OWNER,
                "Own evidence gathering and decide whether the opportunity should progress.",
            ),
            (
                HumanRoleType.SUBJECT_MATTER_VALIDATOR,
                "Validate missing process, data, judgement, value, and risk assumptions.",
            ),
        ]
    else:
        role_specs = [
            (
                HumanRoleType.PRIMARY_OPERATOR,
                "Continue the current human or conventional execution approach.",
            ),
            (
                HumanRoleType.DECISION_OWNER,
                "Own any future reassessment if process evidence materially changes.",
            ),
        ]
    basis = planning_basis(trace)
    return [
        HumanRoleGuidance(
            role_type=role_type,
            responsibility=responsibility,
            basis=basis,
        )
        for role_type, responsibility in role_specs
    ]


def _missing_information(
    assessment: StepAssessment, trace: StepAssessmentTrace
) -> list[InformationGap]:
    gaps: list[InformationGap] = []
    for criterion, value_trace in zip(
        assessment.criteria, trace.criteria, strict=True
    ):
        material_inference = (
            criterion.knowledge_state is KnowledgeState.INFERRED
            and (
                criterion.material_to_recommendation
                or criterion.material_to_priority
            )
        )
        if criterion.knowledge_state is not KnowledgeState.UNKNOWN and not material_inference:
            continue
        kind = (
            InformationGapKind.UNKNOWN_INPUT
            if criterion.knowledge_state is KnowledgeState.UNKNOWN
            else InformationGapKind.INFERRED_REQUIRES_CONFIRMATION
        )
        message = (
            f"{criterion.criterion.value} is unknown and remains visible."
            if kind is InformationGapKind.UNKNOWN_INPUT
            else (
                f"{criterion.criterion.value} is inferred and materially influences "
                "recommendation or priority guidance; confirmation is required."
            )
        )
        gaps.append(
            InformationGap(
                gap_id=f"{assessment.step_id}:criterion:{criterion.criterion.value}",
                step_id=assessment.step_id,
                kind=kind,
                field_name=criterion.criterion.value,
                knowledge_state=criterion.knowledge_state,
                message=message,
                material_to_recommendation=criterion.material_to_recommendation,
                material_to_priority=criterion.material_to_priority,
                basis=planning_basis(
                    trace,
                    assessment_paths=[
                        value_trace.assessment_field_path
                        or trace.assessment_step_path
                    ],
                    review_paths=[value_trace.review_field_path],
                    evidence_ids=[item.evidence_id for item in value_trace.evidence],
                ),
            )
        )
    accountability = assessment.human_accountability
    if accountability.knowledge_state is KnowledgeState.UNKNOWN:
        gaps.append(
            InformationGap(
                gap_id=f"{assessment.step_id}:accountability",
                step_id=assessment.step_id,
                kind=InformationGapKind.UNKNOWN_INPUT,
                field_name="human_accountability_required",
                knowledge_state=KnowledgeState.UNKNOWN,
                message="Human accountability requirements are unknown.",
                material_to_recommendation=accountability.material_to_recommendation,
                material_to_planning=(
                    assessment.recommendation_mode
                    is not RecommendationMode.DO_NOT_RECOMMEND
                ),
                basis=planning_basis(
                    trace,
                    assessment_paths=[
                        trace.human_accountability.assessment_field_path
                        or trace.assessment_step_path
                    ],
                    review_paths=[trace.human_accountability.review_field_path],
                ),
            )
        )
    for value_trace in trace.capability_signals:
        if value_trace.knowledge_state is KnowledgeState.UNKNOWN:
            field = value_trace.review_field_path.split("name=", 1)[-1].rstrip("]")
            gaps.append(
                InformationGap(
                    gap_id=f"{assessment.step_id}:capability:{field}",
                    step_id=assessment.step_id,
                    kind=InformationGapKind.UNKNOWN_INPUT,
                    field_name=field,
                    knowledge_state=KnowledgeState.UNKNOWN,
                    message=f"Capability signal {field} is unknown.",
                    material_to_planning=(
                        assessment.recommendation_mode
                        is RecommendationMode.INVESTIGATE_FURTHER
                    ),
                    basis=planning_basis(
                        trace,
                        review_paths=[value_trace.review_field_path],
                    ),
                )
            )
    if assessment.priority_status is PriorityStatus.INCOMPLETE:
        gaps.append(
            InformationGap(
                gap_id=f"{assessment.step_id}:priority",
                step_id=assessment.step_id,
                kind=InformationGapKind.INCOMPLETE_PRIORITY,
                field_name="priority",
                message=(
                    "Priority is incomplete because these criteria are insufficient: "
                    + ", ".join(
                        item.value for item in assessment.priority_missing_criteria
                    )
                    + "."
                ),
                material_to_priority=True,
                basis=planning_basis(
                    trace,
                    assessment_paths=[
                        f"{trace.assessment_step_path}.priority_status",
                        f"{trace.assessment_step_path}.priority_missing_criteria",
                    ],
                ),
            )
        )
    if assessment.recommendation_mode is RecommendationMode.INVESTIGATE_FURTHER:
        gaps.append(
            InformationGap(
                gap_id=f"{assessment.step_id}:investigation",
                step_id=assessment.step_id,
                kind=InformationGapKind.INVESTIGATION_REQUIRED,
                field_name="recommendation_mode",
                message="The assessment requires further investigation before AI adoption.",
                material_to_recommendation=True,
                basis=planning_basis(trace),
            )
        )
    return gaps


def build_portfolio(
    assessments: list[StepAssessment], traces: list[StepAssessmentTrace]
) -> OpportunityPortfolio:
    items = []
    for sequence, (assessment, trace) in enumerate(
        zip(assessments, traces, strict=True), start=1
    ):
        items.append(
            OpportunityPortfolioItem(
                sequence=sequence,
                step_id=assessment.step_id,
                current_activity=assessment.activity,
                recommendation_mode=assessment.recommendation_mode,
                capabilities=assessment.capabilities,
                priority_status=assessment.priority_status,
                priority=assessment.priority,
                priority_missing_criteria=assessment.priority_missing_criteria,
                gate_results=assessment.gate_results,
                missing_information=_missing_information(assessment, trace),
                recommended_human_roles=_roles(assessment, trace),
                rationale=assessment.reasoning,
                source_traceability=trace,
            )
        )
    return OpportunityPortfolio(items=items)

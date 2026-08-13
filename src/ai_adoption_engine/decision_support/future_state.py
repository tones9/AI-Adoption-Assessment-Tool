"""Mode-constrained proposed future-state workflow generation."""

from ai_adoption_engine.models.decision_support import (
    CapabilityUseStatus,
    FutureStateStep,
    InterventionType,
    OpportunityPortfolio,
    ProposedFutureStateWorkflow,
)
from ai_adoption_engine.models.enums import GateName, GateStatus, RecommendationMode

from ai_adoption_engine.decision_support.portfolio import planning_basis


_INTERVENTION = {
    RecommendationMode.AUTOMATE: InterventionType.AI_ENABLED_EXECUTION,
    RecommendationMode.AUGMENT: InterventionType.AI_ASSISTED_HUMAN_EXECUTION,
    RecommendationMode.INVESTIGATE_FURTHER: (
        InterventionType.CURRENT_STEP_WITH_INVESTIGATION_MARKER
    ),
    RecommendationMode.DO_NOT_RECOMMEND: (
        InterventionType.CURRENT_OR_CONVENTIONAL_EXECUTION
    ),
}

_CAPABILITY_STATUS = {
    RecommendationMode.AUTOMATE: CapabilityUseStatus.PROPOSED,
    RecommendationMode.AUGMENT: CapabilityUseStatus.PROPOSED,
    RecommendationMode.INVESTIGATE_FURTHER: (
        CapabilityUseStatus.UNDER_INVESTIGATION
    ),
    RecommendationMode.DO_NOT_RECOMMEND: CapabilityUseStatus.NOT_APPLIED,
}


def _proposed_activity(mode: RecommendationMode, activity: str) -> str:
    if mode is RecommendationMode.AUTOMATE:
        return f"AI-enabled execution of: {activity}"
    if mode is RecommendationMode.AUGMENT:
        return f"Human execution assisted by AI: {activity}"
    if mode is RecommendationMode.INVESTIGATE_FURTHER:
        return f"Retain current step and investigate feasibility: {activity}"
    return f"Retain current or conventional execution: {activity}"


def build_future_state(
    portfolio: OpportunityPortfolio,
    *,
    process_id: str,
    process_name: str,
) -> ProposedFutureStateWorkflow:
    steps = []
    for item in portfolio.items:
        risk = next(
            (result for result in item.gate_results if result.gate is GateName.RISK_AND_AUTONOMY),
            None,
        )
        if risk is None:
            raise ValueError(f"Missing risk/autonomy gate for step {item.step_id}")
        if item.recommendation_mode is RecommendationMode.AUTOMATE and risk.status not in {
            GateStatus.PASSED,
            GateStatus.PASSED_WITH_CONSTRAINTS,
        }:
            raise ValueError(
                f"AUTOMATE conflicts with risk/autonomy result for step {item.step_id}"
            )
        controls = [risk.rationale]
        if item.recommendation_mode is RecommendationMode.AUTOMATE:
            controls.append(
                "Human exception handling must be defined and validated before deployment."
            )
        elif item.recommendation_mode is RecommendationMode.AUGMENT:
            controls.append(
                "The human operator remains materially responsible for the activity."
            )
        elif item.recommendation_mode is RecommendationMode.INVESTIGATE_FURTHER:
            controls.append(
                "No AI intervention is approved until the identified evidence gaps are resolved."
            )
        else:
            controls.append("No AI intervention is proposed for this step.")
        steps.append(
            FutureStateStep(
                sequence=item.sequence,
                source_step_id=item.step_id,
                current_activity=item.current_activity,
                proposed_activity=_proposed_activity(
                    item.recommendation_mode, item.current_activity
                ),
                recommendation_mode=item.recommendation_mode,
                intervention_type=_INTERVENTION[item.recommendation_mode],
                capabilities=item.capabilities,
                capability_use_status=_CAPABILITY_STATUS[item.recommendation_mode],
                human_roles=item.recommended_human_roles,
                controls_and_constraints=controls,
                rationale=(
                    "This proposed representation is derived from the unchanged Phase 1 "
                    f"recommendation {item.recommendation_mode.value}."
                ),
                basis=planning_basis(item.source_traceability),
            )
        )
    return ProposedFutureStateWorkflow(
        current_state_process_id=process_id,
        current_state_process_name=process_name,
        steps=steps,
    )

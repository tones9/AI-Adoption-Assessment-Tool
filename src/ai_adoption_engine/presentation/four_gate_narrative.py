"""Read-only business narrative for the approved four-gate successor."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ai_adoption_engine.models.four_gate_assessment import (
    AutonomyCeiling,
    FourGatePriorityStatus,
    FourGateStatus,
    OutcomeCode,
    SelectedInterventionFamily,
)
from ai_adoption_engine.models.four_gate_decision_support import (
    FourGateDecisionPortfolioItem,
    FourGateDecisionSupportPackage,
    FourGateInformationGapKind,
)
from ai_adoption_engine.models.four_gate_integrated_assessment import (
    FourGateIntegratedAssessmentSuccess,
)
from ai_adoption_engine.presentation import labels
from ai_adoption_engine.presentation.contracts import phase5_presentation_contract


@dataclass(frozen=True)
class FourGateGapNarrative:
    field_name: str
    statement: str


@dataclass(frozen=True)
class FourGateGateNarrative:
    gate: str
    label: str
    status: str
    status_label: str
    rationale: str
    was_reached: bool


@dataclass(frozen=True)
class FourGateActivityNarrative:
    step_id: str
    sequence: int
    activity: str
    outcome_code: str
    outcome_label: str
    outcome_statement: str
    reason_statement: str
    blocking_gaps: tuple[FourGateGapNarrative, ...]
    contextual_gaps: tuple[FourGateGapNarrative, ...]
    priority_gaps: tuple[FourGateGapNarrative, ...]
    priority_statement: str
    next_action: str
    gates: tuple[FourGateGateNarrative, ...]
    technical_details: tuple[str, ...]

    def business_lines(self) -> tuple[str, ...]:
        return (
            self.activity,
            self.outcome_label,
            self.outcome_statement,
            self.reason_statement,
            *(item.statement for item in self.blocking_gaps),
            *(item.statement for item in self.contextual_gaps),
            *(item.statement for item in self.priority_gaps),
            self.priority_statement,
            self.next_action,
        )


@dataclass(frozen=True)
class FourGateProcessNarrative:
    process_name: str
    headline: str
    what_we_found: tuple[str, ...]
    what_is_still_needed: tuple[str, ...]
    what_this_means: tuple[str, ...]
    next_action: tuple[str, ...]
    activities: tuple[FourGateActivityNarrative, ...]
    outcome_counts: tuple[tuple[str, int], ...]
    policy_reference: tuple[str, ...]


@dataclass(frozen=True)
class FourGatePackageNarrative:
    process_name: str
    completeness_statement: str
    headline: str
    outcome_groups: tuple[str, ...]
    why: tuple[str, ...]
    what_this_means: tuple[str, ...]
    next_action: tuple[str, ...]
    limitations: tuple[str, ...]
    technical_reference: tuple[str, ...]


def build_four_gate_process_narrative(
    integrated: FourGateIntegratedAssessmentSuccess,
) -> FourGateProcessNarrative:
    """Project an exact phase5-v0.2 result; never recompute its decision."""

    phase5_presentation_contract(integrated)
    steps = integrated.process_assessment.step_assessments
    activities = tuple(
        _activity_from_assessment(step, index)
        for index, step in enumerate(steps, start=1)
    )
    counts = Counter(step.outcome_code for step in steps)
    return FourGateProcessNarrative(
        process_name=integrated.process_assessment.process_name,
        headline=_headline(activities),
        what_we_found=_outcome_groups(activities),
        what_is_still_needed=tuple(
            f"{item.activity}: {gap.statement}"
            for item in activities
            for gap in item.blocking_gaps
        ),
        what_this_means=(
            "Each final outcome is derived from the recorded four-gate path; "
            "priority is a separate planning status.",
            "This assessment is decision support only and does not authorise "
            "implementation, a pilot, or deployment.",
        ),
        next_action=(
            "Review each activity's final decision and supporting evidence in "
            "the Decision Package.",
        ),
        activities=activities,
        outcome_counts=tuple(
            (outcome.value, counts[outcome]) for outcome in OutcomeCode
        ),
        policy_reference=(
            f"Framework: {integrated.process_assessment.framework_id} "
            f"{integrated.process_assessment.framework_version}",
            f"Decision contract: {integrated.metadata.phase1_contract_version}",
            f"Decision policy: {integrated.policy.policy_id} "
            f"{integrated.policy.policy_version} "
            f"({integrated.policy.policy_status})",
            "Thresholds and weights are provisional and not academically validated.",
            f"Assessment run: {integrated.metadata.assessment_run_id}",
        ),
    )


def build_four_gate_package_narrative(
    package: FourGateDecisionSupportPackage,
) -> FourGatePackageNarrative:
    """Project an exact phase6-v0.2 package into decision-first language."""

    from ai_adoption_engine.presentation.contracts import phase6_presentation_contract

    phase6_presentation_contract(package)
    activities = tuple(_activity_from_item(item) for item in package.portfolio.items)
    blocking = [
        gap
        for gap in package.missing_information
        if gap.kind is FourGateInformationGapKind.ACTIVE_DECISION_BLOCKER
    ]
    return FourGatePackageNarrative(
        process_name=package.current_state.process_name,
        completeness_statement=(
            "This Decision Package is complete and records classified information gaps."
            if package.missing_information
            else "This Decision Package is complete and records no information gaps."
        ),
        headline=_headline(activities),
        outcome_groups=_outcome_groups(activities),
        why=tuple(
            f"{item.activity}: {item.reason_statement}" for item in activities
        ),
        what_this_means=(
            "The displayed outcome is the sole final recommendation for each activity.",
            "Decision status and priority status are separate; non-AI outcomes "
            "are not treated as AI priorities.",
        ),
        next_action=(
            (
                "Resolve only the active decision blockers listed below before "
                "seeking a final decision for the affected activities."
                if blocking
                else "No active decision-blocking evidence request is recorded."
            ),
            "Any implementation or deployment work remains outside this product.",
        ),
        limitations=(
            "The policy thresholds, weights and bands are provisional and not "
            "academically validated.",
            "This package is decision support only. It does not approve "
            "implementation or deployment.",
            "The proposed future-state workflow is a proposal. Nothing in it "
            "has been deployed.",
            "This package does not establish Return on Investment (ROI).",
        ),
        technical_reference=(
            f"Package ID: {package.package_id}",
            f"Package schema version: {package.package_schema_version}",
            f"Phase 5 schema version: {package.source.integration_schema_version}",
            f"Decision contract: {package.source.phase1_contract_version}",
            f"Framework: {package.current_state.framework_id} "
            f"{package.current_state.framework_version}",
            f"Decision policy: {package.source.policy.policy_id} "
            f"{package.source.policy.policy_version} "
            f"({package.source.policy.policy_status})",
            f"Decision policy fingerprint: "
            f"{package.source.policy.decision_policy_fingerprint}",
            f"Validated process fingerprint: "
            f"{package.source.lineage.validated_process_fingerprint}",
            f"Assessment run: {package.source.integrated_assessment_run_id}",
        ),
    )


def _activity_from_assessment(step, sequence: int) -> FourGateActivityNarrative:
    blocking_fields = {gap.field_name for gap in step.blocking_gaps}
    blocking = tuple(
        FourGateGapNarrative(gap.field_name, gap.blocking_question)
        for gap in step.blocking_gaps
    )
    contextual: list[FourGateGapNarrative] = []
    priority: list[FourGateGapNarrative] = []
    for criterion in step.criteria:
        if criterion.knowledge_state.value != "unknown":
            continue
        if criterion.criterion.value in blocking_fields:
            continue
        gap = FourGateGapNarrative(
            criterion.criterion.value,
            f"{labels.criterion_label(criterion.criterion.value)} is not established; "
            "it did not block the reached decision.",
        )
        if criterion.material_to_priority and not criterion.material_to_decision:
            priority.append(gap)
        else:
            contextual.append(gap)
    return _activity(
        step=step,
        sequence=sequence,
        blocking=blocking,
        contextual=tuple(contextual),
        priority=tuple(priority),
        reason=_assessment_reason(step),
    )


def _activity_from_item(
    item: FourGateDecisionPortfolioItem,
) -> FourGateActivityNarrative:
    by_kind = {
        kind: tuple(
            FourGateGapNarrative(gap.field_name, gap.message)
            for gap in item.information_gaps
            if gap.kind is kind
        )
        for kind in FourGateInformationGapKind
    }
    return _activity(
        step=item,
        sequence=item.sequence,
        blocking=by_kind[FourGateInformationGapKind.ACTIVE_DECISION_BLOCKER],
        contextual=by_kind[FourGateInformationGapKind.CONTEXTUAL_UNKNOWN],
        priority=by_kind[FourGateInformationGapKind.PRIORITY_ONLY],
        reason=item.final_recommendation,
    )


def _activity(
    *,
    step,
    sequence: int,
    blocking: tuple[FourGateGapNarrative, ...],
    contextual: tuple[FourGateGapNarrative, ...],
    priority: tuple[FourGateGapNarrative, ...],
    reason: str,
) -> FourGateActivityNarrative:
    outcome = step.outcome_code
    gates = tuple(
        FourGateGateNarrative(
            gate=gate.gate.value,
            label=labels.four_gate_name_label(gate.gate.value),
            status=gate.status.value,
            status_label=labels.four_gate_status_label(gate.status.value),
            rationale=gate.rationale,
            was_reached=gate.status is not FourGateStatus.NOT_EVALUATED,
        )
        for gate in step.gate_results
    )
    veto = _is_safety_veto(step)
    return FourGateActivityNarrative(
        step_id=step.step_id,
        sequence=sequence,
        activity=getattr(step, "activity", None) or step.current_activity,
        outcome_code=outcome.value,
        outcome_label=labels.four_gate_outcome_label(outcome.value),
        outcome_statement=_OUTCOME_STATEMENTS[outcome],
        reason_statement=reason,
        blocking_gaps=blocking,
        contextual_gaps=contextual,
        priority_gaps=priority,
        priority_statement=_priority_statement(step),
        next_action=_NEXT_ACTIONS[outcome],
        gates=gates,
        technical_details=(
            f"decision_status: {step.decision_status.value}",
            f"change_disposition: {step.change_disposition.value}",
            f"readiness_disposition: {step.readiness_disposition.value}",
            "selected_intervention_family: "
            f"{step.selected_intervention_family.value}",
            f"autonomy_ceiling: {step.autonomy_ceiling.value}",
            f"outcome_code (derived): {outcome.value}",
            f"safety_veto: {str(veto).lower()}",
        ),
    )


def _assessment_reason(step) -> str:
    if step.outcome_code is OutcomeCode.NO_CHANGE_JUSTIFIED:
        return "Gate 1 established that changing this activity is not justified."
    if step.outcome_code is OutcomeCode.PROCESS_IMPROVEMENT_FIRST:
        gate = step.gate_results[1]
        names = ", ".join(
            labels.criterion_label(item.value) for item in gate.material_criteria
        )
        return f"Established Gate 2 blocker evidence: {names}."
    if _is_safety_veto(step):
        return (
            "AI was selected as the Gate 3 candidate and rejected by the Gate 4 "
            "safety veto. Keep Human-Led is the sole final recommendation."
        )
    if step.outcome_code is OutcomeCode.DISCOVERY_REQUIRED:
        return "The active decision cannot be completed until the listed blocker is resolved."
    if step.outcome_code is OutcomeCode.CONVENTIONAL_AUTOMATION:
        return (
            "Gate 3 selected conventional automation before AI capability fit "
            "became decision-material."
        )
    if (
        step.outcome_code is OutcomeCode.KEEP_HUMAN_LED
        and step.selected_intervention_family
        is SelectedInterventionFamily.KEEP_HUMAN_LED
    ):
        return "Gate 3 selected human-led work as the intervention."
    if step.outcome_code is OutcomeCode.AI_ASSISTED_WORK:
        return "Gate 4 set AI-assisted work as the maximum permitted autonomy."
    return "Gate 4 permitted AI automation under the recorded controls."


def _priority_statement(step) -> str:
    if step.priority_status is FourGatePriorityStatus.COMPLETE and step.priority:
        band = labels.priority_band_label(step.priority.band)
        return (
            f"Priority status: Complete — score {step.priority.score:.1f} of 100 "
            f"({band} band)."
        )
    if step.priority_status is FourGatePriorityStatus.INCOMPLETE:
        names = ", ".join(
            labels.criterion_label(item.value)
            for item in step.priority_missing_criteria
        )
        return f"Priority status: Incomplete — missing priority input(s): {names}."
    return "Priority status: Not applicable to this final outcome."


def _is_safety_veto(step) -> bool:
    return (
        step.selected_intervention_family is SelectedInterventionFamily.AI
        and step.autonomy_ceiling is AutonomyCeiling.AI_NOT_PERMITTED
        and step.outcome_code is OutcomeCode.KEEP_HUMAN_LED
    )


def _headline(activities: tuple[FourGateActivityNarrative, ...]) -> str:
    if not activities:
        return "No activities were assessed."
    if len(activities) == 1:
        item = activities[0]
        return f"The final decision for {item.activity} is {item.outcome_label}."
    return (
        "This process contains distinct activity decisions. Each sole final "
        "outcome is shown below."
    )


def _outcome_groups(
    activities: tuple[FourGateActivityNarrative, ...],
) -> tuple[str, ...]:
    return tuple(
        f"{labels.four_gate_outcome_label(outcome.value)}: "
        + ", ".join(
            item.activity for item in activities if item.outcome_code == outcome.value
        )
        + "."
        for outcome in OutcomeCode
        if any(item.outcome_code == outcome.value for item in activities)
    )


_OUTCOME_STATEMENTS = {
    OutcomeCode.NO_CHANGE_JUSTIFIED: (
        "The evidence supports leaving this activity unchanged; this does not "
        "classify the activity as human-led."
    ),
    OutcomeCode.AI_AUTOMATION: (
        "AI automation is the supported decision, subject to the recorded controls."
    ),
    OutcomeCode.AI_ASSISTED_WORK: (
        "AI-assisted work is the supported decision, with human involvement retained."
    ),
    OutcomeCode.CONVENTIONAL_AUTOMATION: (
        "Conventional automation is the supported decision; AI-fit evidence was "
        "not required to reach it."
    ),
    OutcomeCode.PROCESS_IMPROVEMENT_FIRST: (
        "Process improvement must come first because an evidenced Gate 2 blocker "
        "was established."
    ),
    OutcomeCode.KEEP_HUMAN_LED: "Keep Human-Led is the sole final recommendation.",
    OutcomeCode.DISCOVERY_REQUIRED: (
        "More evidence is required only for the active decision that remains open."
    ),
}

_NEXT_ACTIONS = {
    OutcomeCode.NO_CHANGE_JUSTIFIED: "No intervention is proposed on the current evidence.",
    OutcomeCode.AI_AUTOMATION: "Review the proposed controls before any separate implementation decision.",
    OutcomeCode.AI_ASSISTED_WORK: "Review the proposed human controls before any separate implementation decision.",
    OutcomeCode.CONVENTIONAL_AUTOMATION: "Evaluate a conventional automation path outside this decision product.",
    OutcomeCode.PROCESS_IMPROVEMENT_FIRST: "Address the established readiness blocker before selecting an intervention.",
    OutcomeCode.KEEP_HUMAN_LED: "Retain human-led work under the recorded rationale and controls.",
    OutcomeCode.DISCOVERY_REQUIRED: "Resolve the active blocking question; contextual and priority gaps are not decision blockers.",
}

"""Read-only business narrative projection over an authoritative assessment.

Portfolio Version 1 Decision Experience, Stage 2.  Governed by
``docs/portfolio-v1-decision-experience-design-v0.1.md``.

This module explains a decision the Engine has already made.  It never makes
one.  It is pure, deterministic, Streamlit-free, and imports no service,
persistence, workspace, gate, scoring, or policy module: every business
statement it produces restates structured fields that Phase 5 already
persisted, in line with section 5 of the governing design.

Two rules govern every sentence here:

* **Source of truth.**  A statement may restate structured fields only.  Engine
  rationale strings are carried verbatim for Layer 2 and are never parsed to
  manufacture business meaning.
* **Specificity.**  A statement is as specific as the structured evidence
  permits and no more.  ``data_readiness`` being ``UNKNOWN`` supports one
  sentence about data readiness; it never becomes an enumeration of sub-facts
  the Engine does not record.

``UNKNOWN`` means unknown.  It never becomes poor, unsuitable, failed, or not
ready.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_adoption_engine.models.assessment import (
    GateResult,
    StepAssessment,
)
from ai_adoption_engine.models.enums import (
    GateStatus,
    KnowledgeState,
    PriorityStatus,
    RecommendationMode,
)
from ai_adoption_engine.models.integrated_assessment import (
    IntegratedAssessmentSuccess,
)
from ai_adoption_engine.presentation import labels


ACCOUNTABILITY_FIELD = "human_accountability_required"

ROI_LIMITATION = "This assessment does not establish Return on Investment (ROI)."

NO_AUTHORISATION = (
    "This result does not authorise implementation, a pilot, or deployment."
)


# ---------------------------------------------------------------------------
# Frozen projection records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MissingFact:
    """One fact the approved evidence does not establish, or only assumes."""

    field_name: str
    label: str
    statement: str
    knowledge_state: str
    affects_recommendation: bool
    affects_priority: bool


@dataclass(frozen=True)
class GateReference:
    """Layer 2 reference to one persisted assessment check.

    ``rationale`` is the Engine's own text, carried verbatim.  Nothing in this
    module reads it.
    """

    gate: str
    gate_label: str
    status: str
    status_label: str
    was_reached: bool
    material_criteria: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class ActivityNarrative:
    """Business explanation of one assessed activity."""

    step_id: str
    sequence: int
    activity: str
    recommendation: str
    outcome_label: str
    outcome_statement: str
    reason_statement: str
    missing_facts: tuple[MissingFact, ...]
    unconfirmed_facts: tuple[MissingFact, ...]
    priority_statement: str
    next_action: str
    deciding_gate: GateReference | None
    gates: tuple[GateReference, ...]

    def business_lines(self) -> tuple[str, ...]:
        """Return exactly the Layer 1 text for this activity."""

        return (
            self.activity,
            self.outcome_label,
            self.outcome_statement,
            self.reason_statement,
            *(item.statement for item in self.missing_facts),
            *(item.statement for item in self.unconfirmed_facts),
            self.priority_statement,
            self.next_action,
        )


@dataclass(frozen=True)
class ProcessNarrative:
    """Business explanation of one assessed process."""

    process_name: str
    headline: str
    what_we_found: tuple[str, ...]
    what_is_still_needed: tuple[str, ...]
    what_this_means: tuple[str, ...]
    next_action: tuple[str, ...]
    activities: tuple[ActivityNarrative, ...]
    outcome_counts: tuple[tuple[str, int], ...]
    policy_reference: tuple[str, ...]

    def business_lines(self) -> tuple[str, ...]:
        """Return exactly the Layer 1 text for the whole process.

        Technical references - gate rationale, gate tokens, policy identifiers
        and supporting counts - are deliberately excluded, so wording
        safeguards can be asserted against Layer 1 alone.
        """

        lines = [
            self.headline,
            *self.what_we_found,
            *self.what_is_still_needed,
            *self.what_this_means,
            *self.next_action,
        ]
        for activity in self.activities:
            lines.extend(activity.business_lines())
        return tuple(lines)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def build_process_narrative(
    integrated: IntegratedAssessmentSuccess,
) -> ProcessNarrative:
    """Project one successful integrated assessment into business language."""

    assessment = integrated.process_assessment
    activities = tuple(
        build_activity_narrative(step, sequence=index)
        for index, step in enumerate(assessment.step_assessments, start=1)
    )
    counts = {
        mode: sum(
            1
            for step in assessment.step_assessments
            if step.recommendation_mode is mode
        )
        for mode in RecommendationMode
    }
    return ProcessNarrative(
        process_name=assessment.process_name,
        headline=_headline(counts, len(activities)),
        what_we_found=_what_we_found(assessment.step_assessments),
        what_is_still_needed=_what_is_still_needed(activities),
        what_this_means=_what_this_means(counts),
        next_action=_process_next_action(counts),
        activities=activities,
        outcome_counts=tuple(
            (mode.value, counts[mode]) for mode in RecommendationMode
        ),
        policy_reference=(
            f"Decision policy: {integrated.policy.policy_id} "
            f"{integrated.policy.policy_version} ({integrated.policy.policy_status})",
            f"Assessment run: {integrated.metadata.assessment_run_id}",
        ),
    )


def build_activity_narrative(
    step: StepAssessment, *, sequence: int = 1
) -> ActivityNarrative:
    """Project one persisted step assessment into business language."""

    gates = tuple(_gate_reference(gate) for gate in step.gate_results)
    deciding = _deciding_gate(step.gate_results)
    missing = _missing_facts(step)
    return ActivityNarrative(
        step_id=step.step_id,
        sequence=sequence,
        activity=step.activity,
        recommendation=step.recommendation_mode.value,
        outcome_label=labels.recommendation_label(step.recommendation_mode.value),
        outcome_statement=_OUTCOME_STATEMENTS[step.recommendation_mode],
        reason_statement=_reason_statement(step, deciding, missing),
        missing_facts=missing,
        unconfirmed_facts=_unconfirmed_facts(step),
        priority_statement=_priority_statement(step),
        next_action=_ACTIVITY_NEXT_ACTIONS[step.recommendation_mode],
        deciding_gate=_gate_reference(deciding) if deciding is not None else None,
        gates=gates,
    )


# ---------------------------------------------------------------------------
# Outcome vocabulary
#
# Each statement restates one authoritative ``recommendation_mode`` and adds no
# claim beyond it.  None of them implies deployment or implementation approval,
# permanent unsuitability, or a guaranteed result.
# ---------------------------------------------------------------------------

_OUTCOME_STATEMENTS: dict[RecommendationMode, str] = {
    RecommendationMode.AUTOMATE: (
        "The current evidence supports considering a defined automation "
        "opportunity for this activity."
    ),
    RecommendationMode.AUGMENT: (
        "The current evidence supports considering AI-assisted human work for "
        "this activity, with human responsibility retained."
    ),
    RecommendationMode.INVESTIGATE_FURTHER: (
        "More information is needed before an AI adoption recommendation can be "
        "made for this activity."
    ),
    RecommendationMode.DO_NOT_RECOMMEND: (
        "AI adoption is not recommended for this activity on the current evidence."
    ),
}

_ACTIVITY_NEXT_ACTIONS: dict[RecommendationMode, str] = {
    RecommendationMode.AUTOMATE: (
        "Review this result, its conditions and its limitations in the Decision "
        "Package."
    ),
    RecommendationMode.AUGMENT: (
        "Review this result, its conditions and its limitations in the Decision "
        "Package."
    ),
    RecommendationMode.INVESTIGATE_FURTHER: (
        "Gather the information listed above before an AI adoption recommendation "
        "can be made for this activity. Supplying it does not guarantee a "
        "different result."
    ),
    RecommendationMode.DO_NOT_RECOMMEND: (
        "No further action is required for this activity unless the recorded "
        "evidence changes."
    ),
}


# ---------------------------------------------------------------------------
# Activity-level derivation
# ---------------------------------------------------------------------------


def _gate_reference(gate: GateResult) -> GateReference:
    return GateReference(
        gate=gate.gate.value,
        gate_label=labels.gate_name_label(gate.gate.value),
        status=gate.status.value,
        status_label=labels.gate_status_label(gate.status.value),
        was_reached=gate.status is not GateStatus.NOT_EVALUATED,
        material_criteria=tuple(item.value for item in gate.material_criteria),
        rationale=gate.rationale,
    )


def _deciding_gate(gate_results: list[GateResult]) -> GateResult | None:
    """Return the persisted check that carried the outcome.

    Selection reads persisted ``status`` values in their persisted order.  No
    gate logic is recomputed and no threshold is read.
    """

    for gate in gate_results:
        if gate.status in {GateStatus.FAILED, GateStatus.PASSED_WITH_CONSTRAINTS}:
            return gate
    passed = [item for item in gate_results if item.status is GateStatus.PASSED]
    return passed[-1] if passed else None


def _missing_facts(step: StepAssessment) -> tuple[MissingFact, ...]:
    """Return every fact the approved evidence does not establish."""

    facts = [
        MissingFact(
            field_name=criterion.criterion.value,
            label=labels.criterion_label(criterion.criterion.value),
            statement=_not_established(criterion.criterion.value),
            knowledge_state=criterion.knowledge_state.value,
            affects_recommendation=criterion.material_to_recommendation,
            affects_priority=criterion.material_to_priority,
        )
        for criterion in step.criteria
        if criterion.knowledge_state is KnowledgeState.UNKNOWN
    ]
    accountability = step.human_accountability
    if accountability.knowledge_state is KnowledgeState.UNKNOWN:
        facts.append(
            MissingFact(
                field_name=ACCOUNTABILITY_FIELD,
                label=labels.criterion_label(ACCOUNTABILITY_FIELD),
                statement=_not_established(ACCOUNTABILITY_FIELD),
                knowledge_state=accountability.knowledge_state.value,
                affects_recommendation=accountability.material_to_recommendation,
                affects_priority=False,
            )
        )
    return tuple(facts)


def _unconfirmed_facts(step: StepAssessment) -> tuple[MissingFact, ...]:
    """Return material facts recorded as assumptions rather than confirmed.

    The Engine's own confidence threshold is never reproduced here; see section
    5.1 of the governing design.
    """

    return tuple(
        MissingFact(
            field_name=criterion.criterion.value,
            label=labels.criterion_label(criterion.criterion.value),
            statement=(
                f"{labels.criterion_label(criterion.criterion.value)}: this is "
                "recorded as an assumption and still requires confirmation."
            ),
            knowledge_state=criterion.knowledge_state.value,
            affects_recommendation=criterion.material_to_recommendation,
            affects_priority=criterion.material_to_priority,
        )
        for criterion in step.criteria
        if criterion.knowledge_state is KnowledgeState.INFERRED
        and (criterion.material_to_recommendation or criterion.material_to_priority)
    )


def _not_established(field_name: str) -> str:
    return (
        f"{labels.criterion_label(field_name)}: the available evidence does not "
        f"establish {labels.criterion_subject(field_name)}."
    )


def _reason_statement(
    step: StepAssessment,
    deciding: GateResult | None,
    missing: tuple[MissingFact, ...],
) -> str:
    """Explain the outcome from the persisted deciding check.

    The recommendation mode - not a recomputed rule - distinguishes an
    incomplete check from a check that was not met.
    """

    if deciding is None:
        return "The assessment did not record a check outcome for this activity."
    gate_label = labels.gate_name_label(deciding.gate.value)
    mode = step.recommendation_mode
    if mode is RecommendationMode.INVESTIGATE_FURTHER:
        named = _material_missing_subjects(deciding, missing)
        if named:
            return (
                f"The {gate_label} check could not be completed because the "
                f"available evidence does not establish {_join(named)}."
            )
        return (
            f"The {gate_label} check could not be completed because the evidence "
            "recorded for it was not sufficient."
        )
    if mode is RecommendationMode.DO_NOT_RECOMMEND:
        return (
            f"The {gate_label} check was not met by the values recorded in the "
            "approved evidence."
        )
    if deciding.status is GateStatus.PASSED_WITH_CONSTRAINTS:
        return (
            f"The {gate_label} check passed with conditions, so material human "
            "involvement is expected to remain."
        )
    return "Every assessment check passed on the approved evidence."


def _material_missing_subjects(
    deciding: GateResult, missing: tuple[MissingFact, ...]
) -> tuple[str, ...]:
    """Name only facts that are both material to the check and not established."""

    material = {item.value for item in deciding.material_criteria}
    if deciding.accountability_material:
        material.add(ACCOUNTABILITY_FIELD)
    return tuple(
        labels.criterion_subject(fact.field_name)
        for fact in missing
        if fact.field_name in material
    )


def _priority_statement(step: StepAssessment) -> str:
    if step.priority_status is PriorityStatus.INCOMPLETE:
        named = _join(
            tuple(
                labels.criterion_label(item.value)
                for item in step.priority_missing_criteria
            )
        )
        if not named:
            return "A priority score could not be calculated from the available evidence."
        return (
            "A priority score could not be calculated because the available "
            f"evidence does not establish: {named}."
        )
    if step.priority_status is PriorityStatus.COMPLETE and step.priority is not None:
        band = labels.priority_band_label(step.priority.band.value)
        return f"Priority score {step.priority.score:.1f} of 100 ({band} band)."
    return "Priority scoring does not apply to this outcome."


# ---------------------------------------------------------------------------
# Process-level derivation
# ---------------------------------------------------------------------------


def _headline(counts: dict[RecommendationMode, int], total: int) -> str:
    """Describe the decision situation, not the counts."""

    if total == 0:
        return "No activities were assessed."
    investigate = counts[RecommendationMode.INVESTIGATE_FURTHER]
    recommended = (
        counts[RecommendationMode.AUTOMATE] + counts[RecommendationMode.AUGMENT]
    )
    not_recommended = counts[RecommendationMode.DO_NOT_RECOMMEND]
    if investigate == total:
        return (
            "No AI adoption recommendation can be made for this process yet. "
            "Every assessed activity needs more information first."
        )
    if not_recommended == total:
        return (
            "AI adoption is not recommended for any assessed activity on the "
            "current evidence."
        )
    if recommended == total:
        return (
            "Every assessed activity has a supported AI adoption recommendation "
            "on the current evidence."
        )
    if investigate == 0:
        return (
            "Some activities have a supported AI adoption recommendation on the "
            "current evidence and the rest are not recommended. No activity is "
            "waiting for more information."
        )
    if recommended == 0:
        return (
            "No activity has a supported AI adoption recommendation. Some are not "
            "recommended on the current evidence and others need more information "
            "first."
        )
    return (
        "This process has a mixed result: some activities have a supported AI "
        "adoption recommendation, and others need more information before one can "
        "be made."
    )


def _what_we_found(steps: list[StepAssessment]) -> tuple[str, ...]:
    groups = (
        (
            "Recommendation supported on the current evidence",
            (RecommendationMode.AUTOMATE, RecommendationMode.AUGMENT),
        ),
        (
            "More information needed first",
            (RecommendationMode.INVESTIGATE_FURTHER,),
        ),
        (
            "Not recommended on the current evidence",
            (RecommendationMode.DO_NOT_RECOMMEND,),
        ),
    )
    found = []
    for label, modes in groups:
        named = [step.activity for step in steps if step.recommendation_mode in modes]
        if named:
            found.append(f"{label}: {_join(tuple(named))}.")
    return tuple(found)


def _what_is_still_needed(
    activities: tuple[ActivityNarrative, ...],
) -> tuple[str, ...]:
    """Summarise unestablished facts across activities, in first-seen order."""

    if not activities:
        return ()
    ordered: list[str] = []
    where: dict[str, list[str]] = {}
    material: dict[str, bool] = {}
    statement: dict[str, str] = {}
    for activity in activities:
        for fact in activity.missing_facts:
            if fact.field_name not in where:
                ordered.append(fact.field_name)
                where[fact.field_name] = []
                material[fact.field_name] = False
                statement[fact.field_name] = fact.statement
            where[fact.field_name].append(activity.activity)
            material[fact.field_name] = (
                material[fact.field_name] or fact.affects_recommendation
            )
    needed = []
    for field_name in ordered:
        names = where[field_name]
        if len(names) == len(activities):
            scope = f"This applies to all {len(activities)} assessed activities."
        else:
            scope = f"This applies to: {_join(tuple(names))}."
        impact = (
            " It affects the recommendation."
            if material[field_name]
            else " It does not affect the recommendation."
        )
        needed.append(f"{statement[field_name]} {scope}{impact}")
    return tuple(needed)


def _what_this_means(counts: dict[RecommendationMode, int]) -> tuple[str, ...]:
    meaning = []
    if counts[RecommendationMode.INVESTIGATE_FURTHER]:
        meaning.append(
            "'More information needed' is a statement about the available "
            "evidence, not a judgement about the activity or about AI."
        )
    if counts[RecommendationMode.AUTOMATE] or counts[RecommendationMode.AUGMENT]:
        meaning.append(
            "A supported recommendation means the recorded evidence met the "
            "assessment's checks. It is not approval to deploy or implement "
            "anything."
        )
    if counts[RecommendationMode.DO_NOT_RECOMMEND]:
        meaning.append(
            "'Not recommended' reflects the evidence recorded today and can "
            "change if the recorded evidence changes."
        )
    meaning.append(ROI_LIMITATION)
    return tuple(meaning)


def _process_next_action(counts: dict[RecommendationMode, int]) -> tuple[str, ...]:
    actions = []
    if counts[RecommendationMode.INVESTIGATE_FURTHER]:
        actions.append(
            "Review the information listed under what is still needed. Supplying "
            "it does not guarantee a different result."
        )
    actions.append(
        "The Decision Package presents this result with its limitations and the "
        "continuation paths that are permitted."
    )
    actions.append(NO_AUTHORISATION)
    return tuple(actions)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def _join(items: tuple[str, ...]) -> str:
    """Join phrases deterministically in their supplied order."""

    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" and {items[-1]}"

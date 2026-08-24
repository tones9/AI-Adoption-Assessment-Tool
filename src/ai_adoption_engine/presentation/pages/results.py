"""Assessment Results as a business decision page.

Layer 1 - the decision, its reason, what is missing and what happens next - is
visible by default and comes entirely from ``decision_narrative``.  Layer 2 -
gates, criteria, knowledge states, priority detail, evidence, provenance and
policy identifiers - is preserved verbatim behind the canonical
``Technical reasoning and evidence`` control.

This page composes and renders.  It never interprets an assessment: no phrase
tables, no rationale parsing, no gate recomputation.  See
``docs/portfolio-v1-decision-experience-design-v0.1.md``.
"""

from collections import Counter

import streamlit as st

from ai_adoption_engine.models.enums import PriorityStatus, RecommendationMode
from ai_adoption_engine.models.integrated_assessment import IntegratedAssessmentSuccess
from ai_adoption_engine.presentation import labels
from ai_adoption_engine.presentation.components.decision_header import (
    HeaderSection,
    render_decision_header,
)
from ai_adoption_engine.presentation.components.status import guard
from ai_adoption_engine.presentation.components.technical_details import (
    technical_details,
)
from ai_adoption_engine.presentation.context import (
    hydrate_workspace,
    refresh_workspace,
    switch_to_registered_page,
    workspace_writes_available,
    workspace_service,
)
from ai_adoption_engine.presentation.decision_narrative import (
    ActivityNarrative,
    build_process_narrative,
)


_MEANINGFUL_PRIORITY_STATUSES = frozenset(
    {PriorityStatus.COMPLETE, PriorityStatus.INCOMPLETE}
)

_SUPPORTING_COUNT_LABELS = (
    (RecommendationMode.AUTOMATE, "Automate"),
    (RecommendationMode.AUGMENT, "Augment"),
    (RecommendationMode.INVESTIGATE_FURTHER, "Investigate"),
    (RecommendationMode.DO_NOT_RECOMMEND, "Do not recommend"),
)


def _render_activity_technical_layer(integrated, step) -> None:
    """Render every authoritative technical value for one activity."""

    st.caption(f"Recommendation: {step.recommendation_mode.value}")
    st.caption(f"Internal step ID: {step.step_id}")

    st.markdown("**Assessment checks**")
    for gate in step.gate_results:
        with st.container(border=True):
            st.write(
                f"{labels.gate_name_label(gate.gate.value)} — "
                f"{labels.gate_status_label(gate.status.value)} "
                f"({gate.status.value})"
            )
            st.caption(gate.rationale)
            if gate.material_criteria:
                st.caption(
                    "Material criteria: "
                    + ", ".join(item.value for item in gate.material_criteria)
                )
            if gate.accountability_material:
                st.caption("Human accountability was material to this check.")

    st.markdown("**Assessment reasoning**")
    for reason in step.reasoning:
        st.write(f"- {reason}")

    st.markdown("**Criteria**")
    for criterion in step.criteria:
        st.caption(
            f"{criterion.criterion.value}: value={criterion.value} · "
            f"{criterion.knowledge_state.value} · "
            f"material_to_recommendation={criterion.material_to_recommendation} · "
            f"material_to_priority={criterion.material_to_priority}"
        )
    accountability = step.human_accountability
    st.caption(
        f"human_accountability_required: value={accountability.value} · "
        f"{accountability.knowledge_state.value} · "
        f"material_to_recommendation={accountability.material_to_recommendation}"
    )

    st.markdown("**Priority**")
    st.caption(f"priority_status: {step.priority_status.value}")
    if step.priority is not None:
        st.caption(
            f"score={step.priority.score:.2f} · band={step.priority.band.value}"
        )
        for component in step.priority.components:
            st.caption(
                f"{component.criterion.value}: raw={component.raw_value} · "
                f"favourable={component.favourable_value} · "
                f"weight={component.weight} · contribution={component.contribution}"
            )
    if step.priority_missing_criteria:
        st.caption(
            "priority_missing_criteria: "
            + ", ".join(item.value for item in step.priority_missing_criteria)
        )

    st.markdown("**Mapped AI capabilities**")
    if step.capabilities:
        st.caption(", ".join(item.value for item in step.capabilities))
    else:
        st.caption("No AI capability proposed.")

    st.markdown("**Evidence and provenance**")
    trace = next(
        item for item in integrated.step_traceability if item.step_id == step.step_id
    )
    st.caption(
        f"Activity origin: {trace.activity.origin.value} · "
        f"Review: {trace.activity.review_disposition.value}"
    )
    evidence_by_id = {item.evidence_id: item for item in step.evidence}
    for evidence in step.evidence:
        st.caption(f"{evidence.source_locator} · {evidence.evidence_id}")
        st.code(evidence.supporting_snippet, language=None, wrap_lines=True)
    for value_trace in [
        *trace.criteria,
        trace.human_accountability,
        *trace.capability_signals,
    ]:
        st.caption(
            f"{value_trace.review_field_path}: {value_trace.origin.value} / "
            f"{value_trace.knowledge_state.value}"
        )
        for evidence in value_trace.evidence:
            resolved = evidence_by_id.get(evidence.evidence_id)
            if resolved:
                st.code(resolved.supporting_snippet, language=None, wrap_lines=True)
            st.caption(f"{evidence.source_locator} · block {evidence.block_id}")


def _render_activity(integrated, narrative: ActivityNarrative, step) -> None:
    """Render one activity: outcome, why, what is missing, what happens next."""

    with st.container(border=True):
        st.markdown(f"**{narrative.sequence}. {narrative.activity}**")
        st.markdown(f"**{narrative.outcome_label}** — {narrative.outcome_statement}")
        st.write(narrative.reason_statement)
        if narrative.missing_facts:
            st.markdown("**What is missing**")
            for fact in narrative.missing_facts:
                suffix = (
                    " This affects the recommendation."
                    if fact.affects_recommendation
                    else ""
                )
                st.write(f"- {fact.statement}{suffix}")
        if narrative.unconfirmed_facts:
            st.markdown("**Recorded as assumptions**")
            for fact in narrative.unconfirmed_facts:
                st.write(f"- {fact.statement}")
        st.markdown(f"**Next:** {narrative.next_action}")
        if step.priority_status in _MEANINGFUL_PRIORITY_STATUSES:
            st.caption(narrative.priority_statement)
        with technical_details():
            _render_activity_technical_layer(integrated, step)


def _render_supporting_counts(steps) -> None:
    """Counts support the conclusion above; they are never the conclusion."""

    counts = Counter(item.recommendation_mode for item in steps)
    st.caption("Supporting numbers")
    columns = st.columns(5)
    columns[0].metric("Activities assessed", len(steps))
    for column, (mode, label) in zip(columns[1:], _SUPPORTING_COUNT_LABELS):
        column.metric(label, counts[mode])


def render() -> None:
    snapshot = hydrate_workspace()
    if snapshot is None:
        guard("Create or open an assessment first.")
    st.title("Assessment Results")
    approved = st.session_state.get("approved_review")
    if approved is None:
        guard("Explicitly approve the human-reviewed process before assessment.")
    integrated = st.session_state.get("integrated_assessment_result")
    if integrated is None:
        st.write(
            "The approved current-state process is ready for deterministic "
            "AI-adoption assessment."
        )
        if not workspace_writes_available():
            st.info(
                "Assessment cannot be run because this is a frozen evaluation workspace."
            )
            return
        if st.button("Run AI-adoption assessment", type="primary"):
            try:
                with st.spinner("Running the deterministic AI-adoption assessment…"):
                    workspace_service().assess(snapshot.assessment.assessment_id)
                refresh_workspace()
                st.rerun()
            except Exception as exc:
                st.error(f"Assessment pipeline failed: {type(exc).__name__}")
        return
    if not isinstance(integrated, IntegratedAssessmentSuccess):
        st.error("The assessment pipeline could not complete.")
        for error in integrated.errors:
            st.error(f"{error.code.value}: {error.message}")
        return

    narrative = build_process_narrative(integrated)
    steps = integrated.process_assessment.step_assessments

    render_decision_header(
        context_line=f"Assessment complete · {narrative.process_name}",
        headline=narrative.headline,
        sections=(
            HeaderSection("What we found", narrative.what_we_found),
            HeaderSection(
                "What information is still needed", narrative.what_is_still_needed
            ),
            HeaderSection("What this means", narrative.what_this_means),
            HeaderSection("What happens next", narrative.next_action),
        ),
    )
    if st.button(
        "Open the Decision Package",
        key="results-open-decision-package",
        icon=":material/account_tree:",
    ):
        if not switch_to_registered_page("decision-package"):
            st.info("Open Decision Package from the sidebar to continue.")

    _render_supporting_counts(steps)

    st.subheader("Activity-by-activity results")
    for activity, step in zip(narrative.activities, steps, strict=True):
        _render_activity(integrated, activity, step)

    with technical_details():
        for line in narrative.policy_reference:
            st.caption(line)

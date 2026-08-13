"""Phase 5 assessment dashboard and explainable opportunity details."""

from collections import Counter

import streamlit as st

from ai_adoption_engine.models.enums import PriorityStatus, RecommendationMode
from ai_adoption_engine.models.integrated_assessment import IntegratedAssessmentSuccess
from ai_adoption_engine.presentation.components.status import guard
from ai_adoption_engine.presentation.context import (
    hydrate_workspace,
    refresh_workspace,
    workspace_service,
)


def _human_label(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()


def _render_detail(integrated: IntegratedAssessmentSuccess, step) -> None:
    st.header(step.activity)
    st.subheader(step.recommendation_mode.value.replace("_", " ").title())
    if step.priority_status is PriorityStatus.COMPLETE and step.priority:
        st.metric("Priority", f"{step.priority.score:.1f} · {step.priority.band.value}")
    elif step.priority_status is PriorityStatus.INCOMPLETE:
        st.warning(
            "Priority incomplete — missing: "
            + ", ".join(item.value for item in step.priority_missing_criteria)
        )
    else:
        st.caption("Priority not applicable to this recommendation.")
    if step.capabilities:
        st.write("**Mapped AI capabilities:** " + ", ".join(_human_label(item.value) for item in step.capabilities))
    else:
        st.caption("No AI capability proposed.")

    st.markdown("**Gate results**")
    for gate in step.gate_results:
        with st.container(border=True):
            st.write(f"{_human_label(gate.gate.value)} — {gate.status.value.replace('_', ' ')}")
            st.caption(gate.rationale)
            if gate.material_criteria:
                st.caption("Material criteria: " + ", ".join(item.value for item in gate.material_criteria))
    st.markdown("**Reasoning**")
    for reason in step.reasoning:
        st.write(f"- {reason}")

    unknown = [item for item in step.criteria if item.knowledge_state.value == "unknown"]
    if unknown:
        st.markdown("**Missing information**")
        for item in unknown:
            marker = "material" if item.material_to_recommendation or item.material_to_priority else "visible, non-material"
            st.write(f"- {_human_label(item.criterion.value)} — {marker}")

    trace = next(item for item in integrated.step_traceability if item.step_id == step.step_id)
    with st.expander("Evidence and provenance"):
        st.caption(
            f"Activity origin: {trace.activity.origin.value} · Review: {trace.activity.review_disposition.value}"
        )
        evidence_by_id = {item.evidence_id: item for item in step.evidence}
        for evidence in step.evidence:
            st.caption(f"{evidence.source_locator} · {evidence.evidence_id}")
            st.code(evidence.supporting_snippet, language=None, wrap_lines=True)
        for value_trace in [*trace.criteria, trace.human_accountability, *trace.capability_signals]:
            st.caption(
                f"{value_trace.review_field_path}: {value_trace.origin.value} / {value_trace.knowledge_state.value}"
            )
            for evidence in value_trace.evidence:
                resolved = evidence_by_id.get(evidence.evidence_id)
                if resolved:
                    st.code(resolved.supporting_snippet, language=None, wrap_lines=True)
                st.caption(f"{evidence.source_locator} · block {evidence.block_id}")


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
            "The approved current-state process is ready for deterministic AI-adoption assessment."
        )
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

    st.success(
        "Deterministic assessment completed. Investigate further and incomplete priority are valid decision-support outcomes, not system failures."
    )
    assessment = integrated.process_assessment
    steps = assessment.step_assessments
    counts = Counter(item.recommendation_mode for item in steps)
    st.subheader("Executive summary")
    top = st.columns(5)
    top[0].metric("Activities assessed", len(steps))
    top[1].metric("Automate", counts[RecommendationMode.AUTOMATE])
    top[2].metric("Augment", counts[RecommendationMode.AUGMENT])
    top[3].metric("Investigate", counts[RecommendationMode.INVESTIGATE_FURTHER])
    top[4].metric("Do not recommend", counts[RecommendationMode.DO_NOT_RECOMMEND])
    qualifying_complete = sum(
        item.recommendation_mode in {RecommendationMode.AUTOMATE, RecommendationMode.AUGMENT}
        and item.priority_status is PriorityStatus.COMPLETE
        for item in steps
    )
    material_gaps = sum(
        item.priority_status is PriorityStatus.INCOMPLETE
        or item.recommendation_mode is RecommendationMode.INVESTIGATE_FURTHER
        for item in steps
    )
    left, right = st.columns(2)
    left.metric("Qualifying opportunities with complete priority", qualifying_complete)
    right.metric("Activities with material information gaps", material_gaps)
    st.caption(
        f"Policy: {integrated.policy.policy_id} {integrated.policy.policy_version} ({integrated.policy.policy_status})"
    )

    st.subheader("Process opportunity portfolio")
    for item in steps:
        with st.container(border=True):
            columns = st.columns([5, 3, 2])
            columns[0].markdown(f"**{item.activity}**")
            columns[1].write(item.recommendation_mode.value.replace("_", " ").title())
            if item.priority:
                columns[2].write(f"{item.priority.score:.1f} · {item.priority.band.value}")
            else:
                columns[2].write(item.priority_status.value.title())

    labels = {f"{index + 1}. {item.activity}": item for index, item in enumerate(steps)}
    selected = st.selectbox("Opportunity detail", list(labels))
    _render_detail(integrated, labels[selected])

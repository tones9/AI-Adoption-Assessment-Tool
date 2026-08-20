"""One optional, non-decision Gap Resolution Workspace M1 page."""

from __future__ import annotations

import streamlit as st

from ai_adoption_engine.grw.models import GrwReviewDecision
from ai_adoption_engine.presentation.components.status import guard
from ai_adoption_engine.presentation.context import (
    hydrate_workspace,
    refresh_workspace,
    workspace_service,
)
from ai_adoption_engine.workspace.models import ArtifactType


_REVIEW_OPTIONS = {
    "Accept as preliminary understanding": GrwReviewDecision.ACCEPT_PRELIMINARY,
    "Accept as recorded only": GrwReviewDecision.ACCEPT_RECORDED_ONLY,
    "Reject": GrwReviewDecision.REJECT,
}


def _draft_key(assessment_id: str) -> str:
    return f"grw-m1-answer-{assessment_id}"


def _render_non_change_panel() -> None:
    st.subheader("Formal assessment effect")
    st.write("Criterion: unchanged")
    st.write("Assessment gates: unchanged")
    st.write("Recommendation: unchanged")
    st.write("Priority: unchanged")
    st.write("ROI: unchanged")
    st.write("Decision Package: unchanged")
    st.caption("No successor assessment or Decision Package was generated.")


def _baseline_recommendation(package_artifact, step_id: str) -> str:
    """Return the existing package recommendation for the selected M1 activity."""

    package = package_artifact.payload.package
    item = next(item for item in package.portfolio.items if item.step_id == step_id)
    return item.recommendation_mode.value.replace("_", " ").title()


def _render_evidence_escalation() -> None:
    st.info(
        "This information has not changed the formal assessment or recommendation. "
        "To strengthen the evidence basis, you could provide a relevant reviewed "
        "supporting document or a reproducible operational measure. That may support "
        "a future formal reassessment only if it is admissible under an approved "
        "evidence policy."
    )


def render() -> None:
    snapshot = hydrate_workspace()
    if snapshot is None:
        guard("Create or open an assessment first.")
    st.title("Gap resolution")
    package_artifact = snapshot.active_artifacts.get(ArtifactType.DECISION_PACKAGE_RESULT)
    if package_artifact is None:
        guard("Generate a Decision Package before opening optional Gap resolution.")

    status = workspace_service().load_grw_m1_status(snapshot.assessment.assessment_id)
    context = status.context
    if context is None:
        st.info("No optional M1 question is available for this Decision Package.")
        return

    st.info("Your current information is enough for an initial assessment.")
    st.write(
        "We identified additional information that could strengthen this decision. "
        "You may answer this question now or continue with the current recommendation."
    )
    st.caption(
        f"Baseline package: {context.baseline.package_id}. Nothing entered here changes "
        "the current assessment."
    )
    st.caption(
        "Baseline recommendation for this activity: "
        f"{_baseline_recommendation(package_artifact, context.gap.step_id)} "
        "(existing; unchanged by Gap resolution)."
    )
    if st.button("Continue with current recommendation", key="grw-m1-continue"):
        st.success("Your current Decision Package remains the formal recommendation.")

    if status.submission is None:
        with st.container(border=True):
            st.subheader("Strengthen one point")
            st.caption(context.gap.current_activity)
            st.write(context.question.why_it_matters)
            st.markdown(f"**{context.question.customer_question}**")
            st.caption(context.question.help_text)
            st.caption(
                "Please do not enter secrets, credentials, or unnecessary personal information."
            )
            with st.form("grw-m1-answer-form"):
                explicit_unknown = st.checkbox("I do not know", key="grw-m1-unknown")
                answer_text = st.text_area(
                    "Your answer",
                    key=_draft_key(snapshot.assessment.assessment_id),
                    max_chars=2000,
                    disabled=explicit_unknown,
                )
                submitted = st.form_submit_button("Submit answer", type="primary")
            if submitted:
                try:
                    workspace_service().submit_grw_m1_response(
                        snapshot.assessment.assessment_id,
                        baseline=context.baseline,
                        gap_id=context.gap.information_gap.gap_id,
                        answer_text=("I do not know." if explicit_unknown else answer_text),
                        explicit_unknown=explicit_unknown,
                    )
                    refresh_workspace()
                    st.rerun()
                except Exception as exc:
                    st.error(f"Answer submission could not be saved: {type(exc).__name__}")
        return

    with st.container(border=True):
        st.subheader("Submitted evidence")
        st.caption("Original decision limitation: workload evidence for this activity was unknown.")
        st.write("Question asked")
        st.write(status.submission.question.customer_question)
        st.write("Exact customer answer")
        st.text(status.submission.answer_text)
        st.caption(f"Provenance: {status.submission.evidence_class.value}")
        if status.submission.parsed_candidate is not None:
            st.warning(
                "Parsed range candidate only — it is non-authoritative and is not a criterion score."
            )
            st.json(status.submission.parsed_candidate.model_dump(mode="json"))
        st.info("This response is not measured or document-supported evidence.")

    if status.review is None:
        with st.container(border=True):
            st.subheader("Review evidence")
            st.caption(
                "This local M1 workspace does not verify role separation. If the same "
                "person supplied and reviews the answer, this is self-review."
            )
            with st.form("grw-m1-review-form"):
                reviewer_label = st.text_input("Reviewer label", max_chars=200)
                rationale = st.text_area("Review rationale", max_chars=2000)
                selected_label = st.selectbox("Review decision", list(_REVIEW_OPTIONS))
                reviewed = st.form_submit_button("Record review", type="primary")
            if reviewed:
                try:
                    workspace_service().review_grw_m1_submission(
                        snapshot.assessment.assessment_id,
                        submission_artifact_id=status.submission_artifact_id,
                        decision=_REVIEW_OPTIONS[selected_label],
                        reviewer_label=reviewer_label,
                        rationale=rationale,
                    )
                    refresh_workspace()
                    st.rerun()
                except Exception as exc:
                    st.error(f"Review could not be saved: {type(exc).__name__}")
        return

    with st.container(border=True):
        st.subheader("Evidence status")
        st.write(status.review.admissibility_effect.value)
        if status.review.decision is GrwReviewDecision.ACCEPT_PRELIMINARY:
            st.info(
                "This estimate provides preliminary understanding of workload. It is not "
                "formal criterion or gate evidence."
            )
        elif status.review.decision is GrwReviewDecision.ACCEPT_RECORDED_ONLY:
            st.info(
                "This answer is retained for audit and later discussion only. It is not an "
                "assessment input."
            )
        else:
            st.warning("The response was rejected and is not an assessment input.")
        st.caption(f"Review decision: {status.review.decision.value}")
        _render_evidence_escalation()
        _render_non_change_panel()

"""Preliminary context (GRW Milestone 1), told as a business page.

Milestone 1 is deliberately non-decision-affecting.  The page therefore leads
with that rule in plain English and keeps the formal six-part proof - criterion,
gates, recommendation, priority, ROI and Decision Package all unchanged - in the
canonical technical section, where it stays available in full.

Nothing here changes M1 semantics.  The question, the exact submitted answer,
the evidence class, the reviewer's decision and the admissibility effect are all
rendered from the persisted record; this module only chooses the order and the
words around them.
"""

from __future__ import annotations

import streamlit as st

from ai_adoption_engine.grw.models import GrwReviewDecision
from ai_adoption_engine.models.decision_support import DecisionPackageSuccess
from ai_adoption_engine.presentation import labels
from ai_adoption_engine.presentation.components.status import guard
from ai_adoption_engine.presentation.components.technical_details import (
    technical_details,
)
from ai_adoption_engine.presentation.context import (
    hydrate_workspace,
    refresh_workspace,
    switch_to_registered_page,
    workspace_service,
)
from ai_adoption_engine.presentation.decision_narrative import (
    build_package_narrative,
)
from ai_adoption_engine.workspace.models import ArtifactType
from ai_adoption_engine.presentation.components.page_header import (
    render_page_header,
)


_REVIEW_OPTIONS = {
    "Accept as preliminary understanding": GrwReviewDecision.ACCEPT_PRELIMINARY,
    "Accept as recorded only": GrwReviewDecision.ACCEPT_RECORDED_ONLY,
    "Reject": GrwReviewDecision.REJECT,
}

NO_DECISION_CHANGE = (
    "Adding this context does not change your current AI adoption decision."
)

PAGE_PURPOSE = (
    "One question was recorded as open when your decision was made. You can add "
    "background about it here so it sits alongside the decision. "
    "You may answer this question now or continue with the current recommendation."
)

PAGE_PURPOSE_ANSWERED = (
    "One question was recorded as open when your decision was made. You have "
    "added background about it here, and it now sits alongside the decision."
)

USE_OF_ANSWER = (
    "Your answer is kept exactly as you wrote it, together with how it was "
    "supplied and what a reviewer decided it may be used for. It is not "
    "document-supported or measured evidence, and it is not evidence for a "
    "formal reassessment."
)


def _draft_key(assessment_id: str) -> str:
    return f"grw-m1-answer-{assessment_id}"


def _render_non_change_panel() -> None:
    """The formal six-part effect, preserved verbatim as traceability."""

    st.markdown("**Formal assessment effect**")
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
    return labels.recommendation_label(item.recommendation_mode.value)


def _completeness_statement(package_artifact) -> str | None:
    """State what the package actually records, never a sufficiency judgement."""

    payload = package_artifact.payload
    if not isinstance(payload, DecisionPackageSuccess):
        return None
    return build_package_narrative(payload.package).completeness_statement


def _render_evidence_escalation() -> None:
    st.info(
        "This information has not changed the formal assessment or recommendation. "
        "To strengthen the evidence basis, you could provide a relevant reviewed "
        "supporting document or a reproducible operational measure. That may support "
        "a future formal reassessment only if it is admissible under an approved "
        "evidence policy."
    )


def _render_context_technical(context, package_artifact) -> None:
    st.caption(f"Baseline package ID: {context.baseline.package_id}")
    st.caption(f"Assessment: {context.baseline.assessment_id}")
    st.caption(f"Step ID: {context.gap.step_id}")
    st.caption(f"Information gap ID: {context.gap.information_gap.gap_id}")
    st.caption(f"Recorded field: {context.gap.information_gap.field_name}")
    st.caption(f"Question ID: {context.question.question_id}")
    st.caption(f"Question category: {context.question.priority_category}")
    st.caption(
        "Baseline recommendation for this activity: "
        + _baseline_recommendation(package_artifact, context.gap.step_id)
        + " (existing; unchanged by Gap resolution)"
    )


def _render_submission_technical(status) -> None:
    submission = status.submission
    st.caption(f"Submission ID: {submission.submission_id}")
    st.caption(f"Submission artifact: {status.submission_artifact_id}")
    st.caption(f"Submitted at: {submission.submitted_at.isoformat()}")
    st.caption(f"Evidence class: {submission.evidence_class.value}")
    st.caption(f"Submission status: {submission.status.value}")
    if submission.parsed_candidate is not None:
        st.caption(
            f"Parser: {submission.parsed_candidate.parser_version} · "
            f"status {submission.parsed_candidate.parse_status.value}"
        )
        st.json(submission.parsed_candidate.model_dump(mode="json"))


def _render_review_technical(status) -> None:
    review = status.review
    st.caption(f"Review ID: {review.review_id}")
    st.caption(f"Review artifact: {status.review_artifact_id}")
    st.caption(f"Reviewed at: {review.reviewed_at.isoformat()}")
    st.caption(f"Reviewer label: {review.reviewer_label}")
    st.caption(f"Review rationale: {review.rationale}")
    st.caption(f"Review decision: {review.decision.value}")
    st.caption(f"Admissibility effect: {review.admissibility_effect.value}")
    st.caption(f"Assessment effect: {review.assessment_effect}")
    st.caption(f"Reviewed submission SHA-256: {review.submission_payload_sha256}")
    proof = review.non_change_proof
    st.caption(
        f"Criterion snapshot: {proof.criterion.criterion_name} = "
        f"{proof.criterion.value} ({proof.criterion.knowledge_state.value})"
    )
    st.caption(f"Recommendation mode: {proof.recommendation_mode.value}")
    st.caption(f"Priority status: {proof.priority_status.value}")
    st.caption(f"ROI statement: {proof.roi_statement}")
    _render_non_change_panel()


def render() -> None:
    render_page_header("Add preliminary context")
    snapshot = hydrate_workspace()
    if snapshot is None:
        guard("Create or open an assessment first.")
    package_artifact = snapshot.active_artifacts.get(ArtifactType.DECISION_PACKAGE_RESULT)
    if package_artifact is None:
        guard("Generate a Decision Package before opening optional Gap resolution.")

    status = workspace_service().load_grw_m1_status(snapshot.assessment.assessment_id)
    context = status.context
    if context is None:
        st.info("No optional M1 question is available for this Decision Package.")
        return

    st.caption(f"Gap resolution · {context.gap.current_activity}")

    st.subheader("What this page is for")
    st.write(PAGE_PURPOSE if status.submission is None else PAGE_PURPOSE_ANSWERED)

    st.subheader("Your current decision does not change")
    st.warning(NO_DECISION_CHANGE, icon="ℹ️")
    st.write(
        "Decision recorded for this activity: "
        + _baseline_recommendation(package_artifact, context.gap.step_id)
        + ". Nothing on this page changes it."
    )
    completeness = _completeness_statement(package_artifact)
    if completeness:
        st.write(completeness)
    st.caption(
        "The full formal effect — criterion, assessment gates, recommendation, "
        "priority, ROI and Decision Package all unchanged — is recorded under "
        "the technical section on this page."
    )

    st.subheader("The question")
    st.write(context.question.why_it_matters)
    st.markdown(f"**{context.question.customer_question}**")
    st.caption(context.question.help_text)

    if status.submission is None:
        st.subheader("Your answer")
        st.caption(
            "Please do not enter secrets, credentials, or unnecessary personal "
            "information."
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
        st.caption(
            "Records your answer against this question. It does not change your "
            "current decision and it does not start a reassessment."
        )
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
        _render_footer(context, package_artifact, status)
        return

    st.subheader("What you submitted")
    with st.container(border=True):
        st.write("Question asked")
        st.write(status.submission.question.customer_question)
        st.write("Exact customer answer")
        st.text(status.submission.answer_text)
        st.caption(
            "How it was supplied: "
            + labels.evidence_class_label(status.submission.evidence_class.value)
        )
        if status.submission.parsed_candidate is not None:
            st.warning(
                "Parsed range candidate only — it is non-authoritative and is not a "
                "criterion score."
            )
        st.info("This response is not measured or document-supported evidence.")

    st.subheader("How this answer will be used")
    st.write(USE_OF_ANSWER)

    if status.review is None:
        st.subheader("Review")
        st.write(
            "A reviewer confirms what this answer may be used for. They cannot "
            "use it to change the decision."
        )
        with st.container(border=True):
            st.caption(
                "This local M1 workspace does not verify role separation. If the same "
                "person supplied and reviews the answer, this is self-review."
            )
            with st.form("grw-m1-review-form"):
                reviewer_label = st.text_input("Reviewer label", max_chars=200)
                rationale = st.text_area("Review rationale", max_chars=2000)
                selected_label = st.selectbox("Review decision", list(_REVIEW_OPTIONS))
                reviewed = st.form_submit_button("Record review", type="primary")
            st.caption(
                "Records the review decision against this answer. The current "
                "Decision Package stays exactly as it is."
            )
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
        _render_footer(context, package_artifact, status)
        return

    st.subheader("Review outcome")
    with st.container(border=True):
        st.write(
            "Reviewer's decision: "
            + labels.review_decision_label(status.review.decision.value)
        )
        st.write(
            "What this answer may be used for: "
            + labels.admissibility_effect_label(
                status.review.admissibility_effect.value
            )
        )
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

    st.subheader("What happens next")
    st.write(
        "Nothing further is required. Your Decision Package is unchanged and "
        "remains your official decision."
    )
    _render_evidence_escalation()
    _render_footer(context, package_artifact, status)


def _render_footer(context, package_artifact, status) -> None:
    """Navigation and the canonical technical section, in that order."""

    if st.button(
        "Return to decision continuation",
        key="grw-m1-return-dcw",
        icon=":material/arrow_back:",
    ):
        if not switch_to_registered_page("decision-continuation"):
            st.info("Open Decision continuation from the sidebar to return.")
    st.caption(
        "Goes back to the page listing your decision and its optional "
        "continuation routes. Nothing is submitted or discarded."
    )
    with technical_details():
        _render_context_technical(context, package_artifact)
        if status.submission is not None:
            _render_submission_technical(status)
        if status.review is not None:
            _render_review_technical(status)
        else:
            _render_non_change_panel()

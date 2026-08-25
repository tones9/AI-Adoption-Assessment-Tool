"""Package-centred, read-only navigation for existing GRW continuation paths."""

from __future__ import annotations

import streamlit as st

from ai_adoption_engine.application.decision_continuation import (
    DecisionContinuationBaseline,
    DecisionContinuationControlledReport,
    DecisionContinuationRun,
    DecisionContinuationView,
)
from ai_adoption_engine.models.decision_support import DecisionPackageSuccess
from ai_adoption_engine.persistence.base import PersistenceError
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
    decision_continuation_service,
    grw_continuation_available,
    hydrate_workspace,
    switch_to_registered_page,
)
from ai_adoption_engine.presentation.controlled_reassessment_report import (
    build_controlled_reassessment_narrative,
    render_controlled_reassessment_report_html,
)
from ai_adoption_engine.presentation.decision_narrative import (
    build_package_narrative,
)
from ai_adoption_engine.workspace.models import ArtifactType
from ai_adoption_engine.presentation.components.page_header import (
    render_page_header,
)


PAGE_PURPOSE = (
    "This page collects the optional ways to continue from the decision above, "
    "for when you want to record extra context or supply permitted new evidence."
)

NOTHING_REQUIRED = (
    "No. The decision above is complete and stays your official decision. You "
    "can act on it now and close this page."
)

CONTINUATION_IS_OPTIONAL = (
    "Everything on this page is optional. Nothing here replaces the decision "
    "above unless you complete the controlled reassessment route, and even then "
    "the decision above is kept unchanged alongside the new one."
)


def _package_from(snapshot):
    """Return the Decision Package artifact payload this workspace holds."""

    artifact = snapshot.active_artifacts.get(ArtifactType.DECISION_PACKAGE_RESULT)
    if artifact is None or not isinstance(artifact.payload, DecisionPackageSuccess):
        return None
    return artifact.payload.package


def _render_current_decision(package, *, purpose: str, requirement: str) -> None:
    """Lead with the decision itself, in the same words the package uses.

    The summary is the existing package narrative, so this page cannot describe
    the decision differently from the Decision Package that produced it.
    """

    narrative = build_package_narrative(package)
    render_decision_header(
        context_line=f"Current official decision · {narrative.process_name}",
        headline=narrative.headline,
        headline_heading="Your current official decision",
        headline_note=(
            "This is the decision produced from the evidence that has already "
            "been reviewed and approved. "
            + narrative.completeness_statement
        ),
        sections=(
            HeaderSection("What your decision covers", narrative.outcome_groups),
            HeaderSection("What this page is for", (purpose,)),
            HeaderSection("Do you need to do anything?", (requirement,)),
        ),
    )


def _render_baseline_technical(baseline: DecisionContinuationBaseline) -> None:
    with technical_details():
        st.markdown("**Baseline and lineage**")
        st.code(
            "\n".join(
                (
                    f"Assessment: {baseline.assessment_id}",
                    f"Baseline package ID: {baseline.package_id}",
                    f"Package completeness: {baseline.package_completeness}",
                    f"Decision Package artifact: {baseline.package.artifact_id} "
                    f"(revision {baseline.package.artifact_revision})",
                    f"Decision Package SHA-256: {baseline.package.payload_sha256}",
                    f"Approved review artifact: {baseline.approved_review.artifact_id} "
                    f"(revision {baseline.approved_review.artifact_revision})",
                    f"Approved review SHA-256: {baseline.approved_review.payload_sha256}",
                    f"Integrated assessment artifact: "
                    f"{baseline.integrated_assessment.artifact_id} "
                    f"(revision {baseline.integrated_assessment.artifact_revision})",
                    f"Integrated assessment SHA-256: "
                    f"{baseline.integrated_assessment.payload_sha256}",
                    f"Decision policy: {baseline.policy_id} {baseline.policy_version}",
                    f"Decision policy fingerprint: {baseline.policy_fingerprint}",
                )
            ),
            language=None,
        )
        st.markdown("**Recommendation records**")
        for recommendation in baseline.recommendations:
            st.caption(
                f"{recommendation.step_id}: {recommendation.current_activity} · "
                f"{recommendation.recommendation_mode}"
            )


def _render_protected_baseline(snapshot) -> None:
    package = _package_from(snapshot)
    if package is None:
        guard("Generate a Decision Package before continuing.")
    _render_current_decision(
        package,
        purpose=(
            "This workspace is a sealed evaluation record, so the optional "
            "continuation routes are switched off here."
        ),
        requirement=(
            "No. This decision is kept exactly as it was recorded and cannot be "
            "changed from this page."
        ),
    )
    with technical_details():
        st.markdown("**Baseline and lineage**")
        st.caption(f"Baseline package ID: {package.package_id}")
        st.caption(f"Package completeness: {package.completeness.value}")
        for item in package.portfolio.items:
            st.caption(
                f"{item.step_id}: {item.current_activity} · "
                f"{item.recommendation_mode.value}"
            )


def _m1_status_label(view: DecisionContinuationView) -> str:
    status = view.m1_status
    if status.submission is None:
        return "Optional question available"
    if status.review is None:
        return "Answer submitted — awaiting human review"
    return labels.human_label(status.review.admissibility_effect.value)


def _navigate_to_m1() -> None:
    st.session_state.dcw_return_page = "decision-continuation"
    if not switch_to_registered_page("gap-resolution"):
        st.info("Open Gap resolution from the sidebar to continue.")


def _navigate_to_m2(run_id: str | None = None) -> None:
    st.session_state.dcw_return_page = "decision-continuation"
    if run_id is not None:
        st.session_state.dcw_selected_m2_run_id = run_id
        st.session_state.grw_m2_run_id = run_id
    if not switch_to_registered_page("reassessment"):
        st.info("Open Reassessment from the sidebar to continue.")


def _render_keep_option() -> None:
    """Option A needs no action, so it is stated rather than made clickable."""

    with st.container(border=True):
        st.markdown("**Option A — Keep the current decision**")
        st.write(
            "You can stop here. Nothing else is required and nothing changes: the "
            "decision above remains your official decision."
        )
        st.caption("No action is needed to choose this option.")


def _render_m1_route(view: DecisionContinuationView) -> None:
    if view.m1_context is None:
        return
    with st.container(border=True):
        st.markdown("**Option B — Add preliminary context**")
        st.write(
            "Answer one optional question so the background to this activity is "
            "recorded alongside the decision."
        )
        st.warning(
            "This cannot change the decision above. It does not change the "
            "assessment criteria, the checks, the scores, the recommendation, the "
            "priority, or the Decision Package.",
            icon="ℹ️",
        )
        st.write(f"Activity: {view.m1_context.gap.current_activity}")
        st.write(view.m1_context.question.customer_question)
        st.caption(f"Status: {_m1_status_label(view)}")
        if st.button(
            "Add preliminary context",
            key="dcw-open-m1",
            icon=":material/help_center:",
        ):
            _navigate_to_m1()
        st.caption(
            "Opens the Gap resolution page, where you write the answer and a "
            "reviewer records what it may be used for."
        )


def _render_m2_route(view: DecisionContinuationView) -> None:
    if view.m2_discovery_error is not None:
        st.warning(view.m2_discovery_error)
        return
    if view.m2_context is None:
        st.info(
            "Option C — Controlled reassessment is not available for this "
            "decision. A controlled reassessment can only be started for a "
            "question the assessment has already recorded as open."
        )
        return
    _, gap = view.m2_context
    with st.container(border=True):
        st.markdown("**Option C — Controlled reassessment**")
        st.write(
            "Supply a supporting document about the data behind one activity, so "
            "the question the assessment left open can be answered."
        )
        st.write(f"Activity: {gap.current_activity}")
        st.write(
            "The question is: what information is documented about the data "
            "available for this activity?"
        )
        st.markdown("**What this route requires**")
        st.write(
            "- A reviewed supporting document\n"
            "- A reviewed resolution of the open question\n"
            "- Explicit approval to reassess"
        )
        st.markdown("**What it can produce**")
        st.write(
            "If all three are completed, a separate successor Decision Package is "
            "created next to the decision above. The decision above is not "
            "replaced and not edited."
        )
        st.caption(
            "Supplying more evidence does not guarantee a different "
            "recommendation. The route covers this one recorded question only."
        )
        if st.button(
            "Review controlled reassessment",
            key="dcw-open-m2",
            icon=":material/restart_alt:",
        ):
            _navigate_to_m2()
        st.caption(
            "Opens the Reassessment page, where the document, the review and the "
            "approval are recorded step by step."
        )


def _render_controlled_report(report: DecisionContinuationControlledReport) -> None:
    """Render the same projection the downloadable report uses."""

    narrative = build_controlled_reassessment_narrative(report)
    st.subheader("Controlled reassessment decision report")
    for line in narrative.purpose:
        st.write(line)

    with st.container(border=True):
        st.markdown("**Your original decision**")
        for line in narrative.original_decision:
            st.write(line)
    with st.container(border=True):
        st.markdown("**What additional evidence was approved**")
        for line in narrative.approved_evidence:
            st.write(line)
        st.code(narrative.evidence_excerpt, language=None)
    with st.container(border=True):
        st.markdown("**What changed in the assessment input**")
        for line in narrative.input_change:
            st.write(line)
    with st.container(border=True):
        st.markdown("**What did not change**")
        for line in narrative.unchanged:
            st.write(line)
    with st.container(border=True):
        st.markdown("**The separate reassessment decision**")
        for line in narrative.successor_decision:
            st.write(line)
    with st.container(border=True):
        st.markdown("**Original decision compared with the reassessment**")
        for line in narrative.comparison:
            st.write(line)
        st.markdown("**Assessment checks**")
        for line in narrative.gate_differences:
            st.write(line)
    with st.container(border=True):
        st.markdown("**Limitations**")
        for line in narrative.limitations:
            st.write(line)

    st.download_button(
        "Download controlled reassessment report",
        data=render_controlled_reassessment_report_html(report),
        file_name=f"controlled-reassessment-{report.run_id}.html",
        mime="text/html",
        key=f"dcw-download-controlled-report-{report.run_id}",
        icon=":material/download:",
    )
    st.caption(
        "Downloads this same report as a printable file. Nothing is changed by "
        "downloading it."
    )
    with technical_details():
        for line in narrative.technical:
            st.caption(line)


def _render_run_detail(
    run: DecisionContinuationRun, *, lifecycle_resumption_available: bool
) -> None:
    st.write(f"Activity: {run.gap.current_activity}")
    st.caption(f"Current step: {labels.m2_stage_label(run.stage.value)}")
    if run.successor is not None:
        st.write(
            "A separate reassessment was produced using additional approved "
            "evidence. Its recommendation for this activity is "
            f"{labels.recommendation_label(run.successor.target_recommendation)}."
        )
        st.caption(
            "This separate decision sits alongside your current official decision. "
            "It does not replace it and the decision above is unchanged."
        )
        if run.comparison is None:
            st.info(
                "A baseline-versus-successor comparison is not available for this "
                "separate successor. Its absence does not imply failure, success, "
                "or decision improvement."
            )
    if run.comparison is not None:
        st.write("How the two decisions compare")
        st.caption(run.comparison.neutral_explanation)
        st.write(
            "Your current official decision: "
            f"{labels.recommendation_label(run.comparison.baseline_recommendation)} · "
            "Separate reassessment: "
            f"{labels.recommendation_label(run.comparison.successor_recommendation)}"
        )
        st.caption(
            "A difference between the two is not a measured outcome, a Return on "
            "Investment (ROI) result, a deployment approval, or evidence that "
            "adoption succeeded."
        )
        with technical_details():
            st.caption(
                "Comparison categories: "
                + ", ".join(run.comparison.categories)
            )
            st.caption(f"Comparison artifact: {run.comparison.artifact.artifact_id}")
    if run.controlled_report is not None:
        _render_controlled_report(run.controlled_report)
    with technical_details():
        st.caption(
            f"Separate reassessment run: {run.run_id} · state: {run.stage.value}"
        )
        st.caption(f"Opened: {run.created_at} · Updated: {run.updated_at}")
        st.caption(f"Field: {run.gap.information_gap.field_name}")
        st.caption(f"Baseline package ID: {run.baseline.package_id}")
        if run.successor is not None:
            st.caption(f"Successor package ID: {run.successor.package_id}")
            st.caption(
                "Successor artifact: "
                f"{run.successor.package_artifact.artifact_id}"
            )
    if run.is_terminal:
        st.info(
            "This reassessment record is complete or stopped and is available for "
            "inspection only."
        )
        return
    if not lifecycle_resumption_available:
        st.info(
            "This reassessment record is available for inspection, but current "
            "conditions do not permit lifecycle continuation."
        )
        return
    if st.button(
        "Resume controlled reassessment",
        key=f"dcw-resume-{run.run_id}",
        icon=":material/play_arrow:",
    ):
        _navigate_to_m2(run.run_id)
    st.caption(
        "Opens the Reassessment page at the step this record reached. Your "
        "current official decision stays unchanged while it is in progress."
    )


def _render_m2_records(view: DecisionContinuationView) -> None:
    if not view.m2_runs:
        return
    st.subheader("Previous reassessments")
    if view.m2_context is None:
        st.info(
            "Existing reassessment records remain available for inspection, but "
            "a new controlled reassessment cannot be continued at the moment."
        )
    labelled = {
        run.run_id: f"Reassessment {index} — {labels.m2_stage_label(run.stage.value)}"
        for index, run in enumerate(view.m2_runs, start=1)
    }
    valid_ids = list(labelled)
    if st.session_state.get("dcw_selected_m2_run_id") not in valid_ids:
        st.session_state.pop("dcw_selected_m2_run_id", None)
    selected = st.selectbox(
        "Select a reassessment record to inspect",
        valid_ids,
        key="dcw_selected_m2_run_id",
        format_func=lambda run_id: labelled[run_id],
    )
    _render_run_detail(
        next(run for run in view.m2_runs if run.run_id == selected),
        lifecycle_resumption_available=view.m2_context is not None,
    )


def render() -> None:
    render_page_header("Decision continuation")
    snapshot = hydrate_workspace()
    if snapshot is None:
        guard("Create or open an assessment first.")
    if not grw_continuation_available():
        _render_protected_baseline(snapshot)
        return
    try:
        view = decision_continuation_service().open(snapshot.assessment.assessment_id)
    except (PersistenceError, ValueError) as exc:
        st.error(f"Decision continuation could not be opened: {type(exc).__name__}")
        return
    package = _package_from(snapshot)
    if package is None or package.package_id != view.baseline.package_id:
        guard("Generate a Decision Package before continuing.")
    _render_current_decision(
        package, purpose=PAGE_PURPOSE, requirement=NOTHING_REQUIRED
    )
    st.subheader("Your options")
    st.caption(CONTINUATION_IS_OPTIONAL)
    _render_keep_option()
    _render_m1_route(view)
    _render_m2_route(view)
    _render_m2_records(view)
    _render_baseline_technical(view.baseline)

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
from ai_adoption_engine.presentation.components.status import guard
from ai_adoption_engine.presentation.context import (
    decision_continuation_service,
    grw_continuation_available,
    hydrate_workspace,
    switch_to_registered_page,
)
from ai_adoption_engine.presentation.controlled_reassessment_report import (
    render_controlled_reassessment_report_html,
)
from ai_adoption_engine.workspace.models import ArtifactType


def _human(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()


def _criterion_value(value: int | None, knowledge_state: str) -> str:
    rendered = "Unknown" if value is None else str(value)
    return f"{rendered} ({_human(knowledge_state)})"


def _render_baseline(baseline: DecisionContinuationBaseline) -> None:
    st.subheader("Current formal decision")
    st.info(
        "This Decision Package is the active formal baseline. You can continue with "
        "its recommendation now; optional evidence paths do not replace it automatically."
    )
    st.caption(
        f"Active baseline package: {baseline.package_id} · "
        f"{_human(baseline.package_completeness)}"
    )
    with st.container(border=True):
        for recommendation in baseline.recommendations:
            st.markdown(
                f"**{recommendation.current_activity}** — "
                f"{_human(recommendation.recommendation_mode)}"
            )
            st.caption(recommendation.rationale)
    if st.button(
        "Continue with current recommendation",
        key="dcw-continue-baseline",
        icon=":material/arrow_forward:",
    ):
        st.success("The active baseline Decision Package remains the formal recommendation.")
    with st.expander("Technical traceability"):
        st.code(
            "\n".join(
                (
                    f"Assessment: {baseline.assessment_id}",
                    f"Decision Package artifact: {baseline.package.artifact_id} "
                    f"(revision {baseline.package.artifact_revision})",
                    f"Decision Package SHA-256: {baseline.package.payload_sha256}",
                    f"Approved review artifact: {baseline.approved_review.artifact_id}",
                    f"Integrated assessment artifact: {baseline.integrated_assessment.artifact_id}",
                    f"Decision policy: {baseline.policy_id} {baseline.policy_version}",
                    f"Decision policy fingerprint: {baseline.policy_fingerprint}",
                )
            ),
            language=None,
        )


def _render_protected_baseline(snapshot) -> None:
    artifact = snapshot.active_artifacts.get(ArtifactType.DECISION_PACKAGE_RESULT)
    if artifact is None or not isinstance(artifact.payload, DecisionPackageSuccess):
        guard("Generate a Decision Package before continuing.")
    package = artifact.payload.package
    st.subheader("Current formal decision")
    st.info(
        "This Decision Package is an immutable evaluation baseline. Optional GRW "
        "continuation is unavailable for protected evaluation workspaces."
    )
    st.caption(f"Baseline package: {package.package_id} · {_human(package.completeness.value)}")
    with st.container(border=True):
        for item in package.portfolio.items:
            st.markdown(
                f"**{item.current_activity}** — {_human(item.recommendation_mode.value)}"
            )
            st.caption(item.rationale)


def _m1_status_label(view: DecisionContinuationView) -> str:
    status = view.m1_status
    if status.submission is None:
        return "Optional question available"
    if status.review is None:
        return "Answer submitted — awaiting human review"
    return _human(status.review.admissibility_effect.value)


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


def _render_m1_route(view: DecisionContinuationView) -> None:
    if view.m1_context is None:
        return
    with st.container(border=True):
        st.subheader("Improve preliminary understanding")
        st.caption("Optional context only — no formal decision change")
        st.write(view.m1_context.gap.current_activity)
        st.write(view.m1_context.question.customer_question)
        st.caption(f"Status: {_m1_status_label(view)}")
        if st.button(
            "Open optional question",
            key="dcw-open-m1",
            icon=":material/help_center:",
        ):
            _navigate_to_m1()


def _render_m2_route(view: DecisionContinuationView) -> None:
    if view.m2_discovery_error is not None:
        st.warning(view.m2_discovery_error)
        return
    if view.m2_context is None:
        st.info("No controlled data-readiness reassessment route is currently available.")
        return
    _, gap = view.m2_context
    with st.container(border=True):
        st.subheader("Controlled formal reassessment")
        st.caption(
            "Reviewed supporting document, reviewed data-readiness resolution, and "
            "explicit reassessment approval are required."
        )
        st.write(gap.current_activity)
        st.write(
            "What information is documented about the data available for this activity?"
        )
        st.caption(
            "This is the existing M2 M1 data-readiness route. It is not a new gap ranking."
        )
        if st.button(
            "Open controlled reassessment",
            key="dcw-open-m2",
            icon=":material/restart_alt:",
        ):
            _navigate_to_m2()


def _render_controlled_report(report: DecisionContinuationControlledReport) -> None:
    st.subheader("Controlled reassessment decision report")
    st.caption(
        "A read-only projection of the original baseline, approved evidence, and "
        "separate successor decision."
    )
    with st.container(border=True):
        st.markdown("**1. Original baseline decision**")
        st.write(f"Baseline package: {report.baseline_package_id}")
        st.write(
            "Data-readiness value: "
            + _criterion_value(
                report.baseline_value, report.baseline_knowledge_state
            )
        )
        st.write(f"Recommendation: {_human(report.baseline_recommendation)}")
        for rationale in report.baseline_rationale:
            st.caption(rationale)
        st.info(
            "The original baseline Decision Package remains unchanged and is not "
            "overwritten by this successor."
        )
    with st.container(border=True):
        st.markdown("**2. Approved controlled change**")
        st.write(f"Approved reason: {report.approved_change.approval_reason}")
        st.write(f"Exact approved change: {report.approved_change.exact_change}")
        st.write(f"Mapping rationale: {report.approved_change.mapping_rationale}")
        st.write(
            f"Retained uncertainty: {report.approved_change.retained_uncertainty}"
        )
    with st.container(border=True):
        st.markdown("**3. Approved evidence basis**")
        st.write(
            f"Document: {report.evidence.filename} · Source: "
            f"{report.evidence.source_label}"
        )
        st.caption(f"Document SHA-256: {report.evidence.content_sha256}")
        st.caption(
            f"Locator: lines {report.evidence.line_start}-{report.evidence.line_end}; "
            f"characters {report.evidence.start_offset}-{report.evidence.end_offset}"
        )
        st.code(report.evidence.exact_excerpt, language=None)
        st.write(f"Source authority: {report.evidence.source_authority}")
        st.write(f"Scope: {report.evidence.scope_statement}")
        st.write(f"Period or limitation: {report.evidence.period_statement}")
        st.write(f"Evidence-review rationale: {report.evidence.semantic_rationale}")
        st.write(f"Limitations retained: {report.evidence.limitations}")
        st.write(f"Conflict status: {_human(report.evidence.conflict_status)}")
        st.caption(report.evidence.conflict_rationale)
        if report.evidence.reconciliation_statement:
            st.write(f"Reconciliation: {report.evidence.reconciliation_statement}")
        if report.evidence.applicability_statement:
            st.write(f"Applicability: {report.evidence.applicability_statement}")
    with st.container(border=True):
        st.markdown("**4. Separate successor comparison**")
        st.write(f"Successor package: {report.successor_package_id}")
        st.write(
            "Data-readiness value: "
            + _criterion_value(
                report.successor_value, report.successor_knowledge_state
            )
        )
        st.write(f"Recommendation: {_human(report.successor_recommendation)}")
        for rationale in report.successor_rationale:
            st.caption(rationale)
        st.markdown("**Relevant gate differences**")
        if not report.gate_differences:
            st.caption("No gate difference was recorded.")
        for gate in report.gate_differences:
            st.write(
                f"{_human(gate.gate)}: "
                f"{_human(gate.baseline_status or 'not-present')} → "
                f"{_human(gate.successor_status or 'not-present')}"
            )
            if gate.baseline_rationale:
                st.caption(f"Baseline: {gate.baseline_rationale}")
            if gate.successor_rationale:
                st.caption(f"Successor: {gate.successor_rationale}")
        st.caption(
            "Categories: "
            + ", ".join(_human(item) for item in report.comparison_categories)
        )
        st.info(report.neutral_explanation)
        st.caption(
            "Recommendation movement is not a measured outcome, ROI result, "
            "deployment approval, or evidence of adoption success."
        )
    html_report = render_controlled_reassessment_report_html(report)
    st.download_button(
        "Download controlled reassessment report",
        data=html_report,
        file_name=f"controlled-reassessment-{report.run_id}.html",
        mime="text/html",
        key=f"dcw-download-controlled-report-{report.run_id}",
        icon=":material/download:",
    )
    with st.expander("Technical lineage appendix"):
        st.code(
            "\n".join(
                f"{item.label}: {item.artifact_id} "
                f"(revision {item.artifact_revision})\nSHA-256: {item.payload_sha256}"
                for item in report.lineage
            ),
            language=None,
        )
        st.code(
            f"Changed field: {report.approved_change.changed_field_path}\n"
            f"Supporting document: {report.evidence.document_id}",
            language=None,
        )


def _render_run_detail(
    run: DecisionContinuationRun, *, lifecycle_resumption_available: bool
) -> None:
    st.caption(
        f"Separate reassessment run: {run.run_id} · state: {_human(run.stage.value)}"
    )
    st.write(f"Activity: {run.gap.current_activity}")
    st.caption(f"Field: {run.gap.information_gap.field_name}")
    if run.successor is not None:
        st.write(
            f"Separate M2 successor for run {run.run_id}: "
            f"{run.successor.package_id} — "
            f"{_human(run.successor.target_recommendation)}"
        )
        st.caption(
            "This successor is separate from the active formal baseline and does not "
            "replace it."
        )
        if run.comparison is None:
            st.info(
                "A baseline-versus-successor comparison is not available for this "
                "separate successor. Its absence does not imply failure, success, "
                "or decision improvement."
            )
    if run.comparison is not None:
        st.write("Recorded baseline-versus-successor comparison")
        st.caption(run.comparison.neutral_explanation)
        st.write(
            f"Baseline: {_human(run.comparison.baseline_recommendation)} · "
            f"Successor: {_human(run.comparison.successor_recommendation)}"
        )
        st.caption("Categories: " + ", ".join(_human(item) for item in run.comparison.categories))
        st.caption(
            "A recommendation movement is not a measured outcome, ROI result, deployment "
            "approval, or adoption success."
        )
    if run.controlled_report is not None:
        _render_controlled_report(run.controlled_report)
    if run.is_terminal:
        st.info("This reassessment record is complete or stopped and is available for inspection only.")
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


def _render_m2_records(view: DecisionContinuationView) -> None:
    st.subheader("Separate reassessment records")
    if not view.m2_runs:
        st.caption("No persisted reassessment record is attached to this exact active baseline.")
        return
    if view.m2_context is None:
        st.info(
            "Existing reassessment records remain available for inspection, but "
            "current conditions do not permit controlled reassessment continuation."
        )
    valid_ids = [run.run_id for run in view.m2_runs]
    if st.session_state.get("dcw_selected_m2_run_id") not in valid_ids:
        st.session_state.pop("dcw_selected_m2_run_id", None)
    selected = st.selectbox(
        "Select reassessment record",
        valid_ids,
        key="dcw_selected_m2_run_id",
        format_func=lambda run_id: next(
            f"{run_id} — {_human(run.stage.value)}"
            for run in view.m2_runs
            if run.run_id == run_id
        ),
    )
    _render_run_detail(
        next(run for run in view.m2_runs if run.run_id == selected),
        lifecycle_resumption_available=view.m2_context is not None,
    )


def render() -> None:
    snapshot = hydrate_workspace()
    if snapshot is None:
        guard("Create or open an assessment first.")
    st.title("Decision continuation")
    if not grw_continuation_available():
        _render_protected_baseline(snapshot)
        return
    try:
        view = decision_continuation_service().open(snapshot.assessment.assessment_id)
    except (PersistenceError, ValueError) as exc:
        st.error(f"Decision continuation could not be opened: {type(exc).__name__}")
        return
    _render_baseline(view.baseline)
    st.subheader("Optional next actions")
    _render_m1_route(view)
    _render_m2_route(view)
    _render_m2_records(view)

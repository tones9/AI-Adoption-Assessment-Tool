"""Phase 6 future state, roadmap, governance and report rendering."""

import streamlit as st

from ai_adoption_engine.models.decision_support import DecisionPackageSuccess
from ai_adoption_engine.presentation.components.process_flow import render_future_state
from ai_adoption_engine.presentation.components.status import guard
from ai_adoption_engine.presentation.context import (
    hydrate_workspace,
    refresh_workspace,
    workspace_service,
)
from ai_adoption_engine.presentation.report_html import render_report_html


def _human(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()


def render() -> None:
    snapshot = hydrate_workspace()
    if snapshot is None:
        guard("Create or open an assessment first.")
    st.title("Decision Package")
    integrated = st.session_state.get("integrated_assessment_result")
    if integrated is None or getattr(integrated, "status", None) != "success":
        guard("Complete a successful integrated assessment before generating decision support.")
    generated = st.session_state.get("decision_package_result")
    if generated is None:
        st.write(
            "Generate the deterministic business-facing portfolio, future state, roadmap, governance summary and report."
        )
        if st.button("Generate decision package", type="primary"):
            try:
                with st.spinner("Generating the decision-support package…"):
                    workspace_service().generate_package(
                        snapshot.assessment.assessment_id
                    )
                refresh_workspace()
                st.rerun()
            except Exception as exc:
                st.error(f"Decision-package generation failed: {type(exc).__name__}")
        return
    if not isinstance(generated, DecisionPackageSuccess):
        st.error("Decision-package generation could not complete.")
        for error in generated.errors:
            st.error(f"{error.code.value}: {error.message}")
        return
    package = generated.package
    st.success("Decision package generated from the saved assessment result.")
    st.caption(
        f"Package {package.package_id} · {package.completeness.value} · "
        f"Policy {package.source.policy.policy_id} {package.source.policy.policy_version}"
    )
    tabs = st.tabs(["Future state", "Roadmap", "Risk & governance", "Report"])
    with tabs[0]:
        render_future_state(package.future_state)
        st.caption(
            "The approved current-state process remains separate and unchanged. "
            "This is planning guidance, not evidence of deployment."
        )
    with tabs[1]:
        for opportunity in package.roadmap.opportunities:
            with st.expander(
                f"{opportunity.step_id} — {_human(opportunity.recommendation_mode.value)}",
                expanded=bool(opportunity.stages),
            ):
                st.write(_human(opportunity.status.value))
                st.caption(opportunity.rationale)
                if not opportunity.stages:
                    st.info("AI deployment roadmap not applicable.")
                for stage in opportunity.stages:
                    with st.container(border=True):
                        st.markdown(f"**{stage.sequence}. {_human(stage.stage_type.value)}**")
                        st.write(stage.objective)
                        if stage.decision_point:
                            st.warning("Decision gate: " + " / ".join(stage.possible_outcomes))
    with tabs[2]:
        if not package.governance.considerations:
            st.caption("No additional structured governance considerations were generated.")
        for item in package.governance.considerations:
            with st.container(border=True):
                st.markdown(f"**{_human(item.category.value)}**")
                st.write(item.statement)
                st.caption(
                    f"Step {item.step_id} · "
                    f"{'Requires organisational review' if item.requires_review else 'Review not flagged'} · "
                    f"Origin {item.basis.origin.value}"
                )
        st.info(
            "This summary does not claim legal compliance, security approval, ethical acceptability or deployment readiness."
        )
    with tabs[3]:
        st.warning(package.future_state.status.value)
        st.info(package.roi_statement)
        for section in package.report_content.sections:
            st.subheader(section.title)
            for statement in section.statements:
                st.write(statement.text)
                st.caption(
                    f"Origin: {statement.origin.value}"
                    + (f" · Steps: {', '.join(statement.step_ids)}" if statement.step_ids else "")
                )
        st.subheader("Methodology disclosure")
        for disclosure in package.methodology.disclosure_statements:
            st.write(f"- {disclosure}")
        html_report = render_report_html(package)
        st.download_button(
            "Download print-friendly HTML report",
            data=html_report,
            file_name=f"ai-adoption-report-{package.current_state.process_id}.html",
            mime="text/html",
        )
        with st.expander("Reproducibility references"):
            st.code(
                "\n".join(
                    [
                        f"Validated process fingerprint: {package.source.lineage.validated_process_fingerprint}",
                        f"Decision policy fingerprint: {package.source.policy.decision_policy_fingerprint}",
                        f"Assessment run: {package.source.integrated_assessment_run_id}",
                    ]
                ),
                language=None,
            )

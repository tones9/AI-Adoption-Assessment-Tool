"""The Decision Package as the delivered business decision.

Layer 1 - what was decided, why, what it means, what happens next and the
limitations - comes from ``decision_narrative``.  The decision report is the
substance of the deliverable and is rendered directly beneath it; future state,
roadmap and governance remain available as supporting sections.  Identifiers,
fingerprints, planning-origin tokens and provenance are preserved behind the
canonical ``Technical reasoning and evidence`` control.

This page composes and renders.  It never interprets an assessment.  See
``docs/portfolio-v1-decision-experience-design-v0.1.md``.
"""

import streamlit as st

from ai_adoption_engine.models.decision_support import (
    DecisionPackageSuccess,
    ReportSectionId,
)
from ai_adoption_engine.presentation import labels
from ai_adoption_engine.presentation.components.decision_header import (
    HeaderSection,
    render_decision_header,
)
from ai_adoption_engine.presentation.components.process_flow import render_future_state
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
    build_package_narrative,
)
from ai_adoption_engine.presentation.report_html import render_report_html
from ai_adoption_engine.presentation.report_view import build_report_view


_BORDERED_REPORT_SECTIONS = frozenset(
    {
        ReportSectionId.OPPORTUNITY_PORTFOLIO,
        ReportSectionId.RISKS_GOVERNANCE,
        ReportSectionId.ADOPTION_ROADMAP,
        ReportSectionId.MISSING_INFORMATION,
        ReportSectionId.EVIDENCE_APPENDIX,
    }
)


def _render_report(package) -> None:
    """Render the deterministic report projection without altering it."""

    for section in build_report_view(package):
        st.subheader(section.title)
        for block in section.blocks:
            with st.container(
                border=section.section_id in _BORDERED_REPORT_SECTIONS
            ):
                if block.heading:
                    st.markdown(f"**{block.heading}**")
                for paragraph in block.paragraphs:
                    st.write(paragraph)
                for bullet in block.bullets:
                    st.write(f"- {bullet}")
                if block.origin or block.technical_details:
                    with technical_details():
                        if block.origin:
                            st.caption(f"Origin: {block.origin.value}")
                        for detail in block.technical_details:
                            st.code(detail, language=None)


def _render_roadmap(package) -> None:
    activity_by_id = {
        item.step_id: item.current_activity for item in package.portfolio.items
    }
    for opportunity in package.roadmap.opportunities:
        with st.expander(
            f"{activity_by_id[opportunity.step_id]} — "
            f"{labels.recommendation_label(opportunity.recommendation_mode.value)}",
            expanded=bool(opportunity.stages),
        ):
            st.write(labels.roadmap_status_label(opportunity.status.value))
            st.caption(opportunity.rationale)
            if not opportunity.stages:
                st.info("AI deployment roadmap not applicable.")
            for stage in opportunity.stages:
                with st.container(border=True):
                    st.markdown(
                        f"**{stage.sequence}. {labels.human_label(stage.stage_type.value)}**"
                    )
                    st.write(stage.objective)
                    if stage.decision_point:
                        st.warning(
                            "Decision gate: " + " / ".join(stage.possible_outcomes)
                        )


def _render_governance(package) -> None:
    if not package.governance.considerations:
        st.caption("No additional structured governance considerations were generated.")
    for item in package.governance.considerations:
        with st.container(border=True):
            st.markdown(f"**{labels.human_label(item.category.value)}**")
            st.write(item.statement)
            st.caption(
                "Requires organisational review"
                if item.requires_review
                else "Review not flagged"
            )
            with technical_details():
                st.caption(
                    f"Step {item.step_id} · Origin {item.basis.origin.value}"
                )
    st.info(
        "This summary does not claim legal compliance, security approval, "
        "ethical acceptability or deployment readiness."
    )


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
            "Generate the deterministic business-facing portfolio, future state, "
            "roadmap, governance summary and report."
        )
        if not workspace_writes_available():
            st.info(
                "A decision package cannot be generated because this is a frozen "
                "evaluation workspace."
            )
            return
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
    narrative = build_package_narrative(package)

    render_decision_header(
        context_line=f"Decision Package · {narrative.process_name}",
        headline=narrative.headline,
        headline_heading="Decision summary",
        headline_note=narrative.completeness_statement,
        sections=(
            HeaderSection("Why this decision was reached", narrative.why),
            HeaderSection("What this means", narrative.what_this_means),
            HeaderSection("What happens next", narrative.next_action),
            HeaderSection("Risks and limitations", narrative.limitations),
        ),
    )

    if st.button(
        "Review optional evidence-continuation paths",
        key="decision-package-continue",
        icon=":material/route:",
    ):
        if not switch_to_registered_page("decision-continuation"):
            st.info("Open Decision continuation from the sidebar to continue.")

    st.subheader("Supporting decision detail")
    st.caption(
        "The decision report below is the full record of this decision. Future "
        "state, roadmap and governance detail support it."
    )
    _render_report(package)
    st.download_button(
        "Download print-friendly HTML report",
        data=render_report_html(package),
        file_name=f"ai-adoption-report-{package.current_state.process_id}.html",
        mime="text/html",
    )

    tabs = st.tabs(["Future state", "Roadmap", "Risk & governance"])
    with tabs[0]:
        render_future_state(package.future_state)
        st.caption(
            "The approved current-state process remains separate and unchanged. "
            "This is planning guidance, not evidence of deployment."
        )
    with tabs[1]:
        _render_roadmap(package)
    with tabs[2]:
        _render_governance(package)

    with technical_details():
        for line in narrative.technical_reference:
            st.caption(line)
        st.markdown("**Methodology disclosures**")
        for statement in package.methodology.disclosure_statements:
            st.caption(statement)

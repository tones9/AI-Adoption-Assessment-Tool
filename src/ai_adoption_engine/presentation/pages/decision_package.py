"""The Decision Package as a compact, navigable business deliverable.

The immutable Phase 6 package and its deterministic narrative/report projections
remain the only sources of content. This page changes only presentation: the
previous single long document is grouped into six selectable sections, and all
technical values for a section share one canonical disclosure.
"""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

from ai_adoption_engine.models.decision_support import (
    DecisionPackageSuccess,
    ReportSectionId,
)
from ai_adoption_engine.models.enums import RecommendationMode
from ai_adoption_engine.presentation import labels
from ai_adoption_engine.presentation.components.decision_header import (
    HeaderSection,
    render_decision_header,
)
from ai_adoption_engine.presentation.components.page_header import render_page_header
from ai_adoption_engine.presentation.components.primitives import (
    render_badge,
    render_business_list,
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
from ai_adoption_engine.presentation.decision_narrative import build_package_narrative
from ai_adoption_engine.presentation.report_html import render_report_html
from ai_adoption_engine.presentation.report_view import build_report_view


SUMMARY = "Summary"
OPPORTUNITY_PORTFOLIO = "AI opportunity portfolio"
FUTURE_STATE = "Future-state workflow"
ROADMAP = "Roadmap"
RISKS_GOVERNANCE = "Risks & governance"
EVIDENCE_APPENDIX = "Evidence appendix"

PACKAGE_SECTIONS = (
    SUMMARY,
    OPPORTUNITY_PORTFOLIO,
    FUTURE_STATE,
    ROADMAP,
    RISKS_GOVERNANCE,
    EVIDENCE_APPENDIX,
)

_REPORT_GROUPS = {
    SUMMARY: (
        ReportSectionId.EXECUTIVE_SUMMARY,
        ReportSectionId.PROCESS_ASSESSED,
        ReportSectionId.MISSING_INFORMATION,
    ),
    OPPORTUNITY_PORTFOLIO: (
        ReportSectionId.OPPORTUNITY_PORTFOLIO,
        ReportSectionId.HIGHEST_PRIORITY,
        ReportSectionId.REQUIRES_INVESTIGATION,
        ReportSectionId.NOT_RECOMMENDED,
    ),
    FUTURE_STATE: (
        ReportSectionId.FUTURE_STATE,
        ReportSectionId.HUMAN_ROLES,
    ),
    ROADMAP: (ReportSectionId.ADOPTION_ROADMAP,),
    RISKS_GOVERNANCE: (ReportSectionId.RISKS_GOVERNANCE,),
    EVIDENCE_APPENDIX: (
        ReportSectionId.METHODOLOGY,
        ReportSectionId.EVIDENCE_APPENDIX,
    ),
}

# The selector remains a native widget for keyboard, focus and state behavior.
# Only its keyed wrapper is sticky; on narrow screens the six native controls
# scroll horizontally instead of wrapping or overflowing the viewport.
_SECTION_NAV_STYLES = """
<style>
[data-testid="stLayoutWrapper"]:has(> .st-key-decision-package-section-nav) {
  position: sticky;
  top: 0;
  z-index: 50;
  background: var(--aae-bg);
  border-bottom: 1px solid var(--aae-hairline);
  padding: 8px 0 10px;
  margin-bottom: 16px;
}
.st-key-decision-package-section-nav { position: static; }
.st-key-decision-package-section-nav [data-testid="stButtonGroup"] {
  display: flex;
  flex-wrap: nowrap;
  max-width: 100%;
}
.st-key-decision-package-section-nav [role="radiogroup"] {
  flex-wrap: nowrap;
  max-width: 100%;
  overflow-x: auto;
  scrollbar-width: thin;
}
.st-key-decision-package-section-nav [data-testid="stButtonGroup"] button {
  flex: 0 0 auto;
  white-space: nowrap;
}
</style>
"""


def _report_groups(package):
    sections = {
        section.section_id: section for section in build_report_view(package)
    }
    return {
        group: tuple(sections[section_id] for section_id in section_ids)
        for group, section_ids in _REPORT_GROUPS.items()
    }


def _render_block(block, *, show_heading: bool = True) -> None:
    if show_heading and block.heading:
        st.markdown(f"**{block.heading}**")
    for paragraph in block.paragraphs:
        st.write(paragraph)
    render_business_list(block.bullets, boxed=False)


def _render_report_section(section, *, collapse_records: bool = False) -> None:
    st.subheader(section.title)
    if collapse_records:
        for index, block in enumerate(section.blocks, start=1):
            label = block.heading or f"{section.title} · detail {index}"
            with st.expander(label):
                _render_block(block, show_heading=False)
        return
    for block in section.blocks:
        with st.container(border=True):
            _render_block(block)


def _render_report_section_in_one_expander(section, *, label: str) -> None:
    with st.expander(label):
        for block in section.blocks:
            _render_block(block)


def _render_section_technical(
    sections,
    *,
    extra_groups: Sequence[tuple[str, Sequence[str]]] = (),
) -> None:
    """Render one disclosure containing every technical value in a section."""

    with technical_details():
        for section in sections:
            technical_blocks = [
                block
                for block in section.blocks
                if block.origin or block.technical_details
            ]
            if not technical_blocks:
                continue
            st.markdown(f"**{section.title}**")
            for block in technical_blocks:
                if block.heading:
                    st.caption(block.heading)
                if block.origin:
                    st.caption(f"Origin: {block.origin.value}")
                for detail in block.technical_details:
                    st.code(detail, language=None)
        for heading, lines in extra_groups:
            if not lines:
                continue
            st.markdown(f"**{heading}**")
            for line in lines:
                st.caption(line)


def _recommendation_tone(mode: RecommendationMode) -> str:
    return (
        "primary"
        if mode in {RecommendationMode.AUTOMATE, RecommendationMode.AUGMENT}
        else "muted"
    )


def _render_summary(package, narrative, sections) -> None:
    render_decision_header(
        context_line=f"Decision Package · {narrative.process_name}",
        headline=narrative.headline,
        headline_heading="Decision summary",
        headline_note=narrative.completeness_statement,
        boxed=True,
        sections=(
            HeaderSection("Why this decision was reached", narrative.why),
            HeaderSection("What this means", narrative.what_this_means),
            HeaderSection("What happens next", narrative.next_action),
            HeaderSection("Risks and limitations", narrative.limitations),
        ),
    )

    st.subheader("Supporting decision detail")
    _render_report_section(sections[0])
    _render_report_section(sections[1])
    _render_report_section_in_one_expander(
        sections[2], label="Review all missing information"
    )

    _render_section_technical(
        sections,
        extra_groups=(("Package and decision lineage", narrative.technical_reference),),
    )

    primary, secondary = st.columns(2)
    with primary:
        st.download_button(
            "Download print-friendly HTML report",
            data=render_report_html(package),
            file_name=f"ai-adoption-report-{package.current_state.process_id}.html",
            mime="text/html",
            type="primary",
            width="stretch",
        )
    with secondary:
        if st.button(
            "Review optional evidence-continuation paths",
            key="decision-package-continue",
            icon=":material/route:",
            width="stretch",
        ):
            if not switch_to_registered_page("decision-continuation"):
                st.info("Open Decision continuation from the sidebar to continue.")


def _render_portfolio(package, sections) -> None:
    portfolio = sections[0]
    st.subheader(portfolio.title)
    for item, block in zip(package.portfolio.items, portfolio.blocks, strict=True):
        with st.container(border=True):
            title, status = st.columns([4, 1], vertical_alignment="center")
            with title:
                st.markdown(f"**{block.heading}**")
            with status:
                render_badge(
                    labels.recommendation_label(item.recommendation_mode.value),
                    tone=_recommendation_tone(item.recommendation_mode),
                )
            with st.expander("View activity decision"):
                _render_block(block, show_heading=False)

    for section in sections[1:]:
        _render_report_section(section)
    _render_section_technical(sections)


def _future_state_technical(package) -> tuple[str, ...]:
    lines = [f"Future-state status: {package.future_state.status.value}"]
    for step in package.future_state.steps:
        lines.append(
            f"{step.sequence}. Source step ID: {step.source_step_id} · "
            f"Recommendation mode: {step.recommendation_mode.value} · "
            f"Intervention type: {step.intervention_type.value} · "
            f"Capability use: {step.capability_use_status.value}"
        )
        if step.capabilities:
            lines.append(
                f"{step.source_step_id} capabilities: "
                + ", ".join(item.value for item in step.capabilities)
            )
        if step.human_roles:
            lines.append(
                f"{step.source_step_id} human-role records: "
                + ", ".join(
                    f"{item.role_type.value} ({item.confirmation_status.value})"
                    for item in step.human_roles
                )
            )
    return tuple(lines)


def _render_future_state(package, sections) -> None:
    st.subheader(sections[0].title)
    st.warning(package.future_state.status.value, icon="⚠️")
    for paragraph in sections[0].blocks[0].paragraphs:
        st.write(paragraph)
    for step in package.future_state.steps:
        with st.container(border=True):
            title, status = st.columns([4, 1], vertical_alignment="center")
            with title:
                st.markdown(f"**{step.sequence}. {step.proposed_activity}**")
            with status:
                render_badge(
                    labels.recommendation_label(step.recommendation_mode.value),
                    tone=_recommendation_tone(step.recommendation_mode),
                )
            st.caption(
                "Intervention: " + labels.human_label(step.intervention_type.value)
            )
            if step.capabilities:
                st.caption(
                    "AI capabilities: "
                    + ", ".join(
                        labels.human_label(item.value) for item in step.capabilities
                    )
                )
            if step.human_roles:
                st.caption(
                    "Human controls: "
                    + ", ".join(
                        labels.human_label(item.role_type.value)
                        for item in step.human_roles
                    )
                )
            render_business_list(step.controls_and_constraints, boxed=False)

    _render_report_section(sections[1])
    _render_section_technical(
        sections,
        extra_groups=(("Future-state records", _future_state_technical(package)),),
    )


def _render_roadmap(package, sections) -> None:
    section = sections[0]
    activity_by_id = {item.step_id: item for item in package.portfolio.items}
    st.subheader(section.title)
    for opportunity, block in zip(
        package.roadmap.opportunities, section.blocks, strict=True
    ):
        item = activity_by_id[opportunity.step_id]
        with st.expander(block.heading or item.current_activity):
            render_badge(
                labels.recommendation_label(item.recommendation_mode.value),
                tone=_recommendation_tone(item.recommendation_mode),
            )
            _render_block(block, show_heading=False)
            if not opportunity.stages:
                st.info("AI deployment roadmap not applicable.")
    _render_section_technical(sections)


def _governance_records(package) -> tuple[str, ...]:
    return tuple(
        f"Step {item.step_id} · Origin {item.basis.origin.value} · "
        f"Category {item.category.value} · requires_review={item.requires_review}"
        for item in package.governance.considerations
    )


def _render_governance(package, sections) -> None:
    _render_report_section(sections[0], collapse_records=True)
    st.info(
        "This summary does not claim legal compliance, security approval, "
        "ethical acceptability or deployment readiness."
    )
    _render_section_technical(
        sections,
        extra_groups=(("Underlying governance records", _governance_records(package)),),
    )


def _render_evidence(package, sections) -> None:
    _render_report_section(sections[0])
    _render_report_section(sections[1], collapse_records=True)
    _render_section_technical(
        sections,
        extra_groups=(
            ("Methodology disclosures", tuple(package.methodology.disclosure_statements)),
        ),
    )


def _render_section_nav() -> str:
    st.markdown(_SECTION_NAV_STYLES, unsafe_allow_html=True)
    with st.container(key="decision-package-section-nav"):
        selected = st.segmented_control(
            "Decision Package section",
            PACKAGE_SECTIONS,
            default=SUMMARY,
            required=True,
            key="decision-package-section",
            label_visibility="collapsed",
            width="stretch",
        )
    return selected or SUMMARY


def render() -> None:
    snapshot = hydrate_workspace()
    integrated = st.session_state.get("integrated_assessment_result")
    generated = st.session_state.get("decision_package_result")
    render_page_header("Decision Package")

    if snapshot is None:
        guard("Create or open an assessment first.")
    if integrated is None or getattr(integrated, "status", None) != "success":
        guard(
            "Complete a successful integrated assessment before generating "
            "decision support."
        )
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
    groups = _report_groups(package)
    selected = _render_section_nav()

    if selected == SUMMARY:
        _render_summary(package, narrative, groups[selected])
    elif selected == OPPORTUNITY_PORTFOLIO:
        _render_portfolio(package, groups[selected])
    elif selected == FUTURE_STATE:
        _render_future_state(package, groups[selected])
    elif selected == ROADMAP:
        _render_roadmap(package, groups[selected])
    elif selected == RISKS_GOVERNANCE:
        _render_governance(package, groups[selected])
    else:
        _render_evidence(package, groups[EVIDENCE_APPENDIX])

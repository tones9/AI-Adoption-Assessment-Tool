"""Read-only Streamlit projections for already-created successor artifacts."""

from __future__ import annotations

from collections import Counter

import streamlit as st

from ai_adoption_engine.models.four_gate_assessment import (
    OutcomeCode,
)
from ai_adoption_engine.models.four_gate_decision_support import (
    FourGateDecisionPackageSuccess,
    FourGateReportSectionId,
)
from ai_adoption_engine.models.four_gate_integrated_assessment import (
    FourGateIntegratedAssessmentSuccess,
)
from ai_adoption_engine.presentation import labels
from ai_adoption_engine.presentation.components.decision_header import (
    HeaderSection,
    render_decision_header,
)
from ai_adoption_engine.presentation.components.primitives import (
    render_badge,
    render_business_list,
)
from ai_adoption_engine.presentation.components.technical_details import (
    technical_details,
)
from ai_adoption_engine.presentation.four_gate_narrative import (
    build_four_gate_package_narrative,
    build_four_gate_process_narrative,
)
from ai_adoption_engine.presentation.report_html import render_report_html
from ai_adoption_engine.presentation.report_view import build_report_view


SUCCESSOR_PACKAGE_SECTIONS = (
    "Summary",
    "Activity decisions",
    "Future-state workflow",
    "Roadmap",
    "Risks & governance",
    "Evidence appendix",
)

_SUCCESSOR_REPORT_GROUPS = {
    "Summary": (
        FourGateReportSectionId.EXECUTIVE_SUMMARY,
        FourGateReportSectionId.PROCESS_ASSESSED,
        FourGateReportSectionId.MISSING_INFORMATION,
    ),
    "Activity decisions": (
        FourGateReportSectionId.ACTIVITY_DECISION_PORTFOLIO,
        FourGateReportSectionId.HIGHEST_PRIORITY_AI_OPPORTUNITIES,
        FourGateReportSectionId.DISCOVERY_REQUIRED,
        FourGateReportSectionId.OTHER_INTERVENTIONS_AND_NO_CHANGE,
    ),
    "Future-state workflow": (
        FourGateReportSectionId.PROPOSED_FUTURE_STATE_WORKFLOW,
        FourGateReportSectionId.HUMAN_ROLES_AND_CONTROLS,
    ),
    "Roadmap": (FourGateReportSectionId.ADOPTION_ROADMAP,),
    "Risks & governance": (FourGateReportSectionId.RISKS_AND_GOVERNANCE,),
    "Evidence appendix": (
        FourGateReportSectionId.METHODOLOGY_AND_POLICY_DISCLOSURE,
        FourGateReportSectionId.EVIDENCE_AND_TRACEABILITY_APPENDIX,
    ),
}


def render_four_gate_results(
    integrated: FourGateIntegratedAssessmentSuccess,
) -> None:
    """Render an existing phase5-v0.2 result without offering workflow actions."""

    narrative = build_four_gate_process_narrative(integrated)
    render_decision_header(
        context_line=f"Assessment Results · {narrative.process_name}",
        headline=narrative.headline,
        headline_as_title=True,
        boxed=True,
        sections=(
            HeaderSection("What we found", narrative.what_we_found),
            HeaderSection(
                "Active decision blockers",
                narrative.what_is_still_needed
                or ("No active decision blocker is recorded.",),
            ),
            HeaderSection("What this means", narrative.what_this_means),
            HeaderSection("What happens next", narrative.next_action),
        ),
    )

    _render_results_technical(integrated, narrative)
    _render_outcome_counts(integrated)
    st.subheader("Activity-by-activity results")
    for activity in narrative.activities:
        with st.container(border=True):
            title, status = st.columns([4, 1], vertical_alignment="center")
            with title:
                st.markdown(f"**{activity.sequence}. {activity.activity}**")
            with status:
                render_badge(activity.outcome_label, tone=_outcome_tone(activity.outcome_code))
            st.write(activity.outcome_statement)
            st.write(activity.reason_statement)
            _render_gap_group("Active decision blockers", activity.blocking_gaps)
            _render_gap_group("Contextual information", activity.contextual_gaps)
            _render_gap_group("Priority-only information", activity.priority_gaps)
            st.markdown("**Decision status**")
            st.write(
                next(
                    detail.split(": ", 1)[1]
                    for detail in activity.technical_details
                    if detail.startswith("decision_status:")
                )
            )
            st.markdown("**Priority status**")
            st.write(activity.priority_statement)
            st.markdown("**Next action**")
            st.write(activity.next_action)


def render_four_gate_package(generated: FourGateDecisionPackageSuccess) -> None:
    """Render an existing phase6-v0.2 package without generation controls."""

    package = generated.package
    narrative = build_four_gate_package_narrative(package)
    view = build_report_view(package)
    by_id = {section.section_id: section for section in view}
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
    st.download_button(
        "Download print-friendly HTML report",
        data=render_report_html(package),
        file_name=f"ai-adoption-report-{package.current_state.process_id}.html",
        mime="text/html",
        type="primary",
        width="stretch",
    )
    selected = st.segmented_control(
        "Decision Package section",
        SUCCESSOR_PACKAGE_SECTIONS,
        default=SUCCESSOR_PACKAGE_SECTIONS[0],
        required=True,
        key="four-gate-decision-package-section",
        label_visibility="collapsed",
        width="stretch",
    ) or SUCCESSOR_PACKAGE_SECTIONS[0]
    sections = tuple(by_id[item] for item in _SUCCESSOR_REPORT_GROUPS[selected])
    st.subheader("Supporting decision detail")
    for section in sections:
        st.subheader(section.title)
        for index, block in enumerate(section.blocks):
            with st.container(border=True):
                if block.heading:
                    st.markdown(f"**{block.heading}**")
                if (
                    section.section_id
                    is FourGateReportSectionId.ACTIVITY_DECISION_PORTFOLIO
                    and index < len(package.portfolio.items)
                ):
                    item = package.portfolio.items[index]
                    render_badge(
                        labels.four_gate_outcome_label(item.outcome_code.value),
                        tone=_outcome_tone(item.outcome_code.value),
                    )
                for paragraph in block.paragraphs:
                    st.write(paragraph)
                render_business_list(block.bullets, boxed=False)
    with technical_details():
        for line in narrative.technical_reference:
            st.caption(line)
        for section in sections:
            for block in section.blocks:
                if block.origin:
                    st.caption(f"Origin: {block.origin.value}")
                for detail in block.technical_details:
                    st.code(detail, language=None)


def _render_results_technical(integrated, narrative) -> None:
    with technical_details():
        for activity, step in zip(
            narrative.activities,
            integrated.process_assessment.step_assessments,
            strict=True,
        ):
            st.markdown(f"**{activity.sequence}. {activity.activity}**")
            for detail in activity.technical_details:
                st.caption(detail)
            st.markdown("**Four ordered gates**")
            for gate in activity.gates:
                st.caption(
                    f"{gate.label} — {gate.status_label} ({gate.status})"
                )
                st.caption(gate.rationale)
            st.markdown("**Criteria and materiality**")
            for criterion in step.criteria:
                st.caption(
                    f"{criterion.criterion.value}: value={criterion.value} · "
                    f"{criterion.knowledge_state.value} · "
                    f"material_to_decision={criterion.material_to_decision} · "
                    f"material_to_priority={criterion.material_to_priority}"
                )
            st.markdown("**Capability signals and evidence lineage**")
            for signal in step.capability_signals:
                st.caption(
                    f"{signal.signal.value}: value={signal.value} · "
                    f"{signal.knowledge_state.value} · "
                    f"material_to_decision={signal.material_to_decision}"
                )
            trace = next(
                item
                for item in integrated.step_traceability
                if item.step_id == step.step_id
            )
            for reviewed in [
                trace.activity,
                *trace.criteria,
                trace.human_accountability,
                *trace.capability_signals,
            ]:
                st.caption(
                    f"{reviewed.assessment_field_path}: "
                    f"{reviewed.origin.value} / {reviewed.knowledge_state.value}"
                )
                for evidence in reviewed.evidence:
                    st.caption(
                        f"{evidence.source_locator} · {evidence.evidence_id}"
                    )
        st.markdown("**Framework, policy and assessment run**")
        for line in narrative.policy_reference:
            st.caption(line)


def _render_outcome_counts(integrated) -> None:
    counts = Counter(
        step.outcome_code
        for step in integrated.process_assessment.step_assessments
    )
    st.caption("Supporting numbers")
    values = [("Activities assessed", sum(counts.values()))] + [
        (labels.four_gate_outcome_label(outcome.value), counts[outcome])
        for outcome in OutcomeCode
    ]
    for start in range(0, len(values), 2):
        columns = st.columns(2)
        for column, (label, value) in zip(columns, values[start : start + 2]):
            column.metric(label, value)


def _render_gap_group(heading, gaps) -> None:
    render_business_list(
        (gap.statement for gap in gaps)
        if gaps
        else ("No gaps in this classification.",),
        eyebrow=heading,
        boxed=False,
    )


def _outcome_tone(outcome_code: str) -> str:
    return (
        "primary"
        if outcome_code in {
            OutcomeCode.AI_AUTOMATION.value,
            OutcomeCode.AI_ASSISTED_WORK.value,
        }
        else "muted"
    )

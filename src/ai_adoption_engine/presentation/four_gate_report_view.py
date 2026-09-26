"""Business report projection for an immutable phase6-v0.2 package."""

from __future__ import annotations

from ai_adoption_engine.models.four_gate_decision_support import (
    FourGateDecisionSupportPackage,
    FourGateInformationGapKind,
    FourGateReportOrigin,
    FourGateReportSectionId,
)
from ai_adoption_engine.presentation import labels
from ai_adoption_engine.presentation.contracts import phase6_presentation_contract
from ai_adoption_engine.presentation.four_gate_narrative import (
    build_four_gate_package_narrative,
)
from ai_adoption_engine.presentation.report_view import (
    ReportViewBlock,
    ReportViewSection,
)


def build_four_gate_report_view(
    package: FourGateDecisionSupportPackage,
) -> tuple[ReportViewSection, ...]:
    """Render all 13 successor sections without recomputing a decision."""

    phase6_presentation_contract(package)
    narrative = build_four_gate_package_narrative(package)
    renderers = {
        FourGateReportSectionId.EXECUTIVE_SUMMARY: (
            lambda source: _executive_summary(source, narrative)
        ),
        FourGateReportSectionId.ACTIVITY_DECISION_PORTFOLIO: (
            lambda source: _portfolio(package)
        ),
        FourGateReportSectionId.HIGHEST_PRIORITY_AI_OPPORTUNITIES: (
            lambda source: _priority(package)
        ),
        FourGateReportSectionId.DISCOVERY_REQUIRED: (
            lambda source: _discovery(package)
        ),
        FourGateReportSectionId.PROPOSED_FUTURE_STATE_WORKFLOW: (
            lambda source: _future_state(package)
        ),
        FourGateReportSectionId.ADOPTION_ROADMAP: (
            lambda source: _roadmap(package)
        ),
        FourGateReportSectionId.MISSING_INFORMATION: (
            lambda source: _missing_information(package)
        ),
        FourGateReportSectionId.METHODOLOGY_AND_POLICY_DISCLOSURE: (
            lambda source: _methodology(package)
        ),
        FourGateReportSectionId.EVIDENCE_AND_TRACEABILITY_APPENDIX: (
            lambda source: _evidence(package)
        ),
    }
    return tuple(
        ReportViewSection(
            section_id=source.section_id,
            title=source.title,
            blocks=tuple(
                renderers[source.section_id](source)
                if source.section_id in renderers
                else _source_blocks(source)
            ),
        )
        for source in package.report_content.sections
    )


def _source_blocks(source) -> list[ReportViewBlock]:
    if not source.statements:
        return [ReportViewBlock(paragraphs=("No item applies to this section.",))]
    return [
        ReportViewBlock(
            paragraphs=(statement.text,),
            origin=statement.origin,
            technical_details=_statement_technical(statement),
        )
        for statement in source.statements
    ]


def _executive_summary(source, narrative) -> list[ReportViewBlock]:
    return [
        ReportViewBlock(
            paragraphs=(
                narrative.headline,
                narrative.completeness_statement,
                *narrative.outcome_groups,
            ),
            origin=FourGateReportOrigin.ASSESSMENT_FINDING,
            technical_details=tuple(
                f"Source statement: {statement.text}"
                for statement in source.statements
            ),
        )
    ]


def _portfolio(package) -> list[ReportViewBlock]:
    blocks = []
    for item in package.portfolio.items:
        grouped = {
            kind: [
                gap.message for gap in item.information_gaps if gap.kind is kind
            ]
            for kind in FourGateInformationGapKind
        }
        paragraphs = [
            "Final decision: "
            + labels.four_gate_outcome_label(item.outcome_code.value),
            f"Reason / basis: {item.final_recommendation}",
            "Decision status: " + labels.human_label(item.decision_status.value),
            "Priority status: "
            + labels.priority_status_label(item.priority_status.value.lower()),
        ]
        for kind, heading in (
            (
                FourGateInformationGapKind.ACTIVE_DECISION_BLOCKER,
                "Active decision blockers",
            ),
            (FourGateInformationGapKind.CONTEXTUAL_UNKNOWN, "Contextual information"),
            (FourGateInformationGapKind.PRIORITY_ONLY, "Priority-only information"),
        ):
            if grouped[kind]:
                paragraphs.append(f"{heading}: " + "; ".join(grouped[kind]))
        blocks.append(
            ReportViewBlock(
                heading=f"{item.sequence}. {item.activity}",
                paragraphs=tuple(paragraphs),
                origin=FourGateReportOrigin.ASSESSMENT_FINDING,
                technical_details=(
                    f"Internal step ID: {item.step_id}",
                    f"decision_status: {item.decision_status.value}",
                    f"change_disposition: {item.change_disposition.value}",
                    f"readiness_disposition: {item.readiness_disposition.value}",
                    "selected_intervention_family: "
                    f"{item.selected_intervention_family.value}",
                    f"autonomy_ceiling: {item.autonomy_ceiling.value}",
                    f"outcome_code (derived): {item.outcome_code.value}",
                )
                + tuple(
                    f"{gate.gate.value}: {gate.status.value} · "
                    f"{gate.decision_code.value} · {gate.rationale}"
                    for gate in item.gate_results
                ),
            )
        )
    return blocks


def _priority(package) -> list[ReportViewBlock]:
    eligible = sorted(
        (
            item
            for item in package.portfolio.items
            if item.priority_eligible and item.priority is not None
        ),
        key=lambda item: (-item.priority.score, item.sequence),
    )
    return [
        ReportViewBlock(
            bullets=tuple(
                f"{item.activity}: {item.priority.score:.1f} of 100 "
                f"({labels.priority_band_label(item.priority.band)} band)."
                for item in eligible
            )
            or ("No complete, scored AI priority applies.",),
            origin=FourGateReportOrigin.ASSESSMENT_FINDING,
        )
    ]


def _discovery(package) -> list[ReportViewBlock]:
    active = [
        (item, gap)
        for item in package.portfolio.items
        for gap in item.information_gaps
        if gap.kind is FourGateInformationGapKind.ACTIVE_DECISION_BLOCKER
    ]
    return [
        ReportViewBlock(
            heading=item.activity,
            bullets=(gap.message,),
            origin=FourGateReportOrigin.ASSESSMENT_FINDING,
            technical_details=(
                f"Blocking gate: {gap.gate.value}",
                f"Internal step ID: {item.step_id}",
            ),
        )
        for item, gap in active
    ] or [
        ReportViewBlock(
            paragraphs=("No active decision blocker is recorded.",),
            origin=FourGateReportOrigin.ASSESSMENT_FINDING,
        )
    ]


def _future_state(package) -> list[ReportViewBlock]:
    return [
        ReportViewBlock(
            paragraphs=(
                "This future-state workflow is proposed. Nothing in it has been deployed.",
            ),
            bullets=tuple(
                f"{step.sequence}. {step.proposed_activity} — final decision: "
                f"{labels.four_gate_outcome_label(step.final_outcome.value)}."
                for step in package.future_state.steps
            ),
            origin=FourGateReportOrigin.DERIVED_REPORT_GUIDANCE,
            technical_details=tuple(
                f"{step.step_id}: capability_use_status="
                f"{step.capability_use_status.value} · status={step.status}"
                for step in package.future_state.steps
            ),
        )
    ]


def _roadmap(package) -> list[ReportViewBlock]:
    activity = {item.step_id: item.activity for item in package.portfolio.items}
    return [
        ReportViewBlock(
            heading=f"{item.sequence}. {activity[item.step_id]}",
            paragraphs=(
                "Final decision: "
                + labels.four_gate_outcome_label(item.final_outcome.value),
                "Priority status: "
                + labels.priority_status_label(item.priority_status.value.lower()),
                item.guidance,
            ),
            origin=FourGateReportOrigin.DERIVED_REPORT_GUIDANCE,
            technical_details=(
                f"AI priority eligible: {str(item.ai_priority_eligible).lower()}",
                f"Roadmap status: {item.status}",
            ),
        )
        for item in package.roadmap
    ]


def _missing_information(package) -> list[ReportViewBlock]:
    headings = {
        FourGateInformationGapKind.ACTIVE_DECISION_BLOCKER: "Active decision blockers",
        FourGateInformationGapKind.CONTEXTUAL_UNKNOWN: "Contextual information",
        FourGateInformationGapKind.PRIORITY_ONLY: "Priority-only information",
    }
    return [
        ReportViewBlock(
            heading=headings[kind],
            bullets=tuple(
                gap.message for gap in package.missing_information if gap.kind is kind
            )
            or ("No gaps in this classification.",),
            origin=FourGateReportOrigin.ASSESSMENT_FINDING,
        )
        for kind in FourGateInformationGapKind
    ]


def _methodology(package) -> list[ReportViewBlock]:
    return [
        ReportViewBlock(
            bullets=tuple(package.methodology.disclosure_statements),
            origin=FourGateReportOrigin.DISCLOSURE,
            technical_details=(
                f"Framework: {package.methodology.framework_id} "
                f"{package.methodology.framework_version}",
                f"Decision contract: {package.methodology.decision_contract_version}",
                f"Policy: {package.methodology.policy_id} "
                f"{package.methodology.policy_version}",
                f"Policy fingerprint: {package.methodology.policy_fingerprint}",
                "Policy provisional: true",
                "Academically validated: false",
                "Decision support only: true",
                "Proposed future state deployed: false",
            ),
        )
    ]


def _evidence(package) -> list[ReportViewBlock]:
    blocks = []
    for item in package.portfolio.items:
        traces = [
            item.source_traceability.activity,
            *item.source_traceability.criteria,
            item.source_traceability.human_accountability,
            *item.source_traceability.capability_signals,
        ]
        evidence_ids = {
            reference.evidence_id
            for trace in traces
            for reference in trace.evidence
        }
        blocks.append(
            ReportViewBlock(
                heading=item.activity,
                bullets=tuple(
                    f"Source: {reference.source_locator}"
                    for reference in item.source_traceability.activity.evidence
                )
                or ("No activity evidence reference is available.",),
                origin=FourGateReportOrigin.ASSESSMENT_FINDING,
                technical_details=(f"Internal step ID: {item.step_id}",)
                + tuple(
                    f"Evidence ID: {reference.evidence_id} · "
                    f"Document ID: {reference.document_id} · "
                    f"Block ID: {reference.block_id}"
                    for reference in package.evidence_appendix
                    if reference.evidence_id in evidence_ids
                ),
            )
        )
    return blocks


def _statement_technical(statement) -> tuple[str, ...]:
    details = []
    if statement.step_ids:
        details.append("Internal step IDs: " + ", ".join(statement.step_ids))
    if statement.evidence_ids:
        details.append("Evidence IDs: " + ", ".join(statement.evidence_ids))
    if statement.final_outcome:
        details.append("Final outcome: " + statement.final_outcome.value)
    if statement.selected_intervention_family:
        details.append(
            "Selected intervention family: "
            + statement.selected_intervention_family.value
        )
    if statement.autonomy_ceiling:
        details.append("Autonomy ceiling: " + statement.autonomy_ceiling.value)
    return tuple(details)

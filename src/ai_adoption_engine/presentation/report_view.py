"""Business-facing Phase 7 projection of an immutable Phase 6 package."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ai_adoption_engine.models.decision_support import (
    DecisionSupportPackage,
    GovernanceConsideration,
    InformationGap,
    InformationGapKind,
    OpportunityPortfolioItem,
    PlanningOrigin,
    ReportSectionId,
)
from ai_adoption_engine.models.enums import CriterionName, GateStatus, RecommendationMode


@dataclass(frozen=True)
class ReportViewBlock:
    heading: str | None = None
    paragraphs: tuple[str, ...] = ()
    bullets: tuple[str, ...] = ()
    origin: PlanningOrigin | None = None
    technical_details: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReportViewSection:
    section_id: ReportSectionId
    title: str
    blocks: tuple[ReportViewBlock, ...] = field(default_factory=tuple)


def build_report_view(package: DecisionSupportPackage) -> tuple[ReportViewSection, ...]:
    """Create deterministic, consolidated report content without altering Phase 6."""

    renderers = {
        ReportSectionId.EXECUTIVE_SUMMARY: _executive_summary,
        ReportSectionId.OPPORTUNITY_PORTFOLIO: _opportunity_portfolio,
        ReportSectionId.RISKS_GOVERNANCE: _governance,
        ReportSectionId.ADOPTION_ROADMAP: _roadmap,
        ReportSectionId.MISSING_INFORMATION: _missing_information,
        ReportSectionId.EVIDENCE_APPENDIX: _evidence_appendix,
    }
    sections = []
    for source in package.report_content.sections:
        renderer = renderers.get(source.section_id)
        blocks = renderer(package) if renderer else _source_blocks(source.statements)
        sections.append(
            ReportViewSection(
                section_id=source.section_id,
                title=source.title,
                blocks=tuple(blocks),
            )
        )
    return tuple(sections)


def _source_blocks(statements) -> list[ReportViewBlock]:
    return [
        ReportViewBlock(
            paragraphs=(statement.text,),
            origin=statement.origin,
            technical_details=_technical_references(
                statement.step_ids, statement.evidence_ids
            ),
        )
        for statement in statements
    ]


def _executive_summary(package: DecisionSupportPackage) -> list[ReportViewBlock]:
    items = package.portfolio.items
    all_investigate = items and all(
        item.recommendation_mode is RecommendationMode.INVESTIGATE_FURTHER
        for item in items
    )
    if all_investigate:
        activity_count = len(items)
        statement = (
            f"All {activity_count} activities require further investigation because the "
            "current evidence is not sufficient to establish AI-adoption suitability. "
            "The appropriate next action is to gather and validate the missing evidence, "
            "not to begin deployment planning."
        )
        return [
            ReportViewBlock(
                paragraphs=(statement, package.roi_statement),
                origin=PlanningOrigin.ASSESSMENT_FINDING,
                technical_details=(
                    "Applies to activities: "
                    + ", ".join(item.current_activity for item in items),
                ),
            )
        ]
    source = next(
        section
        for section in package.report_content.sections
        if section.section_id is ReportSectionId.EXECUTIVE_SUMMARY
    )
    return _source_blocks(source.statements)


def _opportunity_portfolio(
    package: DecisionSupportPackage,
) -> list[ReportViewBlock]:
    common_gap_keys = _common_gap_keys(package)
    roadmaps = {item.step_id: item for item in package.roadmap.opportunities}
    blocks = []
    for item in package.portfolio.items:
        material = [gap for gap in item.missing_information if _material(gap)]
        common_material = [gap for gap in material if _gap_key(gap) in common_gap_keys]
        specific_material = [gap for gap in material if _gap_key(gap) not in common_gap_keys]
        missing_basis = _portfolio_gap_summary(common_material, specific_material)
        roadmap = roadmaps[item.step_id]
        next_action = (
            roadmap.stages[0].objective if roadmap.stages else roadmap.rationale
        )
        blocks.append(
            ReportViewBlock(
                heading=f"{item.sequence}. {item.current_activity}",
                paragraphs=(
                    f"Recommendation: {_human(item.recommendation_mode.value)}",
                    f"Reason / basis: {_concise_basis(item)}",
                    f"Material missing information: {missing_basis}",
                    f"Next action: {next_action}",
                ),
                origin=PlanningOrigin.ASSESSMENT_FINDING,
                technical_details=(f"Internal step ID: {item.step_id}",),
            )
        )
    return blocks


def _concise_basis(item: OpportunityPortfolioItem) -> str:
    failed = next(
        (gate for gate in item.gate_results if gate.status is GateStatus.FAILED),
        None,
    )
    if failed is not None:
        return failed.rationale
    meaningful = [
        gate
        for gate in item.gate_results
        if gate.status is not GateStatus.NOT_EVALUATED
    ]
    if meaningful:
        return meaningful[-1].rationale
    return item.rationale[-1]


def _portfolio_gap_summary(
    common: list[InformationGap], specific: list[InformationGap]
) -> str:
    parts = []
    if common:
        parts.append(
            f"{len(common)} material process-wide gap"
            f"{'s' if len(common) != 1 else ''} apply"
        )
    if specific:
        parts.append(
            "activity-specific: "
            + ", ".join(_field_label(item.field_name) for item in specific)
        )
    if not parts:
        return "No material missing information is recorded for this activity."
    if common and not specific:
        parts.append("no activity-specific difference")
    return "; ".join(parts) + "."


def _missing_information(package: DecisionSupportPackage) -> list[ReportViewBlock]:
    items = package.portfolio.items
    step_ids = {item.step_id for item in items}
    activity_by_id = {item.step_id: item.current_activity for item in items}
    grouped: dict[tuple, list[InformationGap]] = defaultdict(list)
    for item in items:
        for gap in item.missing_information:
            grouped[_gap_key(gap)].append(gap)

    common = [values[0] for values in grouped.values() if {g.step_id for g in values} == step_ids]
    specific = [
        gap
        for values in grouped.values()
        if {gap.step_id for gap in values} != step_ids
        for gap in values
    ]
    blocks = []
    if common:
        blocks.append(
            ReportViewBlock(
                heading="Process-wide/common gaps",
                paragraphs=(
                    f"These gaps apply consistently across all {len(items)} assessed activities.",
                ),
                bullets=tuple(_group_common_gaps(common)),
                origin=PlanningOrigin.ASSESSMENT_FINDING,
                technical_details=(
                    "Underlying package records retained: "
                    f"{sum(len(values) for values in grouped.values() if {gap.step_id for gap in values} == step_ids)} "
                    "per-step gaps.",
                ),
            )
        )
    by_step: dict[str, list[InformationGap]] = defaultdict(list)
    for gap in specific:
        by_step[gap.step_id].append(gap)
    for item in items:
        differences = by_step.get(item.step_id, [])
        if differences:
            blocks.append(
                ReportViewBlock(
                    heading=f"{item.sequence}. {item.current_activity} — step-specific gaps",
                    bullets=tuple(gap.message for gap in differences),
                    origin=PlanningOrigin.ASSESSMENT_FINDING,
                    technical_details=(f"Internal step ID: {item.step_id}",),
                )
            )
    if common and not specific:
        blocks.append(
            ReportViewBlock(
                paragraphs=("No step-specific differences were identified.",),
                origin=PlanningOrigin.ASSESSMENT_FINDING,
            )
        )
    if not common and not specific:
        blocks.append(
            ReportViewBlock(
                paragraphs=("No material package-level information gap was identified.",),
                origin=PlanningOrigin.ASSESSMENT_FINDING,
            )
        )
    return blocks


def _group_common_gaps(gaps: list[InformationGap]) -> list[str]:
    criteria = {item.value for item in CriterionName}
    unknown_criteria = sorted(
        _field_label(gap.field_name)
        for gap in gaps
        if gap.kind is InformationGapKind.UNKNOWN_INPUT and gap.field_name in criteria
    )
    unknown_capabilities = sorted(
        _field_label(gap.field_name)
        for gap in gaps
        if gap.kind is InformationGapKind.UNKNOWN_INPUT
        and ":capability:" in gap.gap_id
    )
    consumed = {
        gap.field_name
        for gap in gaps
        if (
            gap.kind is InformationGapKind.UNKNOWN_INPUT
            and (gap.field_name in criteria or ":capability:" in gap.gap_id)
        )
    }
    bullets = []
    if unknown_criteria:
        bullets.append("Unknown assessment criteria: " + ", ".join(unknown_criteria) + ".")
    if unknown_capabilities:
        bullets.append("Unknown capability signals: " + ", ".join(unknown_capabilities) + ".")
    bullets.extend(gap.message for gap in gaps if gap.field_name not in consumed)
    return bullets


def _governance(package: DecisionSupportPackage) -> list[ReportViewBlock]:
    items = package.portfolio.items
    step_ids = {item.step_id for item in items}
    grouped: dict[tuple, list[GovernanceConsideration]] = defaultdict(list)
    for item in package.governance.considerations:
        grouped[_governance_key(item)].append(item)
    common = [values[0] for values in grouped.values() if {x.step_id for x in values} == step_ids]
    specific = [
        item
        for values in grouped.values()
        if {item.step_id for item in values} != step_ids
        for item in values
    ]
    blocks = []
    if common:
        blocks.append(
            ReportViewBlock(
                heading="Process-level governance considerations",
                paragraphs=(
                    "These requirements apply consistently across all "
                    f"{len(items)} assessed activities.",
                ),
                bullets=tuple(item.statement for item in common),
                origin=PlanningOrigin.DERIVED_PLANNING_GUIDANCE,
                technical_details=(
                    "Underlying package records retained: "
                    f"{sum(len(values) for values in grouped.values() if {item.step_id for item in values} == step_ids)} "
                    "per-step considerations.",
                ),
            )
        )
    by_step: dict[str, list[GovernanceConsideration]] = defaultdict(list)
    for consideration in specific:
        by_step[consideration.step_id].append(consideration)
    for item in items:
        differences = by_step.get(item.step_id, [])
        if differences:
            blocks.append(
                ReportViewBlock(
                    heading=(
                        f"{item.sequence}. {item.current_activity} — "
                        "step-specific considerations"
                    ),
                    bullets=tuple(value.statement for value in differences),
                    origin=PlanningOrigin.DERIVED_PLANNING_GUIDANCE,
                    technical_details=(f"Internal step ID: {item.step_id}",),
                )
            )
    if common and not specific:
        blocks.append(
            ReportViewBlock(
                paragraphs=("No step-specific governance differences were identified.",),
                origin=PlanningOrigin.DERIVED_PLANNING_GUIDANCE,
            )
        )
    return blocks


def _roadmap(package: DecisionSupportPackage) -> list[ReportViewBlock]:
    activity = {item.step_id: item for item in package.portfolio.items}
    blocks = []
    for item in package.roadmap.opportunities:
        opportunity = activity[item.step_id]
        stage_summary = tuple(
            f"{stage.sequence}. {_human(stage.stage_type.value)}: {stage.objective}"
            + (
                " Decision outcomes: " + " / ".join(stage.possible_outcomes) + "."
                if stage.decision_point
                else ""
            )
            for stage in item.stages
        )
        blocks.append(
            ReportViewBlock(
                heading=f"{opportunity.sequence}. {opportunity.current_activity}",
                paragraphs=(
                    f"Status: {_human(item.status.value)}",
                    item.rationale,
                ),
                bullets=stage_summary,
                origin=PlanningOrigin.DERIVED_PLANNING_GUIDANCE,
                technical_details=(f"Internal step ID: {item.step_id}",),
            )
        )
    return blocks


def _evidence_appendix(package: DecisionSupportPackage) -> list[ReportViewBlock]:
    blocks = []
    for item in package.portfolio.items:
        evidence = item.source_traceability.activity.evidence
        if not evidence:
            blocks.append(
                ReportViewBlock(
                    heading=f"{item.sequence}. {item.current_activity}",
                    paragraphs=("No activity evidence reference is available.",),
                    origin=PlanningOrigin.ASSESSMENT_FINDING,
                    technical_details=(f"Internal step ID: {item.step_id}",),
                )
            )
            continue
        source_bullets = []
        for reference in evidence:
            source_bullets.append(f"Source: {reference.source_locator}")
            snippet = getattr(reference, "exact_snippet", None) or getattr(
                reference, "supporting_snippet", None
            )
            if snippet:
                source_bullets.append(f"Evidence snippet: {snippet}")
        blocks.append(
            ReportViewBlock(
                heading=f"{item.sequence}. {item.current_activity}",
                bullets=tuple(source_bullets),
                origin=PlanningOrigin.ASSESSMENT_FINDING,
                technical_details=tuple(
                    " · ".join(
                        [
                            f"Evidence ID: {reference.evidence_id}",
                            f"Document ID: {reference.document_id}",
                            f"Block ID: {reference.block_id}",
                            f"Offsets: {reference.block_start_offset}:{reference.block_end_offset}",
                        ]
                    )
                    for reference in evidence
                )
                + (f"Internal step ID: {item.step_id}",),
            )
        )
    return blocks


def _common_gap_keys(package: DecisionSupportPackage) -> set[tuple]:
    step_ids = {item.step_id for item in package.portfolio.items}
    grouped: dict[tuple, set[str]] = defaultdict(set)
    for item in package.portfolio.items:
        for gap in item.missing_information:
            grouped[_gap_key(gap)].add(gap.step_id)
    return {key for key, covered in grouped.items() if covered == step_ids}


def _gap_key(gap: InformationGap) -> tuple:
    return (
        gap.kind,
        gap.field_name,
        gap.knowledge_state,
        gap.message,
        gap.material_to_recommendation,
        gap.material_to_priority,
        gap.material_to_planning,
    )


def _governance_key(item: GovernanceConsideration) -> tuple:
    return (item.category, item.statement, item.requires_review)


def _material(gap: InformationGap) -> bool:
    return (
        gap.material_to_recommendation
        or gap.material_to_priority
        or gap.material_to_planning
    )


def _field_label(value: str) -> str:
    return value.replace("_", " ")


def _human(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()


def _technical_references(
    step_ids: list[str], evidence_ids: list[str]
) -> tuple[str, ...]:
    details = []
    if step_ids:
        details.append("Internal step IDs: " + ", ".join(step_ids))
    if evidence_ids:
        details.append("Evidence IDs: " + ", ".join(evidence_ids))
    return tuple(details)

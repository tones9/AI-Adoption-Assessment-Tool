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
    ReportSection,
    ReportSectionId,
)
from ai_adoption_engine.models.enums import CriterionName, GateStatus, RecommendationMode
from ai_adoption_engine.presentation import labels
from ai_adoption_engine.presentation.decision_narrative import (
    build_package_narrative,
    gap_business_statement,
    portfolio_reason_statement,
)


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

    narrative = build_package_narrative(package)
    renderers = {
        ReportSectionId.EXECUTIVE_SUMMARY: (
            lambda pkg, src: _executive_summary(pkg, src, narrative)
        ),
        ReportSectionId.OPPORTUNITY_PORTFOLIO: _opportunity_portfolio,
        ReportSectionId.HIGHEST_PRIORITY: _highest_priority,
        ReportSectionId.FUTURE_STATE: _future_state,
        ReportSectionId.HUMAN_ROLES: _human_roles,
        ReportSectionId.RISKS_GOVERNANCE: _governance,
        ReportSectionId.ADOPTION_ROADMAP: _roadmap,
        ReportSectionId.MISSING_INFORMATION: _missing_information,
        ReportSectionId.EVIDENCE_APPENDIX: _evidence_appendix,
    }
    sections = []
    for source in package.report_content.sections:
        renderer = renderers.get(source.section_id)
        blocks = (
            renderer(package, source)
            if renderer
            else _source_blocks(source.statements)
        )
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


def _executive_summary(
    package: DecisionSupportPackage, source: ReportSection, narrative
) -> list[ReportViewBlock]:
    """Open with the package narrative decision, never with counts or tokens.

    The authoritative source statements are preserved verbatim as technical
    detail wherever the business paragraphs do not already carry them.
    """

    items = package.portfolio.items
    paragraphs = [narrative.headline, narrative.completeness_statement]
    all_investigate = bool(items) and all(
        item.recommendation_mode is RecommendationMode.INVESTIGATE_FURTHER
        for item in items
    )
    technical: list[str] = []
    if all_investigate:
        paragraphs.append(
            f"All {len(items)} activities require further investigation because the "
            "current evidence is not sufficient to establish AI-adoption suitability. "
            "The appropriate next action is to gather and validate the missing evidence, "
            "not to begin deployment planning."
        )
        technical.append(
            "Applies to activities: "
            + ", ".join(item.current_activity for item in items)
        )
    paragraphs.append(package.roi_statement)
    technical.extend(
        f"Source statement: {statement.text}"
        for statement in source.statements
        if statement.text not in paragraphs
    )
    return [
        ReportViewBlock(
            paragraphs=tuple(paragraphs),
            origin=PlanningOrigin.ASSESSMENT_FINDING,
            technical_details=tuple(technical),
        )
    ]


def _opportunity_portfolio(
    package: DecisionSupportPackage, source: ReportSection
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
                    "Recommendation: "
                    + labels.recommendation_label(item.recommendation_mode.value),
                    f"Reason / basis: {portfolio_reason_statement(item)}",
                    f"Material missing information: {missing_basis}",
                    f"Next action: {next_action}",
                ),
                origin=PlanningOrigin.ASSESSMENT_FINDING,
                technical_details=(
                    f"Internal step ID: {item.step_id}",
                    f"Recommendation mode: {item.recommendation_mode.value}",
                    f"Engine rationale: {_concise_basis(item)}",
                ),
            )
        )
    return blocks


def _highest_priority(
    package: DecisionSupportPackage, source: ReportSection
) -> list[ReportViewBlock]:
    """Restate the section's own membership with business priority wording.

    ``item_references`` is a sorted set of step IDs, so the referenced items are
    re-ordered here by the authoritative Phase 6 ordering - highest score first,
    process order as the tie-break - rather than by identifier.
    """

    items = {item.step_id: item for item in package.portfolio.items}
    referenced = [items.get(step_id) for step_id in source.item_references]
    if not referenced or any(
        item is None or item.priority is None for item in referenced
    ):
        return _source_blocks(source.statements)
    referenced = sorted(
        referenced, key=lambda item: (-item.priority.score, item.sequence)
    )
    return [
        ReportViewBlock(
            bullets=tuple(
                f"{item.current_activity}: priority score {item.priority.score:.1f} "
                f"of 100 ({labels.priority_band_label(item.priority.band.value)} band)."
                for item in referenced
            ),
            origin=PlanningOrigin.ASSESSMENT_FINDING,
            technical_details=tuple(
                f"Internal step ID: {item.step_id} · Priority band: "
                f"{item.priority.band.value}"
                for item in referenced
            ),
        )
    ]


def _future_state(
    package: DecisionSupportPackage, source: ReportSection
) -> list[ReportViewBlock]:
    """Render the proposed workflow without raw intervention tokens."""

    steps = package.future_state.steps
    return [
        ReportViewBlock(
            paragraphs=(
                "This future-state workflow is a proposal. Nothing in it has "
                "been deployed.",
            ),
            bullets=tuple(
                f"{step.sequence}. {step.proposed_activity}" for step in steps
            ),
            origin=PlanningOrigin.DERIVED_PLANNING_GUIDANCE,
            technical_details=(
                f"Future-state status: {package.future_state.status.value}",
            )
            + tuple(
                f"{step.sequence}. Intervention type: {step.intervention_type.value} "
                f"· Capability use: {step.capability_use_status.value} "
                f"· Source step ID: {step.source_step_id}"
                for step in steps
            ),
        )
    ]


def _human_roles(
    package: DecisionSupportPackage, source: ReportSection
) -> list[ReportViewBlock]:
    """Name the recommended human roles in business words per activity."""

    bullets = []
    technical = []
    for item in package.portfolio.items:
        if not item.recommended_human_roles:
            bullets.append(
                f"{item.current_activity}: no recommended human role is recorded."
            )
            technical.append(f"Internal step ID: {item.step_id}")
            continue
        roles = ", ".join(
            labels.human_label(role.role_type.value)
            for role in item.recommended_human_roles
        )
        statuses = sorted(
            {role.confirmation_status.value for role in item.recommended_human_roles}
        )
        suffix = (
            "; " + " and ".join(
                labels.role_confirmation_label(status) for status in statuses
            )
            if statuses
            else ""
        )
        bullets.append(f"{item.current_activity}: {roles}{suffix}.")
        technical.append(
            f"Internal step ID: {item.step_id}"
            + (
                " · Role confirmation status: " + ", ".join(statuses)
                if statuses
                else ""
            )
        )
    return [
        ReportViewBlock(
            bullets=tuple(bullets),
            origin=PlanningOrigin.DERIVED_PLANNING_GUIDANCE,
            technical_details=tuple(technical),
        )
    ]


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


def _gap_bullet(gap: InformationGap) -> str:
    """Prefer the evidence-bounded business phrasing; keep the message otherwise."""

    return gap_business_statement(gap) or gap.message


def _replaced_messages(gaps: list[InformationGap]) -> list[str]:
    """Authoritative messages whose business restatement replaced them."""

    return [
        f"Source record: {gap.message}"
        for gap in gaps
        if gap_business_statement(gap) is not None
    ]


def _missing_information(
    package: DecisionSupportPackage, source: ReportSection
) -> list[ReportViewBlock]:
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
        common_bullets, common_sources = _group_common_gaps(common)
        blocks.append(
            ReportViewBlock(
                heading="Process-wide/common gaps",
                paragraphs=(
                    f"These gaps apply consistently across all {len(items)} assessed activities.",
                ),
                bullets=tuple(common_bullets),
                origin=PlanningOrigin.ASSESSMENT_FINDING,
                technical_details=(
                    "Underlying package records retained: "
                    f"{sum(len(values) for values in grouped.values() if {gap.step_id for gap in values} == step_ids)} "
                    "per-step gaps.",
                )
                + tuple(common_sources),
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
                    bullets=tuple(_gap_bullet(gap) for gap in differences),
                    origin=PlanningOrigin.ASSESSMENT_FINDING,
                    technical_details=(f"Internal step ID: {item.step_id}",)
                    + tuple(_replaced_messages(differences)),
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


def _group_common_gaps(
    gaps: list[InformationGap],
) -> tuple[list[str], list[str]]:
    """Return the consolidated bullets and the source records they replaced."""
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
    remaining = [gap for gap in gaps if gap.field_name not in consumed]
    bullets.extend(_gap_bullet(gap) for gap in remaining)
    return bullets, _replaced_messages(remaining)


def _governance(
    package: DecisionSupportPackage, source: ReportSection
) -> list[ReportViewBlock]:
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


def _roadmap(
    package: DecisionSupportPackage, source: ReportSection
) -> list[ReportViewBlock]:
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
                    f"Status: {labels.roadmap_status_label(item.status.value)}",
                    item.rationale,
                ),
                bullets=stage_summary,
                origin=PlanningOrigin.DERIVED_PLANNING_GUIDANCE,
                technical_details=(
                    f"Internal step ID: {item.step_id}",
                    f"Roadmap status: {item.status.value}",
                ),
            )
        )
    return blocks


def _evidence_appendix(
    package: DecisionSupportPackage, source: ReportSection
) -> list[ReportViewBlock]:
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

"""Rendering-independent report content assembled from package components."""

from collections import Counter

from ai_adoption_engine.models.decision_support import (
    AdoptionRoadmap,
    DecisionReportContent,
    FutureStateStatus,
    MethodologyDisclosure,
    OpportunityPortfolio,
    PackageCompleteness,
    PlanningOrigin,
    ProposedFutureStateWorkflow,
    ReportSection,
    ReportSectionId,
    ReportStatement,
    RiskGovernanceSummary,
)
from ai_adoption_engine.models.enums import PriorityStatus, RecommendationMode


ROI_UNAVAILABLE = "ROI / quantified benefit unavailable with current evidence."


def methodology_disclosure(
    policy_id: str, policy_version: str
) -> MethodologyDisclosure:
    return MethodologyDisclosure(
        policy_id=policy_id,
        policy_version=policy_version,
        disclosure_statements=[
            "decision_policy.v0.2 is provisional and is not yet academically validated.",
            "This output is decision support, not guaranteed implementation advice.",
            "The proposed future state is PROPOSED / NOT DEPLOYED.",
            (
                "Production implementation requires further technical, security, governance, "
                "legal, and organisational review."
            ),
        ],
    )


def _statement(
    text: str,
    *,
    origin: PlanningOrigin,
    step_ids: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    reviewed_origins=None,
) -> ReportStatement:
    return ReportStatement(
        text=text,
        origin=origin,
        step_ids=step_ids or [],
        evidence_ids=evidence_ids or [],
        reviewed_origins=reviewed_origins or [],
    )


def build_report(
    *,
    process_name: str,
    completeness: PackageCompleteness,
    portfolio: OpportunityPortfolio,
    future_state: ProposedFutureStateWorkflow,
    roadmap: AdoptionRoadmap,
    governance: RiskGovernanceSummary,
    methodology: MethodologyDisclosure,
) -> DecisionReportContent:
    counts = Counter(item.recommendation_mode for item in portfolio.items)
    executive = [
        _statement(
            (
                f"{len(portfolio.items)} process steps were assessed: "
                + ", ".join(
                    f"{mode.value}={counts[mode]}" for mode in RecommendationMode
                )
                + f". Package completeness is {completeness.value}."
            ),
            origin=PlanningOrigin.ASSESSMENT_FINDING,
            step_ids=[item.step_id for item in portfolio.items],
        ),
        _statement(ROI_UNAVAILABLE, origin=PlanningOrigin.ASSESSMENT_FINDING),
    ]
    process = [
        _statement(
            f"The assessed current-state process is {process_name}.",
            origin=PlanningOrigin.ASSESSMENT_FINDING,
            step_ids=[item.step_id for item in portfolio.items],
        )
    ]
    opportunity_statements = [
        _statement(
            f"{item.current_activity}: {item.recommendation_mode.value}.",
            origin=PlanningOrigin.ASSESSMENT_FINDING,
            step_ids=[item.step_id],
            evidence_ids=[
                reference.evidence_id
                for reference in item.source_traceability.activity.evidence
            ],
            reviewed_origins=[item.source_traceability.activity.origin],
        )
        for item in portfolio.items
    ]
    prioritised = sorted(
        (
            item
            for item in portfolio.items
            if item.priority_status is PriorityStatus.COMPLETE and item.priority
        ),
        key=lambda item: (-item.priority.score, item.sequence),
    )
    highest = (
        [
            _statement(
                f"{item.current_activity}: priority {item.priority.score:.2f} ({item.priority.band.value}).",
                origin=PlanningOrigin.ASSESSMENT_FINDING,
                step_ids=[item.step_id],
            )
            for item in prioritised
        ]
        or [
            _statement(
                "No complete qualifying priority score is currently available.",
                origin=PlanningOrigin.ASSESSMENT_FINDING,
            )
        ]
    )
    investigations = [
        _statement(
            f"{item.current_activity} requires further investigation before adoption.",
            origin=PlanningOrigin.ASSESSMENT_FINDING,
            step_ids=[item.step_id],
        )
        for item in portfolio.items
        if item.recommendation_mode is RecommendationMode.INVESTIGATE_FURTHER
    ] or [
        _statement(
            "No step currently has an INVESTIGATE_FURTHER recommendation.",
            origin=PlanningOrigin.ASSESSMENT_FINDING,
        )
    ]
    not_recommended = [
        _statement(
            f"AI is not recommended for {item.current_activity} under the current evidence and policy.",
            origin=PlanningOrigin.ASSESSMENT_FINDING,
            step_ids=[item.step_id],
        )
        for item in portfolio.items
        if item.recommendation_mode is RecommendationMode.DO_NOT_RECOMMEND
    ] or [
        _statement(
            "No step currently has a DO_NOT_RECOMMEND outcome.",
            origin=PlanningOrigin.ASSESSMENT_FINDING,
        )
    ]
    future = [
        _statement(
            f"{item.proposed_activity} [{item.intervention_type.value}].",
            origin=PlanningOrigin.DERIVED_PLANNING_GUIDANCE,
            step_ids=[item.source_step_id],
        )
        for item in future_state.steps
    ]
    roles = [
        _statement(
            f"{item.current_activity}: "
            + ", ".join(role.role_type.value for role in item.recommended_human_roles)
            + "; organisational assignment NEEDS_CONFIRMATION.",
            origin=PlanningOrigin.DERIVED_PLANNING_GUIDANCE,
            step_ids=[item.step_id],
        )
        for item in portfolio.items
    ]
    risks = [
        _statement(
            item.statement,
            origin=PlanningOrigin.DERIVED_PLANNING_GUIDANCE,
            step_ids=[item.step_id],
            evidence_ids=item.basis.evidence_ids,
            reviewed_origins=item.basis.reviewed_origins,
        )
        for item in governance.considerations
    ]
    roadmap_statements = [
        _statement(
            f"{item.step_id}: {item.status.value}; {item.rationale}",
            origin=PlanningOrigin.DERIVED_PLANNING_GUIDANCE,
            step_ids=[item.step_id],
        )
        for item in roadmap.opportunities
    ]
    gaps = [
        _statement(
            gap.message,
            origin=PlanningOrigin.ASSESSMENT_FINDING,
            step_ids=[gap.step_id],
            evidence_ids=gap.basis.evidence_ids,
            reviewed_origins=gap.basis.reviewed_origins,
        )
        for item in portfolio.items
        for gap in item.missing_information
    ] or [
        _statement(
            "No material package-level information gap was identified.",
            origin=PlanningOrigin.ASSESSMENT_FINDING,
        )
    ]
    disclosure = [
        _statement(text, origin=PlanningOrigin.ASSESSMENT_FINDING)
        for text in methodology.disclosure_statements
    ]
    evidence = [
        _statement(
            (
                f"{reference.evidence_id}: {reference.document_id} / "
                f"{reference.block_id} / {reference.source_locator}."
            ),
            origin=PlanningOrigin.ASSESSMENT_FINDING,
            evidence_ids=[reference.evidence_id],
        )
        for item in portfolio.items
        for reference in item.source_traceability.activity.evidence
    ] or [
        _statement(
            "No activity evidence reference is available in the package appendix.",
            origin=PlanningOrigin.ASSESSMENT_FINDING,
        )
    ]
    sections = [
        (ReportSectionId.EXECUTIVE_SUMMARY, "Executive summary", executive),
        (ReportSectionId.PROCESS_ASSESSED, "Process assessed", process),
        (ReportSectionId.OPPORTUNITY_PORTFOLIO, "AI opportunity portfolio", opportunity_statements),
        (ReportSectionId.HIGHEST_PRIORITY, "Highest-priority opportunities", highest),
        (ReportSectionId.REQUIRES_INVESTIGATION, "Opportunities requiring further investigation", investigations),
        (ReportSectionId.NOT_RECOMMENDED, "AI use not recommended", not_recommended),
        (ReportSectionId.FUTURE_STATE, "Proposed future-state workflow", future),
        (ReportSectionId.HUMAN_ROLES, "Human roles and controls", roles),
        (ReportSectionId.RISKS_GOVERNANCE, "Risks and governance considerations", risks),
        (ReportSectionId.ADOPTION_ROADMAP, "Adoption roadmap", roadmap_statements),
        (ReportSectionId.MISSING_INFORMATION, "Missing information", gaps),
        (ReportSectionId.METHODOLOGY, "Methodology and policy disclosure", disclosure),
        (ReportSectionId.EVIDENCE_APPENDIX, "Evidence and traceability appendix", evidence),
    ]
    return DecisionReportContent(
        sections=[
            ReportSection(
                section_id=section_id,
                title=title,
                statements=statements,
                item_references=sorted(
                    {step_id for statement in statements for step_id in statement.step_ids}
                ),
            )
            for section_id, title, statements in sections
        ]
    )

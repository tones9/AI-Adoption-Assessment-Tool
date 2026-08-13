"""Recommendation-specific adoption roadmap with explicit decision points."""

from ai_adoption_engine.decision_support.portfolio import planning_basis
from ai_adoption_engine.models.decision_support import (
    AdoptionRoadmap,
    OpportunityPortfolio,
    OpportunityRoadmap,
    RoadmapStage,
    RoadmapStageType,
    RoadmapStatus,
)
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState, RecommendationMode


def _stage(
    item,
    sequence: int,
    stage_type: RoadmapStageType,
    objective: str,
    *,
    decision: bool = False,
) -> RoadmapStage:
    return RoadmapStage(
        sequence=sequence,
        stage_type=stage_type,
        objective=objective,
        decision_point=decision,
        possible_outcomes=["GO", "REVISE", "STOP"] if decision else [],
        basis=planning_basis(item.source_traceability),
    )


def _qualifying_stages(item) -> list[RoadmapStage]:
    specs = [
        (
            RoadmapStageType.OPPORTUNITY_VALIDATION,
            "Validate the opportunity, intended outcome, and business case.",
            False,
        )
    ]
    data_readiness = next(
        criterion
        for criterion in item.source_traceability.criteria
        if "data_readiness]" in criterion.review_field_path
    )
    if data_readiness.knowledge_state is not KnowledgeState.KNOWN:
        specs.append(
            (
                RoadmapStageType.DATA_READINESS_VALIDATION,
                "Validate data availability, quality, access, provenance, and permitted use.",
                False,
            )
        )
    specs.extend(
        [
            (
                RoadmapStageType.PROOF_OF_CONCEPT,
                "Test technical feasibility and expected qualitative benefits in a bounded proof of concept.",
                False,
            ),
            (
                RoadmapStageType.GO_REVISE_STOP_DECISION,
                "Decide whether evidence supports progression, revision, or stopping.",
                True,
            ),
            (
                RoadmapStageType.CONTROLLED_PILOT,
                "Run a controlled pilot with defined success, failure, and rollback criteria.",
                False,
            ),
            (
                RoadmapStageType.HUMAN_CONTROL_EVALUATION,
                "Validate human review, exception handling, accountability, and escalation controls.",
                False,
            ),
            (
                RoadmapStageType.GOVERNANCE_SECURITY_REVIEW,
                "Obtain required organisational, security, privacy, legal, and governance review.",
                False,
            ),
            (
                RoadmapStageType.DEPLOYMENT_DECISION,
                "Make an explicit deployment decision; pilot success does not require deployment.",
                True,
            ),
            (
                RoadmapStageType.INTEGRATION_PLANNING,
                "Plan integration only after a positive controlled deployment decision.",
                False,
            ),
            (
                RoadmapStageType.PRODUCTION_MONITORING,
                "Define ongoing performance, risk, exception, and human-oversight monitoring.",
                False,
            ),
        ]
    )
    return [
        _stage(item, index, stage_type, objective, decision=decision)
        for index, (stage_type, objective, decision) in enumerate(specs, start=1)
    ]


def _investigation_stages(item) -> list[RoadmapStage]:
    specs = [
        (
            RoadmapStageType.INFORMATION_GATHERING,
            "Gather the missing recommendation and planning evidence identified in the assessment.",
            False,
        ),
        (
            RoadmapStageType.FEASIBILITY_VALIDATION,
            "Validate technical fit, business value, risk, autonomy, and capability assumptions as applicable.",
            False,
        ),
        (
            RoadmapStageType.GO_REVISE_STOP_DECISION,
            "Reassess whether to explore a bounded proof of concept, revise the opportunity, or stop.",
            True,
        ),
    ]
    return [
        _stage(item, index, stage_type, objective, decision=decision)
        for index, (stage_type, objective, decision) in enumerate(specs, start=1)
    ]


def build_roadmap(portfolio: OpportunityPortfolio) -> AdoptionRoadmap:
    opportunities = []
    for item in portfolio.items:
        if item.recommendation_mode in {
            RecommendationMode.AUTOMATE,
            RecommendationMode.AUGMENT,
        }:
            opportunities.append(
                OpportunityRoadmap(
                    step_id=item.step_id,
                    recommendation_mode=item.recommendation_mode,
                    status=RoadmapStatus.QUALIFYING_OPPORTUNITY,
                    stages=_qualifying_stages(item),
                    rationale=(
                        "The assessment qualifies this opportunity for controlled validation; "
                        "each decision point may result in GO, REVISE, or STOP."
                    ),
                )
            )
        elif item.recommendation_mode is RecommendationMode.INVESTIGATE_FURTHER:
            opportunities.append(
                OpportunityRoadmap(
                    step_id=item.step_id,
                    recommendation_mode=item.recommendation_mode,
                    status=RoadmapStatus.INVESTIGATION_ONLY,
                    stages=_investigation_stages(item),
                    rationale=(
                        "Evidence and feasibility must be resolved before implementation planning."
                    ),
                )
            )
        else:
            opportunities.append(
                OpportunityRoadmap(
                    step_id=item.step_id,
                    recommendation_mode=item.recommendation_mode,
                    status=RoadmapStatus.AI_DEPLOYMENT_NOT_APPLICABLE,
                    stages=[],
                    rationale=(
                        "The assessment does not recommend AI; no AI-deployment roadmap is generated."
                    ),
                )
            )
    return AdoptionRoadmap(opportunities=opportunities)

"""Evidence-aware risk and governance summary generation."""

from ai_adoption_engine.decision_support.portfolio import planning_basis
from ai_adoption_engine.models.assessment import StepAssessment
from ai_adoption_engine.models.decision_support import (
    GovernanceCategory,
    GovernanceConsideration,
    OpportunityPortfolio,
    RiskGovernanceSummary,
)
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState, RecommendationMode


_CRITERION_CATEGORIES = {
    CriterionName.RISK_CONSEQUENCE: GovernanceCategory.CONSEQUENCE_OF_ERROR,
    CriterionName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT: (
        GovernanceCategory.CONSEQUENCE_OF_ERROR
    ),
    CriterionName.HUMAN_JUDGEMENT_REQUIREMENT: GovernanceCategory.HUMAN_JUDGEMENT,
    CriterionName.DATA_READINESS: GovernanceCategory.DATA_READINESS,
}


def build_governance(
    portfolio: OpportunityPortfolio,
    assessments: list[StepAssessment],
) -> RiskGovernanceSummary:
    considerations = []
    for item, assessment in zip(portfolio.items, assessments, strict=True):
        trace = item.source_traceability
        criterion_traces = {
            assessed.criterion: traced
            for assessed, traced in zip(
                assessment.criteria, trace.criteria, strict=True
            )
        }
        criterion_values = {value.criterion: value for value in assessment.criteria}
        for criterion_name, category in _CRITERION_CATEGORIES.items():
            criterion = criterion_values[criterion_name]
            value_trace = criterion_traces[criterion_name]
            if criterion.value is None:
                statement = (
                    f"{criterion_name.value} evidence is unavailable and requires validation."
                )
            else:
                statement = (
                    f"The assessed {criterion_name.value} value is {criterion.value}/5 "
                    f"with {criterion.knowledge_state.value} knowledge state; the organisation "
                    "should validate its implications before any deployment decision."
                )
            considerations.append(
                GovernanceConsideration(
                    consideration_id=f"{item.step_id}:{criterion_name.value}",
                    step_id=item.step_id,
                    category=category,
                    statement=statement,
                    requires_review=True,
                    basis=planning_basis(
                        trace,
                        assessment_paths=[
                            value_trace.assessment_field_path
                            or trace.assessment_step_path
                        ],
                        review_paths=[value_trace.review_field_path],
                        evidence_ids=[
                            reference.evidence_id for reference in value_trace.evidence
                        ],
                    ),
                )
            )
        accountability = assessment.human_accountability
        accountability_statement = (
            "Human accountability requirements are unknown and require validation."
            if accountability.knowledge_state is KnowledgeState.UNKNOWN
            else (
                "Human accountability is recorded as required; the accountable role and "
                "authority must be confirmed."
                if accountability.value is True
                else (
                    "Human accountability is recorded as not required for this assessment "
                    "input; organisational ownership should still be confirmed."
                )
            )
        )
        considerations.append(
            GovernanceConsideration(
                consideration_id=f"{item.step_id}:accountability",
                step_id=item.step_id,
                category=GovernanceCategory.ACCOUNTABILITY,
                statement=accountability_statement,
                requires_review=True,
                basis=planning_basis(
                    trace,
                    assessment_paths=[
                        trace.human_accountability.assessment_field_path
                        or trace.assessment_step_path
                    ],
                    review_paths=[trace.human_accountability.review_field_path],
                ),
            )
        )
        if item.recommendation_mode in {
            RecommendationMode.AUTOMATE,
            RecommendationMode.AUGMENT,
        }:
            considerations.extend(
                [
                    GovernanceConsideration(
                        consideration_id=f"{item.step_id}:human-oversight",
                        step_id=item.step_id,
                        category=GovernanceCategory.HUMAN_OVERSIGHT,
                        statement=(
                            "Human review, exception handling, escalation, and accountability "
                            "controls require validation before deployment."
                        ),
                        requires_review=True,
                        basis=planning_basis(trace),
                    ),
                    GovernanceConsideration(
                        consideration_id=f"{item.step_id}:privacy-security",
                        step_id=item.step_id,
                        category=GovernanceCategory.PRIVACY_SECURITY,
                        statement=(
                            "Privacy and security implications require organisational assessment; "
                            "no compliance or security approval is asserted."
                        ),
                        requires_review=True,
                        basis=planning_basis(trace),
                    ),
                    GovernanceConsideration(
                        consideration_id=f"{item.step_id}:legal-organisational",
                        step_id=item.step_id,
                        category=GovernanceCategory.LEGAL_ORGANISATIONAL,
                        statement=(
                            "Technical, legal, governance, ethical, and organisational review "
                            "is required before a production decision."
                        ),
                        requires_review=True,
                        basis=planning_basis(trace),
                    ),
                ]
            )
        elif item.recommendation_mode is RecommendationMode.INVESTIGATE_FURTHER:
            considerations.append(
                GovernanceConsideration(
                    consideration_id=f"{item.step_id}:investigation-controls",
                    step_id=item.step_id,
                    category=GovernanceCategory.MISSING_EVIDENCE,
                    statement=(
                        "Evidence and feasibility require validation before any pilot or "
                        "deployment-oriented governance conclusion."
                    ),
                    requires_review=True,
                    basis=planning_basis(trace),
                )
            )
    return RiskGovernanceSummary(considerations=considerations)

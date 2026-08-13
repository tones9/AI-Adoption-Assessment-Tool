import pytest

from ai_adoption_engine.decision.policy import DecisionPolicy
from ai_adoption_engine.decision.scoring import calculate_priority
from ai_adoption_engine.models.enums import CriterionName, PriorityBand
from ai_adoption_engine.models.process import BusinessProcess


def test_priority_score_matches_transparent_weighting(
    process: BusinessProcess, policy: DecisionPolicy
) -> None:
    score = calculate_priority(process.steps[0], policy)
    assert score.score == pytest.approx(82.0)
    assert score.band is PriorityBand.HIGH
    assert sum(component.contribution for component in score.components) == pytest.approx(
        score.score
    )


def test_unfavourable_criteria_are_inverted(
    process: BusinessProcess, policy: DecisionPolicy
) -> None:
    score = calculate_priority(process.steps[0], policy)
    risk = next(
        component
        for component in score.components
        if component.criterion is CriterionName.RISK_CONSEQUENCE
    )
    complexity_item = next(
        component
        for component in score.components
        if component.criterion is CriterionName.IMPLEMENTATION_COMPLEXITY
    )
    assert risk.raw_value == 2 and risk.favourable_value == 3
    assert complexity_item.raw_value == 2 and complexity_item.favourable_value == 3


import pytest
from pydantic import ValidationError

from ai_adoption_engine.decision.policy import (
    PROVISIONAL_STATUS,
    DecisionPolicy,
)
from ai_adoption_engine.models.enums import CriterionName, RecommendationMode


def test_policy_is_explicitly_provisional(policy: DecisionPolicy) -> None:
    assert policy.policy_id == "decision_policy.v0.2"
    assert policy.status == PROVISIONAL_STATUS
    assert set(policy.scale.criteria) == set(CriterionName)
    assert set(policy.scoring.eligible_recommendations) == {
        RecommendationMode.AUTOMATE,
        RecommendationMode.AUGMENT,
    }
    assert policy.evidence.material_by_gate
    assert policy.evidence.conditional_by_gate


def test_policy_weights_sum_to_one(policy: DecisionPolicy) -> None:
    assert sum(item.weight for item in policy.scoring.criteria.values()) == pytest.approx(1.0)


def test_policy_rejects_non_normalised_weights(policy: DecisionPolicy) -> None:
    raw = policy.model_dump(mode="json")
    raw["scoring"]["criteria"]["business_value"]["weight"] = 0.20
    with pytest.raises(ValidationError, match="weights must sum to 1.0"):
        DecisionPolicy.model_validate(raw)

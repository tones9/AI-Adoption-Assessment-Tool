import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_adoption_engine.decision.four_gate_policy import (
    PROVISIONAL_STATUS,
    FourGateDecisionPolicy,
    load_four_gate_policy,
)
from ai_adoption_engine.decision.policy import load_policy
from ai_adoption_engine.models.enums import CriterionName
from ai_adoption_engine.models.four_gate_assessment import FourGateName, OutcomeCode

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SUCCESSOR_POLICY_PATH = PROJECT_ROOT / "config" / "decision_policy.v0.3.json"
LEGACY_POLICY_PATH = PROJECT_ROOT / "config" / "decision_policy.v0.2.json"


def test_successor_policy_has_exact_identity_and_provisional_status() -> None:
    policy = load_four_gate_policy(SUCCESSOR_POLICY_PATH)

    assert policy.policy_id == "decision_policy.v0.3"
    assert policy.version == "0.3.0"
    assert policy.framework_id == "four-gate-framework.v0.1"
    assert policy.framework_version == "0.1"
    assert policy.decision_contract_version == "phase1-v0.4"
    assert policy.status == PROVISIONAL_STATUS
    assert set(policy.scale.criteria) == set(CriterionName)
    assert set(policy.scoring.eligible_outcomes) == {
        OutcomeCode.AI_AUTOMATION,
        OutcomeCode.AI_ASSISTED_WORK,
    }
    assert policy.gates.maximum_implementation_complexity_for_readiness == 4
    assert sum(
        item.weight for item in policy.scoring.criteria.values()
    ) == pytest.approx(1.0)


def test_successor_policy_rejects_contract_or_weight_drift() -> None:
    policy = load_four_gate_policy(SUCCESSOR_POLICY_PATH)
    wrong_contract = policy.model_dump(mode="json")
    wrong_contract["decision_contract_version"] = "phase1-v0.3"
    with pytest.raises(ValidationError):
        FourGateDecisionPolicy.model_validate(wrong_contract)

    wrong_weights = policy.model_dump(mode="json")
    wrong_weights["scoring"]["criteria"]["business_value"]["weight"] = 0.20
    with pytest.raises(ValidationError, match="weights must sum to 1.0"):
        FourGateDecisionPolicy.model_validate(wrong_weights)

    wrong_gate_four_materiality = policy.model_dump(mode="json")
    wrong_gate_four_materiality["evidence"]["conditional_by_gate"][
        FourGateName.SAFE_AUTONOMY.value
    ].append(CriterionName.DATA_READINESS.value)
    with pytest.raises(ValidationError, match="Conditional materiality"):
        FourGateDecisionPolicy.model_validate(wrong_gate_four_materiality)


def test_legacy_and_successor_loaders_fail_closed_across_versions() -> None:
    with pytest.raises(ValidationError):
        load_policy(SUCCESSOR_POLICY_PATH)
    with pytest.raises(ValidationError):
        load_four_gate_policy(LEGACY_POLICY_PATH)


def test_policy_json_carries_no_unapproved_dimension() -> None:
    raw = json.loads(SUCCESSOR_POLICY_PATH.read_text(encoding="utf-8"))

    assert "strategic_criticality" not in json.dumps(raw)
    assert set(raw["scale"]["criteria"]) == {item.value for item in CriterionName}
    assert CriterionName.DATA_READINESS.value not in raw["evidence"][
        "conditional_by_gate"
    ][FourGateName.SAFE_AUTONOMY.value]

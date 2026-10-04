import inspect

import ai_adoption_engine.preliminary.rules as rules_module
from ai_adoption_engine.models.preliminary_assessment import (
    PreliminaryDecidingRuleCode,
    PreliminaryInputName,
)
from ai_adoption_engine.preliminary.rules import PRELIMINARY_EVALUATOR_RULES_V0_1


def test_rule_set_has_separate_stable_identity_and_fingerprint() -> None:
    rules = PRELIMINARY_EVALUATOR_RULES_V0_1
    reference = rules.reference()

    assert reference.rule_set_id == "preliminary-evaluator-rules.v0.1"
    assert reference.rule_set_version == "0.1.0"
    assert reference.rule_set_status == "PROVISIONAL CONTINUITY — NOT VALIDATED"
    assert (
        rules.threshold_basis
        == "PROVISIONAL CONTINUITY — NOT VALIDATION OR EQUIVALENCE"
    )
    assert reference.rule_set_fingerprint == rules.fingerprint()
    assert len(reference.rule_set_fingerprint) == 64
    assert rules.fingerprint() == PRELIMINARY_EVALUATOR_RULES_V0_1.fingerprint()


def test_rule_set_contains_every_code_and_activity_identity_manifest() -> None:
    rules = PRELIMINARY_EVALUATOR_RULES_V0_1

    assert {item.deciding_rule_code for item in rules.rules} == set(
        PreliminaryDecidingRuleCode
    )
    assert {item.deciding_rule_code for item in rules.material_manifests} == set(
        PreliminaryDecidingRuleCode
    )
    assert all(
        PreliminaryInputName.ACTIVITY_IDENTITY in item.required_all
        for item in rules.material_manifests
    )


def test_rule_fingerprint_changes_with_rule_content() -> None:
    changed = PRELIMINARY_EVALUATOR_RULES_V0_1.model_copy(
        update={"human_supplied_treatment": "NOT_CONTEXT_ONLY"}
    )

    assert changed.fingerprint() != PRELIMINARY_EVALUATOR_RULES_V0_1.fingerprint()


def test_preliminary_rules_do_not_import_formal_decision_contracts() -> None:
    source = inspect.getsource(rules_module)

    assert "four_gate" not in source
    assert "OutcomeCode" not in source
    assert "DecisionPackage" not in source
    assert "decision_policy" not in source

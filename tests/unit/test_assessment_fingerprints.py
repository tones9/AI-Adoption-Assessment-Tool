from ai_adoption_engine.application.fingerprints import (
    fingerprint_business_process,
    fingerprint_decision_policy,
)
from ai_adoption_engine.decision.policy import DecisionPolicy
from ai_adoption_engine.models.process import BusinessProcess


def test_identical_process_content_has_identical_fingerprint(
    process: BusinessProcess,
) -> None:
    duplicate = BusinessProcess.model_validate(process.model_dump(mode="json"))
    assert fingerprint_business_process(process) == fingerprint_business_process(
        duplicate
    )


def test_meaningful_process_change_changes_fingerprint(
    process: BusinessProcess,
) -> None:
    changed = process.model_copy(update={"name": "Changed process name"}, deep=True)
    assert fingerprint_business_process(process) != fingerprint_business_process(changed)


def test_run_derived_process_id_does_not_affect_fingerprint(
    process: BusinessProcess,
) -> None:
    changed_run_id = process.model_copy(
        update={"process_id": "validated-another-extraction-run"}, deep=True
    )
    assert fingerprint_business_process(process) == fingerprint_business_process(
        changed_run_id
    )


def test_identical_policy_content_has_identical_fingerprint(
    policy: DecisionPolicy,
) -> None:
    duplicate = DecisionPolicy.model_validate(policy.model_dump(mode="json"))
    assert fingerprint_decision_policy(policy) == fingerprint_decision_policy(duplicate)


def test_meaningful_policy_change_changes_fingerprint(
    policy: DecisionPolicy,
) -> None:
    raw = policy.model_dump(mode="json")
    current = raw["gates"]["minimum_business_value"]
    raw["gates"]["minimum_business_value"] = 4 if current != 4 else 3
    changed = DecisionPolicy.model_validate(raw)
    assert fingerprint_decision_policy(policy) != fingerprint_decision_policy(changed)

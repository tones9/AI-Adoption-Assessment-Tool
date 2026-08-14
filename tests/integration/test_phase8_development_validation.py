from evaluation.harness.development_validation import validate_development_cases


def test_development_harness_validates_without_api_calls() -> None:
    report = validate_development_cases()
    assert report["api_calls"] == 0
    assert report["confirmatory_runs"] == 0
    assert report["results"]["DEV-001"]["packet_verified"] is True
    assert report["results"]["DEV-002"]["extraction"]["activity"]["f1"] == .75
    assert report["results"]["frozen_engine_smoke"]["policy_id"] == "decision_policy.v0.2"

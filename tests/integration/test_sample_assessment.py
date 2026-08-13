import json

from ai_adoption_engine.cli import main


def test_diagnostic_cli_emits_complete_assessment(capsys) -> None:
    exit_code = main(["--compact"])
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["policy_id"] == "decision_policy.v0.1"
    assert output["process_id"] == "sample-customer-complaints-v1"
    assert len(output["step_assessments"]) == 5
    assert {
        item["recommendation_mode"] for item in output["step_assessments"]
    } == {
        "AUTOMATE",
        "AUGMENT",
        "INVESTIGATE_FURTHER",
        "DO_NOT_RECOMMEND",
    }


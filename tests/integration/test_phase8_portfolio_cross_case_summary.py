from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PORTFOLIO = ROOT / "evaluation" / "portfolio"
SUMMARY_PATH = PORTFOLIO / "cross_case_summary.v0.1.json"
CASES = ("PORT-001", "PORT-002", "PORT-003")


def _summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text())


def _case_files(case_id: str) -> tuple[dict, dict]:
    slug = case_id.lower()
    run = PORTFOLIO / "runs" / slug / "production-run-v0.1"
    comparison = json.loads(
        (run / "comparison" / "retrospective_comparison.v0.1.json").read_text()
    )
    manifest = json.loads((run / "output_freeze_manifest.v0.1.json").read_text())
    return comparison, manifest


def test_cross_case_summary_covers_every_portfolio_case() -> None:
    summary = _summary()
    register = json.loads((PORTFOLIO / "register.v0.1.json").read_text())
    registered = [case["case_id"] for case in register["cases"]]

    assert summary["case_count"] == len(registered) == 3
    assert [item["case_id"] for item in summary["per_case"]] == registered
    assert [item["case_id"] for item in summary["derived_from"]] == registered
    for entry in summary["derived_from"]:
        assert (ROOT / entry["comparison_path"]).is_file()
        assert (ROOT / entry["output_freeze_manifest_path"]).is_file()


def test_cross_case_per_case_numbers_match_the_frozen_case_artefacts() -> None:
    summary = _summary()
    by_case = {item["case_id"]: item for item in summary["per_case"]}

    for case_id in CASES:
        comparison, manifest = _case_files(case_id)
        entry = by_case[case_id]

        assert entry["alignment"] == comparison["alignment_counts"], case_id
        assert entry["themes"] == len(comparison["themes"]), case_id
        assert (
            entry["unsupported_activities_added"]
            == comparison["process_reconstruction"]["unsupported_steps_added"]
        ), case_id

        outcome = manifest["product_outcome"]
        assert entry["recommendations"] == outcome["recommendation_distribution"], case_id
        assert entry["activities"] == outcome["candidate_step_count"], case_id


def test_cross_case_review_counts_match_each_frozen_run_state() -> None:
    summary = _summary()
    by_case = {item["case_id"]: item for item in summary["per_case"]}

    for case_id in CASES:
        run = PORTFOLIO / "runs" / case_id.lower() / "production-run-v0.1"
        final_state = json.loads((run / "final_run_state.json").read_text())
        assert (
            by_case[case_id]["review_event_counts"]
            == final_state["review_event_counts"]
        ), case_id


def test_cross_case_aggregates_are_arithmetically_correct() -> None:
    summary = _summary()
    aggregates = summary["aggregates"]

    alignment: Counter[str] = Counter()
    recommendations: Counter[str] = Counter()
    activities = 0
    themes = 0
    unknowns = 0
    corrections = 0
    rejections = 0

    for case_id in CASES:
        comparison, manifest = _case_files(case_id)
        alignment.update(comparison["alignment_counts"])
        recommendations.update(manifest["product_outcome"]["recommendation_distribution"])
        activities += manifest["product_outcome"]["candidate_step_count"]
        themes += len(comparison["themes"])

        run = PORTFOLIO / "runs" / case_id.lower() / "production-run-v0.1"
        counts = json.loads((run / "final_run_state.json").read_text())[
            "review_event_counts"
        ]
        unknowns += counts.get("retain-unknown", 0)
        corrections += counts.get("correct", 0)
        rejections += counts.get("reject", 0)

    assert aggregates["total_activities_assessed"] == activities == 16
    assert aggregates["total_intervention_themes"] == themes == 16
    assert aggregates["alignment"] == dict(alignment)
    assert aggregates["recommendations"] == dict(recommendations)
    assert aggregates["total_unknowns_retained_by_review"] == unknowns
    assert aggregates["total_review_corrections"] == corrections
    assert aggregates["total_review_rejections"] == rejections
    assert aggregates["total_unsupported_activities_added"] == 0


def test_cross_case_capability_lists_match_the_frozen_assessments() -> None:
    summary = _summary()
    aggregates = summary["aggregates"]
    by_case = {item["case_id"]: item for item in summary["per_case"]}

    observed: set[str] = set()
    bearing = 0
    for case_id in CASES:
        run = PORTFOLIO / "runs" / case_id.lower() / "production-run-v0.1"
        integrated = json.loads((run / "integrated_assessment.json").read_text())
        case_capabilities: set[str] = set()
        for step in integrated["process_assessment"]["step_assessments"]:
            if step["capabilities"]:
                bearing += 1
            case_capabilities.update(step["capabilities"])
        assert set(by_case[case_id]["capabilities_identified"]) == case_capabilities, case_id
        observed |= case_capabilities

    assert set(aggregates["distinct_capabilities_exercised"]) == observed
    assert aggregates["capability_bearing_activities"] == bearing == 8

    from ai_adoption_engine.models.enums import Capability

    every = {item.value for item in Capability}
    assert set(aggregates["capabilities_never_exercised"]) == every - observed


def test_cross_case_summary_reports_the_degenerate_recommendation_limitation() -> None:
    """The headline honesty check: the engine returned one value in every case."""

    summary = _summary()
    assert summary["aggregates"]["recommendations"]["INVESTIGATE_FURTHER"] == 16
    for mode in ("AUTOMATE", "AUGMENT", "DO_NOT_RECOMMEND"):
        assert summary["aggregates"]["recommendations"][mode] == 0

    findings = {item["finding_id"]: item for item in summary["findings"]}
    assert findings["XC-2"]["strength"] == "MATERIAL_LIMITATION"
    assert findings["XC-7"]["strength"] == "MATERIAL_LIMITATION"
    assert "not meaningfully exercised" in summary["honest_headline"]

    markdown = (PORTFOLIO / "cross_case_summary.v0.1.md").read_text()
    assert "never exercised by a real case" in markdown
    assert "specificity is unmeasured" in markdown.lower()


def test_cross_case_summary_scopes_the_policy_limitation_accurately() -> None:
    """The limitation is construct validity, not absent unit-test coverage.

    tests/unit exercises every recommendation mode, so claiming the policy is
    untested would overstate the finding and misdescribe the codebase.
    """

    summary = _summary()
    detail = next(
        item for item in summary["findings"] if item["finding_id"] == "XC-2"
    )
    assert "Policy logic is exercised by unit tests" in detail["detail"]
    assert "defensible on real processes" in detail["detail"]
    assert "scope_correction" in detail

    markdown = (PORTFOLIO / "cross_case_summary.v0.1.md").read_text()
    assert "policy logic is exercised by unit tests" in markdown.lower()
    assert "not whether policy judgements are defensible on real processes" in markdown

    # The claim above must stay true of the actual suite.
    unit_tests = "\n".join(
        path.read_text() for path in sorted((ROOT / "tests" / "unit").glob("*.py"))
    )
    for mode in ("AUTOMATE", "AUGMENT", "DO_NOT_RECOMMEND", "INVESTIGATE_FURTHER"):
        assert f"RecommendationMode.{mode}" in unit_tests, mode


def test_cross_case_summary_records_the_shared_unchanged_baseline() -> None:
    summary = _summary()
    baseline = summary["shared_production_baseline"]
    freeze = json.loads((PORTFOLIO / "freeze_manifest.v0.1.json").read_text())

    assert (
        baseline["production_subtree_fingerprint"]
        == freeze["production_baseline"]["production_subtree_fingerprint"]
    )
    for case_id in CASES:
        run = PORTFOLIO / "runs" / case_id.lower() / "production-run-v0.1"
        integrated = json.loads((run / "integrated_assessment.json").read_text())
        policy = integrated["policy"]
        assert policy["policy_id"] == baseline["decision_policy_id"], case_id
        assert policy["policy_version"] == baseline["decision_policy_version"], case_id
        assert (
            policy["decision_policy_fingerprint"]
            == baseline["decision_policy_fingerprint"]
        ), case_id

    integrity = summary["evaluation_integrity"]
    assert integrity["after_opened_only_after_output_freeze"] is True
    assert integrity["production_code_modified_during_evaluation"] is False
    assert integrity["policy_modified_during_evaluation"] is False
    assert integrity["capability_taxonomy_modified_during_evaluation"] is False
    assert integrity["reviewer_blindness_claimed_in_any_case"] is False
    assert integrity["operator_scripts_preserved"]["PORT-001"] is False
    assert integrity["operator_scripts_preserved"]["PORT-002"] is False
    assert integrity["operator_scripts_preserved"]["PORT-003"] is True

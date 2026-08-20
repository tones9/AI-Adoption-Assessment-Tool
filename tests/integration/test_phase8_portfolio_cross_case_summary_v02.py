from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PORTFOLIO = ROOT / "evaluation" / "portfolio"
SUMMARY_PATH = PORTFOLIO / "cross_case_summary.v0.2.json"
REGISTER_PATH = PORTFOLIO / "register.v0.3.json"
CASES = ("PORT-001", "PORT-002", "PORT-004")
COMPARISONS = {
    "PORT-001": PORTFOLIO
    / "runs"
    / "port-001"
    / "production-run-v0.1"
    / "comparison"
    / "retrospective_comparison.v0.1.json",
    "PORT-002": PORTFOLIO
    / "runs"
    / "port-002"
    / "production-run-v0.1"
    / "comparison"
    / "retrospective_comparison.v0.1.json",
    "PORT-004": PORTFOLIO
    / "runs"
    / "port-004"
    / "comparison"
    / "retrospective_comparison.v0.1.json",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _summary() -> dict:
    return _load(SUMMARY_PATH)


def test_v02_includes_only_valid_forward_cases_and_retains_port003_historically() -> None:
    summary = _summary()
    register = _load(REGISTER_PATH)

    assert tuple(summary["forward_analysis_case_ids"]) == CASES
    assert [case["case_id"] for case in summary["per_case"]] == list(CASES)
    assert "PORT-003" not in summary["forward_analysis_case_ids"]
    assert summary["evaluation_integrity"]["port003_counted_in_forward_aggregates"] is False

    port003 = next(case for case in register["cases"] if case["case_id"] == "PORT-003")
    assert port003["status"] == "SUPERSEDED_CONTAMINATED_BEFORE"
    assert port003["forward_analysis_included"] is False
    assert port003["superseded_by"] == "PORT-004"

    historical = _load(PORTFOLIO / "cross_case_summary.v0.1.json")
    assert historical["case_count"] == 3
    assert [case["case_id"] for case in historical["per_case"]] == [
        "PORT-001",
        "PORT-002",
        "PORT-003",
    ]


def test_v02_aggregates_are_rederived_from_the_three_included_comparisons() -> None:
    summary = _summary()
    aggregates = summary["aggregates"]

    alignment: Counter[str] = Counter()
    recommendations: Counter[str] = Counter()
    activities = 0
    themes = 0
    uncertainty = 0
    unsupported = 0

    for case_id in CASES:
        comparison = _load(COMPARISONS[case_id])
        alignment.update(comparison["alignment_counts"])
        recommendations.update(comparison["deterministic_recommendation"]["recommendation_distribution"])
        activities += comparison["process_reconstruction"]["retained_step_count"]
        themes += len(comparison["themes"])
        uncertainty += len(comparison["appropriate_uncertainty"])
        unsupported += comparison["process_reconstruction"]["unsupported_steps_added"]

    assert activities == aggregates["total_activities_assessed"] == 20
    assert themes == aggregates["total_intervention_themes"] == 13
    assert dict(alignment) == aggregates["alignment"] == {
        "STRONG_ALIGNMENT": 0,
        "PARTIAL_ALIGNMENT": 7,
        "NO_DOCUMENTED_ALIGNMENT": 6,
        "CONTRADICTION": 0,
    }
    assert dict(recommendations) == aggregates["recommendations"] == {
        "AUTOMATE": 0,
        "AUGMENT": 0,
        "INVESTIGATE_FURTHER": 20,
        "DO_NOT_RECOMMEND": 0,
    }
    assert uncertainty == aggregates["appropriate_uncertainty_findings"] == 6
    assert unsupported == aggregates["total_unsupported_activities_added"] == 0


def test_v02_capabilities_are_derived_from_frozen_assessments_without_port003() -> None:
    summary = _summary()
    by_case = {case["case_id"]: case for case in summary["per_case"]}

    assessment_paths = {
        "PORT-001": PORTFOLIO
        / "runs"
        / "port-001"
        / "production-run-v0.1"
        / "integrated_assessment.json",
        "PORT-002": PORTFOLIO
        / "runs"
        / "port-002"
        / "production-run-v0.1"
        / "integrated_assessment.json",
        "PORT-004": PORTFOLIO
        / "runs"
        / "port-004"
        / "production-run-v0.4-assessed"
        / "stage4-assessment-record.v0.1.json",
    }

    observed: set[str] = set()
    capability_bearing = 0
    for case_id, path in assessment_paths.items():
        data = _load(path)
        if case_id == "PORT-004":
            steps = data["observed_step_assessments"]
        else:
            steps = data["process_assessment"]["step_assessments"]
        case_capabilities = {capability for step in steps for capability in step["capabilities"]}
        case_bearing = sum(bool(step["capabilities"]) for step in steps)
        assert set(by_case[case_id]["capabilities_identified"]) == case_capabilities
        assert by_case[case_id]["capability_bearing_activities"] == case_bearing
        observed |= case_capabilities
        capability_bearing += case_bearing

    assert set(summary["aggregates"]["distinct_capabilities_exercised"]) == observed
    assert summary["aggregates"]["capability_bearing_activities"] == capability_bearing == 7
    assert "GENERATIVE_AI" not in observed

    from ai_adoption_engine.models.enums import Capability

    assert set(summary["aggregates"]["capabilities_not_exercised_in_forward_cases"]) == {
        item.value for item in Capability
    } - observed


def test_v02_review_metrics_are_rederived_without_port003() -> None:
    summary = _summary()
    aggregates = summary["aggregates"]

    port001 = _load(
        PORTFOLIO / "runs" / "port-001" / "production-run-v0.1" / "final_run_state.json"
    )["review_event_counts"]
    port002 = _load(
        PORTFOLIO / "runs" / "port-002" / "production-run-v0.1" / "final_run_state.json"
    )["review_event_counts"]
    port004 = _load(
        PORTFOLIO
        / "runs"
        / "port-004"
        / "production-run-v0.2-review"
        / "stage2-execution-record.v0.1.json"
    )["events_by_action"]

    retained_unknowns = (
        port001["retain-unknown"]
        + port002["retain-unknown"]
        + port004["retain-unknown"]
    )
    corrections = port001["correct"] + port002["correct"] + port004["correct-dependency"]
    rejections = port001["reject"] + port002["reject"]

    assert retained_unknowns == aggregates["reviewed_unknown_retention_events"] == 328
    assert corrections == aggregates["source_bounded_corrections"] == 6
    assert rejections == aggregates["review_rejections"] == 5


def test_v02_keeps_production_fingerprint_cohorts_explicit() -> None:
    summary = _summary()
    register = _load(REGISTER_PATH)
    cohorts = summary["production_fingerprint_cohorts"]
    baseline = _load(PORTFOLIO / "freeze_manifest.v0.1.json")["production_baseline"]
    port004 = _load(COMPARISONS["PORT-004"])["comparison_basis"]

    assert cohorts["HISTORICAL_PHASE8_BASELINE"]["case_ids"] == ["PORT-001", "PORT-002"]
    assert (
        cohorts["HISTORICAL_PHASE8_BASELINE"]["production_fingerprint"]
        == baseline["production_subtree_fingerprint"]
    )
    assert cohorts["PORT004_LATER_PRODUCTION"]["case_ids"] == ["PORT-004"]
    assert (
        cohorts["PORT004_LATER_PRODUCTION"]["production_fingerprint"]
        == port004["production_fingerprint"]
    )
    assert summary["evaluation_integrity"]["production_fingerprint_identical_across_included_cases"] is False
    assert summary["evaluation_integrity"]["cohort_distinction_explicit"] is True

    forward = register["forward_analysis"]
    assert forward["included_case_ids"] == list(CASES)
    assert forward["excluded_case_ids"] == ["PORT-003"]


def test_v02_policy_and_product_learning_claims_remain_bounded() -> None:
    summary = _summary()
    policy = summary["deterministic_policy_observation"]
    learning = summary["product_learning_from_portfolio_validation"]

    assert "All 20" in policy["observed_real_case_gate_behaviour"]
    assert "not validate" in policy["what_this_does_not_validate"]
    assert "scoring" in policy["what_this_does_not_validate"]
    assert "accuracy" in policy["what_this_does_not_validate"]
    assert "precision" not in summary["honest_headline"].lower()

    proposed = "\n".join(learning["post_validation_proposed_extensions"])
    assert "discovered, post-validation extension" in proposed
    assert "not part of the original Phase 1-7 architecture" in proposed
    assert "not implemented or tested" in proposed
    assert "Adoption Execution Layer" in proposed
    assert "out of scope" in proposed


def test_v02_hash_manifest_covers_exactly_the_new_composition_files() -> None:
    listing = PORTFOLIO / "cross_case_summary.v0.2.hashes.sha256"
    listed: dict[str, str] = {}
    for line in listing.read_text().splitlines():
        digest, relative_path = line.split("  ", 1)
        listed[relative_path] = digest
        assert _sha256(ROOT / relative_path) == digest, relative_path

    assert set(listed) == {
        "evaluation/portfolio/register.v0.3.json",
        "evaluation/portfolio/cross_case_summary.v0.2.json",
        "evaluation/portfolio/cross_case_summary.v0.2.md",
    }

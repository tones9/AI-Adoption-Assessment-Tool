from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.harness.decision_metrics import calculate_decision_metrics
from evaluation.harness.end_to_end_metrics import calculate_end_to_end_metrics
from evaluation.harness.extraction_metrics import calculate_extraction_metrics
from evaluation.harness.repeatability_metrics import calculate_repeatability_metrics
from evaluation.harness.step_alignment import kendall_tau_b


ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "evaluation" / "cases" / "development"


def load(path: Path):
    return json.loads(path.read_text())


def test_perfect_development_extraction_scores_one() -> None:
    case = DEV / "dev-001-complaint-demo" / "reference"
    metrics = calculate_extraction_metrics(load(case / "reference_annotation.json"), load(case / "observed_extraction.json"), load(case / "alignment.json"))
    assert metrics["activity"]["f1"] == 1
    assert metrics["ordering_kendall_tau_b"] == 1
    assert metrics["attributes"]["f1"] == 1
    assert metrics["evidence_supported_assertion_rate"] == 1
    assert metrics["appropriate_unknown_rate"] == 1


def test_controlled_errors_have_expected_scores() -> None:
    case = DEV / "dev-002-controlled-errors" / "reference"
    metrics = calculate_extraction_metrics(load(case / "reference_annotation.json"), load(case / "observed_extraction.json"), load(case / "alignment.json"))
    assert metrics["activity"]["precision"] == .75
    assert metrics["activity"]["recall"] == .75
    assert metrics["ordering_kendall_tau_b"] == pytest.approx(1 / 3)
    assert metrics["attributes"]["precision"] == pytest.approx(2 / 3)
    assert metrics["attributes"]["recall"] == .5
    assert metrics["inappropriate_certainty_rate"] == .5
    assert metrics["appropriate_unknown_rate"] == .5


def test_decision_metrics_detect_safety_and_conventional_misses() -> None:
    case = DEV / "dev-002-controlled-errors" / "reference"
    reference = load(case / "reference_annotation.json")["decision_references"]
    metrics = calculate_decision_metrics(reference, load(case / "decision_predictions.json"))
    assert metrics["recommendation_accuracy"] == .5
    assert metrics["unsafe_over_automation_rate"] == .25
    assert metrics["conventional_solution_miss_rate"] == .25
    assert metrics["capabilities"]["precision"] == pytest.approx(2 / 3)


def test_kendall_tau_b_supports_ties_and_small_samples() -> None:
    assert kendall_tau_b([(1, 1)]) is None
    assert kendall_tau_b([(1, 1), (2, 2), (3, 3)]) == 1


def test_repeatability_uses_pairwise_agreement() -> None:
    run = {"steps":[{"activity":"A"},{"activity":"B"}],"knowledge_state_items":["A:known"],"evidence_items":["A:e1"],"recommendations":["A:AUTOMATE"]}
    metrics = calculate_repeatability_metrics([run, run, run])
    assert set(value for value in metrics.values()) == {1.0}


def test_end_to_end_counts_review_effort() -> None:
    metrics = calculate_end_to_end_metrics([{"completed":True,"review_time_seconds":90,"corrections":2,"rejections":1,"additions":1,"retained_unknowns":3,"recommendation_changes_caused_by_review":1,"traceability_completeness":.8}])
    assert metrics["completion_rate"] == 1
    assert metrics["review_time_seconds"] == 90
    assert metrics["final_traceability_completeness"] == .8

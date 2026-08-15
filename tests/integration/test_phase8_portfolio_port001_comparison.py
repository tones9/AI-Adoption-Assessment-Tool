from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PORTFOLIO = ROOT / "evaluation" / "portfolio"
RUN = PORTFOLIO / "runs" / "port-001" / "production-run-v0.1"
COMPARISON = RUN / "comparison"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(name: str) -> dict:
    return json.loads((COMPARISON / name).read_text())


def test_port001_comparison_uses_frozen_inputs_and_output() -> None:
    comparison = _load("retrospective_comparison.v0.1.json")
    basis = comparison["comparison_basis"]

    for path_key, hash_key in (
        ("before_path", "before_sha256"),
        ("product_output_freeze_manifest_path", "product_output_freeze_manifest_sha256"),
        ("after_path", "after_sha256"),
        ("source_capture_path", "source_capture_sha256"),
    ):
        assert _sha256(ROOT / basis[path_key]) == basis[hash_key]

    for line in (RUN / "output_hashes.sha256").read_text().splitlines():
        digest, relative_path = line.split("  ", 1)
        assert _sha256(ROOT / relative_path) == digest, relative_path


def test_port001_theme_classifications_are_complete_and_counted_once() -> None:
    comparison = _load("retrospective_comparison.v0.1.json")
    themes = comparison["themes"]
    assert [theme["theme_id"] for theme in themes] == [
        "PORT-001-T1",
        "PORT-001-T2",
        "PORT-001-T3",
        "PORT-001-T4",
        "PORT-001-T5",
    ]
    assert all(theme["after_evidence"]["source_id"] == "PORT-001-S1" for theme in themes)
    assert all(theme["before_activities"] for theme in themes)
    assert all(theme["explanation"] and theme["remaining_limitation"] for theme in themes)

    counts = Counter(theme["alignment_classification"] for theme in themes)
    expected = comparison["alignment_counts"]
    assert counts == Counter({key: value for key, value in expected.items() if value})
    assert expected == {
        "STRONG_ALIGNMENT": 0,
        "PARTIAL_ALIGNMENT": 3,
        "NO_DOCUMENTED_ALIGNMENT": 2,
        "CONTRADICTION": 0,
    }


def test_port001_comparison_matches_frozen_product_semantics() -> None:
    comparison = _load("retrospective_comparison.v0.1.json")
    integrated = json.loads((RUN / "integrated_assessment.json").read_text())
    assessments = integrated["process_assessment"]["step_assessments"]
    by_step = {item["step_id"]: item for item in assessments}

    assert len(assessments) == comparison["process_reconstruction"]["retained_step_count"] == 6
    assert all(item["recommendation_mode"] == "INVESTIGATE_FURTHER" for item in assessments)
    assert all(
        next(gate for gate in item["gate_results"] if gate["gate"] == "technical_fit")
        ["material_criteria"]
        == ["ai_capability_fit"]
        for item in assessments
    )

    for theme in comparison["themes"]:
        for mapping in theme["relevant_capabilities"]:
            assert mapping["capability"] in by_step[mapping["step_id"]]["capabilities"]
        for activity in theme["before_activities"]:
            assert by_step[activity["step_id"]]["activity"] == activity["activity"]

    review = json.loads((RUN / "approved_review.json").read_text())["review"]
    actions = Counter(event["action"] for event in review["events"])
    assert actions == {
        "accept": 52,
        "retain-unknown": 117,
        "reject": 4,
        "correct": 1,
        "accept-step-order": 1,
        "approve": 1,
    }


def test_port001_uncertainty_is_separate_from_alignment() -> None:
    comparison = _load("retrospective_comparison.v0.1.json")
    findings = comparison["appropriate_uncertainty"]
    assert len(findings) == 2
    assert all(item["assessment"] == "APPROPRIATE_UNCERTAINTY" for item in findings)
    actual_gate = next(item for item in findings if item["actual_gate"] is not None)
    assert actual_gate["actual_gate"] == "technical_fit"
    assert actual_gate["material_missing_information"] == ["ai_capability_fit"]
    assert comparison["additional_plausible_recommendations"] == []


def test_port001_after_was_opened_only_after_output_freeze() -> None:
    unseal = _load("after_unseal_record.v0.1.json")
    freeze = json.loads((RUN / "output_freeze_manifest.v0.1.json").read_text())
    assert freeze["after_boundary_at_output_freeze"]["status"] == (
        "SEALED_NOT_OPENED_FOR_COMPARISON"
    )
    assert unseal["previous_status"] == "SEALED_NOT_OPENED_FOR_COMPARISON"
    assert unseal["current_status"] == "OPENED_FOR_PORT001_RETROSPECTIVE_COMPARISON"
    assert unseal["precondition"]["verified_before_open"] is True
    assert unseal["product_outputs_changed_after_unseal"] is False
    assert unseal["other_after_packets"] == {
        "PORT-002": "SEALED_NOT_OPENED",
        "PORT-003": "SEALED_NOT_OPENED",
    }


def test_port001_comparison_audit_records_the_experimental_boundary() -> None:
    audit = _load("audit_record.v0.1.json")
    assert all(audit["preconditions"].values())
    assert not any(audit["frozen_product_actions"].values())
    assert audit["classification_counts"] == {
        "STRONG_ALIGNMENT": 0,
        "PARTIAL_ALIGNMENT": 3,
        "NO_DOCUMENTED_ALIGNMENT": 2,
        "CONTRADICTION": 0,
        "APPROPRIATE_UNCERTAINTY_FINDINGS": 2,
        "ADDITIONAL_PLAUSIBLE_RECOMMENDATIONS": 0,
    }
    assert audit["materials_explicitly_not_opened"] == [
        "evaluation/portfolio/sealed_after/port-002.after.md",
        "evaluation/portfolio/sealed_after/port-003.after.md",
    ]


def test_port001_comparison_hash_listing_is_complete() -> None:
    listed: dict[str, str] = {}
    for line in (COMPARISON / "hashes.sha256").read_text().splitlines():
        digest, relative_path = line.split("  ", 1)
        listed[relative_path] = digest

    expected_files = {
        "after_unseal_record.v0.1.json",
        "audit_record.v0.1.json",
        "case_study.md",
        "retrospective_comparison.v0.1.json",
    }
    assert {Path(path).name for path in listed} == expected_files
    for relative_path, digest in listed.items():
        assert _sha256(ROOT / relative_path) == digest

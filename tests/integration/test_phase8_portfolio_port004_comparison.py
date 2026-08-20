from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PORTFOLIO = ROOT / "evaluation" / "portfolio"
RUN = PORTFOLIO / "runs" / "port-004"
COMPARISON = RUN / "comparison"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(name: str) -> dict:
    return json.loads((COMPARISON / name).read_text())


def _verify_hash_listing(path: Path, *, relative_to: Path = ROOT) -> dict[str, str]:
    listed: dict[str, str] = {}
    for line in path.read_text().splitlines():
        digest, relative_path = line.split("  ", 1)
        listed[relative_path] = digest
        assert _sha256(relative_to / relative_path) == digest, relative_path
    return listed


def test_port004_frozen_and_sealed_manifests_are_unchanged() -> None:
    run_hashes = _verify_hash_listing(
        RUN / "port-004.run-hashes.sha256", relative_to=RUN
    )
    assert len(run_hashes) == 17

    sealed_hashes = _verify_hash_listing(
        PORTFOLIO / "sealed_after" / "port-004.pre-reveal-hashes.sha256"
    )
    assert set(sealed_hashes) == {
        "evaluation/portfolio/runs/port-004/pre_reveal_protocol.v0.1.md",
        "evaluation/portfolio/source_captures/port-004-s2-pe2e-ai-search-features.capture.md",
        "evaluation/portfolio/source_captures/port-004-s3-uspto-quality-ai-search-usage.capture.md",
        "evaluation/portfolio/source_captures/port-004-s4-simsearch-prime-time.capture.md",
        "evaluation/portfolio/source_captures/port-004-s5-ppac-ai-search-advisory.capture.md",
        "evaluation/portfolio/provenance/port-004.after-manifest.v0.1.json",
        "evaluation/portfolio/sealed_after/port-004.after.md",
        "evaluation/portfolio/sealed_after/port-004.seal-record.v0.1.json",
    }


def test_port004_comparison_uses_only_sealed_after_sources_and_frozen_outputs() -> None:
    comparison = _load("retrospective_comparison.v0.1.json")
    basis = comparison["comparison_basis"]
    for path_key, hash_key in (
        ("before_path", "before_sha256"),
        ("stage1_to_stage5_manifest_path", "stage1_to_stage5_manifest_sha256"),
        ("after_path", "after_sha256"),
    ):
        assert _sha256(ROOT / basis[path_key]) == basis[hash_key]

    expected_sources = {
        "PORT-004-S2",
        "PORT-004-S3",
        "PORT-004-S4",
        "PORT-004-S5",
    }
    assert set(basis["sealed_source_captures"]) == expected_sources
    for source in basis["sealed_source_captures"].values():
        assert _sha256(ROOT / source["path"]) == source["sha256"]

    unseal = _load("after_unseal_record.v0.1.json")
    assert unseal["previous_status"] == "SEALED_NOT_OPENED_FOR_COMPARISON"
    assert unseal["current_status"] == "OPENED_FOR_PORT004_RETROSPECTIVE_COMPARISON"
    assert unseal["preconditions"]["stage1_to_stage5_manifest_verified_before_open"]
    assert unseal["preconditions"]["sealed_hash_listing_verified_before_open"]
    assert unseal["scope_controls"]["new_after_sources_permitted"] is False
    assert unseal["product_outputs_changed_before_or_at_unseal"] is False


def test_port004_theme_classifications_are_complete_and_use_frozen_semantics() -> None:
    comparison = _load("retrospective_comparison.v0.1.json")
    themes = comparison["themes"]
    assert [theme["theme_id"] for theme in themes] == [
        "PORT-004-T1",
        "PORT-004-T2",
        "PORT-004-T3",
    ]
    assert all(theme["after_evidence"]["source_ids"] for theme in themes)
    assert all(theme["relevant_frozen_steps"] for theme in themes)
    assert all(theme["rationale"] and theme["limitations_uncertainty"] for theme in themes)

    counts = Counter(theme["alignment_classification"] for theme in themes)
    assert counts == Counter({"PARTIAL_ALIGNMENT": 1, "NO_DOCUMENTED_ALIGNMENT": 2})
    assert comparison["alignment_counts"] == {
        "STRONG_ALIGNMENT": 0,
        "PARTIAL_ALIGNMENT": 1,
        "NO_DOCUMENTED_ALIGNMENT": 2,
        "CONTRADICTION": 0,
    }

    assessed = json.loads(
        (RUN / "production-run-v0.4-assessed" / "stage4-assessment-record.v0.1.json").read_text()
    )["observed_step_assessments"]
    by_step = {item["step_id"]: item for item in assessed}
    assert len(assessed) == 8
    assert all(item["recommendation_mode"] == "INVESTIGATE_FURTHER" for item in assessed)
    assert all(
        next(gate for gate in item["gate_results"] if gate["gate"] == "technical_fit")[
            "rationale"
        ]
        == "Material evidence is insufficient: ai_capability_fit is unknown."
        for item in assessed
    )

    for theme in themes:
        for step in theme["relevant_frozen_steps"]:
            assert by_step[step["step_id"]]["activity"] == step["activity"]
        for mapping in theme["frozen_capability_mapping"]:
            assert mapping["capability"] in by_step[mapping["step_id"]]["capabilities"]
        for recommendation in theme["frozen_recommendations"]:
            assert (
                by_step[recommendation["step_id"]]["recommendation_mode"]
                == recommendation["recommendation"]
            )


def test_port004_keeps_outcomes_and_uncertainty_separate_from_alignment() -> None:
    comparison = _load("retrospective_comparison.v0.1.json")
    categories = comparison["after_evidence_categories"]
    assert set(categories) == {
        "intervention_existence",
        "reported_use",
        "human_control_statements",
        "measured_outcomes",
    }
    assert categories["reported_use"]["source_ids"] == ["PORT-004-S3"]
    assert categories["measured_outcomes"]["reported_outcome_count"] == 0
    assert comparison["reported_outcomes"] == []

    findings = comparison["appropriate_uncertainty"]
    assert len(findings) == 2
    assert all(item["assessment"] == "APPROPRIATE_UNCERTAINTY" for item in findings)
    actual_gate = next(item for item in findings if item["actual_gate"] is not None)
    assert actual_gate["actual_gate"] == "technical_fit"
    assert actual_gate["material_missing_information"] == ["ai_capability_fit"]
    assert comparison["additional_plausible_recommendations"] == []


def test_port004_audit_and_comparison_hash_listing_preserve_boundaries() -> None:
    audit = _load("audit_record.v0.1.json")
    assert audit["preconditions"]["sealed_source_set_extended"] is False
    assert audit["preconditions"]["material_packet_defect_found"] is False
    assert audit["preconditions"]["after_unseal_record_created_before_analysis"] is True
    assert audit["preconditions"]["curator_blind_to_after_evidence"] is False
    assert audit["preconditions"]["production_reviewer_blindness_claimed"] is False
    assert not any(audit["frozen_product_actions"].values())
    assert audit["classification_counts"] == {
        "STRONG_ALIGNMENT": 0,
        "PARTIAL_ALIGNMENT": 1,
        "NO_DOCUMENTED_ALIGNMENT": 2,
        "CONTRADICTION": 0,
        "APPROPRIATE_UNCERTAINTY_FINDINGS": 2,
        "ADDITIONAL_PLAUSIBLE_RECOMMENDATIONS": 0,
    }

    listed = _verify_hash_listing(COMPARISON / "hashes.sha256")
    assert {Path(path).name for path in listed} == {
        "after_unseal_record.v0.1.json",
        "audit_record.v0.1.json",
        "case_study.md",
        "retrospective_comparison.v0.1.json",
    }

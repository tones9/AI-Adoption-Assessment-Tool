from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PORTFOLIO = ROOT / "evaluation" / "portfolio"
RUN = PORTFOLIO / "runs" / "port-003" / "production-run-v0.1"
COMPARISON = RUN / "comparison"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(name: str) -> dict:
    return json.loads((COMPARISON / name).read_text())


def test_port003_comparison_uses_frozen_inputs_and_output() -> None:
    comparison = _load("retrospective_comparison.v0.1.json")
    basis = comparison["comparison_basis"]
    for path_key, hash_key in (
        ("before_path", "before_sha256"),
        ("product_output_freeze_manifest_path", "product_output_freeze_manifest_sha256"),
        ("after_path", "after_sha256"),
    ):
        assert _sha256(ROOT / basis[path_key]) == basis[hash_key]

    for line in (RUN / "output_hashes.sha256").read_text().splitlines():
        digest, relative_path = line.split("  ", 1)
        assert _sha256(ROOT / relative_path) == digest, relative_path


def test_port003_theme_classifications_are_complete_and_counted_once() -> None:
    comparison = _load("retrospective_comparison.v0.1.json")
    themes = comparison["themes"]
    assert [theme["theme_id"] for theme in themes] == [
        "PORT-003-T1",
        "PORT-003-T2",
        "PORT-003-T3",
        "PORT-003-T4",
        "PORT-003-T5",
        "PORT-003-T6",
    ]
    assert all(theme["after_evidence"]["source_ids"] for theme in themes)
    assert all(theme["explanation"] and theme["remaining_limitation"] for theme in themes)

    counts = Counter(theme["alignment_classification"] for theme in themes)
    expected = comparison["alignment_counts"]
    assert counts == Counter({key: value for key, value in expected.items() if value})
    assert expected == {
        "STRONG_ALIGNMENT": 1,
        "PARTIAL_ALIGNMENT": 3,
        "NO_DOCUMENTED_ALIGNMENT": 2,
        "CONTRADICTION": 0,
    }


def test_port003_out_of_scope_themes_are_labelled_as_an_evaluation_boundary() -> None:
    """The two unidentifiable themes must not be presented as product misses."""

    comparison = _load("retrospective_comparison.v0.1.json")
    out_of_scope = [
        theme
        for theme in comparison["themes"]
        if theme["alignment_classification"] == "NO_DOCUMENTED_ALIGNMENT"
    ]
    assert {theme["theme_id"] for theme in out_of_scope} == {
        "PORT-003-T4",
        "PORT-003-T5",
    }
    for theme in out_of_scope:
        assert theme["before_activities"] == []
        assert theme["relevant_capabilities"] == []
        assert "evaluation-design boundary" in theme["remaining_limitation"]


def test_port003_comparison_matches_frozen_product_semantics() -> None:
    comparison = _load("retrospective_comparison.v0.1.json")
    integrated = json.loads((RUN / "integrated_assessment.json").read_text())
    assessments = integrated["process_assessment"]["step_assessments"]
    by_step = {item["step_id"]: item for item in assessments}

    assert len(assessments) == comparison["process_reconstruction"]["retained_step_count"] == 4
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
            assert mapping["identified_by"] == "PHASE_3_EXTRACTION"
        for activity in theme["before_activities"]:
            assert by_step[activity["step_id"]]["activity"] == activity["activity"]

    review = json.loads((RUN / "approved_review.json").read_text())["review"]
    actions = Counter(event["action"] for event in review["events"])
    assert actions == {
        "accept": 46,
        "retain-unknown": 81,
        "accept-step-order": 1,
        "approve": 1,
    }


def test_port003_credits_no_capability_to_human_review() -> None:
    comparison = _load("retrospective_comparison.v0.1.json")
    recognition = comparison["capability_recognition"]
    assert recognition["review_dependency"].startswith("None")
    contribution = comparison["human_review_contribution"]
    assert contribution["assessment"] == "VERIFICATION_ONLY_NO_CAPABILITY_RECOVERY"

    manifest = json.loads((RUN / "output_freeze_manifest.v0.1.json").read_text())
    assert manifest["human_review"]["capability_signals_corrected"] == 0
    assert manifest["human_review"]["assertions_rejected"] == 0

    # Every capability credited in the comparison must exist in the frozen output.
    integrated = json.loads((RUN / "integrated_assessment.json").read_text())
    frozen = {
        (item["step_id"], capability)
        for item in integrated["process_assessment"]["step_assessments"]
        for capability in item["capabilities"]
    }
    credited = {
        (mapping["step_id"], mapping["capability"])
        for theme in comparison["themes"]
        for mapping in theme["relevant_capabilities"]
    }
    assert credited <= frozen
    assert frozen == {
        ("candidate-step-9561eeeddd601694", "GENERATIVE_AI"),
        ("candidate-step-d3ec490723991cb0", "GENERATIVE_AI"),
    }


def test_port003_uncertainty_and_outcomes_are_kept_separate() -> None:
    comparison = _load("retrospective_comparison.v0.1.json")
    findings = comparison["appropriate_uncertainty"]
    assert len(findings) == 3
    assert all(item["assessment"] == "APPROPRIATE_UNCERTAINTY" for item in findings)
    gated = next(item for item in findings if item["actual_gate"] is not None)
    assert gated["actual_gate"] == "technical_fit"
    assert gated["material_missing_information"] == ["ai_capability_fit"]
    assert comparison["additional_plausible_recommendations"] == []

    outcomes = comparison["reported_outcomes"]
    assert len(outcomes) == 3
    assert all(item["scope_note"] for item in outcomes)
    assert "not combined" in comparison["outcome_comparability_note"]


def test_port003_taxonomy_finding_is_recorded_without_changing_the_taxonomy() -> None:
    comparison = _load("retrospective_comparison.v0.1.json")
    finding = comparison["capability_recognition"]["taxonomy_finding"]
    assert "speech" in finding.lower()
    assert "frozen" in finding.lower()

    audit = _load("audit_record.v0.1.json")
    assert audit["frozen_product_actions"]["capability_taxonomy_modified"] is False

    freeze = json.loads((PORTFOLIO / "freeze_manifest.v0.1.json").read_text())
    baseline = freeze["production_baseline"]
    assert (
        _sha256(ROOT / baseline["decision_policy_path"])
        == baseline["decision_policy_sha256"]
    )
    assert (
        audit["verified_hashes"]["production_subtree_fingerprint"]
        == baseline["production_subtree_fingerprint"]
    )


def test_port003_unseal_record_proves_freeze_preceded_after_access() -> None:
    unseal = _load("after_unseal_record.v0.1.json")
    freeze = json.loads((RUN / "output_freeze_manifest.v0.1.json").read_text())
    assert freeze["after_boundary_at_output_freeze"]["status"] == (
        "SEALED_NOT_OPENED_FOR_COMPARISON"
    )
    assert unseal["previous_status"] == "SEALED_NOT_OPENED_FOR_COMPARISON"
    assert unseal["current_status"] == "OPENED_FOR_PORT003_RETROSPECTIVE_COMPARISON"
    assert unseal["precondition"]["verified_before_current_comparison_open"] is True
    assert unseal["precondition"]["product_output_committed_before_after_access"] is True
    assert unseal["product_outputs_changed_after_unseal"] is False
    assert not any(unseal["frozen_product_actions_permitted_after_unseal"].values())
    assert (
        _sha256(ROOT / unseal["opened_after_path"]) == unseal["opened_after_sha256"]
    )

    disclosure = unseal["researcher_exposure_disclosure"]
    assert disclosure["reviewer_blindness_claimed"] is False
    assert disclosure["prior_public_after_evidence_audit"] is True
    assert disclosure["production_extraction_received_after_material"] is False
    assert disclosure["withdrawn_review_proposal"]["applied_to_any_artefact"] is False
    assert (
        "evaluation/portfolio/sealed_after/port-003.after.md"
        in disclosure["materials_not_read_by_reviewer_before_output_freeze"]
    )


def test_port003_comparison_audit_records_the_experimental_boundary() -> None:
    audit = _load("audit_record.v0.1.json")
    assert all(
        value
        for key, value in audit["preconditions"].items()
        if key != "reviewer_blind_to_public_after_evidence"
    )
    assert audit["preconditions"]["reviewer_blind_to_public_after_evidence"] is False
    assert not any(audit["frozen_product_actions"].values())
    assert audit["classification_counts"] == {
        "STRONG_ALIGNMENT": 1,
        "PARTIAL_ALIGNMENT": 3,
        "NO_DOCUMENTED_ALIGNMENT": 2,
        "CONTRADICTION": 0,
        "APPROPRIATE_UNCERTAINTY_FINDINGS": 3,
        "ADDITIONAL_PLAUSIBLE_RECOMMENDATIONS": 0,
    }
    for source_id, digest in audit["verified_hashes"]["source_capture_sha256"].items():
        index = source_id.rsplit("-", 1)[-1].lower()
        matches = list(PORTFOLIO.glob(f"source_captures/port-003-{index}-*.capture.md"))
        assert len(matches) == 1, source_id
        assert _sha256(matches[0]) == digest, source_id


def test_port003_comparison_hash_listing_is_complete() -> None:
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

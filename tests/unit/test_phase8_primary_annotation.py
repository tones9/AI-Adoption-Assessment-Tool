from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from evaluation.harness.common import load_json, sha256_file
from evaluation.primary_annotation.con001 import (
    BEFORE_PATH,
    BEFORE_SHA256,
    EVIDENCE_CATALOG,
    load_frozen_before,
)
from evaluation.primary_annotation.service import (
    CURRENT_SCHEMA_ID,
    AnnotationStore,
    AnnotationValidationError,
    build_reviewer_safe_current_state,
    new_draft,
    preview_fingerprint,
    validate_current_state,
    validate_decision_reference,
)


def structurally_valid_test_draft() -> dict:
    """A test-only structural fixture; it is not a CON-001 reference annotation."""
    draft = new_draft()
    draft["draft_metadata"]["annotator_id"] = "test-primary"
    current = draft["current_state"]
    current["process_name"] = "Test-only process"
    for assertion in current["process_assertions"].values():
        assertion["knowledge_state"] = "unknown"
    for cue in current["cue_reviews"]:
        cue["disposition"] = "context_only"
        cue["rationale"] = "Test-only structural disposition"
    current["activities"] = [
        {
            "activity_id": "T1",
            "name": "Synthetic test activity",
            "order_state": "ordered",
            "sequence": 1,
            "dependencies": [],
            "knowledge_state": "known",
            "evidence_locators": ["E1"],
            "boundary_rationale": "Test-only boundary fixture",
        }
    ]
    current["assertions"] = [
        {
            "activity_id": "T1",
            "field": field,
            "value": "",
            "knowledge_state": "unknown",
            "evidence_locators": [],
            "rationale": "",
            "supported_empty_confirmed": False,
        }
        for field in ("actor", "system", "input", "output")
    ]
    draft["decision_reference"]["decisions"] = [
        {
            "activity_id": "T1",
            "primary_mode": "INVESTIGATE_FURTHER",
            "acceptable_alternative_modes": [],
            "capabilities": [],
            "human_oversight_required": "Unclear",
            "automation_unsafe": "Unclear",
            "conventional_solution_preferable": "Unclear",
            "priority_rank": None,
            "not_rankable": True,
            "important_missing_information": "Test-only fixture",
            "rationale": "Test-only structural rationale",
        }
    ]
    return draft


def test_before_loader_accesses_only_allowlisted_file(monkeypatch) -> None:
    accessed: list[Path] = []
    original = Path.open

    def tracked_open(self: Path, *args, **kwargs):
        accessed.append(self.resolve())
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracked_open)
    text = load_frozen_before()
    assert "Assembly conveyor maintenance" in text
    assert set(accessed) == {BEFORE_PATH}
    assert all("after" not in path.parts for path in accessed)
    assert sha256_file(BEFORE_PATH) == BEFORE_SHA256


def test_empty_worksheet_contains_only_evidence_and_unconfirmed_cues() -> None:
    draft = new_draft()
    assert draft["current_state"]["activities"] == []
    assert draft["decision_reference"]["decisions"] == []
    assert all(not cue["disposition"] for cue in draft["current_state"]["cue_reviews"])
    assert {item["evidence_id"] for item in EVIDENCE_CATALOG} == {"E1", "E2", "E3", "E4"}


def test_known_and_inferred_assertions_require_permitted_evidence() -> None:
    draft = structurally_valid_test_draft()
    assertion = draft["current_state"]["assertions"][0]
    assertion.update({"value": "Person", "knowledge_state": "known", "evidence_locators": []})
    assert any("known assertions require permitted evidence" in item for item in validate_current_state(draft))
    assertion.update({"knowledge_state": "inferred", "evidence_locators": ["E3"], "rationale": ""})
    assert any("inferred assertions require an explicit rationale" in item for item in validate_current_state(draft))
    assertion.update({"rationale": "Test-only inference", "evidence_locators": ["E99"]})
    assert any("invalid evidence locator" in item for item in validate_current_state(draft))


def test_unknowns_do_not_accept_invented_values() -> None:
    draft = structurally_valid_test_draft()
    draft["current_state"]["assertions"][0]["value"] = "Invented actor"
    assert any("unknown assertions must not contain" in item for item in validate_current_state(draft))


def test_supported_empty_requires_evidence_and_human_confirmation() -> None:
    draft = structurally_valid_test_draft()
    assertion = draft["current_state"]["assertions"][0]
    assertion["knowledge_state"] = "supported_empty"
    errors = validate_current_state(draft)
    assert any("supported-empty assertions require permitted evidence" in item for item in errors)
    assert any("confirm that the cited evidence explicitly establishes absence" in item for item in errors)
    assertion["evidence_locators"] = ["E4"]
    assertion["supported_empty_confirmed"] = True
    assert not any("Assertion 1" in item for item in validate_current_state(draft))


def test_unresolved_ambiguity_is_preserved() -> None:
    draft = structurally_valid_test_draft()
    ambiguity = {
        "scope": "T1",
        "ambiguity": "Test-only unresolved question",
        "why_it_matters": "Test coverage",
        "treatment": "unknown",
    }
    draft["current_state"]["unresolved_ambiguities"].append(ambiguity)
    assert validate_current_state(draft) == []
    assert draft["current_state"]["unresolved_ambiguities"] == [ambiguity]


def test_decision_reference_must_cover_every_activity() -> None:
    draft = structurally_valid_test_draft()
    assert validate_decision_reference(draft) == []
    draft["decision_reference"]["decisions"] = []
    assert "exactly once" in validate_decision_reference(draft)[0]


def test_explicit_preview_and_approval_create_separate_immutable_records(tmp_path: Path) -> None:
    store = AnnotationStore(tmp_path / "records")
    draft = structurally_valid_test_draft()
    preview_hash = preview_fingerprint(draft)
    with pytest.raises(AnnotationValidationError, match="Explicit human approval"):
        store.approve(draft, explicit_approval=False, preview_sha256=preview_hash)
    with pytest.raises(AnnotationValidationError, match="changed after preview"):
        store.approve(draft, explicit_approval=True, preview_sha256="wrong")

    frozen_at = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
    result = store.approve(
        draft,
        explicit_approval=True,
        preview_sha256=preview_hash,
        now=frozen_at,
    )
    assert result["version"] == 1
    version_dir = result["directory"]
    current_path = version_dir / "primary_current_state_reference.v0.1.json"
    decision_path = version_dir / "primary_decision_reference.v0.1.json"
    approval_path = version_dir / "primary_annotation_approval.v0.1.json"
    current = load_json(current_path)
    decision = load_json(decision_path)
    approval = load_json(approval_path)
    assert current["annotator"]["identity_or_pseudonym"] == "test-primary"
    assert current["before_packet"]["sha256"] == BEFORE_SHA256
    assert decision["reviewer_pack_eligible"] is False
    assert {item["role"] for item in approval["records"]} == {
        "current_state_reference",
        "primary_decision_reference_private",
    }
    store.verify_frozen_version(1)

    original_current = current_path.read_bytes()
    unchanged = copy.deepcopy(draft)
    unchanged["draft_metadata"]["revision_reason"] = "Test correction"
    with pytest.raises(AnnotationValidationError, match="must change"):
        store.approve(
            unchanged,
            explicit_approval=True,
            preview_sha256=preview_fingerprint(unchanged),
            now=frozen_at,
        )
    assert current_path.read_bytes() == original_current

    revised = copy.deepcopy(draft)
    revised["draft_metadata"]["revision_reason"] = "Correct test-only rationale"
    revised["decision_reference"]["decisions"][0]["rationale"] = "Revised test-only rationale"
    revision = store.approve(
        revised,
        explicit_approval=True,
        preview_sha256=preview_fingerprint(revised),
        now=frozen_at,
    )
    assert revision["version"] == 2
    assert current_path.read_bytes() == original_current
    store.verify_frozen_version(1)
    store.verify_frozen_version(2)


def test_reviewer_projection_excludes_private_decision_reference(tmp_path: Path) -> None:
    store = AnnotationStore(tmp_path / "records")
    draft = structurally_valid_test_draft()
    result = store.approve(
        draft,
        explicit_approval=True,
        preview_sha256=preview_fingerprint(draft),
    )
    current = load_json(
        result["directory"] / "primary_current_state_reference.v0.1.json"
    )
    decision = load_json(
        result["directory"] / "primary_decision_reference.v0.1.json"
    )
    safe = build_reviewer_safe_current_state(current)
    serialized = json.dumps(safe, sort_keys=True)
    assert "primary_mode" not in serialized
    assert "capabilities" not in serialized
    assert "decision_reference" not in serialized
    assert safe["schema_id"] == CURRENT_SCHEMA_ID
    with pytest.raises(ValueError):
        build_reviewer_safe_current_state(decision)

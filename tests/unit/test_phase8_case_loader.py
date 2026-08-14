from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.harness.case_loader import (
    CaseIntegrityError,
    SealedAfterPacketError,
    load_after_packet,
    load_before_packet,
    verify_case_packet,
)


ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "evaluation" / "cases" / "confirmatory" / "con-001-bmw-maintenance"


def test_all_case_packets_match_frozen_hashes() -> None:
    case_root = ROOT / "evaluation" / "cases"
    manifests = list(case_root.rglob("manifest.json"))
    assert len(manifests) == 8
    for manifest in manifests:
        verify_case_packet(manifest.parent)


def test_before_loader_does_not_return_after_material() -> None:
    loaded = load_before_packet(CASE)
    assert loaded.manifest["case_id"] == "CON-001"
    assert all(path.startswith("before/") for path in loaded.files)


def test_after_packet_is_sealed_without_freeze_record(tmp_path: Path) -> None:
    with pytest.raises(SealedAfterPacketError):
        load_after_packet(CASE, recommendations_frozen=False, freeze_record=None)
    bad_record = tmp_path / "freeze.json"
    bad_record.write_text(json.dumps({"case_id":"CON-999","recommendations_frozen":True}))
    with pytest.raises(SealedAfterPacketError):
        load_after_packet(CASE, recommendations_frozen=True, freeze_record=bad_record)


def test_hash_tampering_is_detected(tmp_path: Path) -> None:
    copied = tmp_path / "case"
    copied.mkdir()
    (copied / "before").mkdir()
    (copied / "after").mkdir()
    manifest = json.loads((CASE / "manifest.json").read_text())
    (copied / "manifest.json").write_text(json.dumps(manifest))
    (copied / "before" / "process_document.txt").write_text("tampered")
    (copied / "after" / "reference_evidence.md").write_bytes((CASE / "after" / "reference_evidence.md").read_bytes())
    with pytest.raises(CaseIntegrityError):
        verify_case_packet(copied)

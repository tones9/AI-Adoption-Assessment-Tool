from __future__ import annotations

import json
import re
from pathlib import Path

from evaluation.harness.common import sha256_file
from evaluation.harness.freeze import verify_protocol_freeze


ROOT = Path(__file__).resolve().parents[2]


def test_all_phase8_json_artifacts_parse() -> None:
    for path in (ROOT / "evaluation").rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))


def test_frozen_baseline_prompt_contains_no_policy_implementation() -> None:
    prompt = (ROOT / "evaluation" / "config" / "baseline_prompt.v0.1.txt").read_text().lower()
    for forbidden in (r"\bthresholds?\b", r"\bweights?\b", r"\bgates?\b", r"decision_policy", r"engine recommendation"):
        assert re.search(forbidden, prompt) is None


def test_case_manifests_record_every_eligibility_rule() -> None:
    manifests = list((ROOT / "evaluation" / "cases").rglob("manifest.json"))
    assert len(manifests) == 8
    for path in manifests:
        manifest = json.loads(path.read_text())
        assert len(manifest["eligibility"]) == 8
        assert all(manifest["eligibility"].values())
        assert manifest["after_sealed"] is True


def test_protocol_freeze_hashes_are_current() -> None:
    verify_protocol_freeze(ROOT)


def test_independent_review_instrument_version_and_hash_are_frozen() -> None:
    freeze = json.loads(
        (ROOT / "evaluation" / "protocol" / "freeze_manifest.v0.1.json").read_text()
    )
    instrument = freeze["independent_reference_review_instrument"]
    assert instrument["id"] == "phase8-independent-reference-review-instrument.v0.1"
    assert instrument["sha256"] == "22e60fed9972d27051bd306cccc6fa87a34be76d5a581e66c2b87be2053dc1f3"
    assert sha256_file(ROOT / instrument["path"]) == instrument["sha256"]

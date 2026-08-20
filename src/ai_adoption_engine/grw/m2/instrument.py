"""Versioned, reviewer-applied data-readiness anchors for M2 M1."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ai_adoption_engine.grw.m2.models import VersionedPolicyReference
from ai_adoption_engine.grw.m2.policy import canonical_json


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_INSTRUMENT_PATH = ROOT / "config" / "grw_m2_data_readiness_instrument.v0.1.json"


def load_instrument_reference(path: str | Path = DEFAULT_INSTRUMENT_PATH) -> tuple[dict, VersionedPolicyReference]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("criterion") != "data_readiness" or payload.get("allowed_values") != [0, 1, 2, 3, 4]:
        raise ValueError("M2 instrument must allow document-supported data_readiness values 0..4 only")
    if set(payload.get("anchors", {})) != {"0", "1", "2", "3", "4"}:
        raise ValueError("M2 instrument anchors are incomplete")
    return payload, VersionedPolicyReference(
        policy_id=payload["instrument_id"], version=payload["version"],
        fingerprint=hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest(),
    )

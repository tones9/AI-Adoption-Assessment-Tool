"""Canonical loaders for the M2 M1 policy fragment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ai_adoption_engine.grw.m2.models import VersionedPolicyReference


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_POLICY_PATH = ROOT / "config" / "grw_m2_m1_admissibility_policy.v0.1.json"


def canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def load_policy_reference(path: str | Path = DEFAULT_POLICY_PATH) -> tuple[dict, VersionedPolicyReference]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {"policy_id", "version", "allowed_evidence_class", "allowed_criterion", "allowed_gate"}
    if not required <= set(payload):
        raise ValueError("M2 policy configuration is incomplete")
    if payload["allowed_evidence_class"] != "DOCUMENT_SUPPORTED" or payload["allowed_criterion"] != "data_readiness" or payload["allowed_gate"] != "technical_fit":
        raise ValueError("M2 policy configuration exceeds the approved M1 boundary")
    encoded = canonical_json(payload).encode("utf-8")
    return payload, VersionedPolicyReference(
        policy_id=payload["policy_id"], version=payload["version"], fingerprint=hashlib.sha256(encoded).hexdigest()
    )

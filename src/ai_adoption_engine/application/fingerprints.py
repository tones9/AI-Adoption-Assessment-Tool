"""Canonical reproducibility fingerprints for deterministic assessment inputs."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from ai_adoption_engine.decision.policy import DecisionPolicy
from ai_adoption_engine.models.process import BusinessProcess

if TYPE_CHECKING:
    from ai_adoption_engine.decision.four_gate_policy import FourGateDecisionPolicy


def _sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def fingerprint_business_process(process: BusinessProcess) -> str:
    """Fingerprint assessment content while excluding the run-derived process ID."""

    return _sha256(process.model_dump(mode="json", exclude={"process_id"}))


def fingerprint_decision_policy(policy: DecisionPolicy) -> str:
    """Fingerprint the exact validated policy content used by the engine."""

    return _sha256(policy.model_dump(mode="json"))


def fingerprint_four_gate_policy(policy: FourGateDecisionPolicy) -> str:
    """Fingerprint the exact validated successor policy without changing v0.2."""

    return _sha256(policy.model_dump(mode="json"))

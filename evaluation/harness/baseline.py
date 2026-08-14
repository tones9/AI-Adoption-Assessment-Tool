from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import sha256_file


FORBIDDEN_BASELINE_FIELDS = {
    "policy", "policy_thresholds", "gates", "weights", "scores",
    "engine_recommendations", "after_packet", "later_intervention",
}


def assert_baseline_isolation(payload: dict[str, Any]) -> None:
    leaked = FORBIDDEN_BASELINE_FIELDS & set(payload)
    if leaked:
        raise ValueError(f"Baseline payload contains forbidden fields: {sorted(leaked)}")


def select_confirmatory_run(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Select the lowest indexed successful, structurally valid run."""
    eligible = [r for r in runs if r.get("status") == "success" and r.get("structurally_valid") is True]
    return min(eligible, key=lambda run: int(run["run_index"])) if eligible else None


def prompt_fingerprint(path: str | Path) -> str:
    return sha256_file(path)

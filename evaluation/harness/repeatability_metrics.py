from __future__ import annotations

from itertools import combinations
from statistics import mean
from typing import Any

from .common import jaccard


def calculate_repeatability_metrics(runs: list[dict[str, Any]]) -> dict[str, float | None]:
    if len(runs) < 2:
        raise ValueError("Repeatability requires at least two runs")
    activity, states, evidence, decisions = [], [], [], []
    for left, right in combinations(runs, 2):
        activity.append(jaccard((s["activity"] for s in left["steps"]), (s["activity"] for s in right["steps"])))
        states.append(jaccard(left.get("knowledge_state_items", []), right.get("knowledge_state_items", [])))
        evidence.append(jaccard(left.get("evidence_items", []), right.get("evidence_items", [])))
        if "recommendations" in left and "recommendations" in right:
            decisions.append(jaccard(left["recommendations"], right["recommendations"]))
    return {
        "activity_set_agreement": mean(activity),
        "known_inferred_unknown_agreement": mean(states),
        "evidence_selection_agreement": mean(evidence),
        "downstream_recommendation_agreement": mean(decisions) if decisions else None,
    }

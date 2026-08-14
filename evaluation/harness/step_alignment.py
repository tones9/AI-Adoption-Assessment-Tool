from __future__ import annotations

from collections import Counter
from typing import Any


ALLOWED_RELATIONS = {"matched", "split", "merge", "spurious", "missed"}


def validate_alignment(alignment: dict[str, Any]) -> None:
    matches = alignment.get("alignments", [])
    seen_system: set[str] = set()
    seen_reference: set[str] = set()
    for item in matches:
        relation = item["relation"]
        if relation not in ALLOWED_RELATIONS:
            raise ValueError(f"Unknown alignment relation: {relation}")
        if relation == "matched":
            system_id, reference_id = item["system_step_ids"][0], item["reference_step_ids"][0]
            if len(item["system_step_ids"]) != 1 or len(item["reference_step_ids"]) != 1:
                raise ValueError("matched alignment must be one-to-one")
            if system_id in seen_system or reference_id in seen_reference:
                raise ValueError("one-to-one matches cannot reuse an identifier")
            seen_system.add(system_id)
            seen_reference.add(reference_id)


def alignment_counts(alignment: dict[str, Any]) -> Counter[str]:
    validate_alignment(alignment)
    return Counter(item["relation"] for item in alignment.get("alignments", []))


def kendall_tau_b(pairs: list[tuple[int, int]]) -> float | None:
    """Kendall tau-b without a scipy dependency; returns None for <2/completely tied pairs."""
    if len(pairs) < 2:
        return None
    concordant = discordant = ties_x = ties_y = 0
    for index, (x1, y1) in enumerate(pairs):
        for x2, y2 in pairs[index + 1 :]:
            dx, dy = x1 - x2, y1 - y2
            if dx == 0 and dy == 0:
                continue
            if dx == 0:
                ties_x += 1
            elif dy == 0:
                ties_y += 1
            elif dx * dy > 0:
                concordant += 1
            else:
                discordant += 1
    denominator = ((concordant + discordant + ties_x) * (concordant + discordant + ties_y)) ** 0.5
    return (concordant - discordant) / denominator if denominator else None

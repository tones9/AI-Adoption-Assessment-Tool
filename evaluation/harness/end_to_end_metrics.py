from __future__ import annotations

from typing import Any


def calculate_end_to_end_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise ValueError("At least one end-to-end record is required")
    count = len(records)
    total = lambda key: sum(int(item.get(key, 0)) for item in records)
    return {
        "completion_rate": sum(item["completed"] for item in records) / count,
        "review_time_seconds": total("review_time_seconds"),
        "corrections": total("corrections"),
        "rejections": total("rejections"),
        "additions": total("additions"),
        "retained_unknowns": total("retained_unknowns"),
        "recommendation_changes_caused_by_review": total("recommendation_changes_caused_by_review"),
        "final_traceability_completeness": sum(float(item["traceability_completeness"]) for item in records) / count,
    }

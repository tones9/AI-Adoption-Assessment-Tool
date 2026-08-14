from __future__ import annotations

from typing import Any

from .common import prf
from .step_alignment import kendall_tau_b, validate_alignment


def calculate_extraction_metrics(
    reference: dict[str, Any], observed: dict[str, Any], alignment: dict[str, Any]
) -> dict[str, Any]:
    validate_alignment(alignment)
    reference_steps = {s["step_id"]: s for s in reference["steps"]}
    observed_steps = {s["step_id"]: s for s in observed["steps"]}
    one_to_one = [a for a in alignment["alignments"] if a["relation"] == "matched"]
    matched = len(one_to_one)
    activity = prf(matched, len(observed_steps) - matched, len(reference_steps) - matched)

    order_pairs = [
        (reference_steps[a["reference_step_ids"][0]]["sequence"], observed_steps[a["system_step_ids"][0]]["sequence"])
        for a in one_to_one
    ]

    attribute_tp = attribute_fp = attribute_fn = 0
    evidence_supported = evidence_total = 0
    inappropriate = certainty_total = 0
    appropriate_unknown = unknown_total = 0
    for judgement in alignment.get("attribute_judgements", []):
        outcome = judgement["outcome"]
        attribute_tp += outcome == "tp"
        attribute_fp += outcome == "fp"
        attribute_fn += outcome == "fn"
    for judgement in alignment.get("assertion_judgements", []):
        evidence_total += 1
        evidence_supported += bool(judgement["evidence_supported"])
        predicted = judgement["predicted_state"]
        expected = judgement["reference_state"]
        if predicted in {"known", "inferred"}:
            certainty_total += 1
            inappropriate += not bool(judgement["certainty_appropriate"])
        if expected == "unknown":
            unknown_total += 1
            appropriate_unknown += predicted == "unknown"

    return {
        "activity": activity,
        "ordering_kendall_tau_b": kendall_tau_b(order_pairs),
        "attributes": prf(attribute_tp, attribute_fp, attribute_fn),
        "evidence_supported_assertion_rate": evidence_supported / evidence_total if evidence_total else None,
        "inappropriate_certainty_rate": inappropriate / certainty_total if certainty_total else None,
        "appropriate_unknown_rate": appropriate_unknown / unknown_total if unknown_total else None,
        "alignment_errors": {
            relation: sum(a["relation"] == relation for a in alignment["alignments"])
            for relation in ("split", "merge", "spurious", "missed")
        },
    }

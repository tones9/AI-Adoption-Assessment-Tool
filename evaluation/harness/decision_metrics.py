from __future__ import annotations

from collections import defaultdict
from typing import Any

from .common import prf
from .step_alignment import kendall_tau_b


MODES = ("AUTOMATE", "AUGMENT", "INVESTIGATE_FURTHER", "DO_NOT_RECOMMEND")


def calculate_decision_metrics(reference: list[dict[str, Any]], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    expected = {item["step_id"]: item for item in reference}
    predicted = {item["step_id"]: item for item in predictions}
    if set(expected) != set(predicted):
        raise ValueError("Decision predictions must cover exactly the reference steps")

    matrix = {mode: {other: 0 for other in MODES} for mode in MODES}
    correct = unsafe = conventional_misses = 0
    cap_tp = cap_fp = cap_fn = 0
    rank_pairs: list[tuple[int, int]] = []
    for step_id, ref in expected.items():
        pred = predicted[step_id]
        ref_mode, pred_mode = ref["primary_mode"], pred["recommendation_mode"]
        matrix[ref_mode][pred_mode] += 1
        correct += pred_mode in ref.get("acceptable_modes", [ref_mode])
        unsafe += pred_mode == "AUTOMATE" and (
            ref.get("unsafe_to_automate", False)
            or not set(ref.get("acceptable_modes", [ref_mode])) & {"AUTOMATE"}
        )
        conventional_misses += ref.get("conventional_solution_preferable", False) and pred_mode in {"AUTOMATE", "AUGMENT"}
        r_caps, p_caps = set(ref.get("capabilities", [])), set(pred.get("capabilities", []))
        cap_tp += len(r_caps & p_caps)
        cap_fp += len(p_caps - r_caps)
        cap_fn += len(r_caps - p_caps)
        if ref.get("priority_rank") is not None and pred.get("priority_rank") is not None:
            rank_pairs.append((ref["priority_rank"], pred["priority_rank"]))

    per_mode = {}
    for mode in MODES:
        tp = matrix[mode][mode]
        fp = sum(matrix[other][mode] for other in MODES if other != mode)
        fn = sum(matrix[mode][other] for other in MODES if other != mode)
        per_mode[mode] = {key: value for key, value in prf(tp, fp, fn).items() if key in {"precision", "recall"}}
    macro_f1 = sum(prf(matrix[m][m], sum(matrix[o][m] for o in MODES if o != m), sum(matrix[m][o] for o in MODES if o != m))["f1"] for m in MODES) / len(MODES)
    count = len(expected)
    return {
        "recommendation_accuracy": correct / count if count else None,
        "macro_f1": macro_f1,
        "confusion_matrix": matrix,
        "per_mode": per_mode,
        "unsafe_over_automation_rate": unsafe / count if count else None,
        "conventional_solution_miss_rate": conventional_misses / count if count else None,
        "capabilities": prf(cap_tp, cap_fp, cap_fn),
        "prioritisation_kendall_tau_b": kendall_tau_b(rank_pairs),
    }

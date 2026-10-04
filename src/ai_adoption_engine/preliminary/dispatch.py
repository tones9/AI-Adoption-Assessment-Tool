"""Exact evaluator-version dispatch without changing the v0.1 default."""

from __future__ import annotations

from ai_adoption_engine.models.review import ApprovedProcessReview
from ai_adoption_engine.preliminary.evaluator import PreliminaryAssessmentEvaluator
from ai_adoption_engine.preliminary.evaluator_v0_2 import PreliminaryAssessmentEvaluatorV2


PRELIMINARY_EVALUATOR_V0_1_ID = "preliminary-evaluator.v0.1"
PRELIMINARY_EVALUATOR_V0_2_ID = "preliminary-evaluator.v0.2"


class UnsupportedPreliminaryEvaluatorVersion(ValueError):
    """Raised before evaluation when exact evaluator dispatch is unsupported."""


def evaluate_preliminary(
    approved_review: ApprovedProcessReview,
    *,
    evaluator_id: str = PRELIMINARY_EVALUATOR_V0_1_ID,
):
    """Dispatch exactly; v0.2 is reachable only through explicit identity selection."""
    if evaluator_id == PRELIMINARY_EVALUATOR_V0_1_ID:
        return PreliminaryAssessmentEvaluator().evaluate(approved_review)
    if evaluator_id == PRELIMINARY_EVALUATOR_V0_2_ID:
        return PreliminaryAssessmentEvaluatorV2().evaluate(approved_review)
    raise UnsupportedPreliminaryEvaluatorVersion(
        f"Unsupported Preliminary evaluator identity: {evaluator_id}"
    )

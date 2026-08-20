from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_adoption_engine.grw.models import (
    GrwAdmissibilityEffect,
    GrwArtifactReference,
    GrwBaselineReference,
    GrwEvidenceClass,
    GrwEvidenceReview,
    GrwEvidenceSubmission,
    GrwGapReference,
    GrwCriterionSnapshot,
    GrwNonChangeProof,
    GrwParseStatus,
    GrwQuestion,
    GrwReviewDecision,
)
from ai_adoption_engine.grw.service import parse_estimate_candidate
from ai_adoption_engine.models.decision_support import (
    InformationGap,
    InformationGapKind,
    PlanningBasis,
    PlanningOrigin,
)
from ai_adoption_engine.models.enums import KnowledgeState, PriorityStatus, RecommendationMode
from tests.fakes.review import FIXED_TIME


def _baseline() -> GrwBaselineReference:
    reference = GrwArtifactReference(
        artifact_id="artifact-baseline",
        artifact_revision=1,
        payload_sha256="a" * 64,
    )
    return GrwBaselineReference(
        assessment_id="assessment-grw-model",
        package_id="decision-package-" + "b" * 64,
        approved_review=reference,
        integrated_assessment=reference,
        decision_package=reference,
    )


def _gap(baseline: GrwBaselineReference) -> GrwGapReference:
    return GrwGapReference(
        package_id=baseline.package_id,
        step_id="step-1",
        current_activity="Route tickets",
        information_gap=InformationGap(
            gap_id="step-1:criterion:repetition",
            step_id="step-1",
            kind=InformationGapKind.UNKNOWN_INPUT,
            field_name="repetition",
            knowledge_state=KnowledgeState.UNKNOWN,
            message="Repetition is unknown.",
            basis=PlanningBasis(
                origin=PlanningOrigin.ASSESSMENT_FINDING,
                step_id="step-1",
            ),
        ),
    )


def _submission(answer_text: str = "Usually around 18,000–22,000 tickets per month."):
    baseline = _baseline()
    return GrwEvidenceSubmission(
        submission_id="grw-submission-1",
        submitted_at=FIXED_TIME,
        baseline=baseline,
        gap=_gap(baseline),
        question=GrwQuestion(
            customer_question="About how many tickets are handled in a typical month?",
            help_text="A range is okay.",
            why_it_matters="It provides workload context.",
        ),
        answer_text=answer_text,
        evidence_class=GrwEvidenceClass.OPERATOR_PROVIDED_ESTIMATE,
        parsed_candidate=parse_estimate_candidate(answer_text),
    )


def _non_change_proof(baseline: GrwBaselineReference) -> GrwNonChangeProof:
    return GrwNonChangeProof(
        baseline=baseline,
        criterion=GrwCriterionSnapshot(
            criterion_name="repetition",
            value=None,
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="Repetition is unknown.",
            evidence_ids=[],
            confidence=None,
        ),
        gate_results=[],
        gate_results_sha256="d" * 64,
        recommendation_mode=RecommendationMode.INVESTIGATE_FURTHER,
        priority_status=PriorityStatus.INCOMPLETE,
        priority=None,
        roi_statement="ROI / quantified benefit unavailable with current evidence.",
    )


def test_range_parser_preserves_only_a_non_authoritative_candidate() -> None:
    answer = "Usually around 18,000–22,000 tickets per month."
    candidate = parse_estimate_candidate(answer)
    assert candidate.parse_status is GrwParseStatus.CANDIDATE_NEEDS_REVIEW
    assert (candidate.lower_bound, candidate.upper_bound) == (18000, 22000)
    assert candidate.unit == "tickets"
    assert candidate.period == "month"
    assert candidate.qualifiers == ["usually", "around"]
    assert "midpoint" not in type(candidate).model_fields
    assert "criterion_value" not in type(candidate).model_fields
    assert "confidence" not in type(candidate).model_fields


def test_unparsed_text_is_a_valid_estimate_and_does_not_gain_precision() -> None:
    candidate = parse_estimate_candidate("It varies considerably between teams.")
    assert candidate.parse_status is GrwParseStatus.NOT_PARSED
    assert candidate.lower_bound is None
    assert candidate.upper_bound is None


def test_submission_preserves_the_exact_customer_answer_and_is_frozen() -> None:
    answer = "  Usually around 18,000–22,000 tickets per month.\n"
    submission = _submission(answer)
    assert submission.answer_text == answer
    assert submission.evidence_class is GrwEvidenceClass.OPERATOR_PROVIDED_ESTIMATE
    assert "criterion" not in type(submission).model_fields
    with pytest.raises(ValidationError):
        submission.answer_text = "Changed"


def test_unknown_submission_cannot_carry_a_range_candidate() -> None:
    baseline = _baseline()
    with pytest.raises(ValidationError, match="explicit unknown"):
        GrwEvidenceSubmission(
            submission_id="grw-submission-unknown",
            submitted_at=FIXED_TIME,
            baseline=baseline,
            gap=_gap(baseline),
            question=GrwQuestion(
                customer_question="About how many tickets are handled in a typical month?",
                help_text="A range is okay.",
                why_it_matters="It provides workload context.",
            ),
            answer_text="I do not know.",
            evidence_class=GrwEvidenceClass.UNKNOWN,
            parsed_candidate=parse_estimate_candidate("18–22 tickets per month"),
        )


@pytest.mark.parametrize(
    ("decision", "effect"),
    [
        (GrwReviewDecision.ACCEPT_PRELIMINARY, GrwAdmissibilityEffect.PRELIMINARY_UNDERSTANDING),
        (GrwReviewDecision.ACCEPT_RECORDED_ONLY, GrwAdmissibilityEffect.RECORDED_ONLY),
        (GrwReviewDecision.REJECT, GrwAdmissibilityEffect.NONE),
    ],
)
def test_review_decision_effect_mapping_is_explicit(decision, effect) -> None:
    review = GrwEvidenceReview(
        review_id="review-1",
        reviewed_at=FIXED_TIME,
        submission_artifact_id="artifact-submission",
        submission_payload_sha256="c" * 64,
        reviewer_label="Reviewer",
        rationale="Reviewed.",
        decision=decision,
        admissibility_effect=effect,
        non_change_proof=_non_change_proof(_baseline()),
    )
    assert review.admissibility_effect is effect
    with pytest.raises(ValidationError):
        review.rationale = "Changed"


def test_review_rejects_a_decision_effect_mismatch() -> None:
    with pytest.raises(ValidationError, match="do not match"):
        GrwEvidenceReview(
            review_id="review-1",
            reviewed_at=FIXED_TIME,
            submission_artifact_id="artifact-submission",
            submission_payload_sha256="c" * 64,
            reviewer_label="Reviewer",
            rationale="Reviewed.",
            decision=GrwReviewDecision.REJECT,
            admissibility_effect=GrwAdmissibilityEffect.RECORDED_ONLY,
            non_change_proof=_non_change_proof(_baseline()),
        )

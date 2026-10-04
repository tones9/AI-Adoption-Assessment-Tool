from datetime import UTC, datetime, timedelta
import inspect

import pytest

import ai_adoption_engine.preliminary.evaluator as evaluator_module
from ai_adoption_engine.models.candidate_process import ResolvedEvidenceReference
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.preliminary_assessment import (
    PRELIMINARY_INPUT_ORDER,
    PreliminaryConfidence,
    PreliminaryDecidingRuleCode,
    PreliminaryEvidenceClassification,
    PreliminaryInputName,
    ProvisionalDirection,
)
from ai_adoption_engine.models.preliminary_evaluation import (
    PreliminaryEvaluationFailure,
    PreliminaryEvaluationFailureCode,
    PreliminaryEvaluationSuccess,
)
from ai_adoption_engine.models.review import (
    ApprovedProcessReview,
    ConflictStatus,
    InformationOrigin,
    ReviewConflict,
    ReviewDisposition,
    ReviewStatus,
    ReviewedAssertion,
)
from ai_adoption_engine.preliminary.evaluator import PreliminaryAssessmentEvaluator
from ai_adoption_engine.review.approval import _project_business_process
from tests.fakes.review import FIXED_TIME, approved_review


SECOND_TIME = FIXED_TIME + timedelta(hours=1)


def _set_assertion(
    assertion: ReviewedAssertion,
    value,
    evidence: ResolvedEvidenceReference,
    *,
    inferred: bool = False,
    disposition: ReviewDisposition = ReviewDisposition.ACCEPTED,
    origin: InformationOrigin | None = None,
) -> None:
    assertion.value = value
    assertion.knowledge_state = (
        KnowledgeState.INFERRED if inferred else KnowledgeState.KNOWN
    )
    assertion.origin = origin or (
        InformationOrigin.MODEL_INFERRED
        if inferred
        else InformationOrigin.DOCUMENT_SUPPORTED
    )
    assertion.rationale = "Reviewed for deterministic evaluator testing."
    assertion.evidence = (
        [] if assertion.origin is InformationOrigin.HUMAN_SUPPLIED else [evidence]
    )
    assertion.confidence = 0.9 if inferred else None
    assertion.disposition = disposition
    assertion.retained = True


def _set_unknown(assertion: ReviewedAssertion) -> None:
    assertion.value = None
    assertion.knowledge_state = KnowledgeState.UNKNOWN
    assertion.origin = InformationOrigin.UNKNOWN
    assertion.rationale = "The reviewed value remains unknown."
    assertion.evidence = []
    assertion.confidence = None
    assertion.disposition = ReviewDisposition.UNKNOWN_RETAINED
    assertion.retained = True


def _configured_review() -> ApprovedProcessReview:
    approved = approved_review().model_copy(deep=True)
    criterion_values = {
        CriterionName.BUSINESS_VALUE: 4,
        CriterionName.DATA_READINESS: 4,
        CriterionName.IMPLEMENTATION_COMPLEXITY: 2,
        CriterionName.CONVENTIONAL_SOLUTION_FIT: 1,
        CriterionName.AI_CAPABILITY_FIT: 4,
        CriterionName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT: 2,
        CriterionName.HUMAN_JUDGEMENT_REQUIREMENT: 2,
        CriterionName.RISK_CONSEQUENCE: 2,
        CriterionName.PREDICTABILITY: 4,
        CriterionName.REPETITION: 4,
    }
    for step in approved.review.steps:
        evidence = step.activity.evidence[0]
        for criterion in step.criteria:
            _set_assertion(
                criterion.assertion, criterion_values[criterion.name], evidence
            )
        _set_assertion(step.human_accountability_required, False, evidence)
        for index, signal in enumerate(step.capability_signals):
            _set_assertion(signal.assertion, index == 0, evidence)
    return ApprovedProcessReview(
        approval=approved.approval,
        review=approved.review,
        business_process=_project_business_process(approved.review),
    )


def _make_activity_human_supplied(approved: ApprovedProcessReview) -> None:
    step = approved.review.steps[0]
    _set_assertion(
        step.activity,
        step.activity.value,
        step.activity.evidence[0],
        origin=InformationOrigin.HUMAN_SUPPLIED,
    )


def _criterion(approved: ApprovedProcessReview, name: CriterionName, step=0):
    return next(
        item.assertion
        for item in approved.review.steps[step].criteria
        if item.name is name
    )


def _reproject(approved: ApprovedProcessReview) -> ApprovedProcessReview:
    return ApprovedProcessReview(
        approval=approved.approval,
        review=approved.review,
        business_process=_project_business_process(approved.review),
    )


def _evaluate(approved: ApprovedProcessReview, *, run_id="pa-run"):
    return PreliminaryAssessmentEvaluator(
        clock=lambda: FIXED_TIME,
        id_factory=lambda: run_id,
    ).evaluate(approved)


def _first_result(approved: ApprovedProcessReview):
    result = _evaluate(approved)
    assert isinstance(result, PreliminaryEvaluationSuccess)
    return result.assessment.activity_results[0]


@pytest.mark.parametrize(
    ("code", "configure"),
    [
        (PreliminaryDecidingRuleCode.INSUFFICIENT_ACTIVITY_IDENTITY, _make_activity_human_supplied),
        (PreliminaryDecidingRuleCode.INSUFFICIENT_CHANGE_CASE, lambda a: _set_unknown(_criterion(a, CriterionName.BUSINESS_VALUE))),
        (PreliminaryDecidingRuleCode.LIKELY_NO_CHANGE, lambda a: setattr(_criterion(a, CriterionName.BUSINESS_VALUE), "value", 1)),
        (PreliminaryDecidingRuleCode.LIKELY_PROCESS_IMPROVEMENT_FIRST, lambda a: setattr(_criterion(a, CriterionName.DATA_READINESS), "value", 1)),
        (PreliminaryDecidingRuleCode.INSUFFICIENT_READINESS, lambda a: _set_unknown(_criterion(a, CriterionName.DATA_READINESS))),
        (PreliminaryDecidingRuleCode.INSUFFICIENT_CONVENTIONAL_FIT, lambda a: _set_unknown(_criterion(a, CriterionName.CONVENTIONAL_SOLUTION_FIT))),
        (PreliminaryDecidingRuleCode.LIKELY_CONVENTIONAL_AUTOMATION, lambda a: setattr(_criterion(a, CriterionName.CONVENTIONAL_SOLUTION_FIT), "value", 4)),
        (PreliminaryDecidingRuleCode.INSUFFICIENT_AI_FIT, lambda a: _set_unknown(_criterion(a, CriterionName.AI_CAPABILITY_FIT))),
        (PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_LOW_AI_FIT, lambda a: setattr(_criterion(a, CriterionName.AI_CAPABILITY_FIT), "value", 2)),
        (PreliminaryDecidingRuleCode.INSUFFICIENT_AI_CAPABILITY, lambda a: _configure_capabilities(a, unknown_first=True)),
        (PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_NO_CAPABILITY, lambda a: _configure_capabilities(a)),
        (PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_SAFETY_VETO, lambda a: setattr(_criterion(a, CriterionName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT), "value", 4)),
        (PreliminaryDecidingRuleCode.INSUFFICIENT_RESIDUAL_RISK, lambda a: _set_unknown(_criterion(a, CriterionName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT))),
        (PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_CONSTRAINT, lambda a: setattr(_criterion(a, CriterionName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT), "value", 3)),
        (PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_AUTONOMY_UNKNOWN, lambda a: _set_unknown(_criterion(a, CriterionName.HUMAN_JUDGEMENT_REQUIREMENT))),
        (PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION, lambda a: None),
    ],
)
def test_every_deciding_rule_path_is_deterministic(code, configure) -> None:
    approved = _configured_review()
    configure(approved)

    activity = _first_result(_reproject(approved))

    assert activity.deciding_rule_code is code
    assert activity.provisional_direction is not None
    assert activity.decision_input_trace[0].input_name is PreliminaryInputName.ACTIVITY_IDENTITY
    assert [item.input_name for item in activity.decision_input_trace] == list(
        PRELIMINARY_INPUT_ORDER
    )


def _configure_capabilities(
    approved: ApprovedProcessReview, *, unknown_first: bool = False
) -> None:
    step = approved.review.steps[0]
    evidence = step.activity.evidence[0]
    for signal in step.capability_signals:
        _set_assertion(signal.assertion, False, evidence)
    if unknown_first:
        _set_unknown(step.capability_signals[0].assertion)


@pytest.mark.parametrize(
    ("target", "value", "expected"),
    [
        (CriterionName.BUSINESS_VALUE, 1, PreliminaryDecidingRuleCode.LIKELY_NO_CHANGE),
        (CriterionName.BUSINESS_VALUE, 2, PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION),
        (CriterionName.DATA_READINESS, 1, PreliminaryDecidingRuleCode.LIKELY_PROCESS_IMPROVEMENT_FIRST),
        (CriterionName.DATA_READINESS, 2, PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_CONSTRAINT),
        (CriterionName.DATA_READINESS, 3, PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_CONSTRAINT),
        (CriterionName.DATA_READINESS, 4, PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION),
        (CriterionName.IMPLEMENTATION_COMPLEXITY, 3, PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION),
        (CriterionName.IMPLEMENTATION_COMPLEXITY, 4, PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_CONSTRAINT),
        (CriterionName.IMPLEMENTATION_COMPLEXITY, 5, PreliminaryDecidingRuleCode.LIKELY_PROCESS_IMPROVEMENT_FIRST),
        (CriterionName.CONVENTIONAL_SOLUTION_FIT, 3, PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION),
        (CriterionName.CONVENTIONAL_SOLUTION_FIT, 4, PreliminaryDecidingRuleCode.LIKELY_CONVENTIONAL_AUTOMATION),
        (CriterionName.AI_CAPABILITY_FIT, 2, PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_LOW_AI_FIT),
        (CriterionName.AI_CAPABILITY_FIT, 3, PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION),
        (CriterionName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT, 2, PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION),
        (CriterionName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT, 3, PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_CONSTRAINT),
        (CriterionName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT, 4, PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_SAFETY_VETO),
        (CriterionName.HUMAN_JUDGEMENT_REQUIREMENT, 2, PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION),
        (CriterionName.HUMAN_JUDGEMENT_REQUIREMENT, 3, PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_CONSTRAINT),
        (CriterionName.RISK_CONSEQUENCE, 2, PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION),
        (CriterionName.RISK_CONSEQUENCE, 3, PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_CONSTRAINT),
        (CriterionName.PREDICTABILITY, 3, PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_CONSTRAINT),
        (CriterionName.PREDICTABILITY, 4, PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION),
    ],
)
def test_ordinal_threshold_boundaries_are_exact(target, value, expected) -> None:
    approved = _configured_review()
    _criterion(approved, target).value = value

    assert _first_result(_reproject(approved)).deciding_rule_code is expected


@pytest.mark.parametrize(
    ("accountability", "expected"),
    [
        (False, PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION),
        (True, PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_CONSTRAINT),
    ],
)
def test_accountability_boundary_is_exact(accountability, expected) -> None:
    approved = _configured_review()
    approved.review.steps[0].human_accountability_required.value = accountability

    assert _first_result(_reproject(approved)).deciding_rule_code is expected


def test_unknown_residual_risk_is_pa_051_insufficient_low() -> None:
    approved = _configured_review()
    _set_unknown(
        _criterion(approved, CriterionName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT)
    )

    activity = _first_result(_reproject(approved))

    assert activity.deciding_rule_code is PreliminaryDecidingRuleCode.INSUFFICIENT_RESIDUAL_RISK
    assert activity.provisional_direction is ProvisionalDirection.INSUFFICIENT_BASIS
    assert activity.confidence.level is PreliminaryConfidence.LOW


def test_conflicted_residual_risk_is_pa_051_and_trace_value_is_null() -> None:
    approved = _configured_review()
    approved.review.conflicts.append(
        ReviewConflict(
            conflict_id="residual-conflict",
            code="contradictory-documentary-evidence",
            message="Reviewed residual-risk evidence conflicts.",
            blocking=False,
            field_path=(
                f"steps.{approved.review.steps[0].candidate_step_id}.criteria."
                "residual_risk_with_human_oversight"
            ),
            status=ConflictStatus.OPEN,
        )
    )

    activity = _first_result(_reproject(approved))

    assert activity.deciding_rule_code is PreliminaryDecidingRuleCode.INSUFFICIENT_RESIDUAL_RISK
    residual = next(
        item
        for item in activity.decision_input_trace
        if item.input_name
        is PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT
    )
    assert residual.classification is PreliminaryEvidenceClassification.CONFLICT
    assert residual.normalized_value is None
    assert activity.confidence.level is PreliminaryConfidence.LOW


def test_documented_one_inference_and_two_inferences_map_to_high_medium_low() -> None:
    high = _configured_review()
    high_result = _first_result(high)

    medium = _configured_review()
    evidence = medium.review.steps[0].activity.evidence[0]
    _set_assertion(
        _criterion(medium, CriterionName.BUSINESS_VALUE),
        4,
        evidence,
        inferred=True,
    )
    medium_result = _first_result(_reproject(medium))

    low = _configured_review()
    evidence = low.review.steps[0].activity.evidence[0]
    for name in (CriterionName.BUSINESS_VALUE, CriterionName.DATA_READINESS):
        _set_assertion(_criterion(low, name), 4, evidence, inferred=True)
    low_result = _first_result(_reproject(low))

    assert high_result.confidence.level is PreliminaryConfidence.HIGH
    assert medium_result.confidence.level is PreliminaryConfidence.MEDIUM
    assert low_result.confidence.level is PreliminaryConfidence.LOW


def test_unreviewed_high_confidence_model_suggestion_is_not_admissible() -> None:
    approved = _configured_review()
    evidence = approved.review.steps[0].activity.evidence[0]
    _set_assertion(
        _criterion(approved, CriterionName.BUSINESS_VALUE),
        5,
        evidence,
        inferred=True,
        disposition=ReviewDisposition.UNREVIEWED,
    )

    activity = _first_result(_reproject(approved))

    assert activity.deciding_rule_code is PreliminaryDecidingRuleCode.INSUFFICIENT_CHANGE_CASE
    business = next(
        item
        for item in activity.decision_input_trace
        if item.input_name is PreliminaryInputName.BUSINESS_VALUE
    )
    assert business.classification is PreliminaryEvidenceClassification.UNKNOWN


def test_corrected_traceable_model_inference_is_admissible() -> None:
    approved = _configured_review()
    evidence = approved.review.steps[0].activity.evidence[0]
    _set_assertion(
        _criterion(approved, CriterionName.BUSINESS_VALUE),
        4,
        evidence,
        inferred=True,
        disposition=ReviewDisposition.CORRECTED,
    )

    activity = _first_result(_reproject(approved))

    assert activity.deciding_rule_code is PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION
    assert activity.confidence.level is PreliminaryConfidence.MEDIUM
    assert activity.reasonable_inferences


@pytest.mark.parametrize("mode", ["rejected", "non-retained"])
def test_rejected_and_non_retained_values_are_not_admissible(mode) -> None:
    approved = _configured_review()
    assertion = _criterion(approved, CriterionName.BUSINESS_VALUE)
    if mode == "rejected":
        assertion.disposition = ReviewDisposition.REJECTED
    else:
        assertion.retained = False

    activity = _first_result(_reproject(approved))

    assert activity.deciding_rule_code is PreliminaryDecidingRuleCode.INSUFFICIENT_CHANGE_CASE


def test_human_supplied_value_is_context_only_and_cannot_satisfy_threshold() -> None:
    approved = _configured_review()
    evidence = approved.review.steps[0].activity.evidence[0]
    _set_assertion(
        _criterion(approved, CriterionName.BUSINESS_VALUE),
        5,
        evidence,
        origin=InformationOrigin.HUMAN_SUPPLIED,
    )

    activity = _first_result(_reproject(approved))

    assert activity.deciding_rule_code is PreliminaryDecidingRuleCode.INSUFFICIENT_CHANGE_CASE
    assert activity.confidence.level is PreliminaryConfidence.LOW


def test_non_material_inference_does_not_change_direction_or_confidence() -> None:
    approved = _configured_review()
    evidence = approved.review.steps[0].activity.evidence[0]
    _set_assertion(
        _criterion(approved, CriterionName.REPETITION),
        5,
        evidence,
        inferred=True,
    )

    activity = _first_result(_reproject(approved))

    assert activity.deciding_rule_code is PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION
    assert activity.confidence.level is PreliminaryConfidence.HIGH
    repetition = next(
        item
        for item in activity.decision_input_trace
        if item.input_name is PreliminaryInputName.REPETITION
    )
    assert repetition.material is False


def test_process_confidence_is_weakest_activity_confidence() -> None:
    approved = _configured_review()
    evidence = approved.review.steps[1].activity.evidence[0]
    _set_assertion(
        _criterion(approved, CriterionName.BUSINESS_VALUE, step=1),
        4,
        evidence,
        inferred=True,
    )

    result = _evaluate(_reproject(approved))

    assert isinstance(result, PreliminaryEvaluationSuccess)
    assert [item.confidence.level for item in result.assessment.activity_results] == [
        PreliminaryConfidence.HIGH,
        PreliminaryConfidence.MEDIUM,
    ]
    assert result.assessment.confidence.level is PreliminaryConfidence.MEDIUM


def test_other_document_evidence_returns_typed_failure_without_partial_result() -> None:
    approved = _configured_review()
    assertion = _criterion(approved, CriterionName.BUSINESS_VALUE)
    other = assertion.evidence[0].model_copy(
        update={"document_id": f"doc-{'f' * 64}"}
    )
    assertion.evidence = [other]

    result = _evaluate(_reproject(approved))

    assert isinstance(result, PreliminaryEvaluationFailure)
    assert result.assessment is None
    assert result.errors[0].code is PreliminaryEvaluationFailureCode.SOURCE_DOCUMENT_MISMATCH


def test_forged_projection_returns_typed_failure() -> None:
    approved = _configured_review()
    forged = ApprovedProcessReview(
        approval=approved.approval,
        review=approved.review,
        business_process=approved.business_process.model_copy(update={"name": "Forged"}),
    )

    result = _evaluate(forged)

    assert isinstance(result, PreliminaryEvaluationFailure)
    assert result.errors[0].code is PreliminaryEvaluationFailureCode.INVALID_PROCESS_PROJECTION


def test_open_blocking_conflict_returns_typed_failure() -> None:
    approved = _configured_review()
    approved.review.conflicts.append(
        ReviewConflict(
            conflict_id="blocking-1",
            code="blocking",
            message="Must resolve.",
            blocking=True,
            field_path="steps.cstep-1.activity",
            status=ConflictStatus.OPEN,
        )
    )

    result = _evaluate(_reproject(approved))

    assert isinstance(result, PreliminaryEvaluationFailure)
    assert result.errors[0].code is PreliminaryEvaluationFailureCode.BLOCKING_REVIEW_CONFLICT


def test_evaluator_accepts_only_approved_process_review() -> None:
    result = PreliminaryAssessmentEvaluator().evaluate(object())  # type: ignore[arg-type]

    assert isinstance(result, PreliminaryEvaluationFailure)
    assert result.errors[0].code is PreliminaryEvaluationFailureCode.APPROVED_REVIEW_REQUIRED


def test_invalid_approval_artifact_returns_typed_failure() -> None:
    approved = _configured_review()
    approved.review.status = ReviewStatus.IN_REVIEW

    result = _evaluate(_reproject(approved))

    assert isinstance(result, PreliminaryEvaluationFailure)
    assert result.errors[0].code is PreliminaryEvaluationFailureCode.INVALID_APPROVAL_ARTIFACT


def test_unapproved_rule_content_returns_typed_failure() -> None:
    rules = evaluator_module.PRELIMINARY_EVALUATOR_RULES_V0_1.model_copy(
        update={"human_supplied_treatment": "NOT_CONTEXT_ONLY"}
    )

    result = PreliminaryAssessmentEvaluator(rules=rules).evaluate(_configured_review())

    assert isinstance(result, PreliminaryEvaluationFailure)
    assert result.errors[0].code is PreliminaryEvaluationFailureCode.INVALID_RULE_SET


def test_invalid_injected_creation_dependency_returns_output_failure() -> None:
    result = PreliminaryAssessmentEvaluator(
        clock=lambda: datetime(2026, 9, 28, 12, 0),
        id_factory=lambda: "pa-run",
    ).evaluate(_configured_review())

    assert isinstance(result, PreliminaryEvaluationFailure)
    assert result.errors[0].code is PreliminaryEvaluationFailureCode.OUTPUT_VALIDATION_FAILED


def test_substantive_and_full_envelope_repeatability() -> None:
    approved = _configured_review()
    first = PreliminaryAssessmentEvaluator(
        clock=lambda: FIXED_TIME, id_factory=lambda: "pa-fixed"
    ).evaluate(approved)
    second = PreliminaryAssessmentEvaluator(
        clock=lambda: SECOND_TIME, id_factory=lambda: "pa-other"
    ).evaluate(approved)
    exact = PreliminaryAssessmentEvaluator(
        clock=lambda: FIXED_TIME, id_factory=lambda: "pa-fixed"
    ).evaluate(approved)

    assert isinstance(first, PreliminaryEvaluationSuccess)
    assert isinstance(second, PreliminaryEvaluationSuccess)
    assert isinstance(exact, PreliminaryEvaluationSuccess)
    assert first.assessment.substantive_json_bytes() == second.assessment.substantive_json_bytes()
    assert first.assessment.canonical_json_bytes() != second.assessment.canonical_json_bytes()
    assert first.assessment.canonical_json_bytes() == exact.assessment.canonical_json_bytes()


def test_evaluator_does_not_depend_on_formal_engine_or_result_models() -> None:
    source = inspect.getsource(evaluator_module)

    assert "four_gate" not in source
    assert "OutcomeCode" not in source
    assert "DecisionPackage" not in source
    assert "engine.evaluate" not in source

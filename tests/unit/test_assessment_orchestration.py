from datetime import timedelta

from ai_adoption_engine.application.assessment import IntegratedAssessmentService
from ai_adoption_engine.application.fingerprints import (
    fingerprint_business_process,
    fingerprint_decision_policy,
)
from ai_adoption_engine.decision.engine import AssessmentEngine
from ai_adoption_engine.decision.policy import DecisionPolicy
from ai_adoption_engine.models.assessment import ProcessAssessment
from ai_adoption_engine.models.enums import (
    CriterionName,
    PriorityStatus,
    RecommendationMode,
)
from ai_adoption_engine.models.integrated_assessment import (
    IntegratedAssessmentFailure,
    IntegratedAssessmentSuccess,
    IntegrationFailureCode,
)
from ai_adoption_engine.models.process import BusinessProcess
from ai_adoption_engine.models.review import ConflictStatus, ReviewConflict
from tests.fakes.review import (
    FIXED_TIME,
    approved_review,
    candidate_result,
    review_service,
)


def _service(policy: DecisionPolicy, **kwargs) -> IntegratedAssessmentService:
    return IntegratedAssessmentService(
        policy_loader=lambda: policy,
        clock=lambda: FIXED_TIME,
        run_id_factory=lambda: "assessment-fixture",
        **kwargs,
    )


def _four_step_approved_review():
    approved = approved_review().model_copy(deep=True)
    base_reviewed = approved.review.steps[0]
    base_candidate = approved.review.original_candidate.steps[0]
    base_process = approved.business_process.steps[0]
    reviewed_steps = []
    candidate_steps = []
    process_steps = []
    for sequence in range(1, 5):
        step_id = f"mode-step-{sequence}"
        activity = f"Synthetic mode activity {sequence}"
        candidate_step = base_candidate.model_copy(deep=True)
        candidate_step.candidate_step_id = step_id
        candidate_step.sequence = sequence
        candidate_step.activity.value = activity
        candidate_steps.append(candidate_step)

        reviewed_step = base_reviewed.model_copy(deep=True)
        reviewed_step.original = candidate_step
        reviewed_step.candidate_step_id = step_id
        reviewed_step.sequence = sequence
        reviewed_step.activity.value = activity
        reviewed_step.activity.original = candidate_step.activity
        reviewed_steps.append(reviewed_step)

        process_step = base_process.model_copy(deep=True)
        process_step.step_id = step_id
        process_step.sequence = sequence
        process_step.activity = activity
        process_steps.append(process_step)

    approved.review.steps = reviewed_steps
    approved.review.original_candidate.steps = candidate_steps
    required_ids = {
        item.evidence_id for item in approved.review.process_name.evidence
    } | {
        item.evidence_id for item in reviewed_steps[0].activity.evidence
    }
    process_payload = approved.business_process.model_dump(
        mode="json", exclude={"steps", "evidence"}
    )
    process_payload["steps"] = [item.model_dump(mode="json") for item in process_steps]
    process_payload["evidence"] = [
        item.model_dump(mode="json")
        for item in approved.business_process.evidence
        if item.evidence_id in required_ids
    ]
    expanded_process = BusinessProcess.model_validate(process_payload)
    return approved.model_copy(update={"business_process": expanded_process})


def test_approved_review_invokes_real_engine_once(policy: DecisionPolicy) -> None:
    calls = []

    class CountingEngine:
        def __init__(self, supplied_policy: DecisionPolicy) -> None:
            self.engine = AssessmentEngine(supplied_policy)

        def assess(self, process: BusinessProcess) -> ProcessAssessment:
            calls.append(process.process_id)
            return self.engine.assess(process)

    result = _service(policy, engine_factory=CountingEngine).assess(approved_review())
    assert isinstance(result, IntegratedAssessmentSuccess)
    assert calls == [result.lineage.validated_process_id]
    assert result.policy.policy_version == policy.version
    artifact = approved_review()
    fingerprinted = _service(policy).assess(artifact)
    assert isinstance(fingerprinted, IntegratedAssessmentSuccess)
    assert fingerprinted.lineage.validated_process_fingerprint == (
        fingerprint_business_process(artifact.business_process)
    )
    assert fingerprinted.policy.decision_policy_fingerprint == (
        fingerprint_decision_policy(policy)
    )


def test_nonapproved_inputs_are_rejected_before_dependencies(
    policy: DecisionPolicy,
) -> None:
    def fail_policy_load():
        raise AssertionError("Policy loading must not occur")

    service = IntegratedAssessmentService(
        policy_loader=fail_policy_load,
        engine_factory=lambda _: (_ for _ in ()).throw(
            AssertionError("Engine construction must not occur")
        ),
        clock=lambda: FIXED_TIME,
        run_id_factory=lambda: "rejected-input",
    )
    extraction = candidate_result()
    review = review_service().start_review(extraction)
    for item in (extraction.candidate, extraction, review):
        result = service.assess(item)  # type: ignore[arg-type]
        assert isinstance(result, IntegratedAssessmentFailure)
        assert result.errors[0].code is IntegrationFailureCode.APPROVAL_REQUIRED


def test_blocked_approved_artifact_is_rejected_before_engine(
    policy: DecisionPolicy,
) -> None:
    approved = approved_review().model_copy(deep=True)
    approved.review.conflicts.append(
        ReviewConflict(
            conflict_id="late-blocker",
            code="late-structural-conflict",
            message="A structural conflict was discovered after approval.",
            blocking=True,
            status=ConflictStatus.OPEN,
        )
    )
    result = _service(
        policy,
        engine_factory=lambda _: (_ for _ in ()).throw(
            AssertionError("Blocked review must not invoke engine")
        ),
    ).assess(approved)
    assert isinstance(result, IntegratedAssessmentFailure)
    assert result.errors[0].code is IntegrationFailureCode.BLOCKED_REVIEW


def test_forged_projection_is_rejected_before_engine(
    policy: DecisionPolicy,
) -> None:
    approved = approved_review()
    forged_process = approved.business_process.model_copy(deep=True)
    forged_process.steps[0].activity = "Unreviewed replacement activity"
    forged = approved.model_copy(update={"business_process": forged_process})
    result = _service(
        policy,
        engine_factory=lambda _: (_ for _ in ()).throw(
            AssertionError("Forged artifact must not invoke engine")
        ),
    ).assess(forged)
    assert isinstance(result, IntegratedAssessmentFailure)
    assert result.errors[0].code is IntegrationFailureCode.INVALID_APPROVAL_ARTIFACT


def test_forged_descriptive_projection_is_also_rejected(
    policy: DecisionPolicy,
) -> None:
    approved = approved_review()
    forged_process = approved.business_process.model_copy(
        update={"description": "A description that was never reviewed."}, deep=True
    )
    result = _service(policy).assess(
        approved.model_copy(update={"business_process": forged_process})
    )
    assert isinstance(result, IntegratedAssessmentFailure)
    assert result.errors[0].code is IntegrationFailureCode.INVALID_APPROVAL_ARTIFACT


def test_unavailable_projection_is_a_structured_failure(
    policy: DecisionPolicy,
) -> None:
    malformed = approved_review().model_copy(update={"business_process": None})
    result = _service(policy).assess(malformed)
    assert isinstance(result, IntegratedAssessmentFailure)
    assert result.errors[0].code is IntegrationFailureCode.PROJECTION_UNAVAILABLE


def test_invalid_projection_is_a_structured_failure(
    policy: DecisionPolicy,
) -> None:
    approved = approved_review()
    malformed_process = approved.business_process.model_copy(update={"steps": []})
    malformed = approved.model_copy(update={"business_process": malformed_process})
    result = _service(policy).assess(malformed)
    assert isinstance(result, IntegratedAssessmentFailure)
    assert result.errors[0].code is IntegrationFailureCode.INVALID_PROCESS_PROJECTION


def test_policy_load_failure_is_structured() -> None:
    service = IntegratedAssessmentService(
        policy_loader=lambda: (_ for _ in ()).throw(RuntimeError("controlled")),
        clock=lambda: FIXED_TIME,
        run_id_factory=lambda: "policy-failure",
    )
    result = service.assess(approved_review())
    assert isinstance(result, IntegratedAssessmentFailure)
    assert result.errors[0].code is IntegrationFailureCode.POLICY_LOAD_FAILED


def test_engine_failure_is_structured(policy: DecisionPolicy) -> None:
    class FailingEngine:
        def assess(self, process: BusinessProcess) -> ProcessAssessment:
            raise RuntimeError("controlled")

    result = _service(policy, engine_factory=lambda _: FailingEngine()).assess(
        approved_review()
    )
    assert isinstance(result, IntegratedAssessmentFailure)
    assert result.errors[0].code is IntegrationFailureCode.ASSESSMENT_ENGINE_FAILED


def test_missing_step_assessment_fails_whole_run(policy: DecisionPolicy) -> None:
    class IncompleteEngine:
        def assess(self, process: BusinessProcess) -> ProcessAssessment:
            complete = AssessmentEngine(policy).assess(process)
            return complete.model_copy(
                update={"step_assessments": complete.step_assessments[:-1]}
            )

    result = _service(policy, engine_factory=lambda _: IncompleteEngine()).assess(
        approved_review()
    )
    assert isinstance(result, IntegratedAssessmentFailure)
    assert result.errors[0].code is IntegrationFailureCode.INVALID_ENGINE_OUTPUT


def test_incomplete_step_assessment_contract_fails_whole_run(
    policy: DecisionPolicy,
) -> None:
    class MissingCriteriaEngine:
        def assess(self, process: BusinessProcess) -> ProcessAssessment:
            complete = AssessmentEngine(policy).assess(process)
            first = complete.step_assessments[0].model_copy(update={"criteria": []})
            return complete.model_copy(
                update={"step_assessments": [first, *complete.step_assessments[1:]]}
            )

    result = _service(policy, engine_factory=lambda _: MissingCriteriaEngine()).assess(
        approved_review()
    )
    assert isinstance(result, IntegratedAssessmentFailure)
    assert result.errors[0].code is IntegrationFailureCode.INVALID_ENGINE_OUTPUT
    assert result.errors[0].step_id is not None


def test_investigate_and_unknowns_are_successful_outcomes(
    policy: DecisionPolicy,
) -> None:
    result = _service(policy).assess(approved_review())
    assert isinstance(result, IntegratedAssessmentSuccess)
    assert all(
        item.recommendation_mode is RecommendationMode.INVESTIGATE_FURTHER
        for item in result.process_assessment.step_assessments
    )
    assert all(
        item.criteria[0].value is None
        for item in result.process_assessment.step_assessments
    )


def test_incomplete_priority_is_not_a_pipeline_failure(
    policy: DecisionPolicy,
) -> None:
    class IncompletePriorityEngine:
        def assess(self, process: BusinessProcess) -> ProcessAssessment:
            assessed = AssessmentEngine(policy).assess(process)
            first = assessed.step_assessments[0].model_copy(
                update={
                    "recommendation_mode": RecommendationMode.AUGMENT,
                    "priority_status": PriorityStatus.INCOMPLETE,
                    "priority": None,
                    "priority_missing_criteria": [CriterionName.REPETITION],
                }
            )
            return assessed.model_copy(
                update={"step_assessments": [first, *assessed.step_assessments[1:]]}
            )

    result = _service(
        policy, engine_factory=lambda _: IncompletePriorityEngine()
    ).assess(approved_review())
    assert isinstance(result, IntegratedAssessmentSuccess)
    assert result.process_assessment.step_assessments[0].priority_status is (
        PriorityStatus.INCOMPLETE
    )


def test_all_four_recommendation_modes_flow_through_unchanged(
    policy: DecisionPolicy,
) -> None:
    approved = _four_step_approved_review()
    expected_modes = [
        RecommendationMode.AUTOMATE,
        RecommendationMode.AUGMENT,
        RecommendationMode.INVESTIGATE_FURTHER,
        RecommendationMode.DO_NOT_RECOMMEND,
    ]

    class FourModeEngine:
        def assess(self, supplied: BusinessProcess) -> ProcessAssessment:
            baseline = AssessmentEngine(policy).assess(supplied)
            steps = [
                target.model_copy(
                    update={"recommendation_mode": mode},
                    deep=True,
                )
                for mode, target in zip(
                    expected_modes, baseline.step_assessments, strict=True
                )
            ]
            return ProcessAssessment(
                process_id=supplied.process_id,
                process_name=supplied.name,
                policy_id=policy.policy_id,
                policy_version=policy.version,
                policy_status=policy.status,
                step_assessments=steps,
            )

    result = _service(policy, engine_factory=lambda _: FourModeEngine()).assess(
        approved
    )
    assert isinstance(result, IntegratedAssessmentSuccess)
    assert [
        item.recommendation_mode
        for item in result.process_assessment.step_assessments
    ] == expected_modes


def test_run_metadata_changes_do_not_change_input_fingerprints(
    policy: DecisionPolicy,
) -> None:
    approved = approved_review()
    first = IntegratedAssessmentService(
        policy_loader=lambda: policy,
        clock=lambda: FIXED_TIME,
        run_id_factory=lambda: "run-one",
    ).assess(approved)
    second = IntegratedAssessmentService(
        policy_loader=lambda: policy,
        clock=lambda: FIXED_TIME + timedelta(days=1),
        run_id_factory=lambda: "run-two",
    ).assess(approved)
    assert isinstance(first, IntegratedAssessmentSuccess)
    assert isinstance(second, IntegratedAssessmentSuccess)
    assert first.metadata != second.metadata
    assert (
        first.lineage.validated_process_fingerprint
        == second.lineage.validated_process_fingerprint
    )
    assert (
        first.policy.decision_policy_fingerprint
        == second.policy.decision_policy_fingerprint
    )

from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_adoption_engine.application.fingerprints import (
    fingerprint_four_gate_policy,
)
from ai_adoption_engine.application.four_gate_assessment import (
    FourGateIntegratedAssessmentService,
)
from ai_adoption_engine.decision.four_gate_engine import FourGateAssessmentEngine
from ai_adoption_engine.decision.four_gate_policy import (
    FourGateDecisionPolicy,
    load_four_gate_policy,
)
from ai_adoption_engine.decision.policy import load_policy
from ai_adoption_engine.models.four_gate_assessment import FourGateProcessAssessment
from ai_adoption_engine.models.four_gate_integrated_assessment import (
    FourGateIntegratedAssessmentFailure,
    FourGateIntegratedAssessmentSuccess,
)
from ai_adoption_engine.models.integrated_assessment import IntegrationFailureCode
from ai_adoption_engine.models.process import BusinessProcess
from ai_adoption_engine.models.review import ConflictStatus, ReviewConflict
from tests.fakes.review import (
    FIXED_TIME,
    approved_review,
    candidate_result,
    review_service,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SUCCESSOR_POLICY_PATH = PROJECT_ROOT / "config" / "decision_policy.v0.3.json"
LEGACY_POLICY_PATH = PROJECT_ROOT / "config" / "decision_policy.v0.2.json"


@pytest.fixture
def successor_policy() -> FourGateDecisionPolicy:
    return load_four_gate_policy(SUCCESSOR_POLICY_PATH)


def _service(
    policy: FourGateDecisionPolicy,
    **kwargs,
) -> FourGateIntegratedAssessmentService:
    return FourGateIntegratedAssessmentService(
        policy_loader=lambda: policy,
        clock=lambda: FIXED_TIME,
        run_id_factory=lambda: "four-gate-assessment-fixture",
        **kwargs,
    )


def test_approved_review_invokes_explicit_successor_and_returns_v02(
    successor_policy: FourGateDecisionPolicy,
) -> None:
    calls: list[str] = []

    class CountingEngine:
        def __init__(self, policy: FourGateDecisionPolicy) -> None:
            self.engine = FourGateAssessmentEngine(policy)

        def assess(self, process: BusinessProcess) -> FourGateProcessAssessment:
            calls.append(process.process_id)
            return self.engine.assess(process)

    approved = approved_review()
    result = _service(
        successor_policy,
        engine_factory=CountingEngine,
    ).assess(approved)

    assert isinstance(result, FourGateIntegratedAssessmentSuccess)
    assert calls == [approved.business_process.process_id]
    assert result.metadata.integration_schema_version == "phase5-v0.2"
    assert result.metadata.phase1_contract_version == "phase1-v0.4"
    assert result.process_assessment.decision_contract_version == "phase1-v0.4"
    assert result.process_assessment.framework_id == "four-gate-framework.v0.1"
    assert result.policy.policy_id == "decision_policy.v0.3"
    assert result.policy.policy_version == "0.3.0"
    assert result.policy.decision_policy_fingerprint == (
        fingerprint_four_gate_policy(successor_policy)
    )
    assert [item.step_id for item in result.step_traceability] == [
        item.step_id for item in approved.business_process.steps
    ]

    first = result.step_traceability[0]
    assert not hasattr(first, "recommendation_path")
    assessed_base = (
        f"process_assessment.step_assessments[step_id={first.step_id}]"
    )
    assert first.decision_status_path == f"{assessed_base}.decision_status"
    assert first.change_disposition_path == f"{assessed_base}.change_disposition"
    assert first.readiness_disposition_path == (
        f"{assessed_base}.readiness_disposition"
    )
    assert first.selected_intervention_family_path == (
        f"{assessed_base}.selected_intervention_family"
    )
    assert first.autonomy_ceiling_path == f"{assessed_base}.autonomy_ceiling"
    assert first.outcome_code_path == f"{assessed_base}.outcome_code"
    assert first.gate_results_path == f"{assessed_base}.gate_results"
    assert len(first.criteria) == 10
    assert len(first.capability_signals) == 10
    assert all(item.assessment_field_path for item in first.criteria)
    assert all(item.assessment_field_path for item in first.capability_signals)


def test_nonapproved_inputs_fail_before_policy_or_engine() -> None:
    calls = {"policy": 0, "engine": 0}

    def fail_policy_load():
        calls["policy"] += 1
        raise AssertionError("Policy loading must not occur")

    def fail_engine(_):
        calls["engine"] += 1
        raise AssertionError("Engine construction must not occur")

    service = FourGateIntegratedAssessmentService(
        policy_loader=fail_policy_load,
        engine_factory=fail_engine,
        clock=lambda: FIXED_TIME,
        run_id_factory=lambda: "rejected-successor-input",
    )
    extraction = candidate_result()
    review = review_service().start_review(extraction)

    for item in (extraction.candidate, extraction, review):
        result = service.assess(item)  # type: ignore[arg-type]
        assert isinstance(result, FourGateIntegratedAssessmentFailure)
        assert result.errors[0].code is IntegrationFailureCode.APPROVAL_REQUIRED
    assert calls == {"policy": 0, "engine": 0}


@pytest.mark.parametrize("failure_kind", ["blocked", "forged"])
def test_invalid_approved_artifacts_fail_before_policy_loading(
    failure_kind: str,
) -> None:
    approved = approved_review().model_copy(deep=True)
    if failure_kind == "blocked":
        approved.review.conflicts.append(
            ReviewConflict(
                conflict_id="late-successor-blocker",
                code="late-structural-conflict",
                message="A blocking conflict appeared after approval.",
                blocking=True,
                status=ConflictStatus.OPEN,
            )
        )
        expected = IntegrationFailureCode.BLOCKED_REVIEW
    else:
        forged_process = approved.business_process.model_copy(deep=True)
        forged_process.steps[0].activity = "Unreviewed activity"
        approved = approved.model_copy(update={"business_process": forged_process})
        expected = IntegrationFailureCode.INVALID_APPROVAL_ARTIFACT

    result = FourGateIntegratedAssessmentService(
        policy_loader=lambda: (_ for _ in ()).throw(
            AssertionError("Invalid approval reached policy loading")
        ),
        clock=lambda: FIXED_TIME,
        run_id_factory=lambda: "invalid-successor-approval",
    ).assess(approved)

    assert isinstance(result, FourGateIntegratedAssessmentFailure)
    assert result.errors[0].code is expected


@pytest.mark.parametrize("invalid_policy", ["legacy", "malformed"])
def test_unknown_or_malformed_policy_fails_closed(invalid_policy: str) -> None:
    if invalid_policy == "legacy":
        supplied_policy = load_policy(LEGACY_POLICY_PATH)
    else:
        supplied_policy = load_four_gate_policy(SUCCESSOR_POLICY_PATH).model_dump(
            mode="json"
        )
        supplied_policy["version"] = "0.3.1"

    result = FourGateIntegratedAssessmentService(
        policy_loader=lambda: supplied_policy,  # type: ignore[arg-type,return-value]
        engine_factory=lambda _: (_ for _ in ()).throw(
            AssertionError("Invalid policy reached engine construction")
        ),
        clock=lambda: FIXED_TIME,
        run_id_factory=lambda: "invalid-successor-policy",
    ).assess(approved_review())

    assert isinstance(result, FourGateIntegratedAssessmentFailure)
    assert result.errors[0].code is IntegrationFailureCode.POLICY_LOAD_FAILED
    assert result.policy is None


def test_engine_failure_and_malformed_output_are_structured(
    successor_policy: FourGateDecisionPolicy,
) -> None:
    failing = _service(
        successor_policy,
        engine_factory=lambda _: (_ for _ in ()).throw(RuntimeError("controlled")),
    ).assess(approved_review())
    assert isinstance(failing, FourGateIntegratedAssessmentFailure)
    assert failing.errors[0].code is IntegrationFailureCode.ASSESSMENT_ENGINE_FAILED
    assert failing.policy is not None

    class MalformedEngine:
        def assess(self, process: BusinessProcess):
            del process
            return {"not": "a four-gate assessment"}

    malformed = _service(
        successor_policy,
        engine_factory=lambda _: MalformedEngine(),
    ).assess(approved_review())
    assert isinstance(malformed, FourGateIntegratedAssessmentFailure)
    assert malformed.errors[0].code is IntegrationFailureCode.INVALID_ENGINE_OUTPUT


def test_incomplete_or_input_drifting_engine_output_fails_closed(
    successor_policy: FourGateDecisionPolicy,
) -> None:
    class IncompleteEngine:
        def assess(self, process: BusinessProcess) -> FourGateProcessAssessment:
            complete = FourGateAssessmentEngine(successor_policy).assess(process)
            return complete.model_copy(
                update={"step_assessments": complete.step_assessments[:-1]}
            )

    incomplete = _service(
        successor_policy,
        engine_factory=lambda _: IncompleteEngine(),
    ).assess(approved_review())
    assert isinstance(incomplete, FourGateIntegratedAssessmentFailure)
    assert incomplete.errors[0].code is IntegrationFailureCode.INVALID_ENGINE_OUTPUT

    class InputDriftEngine:
        def assess(self, process: BusinessProcess) -> FourGateProcessAssessment:
            complete = FourGateAssessmentEngine(successor_policy).assess(process)
            first = complete.step_assessments[0]
            changed_criterion = first.criteria[0].model_copy(
                update={"rationale": "Engine-created rationale drift."}
            )
            changed_first = first.model_copy(
                update={"criteria": [changed_criterion, *first.criteria[1:]]}
            )
            return complete.model_copy(
                update={
                    "step_assessments": [
                        changed_first,
                        *complete.step_assessments[1:],
                    ]
                }
            )

    drift = _service(
        successor_policy,
        engine_factory=lambda _: InputDriftEngine(),
    ).assess(approved_review())
    assert isinstance(drift, FourGateIntegratedAssessmentFailure)
    assert drift.errors[0].code is IntegrationFailureCode.INVALID_ENGINE_OUTPUT
    assert drift.errors[0].step_id is not None


def test_successor_result_rejects_mutated_trace_paths(
    successor_policy: FourGateDecisionPolicy,
) -> None:
    result = _service(successor_policy).assess(approved_review())
    assert isinstance(result, FourGateIntegratedAssessmentSuccess)
    payload = result.model_dump(mode="json")
    payload["step_traceability"][0]["outcome_code_path"] = (
        "process_assessment.step_assessments[step_id=wrong].outcome_code"
    )

    with pytest.raises(ValidationError, match="Invalid successor trace path"):
        FourGateIntegratedAssessmentSuccess.model_validate(payload)


def test_successor_fingerprint_and_result_are_deterministic(
    successor_policy: FourGateDecisionPolicy,
) -> None:
    duplicate = FourGateDecisionPolicy.model_validate(
        successor_policy.model_dump(mode="json")
    )
    assert fingerprint_four_gate_policy(successor_policy) == (
        fingerprint_four_gate_policy(duplicate)
    )

    changed_payload = successor_policy.model_dump(mode="json")
    changed_payload["gates"]["minimum_business_value"] = 3
    changed = FourGateDecisionPolicy.model_validate(changed_payload)
    assert fingerprint_four_gate_policy(successor_policy) != (
        fingerprint_four_gate_policy(changed)
    )

    approved = approved_review()
    first = _service(successor_policy).assess(approved)
    second = _service(successor_policy).assess(approved)
    assert isinstance(first, FourGateIntegratedAssessmentSuccess)
    assert isinstance(second, FourGateIntegratedAssessmentSuccess)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")

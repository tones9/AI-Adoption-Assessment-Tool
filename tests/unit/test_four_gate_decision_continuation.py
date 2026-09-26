from __future__ import annotations

from ai_adoption_engine.application.four_gate_decision_continuation import (
    DecisionContinuationContractFamily,
    SuccessorContinuationState,
    discriminate_decision_continuation,
)
from ai_adoption_engine.workspace.models import ArtifactType
from tests.fakes.four_gate_workspace import (
    persisted_four_gate_baseline,
    persisted_four_gate_data_readiness_baseline,
)
from tests.fakes.m2_reassessment import package_ready_m2_baseline


def test_exact_legacy_and_successor_baselines_are_discriminated(tmp_path) -> None:
    legacy_repository, legacy_id = package_ready_m2_baseline(tmp_path / "legacy")
    successor_repository, successor_id, *_ = persisted_four_gate_baseline(
        tmp_path / "successor"
    )

    legacy = discriminate_decision_continuation(
        legacy_repository.load_workspace(legacy_id)
    )
    successor = discriminate_decision_continuation(
        successor_repository.load_workspace(successor_id)
    )

    assert legacy.contract_family is DecisionContinuationContractFamily.LEGACY
    assert legacy.legacy_continuation_available is True
    assert successor.contract_family is DecisionContinuationContractFamily.FOUR_GATE
    assert successor.continuation_state is SuccessorContinuationState.DEFERRED_UNAVAILABLE
    assert successor.legacy_continuation_available is False
    assert successor.successor_continuation_available is False


def test_exact_gate_two_data_readiness_baseline_activates_only_target_step(
    tmp_path,
) -> None:
    repository, assessment_id, _, package_result, _ = (
        persisted_four_gate_data_readiness_baseline(tmp_path)
    )

    view = discriminate_decision_continuation(repository.load_workspace(assessment_id))

    assert view.contract_family is DecisionContinuationContractFamily.FOUR_GATE
    assert view.continuation_state is SuccessorContinuationState.AVAILABLE
    assert view.successor_continuation_available is True
    assert view.legacy_continuation_available is False
    assert view.eligible_step_ids == (
        package_result.package.portfolio.items[0].step_id,
    )


def test_successor_view_preserves_identity_typed_decisions_and_four_gates(
    tmp_path,
) -> None:
    repository, assessment_id, integrated, package_result, package_ref = (
        persisted_four_gate_baseline(tmp_path)
    )

    view = discriminate_decision_continuation(repository.load_workspace(assessment_id))
    baseline = view.successor_baseline

    assert baseline is not None
    assert baseline.framework_id == "four-gate-framework.v0.1"
    assert baseline.phase1_contract_version == "phase1-v0.4"
    assert baseline.phase5_schema_version == "phase5-v0.2"
    assert baseline.phase6_schema_version == "phase6-v0.2"
    assert baseline.policy_id == "decision_policy.v0.3"
    assert baseline.policy_version == "0.3.0"
    assert baseline.policy_fingerprint == integrated.policy.decision_policy_fingerprint
    assert baseline.decision_package.artifact_id == package_ref.artifact_id
    assert baseline.package_id == package_result.package.package_id
    assert baseline.immutable is True
    assert len(baseline.decisions) == len(package_result.package.portfolio.items)
    for decision, item in zip(
        baseline.decisions, package_result.package.portfolio.items, strict=True
    ):
        assert decision.outcome_code == item.outcome_code.value
        assert decision.change_disposition == item.change_disposition.value
        assert decision.readiness_disposition == item.readiness_disposition.value
        assert (
            decision.selected_intervention_family
            == item.selected_intervention_family.value
        )
        assert decision.autonomy_ceiling == item.autonomy_ceiling.value
        assert len(decision.gates) == 4


def test_mixed_schema_and_inconsistent_policy_pin_fail_closed(tmp_path) -> None:
    repository, assessment_id, *_ = persisted_four_gate_baseline(tmp_path)
    snapshot = repository.load_workspace(assessment_id)
    package = snapshot.active_artifacts[ArtifactType.DECISION_PACKAGE_RESULT]
    mixed = snapshot.model_copy(
        update={
            "active_artifacts": {
                **snapshot.active_artifacts,
                ArtifactType.DECISION_PACKAGE_RESULT: package.model_copy(
                    update={"artifact_schema_version": "phase6-v0.1"}
                ),
            }
        }
    )
    wrong_pin = snapshot.model_copy(
        update={
            "assessment": snapshot.assessment.model_copy(
                update={
                    "contract_pin": snapshot.assessment.contract_pin.model_copy(
                        update={"decision_policy_fingerprint": "f" * 64}
                    )
                }
            )
        }
    )

    for invalid in (mixed, wrong_pin):
        view = discriminate_decision_continuation(invalid)
        assert view.contract_family is DecisionContinuationContractFamily.UNSUPPORTED
        assert view.legacy_continuation_available is False
        assert view.successor_continuation_available is False
        assert view.failure_message == (
            "The saved baseline contract could not be verified. "
            "No continuation action is available."
        )


def test_successor_baseline_with_legacy_grw_artifact_fails_closed(tmp_path) -> None:
    repository, assessment_id, *_ = persisted_four_gate_baseline(tmp_path)
    snapshot = repository.load_workspace(assessment_id)
    package = snapshot.active_artifacts[ArtifactType.DECISION_PACKAGE_RESULT]
    invalid = snapshot.model_copy(
        update={
            "active_artifacts": {
                **snapshot.active_artifacts,
                ArtifactType.GRW_EVIDENCE_SUBMISSION: package.model_copy(
                    update={"artifact_type": ArtifactType.GRW_EVIDENCE_SUBMISSION}
                ),
            }
        }
    )

    view = discriminate_decision_continuation(invalid)

    assert view.contract_family is DecisionContinuationContractFamily.UNSUPPORTED
    assert view.legacy_continuation_available is False

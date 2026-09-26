from pathlib import Path

import pytest

from ai_adoption_engine.decision.four_gate_gates import evaluate_four_gates
from ai_adoption_engine.decision.four_gate_policy import (
    FourGateDecisionPolicy,
    load_four_gate_policy,
)
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.four_gate_assessment import (
    AutonomyCeiling,
    CapabilitySignalName,
    DecisionStatus,
    FourGateName,
    FourGateStatus,
    ReadinessDisposition,
    SelectedInterventionFamily,
)
from ai_adoption_engine.models.process import (
    BusinessProcess,
    CapabilitySignalInput,
    ProcessStep,
)

POLICY_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "decision_policy.v0.3.json"
)


@pytest.fixture
def successor_policy() -> FourGateDecisionPolicy:
    return load_four_gate_policy(POLICY_PATH)


def _step(process: BusinessProcess, step_id: str = "S1") -> ProcessStep:
    return next(
        item.model_copy(deep=True) for item in process.steps if item.step_id == step_id
    )


def _unknown(item) -> None:
    item.value = None
    item.knowledge_state = KnowledgeState.UNKNOWN
    item.confidence = None


def _set_supported_signals(
    step: ProcessStep,
    *true_signals: CapabilitySignalName,
) -> None:
    true_set = set(true_signals)
    for signal_name in CapabilitySignalName:
        setattr(
            step.characteristics.capability_signals,
            signal_name.value,
            CapabilitySignalInput(
                value=signal_name in true_set,
                knowledge_state=KnowledgeState.KNOWN,
                rationale="Explicitly reviewed capability signal.",
                evidence_ids=["E1"],
            ),
        )


def test_missing_activity_evidence_stops_at_gate_one(
    process: BusinessProcess,
    successor_policy: FourGateDecisionPolicy,
) -> None:
    step = _step(process)
    step.evidence_ids = []

    result = evaluate_four_gates(step, successor_policy)

    assert result.decision_status is DecisionStatus.DISCOVERY_REQUIRED
    assert result.gate_results[0].status is FourGateStatus.BLOCKED_BY_EVIDENCE
    assert result.blocking_gaps[0].field_name == "activity"
    assert all(
        item.status is FourGateStatus.NOT_EVALUATED
        for item in result.gate_results[1:]
    )


@pytest.mark.parametrize(
    ("blocker", "unknown_peer"),
    [
        (CriterionName.DATA_READINESS, CriterionName.IMPLEMENTATION_COMPLEXITY),
        (CriterionName.IMPLEMENTATION_COMPLEXITY, CriterionName.DATA_READINESS),
    ],
)
def test_gate_two_known_blocker_wins_over_unrelated_unknowns(
    process: BusinessProcess,
    successor_policy: FourGateDecisionPolicy,
    blocker: CriterionName,
    unknown_peer: CriterionName,
) -> None:
    step = _step(process)
    step.characteristics.criterion(blocker).value = (
        1 if blocker is CriterionName.DATA_READINESS else 5
    )
    _unknown(step.characteristics.criterion(unknown_peer))
    _unknown(step.characteristics.repetition)
    _unknown(step.characteristics.predictability)
    _unknown(step.characteristics.ai_capability_fit)

    result = evaluate_four_gates(step, successor_policy)

    assert result.decision_status is DecisionStatus.COMPLETE
    assert (
        result.readiness_disposition
        is ReadinessDisposition.PROCESS_IMPROVEMENT_FIRST
    )
    assert len(result.gate_results) == 4
    assert result.gate_results[1].material_criteria == [blocker]
    assert unknown_peer in result.gate_results[1].context_criteria
    assert all(
        item.status is FourGateStatus.NOT_EVALUATED
        for item in result.gate_results[2:]
    )


def test_unsupported_low_readiness_requires_discovery_not_process_improvement(
    process: BusinessProcess,
    successor_policy: FourGateDecisionPolicy,
) -> None:
    step = _step(process)
    step.characteristics.data_readiness.value = 1
    step.characteristics.data_readiness.evidence_ids = []

    result = evaluate_four_gates(step, successor_policy)

    assert result.decision_status is DecisionStatus.DISCOVERY_REQUIRED
    assert result.readiness_disposition is ReadinessDisposition.NOT_DETERMINED
    assert result.gate_results[1].status is FourGateStatus.BLOCKED_BY_EVIDENCE


def test_gate_two_context_never_blocks_a_ready_conventional_path(
    process: BusinessProcess,
    successor_policy: FourGateDecisionPolicy,
) -> None:
    step = _step(process, "S2")
    _unknown(step.characteristics.repetition)
    _unknown(step.characteristics.predictability)
    _unknown(step.characteristics.ai_capability_fit)

    result = evaluate_four_gates(step, successor_policy)

    assert result.selected_intervention_family is (
        SelectedInterventionFamily.CONVENTIONAL_AUTOMATION
    )
    assert result.decision_status is DecisionStatus.COMPLETE
    assert result.blocking_gaps == []


def test_conventional_solution_precedes_ai_fit_and_workflow_signal(
    process: BusinessProcess,
    successor_policy: FourGateDecisionPolicy,
) -> None:
    step = _step(process, "S2")
    _unknown(step.characteristics.ai_capability_fit)
    _set_supported_signals(
        step,
        CapabilitySignalName.ROUTES_OR_ORCHESTRATES_WORK,
    )

    result = evaluate_four_gates(step, successor_policy)

    assert result.selected_intervention_family is (
        SelectedInterventionFamily.CONVENTIONAL_AUTOMATION
    )
    assert result.gate_results[2].material_criteria == [
        CriterionName.CONVENTIONAL_SOLUTION_FIT
    ]


def test_ai_fit_requires_deterministic_provenance_supported_capability(
    process: BusinessProcess,
    successor_policy: FourGateDecisionPolicy,
) -> None:
    unresolved = _step(process)
    unresolved_result = evaluate_four_gates(unresolved, successor_policy)
    assert unresolved_result.decision_status is DecisionStatus.DISCOVERY_REQUIRED
    assert unresolved_result.blocking_gaps[0].field_name == "capability_signals"

    all_false = _step(process)
    _set_supported_signals(all_false)
    all_false_result = evaluate_four_gates(all_false, successor_policy)
    assert all_false_result.selected_intervention_family is (
        SelectedInterventionFamily.KEEP_HUMAN_LED
    )

    supported = _step(process)
    _set_supported_signals(
        supported,
        CapabilitySignalName.READS_UNSTRUCTURED_DOCUMENTS,
    )
    supported_result = evaluate_four_gates(supported, successor_policy)
    assert supported_result.selected_intervention_family is SelectedInterventionFamily.AI
    assert supported_result.gate_results[2].material_capability_signals == [
        CapabilitySignalName.READS_UNSTRUCTURED_DOCUMENTS
    ]


def test_low_ai_fit_selects_human_led_without_capability_evidence(
    process: BusinessProcess,
    successor_policy: FourGateDecisionPolicy,
) -> None:
    step = _step(process)
    step.characteristics.ai_capability_fit.value = 2

    result = evaluate_four_gates(step, successor_policy)

    assert result.decision_status is DecisionStatus.COMPLETE
    assert result.selected_intervention_family is (
        SelectedInterventionFamily.KEEP_HUMAN_LED
    )
    assert result.gate_results[2].material_capability_signals == []


def test_gate_four_safety_veto_rejects_ai_without_unrelated_evidence(
    process: BusinessProcess,
    successor_policy: FourGateDecisionPolicy,
) -> None:
    step = _step(process)
    _set_supported_signals(
        step,
        CapabilitySignalName.READS_UNSTRUCTURED_DOCUMENTS,
    )
    step.characteristics.residual_risk_with_human_oversight.value = 4
    _unknown(step.characteristics.human_judgement_requirement)
    _unknown(step.characteristics.risk_consequence)
    _unknown(step.characteristics.human_accountability_required)
    _unknown(step.characteristics.predictability)

    result = evaluate_four_gates(step, successor_policy)

    assert result.selected_intervention_family is SelectedInterventionFamily.AI
    assert result.autonomy_ceiling is AutonomyCeiling.AI_NOT_PERMITTED
    assert result.decision_status is DecisionStatus.COMPLETE
    assert "sole final outcome" in result.gate_results[3].rationale
    assert result.blocking_gaps == []


def test_one_assistance_constraint_wins_over_missing_peer_inputs(
    process: BusinessProcess,
    successor_policy: FourGateDecisionPolicy,
) -> None:
    step = _step(process)
    _set_supported_signals(
        step,
        CapabilitySignalName.READS_UNSTRUCTURED_DOCUMENTS,
    )
    step.characteristics.human_judgement_requirement.value = 3
    _unknown(step.characteristics.risk_consequence)
    _unknown(step.characteristics.human_accountability_required)
    _unknown(step.characteristics.predictability)

    result = evaluate_four_gates(step, successor_policy)

    assert result.autonomy_ceiling is AutonomyCeiling.AI_ASSISTED
    assert result.decision_status is DecisionStatus.COMPLETE
    assert CriterionName.PREDICTABILITY not in result.gate_results[3].material_criteria


def test_missing_peer_blocks_only_when_no_assistance_constraint_is_known(
    process: BusinessProcess,
    successor_policy: FourGateDecisionPolicy,
) -> None:
    step = _step(process)
    _set_supported_signals(
        step,
        CapabilitySignalName.READS_UNSTRUCTURED_DOCUMENTS,
    )
    _unknown(step.characteristics.human_judgement_requirement)

    result = evaluate_four_gates(step, successor_policy)

    assert result.decision_status is DecisionStatus.DISCOVERY_REQUIRED
    assert result.gate_results[3].status is FourGateStatus.BLOCKED_BY_EVIDENCE
    assert result.blocking_gaps[0].field_name == "human_judgement_requirement"


def test_predictability_becomes_material_only_if_automation_remains_possible(
    process: BusinessProcess,
    successor_policy: FourGateDecisionPolicy,
) -> None:
    strict_failure = _step(process)
    _set_supported_signals(
        strict_failure,
        CapabilitySignalName.READS_UNSTRUCTURED_DOCUMENTS,
    )
    strict_failure.characteristics.data_readiness.value = 3
    _unknown(strict_failure.characteristics.predictability)
    assisted = evaluate_four_gates(strict_failure, successor_policy)
    assert assisted.autonomy_ceiling is AutonomyCeiling.AI_ASSISTED
    assert CriterionName.PREDICTABILITY not in assisted.gate_results[3].material_criteria

    still_open = _step(process)
    _set_supported_signals(
        still_open,
        CapabilitySignalName.READS_UNSTRUCTURED_DOCUMENTS,
    )
    _unknown(still_open.characteristics.predictability)
    discovery = evaluate_four_gates(still_open, successor_policy)
    assert discovery.decision_status is DecisionStatus.DISCOVERY_REQUIRED
    assert discovery.blocking_gaps[0].gate is FourGateName.SAFE_AUTONOMY

    known_low = _step(process)
    _set_supported_signals(
        known_low,
        CapabilitySignalName.READS_UNSTRUCTURED_DOCUMENTS,
    )
    known_low.characteristics.predictability.value = 3
    assisted_by_predictability = evaluate_four_gates(known_low, successor_policy)
    assert assisted_by_predictability.autonomy_ceiling is AutonomyCeiling.AI_ASSISTED
    assert (
        CriterionName.PREDICTABILITY
        in assisted_by_predictability.gate_results[3].material_criteria
    )

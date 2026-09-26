from pathlib import Path
from typing import Callable

import pytest
from pydantic import ValidationError

from ai_adoption_engine.decision.four_gate_engine import (
    FourGateAssessmentEngine,
    assess_four_gate,
)
from ai_adoption_engine.decision.four_gate_policy import (
    FourGateDecisionPolicy,
    load_four_gate_policy,
)
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.four_gate_assessment import (
    CLOSED_OUTCOME_COMBINATIONS,
    AutonomyCeiling,
    CapabilitySignalName,
    ChangeDisposition,
    DecisionStatus,
    FourGateName,
    FourGatePriorityStatus,
    FourGateStepAssessment,
    GateDecisionCode,
    OutcomeCode,
    ReadinessDisposition,
    SelectedInterventionFamily,
    derive_outcome,
)
from ai_adoption_engine.models.process import (
    BusinessProcess,
    CapabilitySignalInput,
    ProcessStep,
)

POLICY_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "decision_policy.v0.3.json"
)
Mutator = Callable[[ProcessStep], None]


@pytest.fixture
def successor_policy() -> FourGateDecisionPolicy:
    return load_four_gate_policy(POLICY_PATH)


def _unknown(item) -> None:
    item.value = None
    item.knowledge_state = KnowledgeState.UNKNOWN
    item.confidence = None


def _single_step(process: BusinessProcess) -> BusinessProcess:
    result = process.model_copy(deep=True)
    result.steps = [result.steps[0]]
    step = result.steps[0]
    for signal_name in CapabilitySignalName:
        setattr(
            step.characteristics.capability_signals,
            signal_name.value,
            CapabilitySignalInput(
                value=(
                    signal_name is CapabilitySignalName.READS_UNSTRUCTURED_DOCUMENTS
                ),
                knowledge_state=KnowledgeState.KNOWN,
                rationale="Explicitly reviewed capability signal.",
                evidence_ids=["E1"],
            ),
        )
    return result


def _result_for(
    process: BusinessProcess,
    policy: FourGateDecisionPolicy,
    mutator: Mutator,
) -> FourGateStepAssessment:
    candidate = _single_step(process)
    mutator(candidate.steps[0])
    return assess_four_gate(candidate, policy).step_assessments[0]


def _noop(step: ProcessStep) -> None:
    del step


def test_engine_emits_every_closed_combination_and_all_seven_outcomes(
    process: BusinessProcess,
    successor_policy: FourGateDecisionPolicy,
) -> None:
    def gate_one_discovery(step: ProcessStep) -> None:
        _unknown(step.characteristics.business_value)

    def no_change(step: ProcessStep) -> None:
        step.characteristics.business_value.value = 1

    def gate_two_discovery(step: ProcessStep) -> None:
        _unknown(step.characteristics.data_readiness)

    def process_first(step: ProcessStep) -> None:
        step.characteristics.data_readiness.value = 1

    def gate_three_discovery(step: ProcessStep) -> None:
        _unknown(step.characteristics.conventional_solution_fit)

    def conventional(step: ProcessStep) -> None:
        step.characteristics.conventional_solution_fit.value = 4

    def human_led(step: ProcessStep) -> None:
        step.characteristics.ai_capability_fit.value = 2

    def gate_four_discovery(step: ProcessStep) -> None:
        _unknown(step.characteristics.residual_risk_with_human_oversight)

    def safety_veto(step: ProcessStep) -> None:
        step.characteristics.residual_risk_with_human_oversight.value = 4

    def assisted(step: ProcessStep) -> None:
        step.characteristics.human_judgement_requirement.value = 3

    scenarios = [
        gate_one_discovery,
        no_change,
        gate_two_discovery,
        process_first,
        gate_three_discovery,
        conventional,
        human_led,
        gate_four_discovery,
        safety_veto,
        assisted,
        _noop,
    ]

    results = [
        _result_for(process, successor_policy, mutator) for mutator in scenarios
    ]
    combinations = {
        (
            result.decision_status,
            result.change_disposition,
            result.readiness_disposition,
            result.selected_intervention_family,
            result.autonomy_ceiling,
        )
        for result in results
    }

    assert combinations == set(CLOSED_OUTCOME_COMBINATIONS)
    assert {result.outcome_code for result in results} == set(OutcomeCode)
    for result in results:
        assert [item.gate for item in result.gate_results] == list(FourGateName)


def test_outcome_is_derived_only_and_invalid_combinations_fail(
    process: BusinessProcess,
    successor_policy: FourGateDecisionPolicy,
) -> None:
    result = _result_for(process, successor_policy, _noop)
    payload = result.model_dump(mode="json")
    assert FourGateStepAssessment.model_validate(payload).outcome_code is (
        OutcomeCode.AI_AUTOMATION
    )
    payload["outcome_code"] = OutcomeCode.KEEP_HUMAN_LED.value
    with pytest.raises(ValidationError, match="derived four-gate outcome"):
        FourGateStepAssessment.model_validate(payload)

    with pytest.raises(ValueError, match="Invalid four-gate output-field combination"):
        derive_outcome(
            DecisionStatus.COMPLETE,
            ChangeDisposition.CHANGE_JUSTIFIED,
            ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
            SelectedInterventionFamily.CONVENTIONAL_AUTOMATION,
            AutonomyCeiling.AI_AUTOMATION,
        )

    def gate_two_discovery(step: ProcessStep) -> None:
        _unknown(step.characteristics.data_readiness)

    mismatched_path = _result_for(
        process,
        successor_policy,
        gate_two_discovery,
    ).model_dump(mode="json")
    mismatched_path.update(
        {
            "change_disposition": ChangeDisposition.NOT_DETERMINED.value,
            "readiness_disposition": ReadinessDisposition.NOT_EVALUATED.value,
        }
    )
    with pytest.raises(ValidationError, match="deciding gate does not match"):
        FourGateStepAssessment.model_validate(mismatched_path)


@pytest.mark.parametrize(
    ("gate_index", "wrong_code"),
    [
        (0, GateDecisionCode.READY_FOR_INTERVENTION_SELECTION),
        (1, GateDecisionCode.AI_SELECTED),
        (2, GateDecisionCode.AI_ASSISTED_REQUIRED),
        (3, GateDecisionCode.CHANGE_JUSTIFIED),
    ],
)
def test_each_evaluated_gate_rejects_another_gates_valid_decision_code(
    process: BusinessProcess,
    successor_policy: FourGateDecisionPolicy,
    gate_index: int,
    wrong_code: GateDecisionCode,
) -> None:
    payload = _result_for(process, successor_policy, _noop).model_dump(mode="json")
    payload["gate_results"][gate_index]["decision_code"] = wrong_code.value

    with pytest.raises(ValidationError, match="cannot use decision code"):
        FourGateStepAssessment.model_validate(payload)


@pytest.mark.parametrize(
    ("gate_index", "wrong_code"),
    [
        (0, GateDecisionCode.NO_CHANGE_JUSTIFIED),
        (3, GateDecisionCode.AI_ASSISTED_REQUIRED),
    ],
)
def test_gate_codes_must_agree_with_the_final_typed_path(
    process: BusinessProcess,
    successor_policy: FourGateDecisionPolicy,
    gate_index: int,
    wrong_code: GateDecisionCode,
) -> None:
    payload = _result_for(process, successor_policy, _noop).model_dump(mode="json")
    payload["gate_results"][gate_index]["decision_code"] = wrong_code.value

    with pytest.raises(
        ValidationError,
        match="do not agree with the typed output path",
    ):
        FourGateStepAssessment.model_validate(payload)


def test_discovery_and_not_evaluated_decision_codes_remain_strict(
    process: BusinessProcess,
    successor_policy: FourGateDecisionPolicy,
) -> None:
    def gate_two_discovery(step: ProcessStep) -> None:
        _unknown(step.characteristics.data_readiness)

    discovery_payload = _result_for(
        process,
        successor_policy,
        gate_two_discovery,
    ).model_dump(mode="json")
    discovery_payload["gate_results"][1]["decision_code"] = (
        GateDecisionCode.READY_FOR_INTERVENTION_SELECTION.value
    )
    with pytest.raises(ValidationError, match="evidence-blocked gate"):
        FourGateStepAssessment.model_validate(discovery_payload)

    not_evaluated_payload = _result_for(
        process,
        successor_policy,
        lambda step: setattr(step.characteristics.business_value, "value", 1),
    ).model_dump(mode="json")
    not_evaluated_payload["gate_results"][1]["decision_code"] = (
        GateDecisionCode.DISCOVERY_REQUIRED.value
    )
    with pytest.raises(ValidationError, match="not-evaluated gate"):
        FourGateStepAssessment.model_validate(not_evaluated_payload)


def test_explicit_engine_identity_provenance_and_deterministic_bytes(
    process: BusinessProcess,
    successor_policy: FourGateDecisionPolicy,
) -> None:
    candidate = _single_step(process)
    engine = FourGateAssessmentEngine(successor_policy)

    first = engine.assess(candidate)
    second = engine.assess(candidate)

    assert first.framework_id == "four-gate-framework.v0.1"
    assert first.decision_contract_version == "phase1-v0.4"
    assert first.policy_id == "decision_policy.v0.3"
    assert first.canonical_json_bytes() == second.canonical_json_bytes()
    step = first.step_assessments[0]
    assert [item.criterion for item in step.criteria] == list(CriterionName)
    assert [item.signal for item in step.capability_signals] == list(
        CapabilitySignalName
    )
    assert {item.evidence_id for item in step.evidence} >= {"E1", "E2", "E3"}
    signal = step.capability_signals[0]
    assert signal.value is True
    assert signal.knowledge_state is KnowledgeState.KNOWN
    assert signal.rationale == "Explicitly reviewed capability signal."
    assert signal.evidence_ids == ["E1"]
    assert signal.material_to_decision is True


def test_gate_four_uses_gate_two_data_readiness_without_reattributing_it(
    process: BusinessProcess,
    successor_policy: FourGateDecisionPolicy,
) -> None:
    def data_constrains_automation(step: ProcessStep) -> None:
        step.characteristics.data_readiness.value = 3

    result = _result_for(process, successor_policy, data_constrains_automation)
    data_readiness = next(
        item
        for item in result.criteria
        if item.criterion is CriterionName.DATA_READINESS
    )
    gate_four = result.gate_results[3]

    assert result.outcome_code is OutcomeCode.AI_ASSISTED_WORK
    assert data_readiness.material_at_gates == [FourGateName.IS_IT_READY]
    assert FourGateName.SAFE_AUTONOMY not in data_readiness.material_at_gates
    assert CriterionName.DATA_READINESS not in gate_four.material_criteria
    assert "E3" not in gate_four.evidence_ids
    assert "validated Gate 2 data-readiness finding" in gate_four.rationale


def test_aggregate_evidence_contains_only_reached_path_decision_evidence(
    process: BusinessProcess,
    successor_policy: FourGateDecisionPolicy,
) -> None:
    candidate = _single_step(process)
    step = candidate.steps[0]
    evidence_template = candidate.evidence[0]

    evidence_ids = {
        "context": "E_CONTEXT_PRIORITY_ONLY",
        "accountability": "E_ACCOUNTABILITY_MATERIAL",
        "material_signal": "E_SIGNAL_MATERIAL",
        "context_signal": "E_SIGNAL_CONTEXT_ONLY",
    }
    candidate.evidence.extend(
        evidence_template.model_copy(
            update={
                "evidence_id": evidence_id,
                "source_locator": f"Corrective test — {label}",
                "supporting_snippet": f"Distinct {label} evidence.",
            }
        )
        for label, evidence_id in evidence_ids.items()
    )
    step.characteristics.repetition.evidence_ids = [evidence_ids["context"]]
    step.characteristics.human_accountability_required.evidence_ids = [
        evidence_ids["accountability"]
    ]
    material_signal = (
        step.characteristics.capability_signals.reads_unstructured_documents
    )
    material_signal.evidence_ids = [evidence_ids["material_signal"]]
    step.characteristics.capability_signals.categorises_items.evidence_ids = [
        evidence_ids["context_signal"]
    ]

    result = assess_four_gate(candidate, successor_policy).step_assessments[0]
    aggregate_ids = {item.evidence_id for item in result.evidence}

    assert evidence_ids["accountability"] in aggregate_ids
    assert evidence_ids["material_signal"] in aggregate_ids
    assert evidence_ids["context"] not in aggregate_ids
    assert evidence_ids["context_signal"] not in aggregate_ids

    repetition = next(
        item for item in result.criteria if item.criterion is CriterionName.REPETITION
    )
    assert repetition.material_to_priority is True
    assert repetition.evidence_ids == [evidence_ids["context"]]
    context_signal = next(
        item
        for item in result.capability_signals
        if item.signal is CapabilitySignalName.CATEGORISES_ITEMS
    )
    assert context_signal.material_to_decision is False
    assert context_signal.evidence_ids == [evidence_ids["context_signal"]]


def test_priority_has_complete_incomplete_and_not_applicable_states(
    process: BusinessProcess,
    successor_policy: FourGateDecisionPolicy,
) -> None:
    complete = _result_for(process, successor_policy, _noop)
    assert complete.outcome_code is OutcomeCode.AI_AUTOMATION
    assert complete.priority_status is FourGatePriorityStatus.COMPLETE
    assert complete.priority is not None
    assert CriterionName.IMPLEMENTATION_COMPLEXITY in {
        item.criterion for item in complete.priority.components
    }

    def missing_repetition(step: ProcessStep) -> None:
        _unknown(step.characteristics.repetition)

    incomplete = _result_for(process, successor_policy, missing_repetition)
    assert incomplete.outcome_code is OutcomeCode.AI_AUTOMATION
    assert incomplete.priority_status is FourGatePriorityStatus.INCOMPLETE
    assert incomplete.priority is None
    assert incomplete.priority_missing_criteria == [CriterionName.REPETITION]

    def conventional(step: ProcessStep) -> None:
        step.characteristics.conventional_solution_fit.value = 4

    not_applicable = _result_for(process, successor_policy, conventional)
    assert not_applicable.priority_status is FourGatePriorityStatus.NOT_APPLICABLE
    assert not_applicable.priority is None
    assert not_applicable.priority_missing_criteria == []

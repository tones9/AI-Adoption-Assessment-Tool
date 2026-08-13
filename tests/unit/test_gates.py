from ai_adoption_engine.decision.capabilities import map_capabilities
from ai_adoption_engine.decision.gates import evaluate_gates
from ai_adoption_engine.decision.policy import DecisionPolicy
from ai_adoption_engine.models.enums import CriterionName, GateStatus, RecommendationMode
from ai_adoption_engine.models.process import BusinessProcess


def _step(process: BusinessProcess, step_id: str):
    return next(item.model_copy(deep=True) for item in process.steps if item.step_id == step_id)


def test_unknown_required_criterion_investigates(
    process: BusinessProcess, policy: DecisionPolicy
) -> None:
    step = _step(process, "S4")
    result = evaluate_gates(
        step,
        map_capabilities(step.characteristics.capability_signals),
        policy,
    )
    assert result.recommendation is RecommendationMode.INVESTIGATE_FURTHER
    assert result.results[0].status is GateStatus.PASSED
    assert result.results[1].status is GateStatus.FAILED
    assert all(item.status is GateStatus.NOT_EVALUATED for item in result.results[2:])


def test_low_ai_fit_does_not_recommend(
    process: BusinessProcess, policy: DecisionPolicy
) -> None:
    step = _step(process, "S1")
    step.characteristics.ai_capability_fit.value = 2
    result = evaluate_gates(
        step,
        map_capabilities(step.characteristics.capability_signals),
        policy,
    )
    assert result.recommendation is RecommendationMode.DO_NOT_RECOMMEND
    assert "minimum fit" in result.results[1].rationale


def test_low_business_value_does_not_recommend(
    process: BusinessProcess, policy: DecisionPolicy
) -> None:
    step = _step(process, "S1")
    step.characteristics.business_value.value = 1
    result = evaluate_gates(
        step,
        map_capabilities(step.characteristics.capability_signals),
        policy,
    )
    assert result.recommendation is RecommendationMode.DO_NOT_RECOMMEND
    assert "Conventional process improvement" in result.results[2].rationale


def test_known_low_data_readiness_investigates(
    process: BusinessProcess, policy: DecisionPolicy
) -> None:
    step = _step(process, "S1")
    step.characteristics.data_readiness.value = 1
    result = evaluate_gates(
        step,
        map_capabilities(step.characteristics.capability_signals),
        policy,
    )
    assert result.recommendation is RecommendationMode.INVESTIGATE_FURTHER


def test_conventional_solution_prevents_manufactured_ai_use_case(
    process: BusinessProcess, policy: DecisionPolicy
) -> None:
    step = _step(process, "S2")
    result = evaluate_gates(
        step,
        map_capabilities(step.characteristics.capability_signals),
        policy,
    )
    assert result.recommendation is RecommendationMode.DO_NOT_RECOMMEND
    assert "preferable" in result.results[1].rationale


def test_human_judgement_requires_augmentation(
    process: BusinessProcess, policy: DecisionPolicy
) -> None:
    step = _step(process, "S3")
    result = evaluate_gates(
        step,
        map_capabilities(step.characteristics.capability_signals),
        policy,
    )
    assert result.recommendation is RecommendationMode.AUGMENT
    assert result.results[-1].status is GateStatus.PASSED_WITH_CONSTRAINTS


def test_unacceptable_residual_risk_does_not_recommend(
    process: BusinessProcess, policy: DecisionPolicy
) -> None:
    step = _step(process, "S5")
    result = evaluate_gates(
        step,
        map_capabilities(step.characteristics.capability_signals),
        policy,
    )
    assert result.recommendation is RecommendationMode.DO_NOT_RECOMMEND
    assert result.results[-1].status is GateStatus.FAILED


def test_low_risk_structured_step_can_automate(
    process: BusinessProcess, policy: DecisionPolicy
) -> None:
    step = _step(process, "S1")
    result = evaluate_gates(
        step,
        map_capabilities(step.characteristics.capability_signals),
        policy,
    )
    assert result.recommendation is RecommendationMode.AUTOMATE
    assert result.results[-1].status is GateStatus.PASSED


def test_unknown_nonmaterial_conventional_fit_does_not_block_augmentation(
    process: BusinessProcess, policy: DecisionPolicy
) -> None:
    step = _step(process, "S3")
    step.characteristics.conventional_solution_fit.value = None
    step.characteristics.conventional_solution_fit.knowledge_state = "unknown"
    result = evaluate_gates(
        step,
        map_capabilities(step.characteristics.capability_signals),
        policy,
    )
    assert result.recommendation is RecommendationMode.AUGMENT


def test_unknown_conventional_fit_blocks_when_workflow_automation_makes_it_material(
    process: BusinessProcess, policy: DecisionPolicy
) -> None:
    step = _step(process, "S2")
    step.characteristics.conventional_solution_fit.value = None
    step.characteristics.conventional_solution_fit.knowledge_state = "unknown"
    result = evaluate_gates(
        step,
        map_capabilities(step.characteristics.capability_signals),
        policy,
    )
    assert result.recommendation is RecommendationMode.INVESTIGATE_FURTHER
    assert "conventional_solution_fit is unknown" in result.results[1].rationale


def test_unknown_predictability_does_not_block_already_constrained_augmentation(
    process: BusinessProcess, policy: DecisionPolicy
) -> None:
    step = _step(process, "S3")
    step.characteristics.predictability.value = None
    step.characteristics.predictability.knowledge_state = "unknown"
    result = evaluate_gates(
        step,
        map_capabilities(step.characteristics.capability_signals),
        policy,
    )
    assert result.recommendation is RecommendationMode.AUGMENT
    assert CriterionName.PREDICTABILITY not in result.results[-1].material_criteria


def test_unknown_predictability_blocks_autonomy_decision_when_automation_is_possible(
    process: BusinessProcess, policy: DecisionPolicy
) -> None:
    step = _step(process, "S1")
    step.characteristics.predictability.value = None
    step.characteristics.predictability.knowledge_state = "unknown"
    result = evaluate_gates(
        step,
        map_capabilities(step.characteristics.capability_signals),
        policy,
    )
    assert result.recommendation is RecommendationMode.INVESTIGATE_FURTHER
    assert "predictability is unknown" in result.results[-1].rationale


def test_unknown_accountability_blocks_risk_decision(
    process: BusinessProcess, policy: DecisionPolicy
) -> None:
    step = _step(process, "S3")
    step.characteristics.human_accountability_required.value = None
    step.characteristics.human_accountability_required.knowledge_state = "unknown"
    result = evaluate_gates(
        step,
        map_capabilities(step.characteristics.capability_signals),
        policy,
    )
    assert result.recommendation is RecommendationMode.INVESTIGATE_FURTHER
    assert "human_accountability_required is unknown" in result.results[-1].rationale

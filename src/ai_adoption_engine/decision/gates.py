"""Ordered, gate-material decision rules for provisional policy v0.2."""

from dataclasses import dataclass

from ai_adoption_engine.decision.policy import DecisionPolicy
from ai_adoption_engine.models.assessment import GateResult
from ai_adoption_engine.models.enums import (
    Capability,
    CriterionName,
    GateName,
    GateStatus,
    KnowledgeState,
    RecommendationMode,
)
from ai_adoption_engine.models.evidence import BooleanCriterionInput, CriterionInput
from ai_adoption_engine.models.process import ProcessStep


@dataclass(frozen=True)
class GateEvaluation:
    recommendation: RecommendationMode
    results: list[GateResult]


_GATE_ORDER = (
    GateName.EVIDENCE_SUFFICIENCY,
    GateName.TECHNICAL_FIT,
    GateName.BUSINESS_VALUE,
    GateName.RISK_AND_AUTONOMY,
)


def _evidence_ids(step: ProcessStep, criteria: list[CriterionName]) -> list[str]:
    ids: set[str] = set()
    for criterion in criteria:
        ids.update(step.characteristics.criterion(criterion).evidence_ids)
    return sorted(ids)


def _not_evaluated(after: GateName) -> list[GateResult]:
    index = _GATE_ORDER.index(after)
    return [
        GateResult(
            gate=gate,
            status=GateStatus.NOT_EVALUATED,
            rationale="Not evaluated because an earlier gate determined the outcome.",
        )
        for gate in _GATE_ORDER[index + 1 :]
    ]


def _input_problem(
    name: str,
    item: CriterionInput | BooleanCriterionInput,
    policy: DecisionPolicy,
) -> str | None:
    if item.knowledge_state is KnowledgeState.UNKNOWN or item.value is None:
        return f"{name} is unknown"
    if (
        item.knowledge_state is KnowledgeState.INFERRED
        and (
            item.confidence is None
            or item.confidence < policy.evidence.minimum_inferred_confidence
        )
    ):
        return (
            f"{name} confidence is below "
            f"{policy.evidence.minimum_inferred_confidence:.2f}"
        )
    if (
        policy.evidence.require_material_criterion_evidence_reference
        and not item.evidence_ids
    ):
        return f"{name} has no evidence reference"
    return None


def _material_problem(
    step: ProcessStep,
    criteria: list[CriterionName],
    policy: DecisionPolicy,
    *,
    include_accountability: bool = False,
) -> list[str]:
    problems = [
        problem
        for name in criteria
        if (
            problem := _input_problem(
                name.value,
                step.characteristics.criterion(name),
                policy,
            )
        )
    ]
    if include_accountability:
        problem = _input_problem(
            "human_accountability_required",
            step.characteristics.human_accountability_required,
            policy,
        )
        if problem:
            problems.append(problem)
    return problems


def _insufficient_result(
    gate: GateName,
    problems: list[str],
    step: ProcessStep,
    criteria: list[CriterionName],
    *,
    accountability_material: bool = False,
) -> GateResult:
    evidence_ids = set(_evidence_ids(step, criteria))
    if accountability_material:
        evidence_ids.update(step.characteristics.human_accountability_required.evidence_ids)
    return GateResult(
        gate=gate,
        status=GateStatus.FAILED,
        rationale="Material evidence is insufficient: " + "; ".join(problems) + ".",
        evidence_ids=sorted(evidence_ids),
        material_criteria=criteria,
        accountability_material=accountability_material,
    )


def evaluate_gates(
    step: ProcessStep,
    capabilities: list[Capability],
    policy: DecisionPolicy,
) -> GateEvaluation:
    characteristics = step.characteristics
    results: list[GateResult] = []

    if policy.evidence.require_step_evidence_reference and not step.evidence_ids:
        results.append(
            GateResult(
                gate=GateName.EVIDENCE_SUFFICIENCY,
                status=GateStatus.FAILED,
                rationale="The activity itself has no source evidence reference.",
            )
        )
        results.extend(_not_evaluated(GateName.EVIDENCE_SUFFICIENCY))
        return GateEvaluation(RecommendationMode.INVESTIGATE_FURTHER, results)

    results.append(
        GateResult(
            gate=GateName.EVIDENCE_SUFFICIENCY,
            status=GateStatus.PASSED,
            rationale=(
                "The activity is source-backed. Criterion sufficiency is evaluated only "
                "when a criterion becomes material to the current gate."
            ),
            evidence_ids=sorted(step.evidence_ids),
        )
    )

    technical_material = [CriterionName.AI_CAPABILITY_FIT]
    problems = _material_problem(step, technical_material, policy)
    if problems:
        results.append(
            _insufficient_result(
                GateName.TECHNICAL_FIT,
                problems,
                step,
                technical_material,
            )
        )
        results.extend(_not_evaluated(GateName.TECHNICAL_FIT))
        return GateEvaluation(RecommendationMode.INVESTIGATE_FURTHER, results)

    ai_fit = characteristics.ai_capability_fit.value
    assert ai_fit is not None
    if not capabilities or ai_fit < policy.gates.minimum_ai_capability_fit:
        results.append(
            GateResult(
                gate=GateName.TECHNICAL_FIT,
                status=GateStatus.FAILED,
                rationale=(
                    f"AI capability fit is {ai_fit}/5 and the mapped capabilities are "
                    f"{[item.value for item in capabilities]}; the provisional minimum "
                    f"fit is {policy.gates.minimum_ai_capability_fit}/5."
                ),
                evidence_ids=_evidence_ids(step, technical_material),
                material_criteria=technical_material,
            )
        )
        results.extend(_not_evaluated(GateName.TECHNICAL_FIT))
        return GateEvaluation(RecommendationMode.DO_NOT_RECOMMEND, results)

    conventional = characteristics.conventional_solution_fit
    predictability = characteristics.predictability
    deterministic_signal = Capability.WORKFLOW_AUTOMATION in capabilities or (
        predictability.value is not None
        and predictability.knowledge_state is not KnowledgeState.UNKNOWN
        and predictability.value >= policy.gates.automate_minimum_predictability
    )
    conventional_decisive = (
        conventional.value is not None
        and conventional.value >= policy.gates.conventional_solution_fit_cutoff
    )
    conventional_material = deterministic_signal or conventional_decisive
    if conventional_material:
        technical_material.append(CriterionName.CONVENTIONAL_SOLUTION_FIT)
        problems = _material_problem(
            step,
            [CriterionName.CONVENTIONAL_SOLUTION_FIT],
            policy,
        )
        if problems:
            results.append(
                _insufficient_result(
                    GateName.TECHNICAL_FIT,
                    problems,
                    step,
                    technical_material,
                )
            )
            results.extend(_not_evaluated(GateName.TECHNICAL_FIT))
            return GateEvaluation(RecommendationMode.INVESTIGATE_FURTHER, results)
        assert conventional.value is not None
        if conventional.value >= policy.gates.conventional_solution_fit_cutoff:
            results.append(
                GateResult(
                    gate=GateName.TECHNICAL_FIT,
                    status=GateStatus.FAILED,
                    rationale=(
                        f"Conventional-solution fit is {conventional.value}/5, meeting the "
                        f"{policy.gates.conventional_solution_fit_cutoff}/5 cutoff. "
                        "Conventional software, rules-based automation, or process redesign "
                        "is preferable to manufacturing an AI use case."
                    ),
                    evidence_ids=_evidence_ids(step, technical_material),
                    material_criteria=technical_material,
                )
            )
            results.extend(_not_evaluated(GateName.TECHNICAL_FIT))
            return GateEvaluation(RecommendationMode.DO_NOT_RECOMMEND, results)

    technical_material.append(CriterionName.DATA_READINESS)
    problems = _material_problem(
        step,
        [CriterionName.DATA_READINESS],
        policy,
    )
    if problems:
        results.append(
            _insufficient_result(
                GateName.TECHNICAL_FIT,
                problems,
                step,
                technical_material,
            )
        )
        results.extend(_not_evaluated(GateName.TECHNICAL_FIT))
        return GateEvaluation(RecommendationMode.INVESTIGATE_FURTHER, results)

    data_readiness = characteristics.data_readiness.value
    assert data_readiness is not None
    if data_readiness < policy.gates.minimum_data_readiness:
        results.append(
            GateResult(
                gate=GateName.TECHNICAL_FIT,
                status=GateStatus.FAILED,
                rationale=(
                    f"An AI capability is plausible, but data readiness is {data_readiness}/5, "
                    f"below the provisional {policy.gates.minimum_data_readiness}/5 minimum."
                ),
                evidence_ids=_evidence_ids(step, technical_material),
                material_criteria=technical_material,
            )
        )
        results.extend(_not_evaluated(GateName.TECHNICAL_FIT))
        return GateEvaluation(RecommendationMode.INVESTIGATE_FURTHER, results)

    results.append(
        GateResult(
            gate=GateName.TECHNICAL_FIT,
            status=GateStatus.PASSED,
            rationale=(
                f"AI fit ({ai_fit}/5), data readiness ({data_readiness}/5), and mapped "
                "capabilities pass the provisional technical-fit gate."
            ),
            evidence_ids=_evidence_ids(step, technical_material),
            material_criteria=technical_material,
        )
    )

    business_material = [CriterionName.BUSINESS_VALUE]
    problems = _material_problem(step, business_material, policy)
    if problems:
        results.append(
            _insufficient_result(
                GateName.BUSINESS_VALUE,
                problems,
                step,
                business_material,
            )
        )
        results.extend(_not_evaluated(GateName.BUSINESS_VALUE))
        return GateEvaluation(RecommendationMode.INVESTIGATE_FURTHER, results)

    business_value = characteristics.business_value.value
    assert business_value is not None
    if business_value < policy.gates.minimum_business_value:
        results.append(
            GateResult(
                gate=GateName.BUSINESS_VALUE,
                status=GateStatus.FAILED,
                rationale=(
                    f"Business value is {business_value}/5, below the provisional "
                    f"{policy.gates.minimum_business_value}/5 minimum. Conventional process "
                    "improvement should be considered instead."
                ),
                evidence_ids=_evidence_ids(step, business_material),
                material_criteria=business_material,
            )
        )
        results.extend(_not_evaluated(GateName.BUSINESS_VALUE))
        return GateEvaluation(RecommendationMode.DO_NOT_RECOMMEND, results)

    results.append(
        GateResult(
            gate=GateName.BUSINESS_VALUE,
            status=GateStatus.PASSED,
            rationale=(
                f"Business value is {business_value}/5, meeting the provisional "
                f"{policy.gates.minimum_business_value}/5 minimum."
            ),
            evidence_ids=_evidence_ids(step, business_material),
            material_criteria=business_material,
        )
    )

    risk_material = [
        CriterionName.HUMAN_JUDGEMENT_REQUIREMENT,
        CriterionName.RISK_CONSEQUENCE,
        CriterionName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT,
    ]
    problems = _material_problem(
        step,
        risk_material,
        policy,
        include_accountability=True,
    )
    if problems:
        results.append(
            _insufficient_result(
                GateName.RISK_AND_AUTONOMY,
                problems,
                step,
                risk_material,
                accountability_material=True,
            )
        )
        return GateEvaluation(RecommendationMode.INVESTIGATE_FURTHER, results)

    judgement = characteristics.human_judgement_requirement.value
    risk = characteristics.risk_consequence.value
    residual_risk = characteristics.residual_risk_with_human_oversight.value
    accountability = characteristics.human_accountability_required.value
    assert None not in (judgement, risk, residual_risk, accountability)
    risk_evidence = set(_evidence_ids(step, risk_material))
    risk_evidence.update(characteristics.human_accountability_required.evidence_ids)

    if residual_risk >= policy.gates.unacceptable_residual_risk:
        results.append(
            GateResult(
                gate=GateName.RISK_AND_AUTONOMY,
                status=GateStatus.FAILED,
                rationale=(
                    f"Residual risk remains {residual_risk}/5 even with human oversight, "
                    f"meeting the provisional unacceptable-risk cutoff of "
                    f"{policy.gates.unacceptable_residual_risk}/5."
                ),
                evidence_ids=sorted(risk_evidence),
                material_criteria=risk_material,
                accountability_material=True,
            )
        )
        return GateEvaluation(RecommendationMode.DO_NOT_RECOMMEND, results)

    augmentation_constraints: list[str] = []
    if accountability:
        augmentation_constraints.append("human accountability is explicitly required")
    if judgement >= policy.gates.augment_human_judgement:
        augmentation_constraints.append(f"human judgement is {judgement}/5")
    if risk >= policy.gates.augment_risk_consequence:
        augmentation_constraints.append(f"consequence/risk is {risk}/5")
    if residual_risk >= policy.gates.augment_residual_risk:
        augmentation_constraints.append(f"residual risk is {residual_risk}/5")
    if augmentation_constraints:
        results.append(
            GateResult(
                gate=GateName.RISK_AND_AUTONOMY,
                status=GateStatus.PASSED_WITH_CONSTRAINTS,
                rationale=(
                    "AI may provide value, but material human involvement must remain because "
                    + "; ".join(augmentation_constraints)
                    + "."
                ),
                evidence_ids=sorted(risk_evidence),
                material_criteria=risk_material,
                accountability_material=True,
            )
        )
        return GateEvaluation(RecommendationMode.AUGMENT, results)

    risk_material.append(CriterionName.PREDICTABILITY)
    problems = _material_problem(
        step,
        [CriterionName.PREDICTABILITY],
        policy,
    )
    if problems:
        results.append(
            _insufficient_result(
                GateName.RISK_AND_AUTONOMY,
                problems,
                step,
                risk_material,
                accountability_material=True,
            )
        )
        return GateEvaluation(RecommendationMode.INVESTIGATE_FURTHER, results)

    predictability_value = characteristics.predictability.value
    assert predictability_value is not None
    risk_evidence.update(characteristics.predictability.evidence_ids)
    automation_eligible = (
        predictability_value >= policy.gates.automate_minimum_predictability
        and data_readiness >= policy.gates.automate_minimum_data_readiness
        and judgement <= policy.gates.automate_maximum_human_judgement
        and risk <= policy.gates.automate_maximum_risk_consequence
        and residual_risk <= policy.gates.automate_maximum_residual_risk
        and not accountability
    )
    if not automation_eligible:
        results.append(
            GateResult(
                gate=GateName.RISK_AND_AUTONOMY,
                status=GateStatus.PASSED_WITH_CONSTRAINTS,
                rationale=(
                    "AI may provide value, but the strict provisional automation thresholds "
                    "are not all met, so material human involvement remains."
                ),
                evidence_ids=sorted(risk_evidence),
                material_criteria=risk_material,
                accountability_material=True,
            )
        )
        return GateEvaluation(RecommendationMode.AUGMENT, results)

    results.append(
        GateResult(
            gate=GateName.RISK_AND_AUTONOMY,
            status=GateStatus.PASSED,
            rationale=(
                "Predictability, data readiness, judgement, consequence, residual risk, and "
                "accountability meet every provisional automation threshold."
            ),
            evidence_ids=sorted(risk_evidence),
            material_criteria=risk_material,
            accountability_material=True,
        )
    )
    return GateEvaluation(RecommendationMode.AUTOMATE, results)

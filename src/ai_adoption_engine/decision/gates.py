"""Ordered, deterministic gates for the provisional Phase 1 policy."""

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


def evaluate_gates(
    step: ProcessStep,
    capabilities: list[Capability],
    policy: DecisionPolicy,
) -> GateEvaluation:
    characteristics = step.characteristics
    results: list[GateResult] = []

    insufficient: list[str] = []
    for criterion_name in policy.evidence.required_criteria:
        criterion = characteristics.criterion(criterion_name)
        if criterion.knowledge_state is KnowledgeState.UNKNOWN or criterion.value is None:
            insufficient.append(f"{criterion_name.value} is unknown")
        elif (
            criterion.knowledge_state is KnowledgeState.INFERRED
            and (
                criterion.confidence is None
                or criterion.confidence < policy.evidence.minimum_inferred_confidence
            )
        ):
            insufficient.append(
                f"{criterion_name.value} confidence is below "
                f"{policy.evidence.minimum_inferred_confidence:.2f}"
            )
        if policy.evidence.require_evidence_reference and not criterion.evidence_ids:
            insufficient.append(f"{criterion_name.value} has no evidence reference")

    all_criteria = list(policy.evidence.required_criteria)
    if insufficient:
        results.append(
            GateResult(
                gate=GateName.EVIDENCE_SUFFICIENCY,
                status=GateStatus.FAILED,
                rationale="Material evidence is insufficient: " + "; ".join(insufficient) + ".",
                evidence_ids=_evidence_ids(step, all_criteria),
            )
        )
        results.extend(_not_evaluated(GateName.EVIDENCE_SUFFICIENCY))
        return GateEvaluation(RecommendationMode.INVESTIGATE_FURTHER, results)

    results.append(
        GateResult(
            gate=GateName.EVIDENCE_SUFFICIENCY,
            status=GateStatus.PASSED,
            rationale=(
                "Every required criterion has a supplied value, evidence reference, "
                "and sufficient confidence under the provisional policy."
            ),
            evidence_ids=_evidence_ids(step, all_criteria),
        )
    )

    ai_fit = characteristics.ai_capability_fit.value
    data_readiness = characteristics.data_readiness.value
    conventional_fit = characteristics.conventional_solution_fit.value
    assert ai_fit is not None and data_readiness is not None and conventional_fit is not None
    technical_evidence = _evidence_ids(
        step,
        [
            CriterionName.AI_CAPABILITY_FIT,
            CriterionName.DATA_READINESS,
            CriterionName.CONVENTIONAL_SOLUTION_FIT,
        ],
    )

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
                evidence_ids=technical_evidence,
            )
        )
        results.extend(_not_evaluated(GateName.TECHNICAL_FIT))
        return GateEvaluation(RecommendationMode.DO_NOT_RECOMMEND, results)

    if conventional_fit >= policy.gates.conventional_solution_fit_cutoff:
        results.append(
            GateResult(
                gate=GateName.TECHNICAL_FIT,
                status=GateStatus.FAILED,
                rationale=(
                    f"Conventional-solution fit is {conventional_fit}/5, meeting the "
                    f"{policy.gates.conventional_solution_fit_cutoff}/5 cutoff. "
                    "Conventional software, rules-based automation, or process redesign "
                    "is preferable to manufacturing an AI use case."
                ),
                evidence_ids=technical_evidence,
            )
        )
        results.extend(_not_evaluated(GateName.TECHNICAL_FIT))
        return GateEvaluation(RecommendationMode.DO_NOT_RECOMMEND, results)

    if data_readiness < policy.gates.minimum_data_readiness:
        results.append(
            GateResult(
                gate=GateName.TECHNICAL_FIT,
                status=GateStatus.FAILED,
                rationale=(
                    f"An AI capability is plausible, but data readiness is {data_readiness}/5, "
                    f"below the provisional {policy.gates.minimum_data_readiness}/5 minimum."
                ),
                evidence_ids=technical_evidence,
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
                "capabilities pass the provisional technical-fit gate; a conventional "
                "solution is not clearly preferable."
            ),
            evidence_ids=technical_evidence,
        )
    )

    business_value = characteristics.business_value.value
    assert business_value is not None
    business_evidence = _evidence_ids(step, [CriterionName.BUSINESS_VALUE])
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
                evidence_ids=business_evidence,
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
            evidence_ids=business_evidence,
        )
    )

    judgement = characteristics.human_judgement_requirement.value
    risk = characteristics.risk_consequence.value
    residual_risk = characteristics.residual_risk_with_human_oversight.value
    predictability = characteristics.predictability.value
    assert None not in (judgement, risk, residual_risk, predictability)
    risk_evidence = _evidence_ids(
        step,
        [
            CriterionName.HUMAN_JUDGEMENT_REQUIREMENT,
            CriterionName.RISK_CONSEQUENCE,
            CriterionName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT,
            CriterionName.PREDICTABILITY,
        ],
    )

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
                evidence_ids=risk_evidence,
            )
        )
        return GateEvaluation(RecommendationMode.DO_NOT_RECOMMEND, results)

    requires_augmentation = (
        characteristics.human_accountability_required
        or judgement >= policy.gates.augment_human_judgement
        or risk >= policy.gates.augment_risk_consequence
        or residual_risk >= policy.gates.augment_residual_risk
    )
    automation_eligible = (
        predictability >= policy.gates.automate_minimum_predictability
        and data_readiness >= policy.gates.automate_minimum_data_readiness
        and judgement <= policy.gates.automate_maximum_human_judgement
        and risk <= policy.gates.automate_maximum_risk_consequence
        and residual_risk <= policy.gates.automate_maximum_residual_risk
        and not characteristics.human_accountability_required
    )

    if requires_augmentation or not automation_eligible:
        constraints: list[str] = []
        if characteristics.human_accountability_required:
            constraints.append("human accountability is explicitly required")
        if judgement >= policy.gates.augment_human_judgement:
            constraints.append(f"human judgement is {judgement}/5")
        if risk >= policy.gates.augment_risk_consequence:
            constraints.append(f"consequence/risk is {risk}/5")
        if residual_risk >= policy.gates.augment_residual_risk:
            constraints.append(f"residual risk is {residual_risk}/5")
        if not constraints:
            constraints.append("the strict provisional automation thresholds are not all met")
        results.append(
            GateResult(
                gate=GateName.RISK_AND_AUTONOMY,
                status=GateStatus.PASSED_WITH_CONSTRAINTS,
                rationale=(
                    "AI may provide value, but material human involvement must remain because "
                    + "; ".join(constraints)
                    + "."
                ),
                evidence_ids=risk_evidence,
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
            evidence_ids=risk_evidence,
        )
    )
    return GateEvaluation(RecommendationMode.AUTOMATE, results)


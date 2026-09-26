"""Explicit, persistence-free engine API for the four-gate successor contract."""

from dataclasses import dataclass

from ai_adoption_engine.decision.four_gate_gates import (
    FourGateEvaluation,
    evaluate_four_gates,
    input_problem_code,
)
from ai_adoption_engine.decision.four_gate_policy import FourGateDecisionPolicy
from ai_adoption_engine.models.enums import CriterionName
from ai_adoption_engine.models.four_gate_assessment import (
    CapabilitySignalName,
    FourGateAccountabilityAssessment,
    FourGateCapabilitySignalAssessment,
    FourGateCriterionAssessment,
    FourGateName,
    FourGatePriorityScore,
    FourGatePriorityStatus,
    FourGateProcessAssessment,
    FourGateScoreComponent,
    FourGateStepAssessment,
    OutcomeCode,
    derive_outcome,
)
from ai_adoption_engine.models.process import BusinessProcess, ProcessStep


@dataclass(frozen=True)
class _PriorityEvaluation:
    status: FourGatePriorityStatus
    score: FourGatePriorityScore | None
    missing_criteria: list[CriterionName]


class FourGateAssessmentEngine:
    """Assess only through an explicitly supplied successor policy instance."""

    def __init__(self, policy: FourGateDecisionPolicy) -> None:
        self.policy = policy

    def assess(self, process: BusinessProcess) -> FourGateProcessAssessment:
        return FourGateProcessAssessment(
            process_id=process.process_id,
            process_name=process.name,
            framework_id=self.policy.framework_id,
            framework_version=self.policy.framework_version,
            decision_contract_version=self.policy.decision_contract_version,
            policy_id=self.policy.policy_id,
            policy_version=self.policy.version,
            policy_status=self.policy.status,
            step_assessments=[
                self._assess_step(process, step) for step in process.steps
            ],
        )

    def _assess_step(
        self,
        process: BusinessProcess,
        step: ProcessStep,
    ) -> FourGateStepAssessment:
        evaluation = evaluate_four_gates(step, self.policy)
        outcome = derive_outcome(
            evaluation.decision_status,
            evaluation.change_disposition,
            evaluation.readiness_disposition,
            evaluation.selected_intervention_family,
            evaluation.autonomy_ceiling,
        )
        priority_evaluation = self._evaluate_priority(step, outcome)

        material_gates: dict[CriterionName, list[FourGateName]] = {
            criterion: [] for criterion in CriterionName
        }
        context_gates: dict[CriterionName, list[FourGateName]] = {
            criterion: [] for criterion in CriterionName
        }
        capability_gates: dict[CapabilitySignalName, list[FourGateName]] = {
            signal: [] for signal in CapabilitySignalName
        }
        accountability_gates: list[FourGateName] = []
        for gate_result in evaluation.gate_results:
            for criterion in gate_result.material_criteria:
                material_gates[criterion].append(gate_result.gate)
            for criterion in gate_result.context_criteria:
                context_gates[criterion].append(gate_result.gate)
            for signal in gate_result.material_capability_signals:
                capability_gates[signal].append(gate_result.gate)
            if gate_result.accountability_material:
                accountability_gates.append(gate_result.gate)

        scoreable_criteria = set(self.policy.scoring.criteria)
        eligible_for_priority = outcome in set(self.policy.scoring.eligible_outcomes)
        criteria = []
        for criterion_name in CriterionName:
            item = step.characteristics.criterion(criterion_name)
            criteria.append(
                FourGateCriterionAssessment(
                    criterion=criterion_name,
                    value=item.value,
                    knowledge_state=item.knowledge_state,
                    rationale=item.rationale,
                    evidence_ids=list(item.evidence_ids),
                    confidence=item.confidence,
                    material_to_decision=bool(material_gates[criterion_name]),
                    material_to_priority=(
                        eligible_for_priority and criterion_name in scoreable_criteria
                    ),
                    material_at_gates=material_gates[criterion_name],
                    context_at_gates=context_gates[criterion_name],
                )
            )

        signal_assessments = []
        signals = step.characteristics.capability_signals
        for signal_name in CapabilitySignalName:
            item = getattr(signals, signal_name.value)
            signal_assessments.append(
                FourGateCapabilitySignalAssessment(
                    signal=signal_name,
                    value=item.value,
                    knowledge_state=item.knowledge_state,
                    rationale=item.rationale,
                    evidence_ids=list(item.evidence_ids),
                    confidence=item.confidence,
                    material_to_decision=bool(capability_gates[signal_name]),
                    material_at_gates=capability_gates[signal_name],
                )
            )

        accountability = step.characteristics.human_accountability_required
        evidence = self._decision_evidence(process, step, evaluation)
        reasoning = [result.rationale for result in evaluation.gate_results]
        if priority_evaluation.status is FourGatePriorityStatus.INCOMPLETE:
            reasoning.append(
                "The decision is complete, but priority is unavailable because these "
                "scoring-only inputs are insufficient: "
                + ", ".join(
                    item.value for item in priority_evaluation.missing_criteria
                )
                + "."
            )
        reasoning.append(
            f"Sole final outcome: {outcome.value} under {self.policy.policy_id} "
            f"({self.policy.status})."
        )

        return FourGateStepAssessment(
            step_id=step.step_id,
            activity=step.activity,
            decision_status=evaluation.decision_status,
            change_disposition=evaluation.change_disposition,
            readiness_disposition=evaluation.readiness_disposition,
            selected_intervention_family=evaluation.selected_intervention_family,
            autonomy_ceiling=evaluation.autonomy_ceiling,
            gate_results=evaluation.gate_results,
            blocking_gaps=evaluation.blocking_gaps,
            capabilities=evaluation.capabilities,
            capability_signals=signal_assessments,
            criteria=criteria,
            human_accountability=FourGateAccountabilityAssessment(
                value=accountability.value,
                knowledge_state=accountability.knowledge_state,
                rationale=accountability.rationale,
                evidence_ids=list(accountability.evidence_ids),
                confidence=accountability.confidence,
                material_to_decision=bool(accountability_gates),
                material_at_gates=accountability_gates,
            ),
            priority_status=priority_evaluation.status,
            priority=priority_evaluation.score,
            priority_missing_criteria=priority_evaluation.missing_criteria,
            reasoning=reasoning,
            evidence=evidence,
        )

    def _evaluate_priority(
        self,
        step: ProcessStep,
        outcome: OutcomeCode,
    ) -> _PriorityEvaluation:
        if outcome not in set(self.policy.scoring.eligible_outcomes):
            return _PriorityEvaluation(
                status=FourGatePriorityStatus.NOT_APPLICABLE,
                score=None,
                missing_criteria=[],
            )

        missing = []
        for criterion_name in self.policy.scoring.criteria:
            item = step.characteristics.criterion(criterion_name)
            if (
                input_problem_code(
                    item,
                    self.policy,
                    require_evidence=(
                        self.policy.evidence.require_material_criterion_evidence_reference
                    ),
                )
                is not None
            ):
                missing.append(criterion_name)
        if missing:
            return _PriorityEvaluation(
                status=FourGatePriorityStatus.INCOMPLETE,
                score=None,
                missing_criteria=missing,
            )

        components = []
        total = 0.0
        for criterion_name, criterion_policy in self.policy.scoring.criteria.items():
            item = step.characteristics.criterion(criterion_name)
            assert item.value is not None
            favourable_value = (
                item.value
                if criterion_policy.direction == "favourable"
                else self.policy.scale.maximum - item.value
            )
            contribution = (
                favourable_value
                / self.policy.scale.maximum
                * criterion_policy.weight
                * 100
            )
            total += contribution
            components.append(
                FourGateScoreComponent(
                    criterion=criterion_name,
                    raw_value=item.value,
                    favourable_value=favourable_value,
                    weight=criterion_policy.weight,
                    contribution=round(contribution, 2),
                )
            )

        score = round(total, 2)
        if score >= self.policy.scoring.bands.high_minimum:
            band = "HIGH"
        elif score >= self.policy.scoring.bands.medium_minimum:
            band = "MEDIUM"
        else:
            band = "LOW"
        return _PriorityEvaluation(
            status=FourGatePriorityStatus.COMPLETE,
            score=FourGatePriorityScore(
                score=score,
                band=band,
                components=components,
            ),
            missing_criteria=[],
        )

    @staticmethod
    def _decision_evidence(
        process: BusinessProcess,
        step: ProcessStep,
        evaluation: FourGateEvaluation,
    ):
        referenced_ids = set(step.evidence_ids)
        for gate_result in evaluation.gate_results:
            for criterion_name in gate_result.material_criteria:
                referenced_ids.update(
                    step.characteristics.criterion(criterion_name).evidence_ids
                )
            if gate_result.accountability_material:
                referenced_ids.update(
                    step.characteristics.human_accountability_required.evidence_ids
                )
            for signal_name in gate_result.material_capability_signals:
                referenced_ids.update(
                    getattr(
                        step.characteristics.capability_signals,
                        signal_name.value,
                    ).evidence_ids
                )
        return [
            evidence
            for evidence in process.evidence
            if evidence.evidence_id in referenced_ids
        ]


def assess_four_gate(
    process: BusinessProcess,
    policy: FourGateDecisionPolicy,
) -> FourGateProcessAssessment:
    """Explicit functional API; no default policy or application route is consulted."""

    return FourGateAssessmentEngine(policy).assess(process)

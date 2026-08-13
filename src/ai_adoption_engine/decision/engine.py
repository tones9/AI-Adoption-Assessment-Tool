"""Public deterministic assessment engine."""

from ai_adoption_engine.decision.capabilities import map_capabilities
from ai_adoption_engine.decision.gates import evaluate_gates
from ai_adoption_engine.decision.policy import DecisionPolicy
from ai_adoption_engine.decision.scoring import evaluate_priority
from ai_adoption_engine.models.assessment import (
    AccountabilityAssessment,
    CriterionAssessment,
    ProcessAssessment,
    StepAssessment,
)
from ai_adoption_engine.models.enums import CriterionName, PriorityStatus
from ai_adoption_engine.models.process import BusinessProcess, ProcessStep


class AssessmentEngine:
    def __init__(self, policy: DecisionPolicy) -> None:
        self.policy = policy

    def assess(self, process: BusinessProcess) -> ProcessAssessment:
        return ProcessAssessment(
            process_id=process.process_id,
            process_name=process.name,
            policy_id=self.policy.policy_id,
            policy_version=self.policy.version,
            policy_status=self.policy.status,
            step_assessments=[self._assess_step(process, step) for step in process.steps],
        )

    def _assess_step(
        self,
        process: BusinessProcess,
        step: ProcessStep,
    ) -> StepAssessment:
        capabilities = map_capabilities(step.characteristics.capability_signals)
        gate_evaluation = evaluate_gates(step, capabilities, self.policy)
        priority = None
        priority_status = PriorityStatus.NOT_APPLICABLE
        priority_missing_criteria: list[CriterionName] = []
        if gate_evaluation.recommendation in self.policy.scoring.eligible_recommendations:
            priority_evaluation = evaluate_priority(step, self.policy)
            priority = priority_evaluation.score
            priority_missing_criteria = priority_evaluation.missing_criteria
            priority_status = (
                PriorityStatus.COMPLETE
                if priority is not None
                else PriorityStatus.INCOMPLETE
            )

        referenced_ids = set(step.evidence_ids)
        for criterion_name in CriterionName:
            referenced_ids.update(
                step.characteristics.criterion(criterion_name).evidence_ids
            )
        referenced_ids.update(
            step.characteristics.human_accountability_required.evidence_ids
        )
        for signal in step.characteristics.capability_signals.inputs():
            referenced_ids.update(signal.evidence_ids)
        evidence = [
            reference for reference in process.evidence if reference.evidence_id in referenced_ids
        ]
        reasoning = [result.rationale for result in gate_evaluation.results]
        if priority_status is PriorityStatus.INCOMPLETE:
            reasoning.append(
                "Recommendation is valid, but priority is unavailable because these scoring "
                "inputs are insufficient: "
                + ", ".join(item.value for item in priority_missing_criteria)
                + "."
            )
        reasoning.append(
            f"Final mode: {gate_evaluation.recommendation.value} under "
            f"{self.policy.policy_id} ({self.policy.status})."
        )

        material_gates: dict[CriterionName, list] = {
            criterion: [] for criterion in CriterionName
        }
        accountability_gates = []
        for result in gate_evaluation.results:
            for criterion in result.material_criteria:
                if result.gate not in material_gates[criterion]:
                    material_gates[criterion].append(result.gate)
            if result.accountability_material and result.gate not in accountability_gates:
                accountability_gates.append(result.gate)

        priority_criteria = set(self.policy.scoring.criteria)
        criteria = []
        for criterion_name in CriterionName:
            item = step.characteristics.criterion(criterion_name)
            gates = material_gates[criterion_name]
            criteria.append(
                CriterionAssessment(
                    criterion=criterion_name,
                    value=item.value,
                    knowledge_state=item.knowledge_state,
                    rationale=item.rationale,
                    evidence_ids=item.evidence_ids,
                    confidence=item.confidence,
                    material_to_recommendation=bool(gates),
                    material_to_priority=(
                        gate_evaluation.recommendation
                        in self.policy.scoring.eligible_recommendations
                        and criterion_name in priority_criteria
                    ),
                    material_at_gates=gates,
                )
            )

        accountability = step.characteristics.human_accountability_required
        return StepAssessment(
            step_id=step.step_id,
            activity=step.activity,
            recommendation_mode=gate_evaluation.recommendation,
            capabilities=capabilities,
            criteria=criteria,
            human_accountability=AccountabilityAssessment(
                value=accountability.value,
                knowledge_state=accountability.knowledge_state,
                rationale=accountability.rationale,
                evidence_ids=accountability.evidence_ids,
                confidence=accountability.confidence,
                material_to_recommendation=bool(accountability_gates),
                material_at_gates=accountability_gates,
            ),
            gate_results=gate_evaluation.results,
            priority=priority,
            priority_status=priority_status,
            priority_missing_criteria=priority_missing_criteria,
            reasoning=reasoning,
            evidence=evidence,
        )

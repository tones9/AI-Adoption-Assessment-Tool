"""Public deterministic assessment engine."""

from ai_adoption_engine.decision.capabilities import map_capabilities
from ai_adoption_engine.decision.gates import evaluate_gates
from ai_adoption_engine.decision.policy import DecisionPolicy
from ai_adoption_engine.decision.scoring import calculate_priority
from ai_adoption_engine.models.assessment import ProcessAssessment, StepAssessment
from ai_adoption_engine.models.enums import CriterionName
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
        if gate_evaluation.recommendation in self.policy.scoring.eligible_recommendations:
            priority = calculate_priority(step, self.policy)

        referenced_ids = set(step.evidence_ids)
        for criterion_name in CriterionName:
            referenced_ids.update(
                step.characteristics.criterion(criterion_name).evidence_ids
            )
        evidence = [
            reference for reference in process.evidence if reference.evidence_id in referenced_ids
        ]
        reasoning = [result.rationale for result in gate_evaluation.results]
        reasoning.append(
            f"Final mode: {gate_evaluation.recommendation.value} under "
            f"{self.policy.policy_id} ({self.policy.status})."
        )

        return StepAssessment(
            step_id=step.step_id,
            activity=step.activity,
            recommendation_mode=gate_evaluation.recommendation,
            capabilities=capabilities,
            gate_results=gate_evaluation.results,
            priority=priority,
            reasoning=reasoning,
            evidence=evidence,
        )


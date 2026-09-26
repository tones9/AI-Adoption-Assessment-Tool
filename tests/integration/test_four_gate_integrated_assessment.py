from pathlib import Path

from ai_adoption_engine.application.fingerprints import (
    fingerprint_business_process,
)
from ai_adoption_engine.application.four_gate_assessment import (
    FourGateIntegratedAssessmentService,
)
from ai_adoption_engine.decision.four_gate_policy import load_four_gate_policy
from ai_adoption_engine.models.four_gate_assessment import (
    CapabilitySignalName,
    FourGateName,
    OutcomeCode,
)
from ai_adoption_engine.models.four_gate_integrated_assessment import (
    FourGateIntegratedAssessmentSuccess,
)
from tests.fakes.review import FIXED_TIME, approved_review


POLICY_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "decision_policy.v0.3.json"
)


def test_approved_review_flows_through_successor_phase5_with_complete_trace() -> None:
    approved = approved_review()
    policy = load_four_gate_policy(POLICY_PATH)

    integrated = FourGateIntegratedAssessmentService(
        policy_loader=lambda: policy,
        clock=lambda: FIXED_TIME,
        run_id_factory=lambda: "phase5-v02-integration",
    ).assess(approved)

    assert isinstance(integrated, FourGateIntegratedAssessmentSuccess)
    assert integrated.metadata.integration_schema_version == "phase5-v0.2"
    assert integrated.metadata.phase1_contract_version == "phase1-v0.4"
    assert integrated.lineage.validated_process_fingerprint == (
        fingerprint_business_process(approved.business_process)
    )
    assert integrated.process_assessment.process_id == (
        approved.business_process.process_id
    )
    assert len(integrated.process_assessment.step_assessments) == len(
        approved.business_process.steps
    )

    for process_step, assessed, trace in zip(
        approved.business_process.steps,
        integrated.process_assessment.step_assessments,
        integrated.step_traceability,
        strict=True,
    ):
        assert assessed.step_id == process_step.step_id == trace.step_id
        assert assessed.activity == process_step.activity
        assert len(assessed.gate_results) == 4
        assert [item.gate for item in assessed.gate_results] == list(FourGateName)
        assert assessed.outcome_code is OutcomeCode.DISCOVERY_REQUIRED
        assert len(trace.criteria) == 10
        assert len(trace.capability_signals) == len(CapabilitySignalName)
        assert trace.activity.assessment_field_path == (
            f"{trace.assessment_step_path}.activity"
        )
        assert trace.activity.evidence
        assert all(item.assessment_field_path for item in trace.criteria)
        assert all(item.assessment_field_path for item in trace.capability_signals)
        assert trace.human_accountability.assessment_field_path == (
            f"{trace.assessment_step_path}.human_accountability"
        )
        assert trace.decision_status_path.endswith(".decision_status")
        assert trace.change_disposition_path.endswith(".change_disposition")
        assert trace.readiness_disposition_path.endswith(".readiness_disposition")
        assert trace.selected_intervention_family_path.endswith(
            ".selected_intervention_family"
        )
        assert trace.autonomy_ceiling_path.endswith(".autonomy_ceiling")
        assert trace.outcome_code_path.endswith(".outcome_code")
        assert trace.gate_results_path.endswith(".gate_results")

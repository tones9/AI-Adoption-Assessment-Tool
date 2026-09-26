from pathlib import Path

from ai_adoption_engine.application.four_gate_assessment import (
    FourGateIntegratedAssessmentService,
)
from ai_adoption_engine.decision.four_gate_engine import FourGateAssessmentEngine
from ai_adoption_engine.decision.four_gate_policy import load_four_gate_policy
from ai_adoption_engine.decision_support.four_gate_service import (
    FourGateDecisionSupportPackageService,
)
from ai_adoption_engine.extraction.providers.openai import OpenAIExtractionProvider
from ai_adoption_engine.models.four_gate_assessment import FourGateName
from ai_adoption_engine.models.four_gate_decision_support import (
    FourGateDecisionPackageSuccess,
    FourGateReportSectionId,
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


def test_approved_review_flows_offline_through_successor_phase5_and_phase6(
    monkeypatch,
) -> None:
    approved = approved_review()
    policy = load_four_gate_policy(POLICY_PATH)
    integrated = FourGateIntegratedAssessmentService(
        policy_loader=lambda: policy,
        clock=lambda: FIXED_TIME,
        run_id_factory=lambda: "phase6-v02-offline-assessment",
    ).assess(approved)
    assert isinstance(integrated, FourGateIntegratedAssessmentSuccess)

    def fail_forbidden_runtime(*args, **kwargs):
        raise AssertionError("Phase 6 reran assessment or called a provider")

    monkeypatch.setattr(FourGateAssessmentEngine, "assess", fail_forbidden_runtime)
    monkeypatch.setattr(
        OpenAIExtractionProvider,
        "extract_chunk",
        fail_forbidden_runtime,
    )
    generated = FourGateDecisionSupportPackageService().generate(integrated)

    assert isinstance(generated, FourGateDecisionPackageSuccess)
    package = generated.package
    assert package.package_schema_version == "phase6-v0.2"
    assert package.source.integration_schema_version == "phase5-v0.2"
    assert package.source.phase1_contract_version == "phase1-v0.4"
    assert package.current_state.process_id == approved.business_process.process_id
    assert package.source.lineage.review_id == approved.review.review_id
    assert package.source.lineage.validated_process_fingerprint == (
        integrated.lineage.validated_process_fingerprint
    )
    assert package.source.policy.decision_policy_fingerprint == (
        integrated.policy.decision_policy_fingerprint
    )
    assert [item.step_id for item in package.portfolio.items] == [
        item.step_id
        for item in integrated.process_assessment.step_assessments
    ]
    assert all(
        [gate.gate for gate in item.gate_results] == list(FourGateName)
        for item in package.portfolio.items
    )
    assert [section.section_id for section in package.report_content.sections] == list(
        FourGateReportSectionId
    )
    assert all(
        item.source_traceability.outcome_code_path.endswith(".outcome_code")
        for item in package.portfolio.items
    )

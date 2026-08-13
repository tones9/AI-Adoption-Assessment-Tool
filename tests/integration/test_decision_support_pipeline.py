from ai_adoption_engine.application.assessment import IntegratedAssessmentService
from ai_adoption_engine.decision.engine import AssessmentEngine
from ai_adoption_engine.decision_support import DecisionSupportPackageService
from ai_adoption_engine.extraction.providers.openai import OpenAIExtractionProvider
from ai_adoption_engine.models.decision_support import (
    DecisionPackageSuccess,
    FutureStateStatus,
    PackageCompleteness,
)
from ai_adoption_engine.models.enums import RecommendationMode
from tests.fakes.review import FIXED_TIME, approved_review


def test_complete_offline_pipeline_to_decision_support_package(monkeypatch) -> None:
    def fail_openai(*args, **kwargs):
        raise AssertionError("The offline pipeline called OpenAI")

    monkeypatch.setattr(OpenAIExtractionProvider, "extract_chunk", fail_openai)
    approved = approved_review()
    integrated = IntegratedAssessmentService(
        clock=lambda: FIXED_TIME,
        run_id_factory=lambda: "phase6-offline-assessment",
    ).assess(approved)

    def fail_engine(*args, **kwargs):
        raise AssertionError("Phase 6 reran the Phase 1 engine")

    monkeypatch.setattr(AssessmentEngine, "assess", fail_engine)
    generated = DecisionSupportPackageService().generate(integrated)
    assert isinstance(generated, DecisionPackageSuccess)
    package = generated.package
    assert package.completeness is (
        PackageCompleteness.COMPLETE_WITH_INFORMATION_GAPS
    )
    assert package.current_state.process_id == approved.business_process.process_id
    assert package.source.lineage.review_id == approved.review.review_id
    assert package.source.lineage.validated_process_fingerprint == integrated.lineage.validated_process_fingerprint
    assert package.source.policy.decision_policy_fingerprint == integrated.policy.decision_policy_fingerprint
    assert [item.step_id for item in package.portfolio.items] == [
        item.step_id for item in integrated.process_assessment.step_assessments
    ]
    assert all(
        item.recommendation_mode is RecommendationMode.INVESTIGATE_FURTHER
        for item in package.portfolio.items
    )
    assert package.future_state.status is FutureStateStatus.PROPOSED_NOT_DEPLOYED
    assert all(item.basis.assessment_paths for item in package.future_state.steps)
    assert package.roi_statement == "ROI / quantified benefit unavailable with current evidence."

from ai_adoption_engine.decision_support import DecisionSupportPackageService
from ai_adoption_engine.models.decision_support import (
    DecisionPackageSuccess,
    GovernanceCategory,
    InformationGapKind,
    PlanningOrigin,
    ReportSectionId,
)
from ai_adoption_engine.models.enums import KnowledgeState, RecommendationMode
from tests.fakes.decision_support import sample_integrated_assessment


def _package():
    result = DecisionSupportPackageService().generate(sample_integrated_assessment())
    assert isinstance(result, DecisionPackageSuccess)
    return result.package


def test_unknown_and_investigation_information_remain_visible() -> None:
    package = _package()
    investigation = next(
        item
        for item in package.portfolio.items
        if item.recommendation_mode is RecommendationMode.INVESTIGATE_FURTHER
    )
    assert any(
        gap.kind is InformationGapKind.UNKNOWN_INPUT
        and gap.knowledge_state is KnowledgeState.UNKNOWN
        for gap in investigation.missing_information
    )
    assert any(
        gap.kind is InformationGapKind.INVESTIGATION_REQUIRED
        for gap in investigation.missing_information
    )
    assert all(gap.basis.step_id == investigation.step_id for gap in investigation.missing_information)


def test_governance_language_is_cautious_and_never_claims_approval() -> None:
    package = _package()
    summary = package.governance
    assert summary.legal_conclusions_provided is False
    assert summary.security_approval_claimed is False
    assert summary.deployment_readiness_claimed is False
    statements = " ".join(item.statement.lower() for item in summary.considerations)
    assert "requires validation" in statements
    assert "no compliance or security approval is asserted" in statements
    assert "gdpr compliant" not in statements
    assert "deployment ready" not in statements
    assert {
        GovernanceCategory.CONSEQUENCE_OF_ERROR,
        GovernanceCategory.HUMAN_JUDGEMENT,
        GovernanceCategory.ACCOUNTABILITY,
        GovernanceCategory.DATA_READINESS,
    }.issubset({item.category for item in summary.considerations})


def test_every_planning_interpretation_has_step_basis_and_derived_origin() -> None:
    package = _package()
    for step in package.future_state.steps:
        assert step.basis.origin is PlanningOrigin.DERIVED_PLANNING_GUIDANCE
        assert step.basis.step_id == step.source_step_id
        assert step.basis.assessment_paths
    for roadmap in package.roadmap.opportunities:
        for stage in roadmap.stages:
            assert stage.basis.origin is PlanningOrigin.DERIVED_PLANNING_GUIDANCE
            assert stage.basis.step_id == roadmap.step_id
    for item in package.governance.considerations:
        assert item.basis.origin is PlanningOrigin.DERIVED_PLANNING_GUIDANCE
        assert item.basis.step_id == item.step_id


def test_report_distinguishes_findings_planning_and_evidence_origins() -> None:
    package = _package()
    by_id = {item.section_id: item for item in package.report_content.sections}
    portfolio = by_id[ReportSectionId.OPPORTUNITY_PORTFOLIO]
    future = by_id[ReportSectionId.FUTURE_STATE]
    evidence = by_id[ReportSectionId.EVIDENCE_APPENDIX]
    assert all(
        item.origin is PlanningOrigin.ASSESSMENT_FINDING
        for item in portfolio.statements
    )
    assert all(
        item.origin is PlanningOrigin.DERIVED_PLANNING_GUIDANCE
        for item in future.statements
    )
    assert any(item.evidence_ids for item in evidence.statements)
    assert any(item.reviewed_origins for item in portfolio.statements)


def test_evidence_appendix_is_deduplicated_and_resolvable() -> None:
    package = _package()
    identifiers = [item.evidence_id for item in package.evidence_appendix]
    assert identifiers == sorted(set(identifiers))
    assert all(item.document_id == package.current_state.source_document_id for item in package.evidence_appendix)
    assert all(item.block_id and item.source_locator for item in package.evidence_appendix)

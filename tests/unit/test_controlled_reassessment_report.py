from __future__ import annotations

from dataclasses import replace

from ai_adoption_engine.application.decision_continuation import (
    DecisionContinuationService,
)
from ai_adoption_engine.grw.m2.service import M2ReassessmentService
from ai_adoption_engine.persistence.reassessment import SQLiteReassessmentRepository
from ai_adoption_engine.presentation.controlled_reassessment_report import (
    render_controlled_reassessment_report_html,
)
from ai_adoption_engine.presentation.report_html import render_report_html
from ai_adoption_engine.workspace.models import ArtifactType
from ai_adoption_engine.workspace.service import AssessmentWorkspaceService
from tests.integration.test_grw_m2_m1_lifecycle import _full_lifecycle


def _report(repository, assessment_id):
    workspace = AssessmentWorkspaceService(
        repository, extraction_service_factory=lambda *_args: None
    )
    view = DecisionContinuationService(
        workspace,
        M2ReassessmentService(
            repository, SQLiteReassessmentRepository(repository.path)
        ),
    ).open(assessment_id)
    report = view.m2_runs[0].controlled_report
    assert report is not None
    return report


def test_controlled_reassessment_report_is_deterministic_and_keeps_decisions_separate(
    tmp_path,
) -> None:
    repository, assessment_id, *_ = _full_lifecycle(tmp_path)
    report = _report(repository, assessment_id)

    first = render_controlled_reassessment_report_html(report)
    second = render_controlled_reassessment_report_html(report)

    assert first == second
    assert "1. Original baseline decision" in first
    assert report.baseline_package_id in first
    assert "Unknown (Unknown)" in first
    assert "The baseline Decision Package remains unchanged" in first
    assert "2. Approved controlled change" in first
    assert report.approved_change.approval_reason in first
    assert report.approved_change.mapping_rationale in first
    assert "3. Approved evidence basis" in first
    assert report.evidence.content_sha256 in first
    assert report.evidence.exact_excerpt in first
    assert "4. Separate successor comparison" in first
    assert report.successor_package_id in first
    assert "3 (Known)" in first
    assert "not a measured outcome" in first
    assert "ROI result" in first
    assert "evidence of adoption success" in first
    assert "proves success" not in first.lower()
    assert "improved decision" not in first.lower()
    assert "recommended deployment" not in first.lower()


def test_controlled_reassessment_report_escapes_all_evidence_text(tmp_path) -> None:
    repository, assessment_id, *_ = _full_lifecycle(tmp_path)
    report = _report(repository, assessment_id)
    malicious = "<script>alert('evidence')</script>"
    evidence = replace(
        report.evidence,
        filename=malicious,
        source_label=malicious,
        exact_excerpt=malicious,
        source_authority=malicious,
        scope_statement=malicious,
        period_statement=malicious,
        semantic_rationale=malicious,
        limitations=malicious,
        conflict_rationale=malicious,
        reconciliation_statement=malicious,
        applicability_statement=malicious,
    )

    rendered = render_controlled_reassessment_report_html(
        replace(report, evidence=evidence)
    )

    assert "<script>" not in rendered
    assert rendered.count("&lt;script&gt;") == 11


def test_controlled_renderer_does_not_change_generic_report_output(tmp_path) -> None:
    repository, assessment_id, *_ = _full_lifecycle(tmp_path)
    report = _report(repository, assessment_id)
    workspace = repository.load_workspace(assessment_id)
    package = workspace.active_artifacts[
        ArtifactType.DECISION_PACKAGE_RESULT
    ].payload.package
    before = render_report_html(package)

    render_controlled_reassessment_report_html(report)

    assert render_report_html(package) == before

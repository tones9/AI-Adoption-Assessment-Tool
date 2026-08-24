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
    # Business layer, in the frozen Decision Experience order.
    for heading in (
        "What this report is",
        "Your original decision",
        "What additional evidence was approved",
        "What changed in the assessment input",
        "What did not change",
        "The separate reassessment decision",
        "Original decision compared with the reassessment",
        "Limitations",
    ):
        assert f"<h2>{heading}</h2>" in first, heading
    assert first.index("Your original decision") < first.index(
        "The separate reassessment decision"
    )

    # Criterion values read as business language, not engine vocabulary.
    assert "Not established by the evidence" in first
    assert "3 out of 5 — confirmed by the evidence" in first
    assert "Unknown (Unknown)" not in first
    assert "3 (Known)" not in first

    assert "Your original Decision Package was not rewritten." in first
    assert report.approved_change.approval_reason in first
    assert report.approved_change.mapping_rationale in first
    assert report.evidence.exact_excerpt in first
    assert (
        "It does not establish Return on Investment (ROI), predictive accuracy, "
        "or safety." in first
    )
    assert (
        "A difference between the two decisions is not a measured outcome or "
        "evidence that adoption succeeded." in first
    )

    # Identifiers stay reachable, in the technical appendix only.
    appendix = first.split("<details>", 1)[1]
    body = first.split("<details>", 1)[0]
    for token in (
        report.baseline_package_id,
        report.successor_package_id,
        report.run_id,
        report.evidence.content_sha256,
        report.evidence.document_id,
        report.approved_change.changed_field_path,
    ):
        assert token in appendix, token
        assert token not in body, token
    # The criterion reaches the reader as its business label; the raw field name
    # is recorded in the appendix.  (It also occurs inside the authoritative
    # evidence filename, so only the labelled record is asserted here.)
    assert f"Reviewed field: {report.field_name}" in appendix
    assert f"Reviewed field: {report.field_name}" not in body
    assert "Data readiness:" in body

    lowered = first.lower()
    for framing in (
        "proves success",
        "improved decision",
        "recommended deployment",
        "better decision",
        "upgraded",
        "corrected the decision",
    ):
        assert framing not in lowered


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

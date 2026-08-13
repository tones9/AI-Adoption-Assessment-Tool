from pathlib import Path

import pytest

from ai_adoption_engine.workspace.composition import extraction_service_for
from ai_adoption_engine.workspace.demo_extraction import (
    ScriptedDemoExtractionProvider,
    demo_text,
)
from ai_adoption_engine.workspace.models import ExecutionMode
from ai_adoption_engine.decision_support import DecisionSupportPackageService
from ai_adoption_engine.extraction.providers.base import ExtractionRequest
from ai_adoption_engine.extraction.service import ProcessExtractionService
from ai_adoption_engine.ingestion.text import ingest_raw_text
from ai_adoption_engine.presentation.report_html import render_report_html
from ai_adoption_engine.presentation.report_view import build_report_view
from ai_adoption_engine.models.decision_support import ReportSectionId
from ai_adoption_engine.workspace.composition import build_workspace_service
from tests.fakes.decision_support import sample_integrated_assessment


def test_demo_provider_is_fixture_bound() -> None:
    arbitrary = ingest_raw_text("An arbitrary uploaded process document.")
    assert arbitrary.document is not None
    with pytest.raises(Exception, match="bundled synthetic demo"):
        extraction_service_for(ExecutionMode.OFFLINE_DEMO, arbitrary.document)


def test_live_mode_never_falls_back_to_demo_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    fixture = ingest_raw_text(demo_text())
    assert fixture.document is not None
    with pytest.raises(Exception, match="OPENAI_API_KEY"):
        extraction_service_for(ExecutionMode.LIVE_PROVIDER, fixture.document)


def test_demo_provider_produces_candidate_without_openai(monkeypatch) -> None:
    from ai_adoption_engine.extraction.providers.openai import OpenAIExtractionProvider

    monkeypatch.setattr(
        OpenAIExtractionProvider,
        "extract_chunk",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("OpenAI called")),
    )
    ingestion = ingest_raw_text(demo_text())
    assert ingestion.document is not None
    result = ProcessExtractionService(ScriptedDemoExtractionProvider()).extract(
        ingestion.document
    )
    assert result.status == "success"
    assert result.candidate is not None
    assert len(result.candidate.steps) == 7
    assert {item.provider_name for item in result.provider_invocations} == {"demo-scripted"}


def test_html_report_is_deterministic_and_escapes_content() -> None:
    generated = DecisionSupportPackageService().generate(sample_integrated_assessment())
    assert generated.status == "success"
    package = generated.package
    first = render_report_html(package)
    second = render_report_html(package)
    assert first == second
    assert "PROPOSED / NOT DEPLOYED" in first
    assert "ROI / quantified benefit unavailable with current evidence." in first
    assert package.source.lineage.validated_process_fingerprint in first
    assert "<script>" not in first
    payload = package.model_dump(mode="json")
    payload["report_content"]["sections"][0]["statements"][0]["text"] = (
        "<script>alert('document text')</script>"
    )
    payload["portfolio"]["items"][0]["current_activity"] = (
        "<img src=x onerror=alert('activity')>"
    )
    payload["portfolio"]["items"][0]["source_traceability"]["activity"][
        "evidence"
    ][0]["source_locator"] = "<script>alert('locator')</script>"
    malicious = package.__class__.model_validate(payload)
    rendered = render_report_html(malicious)
    assert "<script>" not in rendered
    assert "<img" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "&lt;img" in rendered


def _seven_step_demo_package(tmp_path: Path, monkeypatch):
    from ai_adoption_engine.extraction.providers.openai import OpenAIExtractionProvider

    monkeypatch.setattr(
        OpenAIExtractionProvider,
        "extract_chunk",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("OpenAI called")),
    )
    path = tmp_path / "seven-step-report.db"
    service = build_workspace_service(path)
    assessment = service.repository.create_assessment(
        "Seven-step report UAT", ExecutionMode.OFFLINE_DEMO
    )
    service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    service.extract(assessment.assessment_id)
    review = service.start_review(assessment.assessment_id)
    service.review_service.accept_assertion(
        review, review.process_name, "process.name"
    )
    for step in review.steps:
        service.review_service.accept_assertion(
            review,
            step.activity,
            f"steps.{step.candidate_step_id}.activity",
        )
    service.review_service.accept_step_order(review)
    service.save_review(assessment.assessment_id, review)
    assert service.approve(assessment.assessment_id).approved is not None
    service.assess(assessment.assessment_id)
    generated = service.generate_package(assessment.assessment_id)
    assert generated.status == "success"
    return generated.package


def test_seven_step_report_consolidates_repetition_without_changing_package_traceability(
    tmp_path, monkeypatch
) -> None:
    package = _seven_step_demo_package(tmp_path, monkeypatch)
    original_gap_ids = [item.gap_id for item in package.missing_information]
    original_governance_ids = [
        item.consideration_id for item in package.governance.considerations
    ]

    view = build_report_view(package)
    html = render_report_html(package)

    gaps = next(
        section for section in view if section.section_id is ReportSectionId.MISSING_INFORMATION
    )
    governance = next(
        section for section in view if section.section_id is ReportSectionId.RISKS_GOVERNANCE
    )
    assert len(package.missing_information) == 154
    assert len(package.governance.considerations) == 42
    assert [item.gap_id for item in package.missing_information] == original_gap_ids
    assert [
        item.consideration_id for item in package.governance.considerations
    ] == original_governance_ids
    assert [block.heading for block in gaps.blocks].count("Process-wide/common gaps") == 1
    assert not any(
        block.heading and "step-specific gaps" in block.heading for block in gaps.blocks
    )
    assert len(gaps.blocks[0].bullets) == 4
    assert any("Unknown assessment criteria" in item for item in gaps.blocks[0].bullets)
    assert any("Unknown capability signals" in item for item in gaps.blocks[0].bullets)
    assert [block.heading for block in governance.blocks].count(
        "Process-level governance considerations"
    ) == 1
    assert len(governance.blocks[0].bullets) == 6
    assert not any(
        block.heading and "step-specific considerations" in block.heading
        for block in governance.blocks
    )
    assert html.count("Process-wide/common gaps") == 1
    assert html.count("Process-level governance considerations") == 1


def test_seven_step_report_is_business_readable_and_materially_shorter(
    tmp_path, monkeypatch
) -> None:
    package = _seven_step_demo_package(tmp_path, monkeypatch)

    html = render_report_html(package)

    assert "All 7 activities require further investigation" in html
    assert "gather and validate the missing evidence" in html
    assert "not to begin deployment planning" in html
    assert html.count("Methodology and policy disclosure") == 1
    assert "Required methodology disclosure" not in html
    for disclosure in package.methodology.disclosure_statements:
        assert html.count(disclosure) == 1
    for item in package.portfolio.items:
        assert f"{item.sequence}. {item.current_activity}" in html
        assert "Recommendation:" in html
        assert "Reason / basis:" in html
        assert "Material missing information:" in html
        assert "Next action:" in html
    # Accepted pre-correction UAT fixture: 34,064 characters and 251 list items.
    assert len(html) < 30_000
    assert html.count("<li>") < 100


def test_roadmap_and_evidence_lead_with_activity_and_keep_ids_secondary(
    tmp_path, monkeypatch
) -> None:
    package = _seven_step_demo_package(tmp_path, monkeypatch)
    html = render_report_html(package)
    roadmap_start = html.index("<section id='adoption-roadmap'>")
    roadmap_end = html.index("</section>", roadmap_start)
    roadmap_html = html[roadmap_start:roadmap_end]
    evidence_start = html.index("<section id='evidence-and-traceability-appendix'>")
    evidence_html = html[evidence_start:]

    for item in package.portfolio.items:
        activity_heading = f"<h3>{item.sequence}. {item.current_activity}</h3>"
        assert activity_heading in roadmap_html
        assert activity_heading in evidence_html
        roadmap_id_position = roadmap_html.index(f"Internal step ID: {item.step_id}")
        roadmap_heading_position = roadmap_html.index(activity_heading)
        assert roadmap_heading_position < roadmap_id_position
        evidence_id_position = evidence_html.index(f"Internal step ID: {item.step_id}")
        evidence_heading_position = evidence_html.index(activity_heading)
        assert evidence_heading_position < evidence_id_position
        reference = item.source_traceability.activity.evidence[0]
        source_position = evidence_html.index(f"Source: {reference.source_locator}")
        technical_position = evidence_html.index(
            f"Evidence ID: {reference.evidence_id}"
        )
        assert evidence_heading_position < source_position < technical_position

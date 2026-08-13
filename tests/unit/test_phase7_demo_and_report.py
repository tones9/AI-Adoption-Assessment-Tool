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
    malicious = package.__class__.model_validate(payload)
    rendered = render_report_html(malicious)
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered

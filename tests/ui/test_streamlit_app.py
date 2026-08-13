from pathlib import Path

from streamlit.testing.v1 import AppTest

from ai_adoption_engine.workspace.models import (
    ArtifactType,
    ExecutionMode,
    WorkflowStage,
)
from ai_adoption_engine.decision_support import DecisionSupportPackageService
from ai_adoption_engine.ingestion.text import ingest_raw_text
from ai_adoption_engine.models.document import (
    IngestionIssue,
    IngestionResult,
    IngestionStatus,
    IssueSeverity,
)
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from tests.fakes.decision_support import sample_integrated_assessment
from tests.fakes.review import approved_review


ROOT = Path(__file__).resolve().parents[2]


def test_app_starts_with_five_page_navigation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(tmp_path / "ui.db"))
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=10).run()
    assert not app.exception
    assert app.title[0].value == "AI Adoption Assessment"
    entrypoint = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    for label in (
        "Assessments",
        "Source & Extraction",
        "Process Review",
        "Assessment Results",
        "Decision Package",
    ):
        assert f'title="{label}"' in entrypoint


def test_inaccessible_source_page_explains_prerequisite(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(tmp_path / "guard.db"))
    app = AppTest.from_string(
        "from ai_adoption_engine.presentation.pages.source import render\nrender()",
        default_timeout=30,
    ).run()
    assert not app.exception
    assert any("Create or open an assessment first" in item.value for item in app.info)


def _selected_page(script: str, assessment_id: str) -> str:
    return (
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment_id!r}\n"
        + script
    )


def test_results_ui_displays_all_four_modes_and_incomplete_priority(tmp_path, monkeypatch) -> None:
    path = tmp_path / "results.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    repository = SQLiteAssessmentRepository(path)
    assessment = repository.create_assessment("Four modes", ExecutionMode.OFFLINE_DEMO)
    approved = approved_review()
    approval_ref = repository.save_artifact_and_advance(
        assessment.assessment_id,
        ArtifactType.APPROVED_REVIEW,
        approved,
        artifact_schema_version="phase4-v0.1",
        stage=WorkflowStage.APPROVED,
    )
    integrated = sample_integrated_assessment()
    incomplete_payload = integrated.model_dump(mode="json")
    incomplete_payload["process_assessment"]["step_assessments"][0]["priority"] = None
    incomplete_payload["process_assessment"]["step_assessments"][0]["priority_status"] = "incomplete"
    incomplete_payload["process_assessment"]["step_assessments"][0]["priority_missing_criteria"] = ["repetition"]
    integrated = integrated.__class__.model_validate(incomplete_payload)
    repository.save_artifact_and_advance(
        assessment.assessment_id,
        ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
        integrated,
        artifact_schema_version="phase5-v0.1",
        stage=WorkflowStage.ASSESSED,
        parent_artifact_id=approval_ref.artifact_id,
    )
    app = AppTest.from_string(
        _selected_page(
            "from ai_adoption_engine.presentation.pages.results import render\nrender()",
            assessment.assessment_id,
        ),
        default_timeout=30,
    ).run()
    assert not app.exception
    rendered = "\n".join(
        str(item.value) for kind in ("markdown", "caption", "warning") for item in app.get(kind)
    )
    for label in ("Automate", "Augment", "Investigate Further", "Do Not Recommend"):
        assert label in rendered
    assert "Incomplete" in rendered


def test_decision_package_ui_renders_proposed_state_gates_and_report(tmp_path, monkeypatch) -> None:
    path = tmp_path / "package.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    repository = SQLiteAssessmentRepository(path)
    assessment = repository.create_assessment("Package", ExecutionMode.OFFLINE_DEMO)
    approved = approved_review()
    approval_ref = repository.save_artifact_and_advance(
        assessment.assessment_id,
        ArtifactType.APPROVED_REVIEW,
        approved,
        artifact_schema_version="phase4-v0.1",
        stage=WorkflowStage.APPROVED,
    )
    integrated = sample_integrated_assessment()
    integrated_ref = repository.save_artifact_and_advance(
        assessment.assessment_id,
        ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
        integrated,
        artifact_schema_version="phase5-v0.1",
        stage=WorkflowStage.ASSESSED,
        parent_artifact_id=approval_ref.artifact_id,
    )
    generated = DecisionSupportPackageService().generate(integrated)
    repository.save_artifact_and_advance(
        assessment.assessment_id,
        ArtifactType.DECISION_PACKAGE_RESULT,
        generated,
        artifact_schema_version="phase6-v0.1",
        stage=WorkflowStage.PACKAGE_READY,
        parent_artifact_id=integrated_ref.artifact_id,
    )
    app = AppTest.from_string(
        _selected_page(
            "from ai_adoption_engine.presentation.pages.decision_package import render\nrender()",
            assessment.assessment_id,
        ),
        default_timeout=30,
    ).run()
    assert not app.exception
    rendered = "\n".join(
        str(item.value)
        for kind in ("markdown", "caption", "warning", "info")
        for item in app.get(kind)
    )
    assert "PROPOSED / NOT DEPLOYED" in rendered
    assert "GO / REVISE / STOP" in rendered
    assert "ROI / quantified benefit unavailable with current evidence." in rendered
    assert app.download_button


def test_scanned_page_warning_states_ocr_is_out_of_scope(tmp_path, monkeypatch) -> None:
    path = tmp_path / "ocr.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    repository = SQLiteAssessmentRepository(path)
    assessment = repository.create_assessment("OCR warning", ExecutionMode.LIVE_PROVIDER)
    base = ingest_raw_text("One extractable page")
    partial = IngestionResult(
        status=IngestionStatus.PARTIAL,
        document=base.document,
        issues=[
            IngestionIssue(
                severity=IssueSeverity.WARNING,
                code="page-no-extractable-text",
                message="Page 2 contains no extractable text.",
                page_number=2,
            )
        ],
    )
    repository.save_artifact_and_advance(
        assessment.assessment_id,
        ArtifactType.INGESTION_RESULT,
        partial,
        artifact_schema_version="phase2-v0.1",
        stage=WorkflowStage.INGESTED,
    )
    app = AppTest.from_string(
        _selected_page(
            "from ai_adoption_engine.presentation.pages.source import render\nrender()",
            assessment.assessment_id,
        ),
        default_timeout=10,
    ).run()
    assert not app.exception
    assert any("OCR is outside the MVP" in item.value for item in app.warning)


def test_malformed_persisted_state_shows_safe_error_without_partial_hydration(tmp_path, monkeypatch) -> None:
    import sqlite3

    path = tmp_path / "corrupt.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    repository = SQLiteAssessmentRepository(path)
    assessment = repository.create_assessment("Corrupt", ExecutionMode.OFFLINE_DEMO)
    repository.save_artifact_and_advance(
        assessment.assessment_id,
        ArtifactType.INGESTION_RESULT,
        ingest_raw_text("Corrupt me"),
        artifact_schema_version="phase2-v0.1",
        stage=WorkflowStage.INGESTED,
    )
    connection = sqlite3.connect(path)
    connection.execute("UPDATE assessment_artifacts SET payload_json = '{}'")
    connection.commit()
    connection.close()
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=10).run()
    app.session_state["selected_assessment_id"] = assessment.assessment_id
    app.run()
    assert not app.exception
    assert any("No partial state was loaded" in item.value for item in app.error)


def test_results_page_never_assesses_without_explicit_approval(tmp_path, monkeypatch) -> None:
    path = tmp_path / "unapproved.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    repository = SQLiteAssessmentRepository(path)
    assessment = repository.create_assessment("Unapproved", ExecutionMode.OFFLINE_DEMO)
    app = AppTest.from_string(
        _selected_page(
            "from ai_adoption_engine.presentation.pages.results import render\nrender()",
            assessment.assessment_id,
        ),
        default_timeout=10,
    ).run()
    assert not app.exception
    assert any("Explicitly approve" in item.value for item in app.info)

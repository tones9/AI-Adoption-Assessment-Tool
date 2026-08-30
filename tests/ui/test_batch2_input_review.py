"""Focused regression coverage for the Batch 2 input and review redesign."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.workspace.composition import build_workspace_service
from ai_adoption_engine.workspace.demo_extraction import demo_text
from ai_adoption_engine.workspace.models import ExecutionMode


ROOT = Path(__file__).resolve().parents[2]


def _page(module: str, assessment_id: str) -> AppTest:
    return AppTest.from_string(
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment_id!r}\n"
        f"from ai_adoption_engine.presentation.pages.{module} import render\n"
        "render()",
        default_timeout=60,
    ).run()


def test_assessment_creation_acknowledgement_and_record_actions_are_unchanged(
    tmp_path, monkeypatch
) -> None:
    database = tmp_path / "assessments.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(database))
    repository = SQLiteAssessmentRepository(database)

    app = AppTest.from_string(
        "from ai_adoption_engine.presentation.pages.assessments import render\nrender()",
        default_timeout=30,
    ).run()
    app.text_input[0].input("Acknowledgement gate")
    app = app.button(
        key="FormSubmitter:new-assessment-Create assessment"
    ).click().run()

    assert any(
        "Acknowledge the local-storage notice" in item.value for item in app.error
    )
    assert repository.list_assessments() == []

    assessment = repository.create_assessment(
        "Saved record", ExecutionMode.OFFLINE_DEMO
    )
    app = AppTest.from_string(
        "from ai_adoption_engine.presentation.pages.assessments import render\nrender()",
        default_timeout=30,
    ).run()

    rendered = "\n".join(item.value for item in app.markdown)
    captions = "\n".join(item.value for item in app.caption)
    assert "Saved record" in rendered
    assert "Created " in captions
    assert assessment.assessment_id in captions
    assert any(item.label == "Open" for item in app.button)
    app = app.button(key=f"open-{assessment.assessment_id}").click().run()
    assert app.session_state["selected_assessment_id"] == assessment.assessment_id
    delete = next(item for item in app.button if item.label == "Delete permanently")
    assert delete.disabled
    app = app.checkbox(key=f"delete-confirm-{assessment.assessment_id}").check().run()
    delete = app.button(key=f"delete-{assessment.assessment_id}")
    assert not delete.disabled
    app = delete.click().run()
    assert not app.exception
    assert repository.list_assessments() == []


def test_open_saved_assessment_navigates_to_source_and_extraction(
    tmp_path, monkeypatch
) -> None:
    database = tmp_path / "open-assessment.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(database))
    assessment = SQLiteAssessmentRepository(database).create_assessment(
        "Saved record", ExecutionMode.OFFLINE_DEMO
    )

    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    app = app.button(key=f"open-{assessment.assessment_id}").click().run()

    assert not app.exception
    assert app.session_state["selected_assessment_id"] == assessment.assessment_id
    assert app.title[0].value == "Source & Extraction"


def test_source_keeps_three_stages_and_disclosures_without_metric_tiles(
    tmp_path, monkeypatch
) -> None:
    database = tmp_path / "source.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(database))
    repository = SQLiteAssessmentRepository(database)
    assessment = repository.create_assessment(
        "Source stages", ExecutionMode.OFFLINE_DEMO
    )

    app = _page("source", assessment.assessment_id)
    assert [item.value for item in app.subheader] == [
        "1. Document input",
        "2. Ingestion result",
        "3. Candidate process extraction",
    ]
    assert not app.metric

    service = build_workspace_service(database)
    service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    service.extract(assessment.assessment_id)
    app = _page("source", assessment.assessment_id)

    assert not app.exception
    assert not app.metric
    assert any(
        item.value == "CANDIDATE / UNCONFIRMED PROCESS EXTRACTION"
        for item in app.warning
    )
    assert any(item.label == "Start process validation" for item in app.button)


def test_validate_process_keeps_actions_order_and_disabled_approval_gate(
    tmp_path, monkeypatch
) -> None:
    database = tmp_path / "review.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(database))
    repository = SQLiteAssessmentRepository(database)
    assessment = repository.create_assessment(
        "Review rows", ExecutionMode.OFFLINE_DEMO
    )
    service = build_workspace_service(database)
    service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    service.extract(assessment.assessment_id)
    session = service.start_review(assessment.assessment_id)

    app = _page("review", assessment.assessment_id)
    assert not app.exception
    assert not app.metric
    assert {item.value for item in app.caption} >= {
        "Outstanding",
        "Complete",
        "Remaining",
    }
    assert not [item for item in app.selectbox if item.key == "selected-review-step"]
    assert len([item for item in app.button if item.label == "Review activity"]) == (
        len(session.steps) - 1
    )
    action = next(
        item for item in app.selectbox if item.label == "Review decision for Activity"
    )
    assert {"Accept", "Correct", "Reject"}.issubset(action.options)
    assert any(item.label == "Accept current step order" for item in app.button)
    approval = next(
        item for item in app.button if item.label == "Approve current-state process"
    )
    assert approval.disabled
    assert any(item.value == "Final approval" for item in app.header)

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ai_adoption_engine.grw.models import GrwReviewDecision
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.workspace.composition import extraction_service_for
from ai_adoption_engine.workspace.demo_extraction import demo_text
from ai_adoption_engine.workspace.models import ExecutionMode
from ai_adoption_engine.workspace.service import AssessmentWorkspaceService


ROOT = Path(__file__).resolve().parents[2]


def _ready_page(tmp_path, monkeypatch):
    path = tmp_path / "grw-ui.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    repository = SQLiteAssessmentRepository(path)
    service = AssessmentWorkspaceService(repository, extraction_service_factory=extraction_service_for)
    assessment = repository.create_assessment("GRW UI", ExecutionMode.OFFLINE_DEMO)
    service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    service.extract(assessment.assessment_id)
    review = service.start_review(assessment.assessment_id)
    service.review_service.accept_assertion(review, review.process_name, "process.name")
    for step in review.steps:
        service.review_service.accept_assertion(
            review, step.activity, f"steps.{step.candidate_step_id}.activity"
        )
    service.review_service.accept_step_order(review)
    service.save_review(assessment.assessment_id, review)
    assert service.approve(assessment.assessment_id).approved is not None
    assert service.assess(assessment.assessment_id).status == "success"
    assert service.generate_package(assessment.assessment_id).status == "success"
    script = (
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment.assessment_id!r}\n"
        "from ai_adoption_engine.presentation.pages.gap_resolution import render\n"
        "render()\n"
    )
    return AppTest.from_string(script, default_timeout=30).run(), service, assessment.assessment_id


def _rendered(app) -> str:
    return "\n".join(
        str(item.value)
        for kind in ("title", "markdown", "caption", "info", "warning", "text", "success")
        for item in app.get(kind)
    )


def test_grw_page_shows_one_optional_question_without_upload_controls(tmp_path, monkeypatch) -> None:
    app, _, _ = _ready_page(tmp_path, monkeypatch)
    assert not app.exception
    rendered = _rendered(app)
    assert "Your current information is enough for an initial assessment." in rendered
    assert "continue with the current recommendation" in rendered
    assert "Baseline recommendation for this activity:" in rendered
    assert "existing; unchanged by Gap resolution" in rendered
    assert len(app.text_area) == 1
    assert "A rough range is okay" in rendered
    assert not app.file_uploader


@pytest.mark.parametrize(
    ("review_label", "expected_effect", "expected_outcome"),
    [
        (
            "Accept as preliminary understanding",
            "PRELIMINARY_UNDERSTANDING",
            "This estimate provides preliminary understanding of workload.",
        ),
        (
            "Accept as recorded only",
            "RECORDED_ONLY",
            "This answer is retained for audit and later discussion only.",
        ),
        ("Reject", "NONE", "The response was rejected and is not an assessment input."),
    ],
)
def test_grw_page_preserves_answer_and_renders_reviewed_non_change_status(
    tmp_path, monkeypatch, review_label, expected_effect, expected_outcome
) -> None:
    app, _, assessment_id = _ready_page(tmp_path, monkeypatch)
    answer = "Usually around 18,000–22,000 tickets per month."
    app = app.text_area[0].input(answer).run()
    app = next(item for item in app.button if item.label == "Submit answer").click().run()
    assert not app.exception
    rendered = _rendered(app)
    assert answer in rendered
    assert "OPERATOR_PROVIDED_ESTIMATE" in rendered
    assert "Parsed range candidate only" in rendered
    app = app.text_input[0].input("UI reviewer").run()
    app = app.text_area[0].input("Useful workload context only.").run()
    app = app.selectbox[0].select(review_label).run()
    app = next(item for item in app.button if item.label == "Record review").click().run()
    assert not app.exception
    rendered = _rendered(app)
    assert expected_effect in rendered
    assert expected_outcome in rendered
    assert "This information has not changed the formal assessment or recommendation." in rendered
    assert "To strengthen the evidence basis, you could provide a relevant reviewed" in rendered
    assert "may support a future formal reassessment only if it is admissible under an approved" in rendered
    for statement in (
        "Criterion: unchanged",
        "Assessment gates: unchanged",
        "Recommendation: unchanged",
        "Priority: unchanged",
        "ROI: unchanged",
        "Decision Package: unchanged",
    ):
        assert statement in rendered
    assert "No successor assessment or Decision Package was generated." in rendered

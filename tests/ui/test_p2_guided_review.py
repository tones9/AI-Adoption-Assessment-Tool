from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from streamlit.testing.v1 import AppTest

from ai_adoption_engine.workspace.composition import build_workspace_service
from ai_adoption_engine.workspace.demo_extraction import demo_text
from ai_adoption_engine.workspace.models import ArtifactType, ExecutionMode


ROOT = Path(__file__).resolve().parents[2]


def _review_workspace(path: Path):
    service = build_workspace_service(path)
    assessment = service.repository.create_assessment("P2 guided UI", ExecutionMode.OFFLINE_DEMO)
    service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    service.extract(assessment.assessment_id)
    service.start_review(assessment.assessment_id)
    return assessment.assessment_id


def _review_app(assessment_id: str) -> AppTest:
    return AppTest.from_string(
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment_id!r}\n"
        "from ai_adoption_engine.presentation.pages.review import render\n"
        "render()",
        default_timeout=30,
    )


def test_guided_review_renders_required_sections_and_preserves_unknowns(tmp_path, monkeypatch) -> None:
    path = tmp_path / "guided.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    assessment_id = _review_workspace(path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    app = _review_app(assessment_id).run()

    assert not app.exception
    headers = [item.value for item in app.header]
    for label in (
        "Review summary",
        "Needs your decision",
        "What the document says",
        "Unknown or not provided",
        "Dependencies and structural issues",
        "Recommended checks",
        "Review more detail",
        "Ready for approval",
    ):
        assert label in headers
    rendered = "\n".join(
        str(item.value)
        for kind in ("markdown", "caption", "warning", "write")
        for item in app.get(kind)
    )
    assert "directly documented" in rendered.lower()
    assert "Unknown values remain explicitly unknown" in rendered
    assert "extraction suggestion" in rendered
    assert "does not approve AI adoption" in rendered
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_guided_review_is_read_only_and_hands_off_after_existing_approval(tmp_path, monkeypatch) -> None:
    path = tmp_path / "approved.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    assessment_id = _review_workspace(path)
    service = build_workspace_service(path)
    session = service.repository.load_workspace(assessment_id).active_artifacts[
        ArtifactType.REVIEW_SESSION
    ].payload
    service.review_service.accept_assertion(session, session.process_name, "process.name")
    for step in session.steps:
        service.review_service.accept_assertion(session, step.activity, f"steps.{step.candidate_step_id}.activity")
    service.review_service.accept_step_order(session)
    service.save_review(assessment_id, session)
    assert service.approve(assessment_id).approved is not None

    app = _review_app(assessment_id).run()

    assert not app.exception
    assert any("Current-state process explicitly approved" in item.value for item in app.success)
    assert any(button.label == "Open assessment results" for button in app.button)
    assert not any("Reset active workspace" in button.label for button in app.button)


def test_guided_review_resumes_from_persisted_phase4_state_after_a_new_session(tmp_path, monkeypatch) -> None:
    path = tmp_path / "resume.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    assessment_id = _review_workspace(path)
    service = build_workspace_service(path)
    session = service.repository.load_workspace(assessment_id).active_artifacts[
        ArtifactType.REVIEW_SESSION
    ].payload
    service.review_service.accept_assertion(session, session.process_name, "process.name")
    service.save_review(assessment_id, session)

    first = _review_app(assessment_id).run()
    reopened = _review_app(assessment_id).run()

    assert not first.exception and not reopened.exception
    assert next(item for item in first.metric if item.label == "Remaining").value == "8"
    assert next(item for item in reopened.metric if item.label == "Remaining").value == "8"
    assert reopened.session_state["guided_review_selected_item"] == (
        "step-order-unconfirmed:process.steps.order"
    )


def test_guided_queue_selection_is_a_transient_valid_work_item_bookmark(tmp_path, monkeypatch) -> None:
    path = tmp_path / "queue-selection.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    assessment_id = _review_workspace(path)
    service = build_workspace_service(path)
    session = service.repository.load_workspace(assessment_id).active_artifacts[
        ArtifactType.REVIEW_SESSION
    ].payload
    target = session.steps[-1]

    app = _review_app(assessment_id).run()
    app = app.button(key=f"open-outstanding-step-activity-unconfirmed:steps.{target.candidate_step_id}.activity").click().run()

    assert not app.exception
    assert app.session_state["guided_review_selected_item"] == (
        f"step-activity-unconfirmed:steps.{target.candidate_step_id}.activity"
    )
    assert app.selectbox(key="selected-review-step").value == target.candidate_step_id


def test_protected_review_hides_phase4_write_controls(tmp_path, monkeypatch) -> None:
    ordinary = tmp_path / "ordinary.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(ordinary))
    assessment_id = _review_workspace(ordinary)
    protected = tmp_path / "evaluation" / "portfolio" / "PORT-004" / "workspace.db"
    protected.parent.mkdir(parents=True)
    shutil.copy2(ordinary, protected)
    before = hashlib.sha256(protected.read_bytes()).hexdigest()
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(protected))

    app = _review_app(assessment_id).run()

    assert not app.exception
    assert any("frozen evaluation record" in item.value for item in app.info)
    assert not any(button.label == "Apply review action" for button in app.button)
    assert not any(button.label == "Approve current-state process" for button in app.button)
    assert hashlib.sha256(protected.read_bytes()).hexdigest() == before


def test_protected_source_hides_process_validation_start_control(tmp_path, monkeypatch) -> None:
    ordinary = tmp_path / "source-ordinary.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(ordinary))
    service = build_workspace_service(ordinary)
    assessment = service.repository.create_assessment("Protected source", ExecutionMode.OFFLINE_DEMO)
    service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    service.extract(assessment.assessment_id)
    protected = tmp_path / "evaluation" / "portfolio" / "PORT-004" / "source.db"
    protected.parent.mkdir(parents=True)
    shutil.copy2(ordinary, protected)
    before = hashlib.sha256(protected.read_bytes()).hexdigest()
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(protected))

    app = AppTest.from_string(
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment.assessment_id!r}\n"
        "from ai_adoption_engine.presentation.pages.source import render\n"
        "render()",
        default_timeout=30,
    ).run()

    assert not app.exception
    assert any("frozen evaluation record" in item.value for item in app.info)
    assert not any(button.label == "Start process validation" for button in app.button)
    assert hashlib.sha256(protected.read_bytes()).hexdigest() == before

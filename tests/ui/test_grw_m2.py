from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from tests.fakes.m2_reassessment import package_ready_m2_baseline


def _rendered(app) -> str:
    return "\n".join(str(item.value) for kind in ("title", "markdown", "caption", "info", "warning", "text") for item in app.get(kind))


def test_m2_page_shows_baseline_and_one_document_question(tmp_path, monkeypatch) -> None:
    repository, assessment_id = package_ready_m2_baseline(tmp_path)
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(repository.path))
    app = AppTest.from_string(
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment_id!r}\n"
        "from ai_adoption_engine.presentation.pages.reassessment import render\n"
        "render()\n",
        default_timeout=30,
    ).run()
    assert not app.exception
    rendered = _rendered(app)
    assert "baseline Decision Package remains active" in rendered
    assert "What information is documented about the data available" in rendered
    assert "Baseline recommendation:" in rendered
    assert not app.file_uploader
    app = next(button for button in app.button if button.label == "Open reassessment").click().run()
    assert not app.exception
    assert len(app.file_uploader) == 1
    rendered = _rendered(app)
    assert "only M2 M1 intake type" in rendered


def test_m2_review_ui_exposes_review_and_conflict_decisions() -> None:
    source = (Path(__file__).resolve().parents[2] / "src" / "ai_adoption_engine" / "presentation" / "pages" / "reassessment.py").read_text(encoding="utf-8")
    assert "Evidence-review outcome" in source
    assert "Relationship to baseline evidence" in source
    assert "M2EvidencePermission(outcome)" in source
    assert "M2ConflictStatus(conflict)" in source
    assert "No material conflict recorded" not in source


def _open_submitted_m2_page(tmp_path, monkeypatch):
    repository, assessment_id = package_ready_m2_baseline(tmp_path)
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(repository.path))
    app = AppTest.from_string(
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment_id!r}\n"
        "from ai_adoption_engine.presentation.pages.reassessment import render\n"
        "render()",
        default_timeout=30,
    ).run()
    app = next(button for button in app.button if button.label == "Open reassessment").click().run()
    app.file_uploader[0].set_value(("support.txt", b"Target fields and authorised access.", "text/plain"))
    app.text_input(key="grw-m2-source").set_value("owner")
    app.text_input(key="grw-m2-submitter").set_value("submitter")
    return next(button for button in app.button if button.label == "Submit supporting document").click().run()


def _complete_review_form(app, *, outcome: str, conflict: str):
    app.text_input(key="grw-m2-reviewer").set_value("reviewer")
    app.text_input(key="grw-m2-scope").set_value("same activity")
    app.text_input(key="grw-m2-period").set_value("current")
    app.text_input(key="grw-m2-authority").set_value("owner")
    app.text_area(key="grw-m2-rationale").set_value("manual semantic review")
    app.text_area(key="grw-m2-limitations").set_value("limitations remain")
    app.selectbox(key="grw-m2-evidence-outcome").set_value(outcome)
    app.selectbox(key="grw-m2-conflict-status").set_value(conflict)
    app.text_area(key="grw-m2-conflict-rationale").set_value("reviewed relationship")
    return next(button for button in app.button if button.label == "Record document evidence review").click().run()


def test_m2_ui_records_accepted_and_rejected_review_paths(tmp_path, monkeypatch) -> None:
    accepted = _complete_review_form(_open_submitted_m2_page(tmp_path / "accepted", monkeypatch), outcome="CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE", conflict="CONSISTENT")
    assert not accepted.exception
    assert any(item.key == "grw-m2-value" for item in accepted.selectbox)
    rejected = _complete_review_form(_open_submitted_m2_page(tmp_path / "rejected", monkeypatch), outcome="REJECTED", conflict="CONSISTENT")
    assert not rejected.exception
    assert "complete or stopped" in _rendered(rejected)


def test_m2_ui_records_insufficient_and_conflict_review_paths(tmp_path, monkeypatch) -> None:
    insufficient = _complete_review_form(_open_submitted_m2_page(tmp_path / "insufficient", monkeypatch), outcome="INSUFFICIENT_FOR_THIS_USE", conflict="CONSISTENT")
    assert not insufficient.exception
    assert "complete or stopped" in _rendered(insufficient)
    conflict = _complete_review_form(_open_submitted_m2_page(tmp_path / "conflict", monkeypatch), outcome="CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE", conflict="CONTRADICTORY")
    assert not conflict.exception
    assert any(item.key == "grw-m2-value" for item in conflict.selectbox)

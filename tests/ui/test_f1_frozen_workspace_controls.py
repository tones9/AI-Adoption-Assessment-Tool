from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from streamlit.testing.v1 import AppTest

from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.workspace.models import ArtifactType, ExecutionMode, WorkflowStage
from tests.fakes.decision_support import sample_integrated_assessment
from tests.fakes.review import approved_review


def _protected_copy(source: Path, tmp_path: Path, name: str) -> Path:
    protected = tmp_path / "evaluation" / "portfolio" / "PORT-F1" / name
    protected.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, protected)
    return protected


def _selected_page(module: str, assessment_id: str) -> AppTest:
    return AppTest.from_string(
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment_id!r}\n"
        f"from ai_adoption_engine.presentation.pages.{module} import render\n"
        "render()",
        default_timeout=30,
    )


def test_protected_assessments_page_offers_open_but_not_create_or_delete(
    tmp_path: Path, monkeypatch
) -> None:
    ordinary = tmp_path / "ordinary.db"
    repository = SQLiteAssessmentRepository(ordinary)
    assessment = repository.create_assessment(
        "Protected UI", ExecutionMode.OFFLINE_DEMO
    )
    protected = _protected_copy(ordinary, tmp_path, "assessments.db")
    before = hashlib.sha256(protected.read_bytes()).hexdigest()
    entries = tuple(sorted(item.name for item in protected.parent.iterdir()))
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(protected))

    app = AppTest.from_string(
        "from ai_adoption_engine.presentation.pages.assessments import render\nrender()",
        default_timeout=30,
    ).run()

    assert not app.exception
    assert any("frozen evaluation workspace" in item.value for item in app.info)
    assert any(button.label == "Open" for button in app.button)
    assert not any(button.label == "Create assessment" for button in app.button)
    assert not any(button.label == "Delete permanently" for button in app.button)
    assert assessment.assessment_id in {button.key.removeprefix("open-") for button in app.button if button.key}
    assert hashlib.sha256(protected.read_bytes()).hexdigest() == before
    assert tuple(sorted(item.name for item in protected.parent.iterdir())) == entries


def test_protected_results_and_package_pages_hide_generation_controls(
    tmp_path: Path, monkeypatch
) -> None:
    ordinary = tmp_path / "ordinary-results.db"
    repository = SQLiteAssessmentRepository(ordinary)
    assessment = repository.create_assessment(
        "Protected generation", ExecutionMode.OFFLINE_DEMO
    )
    approved = approved_review()
    approval_ref = repository.save_artifact_and_advance(
        assessment.assessment_id,
        ArtifactType.APPROVED_REVIEW,
        approved,
        artifact_schema_version="phase4-v0.1",
        stage=WorkflowStage.APPROVED,
    )
    results_path = _protected_copy(ordinary, tmp_path, "results.db")
    results_before = hashlib.sha256(results_path.read_bytes()).hexdigest()
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(results_path))

    results_app = _selected_page("results", assessment.assessment_id).run()

    assert not results_app.exception
    assert any("frozen evaluation workspace" in item.value for item in results_app.info)
    assert not any(
        button.label == "Run AI-adoption assessment" for button in results_app.button
    )
    assert hashlib.sha256(results_path.read_bytes()).hexdigest() == results_before

    integrated = sample_integrated_assessment()
    repository.save_artifact_and_advance(
        assessment.assessment_id,
        ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
        integrated,
        artifact_schema_version="phase5-v0.1",
        stage=WorkflowStage.ASSESSED,
        parent_artifact_id=approval_ref.artifact_id,
    )
    package_path = _protected_copy(ordinary, tmp_path, "package.db")
    package_before = hashlib.sha256(package_path.read_bytes()).hexdigest()
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(package_path))

    package_app = _selected_page("decision_package", assessment.assessment_id).run()

    assert not package_app.exception
    assert any("frozen evaluation workspace" in item.value for item in package_app.info)
    assert not any(
        button.label == "Generate decision package" for button in package_app.button
    )
    assert hashlib.sha256(package_path.read_bytes()).hexdigest() == package_before

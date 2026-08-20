"""UI coverage for the Decision Continuation Workspace."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path

from streamlit.testing.v1 import AppTest
from streamlit.util import calc_hash

from ai_adoption_engine.grw.m2.service import M2ReassessmentService
from ai_adoption_engine.grw.m2.models import (
    M2ConflictStatus,
    M2DocumentLocator,
    M2EvidencePermission,
)
from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.persistence.reassessment import SQLiteReassessmentRepository
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.workspace.composition import extraction_service_for
from ai_adoption_engine.workspace.demo_extraction import demo_text
from ai_adoption_engine.workspace.models import ExecutionMode
from ai_adoption_engine.workspace.service import AssessmentWorkspaceService
from tests.fakes.m2_reassessment import package_ready_m2_baseline
from tests.integration.test_grw_m2_m1_lifecycle import _actor


def _rendered(app) -> str:
    return "\n".join(
        str(item.value)
        for kind in ("title", "subheader", "markdown", "caption", "info", "warning", "text")
        for item in app.get(kind)
    )


def _dcw_app(assessment_id: str) -> AppTest:
    return AppTest.from_string(
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment_id!r}\n"
        "from ai_adoption_engine.presentation.pages.decision_continuation import render\n"
        "render()\n",
        default_timeout=30,
    ).run()


def _package_ready_m1_baseline(tmp_path):
    database = SQLiteAssessmentRepository(tmp_path / "dcw-m1.db")
    workspace = AssessmentWorkspaceService(
        database, extraction_service_factory=extraction_service_for
    )
    assessment = database.create_assessment("DCW M1", ExecutionMode.OFFLINE_DEMO)
    workspace.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    workspace.extract(assessment.assessment_id)
    review = workspace.start_review(assessment.assessment_id)
    workspace.review_service.accept_assertion(review, review.process_name, "process.name")
    for step in review.steps:
        workspace.review_service.accept_assertion(
            review, step.activity, f"steps.{step.candidate_step_id}.activity"
        )
    workspace.review_service.accept_step_order(review)
    workspace.save_review(assessment.assessment_id, review)
    assert workspace.approve(assessment.assessment_id).approved is not None
    assert workspace.assess(assessment.assessment_id).status == "success"
    assert workspace.generate_package(assessment.assessment_id).status == "success"
    return database, assessment.assessment_id


def _package_ready_m2_successor_without_comparison(tmp_path):
    repository, assessment_id = package_ready_m2_baseline(tmp_path)
    service = M2ReassessmentService(
        repository, SQLiteReassessmentRepository(repository.path)
    )
    run_id, _, _ = service.create_run(assessment_id)
    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "m2_data_readiness_supporting_document.txt"
    )
    payload = fixture.read_bytes()
    text = payload.decode("utf-8")
    service.submit_supporting_document(
        run_id,
        content_bytes=payload,
        filename=fixture.name,
        source_label="Synthetic service operations manager",
        submitter=_actor("submitter"),
    )
    service.review_document_evidence(
        run_id,
        reviewer=_actor(),
        locator=M2DocumentLocator(
            start_offset=0,
            end_offset=len(text),
            line_start=1,
            line_end=text.count("\n", 0, len(text)) + 1,
            exact_excerpt=text,
        ),
        scope_statement="The document covers the selected categorisation activity.",
        period_statement="January 2025 onward.",
        source_authority="Synthetic service operations manager",
        semantic_rationale="The fields, access and limits support the M2 M1 instrument anchor.",
        limitations="Text quality limitations remain.",
        conflict_status=M2ConflictStatus.CONSISTENT,
        conflict_rationale="No material conflict identified.",
        permission=M2EvidencePermission.CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE,
    )
    service.propose_data_readiness_resolution(
        run_id,
        proposed_value=3,
        proposed_knowledge_state=KnowledgeState.KNOWN,
        mapping_rationale="The document meets anchor 3; limitations remain explicit.",
        data_owner=_actor("owner"),
        criterion_reviewer=_actor("criterion reviewer"),
    )
    service.request_reassessment(run_id)
    service.approve_reassessment(
        run_id,
        approver=_actor("approver"),
        rationale="The exact M2 M1 resolution is approved for a separate successor.",
    )
    service.build_successor_review(run_id)
    service.assess_successor(run_id)
    service.generate_successor_package(run_id)
    return repository, assessment_id, run_id


def test_dcw_page_shows_active_baseline_and_m2_route_without_lifecycle_controls(
    tmp_path, monkeypatch
) -> None:
    repository, assessment_id = package_ready_m2_baseline(tmp_path)
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(repository.path))

    app = _dcw_app(assessment_id)

    assert not app.exception
    rendered = _rendered(app)
    assert "Current formal decision" in rendered
    assert "active formal baseline" in rendered
    assert "Controlled formal reassessment" in rendered
    assert "This is the existing M2 M1 data-readiness route" in rendered
    assert "InformationGap" not in rendered
    assert not app.file_uploader
    assert not any("approve" in button.label.lower() for button in app.button)
    assert not any(
        button.label
        in {
            "Record document evidence review",
            "Record reviewed criterion resolution",
            "Run Phase 5 successor assessment",
            "Generate Phase 6 successor Decision Package",
        }
        for button in app.button
    )


def test_dcw_page_shows_existing_m1_as_non_decision_route(tmp_path, monkeypatch) -> None:
    repository, assessment_id = _package_ready_m1_baseline(tmp_path)
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(repository.path))

    app = _dcw_app(assessment_id)

    assert not app.exception
    rendered = _rendered(app)
    assert "Improve preliminary understanding" in rendered
    assert "Optional context only — no formal decision change" in rendered
    assert "Controlled formal reassessment" not in rendered


def test_dcw_discovers_persisted_run_in_a_fresh_streamlit_session(tmp_path, monkeypatch) -> None:
    repository, assessment_id = package_ready_m2_baseline(tmp_path)
    M2ReassessmentService(
        repository, SQLiteReassessmentRepository(repository.path)
    ).create_run(assessment_id)
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(repository.path))

    app = _dcw_app(assessment_id)

    assert not app.exception
    assert any(button.label == "Resume controlled reassessment" for button in app.button)
    assert "Separate reassessment run:" in _rendered(app)


def test_dcw_terminal_run_is_inspectable_but_not_resumable(tmp_path, monkeypatch) -> None:
    repository, assessment_id = package_ready_m2_baseline(tmp_path)
    run_id, _, _ = M2ReassessmentService(
        repository, SQLiteReassessmentRepository(repository.path)
    ).create_run(assessment_id)
    connection = sqlite3.connect(repository.path)
    connection.execute("UPDATE reassessment_runs SET stage='STALE' WHERE run_id=?", (run_id,))
    connection.commit()
    connection.close()
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(repository.path))

    app = _dcw_app(assessment_id)

    assert not app.exception
    assert "inspection only" in _rendered(app)
    assert not any(button.label == "Resume controlled reassessment" for button in app.button)


def test_dcw_shows_history_but_no_resume_when_current_m2_route_is_unavailable(
    tmp_path, monkeypatch
) -> None:
    repository, assessment_id = package_ready_m2_baseline(tmp_path)
    M2ReassessmentService(
        repository, SQLiteReassessmentRepository(repository.path)
    ).create_run(assessment_id)
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(repository.path))
    monkeypatch.setattr(M2ReassessmentService, "open_m2_m1_context", lambda *_: None)

    app = _dcw_app(assessment_id)

    assert not app.exception
    rendered = _rendered(app)
    assert "Existing reassessment records remain available for inspection" in rendered
    assert "Separate reassessment run:" in rendered
    assert not any(button.label == "Resume controlled reassessment" for button in app.button)


def test_dcw_shows_package_ready_successor_when_comparison_is_not_available(
    tmp_path, monkeypatch
) -> None:
    repository, assessment_id, run_id = _package_ready_m2_successor_without_comparison(
        tmp_path
    )
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(repository.path))

    app = _dcw_app(assessment_id)

    assert not app.exception
    rendered = _rendered(app)
    assert f"Separate M2 successor for run {run_id}" in rendered
    assert "baseline-versus-successor comparison is not available" in rendered
    assert "Current formal decision" in rendered


def test_dcw_protected_workspace_shows_immutable_baseline_without_grw_routes(
    tmp_path, monkeypatch
) -> None:
    source_repository, assessment_id = package_ready_m2_baseline(tmp_path / "source")
    protected = (
        tmp_path
        / "evaluation"
        / "portfolio"
        / "runs"
        / "synthetic"
        / "workspace.db"
    )
    protected.parent.mkdir(parents=True)
    shutil.copy2(source_repository.path, protected)
    before = hashlib.sha256(protected.read_bytes()).hexdigest()
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(protected))

    app = _dcw_app(assessment_id)

    assert not app.exception
    rendered = _rendered(app)
    assert "immutable evaluation baseline" in rendered
    assert "Controlled formal reassessment" not in rendered
    assert hashlib.sha256(protected.read_bytes()).hexdigest() == before


def test_dcw_package_entry_and_m2_return_control_are_available_in_native_navigation(
    tmp_path, monkeypatch
) -> None:
    repository, assessment_id = package_ready_m2_baseline(tmp_path)
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(repository.path))
    root = Path(__file__).resolve().parents[2]
    app = AppTest.from_file(root / "streamlit_app.py", default_timeout=30)
    app.session_state["selected_assessment_id"] = assessment_id
    app._page_hash = calc_hash("decision-package")
    app.run()

    app = next(button for button in app.button if button.label == "Continue decision").click().run()
    assert not app.exception
    assert app.title[0].value == "Decision continuation"
    open_m2 = next(
        button for button in app.button if button.label == "Open controlled reassessment"
    )
    assert not open_m2.disabled
    # Re-open the registered target as a fresh browser/page render. AppTest
    # retains its explicitly assigned initial page hash after chained switches.
    app._page_hash = calc_hash("reassessment")
    app.run()
    assert app.title[0].value == "Reassess with supporting document"
    assert any(
        button.label == "Return to decision continuation" for button in app.button
    )

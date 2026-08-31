from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from streamlit.testing.v1 import AppTest

from ai_adoption_engine.models.candidate_process import (
    CandidateAssertion,
    CandidateDependency,
)
from ai_adoption_engine.presentation.review_progress import build_review_progress
from ai_adoption_engine.workspace.composition import build_workspace_service
from ai_adoption_engine.workspace.demo_extraction import demo_text
from ai_adoption_engine.workspace.models import (
    ArtifactType,
    ExecutionMode,
    WorkflowStage,
)


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
    headers = [item.value for item in [*app.header, *app.subheader]]
    for label in (
        "Review summary",
        "Review progress",
        "What the document says",
        "Unknown or not provided",
        "Dependencies and structural issues",
        "Recommended checks",
        "Assertion review",
        "Final approval",
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
    assert [item.value for item in first.markdown].count("### 8") >= 2
    assert [item.value for item in reopened.markdown].count("### 8") >= 2
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
    assert app.session_state["selected-review-step"] == target.candidate_step_id


def test_rejecting_loop_activity_removes_its_dependency_blocker_across_reopen(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "loop-activity.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    service = build_workspace_service(path)
    assessment = service.repository.create_assessment(
        "Loop activity UI", ExecutionMode.OFFLINE_DEMO
    )
    assessment_id = assessment.assessment_id
    service.ingest_upload(assessment_id, raw_text=demo_text())
    candidate = service.extract(assessment_id)
    loop_candidate = candidate.candidate.steps[-1]
    loop_candidate.activity.value = "Loop continues"
    dependency = CandidateDependency(
        target_label=CandidateAssertion[str](
            value="Steps 4 to 7",
            knowledge_state="known",
            rationale="The source describes the repeated range.",
            evidence=loop_candidate.activity.evidence,
        ),
        relationship=CandidateAssertion[str](
            value="repeat for each item",
            knowledge_state="known",
            rationale="The source describes loop control.",
            evidence=loop_candidate.activity.evidence,
        ),
    )
    loop_candidate.dependencies.append(dependency)
    candidate_ref = service.repository.load_workspace(assessment_id).active_artifacts[
        ArtifactType.CANDIDATE_EXTRACTION_RESULT
    ]
    service.repository.save_artifact_and_advance(
        assessment_id,
        ArtifactType.CANDIDATE_EXTRACTION_RESULT,
        candidate,
        artifact_schema_version="phase3-v0.1",
        stage=WorkflowStage.CANDIDATE_READY,
        parent_artifact_id=candidate_ref.parent_artifact_id,
    )
    session = service.start_review(assessment_id)
    loop_step = session.steps[-1]
    assert loop_step.activity.value == "Loop continues"
    assert len(loop_step.dependencies) == 1
    service.review_service.accept_assertion(
        session, session.process_name, "process.name"
    )
    for step in session.steps:
        if step.candidate_step_id != loop_step.candidate_step_id:
            service.review_service.accept_assertion(
                session,
                step.activity,
                f"steps.{step.candidate_step_id}.activity",
            )
    service.review_service.accept_step_order(session)
    service.save_review(assessment_id, session)

    before = build_review_progress(session)
    assert before.remaining_required == 2
    assert {item.field_label for item in before.outstanding} == {
        "Activity",
        "Dependency",
    }

    app = _review_app(assessment_id).run()
    activity_path = f"steps.{loop_step.candidate_step_id}.activity"
    action = next(
        item
        for item in app.selectbox
        if item.key and item.key.startswith(f"action-{activity_path}-")
    )
    assert "Reject/remove step" in action.options
    app = action.select("Reject/remove step").run()
    rationale = next(
        item
        for item in app.text_input
        if item.key and item.key.startswith(f"rationale-{activity_path}-")
    )
    app = rationale.input("Loop control is not an independent activity.").run()
    apply_action = next(
        item
        for item in app.button
        if item.key and item.key.startswith(f"apply-{activity_path}-")
    )
    app = apply_action.click().run()

    persisted = service.repository.load_workspace(assessment_id).active_artifacts[
        ArtifactType.REVIEW_SESSION
    ].payload
    persisted_loop = next(
        step
        for step in persisted.steps
        if step.candidate_step_id == loop_step.candidate_step_id
    )
    after_removal = build_review_progress(persisted)
    assert persisted_loop.retained is False
    assert persisted_loop.dependencies[0].retained is True
    assert (
        persisted.events[-1].field_path
        == f"steps.{loop_step.candidate_step_id}"
    )
    assert after_removal.remaining_required == 1
    assert [item.field_path for item in after_removal.outstanding] == [
        "process.steps.order"
    ]

    accept_order = next(
        button for button in app.button if button.label == "Accept current step order"
    )
    app = accept_order.click().run()
    assert not app.exception
    assert any("Ready for approval" in item.value for item in app.success)
    confirmation = next(
        item
        for item in app.checkbox
        if item.label == "APPROVE CURRENT-STATE PROCESS"
    )
    app = confirmation.check().run()
    assert not next(
        button
        for button in app.button
        if button.label == "Approve current-state process"
    ).disabled

    rerun = app.run()
    reopened = _review_app(assessment_id).run()
    for current in (rerun, reopened):
        assert not current.exception
        assert any("Ready for approval" in item.value for item in current.success)
        confirmation = next(
            item
            for item in current.checkbox
            if item.label == "APPROVE CURRENT-STATE PROCESS"
        )
        current = confirmation.check().run()
        assert not next(
            button
            for button in current.button
            if button.label == "Approve current-state process"
        ).disabled
        rendered = "\n".join(
            str(item.value)
            for kind in ("markdown", "caption", "warning", "write")
            for item in current.get(kind)
        )
        assert "Loop continues → Activity" not in rendered
        assert "Loop continues → Dependency" not in rendered

    final_session = service.repository.load_workspace(assessment_id).active_artifacts[
        ArtifactType.REVIEW_SESSION
    ].payload
    assert build_review_progress(final_session).remaining_required == 0


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

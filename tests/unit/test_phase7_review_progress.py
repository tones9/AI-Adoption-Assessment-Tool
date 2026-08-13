from pathlib import Path

from ai_adoption_engine.presentation.review_progress import build_review_progress
from ai_adoption_engine.workspace.composition import build_workspace_service
from ai_adoption_engine.workspace.demo_extraction import demo_text
from ai_adoption_engine.workspace.models import ExecutionMode


def _demo_review(tmp_path: Path):
    service = build_workspace_service(tmp_path / "progress.db")
    assessment = service.repository.create_assessment(
        "Review progress", ExecutionMode.OFFLINE_DEMO
    )
    service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    service.extract(assessment.assessment_id)
    return service, service.start_review(assessment.assessment_id)


def test_progress_uses_actual_phase4_approval_requirements(tmp_path: Path) -> None:
    _, session = _demo_review(tmp_path)

    progress = build_review_progress(session)

    assert progress.total_required == 9
    assert progress.completed_required == 0
    assert progress.remaining_required == 9
    assert [item.field_path for item in progress.outstanding] == [
        "process.name",
        "process.steps.order",
        *(f"steps.{step.candidate_step_id}.activity" for step in session.steps),
    ]
    assert all("criteria" not in (item.field_path or "") for item in progress.outstanding)
    assert all(
        "capability_signals" not in (item.field_path or "")
        for item in progress.outstanding
    )


def test_progress_identifies_one_persisted_activity_blocker(tmp_path: Path) -> None:
    service, session = _demo_review(tmp_path)
    unresolved = session.steps[5]
    service.review_service.accept_assertion(session, session.process_name, "process.name")
    for step in session.steps:
        if step is unresolved:
            continue
        service.review_service.accept_assertion(
            session,
            step.activity,
            f"steps.{step.candidate_step_id}.activity",
        )
    service.review_service.accept_step_order(session)

    progress = build_review_progress(session)

    assert progress.total_required == 9
    assert progress.completed_required == 8
    assert progress.remaining_required == 1
    assert progress.outstanding[0].step_id == unresolved.candidate_step_id
    assert progress.outstanding[0].location_label.startswith(
        "Step 6 — Approve or return the proposed response"
    )
    assert progress.outstanding[0].field_label == "Activity"

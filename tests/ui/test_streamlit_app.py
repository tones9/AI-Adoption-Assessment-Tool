from pathlib import Path

from streamlit.testing.v1 import AppTest
from streamlit.util import calc_hash

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
from ai_adoption_engine.workspace.composition import build_workspace_service
from ai_adoption_engine.workspace.demo_extraction import demo_text
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
    assert "AI deployment roadmap not applicable." in rendered
    assert "does not claim legal compliance" in rendered
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


def test_start_human_review_button_persists_once_and_opens_same_review(
    tmp_path, monkeypatch
) -> None:
    from ai_adoption_engine.decision.engine import AssessmentEngine
    from ai_adoption_engine.extraction.providers.openai import OpenAIExtractionProvider

    def forbidden(*args, **kwargs):
        raise AssertionError("A review transition must not invoke OpenAI or assessment")

    monkeypatch.setattr(OpenAIExtractionProvider, "extract_chunk", forbidden)
    monkeypatch.setattr(AssessmentEngine, "assess", forbidden)

    path = tmp_path / "start-review.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    repository = SQLiteAssessmentRepository(path)
    assessment = repository.create_assessment(
        "Start review UAT", ExecutionMode.OFFLINE_DEMO
    )
    service = build_workspace_service(path)
    service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    service.extract(assessment.assessment_id)
    candidate_workspace = repository.load_workspace(assessment.assessment_id)
    candidate_ref = candidate_workspace.active_artifacts[
        ArtifactType.CANDIDATE_EXTRACTION_RESULT
    ]
    assert candidate_workspace.assessment.current_stage is WorkflowStage.CANDIDATE_READY

    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30)
    app.session_state["selected_assessment_id"] = assessment.assessment_id
    app._page_hash = calc_hash("source")
    app.run()
    assert app.title[0].value == "Source & Extraction"
    start = next(button for button in app.button if button.label == "Start human review")

    app = start.click().run()
    assert not app.exception
    assert app.title[0].value == "Process Review"
    assert any(
        "CANDIDATE / UNCONFIRMED" in warning.value for warning in app.warning
    )

    started = SQLiteAssessmentRepository(path).load_workspace(
        assessment.assessment_id
    )
    review_ref = started.active_artifacts[ArtifactType.REVIEW_SESSION]
    review_id = review_ref.payload.review_id
    assert started.assessment.current_stage is WorkflowStage.IN_REVIEW
    assert review_ref.parent_artifact_id == candidate_ref.artifact_id
    assert len(
        repository.list_artifact_revisions(
            assessment.assessment_id, ArtifactType.REVIEW_SESSION
        )
    ) == 1
    assert ArtifactType.APPROVED_REVIEW not in started.active_artifacts
    assert ArtifactType.INTEGRATED_ASSESSMENT_RESULT not in started.active_artifacts
    assert ArtifactType.DECISION_PACKAGE_RESULT not in started.active_artifacts

    app._page_hash = calc_hash("source")
    app.run()
    assert app.title[0].value == "Source & Extraction"
    assert not any(button.label == "Start human review" for button in app.button)
    open_review = next(
        button for button in app.button if button.label == "Open Process Review"
    )
    assert any(review_id in caption.value for caption in app.caption)

    app = open_review.click().run()
    assert not app.exception
    assert app.title[0].value == "Process Review"
    reopened = SQLiteAssessmentRepository(path).load_workspace(
        assessment.assessment_id
    )
    reopened_review = reopened.active_artifacts[ArtifactType.REVIEW_SESSION]
    assert reopened_review.artifact_id == review_ref.artifact_id
    assert reopened_review.payload.review_id == review_id
    assert len(
        repository.list_artifact_revisions(
            assessment.assessment_id, ArtifactType.REVIEW_SESSION
        )
    ) == 1


def test_approval_blockers_are_explicit_and_final_resolution_enables_approval(
    tmp_path, monkeypatch
) -> None:
    from ai_adoption_engine.decision.engine import AssessmentEngine
    from ai_adoption_engine.extraction.providers.openai import OpenAIExtractionProvider

    def forbidden(*args, **kwargs):
        raise AssertionError("Approval review must not invoke OpenAI or assessment")

    monkeypatch.setattr(OpenAIExtractionProvider, "extract_chunk", forbidden)
    monkeypatch.setattr(AssessmentEngine, "assess", forbidden)

    path = tmp_path / "approval-eligibility.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    repository = SQLiteAssessmentRepository(path)
    assessment = repository.create_assessment(
        "Approval eligibility UAT", ExecutionMode.OFFLINE_DEMO
    )
    service = build_workspace_service(path)
    service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    service.extract(assessment.assessment_id)
    session = service.start_review(assessment.assessment_id)
    service.review_service.accept_assertion(
        session,
        session.steps[1].activity,
        f"steps.{session.steps[1].candidate_step_id}.activity",
    )
    service.review_service.accept_step_order(session)
    service.save_review(assessment.assessment_id, session)

    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30)
    app.session_state["selected_assessment_id"] = assessment.assessment_id
    app._page_hash = calc_hash("review")
    app.run()
    assert not app.exception

    blocker = next(
        item.value for item in app.warning if "Approval blocked because" in item.value
    )
    assert "process name must be accepted or corrected" in blocker
    assert "Step 1 “Record the complaint”" in blocker
    assert "Step 3 “Review the categorised complaint”" in blocker
    assert "Step 7 “Send the response and close the case”" in blocker
    assert "Step 2 “Categorise complaint" not in blocker
    requirements = "\n".join(item.value for item in app.markdown)
    assert ":orange-badge[Incomplete] Process identity confirmed" in requirements
    assert ":orange-badge[Incomplete] Every retained step activity confirmed" in requirements
    assert ":green-badge[Complete] Step ordering accepted" in requirements
    confirmation = next(
        item
        for item in app.checkbox
        if item.label == "APPROVE CURRENT-STATE PROCESS"
    )
    approval_button = next(
        item
        for item in app.button
        if item.label == "Approve current-state process"
    )
    assert confirmation.disabled
    assert approval_button.disabled

    app.button(
        key="FormSubmitter:review-process.name-Apply review action"
    ).click().run()
    unreviewed_activity_buttons = [
        item.key
        for item in app.button
        if item.key
        and ".activity-Apply review action" in item.key
        and item.key
        != (
            "FormSubmitter:review-steps."
            f"{session.steps[1].candidate_step_id}.activity-Apply review action"
        )
    ]
    for key in unreviewed_activity_buttons:
        app.button(key=key).click().run()

    assert not app.exception
    assert any(
        "All structural approval requirements are complete" in item.value
        for item in app.success
    )
    confirmation = next(
        item
        for item in app.checkbox
        if item.label == "APPROVE CURRENT-STATE PROCESS"
    )
    assert not confirmation.disabled
    confirmation.check().run()
    approval_button = next(
        item
        for item in app.button
        if item.label == "Approve current-state process"
    )
    assert not approval_button.disabled
    next(
        item for item in app.text_input if item.label == "Optional approval rationale"
    ).input("The current-state process was reviewed during UAT.")
    approval_button.click().run()

    assert not app.exception
    assert any(
        "Current-state process explicitly approved" in item.value
        for item in app.success
    )
    approved = SQLiteAssessmentRepository(path).load_workspace(
        assessment.assessment_id
    )
    assert approved.assessment.current_stage is WorkflowStage.APPROVED
    assert ArtifactType.APPROVED_REVIEW in approved.active_artifacts
    assert ArtifactType.INTEGRATED_ASSESSMENT_RESULT not in approved.active_artifacts
    assert ArtifactType.DECISION_PACKAGE_RESULT not in approved.active_artifacts


def test_complete_offline_demo_ui_journey_persists_and_reopens_exact_chain(
    tmp_path, monkeypatch
) -> None:
    from ai_adoption_engine.extraction.providers.openai import OpenAIExtractionProvider

    def forbidden(*args, **kwargs):
        raise AssertionError("Offline Demo must never invoke OpenAI")

    monkeypatch.setattr(OpenAIExtractionProvider, "extract_chunk", forbidden)
    path = tmp_path / "complete-offline-uat.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))

    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    app.text_input[0].input("Complete Offline Demo UAT")
    app.checkbox[0].check()
    app.button(key="FormSubmitter:new-assessment-Create assessment").click().run()
    assessment_id = app.session_state["selected_assessment_id"]

    app._page_hash = calc_hash("source")
    app.run()
    next(item for item in app.button if item.label == "Ingest document").click().run()
    next(
        item for item in app.button if item.label == "Extract candidate process"
    ).click().run()
    next(
        item for item in app.button if item.label == "Start human review"
    ).click().run()

    repository = SQLiteAssessmentRepository(path)
    started = repository.load_workspace(assessment_id)
    assert started.assessment.current_stage is WorkflowStage.IN_REVIEW
    session = started.active_artifacts[ArtifactType.REVIEW_SESSION].payload
    service = build_workspace_service(path)
    service.review_service.accept_assertion(
        session, session.process_name, "process.name"
    )
    for step in session.steps:
        service.review_service.accept_assertion(
            session, step.activity, f"steps.{step.candidate_step_id}.activity"
        )
    service.review_service.retain_unknown(
        session,
        session.steps[0].criteria[0].assertion,
        f"steps.{session.steps[0].candidate_step_id}.criteria[0]",
        rationale="The source does not establish this assessment value.",
    )
    dependency_step = next(step for step in session.steps if step.dependencies)
    service.review_service.correct_dependency(
        session,
        dependency_step.candidate_step_id,
        0,
        dependency_step.dependencies[0].target_candidate_step_id,
        rationale="The reviewer confirmed the candidate dependency.",
    )
    service.review_service.accept_step_order(session)
    service.save_review(assessment_id, session)

    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30)
    app.session_state["selected_assessment_id"] = assessment_id
    app._page_hash = calc_hash("review")
    app.run()
    confirmation = next(
        item
        for item in app.checkbox
        if item.label == "APPROVE CURRENT-STATE PROCESS"
    )
    confirmation.check().run()
    next(
        item for item in app.text_input if item.label == "Optional approval rationale"
    ).input("Complete Offline Demo UAT approval.")
    next(
        item
        for item in app.button
        if item.label == "Approve current-state process"
    ).click().run()
    assert not app.exception

    app._page_hash = calc_hash("results")
    app.run()
    next(
        item for item in app.button if item.label == "Run AI-adoption assessment"
    ).click().run()
    assert not app.exception
    assert next(item for item in app.metric if item.label == "Activities assessed").value == "7"
    assert next(item for item in app.metric if item.label == "Investigate").value == "7"
    assert not app.error

    app._page_hash = calc_hash("decision-package")
    app.run()
    next(
        item for item in app.button if item.label == "Generate decision package"
    ).click().run()
    assert not app.exception
    rendered = "\n".join(
        str(item.value)
        for kind in ("markdown", "caption", "warning", "info", "subheader")
        for item in app.get(kind)
    )
    for marker in (
        "PROPOSED / NOT DEPLOYED",
        "GO / REVISE / STOP",
        "ROI / quantified benefit unavailable with current evidence.",
        "does not claim legal compliance",
    ):
        assert marker in rendered
    assert any(
        item.label == "Download print-friendly HTML report"
        for item in app.download_button
    )

    completed = repository.load_workspace(assessment_id)
    immutable_ids = {
        artifact_type: completed.active_artifacts[artifact_type].artifact_id
        for artifact_type in (
            ArtifactType.CANDIDATE_EXTRACTION_RESULT,
            ArtifactType.APPROVED_REVIEW,
            ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
            ArtifactType.DECISION_PACKAGE_RESULT,
        )
    }
    app.run()
    reopened_app = AppTest.from_file(
        ROOT / "streamlit_app.py", default_timeout=30
    ).run()
    next(item for item in reopened_app.button if item.label == "Open").click().run()
    reopened_app._page_hash = calc_hash("decision-package")
    reopened_app.run()
    assert not reopened_app.exception
    assert reopened_app.download_button

    reopened = SQLiteAssessmentRepository(path).load_workspace(assessment_id)
    assert reopened.assessment.current_stage is WorkflowStage.PACKAGE_READY
    assert all(
        reopened.active_artifacts[artifact_type].artifact_id == artifact_id
        for artifact_type, artifact_id in immutable_ids.items()
    )
    assert (
        reopened.active_artifacts[
            ArtifactType.INTEGRATED_ASSESSMENT_RESULT
        ].parent_artifact_id
        == reopened.active_artifacts[ArtifactType.APPROVED_REVIEW].artifact_id
    )
    assert (
        reopened.active_artifacts[
            ArtifactType.DECISION_PACKAGE_RESULT
        ].parent_artifact_id
        == reopened.active_artifacts[
            ArtifactType.INTEGRATED_ASSESSMENT_RESULT
        ].artifact_id
    )
    assert all(
        len(repository.list_artifact_revisions(assessment_id, artifact_type)) == 1
        for artifact_type in immutable_ids
    )

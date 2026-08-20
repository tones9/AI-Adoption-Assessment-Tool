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
from ai_adoption_engine.presentation.review_progress import (
    document_supported_unreviewed,
    inferred_unreviewed,
    iter_process_assertions,
    iter_step_assertions,
)
from ai_adoption_engine.workspace.composition import build_workspace_service
from ai_adoption_engine.workspace.demo_extraction import demo_text
from tests.fakes.decision_support import sample_integrated_assessment
from tests.fakes.review import approved_review


ROOT = Path(__file__).resolve().parents[2]


def test_app_starts_with_six_page_navigation(tmp_path, monkeypatch) -> None:
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
        "Gap resolution",
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


def _widget_with_key_prefix(widgets, prefix: str):
    return next(item for item in widgets if item.key and item.key.startswith(prefix))


def _apply_review_action(app: AppTest, field_path: str, action: str) -> AppTest:
    selector = _widget_with_key_prefix(app.selectbox, f"action-{field_path}-")
    app = selector.select(action).run()
    button = _widget_with_key_prefix(app.button, f"apply-{field_path}-")
    assert not button.disabled
    return button.click().run()


def _confirm_document_group(app: AppTest, key: str) -> AppTest:
    button = app.button(key=f"confirm-documented-{key}")
    assert not button.disabled
    return button.click().run()


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
    expander_labels = [item.label for item in app.expander]
    for opportunity in generated.package.portfolio.items:
        assert any(
            label.startswith(opportunity.current_activity)
            for label in expander_labels
        )
    subheaders = [item.value for item in app.subheader]
    assert subheaders.count("Methodology and policy disclosure") == 1
    assert "Methodology disclosure" not in subheaders
    assert rendered.count("Reason / basis:") == len(generated.package.portfolio.items)
    assert rendered.count("Material missing information:") == len(
        generated.package.portfolio.items
    )
    assert rendered.count("Next action:") == len(generated.package.portfolio.items)


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
    service.review_service.accept_assertion(session, session.process_name, "process.name")
    unresolved_step = session.steps[5]
    for step in session.steps:
        if step.candidate_step_id == unresolved_step.candidate_step_id:
            continue
        service.review_service.accept_assertion(
            session,
            step.activity,
            f"steps.{step.candidate_step_id}.activity",
        )
    service.review_service.accept_step_order(session)
    service.save_review(assessment.assessment_id, session)

    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30)
    app.session_state["selected_assessment_id"] = assessment.assessment_id
    app._page_hash = calc_hash("review")
    app.run()
    assert not app.exception

    metrics = {item.label: item.value for item in app.metric}
    assert metrics["Required items"] == "9"
    assert metrics["Complete"] == "8"
    assert metrics["Remaining"] == "1"
    assert any(
        "1 required item needs attention before approval" in item.value
        for item in app.warning
    )
    assert any(
        "Not ready for approval — 1 required item remains" in item.value
        for item in app.error
    )
    requirements = "\n".join(item.value for item in app.markdown)
    assert "Step 6 — Approve or return the proposed response → Activity" in requirements
    assert "Accept or correct this retained activity" in requirements
    assert "Step 5" not in "\n".join(
        item.value for item in app.markdown if "Accept or correct this retained activity" in item.value
    )
    assert not any(
        item.label == "APPROVE CURRENT-STATE PROCESS" for item in app.checkbox
    )
    approval_button = next(
        item
        for item in app.button
        if item.label == "Approve current-state process"
    )
    assert approval_button.disabled
    assert "Resolve the 1 required item listed immediately above" in approval_button.help

    # Refresh and reopen from durable SQLite state: the same exact blocker remains.
    app.run()
    reopened = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30)
    reopened.session_state["selected_assessment_id"] = assessment.assessment_id
    reopened._page_hash = calc_hash("review")
    app = reopened.run()
    assert not app.exception
    assert next(item for item in app.metric if item.label == "Remaining").value == "1"

    app = next(item for item in app.button if item.label == "Open step").click().run()
    assert app.selectbox(key="selected-review-step").value == unresolved_step.candidate_step_id
    assert any("Review attention requested here: Activity" in item.value for item in app.warning)
    app = _confirm_document_group(
        app, f"step-{unresolved_step.candidate_step_id}"
    )

    assert not app.exception
    assert any(
        "Ready for explicit approval" in item.value
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


def test_scoped_document_confirmation_reduces_demo_review_work_without_flattening_audit(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "scoped-confirmation.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    repository = SQLiteAssessmentRepository(path)
    assessment = repository.create_assessment(
        "Scoped confirmation UAT", ExecutionMode.OFFLINE_DEMO
    )
    service = build_workspace_service(path)
    service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    service.extract(assessment.assessment_id)
    session = service.start_review(assessment.assessment_id)

    all_targets = iter_process_assertions(session)
    for step in session.steps:
        all_targets.extend(iter_step_assertions(session, step.candidate_step_id))
    documented_count = len(document_supported_unreviewed(all_targets))
    assert len(all_targets) == 200
    assert documented_count == 52

    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30)
    app.session_state["selected_assessment_id"] = assessment.assessment_id
    app._page_hash = calc_hash("review")
    app.run()
    assert not app.exception
    metrics = {item.label: item.value for item in app.metric}
    assert metrics == {"Required items": "9", "Complete": "0", "Remaining": "9"}

    app = _confirm_document_group(app, "process")
    for step in session.steps:
        app = app.selectbox(key="selected-review-step").select(
            step.candidate_step_id
        ).run()
        app = _confirm_document_group(app, f"step-{step.candidate_step_id}")
    app = next(
        item for item in app.button if item.label == "Accept current step order"
    ).click().run()

    assert next(item for item in app.metric if item.label == "Remaining").value == "0"
    persisted = repository.load_active_artifact(
        assessment.assessment_id, ArtifactType.REVIEW_SESSION
    ).payload
    persisted_targets = iter_process_assertions(persisted)
    for step in persisted.steps:
        persisted_targets.extend(
            iter_step_assertions(persisted, step.candidate_step_id)
        )
    assert not document_supported_unreviewed(persisted_targets)
    assert len(persisted.events) == documented_count + 1
    assert inferred_unreviewed(persisted)
    assert sum(
        item.assertion.knowledge_state.value == "unknown"
        and item.assertion.disposition.value == "unreviewed"
        for item in persisted_targets
    ) == 147
    # Eight scoped confirmations + order + checkbox + approval replace the
    # misleading ~194-action UI path while preserving individual audit events.
    assert any(
        item.label == "APPROVE CURRENT-STATE PROCESS" for item in app.checkbox
    )


def test_review_action_controls_are_conditional_and_saved_state_is_visible(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "conditional-review-controls.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    repository = SQLiteAssessmentRepository(path)
    assessment = repository.create_assessment(
        "Conditional review controls", ExecutionMode.OFFLINE_DEMO
    )
    service = build_workspace_service(path)
    service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    service.extract(assessment.assessment_id)
    session = service.start_review(assessment.assessment_id)

    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30)
    app.session_state["selected_assessment_id"] = assessment.assessment_id
    app._page_hash = calc_hash("review")
    app.run()
    assert not app.exception

    # The page edits one activity at a time and summarizes the rest without
    # requiring the user to expand every activity card.
    assert len([item for item in app.selectbox if item.key == "selected-review-step"]) == 1
    progress = "\n".join(item.value for item in app.markdown)
    assert ":gray-badge[Not reviewed]" in progress
    assert "Optional descriptive fields" in "\n".join(
        item.value for item in app.caption
    )
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["Required items"] == "9"
    assert metrics["Remaining"] == "9"
    assert len([item for item in app.button if item.label == "Apply review action"]) < 45

    process_action = _widget_with_key_prefix(app.selectbox, "action-process.name-")
    process_button = _widget_with_key_prefix(app.button, "apply-process.name-")
    assert process_action.value == "Choose an action"
    assert process_button.disabled
    assert not any(
        item.key and item.key.startswith("value-process.name-")
        for item in app.text_input
    )

    app = process_action.select("Accept").run()
    assert not any(
        item.key and item.key.startswith("rationale-process.name-")
        for item in app.text_input
    )
    app = _widget_with_key_prefix(app.button, "apply-process.name-").click().run()
    assert any("Process name: accept saved" in item.value for item in app.success)
    assert any(":green-badge[Accepted]" in item.value for item in app.markdown)

    first_step = session.steps[0]
    unknown_path = f"steps.{first_step.candidate_step_id}.criteria[0]"
    unknown_action = _widget_with_key_prefix(app.selectbox, f"action-{unknown_path}-")
    app = unknown_action.select("Retain unknown").run()
    assert not any(
        item.key and item.key.startswith(f"value-{unknown_path}-")
        for item in [*app.number_input, *app.selectbox]
    )
    assert not any(
        item.key and item.key.startswith(f"rationale-{unknown_path}-")
        for item in app.text_input
    )
    app = _widget_with_key_prefix(app.button, f"apply-{unknown_path}-").click().run()
    assert any("unknown retained saved" in item.value for item in app.success)
    assert any(":gray-badge[Unknown retained]" in item.value for item in app.markdown)

    # Correction and rejection expose rationale only when it is required, and
    # saved states remain visibly distinct.
    description_action = _widget_with_key_prefix(
        app.selectbox, "action-process.description-"
    )
    app = description_action.select("Correct").run()
    _widget_with_key_prefix(app.text_input, "value-process.description-").input(
        "Human-corrected process description"
    )
    _widget_with_key_prefix(
        app.text_input, "rationale-process.description-"
    ).input("The reviewer corrected the extracted description.")
    app = _widget_with_key_prefix(
        app.button, "apply-process.description-"
    ).click().run()
    rendered = "\n".join(item.value for item in app.markdown)
    assert ":blue-badge[Corrected]" in rendered
    assert ":blue-badge[Human supplied]" in rendered

    objective_action = _widget_with_key_prefix(
        app.selectbox, "action-process.objective-"
    )
    app = objective_action.select("Reject").run()
    _widget_with_key_prefix(
        app.text_input, "rationale-process.objective-"
    ).input("The objective is not supported as extracted.")
    app = _widget_with_key_prefix(
        app.button, "apply-process.objective-"
    ).click().run()
    assert any(":red-badge[Rejected]" in item.value for item in app.markdown)

    # A human-added collection value is saved through the Phase 4 operation and
    # cannot acquire document evidence in the UI.
    outputs_path = f"steps.{first_step.candidate_step_id}.outputs"
    app.text_input(key=f"add-value-{outputs_path}").input("Triage record")
    app.text_input(key=f"add-rationale-{outputs_path}").input(
        "The reviewer confirmed this output from operational knowledge."
    )
    app = app.button(
        key=f"FormSubmitter:add-{outputs_path}-Add value"
    ).click().run()
    assert any("Human-supplied outputs value added" in item.value for item in app.success)
    captions = "\n".join(item.value for item in app.caption)
    assert "Human-supplied information — no document evidence claimed" in captions


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
    app._page_hash = calc_hash("review")
    app.run()
    app = _confirm_document_group(app, "process")
    for step in session.steps:
        app = app.selectbox(key="selected-review-step").select(
            step.candidate_step_id
        ).run()
        app = _confirm_document_group(app, f"step-{step.candidate_step_id}")

    first_step = session.steps[0]
    app.selectbox(key="selected-review-step").select(
        first_step.candidate_step_id
    ).run()
    unknown_path = f"steps.{first_step.candidate_step_id}.criteria[0]"
    app = _apply_review_action(app, unknown_path, "Retain unknown")
    assert any("unknown retained saved" in item.value for item in app.success)
    assert not any(
        item.key and unknown_path in item.key for item in app.number_input
    )

    next(
        item for item in app.button if item.label == "Accept current step order"
    ).click().run()
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

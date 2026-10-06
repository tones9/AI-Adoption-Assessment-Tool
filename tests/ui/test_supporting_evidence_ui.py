from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ai_adoption_engine.models.preliminary_assessment import AssessmentJourney
from ai_adoption_engine.models.preliminary_journey import ApprovedReviewArtifactPin
from ai_adoption_engine.models.formal_evidence import (
    FORMAL_EVIDENCE_FAMILY,
    REVIEWER_DECLARATION_SCHEMA,
    AttemptStatus,
    DocumentCategory,
    EvidenceClassification,
    ReviewerDeclaration,
)
from ai_adoption_engine.preliminary.composition import build_preliminary_service_bundle
from ai_adoption_engine.presentation.supporting_evidence_ui import (
    SUPPORTING_EVIDENCE_UI_ENV,
    supporting_evidence_ui_enabled,
)
from ai_adoption_engine.supporting_evidence.composition import (
    build_supporting_evidence_service_bundle,
)
from ai_adoption_engine.supporting_evidence.errors import (
    SupportingEvidenceFinalizationError,
)
from ai_adoption_engine.supporting_evidence.provider import (
    SUPPORTING_EVIDENCE_PROVIDER_SCHEMA,
    RawSupportingCitation,
    RawSupportingEvidenceBatch,
    RawSupportingEvidenceItem,
    ScriptedSupportingEvidenceProvider,
)
from ai_adoption_engine.workspace.composition import build_workspace_service
from ai_adoption_engine.workspace.demo_extraction import demo_text
from ai_adoption_engine.workspace.models import ArtifactType, ExecutionMode


ROOT = Path(__file__).resolve().parents[2]
PRELIMINARY_FLAG = "AI_ADOPTION_ENGINE_PRELIMINARY_UI"


def _approved_workspace(path: Path) -> tuple[str, ApprovedReviewArtifactPin]:
    service = build_workspace_service(path)
    assessment = service.repository.create_assessment(
        "Supporting evidence UI", ExecutionMode.OFFLINE_DEMO
    )
    assessment_id = assessment.assessment_id
    service.ingest_upload(assessment_id, raw_text=demo_text())
    service.extract(assessment_id)
    session = service.start_review(assessment_id)
    service.review_service.accept_assertion(
        session, session.process_name, "process.name"
    )
    for step in session.steps:
        service.review_service.accept_assertion(
            session, step.activity, f"steps.{step.candidate_step_id}.activity"
        )
    service.review_service.accept_step_order(session)
    service.save_review(assessment_id, session)
    approved = service.approve(assessment_id)
    assert approved.approved is not None
    artifact = service.repository.load_workspace(assessment_id).active_artifacts[
        ArtifactType.APPROVED_REVIEW
    ]
    return assessment_id, ApprovedReviewArtifactPin(
        assessment_id=assessment_id,
        artifact_id=artifact.artifact_id,
        artifact_revision=artifact.artifact_revision,
        artifact_schema_version=artifact.artifact_schema_version,
        payload_sha256=artifact.payload_sha256,
    )


def _formal_lifecycle(path: Path) -> tuple[str, str, str]:
    assessment_id, pin = _approved_workspace(path)
    services = build_preliminary_service_bundle(path)
    created = services.journeys.create_or_reuse_journey(pin)
    state = services.journeys.get_state(created.journey.journey_id)
    selected = services.journeys.select_route(
        created.journey.journey_id,
        AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
        request_token="supporting-ui-route",
        expected_latest_sequence=state.latest_event_sequence,
    )
    result = services.formal.start_formal_lifecycle(
        created.journey.journey_id,
        request_token="supporting-ui-formal",
        route_choice_event_id=selected.effective_route_event.event_id,
        route_choice_event_sequence=selected.effective_route_event.event_sequence,
    )
    return assessment_id, created.journey.journey_id, result.lifecycle.formal_lifecycle_id


def _reviewer() -> ReviewerDeclaration:
    return ReviewerDeclaration(
        schema_version=REVIEWER_DECLARATION_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        reviewer_display_name="Casey Reviewer",
        declared_organisational_role="Operations lead",
        identity_and_authority_locally_declared_not_authenticated=True,
        declared_at=datetime.now(UTC),
    )


def _page(assessment_id: str) -> AppTest:
    return AppTest.from_string(
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment_id!r}\n"
        "from ai_adoption_engine.presentation.pages.process_journey import render\n"
        "render()",
        default_timeout=30,
    )


def _rendered(app: AppTest) -> str:
    return "\n".join(
        str(getattr(item, "value", ""))
        for kind in (
            "title",
            "subheader",
            "markdown",
            "caption",
            "write",
            "warning",
            "info",
            "error",
            "success",
        )
        for item in app.get(kind)
    )


def _widget(items, *, label: str | None = None, key: str | None = None):
    return next(
        item
        for item in items
        if (label is None or item.label == label) and (key is None or item.key == key)
    )


@pytest.fixture(autouse=True)
def _formal_assessment_ui_off(monkeypatch):
    """These Slice 6 tests exercise the supporting workflow directly.

    Since D-038 the Formal Assessment UI is on by default and fronts the
    Organisational route, so it is switched off here via its kill switch.
    """

    monkeypatch.setenv("AI_ADOPTION_ENGINE_FORMAL_ASSESSMENT_UI", "0")


@pytest.mark.parametrize("value", (None, "", "  "))
def test_supporting_evidence_feature_is_default_on(monkeypatch, value) -> None:
    monkeypatch.delenv(PRELIMINARY_FLAG, raising=False)
    if value is None:
        monkeypatch.delenv(SUPPORTING_EVIDENCE_UI_ENV, raising=False)
    else:
        monkeypatch.setenv(SUPPORTING_EVIDENCE_UI_ENV, value)
    assert supporting_evidence_ui_enabled() is True


@pytest.mark.parametrize("value", ("0", "false", "no", "off", "OFF"))
def test_supporting_evidence_explicit_off_is_a_kill_switch(monkeypatch, value) -> None:
    monkeypatch.setenv(PRELIMINARY_FLAG, "1")
    monkeypatch.setenv(SUPPORTING_EVIDENCE_UI_ENV, value)
    assert supporting_evidence_ui_enabled() is False


@pytest.mark.parametrize("value", ("disabled", "TRUE-ish"))
def test_supporting_evidence_ambiguous_value_fails_closed(monkeypatch, value) -> None:
    monkeypatch.setenv(PRELIMINARY_FLAG, "1")
    monkeypatch.setenv(SUPPORTING_EVIDENCE_UI_ENV, value)
    assert supporting_evidence_ui_enabled() is False


@pytest.mark.parametrize("value", ("0", "off"))
def test_supporting_evidence_requires_preliminary_ui(monkeypatch, value) -> None:
    monkeypatch.setenv(PRELIMINARY_FLAG, value)
    monkeypatch.setenv(SUPPORTING_EVIDENCE_UI_ENV, "1")
    assert supporting_evidence_ui_enabled() is False


@pytest.mark.parametrize("value", ("1", "true", "TRUE", "yes", "on"))
def test_supporting_evidence_feature_accepts_only_approved_truthy_values(
    monkeypatch, value
) -> None:
    monkeypatch.setenv(PRELIMINARY_FLAG, "1")
    monkeypatch.setenv(SUPPORTING_EVIDENCE_UI_ENV, value)
    assert supporting_evidence_ui_enabled() is True


def test_disabled_placeholder_does_not_apply_migration_seven(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "disabled.db"
    assessment_id, _, _ = _formal_lifecycle(path)
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(PRELIMINARY_FLAG, "1")
    monkeypatch.setenv(SUPPORTING_EVIDENCE_UI_ENV, "0")

    app = _page(assessment_id).run()

    assert not app.exception
    rendered = _rendered(app)
    assert "Supporting evidence, evidence review, formal conversion" in rendered
    connection = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        connection.close()
    assert "preliminary_supporting_documents" not in tables


def test_enabled_composition_uses_exact_active_lifecycle_and_provider_is_lazy(
    tmp_path,
) -> None:
    path = tmp_path / "enabled.db"
    _, _, formal_lifecycle_id = _formal_lifecycle(path)
    calls = 0

    def provider_factory():
        nonlocal calls
        calls += 1
        raise RuntimeError("provider constructed")

    bundle = build_supporting_evidence_service_bundle(
        path, provider_factory=provider_factory
    )
    lineage = bundle.repository.load_active_lineage(formal_lifecycle_id)

    assert lineage.formal_lifecycle_id == formal_lifecycle_id
    assert calls == 0
    assert bundle.repository.current_documents(formal_lifecycle_id) == ()
    assert calls == 0
    with pytest.raises(RuntimeError, match="provider constructed"):
        bundle.extraction()
    assert calls == 1


def test_enabled_page_shows_complete_progressive_workflow_without_running_preliminary(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "workflow.db"
    assessment_id, journey_id, formal_lifecycle_id = _formal_lifecycle(path)
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(PRELIMINARY_FLAG, "1")
    monkeypatch.setenv(SUPPORTING_EVIDENCE_UI_ENV, "true")

    app = _page(assessment_id).run()

    assert not app.exception
    rendered = _rendered(app)
    for heading in (
        "1. Add documents",
        "2. Extract evidence",
        "3. Review evidence",
        "4. Map formal inputs",
        "5. Prepare assessment inputs",
    ):
        assert heading in rendered
    assert formal_lifecycle_id not in rendered
    assert "request token" not in rendered.lower()
    history = build_preliminary_service_bundle(path).journeys.get_history(journey_id)
    assert history.runs == ()
    connection = sqlite3.connect(path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_journey_schema_migrations WHERE version = 7"
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_enabled_page_collects_metadata_and_runs_local_ingestion(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "upload.db"
    assessment_id, _, formal_lifecycle_id = _formal_lifecycle(path)
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(PRELIMINARY_FLAG, "1")
    monkeypatch.setenv(SUPPORTING_EVIDENCE_UI_ENV, "1")

    app = _page(assessment_id).run()
    app = app.file_uploader[0].upload(
        "monthly-volumes.txt",
        b"Monthly complaint volume is 100.",
        "text/plain",
    ).run()
    app = _widget(app.text_area, label="Document description").set_value(
        "Monthly complaint volumes"
    ).run()
    app = _widget(
        app.selectbox, label="Primary evidence category"
    ).select("Process volumes and frequency").run()
    app = _widget(
        app.text_input, key="supporting-upload-reviewer-name"
    ).set_value("Casey Reviewer").run()
    app = _widget(
        app.text_input, key="supporting-upload-reviewer-role"
    ).set_value("Operations lead").run()
    app = _widget(
        app.checkbox, key="supporting-upload-reviewer-declaration"
    ).check().run()
    app = _widget(app.button, label="Add supporting document").click().run()

    assert not app.exception
    rendered = _rendered(app)
    assert "monthly-volumes.txt" in rendered
    assert "Ingestion: Complete" in rendered
    bundle = build_supporting_evidence_service_bundle(path)
    documents = bundle.repository.current_documents(formal_lifecycle_id)
    assert len(documents) == 1
    metadata = bundle.repository.metadata_revisions_for_document(
        formal_lifecycle_id, documents[0].document_id
    )[-1]
    assert metadata.description == "Monthly complaint volumes"
    assert metadata.primary_category is DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY
    ingestion = bundle.repository.latest_ingestion_attempt(
        formal_lifecycle_id=formal_lifecycle_id,
        document_id=documents[0].document_id,
    )
    assert ingestion is not None and ingestion.status is AttemptStatus.SUCCEEDED


def test_consent_precedes_injected_provider_call_and_extraction_is_explicit(
    tmp_path, monkeypatch
) -> None:
    import ai_adoption_engine.presentation.supporting_evidence_ui as ui_module

    path = tmp_path / "consent.db"
    assessment_id, _, formal_lifecycle_id = _formal_lifecycle(path)
    seed_bundle = build_supporting_evidence_service_bundle(
        path,
        provider_factory=lambda: (_ for _ in ()).throw(AssertionError("unused")),
    )
    lineage = seed_bundle.repository.load_active_lineage(formal_lifecycle_id)
    intake = seed_bundle.intake.accept(
        lineage=lineage,
        request_token="seed-document",
        filename="volume.txt",
        raw_bytes=b"Monthly complaint volume is 100.",
        description="Monthly volume",
        primary_category=DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
        submitter=_reviewer(),
    )
    seed_bundle.ingestion.ingest(
        lineage=lineage,
        document_id=intake.document.document_id,
        request_token="seed-ingestion",
    )
    provider = ScriptedSupportingEvidenceProvider(
        (
            RawSupportingEvidenceBatch(
                schema_version=SUPPORTING_EVIDENCE_PROVIDER_SCHEMA,
                items=(
                    RawSupportingEvidenceItem(
                        proposed_claim="Monthly complaint volume is 100.",
                        proposed_classification=EvidenceClassification.DOCUMENTED_FACT,
                        primary_citation=RawSupportingCitation(
                            document_id=intake.document.document_id,
                            block_id="t-b0001",
                            exact_excerpt="Monthly complaint volume is 100.",
                        ),
                        proposed_category=DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
                        ambiguity_indicated=False,
                        conflict_indicated=False,
                        relevance_explanation="May inform formal review.",
                    ),
                )
            ),
        ),
        external=True,
        provider_id="openai",
        provider_version="gpt-5.6-terra",
    )
    bundle = build_supporting_evidence_service_bundle(
        path, provider_factory=lambda: provider
    )
    monkeypatch.setattr(
        ui_module, "_cached_supporting_evidence_services", lambda database_path: bundle
    )
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(PRELIMINARY_FLAG, "1")
    monkeypatch.setenv(SUPPORTING_EVIDENCE_UI_ENV, "1")

    app = _page(assessment_id).run()
    assert provider.calls == []
    app = _widget(
        app.text_input, key=f"consent-name-{intake.document.document_id}"
    ).set_value("Casey Reviewer").run()
    app = _widget(
        app.checkbox, key=f"consent-choice-{intake.document.document_id}"
    ).check().run()
    app = _widget(
        app.button, key=f"save-consent-{intake.document.document_id}"
    ).click().run()
    assert not app.exception
    assert provider.calls == []

    app = _widget(
        app.button, key=f"extract-{intake.document.document_id}"
    ).click().run()

    assert not app.exception
    assert len(provider.calls) == 1
    assert "Monthly complaint volume is 100." in _rendered(app)

    review_queue = bundle.reviews.get_review_queue(formal_lifecycle_id)
    proposal_id = review_queue.items[0].proposal.proposal_id
    assert proposal_id is not None
    app = _widget(app.checkbox, key=f"direct-{proposal_id}").check().run()
    app = _widget(app.text_area, key=f"review-rationale-{proposal_id}").set_value(
        "The exact excerpt states the monthly volume."
    ).run()
    app = _widget(app.text_input, key=f"review-{proposal_id}-reviewer-name").set_value(
        "Casey Reviewer"
    ).run()
    app = _widget(app.text_input, key=f"review-{proposal_id}-reviewer-role").set_value(
        "Operations lead"
    ).run()
    app = _widget(
        app.checkbox, key=f"review-{proposal_id}-reviewer-declaration"
    ).check().run()
    app = _widget(app.button, key=f"save-review-{proposal_id}").click().run()
    assert not app.exception

    app = _widget(app.selectbox, key=f"criterion-value-{proposal_id}").select("5").run()
    app = _widget(app.text_area, key=f"mapping-rationale-{proposal_id}").set_value(
        "Use the reviewed monthly volume as a high repetition signal."
    ).run()
    app = _widget(app.text_input, key=f"mapping-{proposal_id}-reviewer-name").set_value(
        "Casey Reviewer"
    ).run()
    app = _widget(app.text_input, key=f"mapping-{proposal_id}-reviewer-role").set_value(
        "Operations lead"
    ).run()
    app = _widget(
        app.checkbox, key=f"mapping-{proposal_id}-reviewer-declaration"
    ).check().run()
    app = _widget(app.button, key=f"save-mapping-{proposal_id}").click().run()
    assert not app.exception

    original_readiness = bundle.formal_inputs.evaluate_and_persist_readiness
    readiness_attempts = 0

    def fail_readiness_once(*args, **kwargs):
        nonlocal readiness_attempts
        readiness_attempts += 1
        if readiness_attempts == 1:
            raise SupportingEvidenceFinalizationError("injected readiness failure")
        return original_readiness(*args, **kwargs)

    monkeypatch.setattr(
        bundle.formal_inputs,
        "evaluate_and_persist_readiness",
        fail_readiness_once,
    )
    app = _widget(
        app.button, label="Prepare organisational assessment inputs"
    ).click().run()
    assert not app.exception
    assert "Preparation could not complete safely" in _rendered(app)
    candidates = bundle.repository.candidate_sets_for_lifecycle(formal_lifecycle_id)
    assert len(candidates) == 1
    assert bundle.repository.readiness_for_lifecycle(formal_lifecycle_id) == ()

    app = _widget(
        app.button, label="Prepare organisational assessment inputs"
    ).click().run()
    assert not app.exception
    assert "Ready to attempt an organisational assessment" in _rendered(app)
    assert len(bundle.repository.candidate_sets_for_lifecycle(formal_lifecycle_id)) == 1
    state = bundle.formal_inputs.get_current_preparation_state(formal_lifecycle_id)
    assert state.candidate_set_current is True
    assert state.latest_readiness is not None
    assert state.latest_readiness.status.value == "READY_TO_ATTEMPT"


def test_preparation_shows_plain_blocker_and_requires_explicit_document_exclusion(
    tmp_path, monkeypatch
) -> None:
    import ai_adoption_engine.presentation.supporting_evidence_ui as ui_module

    path = tmp_path / "exclusion.db"
    assessment_id, _, formal_lifecycle_id = _formal_lifecycle(path)
    bundle = build_supporting_evidence_service_bundle(
        path,
        provider_factory=lambda: (_ for _ in ()).throw(AssertionError("unused")),
    )
    lineage = bundle.repository.load_active_lineage(formal_lifecycle_id)
    intake = bundle.intake.accept(
        lineage=lineage,
        request_token="excluded-document",
        filename="outdated-policy.txt",
        raw_bytes=b"This policy document is deliberately excluded.",
        description="Outdated policy",
        primary_category=DocumentCategory.LEGAL_POLICY_SECURITY_OR_OPERATIONAL_CONSTRAINTS,
        submitter=_reviewer(),
    )
    bundle.ingestion.ingest(
        lineage=lineage,
        document_id=intake.document.document_id,
        request_token="excluded-ingestion",
    )
    monkeypatch.setattr(
        ui_module, "_cached_supporting_evidence_services", lambda database_path: bundle
    )
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(PRELIMINARY_FLAG, "1")
    monkeypatch.setenv(SUPPORTING_EVIDENCE_UI_ENV, "1")

    app = _page(assessment_id).run()
    assert "still needs successful extraction or explicit exclusion" in _rendered(app)
    app = _widget(
        app.checkbox, key=f"exclude-document-{intake.document.document_id}"
    ).check().run()
    app = _widget(app.checkbox, key="confirm-document-exclusions").check().run()
    app = _widget(
        app.button, label="Prepare organisational assessment inputs"
    ).click().run()

    assert not app.exception
    assert "More formal inputs are needed" in _rendered(app)
    candidate = bundle.repository.candidate_sets_for_lifecycle(formal_lifecycle_id)[-1]
    assert candidate.explicitly_excluded_document_ids == (
        intake.document.document_id,
    )


def test_route_switch_and_restart_resume_exact_supporting_history(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "route-resume.db"
    assessment_id, journey_id, formal_lifecycle_id = _formal_lifecycle(path)
    bundle = build_supporting_evidence_service_bundle(
        path,
        provider_factory=lambda: (_ for _ in ()).throw(AssertionError("unused")),
    )
    lineage = bundle.repository.load_active_lineage(formal_lifecycle_id)
    intake = bundle.intake.accept(
        lineage=lineage,
        request_token="route-history-document",
        filename="route-history.txt",
        raw_bytes=b"Persist this supporting history across route changes.",
        description="Route persistence evidence",
        primary_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
        submitter=_reviewer(),
    )
    bundle.ingestion.ingest(
        lineage=lineage,
        document_id=intake.document.document_id,
        request_token="route-history-ingestion",
    )
    preliminary = build_preliminary_service_bundle(path)
    state = preliminary.journeys.get_state(journey_id)
    preliminary.journeys.select_route(
        journey_id,
        AssessmentJourney.EXPLORE_PROCESS,
        request_token="route-history-explore",
        expected_latest_sequence=state.latest_event_sequence,
    )
    state = preliminary.journeys.get_state(journey_id)
    preliminary.journeys.select_route(
        journey_id,
        AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
        request_token="route-history-return",
        expected_latest_sequence=state.latest_event_sequence,
    )
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(PRELIMINARY_FLAG, "1")
    monkeypatch.setenv(SUPPORTING_EVIDENCE_UI_ENV, "1")

    app = _page(assessment_id).run()

    assert not app.exception
    assert "route-history.txt" in _rendered(app)
    reopened = build_supporting_evidence_service_bundle(path)
    assert reopened.repository.current_documents(formal_lifecycle_id) == (
        intake.document,
    )
    assert build_preliminary_service_bundle(path).journeys.get_history(journey_id).runs == ()


def test_frozen_guard_precedes_repository_construction(monkeypatch) -> None:
    import ai_adoption_engine.presentation.supporting_evidence_ui as module

    monkeypatch.setenv(PRELIMINARY_FLAG, "1")
    monkeypatch.setenv(SUPPORTING_EVIDENCE_UI_ENV, "1")
    monkeypatch.setattr(module, "frozen_evaluation_workspace_selected", lambda: True)
    constructed = False

    def fail_if_constructed(*args, **kwargs):
        nonlocal constructed
        constructed = True
        raise AssertionError("repository constructed")

    monkeypatch.setattr(module, "_cached_supporting_evidence_services", fail_if_constructed)
    with pytest.raises(RuntimeError, match="frozen"):
        module.supporting_evidence_services()
    assert constructed is False


def test_missing_provider_configuration_does_not_block_history_inspection(
    tmp_path, monkeypatch
) -> None:
    import ai_adoption_engine.supporting_evidence.composition as module

    path = tmp_path / "missing-provider.db"
    _, _, formal_lifecycle_id = _formal_lifecycle(path)
    monkeypatch.setattr(
        module,
        "DEFAULT_SUPPORTING_EVIDENCE_CONFIGURATION",
        tmp_path / "missing.json",
    )
    bundle = module.build_supporting_evidence_service_bundle(path)

    assert bundle.repository.load_active_lineage(formal_lifecycle_id)
    assert bundle.repository.current_documents(formal_lifecycle_id) == ()
    with pytest.raises(FileNotFoundError):
        bundle.extraction()

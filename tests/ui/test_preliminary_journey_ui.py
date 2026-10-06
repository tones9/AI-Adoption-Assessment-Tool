from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ai_adoption_engine.models.preliminary_assessment import AssessmentJourney
from ai_adoption_engine.models.preliminary_journey import ApprovedReviewArtifactPin
from ai_adoption_engine.models.preliminary_evaluation import (
    PreliminaryEvaluationError,
    PreliminaryEvaluationFailure,
    PreliminaryEvaluationFailureCode,
)
from ai_adoption_engine.preliminary.composition import build_preliminary_service_bundle
from ai_adoption_engine.preliminary.evaluator import PreliminaryAssessmentEvaluator
from ai_adoption_engine.preliminary.journey import (
    current_preliminary_compatibility_identity,
    preliminary_v0_2_compatibility_identity,
)
from ai_adoption_engine.preliminary.rules import PRELIMINARY_EVALUATOR_RULES_V0_1
from ai_adoption_engine.preliminary.run import (
    PreliminaryRunFinalizationError,
    PreliminaryRunResultService,
)
from ai_adoption_engine.presentation.preliminary_ui import (
    PRELIMINARY_EVALUATOR_ENV,
    UnsupportedPreliminaryEvaluatorConfiguration,
    configured_preliminary_compatibility_identity,
)
from ai_adoption_engine.workspace.composition import build_workspace_service
from ai_adoption_engine.workspace.demo_extraction import demo_text
from ai_adoption_engine.workspace.models import ArtifactType, ExecutionMode


ROOT = Path(__file__).resolve().parents[2]
FEATURE_FLAG = "AI_ADOPTION_ENGINE_PRELIMINARY_UI"


@pytest.fixture(autouse=True)
def _pin_v0_1_and_downstream_off(monkeypatch):
    """Keep these journey tests on their original v0.1 contract.

    D-038 made v0.2 the default evaluator and turned the Supporting Evidence and
    Formal Assessment UIs on by default. These tests cover v0.1 rendering and the
    plain Organisational placeholder, so they pin v0.1 explicitly and use the
    downstream kill switches. Tests that need v0.2 still set it themselves.
    """

    monkeypatch.setenv(PRELIMINARY_EVALUATOR_ENV, "preliminary-evaluator.v0.1")
    monkeypatch.setenv("AI_ADOPTION_ENGINE_SUPPORTING_EVIDENCE_UI", "0")
    monkeypatch.setenv("AI_ADOPTION_ENGINE_FORMAL_ASSESSMENT_UI", "0")


def _selected_page(module: str, assessment_id: str) -> AppTest:
    return AppTest.from_string(
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment_id!r}\n"
        f"from ai_adoption_engine.presentation.pages.{module} import render\n"
        "render()",
        default_timeout=30,
    )


def _approved_workspace(path: Path) -> tuple[str, ApprovedReviewArtifactPin]:
    service = build_workspace_service(path)
    assessment = service.repository.create_assessment(
        "Preliminary UI", ExecutionMode.OFFLINE_DEMO
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
            session,
            step.activity,
            f"steps.{step.candidate_step_id}.activity",
        )
    service.review_service.accept_step_order(session)
    service.save_review(assessment_id, session)
    approved = service.approve(assessment_id)
    assert approved.approved is not None
    snapshot = service.repository.load_workspace(assessment_id)
    artifact = snapshot.active_artifacts[ArtifactType.APPROVED_REVIEW]
    return assessment_id, ApprovedReviewArtifactPin(
        assessment_id=assessment_id,
        artifact_id=artifact.artifact_id,
        artifact_revision=artifact.artifact_revision,
        artifact_schema_version=artifact.artifact_schema_version,
        payload_sha256=artifact.payload_sha256,
    )


def _extracted_workspace(path: Path) -> str:
    service = build_workspace_service(path)
    assessment = service.repository.create_assessment(
        "Route-choice UI", ExecutionMode.OFFLINE_DEMO
    )
    service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    service.extract(assessment.assessment_id)
    return assessment.assessment_id


def _review_ready_workspace(path: Path) -> str:
    service = build_workspace_service(path)
    assessment = service.repository.create_assessment(
        "Approval integration UI", ExecutionMode.OFFLINE_DEMO
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
            session,
            step.activity,
            f"steps.{step.candidate_step_id}.activity",
        )
    service.review_service.accept_step_order(session)
    service.save_review(assessment_id, session)
    return assessment_id


def _materialized_explore(path: Path) -> tuple[str, str]:
    assessment_id, pin = _approved_workspace(path)
    services = build_preliminary_service_bundle(path)
    created = services.journeys.create_or_reuse_journey(pin)
    state = services.journeys.get_state(created.journey.journey_id)
    services.journeys.select_route(
        created.journey.journey_id,
        AssessmentJourney.EXPLORE_PROCESS,
        request_token="ui-fixture-explore",
        expected_latest_sequence=state.latest_event_sequence,
    )
    return assessment_id, created.journey.journey_id


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


def _button(app: AppTest, label: str):
    return next(item for item in app.button if item.label == label)


@pytest.mark.parametrize("value", ("0", "false", "no", "off"))
def test_explicit_off_does_not_construct_preliminary_store(
    tmp_path, monkeypatch, value
) -> None:
    path = tmp_path / "feature-off.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, value)

    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()

    assert not app.exception
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
    assert "preliminary_journeys" not in tables


@pytest.mark.parametrize("value", (None, "", " "))
def test_preliminary_ui_is_default_on(monkeypatch, value) -> None:
    from ai_adoption_engine.presentation.preliminary_ui import preliminary_ui_enabled

    if value is None:
        monkeypatch.delenv(FEATURE_FLAG, raising=False)
    else:
        monkeypatch.setenv(FEATURE_FLAG, value)
    assert preliminary_ui_enabled() is True


@pytest.mark.parametrize("value", ("enabled", "TRUE-ish"))
def test_preliminary_ui_ambiguous_value_fails_closed(monkeypatch, value) -> None:
    from ai_adoption_engine.presentation.preliminary_ui import preliminary_ui_enabled

    monkeypatch.setenv(FEATURE_FLAG, value)
    assert preliminary_ui_enabled() is False


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        (None, preliminary_v0_2_compatibility_identity()),
        ("preliminary-evaluator.v0.1", current_preliminary_compatibility_identity()),
        (
            "preliminary-evaluator.v0.2",
            preliminary_v0_2_compatibility_identity(),
        ),
    ],
)
def test_evaluator_selector_maps_only_to_complete_approved_identity(
    monkeypatch, configured, expected
) -> None:
    if configured is None:
        monkeypatch.delenv(PRELIMINARY_EVALUATOR_ENV, raising=False)
    else:
        monkeypatch.setenv(PRELIMINARY_EVALUATOR_ENV, configured)

    assert configured_preliminary_compatibility_identity() == expected


def test_invalid_evaluator_selector_fails_before_database_creation(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "invalid-selector.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, "1")
    monkeypatch.setenv(PRELIMINARY_EVALUATOR_ENV, "preliminary-evaluator.v9")

    with pytest.raises(UnsupportedPreliminaryEvaluatorConfiguration):
        configured_preliminary_compatibility_identity()
    assert not path.exists()

    script = (
        "import streamlit as st\n"
        "from ai_adoption_engine.presentation.preliminary_ui import preliminary_services\n"
        "try:\n"
        "    preliminary_services()\n"
        "except Exception as exc:\n"
        "    st.write(type(exc).__name__)\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()
    assert not app.exception
    assert "UnsupportedPreliminaryEvaluatorConfiguration" in _rendered(app)
    assert not path.exists()


def test_disabled_preliminary_ui_ignores_invalid_evaluator_selector(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "disabled-invalid-selector.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, "0")
    monkeypatch.setenv(PRELIMINARY_EVALUATOR_ENV, "preliminary-evaluator.v9")
    script = (
        "import streamlit as st\n"
        "from ai_adoption_engine.presentation.preliminary_ui import preliminary_services\n"
        "try:\n"
        "    preliminary_services()\n"
        "except Exception as exc:\n"
        "    st.write(str(exc))\n"
    )

    app = AppTest.from_string(script, default_timeout=30).run()

    assert not app.exception
    assert "Preliminary UI is not enabled" in _rendered(app)
    assert not path.exists()


def test_explicit_v0_2_constructs_exact_journey_and_run_services_only(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "v0-2-services.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, "1")
    monkeypatch.setenv(PRELIMINARY_EVALUATOR_ENV, "preliminary-evaluator.v0.2")
    identity = configured_preliminary_compatibility_identity()
    build_workspace_service(path)
    services = build_preliminary_service_bundle(path, supported_identity=identity)

    assert services.journeys.supported_identity == preliminary_v0_2_compatibility_identity()
    assert services.runs.supported_identity == preliminary_v0_2_compatibility_identity()
    assert services.formal.supported_identity == current_preliminary_compatibility_identity()


def test_feature_on_registers_process_journey_without_eager_store_creation(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "feature-on.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, "1")

    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()

    assert not app.exception
    labels = [item.label for item in app.sidebar.get("page_link")]
    assert "Process journey" not in labels
    assert "Preliminary Assessment" not in labels
    assert "Organisational Assessment" not in labels
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
    assert "preliminary_journeys" not in tables


@pytest.mark.parametrize(
    ("route", "expected_label"),
    [
        (AssessmentJourney.EXPLORE_PROCESS, "Preliminary Assessment"),
        (
            AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
            "Organisational Assessment",
        ),
    ],
)
def test_materialized_route_uses_customer_facing_sidebar_destination(
    tmp_path, monkeypatch, route, expected_label
) -> None:
    path = tmp_path / f"route-navigation-{route.value}.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, "1")
    assessment_id, pin = _approved_workspace(path)
    services = build_preliminary_service_bundle(path)
    created = services.journeys.create_or_reuse_journey(pin)
    state = services.journeys.get_state(created.journey.journey_id)
    services.journeys.select_route(
        created.journey.journey_id,
        route,
        request_token=f"navigation-{route.value}",
        expected_latest_sequence=state.latest_event_sequence,
    )
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30)
    app.session_state.selected_assessment_id = assessment_id
    app.session_state.loaded_assessment_id = assessment_id
    app.session_state.workspace_snapshot = build_workspace_service(
        path
    ).repository.load_workspace(assessment_id)

    app = app.run()

    assert not app.exception
    labels = [item.label for item in app.sidebar.get("page_link")]
    assert expected_label in labels
    assert "Process journey" not in labels


@pytest.mark.parametrize(
    "route_label",
    ["Explore this process", "Run an organisational assessment"],
)
def test_route_choice_appears_after_extraction_and_uses_validation_for_both_routes(
    tmp_path, monkeypatch, route_label
) -> None:
    path = tmp_path / f"route-{route_label[:3]}.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, "1")
    assessment_id = _extracted_workspace(path)

    app = _selected_page("source", assessment_id).run()

    assert not app.exception
    assert _button(app, "Explore this process")
    assert _button(app, "Run an organisational assessment")
    assert _button(app, "Start process validation").disabled

    app = _button(app, route_label).click().run()

    assert not app.exception
    assert not _button(app, "Start process validation").disabled
    connection = sqlite3.connect(path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='preliminary_journeys'"
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_route_intent_fails_closed_on_candidate_lineage_mismatch(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "intent-lineage.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, "1")
    assessment_id = _extracted_workspace(path)
    script = (
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment_id!r}\n"
        "from ai_adoption_engine.models.preliminary_assessment import AssessmentJourney\n"
        "from ai_adoption_engine.presentation.context import hydrate_workspace\n"
        "from ai_adoption_engine.presentation.preliminary_ui import PreliminaryRouteIntent, route_intent\n"
        "snapshot = hydrate_workspace()\n"
        "st.session_state.preliminary_route_intent = PreliminaryRouteIntent(\n"
        "  assessment_id=snapshot.assessment.assessment_id,\n"
        "  source_document_id='doc-' + ('0' * 64),\n"
        "  extraction_run_id='stale-run',\n"
        "  route=AssessmentJourney.EXPLORE_PROCESS,\n"
        ")\n"
        "st.write('cleared' if route_intent(snapshot) is None else 'retained')\n"
    )

    app = AppTest.from_string(script, default_timeout=30).run()

    assert not app.exception
    assert any(item.value == "cleared" for item in app.markdown)


def test_explore_approval_materialises_route_and_runs_first_assessment_once(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "approval-materialisation.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, "1")
    assessment_id = _review_ready_workspace(path)
    script = (
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment_id!r}\n"
        "from ai_adoption_engine.models.preliminary_assessment import AssessmentJourney\n"
        "from ai_adoption_engine.presentation.context import hydrate_workspace\n"
        "from ai_adoption_engine.presentation.preliminary_ui import route_intent, set_route_intent\n"
        "from ai_adoption_engine.presentation.pages import review\n"
        "review.switch_to_registered_page = lambda page: True\n"
        "snapshot = hydrate_workspace()\n"
        "if route_intent(snapshot) is None:\n"
        "    set_route_intent(snapshot, AssessmentJourney.EXPLORE_PROCESS)\n"
        "review.render()\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()
    app = app.button_group[0].set_value("Final approval").run()
    approval = next(
        item for item in app.checkbox if item.label == "I approve this current-state process"
    )
    app = approval.check().run()
    app = _button(app, "Approve current-state process").click().run()

    assert not app.exception
    snapshot = build_workspace_service(path).repository.load_workspace(assessment_id)
    approved_artifact = snapshot.active_artifacts[ArtifactType.APPROVED_REVIEW]
    pin = ApprovedReviewArtifactPin(
        assessment_id=assessment_id,
        artifact_id=approved_artifact.artifact_id,
        artifact_revision=approved_artifact.artifact_revision,
        artifact_schema_version=approved_artifact.artifact_schema_version,
        payload_sha256=approved_artifact.payload_sha256,
    )
    state = build_preliminary_service_bundle(path).journeys.find_journey_for_approved_review(pin)
    assert state is not None
    assert state.current_route.value == "EXPLORE_PROCESS"
    assert state.preliminary_status.value == "AVAILABLE"
    history = build_preliminary_service_bundle(path).journeys.get_history(
        state.journey.journey_id
    )
    assert len(history.runs) == 1
    assert history.runs[0].result is not None

    destination = _selected_page("process_journey", assessment_id).run()
    assert not destination.exception
    assert "Preliminary result" in _rendered(destination)
    assert not any(
        item.label == "Run Preliminary Assessment" for item in destination.button
    )

    app = app.run()
    replayed = build_preliminary_service_bundle(path).journeys.get_history(
        state.journey.journey_id
    )
    assert len(replayed.runs) == 1


def test_v0_2_explore_approval_runs_once_and_uses_versioned_projector(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "approval-materialisation-v0-2.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, "1")
    monkeypatch.setenv(PRELIMINARY_EVALUATOR_ENV, "preliminary-evaluator.v0.2")
    assessment_id = _review_ready_workspace(path)
    script = (
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment_id!r}\n"
        "from ai_adoption_engine.models.preliminary_assessment import AssessmentJourney\n"
        "from ai_adoption_engine.presentation.context import hydrate_workspace\n"
        "from ai_adoption_engine.presentation.preliminary_ui import route_intent, set_route_intent\n"
        "from ai_adoption_engine.presentation.pages import review\n"
        "review.switch_to_registered_page = lambda page: True\n"
        "snapshot = hydrate_workspace()\n"
        "if route_intent(snapshot) is None:\n"
        "    set_route_intent(snapshot, AssessmentJourney.EXPLORE_PROCESS)\n"
        "review.render()\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()
    app = app.button_group[0].set_value("Final approval").run()
    approval = next(
        item for item in app.checkbox if item.label == "I approve this current-state process"
    )
    app = approval.check().run()
    app = _button(app, "Approve current-state process").click().run()

    assert not app.exception
    snapshot = build_workspace_service(path).repository.load_workspace(assessment_id)
    approved_artifact = snapshot.active_artifacts[ArtifactType.APPROVED_REVIEW]
    pin = ApprovedReviewArtifactPin(
        assessment_id=assessment_id,
        artifact_id=approved_artifact.artifact_id,
        artifact_revision=approved_artifact.artifact_revision,
        artifact_schema_version=approved_artifact.artifact_schema_version,
        payload_sha256=approved_artifact.payload_sha256,
    )
    services = build_preliminary_service_bundle(
        path,
        supported_identity=preliminary_v0_2_compatibility_identity(),
    )
    state = services.journeys.find_journey_for_approved_review(pin)
    assert state is not None
    assert state.preliminary_status.value == "AVAILABLE"
    assert state.active_preliminary_result is not None
    assert state.active_preliminary_result.output_schema_version == (
        "preliminary-assessment.v0.2"
    )
    history = services.journeys.get_history(state.journey.journey_id)
    assert len(history.runs) == 1
    assert history.runs[0].manifest.evaluator.evaluator_id == (
        "preliminary-evaluator.v0.2"
    )
    assert history.runs[0].manifest.rule_set.rule_set_fingerprint == (
        preliminary_v0_2_compatibility_identity().rule_set_fingerprint
    )

    destination = _selected_page("process_journey", assessment_id).run()
    assert not destination.exception
    rendered = _rendered(destination)
    for expected in (
        "Preliminary Assessment",
        "Provisional exploration only.",
        "evidence coverage",
        "It is not probability, safety, implementation readiness, or approval.",
        "Activity 1",
        "Opportunity 1",
        "Documented evidence",
        "Rule-derived inferences",
        "Unknowns",
        "Conflicts",
        "Next evidence to collect",
        "No single process-wide direction has been generated.",
    ):
        assert expected in rendered
    audit = next(
        item
        for item in destination.expander
        if item.label == "Technical and audit details"
    )
    assert audit.proto.expanded is False

    app = app.run()
    replayed = services.journeys.get_history(state.journey.journey_id)
    assert len(replayed.runs) == 1


def test_organisational_approval_starts_awaiting_inputs_without_preliminary_run(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "approval-organisational.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, "1")
    assessment_id = _review_ready_workspace(path)
    script = (
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment_id!r}\n"
        "from ai_adoption_engine.models.preliminary_assessment import AssessmentJourney\n"
        "from ai_adoption_engine.presentation.context import hydrate_workspace\n"
        "from ai_adoption_engine.presentation.preliminary_ui import route_intent, set_route_intent\n"
        "from ai_adoption_engine.presentation.pages import review\n"
        "review.switch_to_registered_page = lambda page: True\n"
        "snapshot = hydrate_workspace()\n"
        "if route_intent(snapshot) is None:\n"
        "    set_route_intent(snapshot, AssessmentJourney.ORGANISATIONAL_ASSESSMENT)\n"
        "review.render()\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()
    app = app.button_group[0].set_value("Final approval").run()
    approval = next(
        item for item in app.checkbox if item.label == "I approve this current-state process"
    )
    app = approval.check().run()
    app = _button(app, "Approve current-state process").click().run()

    assert not app.exception
    snapshot = build_workspace_service(path).repository.load_workspace(assessment_id)
    approved_artifact = snapshot.active_artifacts[ArtifactType.APPROVED_REVIEW]
    pin = ApprovedReviewArtifactPin(
        assessment_id=assessment_id,
        artifact_id=approved_artifact.artifact_id,
        artifact_revision=approved_artifact.artifact_revision,
        artifact_schema_version=approved_artifact.artifact_schema_version,
        payload_sha256=approved_artifact.payload_sha256,
    )
    services = build_preliminary_service_bundle(path)
    state = services.journeys.find_journey_for_approved_review(pin)
    assert state is not None
    assert state.current_route.value == "ORGANISATIONAL_ASSESSMENT"
    assert state.formal_lifecycle_status.value == "AWAITING_FORMAL_INPUTS"
    assert services.journeys.get_history(state.journey.journey_id).runs == ()

    destination = _selected_page("process_journey", assessment_id).run()
    assert not destination.exception
    assert "Awaiting formal inputs" in _rendered(destination)
    assert not any(
        item.label == "Start organisational assessment setup"
        for item in destination.button
    )


def test_v0_2_selector_keeps_organisational_route_preliminary_free(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "approval-organisational-v0-2-selector.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, "1")
    monkeypatch.setenv(PRELIMINARY_EVALUATOR_ENV, "preliminary-evaluator.v0.2")
    assessment_id = _review_ready_workspace(path)
    script = (
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment_id!r}\n"
        "from ai_adoption_engine.models.preliminary_assessment import AssessmentJourney\n"
        "from ai_adoption_engine.presentation.context import hydrate_workspace\n"
        "from ai_adoption_engine.presentation.preliminary_ui import route_intent, set_route_intent\n"
        "from ai_adoption_engine.presentation.pages import review\n"
        "review.switch_to_registered_page = lambda page: True\n"
        "snapshot = hydrate_workspace()\n"
        "if route_intent(snapshot) is None:\n"
        "    set_route_intent(snapshot, AssessmentJourney.ORGANISATIONAL_ASSESSMENT)\n"
        "review.render()\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()
    app = app.button_group[0].set_value("Final approval").run()
    approval = next(
        item for item in app.checkbox if item.label == "I approve this current-state process"
    )
    app = approval.check().run()
    app = _button(app, "Approve current-state process").click().run()

    assert not app.exception
    snapshot = build_workspace_service(path).repository.load_workspace(assessment_id)
    artifact = snapshot.active_artifacts[ArtifactType.APPROVED_REVIEW]
    pin = ApprovedReviewArtifactPin(
        assessment_id=assessment_id,
        artifact_id=artifact.artifact_id,
        artifact_revision=artifact.artifact_revision,
        artifact_schema_version=artifact.artifact_schema_version,
        payload_sha256=artifact.payload_sha256,
    )
    services = build_preliminary_service_bundle(
        path,
        supported_identity=preliminary_v0_2_compatibility_identity(),
    )
    state = services.journeys.find_journey_for_approved_review(pin)
    assert state is not None
    assert state.formal_lifecycle_status.value == "AWAITING_FORMAL_INPUTS"
    assert services.journeys.get_history(state.journey.journey_id).runs == ()

    destination = _selected_page("process_journey", assessment_id).run()
    assert not destination.exception
    assert "Awaiting formal inputs" in _rendered(destination)


def test_process_journey_runs_and_renders_provisional_activity_results(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "explore.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, "1")
    assessment_id, _ = _materialized_explore(path)

    app = _selected_page("process_journey", assessment_id).run()
    assert not app.exception
    assert _button(app, "Run Preliminary Assessment")

    app = _button(app, "Run Preliminary Assessment").click().run()

    assert not app.exception
    rendered = _rendered(app)
    assert "Provisional exploration only." in rendered
    assert "evidence coverage" in rendered
    assert "Confidence describes evidence coverage, not probability" in rendered
    assert "Documented facts" in rendered
    assert "Reasonable inferences" in rendered
    assert "Unknowns" in rendered
    assert "Next evidence to collect" in rendered
    assert "No single process-wide direction has been generated." in rendered
    assert _button(app, "Run a new Preliminary Assessment")
    assert _button(app, "View assessment history")


def test_switching_selector_exposes_only_its_compatible_active_result(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "selector-switch.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, "1")
    assessment_id, journey_id = _materialized_explore(path)
    v0_1 = build_preliminary_service_bundle(path)
    v0_2 = build_preliminary_service_bundle(
        path,
        supported_identity=preliminary_v0_2_compatibility_identity(),
    )
    route = v0_1.journeys.get_state(journey_id).current_route_event
    assert route is not None
    v0_1.runs.evaluate_and_persist(
        journey_id,
        request_token="selector-switch-v0-1",
        route_choice_event_id=route.event_id,
        route_choice_event_sequence=route.event_sequence,
    )
    v0_2.runs.evaluate_and_persist(
        journey_id,
        request_token="selector-switch-v0-2",
        route_choice_event_id=route.event_id,
        route_choice_event_sequence=route.event_sequence,
    )

    assert v0_1.journeys.get_state(journey_id).active_preliminary_result is not None
    assert (
        v0_1.journeys.get_state(journey_id).active_preliminary_result.output_schema_version
        == "preliminary-assessment.v0.1"
    )
    assert v0_2.journeys.get_state(journey_id).active_preliminary_result is not None
    assert (
        v0_2.journeys.get_state(journey_id).active_preliminary_result.output_schema_version
        == "preliminary-assessment.v0.2"
    )
    assert len(v0_2.journeys.get_history(journey_id).runs) == 2

    monkeypatch.setenv(PRELIMINARY_EVALUATOR_ENV, "preliminary-evaluator.v0.1")
    v0_1_page = _selected_page("process_journey", assessment_id).run()
    assert not v0_1_page.exception
    assert "Preliminary result" in _rendered(v0_1_page)
    assert "Confidence describes evidence coverage" in _rendered(v0_1_page)

    monkeypatch.setenv(PRELIMINARY_EVALUATOR_ENV, "preliminary-evaluator.v0.2")
    v0_2_page = _selected_page("process_journey", assessment_id).run()
    assert not v0_2_page.exception
    assert "Preliminary Assessment" in _rendered(v0_2_page)
    assert "It is not probability, safety, implementation readiness, or approval" in _rendered(v0_2_page)
    assert any(
        item.label == "Historical technical details" for item in v0_2_page.expander
    )


def test_corrupt_v0_2_presentation_fails_safely_without_partial_customer_view(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "corrupt-v0-2-presentation.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, "1")
    monkeypatch.setenv(PRELIMINARY_EVALUATOR_ENV, "preliminary-evaluator.v0.2")
    assessment_id, journey_id = _materialized_explore(path)
    services = build_preliminary_service_bundle(
        path,
        supported_identity=preliminary_v0_2_compatibility_identity(),
    )
    state = services.journeys.get_state(journey_id)
    assert state.current_route_event is not None
    operation = services.runs.evaluate_and_persist(
        journey_id,
        request_token="corrupt-v0-2-presentation",
        route_choice_event_id=state.current_route_event.event_id,
        route_choice_event_sequence=state.current_route_event.event_sequence,
    )
    assert operation.result is not None
    connection = sqlite3.connect(path)
    try:
        row = connection.execute(
            "SELECT payload_json FROM preliminary_results_v0_2 WHERE preliminary_result_id = ?",
            (operation.result.preliminary_result_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        payload["assessment"]["activity_results"][0]["rule_set_fingerprint"] = (
            "0" * 64
        )
        payload_json = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        connection.execute("DROP TRIGGER preliminary_results_v0_2_immutable_update")
        connection.execute(
            "UPDATE preliminary_results_v0_2 SET payload_json = ?, payload_sha256 = ? WHERE preliminary_result_id = ?",
            (payload_json, digest, operation.result.preliminary_result_id),
        )
        connection.commit()
    finally:
        connection.close()

    app = _selected_page("process_journey", assessment_id).run()

    assert not app.exception
    rendered = _rendered(app)
    assert "could not be displayed safely" in rendered
    assert "No partial result has been presented" in rendered
    assert "Opportunity 1" not in rendered
    assert "rule_set_fingerprint" not in rendered


def test_materialized_journey_protects_new_strict_actions(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "protected.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, "1")
    assessment_id, _ = _materialized_explore(path)

    results = _selected_page("results", assessment_id).run()
    package = _selected_page("decision_package", assessment_id).run()

    assert not results.exception and not package.exception
    assert "This assessment continues in Process journey" in _rendered(results)
    assert not any(item.label == "Run AI-adoption assessment" for item in results.button)
    assert _button(results, "Open Process journey")
    assert "No new Decision Package will be generated" in _rendered(package)
    assert not any(item.label == "Generate decision package" for item in package.button)
    assert _button(package, "Open Process journey")


def test_route_switch_preserves_result_and_formal_lifecycle(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "switch.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, "1")
    assessment_id, journey_id = _materialized_explore(path)
    services = build_preliminary_service_bundle(path)
    explore = services.journeys.get_state(journey_id)
    assert explore.current_route_event is not None
    services.runs.evaluate_and_persist(
        journey_id,
        request_token="seed-result",
        route_choice_event_id=explore.current_route_event.event_id,
        route_choice_event_sequence=explore.current_route_event.event_sequence,
    )
    after_result = services.journeys.get_state(journey_id)
    services.journeys.select_route(
        journey_id,
        AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
        request_token="switch-organisational",
        expected_latest_sequence=after_result.latest_event_sequence,
    )

    app = _selected_page("process_journey", assessment_id).run()
    assert not app.exception
    context_only = next(
        item
        for item in app.checkbox
        if item.label
        == "Reference the latest Preliminary Assessment as context only — not formal evidence"
    )
    assert context_only.value is False
    formal_confirmation = next(
        item
        for item in app.checkbox
        if item.label
        == "I understand this does not satisfy evidence requirements or approve implementation"
    )
    app = formal_confirmation.check().run()
    app = _button(app, "Start organisational assessment setup").click().run()

    assert not app.exception
    assert "Awaiting formal inputs" in _rendered(app)
    assert "supporting evidence" in _rendered(app).lower()

    app = app.checkbox(key=f"confirm-route-{journey_id}-EXPLORE_PROCESS").check().run()
    app = _button(app, "Explore this process").click().run()

    assert not app.exception
    rendered = _rendered(app)
    assert "Organisational assessment setup retained" in rendered
    assert "Preliminary result" in rendered


def test_interrupted_run_can_be_explicitly_abandoned_retried_and_rerun(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "recovery.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, "1")
    assessment_id, journey_id = _materialized_explore(path)
    services = build_preliminary_service_bundle(path)
    state = services.journeys.get_state(journey_id)
    assert state.current_route_event is not None
    original = services.runs._journeys._insert_journey_event

    def interrupt_terminal_write(connection, event):
        if event.event_type.value == "RESULT_RECORDED":
            raise sqlite3.OperationalError("simulated interrupted finalization")
        return original(connection, event)

    monkeypatch.setattr(
        services.runs._journeys,
        "_insert_journey_event",
        interrupt_terminal_write,
    )
    with pytest.raises(PreliminaryRunFinalizationError):
        services.runs.evaluate_and_persist(
            journey_id,
            request_token="interrupted-run",
            route_choice_event_id=state.current_route_event.event_id,
            route_choice_event_sequence=state.current_route_event.event_sequence,
        )
    running = services.journeys.get_history(journey_id).runs[0]

    app = _selected_page("process_journey", assessment_id).run()
    assert not app.exception
    assert "Preliminary Assessment running" in _rendered(app)
    assert _button(app, "Mark run as interrupted").disabled

    app = app.checkbox(
        key=f"confirm-abandon-{running.manifest.preliminary_run_id}"
    ).check().run()
    app = _button(app, "Mark run as interrupted").click().run()

    assert not app.exception
    assert "failed or was interrupted" in _rendered(app)
    app = _button(app, "Retry Preliminary Assessment").click().run()
    assert not app.exception
    assert "Preliminary result" in _rendered(app)

    confirmation = next(
        item
        for item in app.checkbox
        if item.label == "I understand that a new run creates a new immutable result"
    )
    app = confirmation.check().run()
    app = _button(app, "Run a new Preliminary Assessment").click().run()

    assert not app.exception
    history = build_preliminary_service_bundle(path).journeys.get_history(journey_id)
    assert len(history.runs) == 3
    assert history.runs[0].result is not None
    assert history.runs[1].result is not None
    assert history.runs[2].status.value == "ABANDONED"


def test_failed_run_exposes_retry_without_raw_failure_details(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "failed.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, "1")
    assessment_id, journey_id = _materialized_explore(path)
    services = build_preliminary_service_bundle(path)
    state = services.journeys.get_state(journey_id)
    assert state.current_route_event is not None
    failure = PreliminaryEvaluationFailure(
        rule_set=PRELIMINARY_EVALUATOR_RULES_V0_1.reference(),
        errors=(
            PreliminaryEvaluationError(
                code=PreliminaryEvaluationFailureCode.OUTPUT_VALIDATION_FAILED,
                message="Injected typed failure for presentation coverage.",
            ),
        ),
    )
    monkeypatch.setattr(
        PreliminaryAssessmentEvaluator,
        "evaluate",
        lambda self, approved: failure,
    )
    runner = PreliminaryRunResultService(services.store)
    operation = runner.evaluate_and_persist(
        journey_id,
        request_token="typed-failure",
        route_choice_event_id=state.current_route_event.event_id,
        route_choice_event_sequence=state.current_route_event.event_sequence,
    )
    assert operation.status.value == "FAILED"

    app = _selected_page("process_journey", assessment_id).run()

    assert not app.exception
    assert "failed or was interrupted" in _rendered(app)
    assert _button(app, "Retry Preliminary Assessment")
    assert "Injected typed failure" not in _rendered(app)


def test_approved_page_recovers_partial_journey_materialisation(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "partial-materialisation.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, "1")
    assessment_id, pin = _approved_workspace(path)
    services = build_preliminary_service_bundle(path)
    created = services.journeys.create_or_reuse_journey(pin)
    assert services.journeys.get_state(created.journey.journey_id).current_route_event is None
    script = (
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment_id!r}\n"
        "from ai_adoption_engine.models.preliminary_assessment import AssessmentJourney\n"
        "from ai_adoption_engine.presentation.context import hydrate_workspace\n"
        "from ai_adoption_engine.presentation.preliminary_ui import set_route_intent\n"
        "from ai_adoption_engine.presentation.pages import review\n"
        "review.switch_to_registered_page = lambda page: True\n"
        "snapshot = hydrate_workspace()\n"
        "set_route_intent(snapshot, AssessmentJourney.EXPLORE_PROCESS)\n"
        "review.render()\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()
    assert not app.exception
    assert "Journey setup incomplete" in _rendered(app)
    assert "approval remains valid" in _rendered(app)

    app = _button(app, "Continue journey setup").click().run()

    assert not app.exception
    state = build_preliminary_service_bundle(path).journeys.get_state(
        created.journey.journey_id
    )
    assert state.current_route.value == "EXPLORE_PROCESS"
    assert state.preliminary_status.value == "AVAILABLE"
    history = build_preliminary_service_bundle(path).journeys.get_history(
        created.journey.journey_id
    )
    assert len(history.runs) == 1
    assert history.runs[0].result is not None
    app = app.run()
    assert _button(app, "Open Preliminary Assessment")


def test_corrupt_history_fails_closed_in_process_journey(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "corrupt-history.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(FEATURE_FLAG, "1")
    assessment_id, journey_id = _materialized_explore(path)
    services = build_preliminary_service_bundle(path)
    state = services.journeys.get_state(journey_id)
    assert state.current_route_event is not None
    operation = services.runs.evaluate_and_persist(
        journey_id,
        request_token="corrupt-result",
        route_choice_event_id=state.current_route_event.event_id,
        route_choice_event_sequence=state.current_route_event.event_sequence,
    )
    assert operation.result is not None
    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP TRIGGER preliminary_results_immutable_update")
        connection.execute(
            "UPDATE preliminary_results SET payload_sha256 = ? WHERE preliminary_result_id = ?",
            ("0" * 64, operation.result.preliminary_result_id),
        )
        connection.commit()
    finally:
        connection.close()

    app = _selected_page("process_journey", assessment_id).run()

    assert not app.exception
    assert "unsupported or corrupt" in _rendered(app)
    assert not any(
        item.label in {"Run Preliminary Assessment", "Retry Preliminary Assessment"}
        for item in app.button
    )

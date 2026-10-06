from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from ai_adoption_engine.decision.four_gate_engine import FourGateAssessmentEngine
from ai_adoption_engine.formal.composition import (
    DEFAULT_FOUR_GATE_POLICY,
    build_formal_assessment_service_bundle,
)
from ai_adoption_engine.formal.input_adapter import FormalFourGateInputAdapter
from ai_adoption_engine.formal.run_service import (
    FormalAssessmentRunService,
    FormalRunCompleted,
)
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.formal_assessment import (
    FormalAssessmentInputMode,
    FormalAssessmentResult,
    FormalRunStatus,
    FormalValueOrigin,
    SupportingEvidenceDisposition,
)
from ai_adoption_engine.models.formal_evidence import (
    CriterionFormalTarget,
    DocumentCategory,
    EvidenceClassification,
    FormalTargetKind,
    ReviewAction,
)
from ai_adoption_engine.persistence.formal_assessment import (
    SQLiteFormalAssessmentRepository,
)
from ai_adoption_engine.persistence.formal_evidence import SQLiteFormalEvidenceRepository
from ai_adoption_engine.preliminary.composition import build_preliminary_service_bundle
from ai_adoption_engine.presentation import formal_assessment_ui as ui_module
from ai_adoption_engine.presentation.formal_assessment_ui import (
    FORMAL_ASSESSMENT_UI_ENV,
    formal_assessment_ui_enabled,
)
from ai_adoption_engine.presentation.formal_assessment_workflow import (
    EXCLUSION_CONFIRMATION,
)
from ai_adoption_engine.presentation.supporting_evidence_ui import (
    SUPPORTING_EVIDENCE_UI_ENV,
)
from ai_adoption_engine.models.preliminary_assessment import AssessmentJourney
from ai_adoption_engine.supporting_evidence.composition import (
    build_supporting_evidence_service_bundle,
)
from ai_adoption_engine.supporting_evidence.extraction import (
    SupportingEvidenceExtractionService,
)
from ai_adoption_engine.supporting_evidence.provider import (
    SUPPORTING_EVIDENCE_PROVIDER_SCHEMA,
    RawSupportingCitation,
    RawSupportingEvidenceBatch,
    RawSupportingEvidenceItem,
    ScriptedSupportingEvidenceProvider,
)
from tests.ui.test_supporting_evidence_ui import (
    PRELIMINARY_FLAG,
    _formal_lifecycle,
    _page,
    _rendered,
    _reviewer,
)


COMPLETED = "Organisational assessment completed — review required"


@dataclass
class CountingEngine(FourGateAssessmentEngine):
    policy: object
    calls: int = 0

    def assess(self, process):
        self.calls += 1
        return super().assess(process)


class FailingEngine(FourGateAssessmentEngine):
    def assess(self, process):
        del process
        raise RuntimeError("engine unavailable")


class EngineLog:
    """Counts every strict-engine construction and invocation."""

    def __init__(self) -> None:
        self.engines: list[CountingEngine] = []
        self.fail = False

    def __call__(self, policy):
        if self.fail:
            return FailingEngine(policy)
        engine = CountingEngine(policy)
        self.engines.append(engine)
        return engine

    @property
    def calls(self) -> int:
        return sum(item.calls for item in self.engines)


def _bundle(path: Path, log: EngineLog, **kwargs):
    return build_formal_assessment_service_bundle(
        path,
        run_service_factory=lambda repository, *, policy_path, adapter: FormalAssessmentRunService(
            repository,
            policy_path=policy_path,
            adapter=adapter,
            engine_factory=log,
        ),
        **kwargs,
    )


def _enable(monkeypatch, path: Path, bundle=None, *, supporting: bool = False) -> None:
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(PRELIMINARY_FLAG, "1")
    monkeypatch.setenv(FORMAL_ASSESSMENT_UI_ENV, "1")
    if supporting:
        monkeypatch.setenv(SUPPORTING_EVIDENCE_UI_ENV, "1")
    else:
        monkeypatch.delenv(SUPPORTING_EVIDENCE_UI_ENV, raising=False)
    if bundle is not None:
        monkeypatch.setattr(
            ui_module,
            "_cached_formal_assessment_services",
            lambda database_path, policy_path: bundle,
        )


def _keyed(items, prefix: str):
    return next(item for item in items if item.key and item.key.startswith(prefix))


def _choose(app: AppTest, lifecycle_id: str, mode: FormalAssessmentInputMode) -> AppTest:
    return _keyed(app.radio, f"formal-input-mode-{lifecycle_id}").set_value(mode).run()


def _prepare(app: AppTest, lifecycle_id: str, mode: FormalAssessmentInputMode) -> AppTest:
    return _keyed(app.button, f"prepare-formal-{lifecycle_id}-{mode.value}").click().run()


def _attempt(app: AppTest) -> AppTest:
    app = _keyed(app.checkbox, "final-formal-confirm-").check().run()
    return _keyed(app.button, "run-formal-").click().run()


def _declare(app: AppTest, prefix: str) -> AppTest:
    app = _keyed(app.text_input, f"{prefix}-name").set_value("Casey Reviewer").run()
    app = _keyed(app.text_input, f"{prefix}-role").set_value("Operations lead").run()
    return _keyed(app.checkbox, f"{prefix}-local-authority").check().run()


def _exclude(app: AppTest, lifecycle_id: str) -> AppTest:
    app = _declare(app, f"exclude-{lifecycle_id}")
    app = _keyed(app.text_area, f"exclude-reason-{lifecycle_id}").set_value(
        "This run deliberately uses the approved process only."
    ).run()
    return _keyed(app.text_input, f"exclude-confirm-{lifecycle_id}").set_value(
        EXCLUSION_CONFIRMATION
    ).run()


def _tables(path: Path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    finally:
        connection.close()


def _supporting_rows(path: Path) -> dict[str, int]:
    connection = sqlite3.connect(path)
    try:
        names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name LIKE 'preliminary_supporting_%'"
            )
        ]
        return {
            name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            for name in names
        }
    finally:
        connection.close()


def _seed_document(path: Path, lifecycle_id: str, filename: str = "volumes.txt"):
    bundle = build_supporting_evidence_service_bundle(
        path, provider_factory=lambda: (_ for _ in ()).throw(AssertionError("unused"))
    )
    lineage = bundle.repository.load_active_lineage(lifecycle_id)
    intake = bundle.intake.accept(
        lineage=lineage,
        request_token=f"seed-{filename}",
        filename=filename,
        raw_bytes=b"Monthly complaint volume is 100.",
        description="Monthly volume",
        primary_category=DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
        submitter=_reviewer(),
    )
    ingested = bundle.ingestion.ingest(
        lineage=lineage,
        document_id=intake.document.document_id,
        request_token=f"seed-{filename}-ingest",
    )
    return bundle, lineage, intake, ingested


def _ready_supporting(path: Path, lifecycle_id: str, mappings):
    """Create exact current ready supporting evidence through Slice 3–5 services."""

    bundle, lineage, intake, ingested = _seed_document(path, lifecycle_id)
    block = ingested.ingested_document.blocks[0]
    activity_id = bundle.repository.approved_activity_catalog(lineage)[0][0]
    items = tuple(
        RawSupportingEvidenceItem(
            proposed_claim=f"Reviewed claim {index}.",
            proposed_classification=EvidenceClassification.DOCUMENTED_FACT,
            primary_citation=RawSupportingCitation(
                document_id=intake.document.document_id,
                block_id=block.block_id,
                exact_excerpt=block.extracted_text,
            ),
            proposed_category=DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
            suggested_activity_ids=(activity_id,),
            ambiguity_indicated=False,
            conflict_indicated=False,
            relevance_explanation="May inform formal review.",
            extraction_confidence=0.9,
        )
        for index in range(1, len(mappings) + 1)
    )
    provider = ScriptedSupportingEvidenceProvider(
        (RawSupportingEvidenceBatch(schema_version=SUPPORTING_EVIDENCE_PROVIDER_SCHEMA, items=items),)
    )
    extraction = SupportingEvidenceExtractionService(bundle.repository, provider).extract(
        lineage=lineage,
        document_id=intake.document.document_id,
        ingestion_attempt_id=ingested.attempt.attempt_id,
        request_token="seed-extract",
    )
    for index, (proposal, (target, value)) in enumerate(
        zip(extraction.proposals, mappings, strict=True)
    ):
        review = bundle.reviews.review_proposal(
            lifecycle_id,
            proposal.proposal_id,
            request_token=f"seed-review-{index}",
            expected_prior_revision_id=None,
            action=ReviewAction.ACCEPT,
            reviewer=_reviewer(),
            approved_claim=None,
            selected_category=DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
            approved_classification=EvidenceClassification.DOCUMENTED_FACT,
            claim_directly_supported_by_excerpt=True,
            rationale="The unchanged excerpt directly supports this claim.",
        )
        bundle.formal_inputs.map_reviewed_evidence(
            lifecycle_id,
            review.revision.revision_id,
            request_token=f"seed-map-{index}",
            expected_prior_mapping_id=None,
            activity_id=activity_id,
            target=target,
            value=value,
            knowledge_state=KnowledgeState.KNOWN,
            approved_evidence_classification=EvidenceClassification.DOCUMENTED_FACT,
            reviewer=_reviewer(),
            rationale="The reviewer explicitly approves this typed formal value.",
        )
    candidate = bundle.formal_inputs.prepare_candidate_set(
        lifecycle_id, request_token="seed-candidate"
    )
    readiness = bundle.formal_inputs.evaluate_and_persist_readiness(
        lifecycle_id,
        candidate.candidate_set.candidate_set_id,
        request_token="seed-readiness",
    )
    assert readiness.readiness.status.value == "READY_TO_ATTEMPT"
    return SimpleNamespace(
        bundle=bundle,
        activity_id=activity_id,
        candidate=candidate.candidate_set,
        readiness=readiness.readiness,
    )


def _criterion_states(path: Path, lifecycle_id: str):
    """Return one known and one unknown criterion of the first approved activity."""

    lineage = SQLiteFormalEvidenceRepository(path).load_active_lineage(lifecycle_id)
    connection = sqlite3.connect(path)
    try:
        payload = connection.execute(
            "SELECT payload_json FROM assessment_artifacts WHERE artifact_id = ?",
            (lineage.approved_review_artifact_id,),
        ).fetchone()[0]
    finally:
        connection.close()
    from ai_adoption_engine.models.review import ApprovedProcessReview

    approved = ApprovedProcessReview.model_validate_json(payload)
    step = approved.business_process.steps[0]
    known = unknown = None
    for name in CriterionName:
        value = step.characteristics.criterion(name)
        if value.knowledge_state is KnowledgeState.KNOWN and known is None:
            known = (name, value.value)
        if value.knowledge_state is KnowledgeState.UNKNOWN and unknown is None:
            unknown = name
    return known, unknown



def _formal_lifecycle_with_known(path: Path) -> tuple[str, str, str]:
    """Approve the demo process with one document-supported known criterion."""

    from ai_adoption_engine.models.review import InformationOrigin
    from ai_adoption_engine.models.preliminary_journey import ApprovedReviewArtifactPin
    from ai_adoption_engine.workspace.composition import build_workspace_service
    from ai_adoption_engine.workspace.demo_extraction import demo_text
    from ai_adoption_engine.workspace.models import ArtifactType, ExecutionMode

    service = build_workspace_service(path)
    assessment_id = service.repository.create_assessment(
        "Formal assessment UI", ExecutionMode.OFFLINE_DEMO
    ).assessment_id
    service.ingest_upload(assessment_id, raw_text=demo_text())
    service.extract(assessment_id)
    session = service.start_review(assessment_id)
    review = service.review_service
    review.accept_assertion(session, session.process_name, "process.name")
    for step in session.steps:
        review.accept_assertion(session, step.activity, f"steps.{step.candidate_step_id}.activity")
    first = session.steps[0]
    index, criterion = next(
        (index, item)
        for index, item in enumerate(first.criteria)
        if item.name is CriterionName.DATA_READINESS
    )
    review.resolve_unknown(
        session,
        criterion.assertion,
        f"steps.{first.candidate_step_id}.criteria[{index}]",
        3,
        rationale="The documented workflow supports a limited readiness value.",
        origin=InformationOrigin.DOCUMENT_SUPPORTED,
        evidence=list(first.activity.evidence),
    )
    review.accept_step_order(session)
    service.save_review(assessment_id, session)
    assert service.approve(assessment_id).approved is not None
    artifact = service.repository.load_workspace(assessment_id).active_artifacts[
        ArtifactType.APPROVED_REVIEW
    ]
    pin = ApprovedReviewArtifactPin(
        assessment_id=assessment_id,
        artifact_id=artifact.artifact_id,
        artifact_revision=artifact.artifact_revision,
        artifact_schema_version=artifact.artifact_schema_version,
        payload_sha256=artifact.payload_sha256,
    )
    services = build_preliminary_service_bundle(path)
    created = services.journeys.create_or_reuse_journey(pin)
    state = services.journeys.get_state(created.journey.journey_id)
    selected = services.journeys.select_route(
        created.journey.journey_id,
        AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
        request_token="formal-ui-route",
        expected_latest_sequence=state.latest_event_sequence,
    )
    result = services.formal.start_formal_lifecycle(
        created.journey.journey_id,
        request_token="formal-ui-formal",
        route_choice_event_id=selected.effective_route_event.event_id,
        route_choice_event_sequence=selected.effective_route_event.event_sequence,
    )
    return assessment_id, created.journey.journey_id, result.lifecycle.formal_lifecycle_id


def _target(name: CriterionName) -> CriterionFormalTarget:
    return CriterionFormalTarget(kind=FormalTargetKind.CRITERION, criterion=name)


def _repository(path: Path) -> SQLiteFormalAssessmentRepository:
    return SQLiteFormalAssessmentRepository(path)


# ---------------------------------------------------------------------------
# Feature flag, composition, frozen, and disabled behaviour


@pytest.mark.parametrize("value", (None, "", "0", "false", "no", "off", "enabled", "TRUE-ish"))
def test_formal_assessment_feature_is_default_off(monkeypatch, value) -> None:
    monkeypatch.setenv(PRELIMINARY_FLAG, "1")
    if value is None:
        monkeypatch.delenv(FORMAL_ASSESSMENT_UI_ENV, raising=False)
    else:
        monkeypatch.setenv(FORMAL_ASSESSMENT_UI_ENV, value)
    assert formal_assessment_ui_enabled() is False


@pytest.mark.parametrize("value", ("1", "true", "TRUE", " yes ", "on", "On"))
def test_formal_assessment_feature_accepts_only_approved_truthy_values(monkeypatch, value) -> None:
    monkeypatch.setenv(PRELIMINARY_FLAG, "1")
    monkeypatch.setenv(FORMAL_ASSESSMENT_UI_ENV, value)
    assert formal_assessment_ui_enabled() is True


def test_formal_assessment_feature_requires_preliminary_ui(monkeypatch) -> None:
    monkeypatch.delenv(PRELIMINARY_FLAG, raising=False)
    monkeypatch.setenv(FORMAL_ASSESSMENT_UI_ENV, "1")
    assert formal_assessment_ui_enabled() is False


def test_services_refuse_when_disabled_or_frozen_before_construction(monkeypatch) -> None:
    constructed = False

    def fail_if_constructed(*args, **kwargs):
        nonlocal constructed
        constructed = True
        raise AssertionError("constructed")

    monkeypatch.setattr(ui_module, "_cached_formal_assessment_services", fail_if_constructed)
    monkeypatch.setenv(PRELIMINARY_FLAG, "1")
    monkeypatch.delenv(FORMAL_ASSESSMENT_UI_ENV, raising=False)
    with pytest.raises(RuntimeError, match="not enabled"):
        ui_module.formal_assessment_services()
    monkeypatch.setenv(FORMAL_ASSESSMENT_UI_ENV, "1")
    monkeypatch.setattr(ui_module, "frozen_evaluation_workspace_selected", lambda: True)
    with pytest.raises(RuntimeError, match="frozen"):
        ui_module.formal_assessment_services()
    assert constructed is False


def test_composition_is_inert_and_uses_exact_identities(tmp_path) -> None:
    path = tmp_path / "compose.db"
    _formal_lifecycle(path)
    calls = {"policy": 0, "engine": 0, "project": 0}

    class SpyAdapter(FormalFourGateInputAdapter):
        def project(self, **kwargs):
            calls["project"] += 1
            return super().project(**kwargs)

    def policy_loader(path):
        calls["policy"] += 1
        raise AssertionError("policy loaded")

    def engine_factory(policy):
        calls["engine"] += 1
        raise AssertionError("engine constructed")

    bundle = build_formal_assessment_service_bundle(
        path,
        adapter_factory=SpyAdapter,
        run_service_factory=lambda repository, *, policy_path, adapter: FormalAssessmentRunService(
            repository,
            policy_path=policy_path,
            adapter=adapter,
            policy_loader=policy_loader,
            engine_factory=engine_factory,
        ),
    )
    assert calls == {"policy": 0, "engine": 0, "project": 0}
    assert bundle.policy_path == DEFAULT_FOUR_GATE_POLICY
    assert bundle.policy_path.name == "decision_policy.v0.3.json"
    assert bundle.runs.adapter is bundle.adapter
    assert 8 in bundle.repository.migration_versions()
    assert not hasattr(bundle, "provider")


def test_cache_identity_is_exact_database_and_policy(monkeypatch, tmp_path) -> None:
    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(
        ui_module,
        "_cached_formal_assessment_services",
        lambda database_path, policy_path: seen.append((database_path, policy_path)) or "bundle",
    )
    monkeypatch.setenv(PRELIMINARY_FLAG, "1")
    monkeypatch.setenv(FORMAL_ASSESSMENT_UI_ENV, "1")
    monkeypatch.setattr(ui_module, "frozen_evaluation_workspace_selected", lambda: False)
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(tmp_path / "exact.db"))
    assert ui_module.formal_assessment_services() == "bundle"
    assert seen == [(str(tmp_path / "exact.db"), str(DEFAULT_FOUR_GATE_POLICY))]


@pytest.mark.parametrize("value", (None, "0", "invalid"))
def test_disabled_flag_preserves_route_and_creates_no_migration_eight(
    tmp_path, monkeypatch, value
) -> None:
    path = tmp_path / "disabled.db"
    assessment_id, journey_id, _ = _formal_lifecycle(path)
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    monkeypatch.setenv(PRELIMINARY_FLAG, "1")
    monkeypatch.delenv(SUPPORTING_EVIDENCE_UI_ENV, raising=False)
    if value is None:
        monkeypatch.delenv(FORMAL_ASSESSMENT_UI_ENV, raising=False)
    else:
        monkeypatch.setenv(FORMAL_ASSESSMENT_UI_ENV, value)
    before = _tables(path)
    sidecars_before = {item.name for item in tmp_path.iterdir()}

    app = _page(assessment_id).run()

    assert not app.exception
    rendered = _rendered(app)
    assert "Awaiting formal inputs" in rendered
    assert "Supporting evidence, evidence review, formal conversion" in rendered
    assert "Choose assessment inputs" not in rendered
    after = _tables(path)
    assert after == before
    assert not any("formal_assessment" in name for name in after)
    assert {item.name for item in tmp_path.iterdir()} == sidecars_before
    assert build_preliminary_service_bundle(path).journeys.get_history(journey_id).runs == ()


def test_enabled_page_shows_unselected_explicit_choices_without_writes(tmp_path, monkeypatch) -> None:
    path = tmp_path / "choices.db"
    assessment_id, journey_id, lifecycle_id = _formal_lifecycle(path)
    log = EngineLog()
    _enable(monkeypatch, path, _bundle(path, log))

    app = _page(assessment_id).run()

    assert not app.exception
    radio = _keyed(app.radio, f"formal-input-mode-{lifecycle_id}")
    assert radio.value is None
    assert len(radio.options) == 2
    rendered = _rendered(app)
    assert "Supporting evidence is optional" in rendered
    assert "Discovery Required" in rendered
    assert "neither formal approval nor implementation authority" in rendered
    assert lifecycle_id not in rendered
    assert log.calls == 0 and log.engines == []
    assert _repository(path).lifecycle_authorizations(lifecycle_id) == ()
    assert build_preliminary_service_bundle(path).journeys.get_history(journey_id).runs == ()
    assert not any(button.key and button.key.startswith("run-formal-") for button in app.button)


# ---------------------------------------------------------------------------
# Process-only and exclusion


def test_process_only_run_without_supporting_history(tmp_path, monkeypatch) -> None:
    path = tmp_path / "process-only.db"
    assessment_id, journey_id, lifecycle_id = _formal_lifecycle(path)
    log = EngineLog()
    bundle = _bundle(path, log)
    _enable(monkeypatch, path, bundle)
    mode = FormalAssessmentInputMode.APPROVED_PROCESS_ONLY

    app = _choose(_page(assessment_id).run(), lifecycle_id, mode)
    app = _prepare(app, lifecycle_id, mode)
    assert not app.exception
    draft = app.session_state["formal_assessment_pending_drafts"][lifecycle_id]
    first_ids = (draft.authorization.authorization_id, draft.request.request_token)
    # Harmless reruns keep the same pending identities.
    app = app.run()
    app = _keyed(app.checkbox, "final-formal-confirm-").check().run()
    app = _keyed(app.checkbox, "final-formal-confirm-").uncheck().run()
    draft = app.session_state["formal_assessment_pending_drafts"][lifecycle_id]
    assert (draft.authorization.authorization_id, draft.request.request_token) == first_ids
    assert "No supporting evidence history exists" in _rendered(app)
    assert log.calls == 0

    app = _attempt(app)

    assert not app.exception
    assert log.calls == 1
    rendered = _rendered(app)
    assert COMPLETED in rendered
    assert "This result is not formal approval or implementation authority." in rendered
    assert "Approved process only" in rendered
    assert "Decision Package" not in rendered
    assert lifecycle_id not in rendered
    audit = next(item for item in app.expander if item.label == "Audit details")
    assert audit.proto.expanded is False
    repository = _repository(path)
    (authorization,) = repository.lifecycle_authorizations(lifecycle_id)
    assert authorization.authorization_id == first_ids[0]
    choice = authorization.input_choice
    assert choice.mode is mode
    assert choice.supporting_evidence_disposition is SupportingEvidenceDisposition.NO_SUPPORTING_HISTORY
    assert choice.supporting_candidate is None and choice.exclusion is None
    assert authorization.explicit_run_confirmation == "ATTEMPT ORGANISATIONAL ASSESSMENT"
    assert authorization.authorization_scope.startswith("ASSESSMENT_RUN_ATTEMPT_ONLY")
    lineage = SQLiteFormalEvidenceRepository(path).load_active_lineage(lifecycle_id)
    assert authorization.approved_process.lineage == lineage
    result = repository.current_successful_result(lifecycle_id)
    assert isinstance(result, FormalAssessmentResult)
    assert result.implementation_approval_granted is False
    assert result.decision_package_generated is False
    guidance = repository.load_evidence_guidance(f"formal-guidance-{result.result_id}")
    assert guidance.source_result == result
    # No migration-7 supporting records were needed or created.
    assert all(count == 0 for count in _supporting_rows(path).values())
    assert build_preliminary_service_bundle(path).journeys.get_history(journey_id).runs == ()

    # Reruns render the persisted result without reinvoking the engine or
    # rederiving guidance.
    app = app.run()
    assert COMPLETED in _rendered(app)
    assert log.calls == 1
    assert repository.load_evidence_guidance(f"formal-guidance-{result.result_id}") == guidance

    # Restart replay of the exact root request returns the persisted outcome.
    restarted_log = EngineLog()
    restarted = _bundle(path, restarted_log)
    token = authorization.request.request_token.removesuffix(":authorize")
    from ai_adoption_engine.presentation.formal_assessment_workflow import _request

    replay = restarted.runs.execute(
        authorization,
        approved_review=_approved(path, lineage),
        request=_request(token, "run-organisational-assessment"),
    )
    assert isinstance(replay, FormalRunCompleted) and replay.replayed
    assert replay.result == result
    assert restarted_log.calls == 0


def _approved(path: Path, lineage):
    from ai_adoption_engine.models.review import ApprovedProcessReview

    connection = sqlite3.connect(path)
    try:
        payload = connection.execute(
            "SELECT payload_json FROM assessment_artifacts WHERE artifact_id = ?",
            (lineage.approved_review_artifact_id,),
        ).fetchone()[0]
    finally:
        connection.close()
    return ApprovedProcessReview.model_validate_json(payload)


def test_duplicate_click_after_unconfirmed_outcome_replays_without_reinvocation(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "double.db"
    assessment_id, _, lifecycle_id = _formal_lifecycle(path)
    log = EngineLog()
    bundle = _bundle(path, log)
    real_execute = bundle.runs.execute
    calls = 0

    def execute_then_lose_response(*args, **kwargs):
        nonlocal calls
        calls += 1
        outcome = real_execute(*args, **kwargs)
        if calls == 1:
            raise RuntimeError("response lost after persistence")
        return outcome

    object.__setattr__(bundle.runs, "execute", execute_then_lose_response)
    _enable(monkeypatch, path, bundle)
    mode = FormalAssessmentInputMode.APPROVED_PROCESS_ONLY
    app = _prepare(_choose(_page(assessment_id).run(), lifecycle_id, mode), lifecycle_id, mode)
    app = _attempt(app)
    assert not app.exception
    assert "never runs it twice" in _rendered(app)
    assert log.calls == 1

    app = _keyed(app.button, "run-formal-").click().run()

    assert not app.exception
    assert calls == 2
    assert log.calls == 1
    assert COMPLETED in _rendered(app)
    assert len(_repository(path).lifecycle_authorizations(lifecycle_id)) == 1


def test_existing_history_requires_exact_exclusion_and_preserves_history(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "exclusion.db"
    assessment_id, _, lifecycle_id = _formal_lifecycle(path)
    _, _, intake, _ = _seed_document(path, lifecycle_id, "outdated-policy.txt")
    supporting_before = _supporting_rows(path)
    log = EngineLog()
    _enable(monkeypatch, path, _bundle(path, log))
    mode = FormalAssessmentInputMode.APPROVED_PROCESS_ONLY

    app = _choose(_page(assessment_id).run(), lifecycle_id, mode)
    rendered = _rendered(app)
    assert "cannot be silently ignored" in rendered
    assert "outdated-policy.txt" in rendered
    assert "remain available for a future run" in rendered

    # Without the declaration, rationale, and exact confirmation, nothing is prepared.
    app = _prepare(app, lifecycle_id, mode)
    assert "could not be prepared" in _rendered(app)
    assert lifecycle_id not in app.session_state["formal_assessment_pending_drafts"]
    app = _declare(app, f"exclude-{lifecycle_id}")
    app = _keyed(app.text_area, f"exclude-reason-{lifecycle_id}").set_value("Use source only.").run()
    app = _keyed(app.text_input, f"exclude-confirm-{lifecycle_id}").set_value(
        "exclude current supporting evidence"
    ).run()
    app = _prepare(app, lifecycle_id, mode)
    assert "could not be prepared" in _rendered(app)

    app = _exclude(app, lifecycle_id)
    app = _prepare(app, lifecycle_id, mode)
    assert "Excluded from this run only: outdated-policy.txt" in _rendered(app)
    app = _attempt(app)

    assert not app.exception
    assert log.calls == 1
    assert COMPLETED in _rendered(app)
    (authorization,) = _repository(path).lifecycle_authorizations(lifecycle_id)
    choice = authorization.input_choice
    assert choice.supporting_evidence_disposition is (
        SupportingEvidenceDisposition.CURRENT_SUPPORTING_EVIDENCE_EXPLICITLY_EXCLUDED
    )
    exclusion = choice.exclusion
    evidence = SQLiteFormalEvidenceRepository(path)
    head = evidence.latest_workflow_event(lifecycle_id)
    metadata = evidence.metadata_revisions_for_document(lifecycle_id, intake.document.document_id)
    assert exclusion.supporting_history_head_id == head.event_id
    assert len(exclusion.supporting_history_head_sha256) == 64
    assert [(item.document_id, item.document_content_sha256, item.metadata_revision_id) for item in exclusion.current_documents] == [
        (intake.document.document_id, intake.document.source_blob_sha256, metadata[-1].revision_id)
    ]
    assert exclusion.declarant.reviewer_display_name == "Casey Reviewer"
    assert exclusion.declarant.declared_organisational_role == "Operations lead"
    assert exclusion.declarant.identity_and_authority_locally_declared_not_authenticated is True
    assert exclusion.confirmation == EXCLUSION_CONFIRMATION
    assert exclusion.rationale == "This run deliberately uses the approved process only."
    assert exclusion.history_effect == "REFERENCE_ONLY_NO_DELETE_SUPERSESSION_OR_REWRITE"
    assert exclusion.request.request_token.endswith(":exclude")
    # Supporting history is untouched and still current.
    assert _supporting_rows(path) == supporting_before
    assert evidence.current_documents(lifecycle_id)[0].document_id == intake.document.document_id


def test_supporting_ui_disabled_still_requires_exclusion_and_offers_no_uploads(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "supporting-off.db"
    assessment_id, _, lifecycle_id = _formal_lifecycle(path)
    _seed_document(path, lifecycle_id)
    log = EngineLog()
    _enable(monkeypatch, path, _bundle(path, log), supporting=False)

    supporting = FormalAssessmentInputMode.APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE
    app = _choose(_page(assessment_id).run(), lifecycle_id, supporting)
    rendered = _rendered(app)
    assert "not available in this deployment" in rendered
    assert "explicitly exclude the current supporting history" in rendered
    assert not app.file_uploader
    assert not any(item.key and item.key.startswith("prepare-formal-") for item in app.button)

    process_only = FormalAssessmentInputMode.APPROVED_PROCESS_ONLY
    app = _choose(app, lifecycle_id, process_only)
    app = _prepare(app, lifecycle_id, process_only)
    assert "could not be prepared" in _rendered(app)
    app = _prepare(_exclude(app, lifecycle_id), lifecycle_id, process_only)
    app = _attempt(app)
    assert COMPLETED in _rendered(app)
    assert log.calls == 1


def test_incomplete_supporting_evidence_blocks_inclusion_and_shows_workflow(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "incomplete.db"
    assessment_id, _, lifecycle_id = _formal_lifecycle(path)
    _seed_document(path, lifecycle_id)
    log = EngineLog()
    _enable(monkeypatch, path, _bundle(path, log), supporting=True)
    monkeypatch.setattr(
        "ai_adoption_engine.presentation.supporting_evidence_ui._cached_supporting_evidence_services",
        lambda database_path: build_supporting_evidence_service_bundle(
            database_path,
            provider_factory=lambda: (_ for _ in ()).throw(AssertionError("unused")),
        ),
    )
    mode = FormalAssessmentInputMode.APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE

    app = _choose(_page(assessment_id).run(), lifecycle_id, mode)

    assert not app.exception
    rendered = _rendered(app)
    assert "not yet been reviewed, mapped, and prepared" in rendered
    assert "1. Add documents" in rendered
    assert not any(item.key and item.key.startswith("prepare-formal-") for item in app.button)
    assert _repository(path).lifecycle_authorizations(lifecycle_id) == ()
    assert log.calls == 0


def test_ready_supporting_evidence_run_pins_exact_candidate(tmp_path, monkeypatch) -> None:
    path = tmp_path / "supporting.db"
    assessment_id, journey_id, lifecycle_id = _formal_lifecycle(path)
    _, unknown = _criterion_states(path, lifecycle_id)
    assert unknown is not None
    ready = _ready_supporting(path, lifecycle_id, ((_target(unknown), 4),))
    supporting_before = _supporting_rows(path)
    log = EngineLog()
    _enable(monkeypatch, path, _bundle(path, log))
    mode = FormalAssessmentInputMode.APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE

    app = _choose(_page(assessment_id).run(), lifecycle_id, mode)
    assert "Ready supporting evidence is available" in _rendered(app)
    app = _prepare(app, lifecycle_id, mode)
    assert not any(item.key and "-record" in item.key for item in app.button)
    assert "Current ready supporting evidence is included" in _rendered(app)
    app = _attempt(app)

    assert not app.exception
    assert log.calls == 1
    rendered = _rendered(app)
    assert COMPLETED in rendered
    assert "Approved process with supporting evidence" in rendered
    (authorization,) = _repository(path).lifecycle_authorizations(lifecycle_id)
    pin = authorization.input_choice.supporting_candidate
    assert pin.candidate_set_id == ready.candidate.candidate_set_id
    assert pin.readiness_id == ready.readiness.readiness_id
    assert pin.readiness_status == "READY_TO_ATTEMPT"
    assert authorization.conflict_resolutions == ()
    result = _repository(path).current_successful_result(lifecycle_id)
    step = result.manifest.projection.engine_input.steps[0]
    assert step.characteristics.criterion(unknown).value == 4
    assert _supporting_rows(path) == supporting_before
    assert build_preliminary_service_bundle(path).journeys.get_history(journey_id).runs == ()


def test_known_source_conflict_requires_explicit_human_resolution(tmp_path, monkeypatch) -> None:
    path = tmp_path / "conflict.db"
    assessment_id, _, lifecycle_id = _formal_lifecycle_with_known(path)
    known, _ = _criterion_states(path, lifecycle_id)
    assert known is not None
    name, value = known
    other = (value + 1) % 6
    _ready_supporting(path, lifecycle_id, ((_target(name), other),))
    log = EngineLog()
    _enable(monkeypatch, path, _bundle(path, log))
    mode = FormalAssessmentInputMode.APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE

    app = _prepare(_choose(_page(assessment_id).run(), lifecycle_id, mode), lifecycle_id, mode)
    assert not app.exception
    rendered = _rendered(app)
    assert "Resolve conflicting values" in rendered
    assert "Record a resolution for every conflict" in rendered
    assert not any(item.key and item.key.startswith("run-formal-") for item in app.button)
    selection = _keyed(app.radio, "formal-conflict-")
    assert selection.value is None
    labels = list(selection.options)
    assert any("Approved process" in item for item in labels)
    assert any("Reviewed supporting evidence" in item for item in labels)
    record = next(item for item in app.button if item.key and item.key.endswith("-record"))
    assert record.disabled

    prefix = selection.key.removesuffix("-selection")
    supporting_index = next(
        index for index, label in enumerate(labels) if "Reviewed supporting evidence" in label
    )
    app = selection.set_value(supporting_index).run()
    app = _declare(app, prefix)
    app = _keyed(app.text_area, f"{prefix}-rationale").set_value(
        "The reviewed report is more recent than the source document."
    ).run()
    record = next(item for item in app.button if item.key == f"{prefix}-record")
    assert record.disabled  # explicit confirmation still missing
    app = _keyed(app.checkbox, f"{prefix}-confirm").check().run()
    app = next(item for item in app.button if item.key == f"{prefix}-record").click().run()
    assert "Selected for this run" in _rendered(app)
    assert log.calls == 0
    app = _attempt(app)

    assert not app.exception
    assert log.calls == 1
    (authorization,) = _repository(path).lifecycle_authorizations(lifecycle_id)
    (resolution,) = authorization.conflict_resolutions
    assert resolution.selected_value == other
    assert resolution.explicit_human_selection is True
    assert resolution.reviewer.reviewer_display_name == "Casey Reviewer"
    assert resolution.rationale.startswith("The reviewed report")
    assert {item.origin for item in resolution.alternatives} == {
        FormalValueOrigin.APPROVED_PROCESS,
        FormalValueOrigin.SUPPORTING_MAPPING,
    }
    assert resolution.run_lineage == authorization.run_lineage
    result = _repository(path).current_successful_result(lifecycle_id)
    assert result.manifest.projection.engine_input.steps[0].characteristics.criterion(name).value == other


def test_supporting_vs_supporting_conflict_and_identical_values(tmp_path, monkeypatch) -> None:
    path = tmp_path / "support-conflict.db"
    assessment_id, _, lifecycle_id = _formal_lifecycle_with_known(path)
    known, unknown = _criterion_states(path, lifecycle_id)
    assert known is not None and unknown is not None
    # Identical corroborating value creates no conflict; differing values over an
    # unknown create exactly one supporting-only conflict.
    _ready_supporting(
        path,
        lifecycle_id,
        ((_target(known[0]), known[1]), (_target(unknown), 2), (_target(unknown), 5)),
    )
    log = EngineLog()
    _enable(monkeypatch, path, _bundle(path, log))
    mode = FormalAssessmentInputMode.APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE

    app = _prepare(_choose(_page(assessment_id).run(), lifecycle_id, mode), lifecycle_id, mode)
    draft = app.session_state["formal_assessment_pending_drafts"][lifecycle_id]
    assert len(draft.conflicts) == 1
    (alternatives,) = draft.conflicts
    assert {item.origin for item in alternatives} == {FormalValueOrigin.SUPPORTING_MAPPING}
    assert {item.value for item in alternatives} == {2, 5}
    selection = _keyed(app.radio, "formal-conflict-")
    prefix = selection.key.removesuffix("-selection")
    app = selection.set_value(0).run()
    app = _declare(app, prefix)
    app = _keyed(app.text_area, f"{prefix}-rationale").set_value("Chosen explicitly.").run()
    app = _keyed(app.checkbox, f"{prefix}-confirm").check().run()
    app = next(item for item in app.button if item.key == f"{prefix}-record").click().run()
    app = _attempt(app)

    assert not app.exception
    assert log.calls == 1
    result = _repository(path).current_successful_result(lifecycle_id)
    traces = {
        (trace.target.criterion if trace.target.kind is FormalTargetKind.CRITERION else None): trace
        for activity in result.manifest.projection.activities[:1]
        for trace in activity.field_resolutions
    }
    assert traces[known[0]].origin.value == "CORROBORATED"
    assert traces[unknown].origin.value == "EXPLICITLY_RESOLVED"


# ---------------------------------------------------------------------------
# Outcomes, recovery, history, and supersession


def test_pre_run_rejection_persists_nothing_and_returns_to_inputs(tmp_path, monkeypatch) -> None:
    path = tmp_path / "rejection.db"
    assessment_id, _, lifecycle_id = _formal_lifecycle(path)
    log = EngineLog()

    class RejectingAdapter(FormalFourGateInputAdapter):
        def project(self, **kwargs):
            return super().project(**{**kwargs, "approved_review": None})

    _enable(monkeypatch, path, _bundle(path, log, adapter_factory=RejectingAdapter))
    mode = FormalAssessmentInputMode.APPROVED_PROCESS_ONLY
    app = _attempt(_prepare(_choose(_page(assessment_id).run(), lifecycle_id, mode), lifecycle_id, mode))

    assert not app.exception
    rendered = _rendered(app)
    assert "no longer match the exact current approved process" in rendered
    assert "Traceback" not in rendered and "INVALID" not in rendered
    assert log.calls == 0
    assert _repository(path).lifecycle_authorizations(lifecycle_id) == ()
    assert lifecycle_id not in app.session_state["formal_assessment_pending_drafts"]
    assert any(item.key == f"prepare-formal-{lifecycle_id}-{mode.value}" for item in app.button)


def test_terminal_failure_explicit_retry_uses_original_projection(tmp_path, monkeypatch) -> None:
    path = tmp_path / "retry.db"
    assessment_id, _, lifecycle_id = _formal_lifecycle(path)
    log = EngineLog()
    log.fail = True
    _enable(monkeypatch, path, _bundle(path, log))
    mode = FormalAssessmentInputMode.APPROVED_PROCESS_ONLY
    app = _attempt(_prepare(_choose(_page(assessment_id).run(), lifecycle_id, mode), lifecycle_id, mode))

    assert not app.exception
    rendered = _rendered(app)
    assert "No completed organisational assessment result was created" in rendered
    assert "Failed — no completed result was created" in rendered
    assert "engine unavailable" not in rendered
    (authorization,) = _repository(path).lifecycle_authorizations(lifecycle_id)
    run_id = authorization.run_lineage.run_id
    # No automatic retry: a rerun leaves the failed attempt untouched.
    app = app.run()
    assert len(_repository(path).run_history(run_id).manifests) == 1

    log.fail = False
    app = _keyed(app.button, f"retry-available-{authorization.authorization_id}").click().run()
    assert "Retry available" in _rendered(app)
    assert "Retry uses the original immutable inputs" in _rendered(app)
    app = _keyed(app.button, f"retry-{authorization.authorization_id}").click().run()

    assert not app.exception
    assert log.calls == 1
    assert COMPLETED in _rendered(app)
    history = _repository(path).run_history(run_id)
    assert len(history.manifests) == 2
    assert history.manifests[1].projection == history.manifests[0].projection
    assert history.manifests[1].authorization == authorization
    assert len(_repository(path).lifecycle_authorizations(lifecycle_id)) == 1


def _interrupting_bundle(path: Path, log: EngineLog):
    state = {"armed": True}

    def inject(stage: str) -> None:
        if state["armed"] and stage == "APPEND_RUN_EVENT":
            state["armed"] = False
            raise RuntimeError("final write failure")

    return _bundle(
        path,
        log,
        repository_factory=lambda database_path: SQLiteFormalAssessmentRepository(
            database_path, failure_injector=inject
        ),
    )


def test_recovery_required_interrupt_then_abandon_is_explicit(tmp_path, monkeypatch) -> None:
    path = tmp_path / "recovery.db"
    assessment_id, _, lifecycle_id = _formal_lifecycle(path)
    log = EngineLog()
    _enable(monkeypatch, path, _interrupting_bundle(path, log))
    mode = FormalAssessmentInputMode.APPROVED_PROCESS_ONLY
    app = _attempt(_prepare(_choose(_page(assessment_id).run(), lifecycle_id, mode), lifecycle_id, mode))

    assert not app.exception
    rendered = _rendered(app)
    assert "needs an explicit recovery action" in rendered
    assert "Running — not completed" in rendered
    assert log.calls == 1
    (authorization,) = _repository(path).lifecycle_authorizations(lifecycle_id)
    key = authorization.authorization_id
    app = app.run()
    assert log.calls == 1

    app = _keyed(app.button, f"interrupt-{key}").click().run()
    assert "Interrupted — explicit recovery required" in _rendered(app)
    assert _repository(path).load_run_state(authorization.run_lineage.run_id).current_status is FormalRunStatus.INTERRUPTED
    abandon = _keyed(app.button, f"abandon-{key}")
    assert abandon.disabled
    app = _keyed(app.text_input, f"abandon-reason-{key}").set_value(
        "The interrupted attempt is deliberately closed."
    ).run()
    app = _keyed(app.button, f"abandon-{key}").click().run()

    assert not app.exception
    assert "Abandoned" in _rendered(app)
    assert _repository(path).load_run_state(authorization.run_lineage.run_id).current_status is FormalRunStatus.ABANDONED
    assert _repository(path).current_successful_result(lifecycle_id) is None
    assert log.calls == 1


def test_interrupted_attempt_retries_only_with_original_projection(tmp_path, monkeypatch) -> None:
    path = tmp_path / "interrupt-retry.db"
    assessment_id, _, lifecycle_id = _formal_lifecycle(path)
    log = EngineLog()
    _enable(monkeypatch, path, _interrupting_bundle(path, log))
    mode = FormalAssessmentInputMode.APPROVED_PROCESS_ONLY
    app = _attempt(_prepare(_choose(_page(assessment_id).run(), lifecycle_id, mode), lifecycle_id, mode))
    (authorization,) = _repository(path).lifecycle_authorizations(lifecycle_id)
    key = authorization.authorization_id
    app = _keyed(app.button, f"interrupt-{key}").click().run()
    app = _keyed(app.button, f"retry-available-{key}").click().run()
    app = _keyed(app.button, f"retry-{key}").click().run()

    assert not app.exception
    assert log.calls == 2
    assert COMPLETED in _rendered(app)
    history = _repository(path).run_history(authorization.run_lineage.run_id)
    assert history.manifests[-1].projection == history.manifests[0].projection
    assert history.manifests[-1].authorization.input_choice.mode is mode


def test_deliberate_new_run_supersedes_while_failures_never_do(tmp_path, monkeypatch) -> None:
    path = tmp_path / "supersede.db"
    assessment_id, journey_id, lifecycle_id = _formal_lifecycle(path)
    log = EngineLog()
    _enable(monkeypatch, path, _bundle(path, log))
    mode = FormalAssessmentInputMode.APPROVED_PROCESS_ONLY
    app = _attempt(_prepare(_choose(_page(assessment_id).run(), lifecycle_id, mode), lifecycle_id, mode))
    repository = _repository(path)
    first = repository.current_successful_result(lifecycle_id)
    assert "Current organisational assessment result" in _rendered(app)

    # A failed deliberate attempt never replaces the current successful result.
    log.fail = True
    app = _attempt(_prepare(app, lifecycle_id, mode))
    assert repository.current_successful_result(lifecycle_id) == first
    log.fail = False

    app = _attempt(_prepare(app, lifecycle_id, mode))

    assert not app.exception
    authorizations = repository.lifecycle_authorizations(lifecycle_id)
    assert len(authorizations) == 3
    assert len({item.authorization_id for item in authorizations}) == 3
    assert len({item.run_lineage.run_id for item in authorizations}) == 3
    assert len({item.request.request_token for item in authorizations}) == 3
    second = repository.current_successful_result(lifecycle_id)
    assert second.result_id != first.result_id
    assert repository.load_terminal_record(first.result_id) == first
    assert len(repository.successful_result_heads(lifecycle_id)) == 1
    rendered = _rendered(app)
    assert "Superseded — kept as a historical result" in rendered
    assert "Failed — no completed result was created" in rendered
    assert any(item.label == "View historical result" for item in app.expander)
    assert log.calls == 2

    # Route switching and restart preserve every formal and supporting record.
    preliminary = build_preliminary_service_bundle(path)
    state = preliminary.journeys.get_state(journey_id)
    preliminary.journeys.select_route(
        journey_id,
        AssessmentJourney.EXPLORE_PROCESS,
        request_token="formal-ui-explore",
        expected_latest_sequence=state.latest_event_sequence,
    )
    app = _page(assessment_id).run()
    assert not any(item.key and item.key.startswith("formal-input-mode-") for item in app.radio)
    assert "Current organisational assessment result" not in _rendered(app)
    state = preliminary.journeys.get_state(journey_id)
    preliminary.journeys.select_route(
        journey_id,
        AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
        request_token="formal-ui-return",
        expected_latest_sequence=state.latest_event_sequence,
    )
    restarted = _repository(path)
    assert restarted.lifecycle_authorizations(lifecycle_id) == authorizations
    assert restarted.current_successful_result(lifecycle_id) == second
    app = _page(assessment_id).run()
    assert "Current organisational assessment result" in _rendered(app)
    assert log.calls == 2

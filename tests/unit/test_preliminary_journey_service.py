from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pytest

from ai_adoption_engine.models.preliminary_assessment import AssessmentJourney
from ai_adoption_engine.models.preliminary_evaluation import PreliminaryEvaluationSuccess
from ai_adoption_engine.models.preliminary_journey import (
    ApprovedReviewArtifactPin,
    FormalLifecycleStatus,
    PreliminaryCurrentRoute,
    PreliminaryJourneyStatus,
)
from ai_adoption_engine.models.preliminary_persistence import (
    PersistedPreliminaryResult,
    PreliminaryEvaluatorReference,
    PreliminaryJourneyEvent,
    PreliminaryJourneyEventType,
    PreliminaryPersistenceRecordType,
    PreliminaryRunAbandonedPayload,
    PreliminaryRunCompletedPayload,
    PreliminaryRunEventType,
    PreliminaryRunFailedPayload,
    PreliminaryRunLifecycleEvent,
    PreliminaryRunLinkedPayload,
    PreliminaryRunManifest,
    PreliminaryRunProjectedStatus,
    PreliminaryResultRecordedPayload,
    PreliminaryRunStartedPayload,
    PreliminaryRunStateProjection,
)
from ai_adoption_engine.persistence.preliminary import SQLitePreliminaryJourneyStore
from ai_adoption_engine.persistence.preliminary_serialization import (
    serialize_preliminary_persistence_record,
)
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.preliminary.evaluator import PreliminaryAssessmentEvaluator
from ai_adoption_engine.preliminary.formal import PreliminaryFormalStartService
from ai_adoption_engine.preliminary.journey import (
    ApprovedReviewValidationError,
    PreliminaryJourneyConcurrencyError,
    PreliminaryJourneyCorruptionError,
    PreliminaryJourneyIdempotencyError,
    PreliminaryJourneyService,
    PreliminaryJourneyServiceError,
    UnsupportedPreliminaryCompatibilityIdentityError,
    current_preliminary_compatibility_identity,
    preliminary_v0_2_compatibility_identity,
)
from ai_adoption_engine.preliminary.rules import PRELIMINARY_EVALUATOR_RULES_V0_1
from ai_adoption_engine.preliminary.rules_v0_2 import PRELIMINARY_EVALUATOR_RULES_V0_2
from ai_adoption_engine.workspace.models import ArtifactType, ExecutionMode, WorkflowStage
from tests.fakes.review import FIXED_TIME, approved_review


class SequentialIds:
    def __init__(self) -> None:
        self._counts: dict[str, int] = defaultdict(int)

    def __call__(self, prefix: str) -> str:
        self._counts[prefix] += 1
        return f"{prefix}-{self._counts[prefix]}"


@dataclass(frozen=True)
class ServiceContext:
    path: Path
    repository: SQLiteAssessmentRepository
    store: SQLitePreliminaryJourneyStore
    service: PreliminaryJourneyService
    assessment_id: str
    review_artifact_id: str
    approved: object
    pin: ApprovedReviewArtifactPin
    journey_id: str


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _context(tmp_path: Path) -> ServiceContext:
    tmp_path.mkdir(parents=True, exist_ok=True)
    repository_ids = SequentialIds()
    path = tmp_path / "workspace.db"
    repository = SQLiteAssessmentRepository(
        path,
        clock=lambda: FIXED_TIME,
        id_factory=repository_ids,
    )
    assessment = repository.create_assessment(
        "Source assessment", ExecutionMode.OFFLINE_DEMO
    )
    approved = approved_review()
    review_ref = repository.save_artifact_and_advance(
        assessment.assessment_id,
        ArtifactType.REVIEW_SESSION,
        approved.review,
        artifact_schema_version="phase4-v0.1",
        stage=WorkflowStage.IN_REVIEW,
    )
    approved_ref = repository.save_artifact_and_advance(
        assessment.assessment_id,
        ArtifactType.APPROVED_REVIEW,
        approved,
        artifact_schema_version="phase4-v0.1",
        stage=WorkflowStage.APPROVED,
        parent_artifact_id=review_ref.artifact_id,
    )
    stored = repository.load_artifact(approved_ref.artifact_id)
    pin = ApprovedReviewArtifactPin(
        assessment_id=assessment.assessment_id,
        artifact_id=approved_ref.artifact_id,
        artifact_revision=approved_ref.artifact_revision,
        artifact_schema_version=stored.artifact_schema_version,
        payload_sha256=stored.payload_sha256,
    )
    store = SQLitePreliminaryJourneyStore(path, clock=lambda: FIXED_TIME)
    service = PreliminaryJourneyService(
        store,
        clock=lambda: FIXED_TIME,
        id_factory=SequentialIds(),
    )
    created = service.create_or_reuse_journey(pin)
    return ServiceContext(
        path=path,
        repository=repository,
        store=store,
        service=service,
        assessment_id=assessment.assessment_id,
        review_artifact_id=review_ref.artifact_id,
        approved=approved,
        pin=pin,
        journey_id=created.journey.journey_id,
    )


def _select_explore(context: ServiceContext, *, expected: int = 1) -> None:
    context.service.select_route(
        context.journey_id,
        AssessmentJourney.EXPLORE_PROCESS,
        request_token=f"route-explore-{expected}",
        expected_latest_sequence=expected,
    )


def _insert_journey_event(
    connection: sqlite3.Connection, event: PreliminaryJourneyEvent
) -> None:
    payload_json, payload_sha = serialize_preliminary_persistence_record(
        PreliminaryPersistenceRecordType.JOURNEY_EVENT,
        event.schema_version,
        event,
    )
    connection.execute(
        """INSERT INTO preliminary_journey_events(
               event_id, journey_id, event_sequence, schema_version,
               event_type, payload_schema_version, occurred_at,
               payload_json, payload_sha256
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event.event_id,
            event.journey_id,
            event.event_sequence,
            event.schema_version,
            event.event_type.value,
            event.payload.schema_version,
            event.occurred_at.isoformat(),
            payload_json,
            payload_sha,
        ),
    )


def _insert_manifest(
    connection: sqlite3.Connection, manifest: PreliminaryRunManifest
) -> None:
    payload_json, payload_sha = serialize_preliminary_persistence_record(
        PreliminaryPersistenceRecordType.RUN_MANIFEST,
        manifest.schema_version,
        manifest,
    )
    source = manifest.source
    connection.execute(
        """INSERT INTO preliminary_run_manifests VALUES (
               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
           )""",
        (
            manifest.preliminary_run_id,
            manifest.journey_id,
            manifest.schema_version,
            manifest.store_id,
            manifest.request_token,
            manifest.retry_of_run_id,
            manifest.route_choice_event_id,
            manifest.route_choice_event_sequence,
            source.source_assessment_id,
            source.approved_review_artifact_id,
            source.approved_review_payload_sha256,
            source.source_document_id,
            source.validated_process_id,
            source.validated_process_fingerprint,
            manifest.evaluator.evaluator_id,
            manifest.evaluator.evaluator_version,
            manifest.rule_set.rule_set_id,
            manifest.rule_set.rule_set_version,
            manifest.rule_set.rule_set_fingerprint,
            manifest.output_schema_version,
            manifest.created_at.isoformat(),
            payload_json,
            payload_sha,
        ),
    )


def _insert_run_event(
    connection: sqlite3.Connection, event: PreliminaryRunLifecycleEvent
) -> None:
    payload_json, payload_sha = serialize_preliminary_persistence_record(
        PreliminaryPersistenceRecordType.RUN_EVENT,
        event.schema_version,
        event,
    )
    connection.execute(
        """INSERT INTO preliminary_run_events VALUES (
               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
           )""",
        (
            event.run_event_id,
            event.preliminary_run_id,
            event.journey_id,
            event.event_sequence,
            event.schema_version,
            event.event_type.value,
            event.payload.schema_version,
            getattr(event.payload, "preliminary_result_id", None),
            event.occurred_at.isoformat(),
            payload_json,
            payload_sha,
        ),
    )


def _write_projection(
    connection: sqlite3.Connection,
    projection: PreliminaryRunStateProjection,
    *,
    update: bool = False,
) -> None:
    payload_json, payload_sha = serialize_preliminary_persistence_record(
        PreliminaryPersistenceRecordType.RUN_STATE_PROJECTION,
        projection.schema_version,
        projection,
    )
    values = (
        projection.schema_version,
        projection.projected_status.value,
        projection.terminal_event_id,
        projection.projected_at.isoformat(),
        payload_json,
        payload_sha,
        projection.preliminary_run_id,
        projection.journey_id,
    )
    if update:
        connection.execute(
            """UPDATE preliminary_run_state_index SET
                   schema_version = ?, projected_status = ?, terminal_event_id = ?,
                   projected_at = ?, payload_json = ?, payload_sha256 = ?
               WHERE preliminary_run_id = ? AND journey_id = ?""",
            values,
        )
    else:
        connection.execute(
            """INSERT INTO preliminary_run_state_index VALUES (
                   ?, ?, ?, ?, ?, ?, ?, ?
               )""",
            (
                projection.preliminary_run_id,
                projection.journey_id,
                *values[:6],
            ),
        )


def _seed_run(
    context: ServiceContext,
    run_id: str,
    *,
    terminal: PreliminaryRunEventType | None = None,
    event_sequence: int | None = None,
) -> PersistedPreliminaryResult | None:
    state = context.service.get_state(context.journey_id)
    assert state.current_route_event is not None
    source = state.journey.source
    manifest = PreliminaryRunManifest(
        schema_version="preliminary-run-manifest.v0.1",
        store_id="preliminary-journey-store.v0.1",
        preliminary_run_id=run_id,
        journey_id=context.journey_id,
        request_token=f"run-token-{run_id}",
        route_choice_event_id=state.current_route_event.event_id,
        route_choice_event_sequence=state.current_route_event.event_sequence,
        source=source,
        evaluator=PreliminaryEvaluatorReference(
            evaluator_id="preliminary-evaluator.v0.1",
            evaluator_version="0.1.0",
        ),
        rule_set=PRELIMINARY_EVALUATOR_RULES_V0_1.reference(),
        output_schema_version="preliminary-assessment.v0.1",
        created_at=FIXED_TIME,
    )
    connection = _connect(context.path)
    try:
        next_sequence = event_sequence or connection.execute(
            "SELECT MAX(event_sequence) + 1 FROM preliminary_journey_events WHERE journey_id = ?",
            (context.journey_id,),
        ).fetchone()[0]
        _insert_manifest(connection, manifest)
        linked = PreliminaryJourneyEvent(
            schema_version="preliminary-journey-event.v0.1",
            event_id=f"journey-link-{run_id}",
            journey_id=context.journey_id,
            event_sequence=next_sequence,
            event_type=PreliminaryJourneyEventType.RUN_LINKED,
            occurred_at=FIXED_TIME,
            payload=PreliminaryRunLinkedPayload(
                schema_version="preliminary-run-link.v0.1",
                preliminary_run_id=run_id,
                route_choice_event_id=manifest.route_choice_event_id,
                route_choice_event_sequence=manifest.route_choice_event_sequence,
            ),
        )
        _insert_journey_event(connection, linked)
        started = PreliminaryRunLifecycleEvent(
            schema_version="preliminary-run-event.v0.1",
            run_event_id=f"run-event-{run_id}-1",
            preliminary_run_id=run_id,
            journey_id=context.journey_id,
            event_sequence=1,
            event_type=PreliminaryRunEventType.RUN_STARTED,
            occurred_at=FIXED_TIME,
            payload=PreliminaryRunStartedPayload(
                schema_version="preliminary-run-started.v0.1",
                preliminary_run_id=run_id,
            ),
        )
        _insert_run_event(connection, started)
        _write_projection(
            connection,
            PreliminaryRunStateProjection(
                schema_version="preliminary-run-state-projection.v0.1",
                preliminary_run_id=run_id,
                journey_id=context.journey_id,
                projected_status=PreliminaryRunProjectedStatus.STARTED,
                projected_at=FIXED_TIME,
            ),
        )
        if terminal is None:
            connection.commit()
            return None

        result_id = f"result-{run_id}"
        if terminal is PreliminaryRunEventType.RUN_COMPLETED:
            terminal_payload = PreliminaryRunCompletedPayload(
                schema_version="preliminary-run-completed.v0.1",
                preliminary_run_id=run_id,
                preliminary_result_id=result_id,
            )
        elif terminal is PreliminaryRunEventType.RUN_FAILED:
            terminal_payload = PreliminaryRunFailedPayload(
                schema_version="preliminary-run-failed.v0.1",
                preliminary_run_id=run_id,
                error_code="EVALUATION_FAILED",
            )
        else:
            terminal_payload = PreliminaryRunAbandonedPayload(
                schema_version="preliminary-run-abandoned.v0.1",
                preliminary_run_id=run_id,
                reason_code="INTERRUPTED",
            )
        terminal_event = PreliminaryRunLifecycleEvent(
            schema_version="preliminary-run-event.v0.1",
            run_event_id=f"run-event-{run_id}-2",
            preliminary_run_id=run_id,
            journey_id=context.journey_id,
            event_sequence=2,
            event_type=terminal,
            occurred_at=FIXED_TIME,
            payload=terminal_payload,
        )
        result: PersistedPreliminaryResult | None = None
        if terminal is PreliminaryRunEventType.RUN_COMPLETED:
            evaluated = PreliminaryAssessmentEvaluator(
                clock=lambda: FIXED_TIME,
                id_factory=lambda: run_id,
            ).evaluate(context.approved)
            assert isinstance(evaluated, PreliminaryEvaluationSuccess)
            result = PersistedPreliminaryResult(
                schema_version="preliminary-result.v0.1",
                preliminary_result_id=result_id,
                preliminary_run_id=run_id,
                journey_id=context.journey_id,
                completed_run_event_id=terminal_event.run_event_id,
                source=source,
                evaluator=manifest.evaluator,
                rule_set=manifest.rule_set,
                output_schema_version=manifest.output_schema_version,
                created_at=FIXED_TIME,
                assessment=evaluated.assessment,
            )
            _insert_result(connection, result)
        _insert_run_event(connection, terminal_event)
        _write_projection(
            connection,
            PreliminaryRunStateProjection(
                schema_version="preliminary-run-state-projection.v0.1",
                preliminary_run_id=run_id,
                journey_id=context.journey_id,
                projected_status=PreliminaryRunProjectedStatus(
                    terminal.value.removeprefix("RUN_")
                ),
                terminal_event_id=terminal_event.run_event_id,
                projected_at=FIXED_TIME,
            ),
            update=True,
        )
        if result is not None:
            _insert_journey_event(
                connection,
                PreliminaryJourneyEvent(
                    schema_version="preliminary-journey-event.v0.1",
                    event_id=f"journey-result-{run_id}",
                    journey_id=context.journey_id,
                    event_sequence=next_sequence + 1,
                    event_type=PreliminaryJourneyEventType.RESULT_RECORDED,
                    occurred_at=FIXED_TIME,
                    payload=PreliminaryResultRecordedPayload(
                        schema_version="preliminary-result-recorded.v0.1",
                        preliminary_run_id=run_id,
                        preliminary_result_id=result_id,
                    ),
                ),
            )
        connection.commit()
        return result
    finally:
        connection.close()


def _insert_result(
    connection: sqlite3.Connection, result: PersistedPreliminaryResult
) -> None:
    payload_json, payload_sha = serialize_preliminary_persistence_record(
        PreliminaryPersistenceRecordType.PRELIMINARY_RESULT,
        result.schema_version,
        result,
    )
    source = result.source
    connection.execute(
        """INSERT INTO preliminary_results VALUES (
               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
           )""",
        (
            result.preliminary_result_id,
            result.preliminary_run_id,
            result.journey_id,
            result.completed_run_event_id,
            result.schema_version,
            source.source_assessment_id,
            source.approved_review_artifact_id,
            source.approved_review_payload_sha256,
            source.source_document_id,
            source.validated_process_id,
            source.validated_process_fingerprint,
            result.evaluator.evaluator_id,
            result.evaluator.evaluator_version,
            result.rule_set.rule_set_id,
            result.rule_set.rule_set_version,
            result.rule_set.rule_set_fingerprint,
            result.output_schema_version,
            result.created_at.isoformat(),
            payload_json,
            payload_sha,
        ),
    )


def _rewrite_approved_payload(
    context: ServiceContext,
    mutate,
) -> ApprovedReviewArtifactPin:
    connection = _connect(context.path)
    try:
        row = connection.execute(
            "SELECT payload_json FROM assessment_artifacts WHERE artifact_id = ?",
            (context.pin.artifact_id,),
        ).fetchone()
        payload = json.loads(row["payload_json"])
        mutate(payload)
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        payload_sha = hashlib.sha256(encoded.encode()).hexdigest()
        connection.execute(
            """UPDATE assessment_artifacts
               SET payload_json = ?, payload_sha256 = ?
               WHERE artifact_id = ?""",
            (encoded, payload_sha, context.pin.artifact_id),
        )
        connection.commit()
    finally:
        connection.close()
    return context.pin.model_copy(update={"payload_sha256": payload_sha})


def test_create_or_reuse_exact_active_approved_review(tmp_path: Path) -> None:
    context = _context(tmp_path)

    reused = context.service.create_or_reuse_journey(context.pin)

    assert reused.created is False
    assert reused.journey.journey_id == context.journey_id
    connection = _connect(context.path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM preliminary_journeys").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM preliminary_journey_events").fetchone()[0] == 1
    finally:
        connection.close()


def test_new_active_approved_review_creates_a_separate_journey(tmp_path: Path) -> None:
    context = _context(tmp_path)
    new_ref = context.repository.save_artifact_and_advance(
        context.assessment_id,
        ArtifactType.APPROVED_REVIEW,
        context.approved,
        artifact_schema_version="phase4-v0.1",
        stage=WorkflowStage.APPROVED,
        parent_artifact_id=context.review_artifact_id,
    )
    stored = context.repository.load_artifact(new_ref.artifact_id)
    new_pin = ApprovedReviewArtifactPin(
        assessment_id=context.assessment_id,
        artifact_id=new_ref.artifact_id,
        artifact_revision=new_ref.artifact_revision,
        artifact_schema_version=stored.artifact_schema_version,
        payload_sha256=stored.payload_sha256,
    )

    created = context.service.create_or_reuse_journey(new_pin)

    assert created.created is True
    assert created.journey.journey_id != context.journey_id
    with pytest.raises(ApprovedReviewValidationError, match="active approval"):
        context.service.create_or_reuse_journey(context.pin)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("assessment_id", "assessment-other"),
        ("artifact_revision", 99),
        ("artifact_schema_version", "phase4-v9.9"),
        ("payload_sha256", "0" * 64),
    ],
)
def test_journey_creation_fails_closed_for_bad_source_pins(
    tmp_path: Path, field: str, value: object
) -> None:
    context = _context(tmp_path)
    bad = context.pin.model_copy(update={field: value})

    with pytest.raises(ApprovedReviewValidationError):
        PreliminaryJourneyService(context.store).create_or_reuse_journey(bad)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["review"].__setitem__("status", "in-review"),
        lambda payload: payload["business_process"].__setitem__(
            "process_id", "process-mismatch"
        ),
        lambda payload: payload["approval"].__setitem__(
            "approved_at", "2030-01-01T00:00:00Z"
        ),
        lambda payload: payload["review"]["original_candidate"].__setitem__(
            "source_document_id", "doc-" + "f" * 64
        ),
        lambda payload: payload["review"]["original_candidate"].__setitem__(
            "extraction_run_id", "different-extraction-run"
        ),
    ],
    ids=(
        "review",
        "validated-process",
        "approval",
        "source-document",
        "extraction-lineage",
    ),
)
def test_approved_review_content_and_lineage_fail_closed(
    tmp_path: Path, mutate
) -> None:
    context = _context(tmp_path)
    changed_pin = _rewrite_approved_payload(context, mutate)

    with pytest.raises(PreliminaryJourneyServiceError):
        context.service.create_or_reuse_journey(changed_pin)


def test_approved_review_must_match_its_exact_parent_review_artifact(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    connection = _connect(context.path)
    try:
        row = connection.execute(
            "SELECT payload_json FROM assessment_artifacts WHERE artifact_id = ?",
            (context.review_artifact_id,),
        ).fetchone()
        payload = json.loads(row["payload_json"])
        payload["review_id"] = "review-parent-mismatch"
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        connection.execute(
            """UPDATE assessment_artifacts
               SET payload_json = ?, payload_sha256 = ?
               WHERE artifact_id = ?""",
            (
                encoded,
                hashlib.sha256(encoded.encode()).hexdigest(),
                context.review_artifact_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PreliminaryJourneyCorruptionError):
        context.service.get_state(context.journey_id)


def test_all_route_transitions_noop_selection_and_token_replay(tmp_path: Path) -> None:
    context = _context(tmp_path)
    initial = context.service.get_state(context.journey_id)
    assert initial.current_route is PreliminaryCurrentRoute.UNSELECTED

    selected = context.service.select_route(
        context.journey_id,
        AssessmentJourney.EXPLORE_PROCESS,
        request_token="route-1",
        expected_latest_sequence=1,
    )
    assert selected.request.event_appended is True
    assert selected.effective_route_event.event_type is PreliminaryJourneyEventType.ROUTE_SELECTED

    replayed = context.service.select_route(
        context.journey_id,
        AssessmentJourney.EXPLORE_PROCESS,
        request_token="route-1",
        expected_latest_sequence=1,
    )
    assert replayed.replayed is True
    assert replayed.request == selected.request

    noop = context.service.select_route(
        context.journey_id,
        AssessmentJourney.EXPLORE_PROCESS,
        request_token="route-2",
        expected_latest_sequence=2,
    )
    assert noop.request.event_appended is False
    assert noop.request.resulting_event_id is None

    formal = context.service.select_route(
        context.journey_id,
        AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
        request_token="route-3",
        expected_latest_sequence=2,
    )
    assert formal.effective_route_event.event_type is PreliminaryJourneyEventType.ROUTE_CHANGED
    explore_again = context.service.select_route(
        context.journey_id,
        AssessmentJourney.EXPLORE_PROCESS,
        request_token="route-4",
        expected_latest_sequence=3,
    )
    assert explore_again.effective_route_event.event_sequence == 4
    assert context.service.get_state(context.journey_id).current_route is PreliminaryCurrentRoute.EXPLORE_PROCESS


def test_route_requests_reject_token_conflicts_and_stale_sequences(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _select_explore(context)

    with pytest.raises(PreliminaryJourneyIdempotencyError):
        context.service.select_route(
            context.journey_id,
            AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
            request_token="route-explore-1",
            expected_latest_sequence=2,
        )
    with pytest.raises(PreliminaryJourneyConcurrencyError):
        context.service.select_route(
            context.journey_id,
            AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
            request_token="stale",
            expected_latest_sequence=1,
        )


def test_later_non_route_event_does_not_change_or_invalidate_route(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    _seed_run(context, "run-failed", terminal=PreliminaryRunEventType.RUN_FAILED)

    state = context.service.get_state(context.journey_id)
    assert state.latest_event_sequence == 3
    assert state.current_route is PreliminaryCurrentRoute.EXPLORE_PROCESS
    assert state.current_route_event is not None
    assert state.current_route_event.event_sequence == 2

    noop = context.service.select_route(
        context.journey_id,
        AssessmentJourney.EXPLORE_PROCESS,
        request_token="after-audit",
        expected_latest_sequence=3,
    )
    assert noop.request.event_appended is False
    assert noop.effective_route_event.event_sequence == 2
    replay = context.service.select_route(
        context.journey_id,
        AssessmentJourney.EXPLORE_PROCESS,
        request_token="route-explore-1",
        expected_latest_sequence=1,
    )
    assert replay.replayed is True
    assert replay.effective_route_event.event_sequence == 2


def test_preliminary_status_branches_and_precedence(tmp_path: Path) -> None:
    not_started = _context(tmp_path / "not-started")
    assert not_started.service.get_state(not_started.journey_id).preliminary_status is PreliminaryJourneyStatus.NOT_STARTED

    running = _context(tmp_path / "running")
    _select_explore(running)
    _seed_run(running, "run-complete", terminal=PreliminaryRunEventType.RUN_COMPLETED)
    _seed_run(running, "run-active")
    assert running.service.get_state(running.journey_id).preliminary_status is PreliminaryJourneyStatus.RUNNING

    retry = _context(tmp_path / "retry")
    _select_explore(retry)
    _seed_run(retry, "run-failed", terminal=PreliminaryRunEventType.RUN_FAILED)
    assert retry.service.get_state(retry.journey_id).preliminary_status is PreliminaryJourneyStatus.RETRY_AVAILABLE

    available = _context(tmp_path / "available")
    _select_explore(available)
    _seed_run(available, "run-complete", terminal=PreliminaryRunEventType.RUN_COMPLETED)
    _seed_run(available, "run-later-failed", terminal=PreliminaryRunEventType.RUN_FAILED)
    assert available.service.get_state(available.journey_id).preliminary_status is PreliminaryJourneyStatus.AVAILABLE

    historical = _context(tmp_path / "historical")
    _select_explore(historical)
    _seed_run(historical, "run-old", terminal=PreliminaryRunEventType.RUN_COMPLETED)
    future_identity = preliminary_v0_2_compatibility_identity()
    future = PreliminaryJourneyService(
        historical.store,
        supported_identity=future_identity,
    )
    assert future.get_state(historical.journey_id).preliminary_status is PreliminaryJourneyStatus.RERUN_REQUIRED


def test_current_identity_retry_precedes_an_incompatible_historical_result(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    historical = _seed_run(
        context, "run-old", terminal=PreliminaryRunEventType.RUN_COMPLETED
    )
    assert historical is not None
    state = context.service.get_state(context.journey_id)
    assert state.current_route_event is not None
    future_identity = preliminary_v0_2_compatibility_identity()
    service = PreliminaryJourneyService(
        context.store,
        supported_identity=future_identity,
    )
    manifest = PreliminaryRunManifest(
        schema_version="preliminary-run-manifest.v0.1",
        store_id="preliminary-journey-store.v0.1",
        preliminary_run_id="run-current-failed",
        journey_id=context.journey_id,
        request_token="future-attempt",
        route_choice_event_id=state.current_route_event.event_id,
        route_choice_event_sequence=state.current_route_event.event_sequence,
        source=state.journey.source,
        evaluator=PreliminaryEvaluatorReference(
            evaluator_id=future_identity.evaluator_id,
            evaluator_version=future_identity.evaluator_version,
        ),
        rule_set=PRELIMINARY_EVALUATOR_RULES_V0_2.reference(),
        output_schema_version=future_identity.output_schema_version,
        created_at=FIXED_TIME,
    )
    started = PreliminaryRunLifecycleEvent(
        schema_version="preliminary-run-event.v0.1",
        run_event_id="future-started",
        preliminary_run_id=manifest.preliminary_run_id,
        journey_id=context.journey_id,
        event_sequence=1,
        event_type=PreliminaryRunEventType.RUN_STARTED,
        occurred_at=FIXED_TIME,
        payload=PreliminaryRunStartedPayload(
            schema_version="preliminary-run-started.v0.1",
            preliminary_run_id=manifest.preliminary_run_id,
        ),
    )
    failed = PreliminaryRunLifecycleEvent(
        schema_version="preliminary-run-event.v0.1",
        run_event_id="future-failed",
        preliminary_run_id=manifest.preliminary_run_id,
        journey_id=context.journey_id,
        event_sequence=2,
        event_type=PreliminaryRunEventType.RUN_FAILED,
        occurred_at=FIXED_TIME,
        payload=PreliminaryRunFailedPayload(
            schema_version="preliminary-run-failed.v0.1",
            preliminary_run_id=manifest.preliminary_run_id,
            error_code="EVALUATION_FAILED",
        ),
    )

    assert service._preliminary_status(
        {manifest.preliminary_run_id: manifest},
        {manifest.preliminary_run_id: [started, failed]},
        {manifest.preliminary_run_id: 99},
        [historical],
        None,
        state.journey,
    ) is PreliminaryJourneyStatus.RETRY_AVAILABLE

def test_compatible_result_is_selected_independently_then_exposed_only_on_explore(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    first = _seed_run(context, "run-1", terminal=PreliminaryRunEventType.RUN_COMPLETED)
    second = _seed_run(context, "run-2", terminal=PreliminaryRunEventType.RUN_COMPLETED)
    assert first is not None and second is not None

    explore = context.service.get_state(context.journey_id)
    assert explore.latest_compatible_result == second
    assert explore.active_preliminary_result == second

    formal = context.service.select_route(
        context.journey_id,
        AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
        request_token="choose-formal",
        expected_latest_sequence=6,
    )
    hidden = context.service.get_state(context.journey_id)
    assert hidden.current_route is PreliminaryCurrentRoute.ORGANISATIONAL_ASSESSMENT
    assert hidden.latest_compatible_result == second
    assert hidden.active_preliminary_result is None

    context.service.select_route(
        context.journey_id,
        AssessmentJourney.EXPLORE_PROCESS,
        request_token="return-explore",
        expected_latest_sequence=formal.effective_route_event.event_sequence,
    )
    assert context.service.get_state(context.journey_id).active_preliminary_result == second


def test_switching_route_does_not_cancel_or_rewrite_an_active_run(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    _seed_run(context, "run-active")

    context.service.select_route(
        context.journey_id,
        AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
        request_token="switch-during-run",
        expected_latest_sequence=3,
    )
    state = context.service.get_state(context.journey_id)

    assert state.current_route is PreliminaryCurrentRoute.ORGANISATIONAL_ASSESSMENT
    assert state.preliminary_status is PreliminaryJourneyStatus.RUNNING
    connection = _connect(context.path)
    try:
        assert [
            row[0]
            for row in connection.execute(
                """SELECT event_type FROM preliminary_run_events
                   WHERE preliminary_run_id = 'run-active' ORDER BY event_sequence"""
            )
        ] == ["RUN_STARTED"]
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evaluator_id", "preliminary-evaluator.v9"),
        ("evaluator_version", "9.0.0"),
        ("rule_set_id", "preliminary-evaluator-rules.v9"),
        ("rule_set_version", "9.0.0"),
        ("rule_set_fingerprint", "a" * 64),
        ("output_schema_version", "preliminary-assessment.v9"),
    ],
)
def test_every_supported_identity_pin_controls_result_compatibility(
    tmp_path: Path, field: str, value: str
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    _seed_run(context, "run-complete", terminal=PreliminaryRunEventType.RUN_COMPLETED)
    changed_identity = current_preliminary_compatibility_identity().model_copy(
        update={field: value}
    )

    with pytest.raises(
        UnsupportedPreliminaryCompatibilityIdentityError, match="identity"
    ):
        PreliminaryJourneyService(
            context.store,
            supported_identity=changed_identity,
        )


def test_formal_history_remains_visible_after_switching_back_to_explore(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    selected = context.service.select_route(
        context.journey_id,
        AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
        request_token="formal-route",
        expected_latest_sequence=1,
    )
    formal = PreliminaryFormalStartService(
        context.store,
        clock=lambda: FIXED_TIME,
        id_factory=lambda prefix: f"formal-test-{prefix}",
    ).start_formal_lifecycle(
        context.journey_id,
        request_token="formal-start",
        route_choice_event_id=selected.effective_route_event.event_id,
        route_choice_event_sequence=selected.effective_route_event.event_sequence,
    ).lifecycle

    context.service.select_route(
        context.journey_id,
        AssessmentJourney.EXPLORE_PROCESS,
        request_token="back-to-explore",
        expected_latest_sequence=3,
    )
    state = context.service.get_state(context.journey_id)
    assert state.current_route is PreliminaryCurrentRoute.EXPLORE_PROCESS
    assert state.formal_lifecycle_status is FormalLifecycleStatus.AWAITING_FORMAL_INPUTS
    assert state.formal_lifecycle == formal


def test_unsupported_and_corrupt_results_fail_closed(tmp_path: Path) -> None:
    unsupported = _context(tmp_path / "unsupported")
    _select_explore(unsupported)
    result = _seed_run(
        unsupported, "run-complete", terminal=PreliminaryRunEventType.RUN_COMPLETED
    )
    assert result is not None
    connection = _connect(unsupported.path)
    try:
        connection.execute("DROP TRIGGER preliminary_results_immutable_update")
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE preliminary_results SET schema_version = 'preliminary-result.v9.9'"
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(PreliminaryJourneyCorruptionError, match="Unsupported or corrupt"):
        unsupported.service.get_state(unsupported.journey_id)

    corrupt = _context(tmp_path / "corrupt")
    _select_explore(corrupt)
    _seed_run(corrupt, "run-complete", terminal=PreliminaryRunEventType.RUN_COMPLETED)
    connection = _connect(corrupt.path)
    try:
        connection.execute("DROP TRIGGER preliminary_results_immutable_update")
        connection.execute(
            "UPDATE preliminary_results SET payload_json = payload_json || ' '"
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(PreliminaryJourneyCorruptionError, match="Unsupported or corrupt"):
        corrupt.service.get_state(corrupt.journey_id)


def test_corrupt_non_authoritative_run_projection_fails_closed(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    _seed_run(context, "run-failed", terminal=PreliminaryRunEventType.RUN_FAILED)
    connection = _connect(context.path)
    try:
        assert context.service.get_state(context.journey_id).preliminary_status is PreliminaryJourneyStatus.RETRY_AVAILABLE
        connection.execute(
            """UPDATE preliminary_run_state_index
               SET payload_json = payload_json || ' '
               WHERE preliminary_run_id = ?""",
            ("run-failed",),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PreliminaryJourneyCorruptionError, match="Unsupported or corrupt"):
        context.service.get_state(context.journey_id)


def test_concurrent_route_requests_allow_one_expected_sequence_winner(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)

    def choose(route: AssessmentJourney, token: str) -> str:
        service = PreliminaryJourneyService(context.store)
        try:
            service.select_route(
                context.journey_id,
                route,
                request_token=token,
                expected_latest_sequence=1,
            )
        except PreliminaryJourneyConcurrencyError:
            return "stale"
        return "selected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                lambda args: choose(*args),
                [
                    (AssessmentJourney.EXPLORE_PROCESS, "concurrent-explore"),
                    (
                        AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
                        "concurrent-formal",
                    ),
                ],
            )
        )

    assert sorted(outcomes) == ["selected", "stale"]
    assert context.service.get_state(context.journey_id).latest_event_sequence == 2


def test_slice2_does_not_change_strict_stage_artifacts_pointers_or_defaults(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    before = context.repository.load_workspace(context.assessment_id)
    _select_explore(context)
    context.service.select_route(
        context.journey_id,
        AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
        request_token="strict-invariance",
        expected_latest_sequence=2,
    )
    after = context.repository.load_workspace(context.assessment_id)

    assert after.assessment.current_stage == before.assessment.current_stage
    assert after.assessment.contract_pin == before.assessment.contract_pin
    assert after.active_artifacts == before.active_artifacts
    assert set(after.active_artifacts) == {
        ArtifactType.REVIEW_SESSION,
        ArtifactType.APPROVED_REVIEW,
    }

from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pytest

from ai_adoption_engine.models.preliminary_assessment import AssessmentJourney
from ai_adoption_engine.models.preliminary_journey import PreliminaryJourneyStatus
from ai_adoption_engine.models.preliminary_persistence import (
    PreliminaryRecoveryAction,
    PreliminaryRunEventType,
    PreliminaryRunProjectedStatus,
)
from ai_adoption_engine.preliminary.evaluator import PreliminaryAssessmentEvaluator
from ai_adoption_engine.preliminary.journey import (
    PreliminaryJourneyCorruptionError,
    current_preliminary_compatibility_identity,
)
from ai_adoption_engine.preliminary.run import (
    PreliminaryRunConcurrencyError,
    PreliminaryRunNotAllowedError,
    PreliminaryRunRecoveryConflictError,
    PreliminaryRunRecoveryIdempotencyError,
    PreliminaryRunRecoveryWriteError,
    PreliminaryRunResultService,
)
from tests.unit.test_preliminary_journey_service import (
    _connect,
    _context,
    _rewrite_approved_payload,
    _seed_run,
    _select_explore,
)
from tests.unit.test_preliminary_run_service import (
    RunIds,
    _route_pin,
    _run,
    _service,
)


def _recovery_service(context, **overrides) -> PreliminaryRunResultService:
    return _service(context, id_factory=RunIds(), **overrides)


def _retry(service, context, predecessor: str, token: str = "retry-1"):
    event_id, sequence = _route_pin(context)
    return service.retry_and_persist(
        context.journey_id,
        predecessor,
        request_token=token,
        route_choice_event_id=event_id,
        route_choice_event_sequence=sequence,
    )


def test_explicit_abandonment_is_append_only_and_idempotent(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    _seed_run(context, "run-active")
    service = _recovery_service(context)

    first = service.abandon_interrupted_run(
        context.journey_id,
        "run-active",
        recovery_request_token="abandon-1",
    )
    replay = service.abandon_interrupted_run(
        context.journey_id,
        "run-active",
        recovery_request_token="abandon-1",
    )

    assert first.action is PreliminaryRecoveryAction.ABANDON
    assert first.operation.status is PreliminaryRunProjectedStatus.ABANDONED
    assert first.operation.manifest.request_token == "run-token-run-active"
    assert first.operation.manifest.retry_of_run_id is None
    assert replay.replayed is True
    assert replay.operation.model_copy(update={"replayed": False}) == first.operation
    assert replay.recovery_event == first.recovery_event
    connection = _connect(context.path)
    try:
        assert connection.execute(
            """SELECT COUNT(*) FROM preliminary_run_events
               WHERE preliminary_run_id = 'run-active'"""
        ).fetchone()[0] == 2
        assert connection.execute(
            """SELECT COUNT(*) FROM preliminary_journey_events
               WHERE event_type = 'RUN_RECOVERY_RECORDED'"""
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_original_run_token_replay_after_abandonment_never_reevaluates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    _seed_run(context, "run-active")
    service = _recovery_service(context)
    service.abandon_interrupted_run(
        context.journey_id,
        "run-active",
        recovery_request_token="abandon-original",
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("The evaluator must not run for transport replay")

    monkeypatch.setattr(PreliminaryAssessmentEvaluator, "evaluate", forbidden)
    event_id, sequence = _route_pin(context)
    replay = service.evaluate_and_persist(
        context.journey_id,
        request_token="run-token-run-active",
        route_choice_event_id=event_id,
        route_choice_event_sequence=sequence,
    )
    assert replay.replayed is True
    assert replay.status is PreliminaryRunProjectedStatus.ABANDONED


@pytest.mark.parametrize(
    "terminal",
    [
        PreliminaryRunEventType.RUN_COMPLETED,
        PreliminaryRunEventType.RUN_FAILED,
        PreliminaryRunEventType.RUN_ABANDONED,
    ],
)
def test_abandonment_refuses_every_terminal_run(
    tmp_path: Path, terminal: PreliminaryRunEventType
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    _seed_run(context, "run-terminal", terminal=terminal)
    with pytest.raises(PreliminaryRunRecoveryConflictError):
        _recovery_service(context).abandon_interrupted_run(
            context.journey_id,
            "run-terminal",
            recovery_request_token="conflicting-abandonment",
        )


def test_abandonment_token_conflict_fails_without_a_second_event(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    _seed_run(context, "run-active")
    service = _recovery_service(context)
    service.abandon_interrupted_run(
        context.journey_id,
        "run-active",
        recovery_request_token="one-token",
    )
    with pytest.raises(PreliminaryRunRecoveryConflictError):
        service.abandon_interrupted_run(
            context.journey_id,
            "run-active",
            recovery_request_token="another-token",
        )


@pytest.mark.parametrize(
    "terminal",
    [PreliminaryRunEventType.RUN_FAILED, PreliminaryRunEventType.RUN_ABANDONED],
)
def test_failed_or_abandoned_run_retries_with_new_identity_and_exact_lineage(
    tmp_path: Path, terminal: PreliminaryRunEventType
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    _seed_run(context, "predecessor", terminal=terminal)
    service = _recovery_service(context)

    result = _retry(service, context, "predecessor")

    assert result.action is PreliminaryRecoveryAction.RETRY
    assert result.operation.status is PreliminaryRunProjectedStatus.COMPLETED
    assert result.operation.manifest.preliminary_run_id != "predecessor"
    assert result.operation.manifest.request_token == "retry-1"
    assert result.operation.manifest.retry_of_run_id == "predecessor"
    assert result.recovery_event.payload.retry_run_id == result.operation.manifest.preliminary_run_id
    assert context.service.get_state(context.journey_id).preliminary_status is PreliminaryJourneyStatus.AVAILABLE
    connection = _connect(context.path)
    try:
        predecessor = connection.execute(
            """SELECT request_token, retry_of_run_id FROM preliminary_run_manifests
               WHERE preliminary_run_id = 'predecessor'"""
        ).fetchone()
        assert tuple(predecessor) == ("run-token-predecessor", None)
    finally:
        connection.close()


@pytest.mark.parametrize(
    "terminal",
    [None, PreliminaryRunEventType.RUN_COMPLETED],
)
def test_retry_refuses_active_or_completed_predecessor(
    tmp_path: Path, terminal: PreliminaryRunEventType | None
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    _seed_run(context, "not-retryable", terminal=terminal)
    with pytest.raises(PreliminaryRunRecoveryConflictError):
        _retry(_recovery_service(context), context, "not-retryable")


def test_retry_transport_replay_does_not_reevaluate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    _seed_run(context, "failed", terminal=PreliminaryRunEventType.RUN_FAILED)
    service = _recovery_service(context)
    calls = 0
    original = PreliminaryAssessmentEvaluator.evaluate

    def counted(self, approved):
        nonlocal calls
        calls += 1
        return original(self, approved)

    monkeypatch.setattr(PreliminaryAssessmentEvaluator, "evaluate", counted)
    first = _retry(service, context, "failed", "retry-replay")
    replay = _retry(service, context, "failed", "retry-replay")
    assert calls == 1
    assert replay.replayed is True
    assert replay.operation.result == first.operation.result


def test_retry_typed_evaluator_failure_has_no_result(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    _seed_run(context, "failed", terminal=PreliminaryRunEventType.RUN_FAILED)
    service = _recovery_service(
        context, evaluation_clock=lambda: datetime(2026, 1, 1)
    )
    result = _retry(service, context, "failed", "retry-fails")
    assert result.operation.status is PreliminaryRunProjectedStatus.FAILED
    assert result.operation.result is None
    assert result.operation.terminal_code == "OUTPUT_VALIDATION_FAILED"


def test_retry_requires_same_journey_and_current_explore_route(tmp_path: Path) -> None:
    first = _context(tmp_path / "first")
    second = _context(tmp_path / "second")
    _select_explore(first)
    _select_explore(second)
    _seed_run(first, "failed-first", terminal=PreliminaryRunEventType.RUN_FAILED)
    with pytest.raises(PreliminaryRunRecoveryConflictError):
        _retry(_recovery_service(second), second, "failed-first")

    _seed_run(second, "failed-second", terminal=PreliminaryRunEventType.RUN_FAILED)
    latest_sequence = second.service.get_state(
        second.journey_id
    ).latest_event_sequence
    second.service.select_route(
        second.journey_id,
        AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
        request_token="formal",
        expected_latest_sequence=latest_sequence,
    )
    event_id, sequence = _route_pin(second)
    with pytest.raises(PreliminaryRunNotAllowedError, match="Explore"):
        _recovery_service(second).retry_and_persist(
            second.journey_id,
            "failed-second",
            request_token="route-refused",
            route_choice_event_id=event_id,
            route_choice_event_sequence=sequence,
        )


def test_retry_rejects_stale_route_identity_and_source_mutation(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    _seed_run(context, "failed", terminal=PreliminaryRunEventType.RUN_FAILED)
    service = _recovery_service(context)
    event_id, sequence = _route_pin(context)
    with pytest.raises(PreliminaryRunNotAllowedError, match="stale"):
        service.retry_and_persist(
            context.journey_id,
            "failed",
            request_token="stale-retry",
            route_choice_event_id=event_id,
            route_choice_event_sequence=sequence + 1,
        )
    _rewrite_approved_payload(
        context,
        lambda payload: payload["business_process"].__setitem__("name", "Mutated"),
    )
    with pytest.raises(PreliminaryJourneyCorruptionError):
        service.retry_and_persist(
            context.journey_id,
            "failed",
            request_token="mutated-source",
            route_choice_event_id=event_id,
            route_choice_event_sequence=sequence,
        )


def test_recovery_service_rejects_identity_mismatch(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    _seed_run(context, "active")
    identity = current_preliminary_compatibility_identity().model_copy(
        update={"rule_set_fingerprint": "a" * 64}
    )
    with pytest.raises(PreliminaryRunNotAllowedError, match="identity"):
        _recovery_service(context, supported_identity=identity)


def test_concurrent_abandonment_allows_one_terminal_winner(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    _seed_run(context, "active")
    service = _recovery_service(context)

    def abandon(token: str):
        try:
            return service.abandon_interrupted_run(
                context.journey_id,
                "active",
                recovery_request_token=token,
            )
        except PreliminaryRunRecoveryConflictError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(abandon, ("race-1", "race-2")))
    assert sum(hasattr(item, "operation") for item in outcomes) == 1
    assert sum(isinstance(item, PreliminaryRunRecoveryConflictError) for item in outcomes) == 1


def test_concurrent_retry_rejects_a_second_active_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    _seed_run(context, "failed", terminal=PreliminaryRunEventType.RUN_FAILED)
    first_service = _recovery_service(context)
    second_service = _recovery_service(context)
    entered = threading.Event()
    release = threading.Event()
    original = PreliminaryAssessmentEvaluator.evaluate

    def blocked(self, approved):
        entered.set()
        assert release.wait(timeout=5)
        return original(self, approved)

    monkeypatch.setattr(PreliminaryAssessmentEvaluator, "evaluate", blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_retry, first_service, context, "failed", "race-retry-1")
        assert entered.wait(timeout=5)
        with pytest.raises(PreliminaryRunConcurrencyError):
            _retry(second_service, context, "failed", "race-retry-2")
        release.set()
        future.result(timeout=5)


def test_abandonment_transaction_rolls_back_late_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    _seed_run(context, "active")
    service = _recovery_service(context)
    original = service._journeys._insert_journey_event

    def fail_recovery(connection, event):
        if event.event_type.value == "RUN_RECOVERY_RECORDED":
            raise sqlite3.OperationalError("injected recovery write failure")
        return original(connection, event)

    monkeypatch.setattr(service._journeys, "_insert_journey_event", fail_recovery)
    with pytest.raises(PreliminaryRunRecoveryWriteError):
        service.abandon_interrupted_run(
            context.journey_id,
            "active",
            recovery_request_token="atomic-abandon",
        )
    state = context.service.get_state(context.journey_id)
    assert state.preliminary_status is PreliminaryJourneyStatus.RUNNING


def test_retry_start_transaction_rolls_back_partial_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    _seed_run(context, "failed", terminal=PreliminaryRunEventType.RUN_FAILED)
    service = _recovery_service(context)
    original = service._journeys._insert_journey_event

    def fail_recovery(connection, event):
        if event.event_type.value == "RUN_RECOVERY_RECORDED":
            raise sqlite3.OperationalError("injected retry audit failure")
        return original(connection, event)

    monkeypatch.setattr(service._journeys, "_insert_journey_event", fail_recovery)
    with pytest.raises(PreliminaryRunRecoveryWriteError):
        _retry(service, context, "failed", "atomic-retry")
    connection = _connect(context.path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_run_manifests"
        ).fetchone()[0] == 1
    finally:
        connection.close()


@pytest.mark.parametrize(
    "later_terminal",
    [PreliminaryRunEventType.RUN_FAILED, PreliminaryRunEventType.RUN_ABANDONED],
)
def test_older_compatible_result_remains_available_after_later_terminal_run(
    tmp_path: Path, later_terminal: PreliminaryRunEventType
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    completed = _run(_service(context), context, "completed-first")
    assert completed.result is not None
    _seed_run(context, "later", terminal=later_terminal)
    state = context.service.get_state(context.journey_id)
    assert state.preliminary_status is PreliminaryJourneyStatus.AVAILABLE
    assert state.latest_compatible_result == completed.result


def test_corrupt_recovery_audit_fails_closed(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    _seed_run(context, "active")
    result = _recovery_service(context).abandon_interrupted_run(
        context.journey_id,
        "active",
        recovery_request_token="corrupt-recovery",
    )
    connection = _connect(context.path)
    try:
        connection.execute("DROP TRIGGER preliminary_journey_events_immutable_update")
        connection.execute(
            """UPDATE preliminary_journey_events SET payload_sha256 = ?
               WHERE event_id = ?""",
            ("0" * 64, result.recovery_event.event_id),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(PreliminaryJourneyCorruptionError):
        context.service.get_state(context.journey_id)


def test_recovery_does_not_change_strict_state(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    _seed_run(context, "active")
    connection = _connect(context.path)
    try:
        before = {
            table: connection.execute(f"SELECT * FROM {table}").fetchall()
            for table in (
                "assessments",
                "assessment_artifacts",
                "active_artifacts",
                "schema_migrations",
            )
        }
    finally:
        connection.close()
    service = _recovery_service(context)
    service.abandon_interrupted_run(
        context.journey_id,
        "active",
        recovery_request_token="strict-abandon",
    )
    _retry(service, context, "active", "strict-retry")
    connection = _connect(context.path)
    try:
        for table, rows in before.items():
            assert connection.execute(f"SELECT * FROM {table}").fetchall() == rows
    finally:
        connection.close()

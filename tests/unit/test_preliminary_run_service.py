from __future__ import annotations

import sqlite3
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pytest

from ai_adoption_engine.models.preliminary_assessment import AssessmentJourney
from ai_adoption_engine.models.preliminary_journey import PreliminaryJourneyStatus
from ai_adoption_engine.models.preliminary_persistence import (
    PreliminaryRunProjectedStatus,
)
from ai_adoption_engine.preliminary.evaluator import PreliminaryAssessmentEvaluator
from ai_adoption_engine.preliminary.journey import (
    PreliminaryJourneyCorruptionError,
    current_preliminary_compatibility_identity,
)
from ai_adoption_engine.preliminary.run import (
    PreliminaryRunConcurrencyError,
    PreliminaryRunFinalizationError,
    PreliminaryRunIdempotencyError,
    PreliminaryRunNotAllowedError,
    PreliminaryRunResultService,
)
from tests.fakes.review import FIXED_TIME
from tests.unit.test_preliminary_journey_service import (
    _connect,
    _context,
    _rewrite_approved_payload,
    _select_explore,
)


class RunIds:
    def __init__(self) -> None:
        self._counts: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def __call__(self, prefix: str) -> str:
        with self._lock:
            self._counts[prefix] += 1
            return f"slice3-{prefix}-{self._counts[prefix]}"


def _service(context, **overrides) -> PreliminaryRunResultService:
    values = {
        "clock": lambda: FIXED_TIME,
        "evaluation_clock": lambda: FIXED_TIME,
        "id_factory": RunIds(),
    }
    values.update(overrides)
    return PreliminaryRunResultService(context.store, **values)


def _route_pin(context) -> tuple[str, int]:
    event = context.service.get_state(context.journey_id).current_route_event
    assert event is not None
    return event.event_id, event.event_sequence


def _run(service, context, token: str = "run-request-1"):
    event_id, sequence = _route_pin(context)
    return service.evaluate_and_persist(
        context.journey_id,
        request_token=token,
        route_choice_event_id=event_id,
        route_choice_event_sequence=sequence,
    )


def _counts(path: Path) -> dict[str, int]:
    connection = _connect(path)
    try:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "preliminary_run_manifests",
                "preliminary_run_events",
                "preliminary_results",
                "preliminary_result_supersessions",
            )
        }
    finally:
        connection.close()


def test_success_persists_one_completed_run_and_immutable_result(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _select_explore(context)

    operation = _run(_service(context), context)

    assert operation.status is PreliminaryRunProjectedStatus.COMPLETED
    assert operation.result is not None
    assert operation.result.assessment.preliminary_assessment_id == operation.manifest.preliminary_run_id
    assert operation.result.source == operation.manifest.source
    assert operation.result.rule_set == operation.manifest.rule_set
    assert operation.supersession is None
    assert _counts(context.path) == {
        "preliminary_run_manifests": 1,
        "preliminary_run_events": 2,
        "preliminary_results": 1,
        "preliminary_result_supersessions": 0,
    }
    state = context.service.get_state(context.journey_id)
    assert state.preliminary_status is PreliminaryJourneyStatus.AVAILABLE
    assert state.active_preliminary_result == operation.result


def test_typed_evaluator_failure_is_terminal_without_result(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    service = _service(context, evaluation_clock=lambda: datetime(2026, 1, 1))

    operation = _run(service, context)

    assert operation.status is PreliminaryRunProjectedStatus.FAILED
    assert operation.terminal_code == "OUTPUT_VALIDATION_FAILED"
    assert operation.result is None
    assert _counts(context.path)["preliminary_results"] == 0
    assert context.service.get_state(context.journey_id).preliminary_status is PreliminaryJourneyStatus.RETRY_AVAILABLE
    with pytest.raises(PreliminaryRunNotAllowedError, match="Slice 4"):
        _run(service, context, "retry-is-not-slice-3")


def test_transport_replay_returns_original_without_reevaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    service = _service(context)
    calls = 0
    original = PreliminaryAssessmentEvaluator.evaluate

    def counted(self, approved):
        nonlocal calls
        calls += 1
        return original(self, approved)

    monkeypatch.setattr(PreliminaryAssessmentEvaluator, "evaluate", counted)
    first = _run(service, context)
    replay = _run(service, context)

    assert calls == 1
    assert replay.replayed is True
    assert replay.manifest == first.manifest
    assert replay.result == first.result
    event_id, sequence = _route_pin(context)
    with pytest.raises(PreliminaryRunIdempotencyError):
        service.evaluate_and_persist(
            context.journey_id,
            request_token="run-request-1",
            route_choice_event_id=event_id,
            route_choice_event_sequence=sequence + 1,
        )


def test_deliberate_rerun_creates_new_result_and_supersession(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    service = _service(context)
    first = _run(service, context, "deliberate-1")
    second = _run(service, context, "deliberate-2")

    assert first.result is not None and second.result is not None
    assert first.manifest.preliminary_run_id != second.manifest.preliminary_run_id
    assert first.result.preliminary_result_id != second.result.preliminary_result_id
    assert second.supersession is not None
    assert second.supersession.superseded_result_id == first.result.preliminary_result_id
    assert second.supersession.superseding_result_id == second.result.preliminary_result_id
    assert context.service.get_state(context.journey_id).latest_compatible_result == second.result
    connection = _connect(context.path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE preliminary_results SET created_at = created_at WHERE preliminary_result_id = ?",
                (first.result.preliminary_result_id,),
            )
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "DELETE FROM preliminary_results WHERE preliminary_result_id = ?",
                (first.result.preliminary_result_id,),
            )
    finally:
        connection.close()


def test_route_change_during_evaluation_keeps_history_but_hides_active_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    service = _service(context)
    entered = threading.Event()
    release = threading.Event()
    original = PreliminaryAssessmentEvaluator.evaluate

    def blocked(self, approved):
        entered.set()
        assert release.wait(timeout=5)
        return original(self, approved)

    monkeypatch.setattr(PreliminaryAssessmentEvaluator, "evaluate", blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_run, service, context, "route-change-run")
        assert entered.wait(timeout=5)
        running = context.service.get_state(context.journey_id)
        context.service.select_route(
            context.journey_id,
            AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
            request_token="route-away",
            expected_latest_sequence=running.latest_event_sequence,
        )
        release.set()
        operation = future.result(timeout=5)

    state = context.service.get_state(context.journey_id)
    assert operation.result is not None
    assert state.latest_compatible_result == operation.result
    assert state.active_preliminary_result is None
    context.service.select_route(
        context.journey_id,
        AssessmentJourney.EXPLORE_PROCESS,
        request_token="route-back",
        expected_latest_sequence=state.latest_event_sequence,
    )
    assert context.service.get_state(context.journey_id).active_preliminary_result == operation.result


def test_concurrent_new_request_is_rejected_while_first_run_is_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    first_service = _service(context)
    second_service = _service(context)
    entered = threading.Event()
    release = threading.Event()
    original = PreliminaryAssessmentEvaluator.evaluate

    def blocked(self, approved):
        entered.set()
        assert release.wait(timeout=5)
        return original(self, approved)

    monkeypatch.setattr(PreliminaryAssessmentEvaluator, "evaluate", blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_run, first_service, context, "concurrent-1")
        assert entered.wait(timeout=5)
        with pytest.raises(PreliminaryRunConcurrencyError):
            _run(second_service, context, "concurrent-2")
        release.set()
        future.result(timeout=5)


def test_terminal_transaction_failure_leaves_only_valid_started_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    service = _service(context)

    original = service._journeys._insert_journey_event

    def fail_after_terminal_writes(connection, event):
        if event.event_type.value == "RESULT_RECORDED":
            raise sqlite3.OperationalError("injected late final write failure")
        return original(connection, event)

    monkeypatch.setattr(
        service._journeys, "_insert_journey_event", fail_after_terminal_writes
    )
    with pytest.raises(PreliminaryRunFinalizationError):
        _run(service, context, "atomicity")

    assert _counts(context.path) == {
        "preliminary_run_manifests": 1,
        "preliminary_run_events": 1,
        "preliminary_results": 0,
        "preliminary_result_supersessions": 0,
    }
    assert context.service.get_state(context.journey_id).preliminary_status is PreliminaryJourneyStatus.RUNNING


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
def test_service_rejects_unsupported_identity(
    tmp_path: Path, field: str, value: str
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    identity = current_preliminary_compatibility_identity().model_copy(
        update={field: value}
    )
    with pytest.raises(PreliminaryRunNotAllowedError, match="identity"):
        _run(_service(context, supported_identity=identity), context)
    assert _counts(context.path)["preliminary_run_manifests"] == 0


def test_run_requires_an_explicit_latest_explore_route(tmp_path: Path) -> None:
    context = _context(tmp_path)
    service = _service(context)
    with pytest.raises(PreliminaryRunNotAllowedError, match="Explore"):
        service.evaluate_and_persist(
            context.journey_id,
            request_token="unselected",
            route_choice_event_id="missing-route",
            route_choice_event_sequence=1,
        )

    context.service.select_route(
        context.journey_id,
        AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
        request_token="formal",
        expected_latest_sequence=1,
    )
    event_id, sequence = _route_pin(context)
    with pytest.raises(PreliminaryRunNotAllowedError, match="Explore"):
        service.evaluate_and_persist(
            context.journey_id,
            request_token="formal-route",
            route_choice_event_id=event_id,
            route_choice_event_sequence=sequence,
        )
    assert _counts(context.path)["preliminary_run_manifests"] == 0


def test_stale_route_pin_and_mutated_source_fail_without_run_writes(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    service = _service(context)
    event_id, sequence = _route_pin(context)
    with pytest.raises(PreliminaryRunNotAllowedError, match="stale"):
        service.evaluate_and_persist(
            context.journey_id,
            request_token="stale",
            route_choice_event_id=event_id,
            route_choice_event_sequence=sequence + 1,
        )

    _rewrite_approved_payload(
        context,
        lambda payload: payload["business_process"].__setitem__("name", "Mutated"),
    )
    with pytest.raises(PreliminaryJourneyCorruptionError, match="source"):
        service.evaluate_and_persist(
            context.journey_id,
            request_token="mutated-source",
            route_choice_event_id=event_id,
            route_choice_event_sequence=sequence,
        )
    assert _counts(context.path)["preliminary_run_manifests"] == 0


def test_corrupt_result_history_fails_closed_on_state_and_replay(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    service = _service(context)
    operation = _run(service, context, "corrupt-result")
    assert operation.result is not None
    connection = _connect(context.path)
    try:
        connection.execute("DROP TRIGGER preliminary_results_immutable_update")
        connection.execute(
            "UPDATE preliminary_results SET payload_sha256 = ? WHERE preliminary_result_id = ?",
            ("0" * 64, operation.result.preliminary_result_id),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(PreliminaryJourneyCorruptionError):
        context.service.get_state(context.journey_id)
    with pytest.raises(PreliminaryJourneyCorruptionError):
        _run(service, context, "corrupt-result")


def test_missing_projection_and_incomplete_history_fail_closed(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    operation = _run(_service(context), context, "missing-projection")
    connection = _connect(context.path)
    try:
        connection.execute(
            "DELETE FROM preliminary_run_state_index WHERE preliminary_run_id = ?",
            (operation.manifest.preliminary_run_id,),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(PreliminaryJourneyCorruptionError, match="projection"):
        context.service.get_state(context.journey_id)


def test_corrupt_supersession_history_fails_closed(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    service = _service(context)
    _run(service, context, "supersession-1")
    second = _run(service, context, "supersession-2")
    assert second.supersession is not None
    connection = _connect(context.path)
    try:
        connection.execute(
            "DROP TRIGGER preliminary_supersessions_immutable_update"
        )
        connection.execute(
            """UPDATE preliminary_result_supersessions
               SET payload_sha256 = ? WHERE supersession_id = ?""",
            ("0" * 64, second.supersession.supersession_id),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(PreliminaryJourneyCorruptionError):
        context.service.get_state(context.journey_id)


def test_run_does_not_change_strict_stage_artifacts_or_active_pointers(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    connection = _connect(context.path)
    try:
        before_assessment = tuple(
            connection.execute(
                "SELECT * FROM assessments WHERE assessment_id = ?",
                (context.assessment_id,),
            ).fetchone()
        )
        before_artifacts = connection.execute(
            "SELECT * FROM assessment_artifacts ORDER BY artifact_id"
        ).fetchall()
        before_active = connection.execute(
            "SELECT * FROM active_artifacts ORDER BY artifact_type"
        ).fetchall()
        before_strict_migrations = connection.execute(
            "SELECT * FROM schema_migrations ORDER BY version"
        ).fetchall()
    finally:
        connection.close()

    _run(_service(context), context, "strict-invariance")

    connection = _connect(context.path)
    try:
        assert tuple(
            connection.execute(
                "SELECT * FROM assessments WHERE assessment_id = ?",
                (context.assessment_id,),
            ).fetchone()
        ) == before_assessment
        assert connection.execute(
            "SELECT * FROM assessment_artifacts ORDER BY artifact_id"
        ).fetchall() == before_artifacts
        assert connection.execute(
            "SELECT * FROM active_artifacts ORDER BY artifact_type"
        ).fetchall() == before_active
        assert connection.execute(
            "SELECT * FROM schema_migrations ORDER BY version"
        ).fetchall() == before_strict_migrations
    finally:
        connection.close()

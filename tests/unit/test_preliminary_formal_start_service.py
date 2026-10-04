from __future__ import annotations

import sqlite3
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from ai_adoption_engine.models.preliminary_assessment import AssessmentJourney
from ai_adoption_engine.models.preliminary_journey import (
    FormalLifecycleStatus,
    PreliminaryCurrentRoute,
    PreliminaryJourneyStatus,
)
from ai_adoption_engine.models.preliminary_persistence import (
    PreliminaryJourneyEventType,
    PreliminaryResultReferenceUse,
)
from ai_adoption_engine.preliminary.formal import (
    PreliminaryFormalStartConflictError,
    PreliminaryFormalStartIdempotencyError,
    PreliminaryFormalStartNotAllowedError,
    PreliminaryFormalStartService,
    PreliminaryFormalStartWriteError,
)
from ai_adoption_engine.preliminary.journey import PreliminaryJourneyCorruptionError
from tests.fakes.review import FIXED_TIME
from tests.unit.test_preliminary_journey_service import (
    _connect,
    _context,
    _rewrite_approved_payload,
    _select_explore,
)
from tests.unit.test_preliminary_run_service import _run, _service


class FormalIds:
    def __init__(self) -> None:
        self._counts: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def __call__(self, prefix: str) -> str:
        with self._lock:
            self._counts[prefix] += 1
            return f"slice5-{prefix}-{self._counts[prefix]}"


def _formal_service(context, **overrides) -> PreliminaryFormalStartService:
    values = {
        "clock": lambda: FIXED_TIME,
        "id_factory": FormalIds(),
    }
    values.update(overrides)
    return PreliminaryFormalStartService(context.store, **values)


def _select_formal(context):
    latest = context.service.get_state(context.journey_id).latest_event_sequence
    return context.service.select_route(
        context.journey_id,
        AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
        request_token=f"formal-route-{latest}",
        expected_latest_sequence=latest,
    ).effective_route_event


def _start(service, context, route, token: str = "formal-start-1", **overrides):
    values = {
        "request_token": token,
        "route_choice_event_id": route.event_id,
        "route_choice_event_sequence": route.event_sequence,
    }
    values.update(overrides)
    return service.start_formal_lifecycle(context.journey_id, **values)


def test_formal_start_without_preliminary_result_is_isolated_and_visible(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    route = _select_formal(context)

    result = _start(_formal_service(context), context, route)

    assert result.replayed is False
    assert result.lifecycle.status == "AWAITING_FORMAL_INPUTS"
    assert result.lifecycle.source.source_assessment_id == context.assessment_id
    assert result.lifecycle.journey_id == context.journey_id
    assert result.lifecycle.preliminary_result_id is None
    assert result.lifecycle.preliminary_result_use is None
    assert result.request.request_token == "formal-start-1"
    assert result.start_event.event_type is PreliminaryJourneyEventType.FORMAL_LIFECYCLE_STARTED
    state = context.service.get_state(context.journey_id)
    assert state.formal_lifecycle_status is FormalLifecycleStatus.AWAITING_FORMAL_INPUTS
    assert state.formal_lifecycle == result.lifecycle


def test_valid_preliminary_result_is_retained_only_as_explicit_context(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    operation = _run(_service(context), context, "context-result")
    assert operation.result is not None
    before = context.service.get_state(context.journey_id)
    route = _select_formal(context)

    result = _start(
        _formal_service(context),
        context,
        route,
        preliminary_result_id=operation.result.preliminary_result_id,
        preliminary_result_use=(
            PreliminaryResultReferenceUse.CONTEXT_ONLY_NOT_FORMAL_EVIDENCE
        ),
    )

    assert result.lifecycle.preliminary_result_id == operation.result.preliminary_result_id
    assert (
        result.lifecycle.preliminary_result_use
        == "CONTEXT_ONLY_NOT_FORMAL_EVIDENCE"
    )
    assert result.request.preliminary_result_use == result.lifecycle.preliminary_result_use
    after = context.service.get_state(context.journey_id)
    assert after.preliminary_status is before.preliminary_status
    assert after.latest_compatible_result == before.latest_compatible_result
    assert after.active_preliminary_result is None


def test_result_reference_requires_exact_context_only_classification(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    operation = _run(_service(context), context, "classification")
    assert operation.result is not None
    route = _select_formal(context)
    with pytest.raises(PreliminaryFormalStartNotAllowedError, match="context"):
        _start(
            _formal_service(context),
            context,
            route,
            preliminary_result_id=operation.result.preliminary_result_id,
        )


def test_same_token_replay_returns_original_without_new_history(tmp_path: Path) -> None:
    context = _context(tmp_path)
    route = _select_formal(context)
    service = _formal_service(context)
    first = _start(service, context, route, "same-token")
    replay = _start(service, context, route, "same-token")

    assert replay.replayed is True
    assert replay.lifecycle == first.lifecycle
    assert replay.request == first.request
    assert replay.start_event == first.start_event
    connection = _connect(context.path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_formal_lifecycles"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_formal_start_requests"
        ).fetchone()[0] == 1
        assert connection.execute(
            """SELECT COUNT(*) FROM preliminary_journey_events
               WHERE event_type = 'FORMAL_LIFECYCLE_STARTED'"""
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_replay_parameter_change_and_conflicting_token_are_rejected(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    route = _select_formal(context)
    service = _formal_service(context)
    _start(service, context, route, "original")
    with pytest.raises(PreliminaryFormalStartIdempotencyError):
        service.start_formal_lifecycle(
            context.journey_id,
            request_token="original",
            route_choice_event_id=route.event_id,
            route_choice_event_sequence=route.event_sequence + 1,
        )
    with pytest.raises(PreliminaryFormalStartConflictError):
        _start(service, context, route, "different-token")


def test_concurrent_formal_starts_create_exactly_one_lifecycle(tmp_path: Path) -> None:
    context = _context(tmp_path)
    route = _select_formal(context)
    service = _formal_service(context)

    def start(token: str):
        try:
            return _start(service, context, route, token)
        except PreliminaryFormalStartConflictError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(start, ("race-1", "race-2")))
    assert sum(hasattr(item, "lifecycle") for item in outcomes) == 1
    assert sum(isinstance(item, PreliminaryFormalStartConflictError) for item in outcomes) == 1


def test_latest_route_must_be_organisational_and_exactly_pinned(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    explore = context.service.get_state(context.journey_id).current_route_event
    assert explore is not None
    with pytest.raises(PreliminaryFormalStartNotAllowedError, match="Organisational"):
        _start(_formal_service(context), context, explore)

    route = _select_formal(context)
    with pytest.raises(PreliminaryFormalStartNotAllowedError, match="stale"):
        _formal_service(context).start_formal_lifecycle(
            context.journey_id,
            request_token="stale",
            route_choice_event_id=explore.event_id,
            route_choice_event_sequence=explore.event_sequence,
        )
    assert route.event_sequence > explore.event_sequence


def test_later_non_route_start_event_does_not_invalidate_route_pin(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    route = _select_formal(context)
    result = _start(_formal_service(context), context, route)
    assert result.start_event.event_sequence > route.event_sequence
    state = context.service.get_state(context.journey_id)
    assert state.current_route_event == route
    assert state.formal_lifecycle == result.lifecycle


def test_later_route_change_rejects_new_start_but_does_not_hide_existing(
    tmp_path: Path,
) -> None:
    rejected = _context(tmp_path / "rejected")
    formal_route = _select_formal(rejected)
    rejected.service.select_route(
        rejected.journey_id,
        AssessmentJourney.EXPLORE_PROCESS,
        request_token="back-before-start",
        expected_latest_sequence=formal_route.event_sequence,
    )
    with pytest.raises(PreliminaryFormalStartNotAllowedError, match="Organisational"):
        _start(_formal_service(rejected), rejected, formal_route)

    retained = _context(tmp_path / "retained")
    retained_route = _select_formal(retained)
    service = _formal_service(retained)
    created = _start(service, retained, retained_route, "retained-start")
    retained.service.select_route(
        retained.journey_id,
        AssessmentJourney.EXPLORE_PROCESS,
        request_token="back-after-start",
        expected_latest_sequence=created.start_event.event_sequence,
    )
    state = retained.service.get_state(retained.journey_id)
    assert state.current_route is PreliminaryCurrentRoute.EXPLORE_PROCESS
    assert state.formal_lifecycle == created.lifecycle
    replay = _start(service, retained, retained_route, "retained-start")
    assert replay.replayed is True


def test_source_mutation_and_cross_journey_route_pin_fail_closed(tmp_path: Path) -> None:
    mutated = _context(tmp_path / "mutated")
    route = _select_formal(mutated)
    _rewrite_approved_payload(
        mutated,
        lambda payload: payload["business_process"].__setitem__("name", "Mutated"),
    )
    with pytest.raises(PreliminaryJourneyCorruptionError):
        _start(_formal_service(mutated), mutated, route)

    first = _context(tmp_path / "first")
    second = _context(tmp_path / "second")
    first_route = _select_formal(first)
    _select_formal(second)
    with pytest.raises(PreliminaryFormalStartNotAllowedError, match="stale"):
        _formal_service(second).start_formal_lifecycle(
            second.journey_id,
            request_token="cross-journey-route",
            route_choice_event_id=f"foreign-{first_route.event_id}",
            route_choice_event_sequence=first_route.event_sequence,
        )


def test_inactive_approved_review_rejects_a_new_formal_start(tmp_path: Path) -> None:
    context = _context(tmp_path)
    route = _select_formal(context)
    connection = _connect(context.path)
    try:
        connection.execute(
            """DELETE FROM active_artifacts
               WHERE assessment_id = ? AND artifact_type = 'APPROVED_REVIEW'""",
            (context.assessment_id,),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(PreliminaryJourneyCorruptionError, match="no longer validates"):
        _start(_formal_service(context), context, route)


def test_cross_journey_and_corrupt_preliminary_results_are_rejected(
    tmp_path: Path,
) -> None:
    first = _context(tmp_path / "first")
    _select_explore(first)
    operation = _run(_service(first), first, "cross-result")
    assert operation.result is not None
    second = _context(tmp_path / "second")
    second_route = _select_formal(second)
    with pytest.raises(PreliminaryFormalStartNotAllowedError, match="same-journey"):
        _start(
            _formal_service(second),
            second,
            second_route,
            preliminary_result_id=operation.result.preliminary_result_id,
            preliminary_result_use=(
                PreliminaryResultReferenceUse.CONTEXT_ONLY_NOT_FORMAL_EVIDENCE
            ),
        )

    corrupt = _context(tmp_path / "corrupt")
    _select_explore(corrupt)
    corrupt_operation = _run(_service(corrupt), corrupt, "corrupt-result")
    assert corrupt_operation.result is not None
    corrupt_route = _select_formal(corrupt)
    connection = _connect(corrupt.path)
    try:
        connection.execute("DROP TRIGGER preliminary_results_immutable_update")
        connection.execute(
            """UPDATE preliminary_results SET payload_sha256 = ?
               WHERE preliminary_result_id = ?""",
            ("0" * 64, corrupt_operation.result.preliminary_result_id),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(PreliminaryJourneyCorruptionError):
        _start(
            _formal_service(corrupt),
            corrupt,
            corrupt_route,
            preliminary_result_id=corrupt_operation.result.preliminary_result_id,
            preliminary_result_use=(
                PreliminaryResultReferenceUse.CONTEXT_ONLY_NOT_FORMAL_EVIDENCE
            ),
        )


def test_formal_start_transaction_rolls_back_lifecycle_and_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    route = _select_formal(context)
    service = _formal_service(context)

    def fail_event(*_args, **_kwargs):
        raise sqlite3.OperationalError("injected formal event failure")

    monkeypatch.setattr(service._journeys, "_insert_journey_event", fail_event)
    with pytest.raises(PreliminaryFormalStartWriteError):
        _start(service, context, route, "atomic-start")
    connection = _connect(context.path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_formal_lifecycles"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_formal_start_requests"
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_formal_start_changes_no_strict_state_or_formal_evidence(tmp_path: Path) -> None:
    context = _context(tmp_path)
    route = _select_formal(context)
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

    _start(_formal_service(context), context, route, "strict-invariance")

    connection = _connect(context.path)
    try:
        for table, rows in before.items():
            assert connection.execute(f"SELECT * FROM {table}").fetchall() == rows
        artifact_types = {
            row[0]
            for row in connection.execute(
                "SELECT artifact_type FROM assessment_artifacts"
            )
        }
        assert artifact_types == {"REVIEW_SESSION", "APPROVED_REVIEW"}
    finally:
        connection.close()


def test_formal_start_preserves_preliminary_run_result_and_status_history(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    operation = _run(_service(context), context, "preserved")
    assert operation.result is not None
    before = context.service.get_state(context.journey_id)
    route = _select_formal(context)
    created = _start(_formal_service(context), context, route)
    after = context.service.get_state(context.journey_id)
    assert after.preliminary_status is PreliminaryJourneyStatus.AVAILABLE
    assert after.preliminary_status is before.preliminary_status
    assert after.latest_compatible_result == before.latest_compatible_result
    assert after.formal_lifecycle == created.lifecycle


def test_corrupt_formal_start_request_fails_closed(tmp_path: Path) -> None:
    context = _context(tmp_path)
    route = _select_formal(context)
    created = _start(_formal_service(context), context, route)
    connection = _connect(context.path)
    try:
        connection.execute(
            "DROP TRIGGER preliminary_formal_start_requests_immutable_update"
        )
        connection.execute(
            """UPDATE preliminary_formal_start_requests SET payload_sha256 = ?
               WHERE formal_start_request_id = ?""",
            ("0" * 64, created.request.formal_start_request_id),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(PreliminaryJourneyCorruptionError):
        context.service.get_state(context.journey_id)

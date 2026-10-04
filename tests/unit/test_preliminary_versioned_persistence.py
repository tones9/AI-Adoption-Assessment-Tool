from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_adoption_engine.models.preliminary_persistence import (
    PersistedPreliminaryRuleSetReference,
    PreliminaryEvaluatorReference,
    PreliminaryPersistenceRecordType,
    PreliminaryRunManifest,
    PreliminaryRunProjectedStatus,
)
from ai_adoption_engine.models.preliminary_run import PreliminaryRunOperationResult
from ai_adoption_engine.persistence.preliminary_serialization import (
    deserialize_preliminary_persistence_record,
)
from ai_adoption_engine.persistence.preliminary import SQLitePreliminaryJourneyStore
from ai_adoption_engine.persistence.workspace_protection import (
    FrozenEvaluationWorkspaceError,
)
from ai_adoption_engine.preliminary.journey import (
    PreliminaryJourneyService,
    preliminary_v0_2_compatibility_identity,
)
from ai_adoption_engine.preliminary.formal import (
    PreliminaryFormalStartNotAllowedError,
    PreliminaryFormalStartService,
)
from ai_adoption_engine.preliminary.run import (
    PreliminaryRunIdempotencyError,
    PreliminaryRunNotAllowedError,
    PreliminaryRunRecoveryConflictError,
)
from tests.unit.test_preliminary_journey_service import _connect, _context, _select_explore
from tests.unit.test_preliminary_run_service import RunIds, _run, _service


def _leave_started(manifest, started, _approved_review):
    return PreliminaryRunOperationResult(
        manifest=manifest,
        started_event=started,
        status=PreliminaryRunProjectedStatus.STARTED,
    )


def test_default_v0_1_and_explicit_v0_2_round_trip_and_coexist(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    ids = RunIds()
    default_service = _service(context, id_factory=ids)
    v0_2_service = _service(
        context,
        id_factory=ids,
        supported_identity=preliminary_v0_2_compatibility_identity(),
    )

    v0_1 = _run(default_service, context, "versioned-v0-1")
    v0_2 = _run(v0_2_service, context, "versioned-v0-2")

    assert v0_1.manifest.output_schema_version == "preliminary-assessment.v0.1"
    assert v0_1.result is not None
    assert v0_2.result is not None
    assert v0_2.manifest.evaluator.evaluator_id == "preliminary-evaluator.v0.2"
    assert v0_2.manifest.rule_set.rule_set_id == "preliminary-evaluator-rules.v0.2"
    assert v0_2.manifest.output_schema_version == "preliminary-assessment.v0.2"
    assert v0_2.result.assessment.schema_version == "preliminary-assessment.v0.2"
    assert v0_2.supersession is None

    connection = _connect(context.path)
    try:
        row = connection.execute(
            """SELECT schema_version, payload_json, payload_sha256
               FROM preliminary_results_v0_2
               WHERE preliminary_result_id = ?""",
            (v0_2.result.preliminary_result_id,),
        ).fetchone()
        assert row is not None
        hydrated = deserialize_preliminary_persistence_record(
            PreliminaryPersistenceRecordType.PRELIMINARY_RESULT,
            row["schema_version"],
            row["payload_json"],
            row["payload_sha256"],
        )
        assert hydrated == v0_2.result
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_results"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_results_v0_2"
        ).fetchone()[0] == 1
    finally:
        connection.close()

    default_state = context.service.get_state(context.journey_id)
    v0_2_state = PreliminaryJourneyService(
        context.store,
        supported_identity=preliminary_v0_2_compatibility_identity(),
    ).get_state(context.journey_id)
    assert default_state.latest_compatible_result == v0_1.result
    assert default_state.active_preliminary_result == v0_1.result
    assert v0_2_state.latest_compatible_result == v0_2.result
    assert v0_2_state.active_preliminary_result == v0_2.result


def test_versioned_token_replay_and_cross_version_conflict(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    ids = RunIds()
    v0_2_service = _service(
        context,
        id_factory=ids,
        supported_identity=preliminary_v0_2_compatibility_identity(),
    )
    first = _run(v0_2_service, context, "shared-token")
    replay = _run(v0_2_service, context, "shared-token")

    assert replay.replayed is True
    assert replay.manifest == first.manifest
    assert replay.result == first.result
    with pytest.raises(PreliminaryRunIdempotencyError, match="identity"):
        _run(_service(context, id_factory=ids), context, "shared-token")


def test_v0_2_recovery_and_retry_preserve_exact_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    service = _service(
        context,
        id_factory=RunIds(),
        supported_identity=preliminary_v0_2_compatibility_identity(),
    )
    monkeypatch.setattr(service, "_evaluate_started", _leave_started)
    started = _run(service, context, "v0-2-interrupted")
    abandoned = service.abandon_interrupted_run(
        context.journey_id,
        started.manifest.preliminary_run_id,
        recovery_request_token="v0-2-abandon",
    )
    monkeypatch.undo()
    route = context.service.get_state(context.journey_id).current_route_event
    assert route is not None
    retried = service.retry_and_persist(
        context.journey_id,
        abandoned.operation.manifest.preliminary_run_id,
        request_token="v0-2-retry",
        route_choice_event_id=route.event_id,
        route_choice_event_sequence=route.event_sequence,
    )

    assert retried.operation.status is PreliminaryRunProjectedStatus.COMPLETED
    assert retried.operation.manifest.evaluator == started.manifest.evaluator
    assert retried.operation.manifest.rule_set == started.manifest.rule_set
    assert (
        retried.operation.manifest.output_schema_version
        == started.manifest.output_schema_version
        == "preliminary-assessment.v0.2"
    )


def test_retry_cannot_silently_upgrade_a_v0_1_predecessor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    _select_explore(context)
    ids = RunIds()
    v0_1_service = _service(context, id_factory=ids)
    monkeypatch.setattr(v0_1_service, "_evaluate_started", _leave_started)
    started = _run(v0_1_service, context, "v0-1-interrupted")
    abandoned = v0_1_service.abandon_interrupted_run(
        context.journey_id,
        started.manifest.preliminary_run_id,
        recovery_request_token="v0-1-abandon",
    )
    route = context.service.get_state(context.journey_id).current_route_event
    assert route is not None
    v0_2_service = _service(
        context,
        id_factory=ids,
        supported_identity=preliminary_v0_2_compatibility_identity(),
    )

    with pytest.raises(PreliminaryRunRecoveryConflictError, match="compatible"):
        v0_2_service.retry_and_persist(
            context.journey_id,
            abandoned.operation.manifest.preliminary_run_id,
            request_token="silent-upgrade-refused",
            route_choice_event_id=route.event_id,
            route_choice_event_sequence=route.event_sequence,
        )


@pytest.mark.parametrize(
    "change",
    [
        {"evaluator_version": "0.1.0"},
        {"rule_set_fingerprint": "0" * 64},
        {"output_schema_version": "preliminary-assessment.v0.1"},
    ],
)
def test_mixed_identity_and_fingerprint_drift_fail_closed(
    tmp_path: Path, change: dict[str, str]
) -> None:
    context = _context(tmp_path)
    identity = preliminary_v0_2_compatibility_identity().model_copy(update=change)
    with pytest.raises(PreliminaryRunNotAllowedError, match="identity"):
        _service(context, supported_identity=identity)

    with pytest.raises(ValidationError, match="mixed|Unsupported"):
        PreliminaryRunManifest(
            schema_version="preliminary-run-manifest.v0.1",
            store_id="preliminary-journey-store.v0.1",
            preliminary_run_id="mixed-run",
            journey_id=context.journey_id,
            request_token="mixed-token",
            route_choice_event_id="route-event",
            route_choice_event_sequence=1,
            source=context.service.get_state(context.journey_id).journey.source,
            evaluator=PreliminaryEvaluatorReference(
                evaluator_id="preliminary-evaluator.v0.2",
                evaluator_version="0.2.0",
            ),
            rule_set=PersistedPreliminaryRuleSetReference(
                rule_set_id="preliminary-evaluator-rules.v0.1",
                rule_set_version="0.1.0",
                rule_set_status="PROVISIONAL CONTINUITY — NOT VALIDATED",
                rule_set_fingerprint=(
                    "3db8a54561bcfe263a5483e5d4c49e203bfac40eafbc8bc778cf773ed6ad1790"
                ),
            ),
            output_schema_version="preliminary-assessment.v0.2",
            created_at=context.service.get_state(context.journey_id).journey.created_at,
        )


def test_v0_2_remains_disconnected_from_formal_start(tmp_path: Path) -> None:
    context = _context(tmp_path)
    with pytest.raises(PreliminaryFormalStartNotAllowedError, match="v0.1"):
        PreliminaryFormalStartService(
            context.store,
            supported_identity=preliminary_v0_2_compatibility_identity(),
        )


def test_frozen_workspace_bytes_and_sidecars_are_invariant(tmp_path: Path) -> None:
    ordinary = _context(tmp_path / "ordinary")
    protected = (
        tmp_path / "evaluation" / "portfolio" / "frozen" / "workspace.db"
    )
    protected.parent.mkdir(parents=True)
    shutil.copy2(ordinary.path, protected)
    before_bytes = protected.read_bytes()
    before_entries = tuple(sorted(item.name for item in protected.parent.iterdir()))

    with pytest.raises(FrozenEvaluationWorkspaceError):
        SQLitePreliminaryJourneyStore(protected)

    assert protected.read_bytes() == before_bytes
    assert tuple(sorted(item.name for item in protected.parent.iterdir())) == before_entries
    assert not any(
        item.name.endswith(("-journal", "-wal", "-shm"))
        for item in protected.parent.iterdir()
    )

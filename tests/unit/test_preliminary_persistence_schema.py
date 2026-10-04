from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest

from ai_adoption_engine.application.fingerprints import fingerprint_business_process
from ai_adoption_engine.models.preliminary_assessment import (
    AssessmentJourney,
    JourneySelection,
)
from ai_adoption_engine.models.preliminary_evaluation import (
    PreliminaryEvaluationSuccess,
)
from ai_adoption_engine.models.preliminary_persistence import (
    JourneyCreatedPayload,
    PersistedPreliminaryResult,
    PreliminaryEvaluatorReference,
    PreliminaryFormalLifecycle,
    PreliminaryJourney,
    PreliminaryJourneyEvent,
    PreliminaryJourneyEventType,
    PreliminaryPersistenceRecordType,
    PreliminaryResultRecordedPayload,
    PreliminaryRunAbandonedPayload,
    PreliminaryRunCompletedPayload,
    PreliminaryRunEventType,
    PreliminaryRunLifecycleEvent,
    PreliminaryRunLinkedPayload,
    PreliminaryRunManifest,
    PreliminaryRunProjectedStatus,
    PreliminaryRunStartedPayload,
    PreliminaryRunStateProjection,
    PreliminarySourceSnapshot,
)
from ai_adoption_engine.persistence.preliminary import SQLitePreliminaryJourneyStore
from ai_adoption_engine.persistence.preliminary_migrations import (
    PRELIMINARY_JOURNEY_STORE_MIGRATIONS,
)
from ai_adoption_engine.persistence.preliminary_serialization import (
    serialize_preliminary_persistence_record,
)
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.persistence.workspace_protection import (
    FrozenEvaluationWorkspaceError,
)
from ai_adoption_engine.preliminary.evaluator import PreliminaryAssessmentEvaluator
from ai_adoption_engine.preliminary.rules import PRELIMINARY_EVALUATOR_RULES_V0_1
from ai_adoption_engine.workspace.models import (
    ArtifactType,
    ExecutionMode,
    WorkflowStage,
)
from tests.fakes.review import FIXED_TIME, approved_review


@dataclass(frozen=True)
class PreparedJourney:
    path: Path
    repository: SQLiteAssessmentRepository
    approved: object
    approved_artifact_id: str
    source: PreliminarySourceSnapshot
    journey: PreliminaryJourney


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _prepare(tmp_path: Path, name: str = "workspace.db") -> PreparedJourney:
    path = tmp_path / name
    artifact_ids = iter(("artifact-review", "artifact-approved"))

    def next_id(prefix: str) -> str:
        if prefix == "assessment":
            return "assessment-source"
        if prefix == "artifact":
            return next(artifact_ids)
        return f"{prefix}-generated"

    repository = SQLiteAssessmentRepository(
        path,
        clock=lambda: FIXED_TIME,
        id_factory=next_id,
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
    approval_event = next(
        event for event in approved.review.events if event.action.value == "approve"
    )
    source = PreliminarySourceSnapshot(
        source_assessment_id=assessment.assessment_id,
        approved_review_artifact_id=approved_ref.artifact_id,
        approved_review_schema_version="phase4-v0.1",
        approved_review_payload_sha256=stored.payload_sha256,
        source_document_id=approved.review.original_candidate.source_document_id,
        extraction_run_id=approved.review.original_candidate.extraction_run_id,
        review_id=approved.review.review_id,
        approval_event_id=approval_event.event_id,
        approved_at=approved.approval.approved_at,
        validated_process_id=approved.business_process.process_id,
        validated_process_fingerprint=fingerprint_business_process(
            approved.business_process
        ),
    )
    journey = PreliminaryJourney(
        schema_version="preliminary-journey.v0.1",
        store_id="preliminary-journey-store.v0.1",
        store_version="0.1.0",
        journey_id="journey-1",
        source=source,
        created_at=FIXED_TIME,
    )
    SQLitePreliminaryJourneyStore(path, clock=lambda: FIXED_TIME)
    return PreparedJourney(
        path=path,
        repository=repository,
        approved=approved,
        approved_artifact_id=approved_ref.artifact_id,
        source=source,
        journey=journey,
    )


def _insert_journey(connection: sqlite3.Connection, journey: PreliminaryJourney) -> None:
    payload_json, payload_sha = serialize_preliminary_persistence_record(
        PreliminaryPersistenceRecordType.JOURNEY,
        journey.schema_version,
        journey,
    )
    source = journey.source
    connection.execute(
        """INSERT INTO preliminary_journeys VALUES (
               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
           )""",
        (
            journey.journey_id,
            journey.schema_version,
            journey.store_id,
            journey.store_version,
            source.source_assessment_id,
            source.approved_review_artifact_id,
            source.approved_review_schema_version,
            source.approved_review_payload_sha256,
            source.source_document_id,
            source.extraction_run_id,
            source.review_id,
            source.approval_event_id,
            source.approved_at.isoformat(),
            source.validated_process_id,
            source.validated_process_fingerprint,
            journey.created_at.isoformat(),
            payload_json,
            payload_sha,
        ),
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


def _created_event(journey_id: str = "journey-1") -> PreliminaryJourneyEvent:
    return PreliminaryJourneyEvent(
        schema_version="preliminary-journey-event.v0.1",
        event_id="event-created",
        journey_id=journey_id,
        event_sequence=1,
        event_type=PreliminaryJourneyEventType.JOURNEY_CREATED,
        occurred_at=FIXED_TIME,
        payload=JourneyCreatedPayload(
            schema_version="journey-created.v0.1",
            journey_id=journey_id,
            source_assessment_id="assessment-source",
            approved_review_artifact_id="artifact-generated",
        ),
    )


def _route_event(
    sequence: int,
    route: AssessmentJourney,
    *,
    event_id: str | None = None,
) -> PreliminaryJourneyEvent:
    return PreliminaryJourneyEvent(
        schema_version="preliminary-journey-event.v0.1",
        event_id=event_id or f"event-route-{sequence}",
        journey_id="journey-1",
        event_sequence=sequence,
        event_type=(
            PreliminaryJourneyEventType.ROUTE_SELECTED
            if sequence == 2
            else PreliminaryJourneyEventType.ROUTE_CHANGED
        ),
        occurred_at=FIXED_TIME,
        payload=JourneySelection(
            schema_version="journey-selection.v0.1",
            journey=route,
        ),
    )


def _manifest(
    prepared: PreparedJourney,
    run_id: str,
    token: str,
    *,
    route_event: PreliminaryJourneyEvent,
    retry_of: str | None = None,
) -> PreliminaryRunManifest:
    return PreliminaryRunManifest(
        schema_version="preliminary-run-manifest.v0.1",
        store_id="preliminary-journey-store.v0.1",
        preliminary_run_id=run_id,
        journey_id="journey-1",
        request_token=token,
        retry_of_run_id=retry_of,
        route_choice_event_id=route_event.event_id,
        route_choice_event_sequence=route_event.event_sequence,
        source=prepared.source,
        evaluator=PreliminaryEvaluatorReference(
            evaluator_id="preliminary-evaluator.v0.1",
            evaluator_version="0.1.0",
        ),
        rule_set=PRELIMINARY_EVALUATOR_RULES_V0_1.reference(),
        output_schema_version="preliminary-assessment.v0.1",
        created_at=FIXED_TIME,
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


def _run_event(
    run_id: str,
    sequence: int,
    event_type: PreliminaryRunEventType,
    *,
    result_id: str | None = None,
) -> PreliminaryRunLifecycleEvent:
    if event_type is PreliminaryRunEventType.RUN_STARTED:
        payload = PreliminaryRunStartedPayload(
            schema_version="preliminary-run-started.v0.1",
            preliminary_run_id=run_id,
        )
    elif event_type is PreliminaryRunEventType.RUN_ABANDONED:
        payload = PreliminaryRunAbandonedPayload(
            schema_version="preliminary-run-abandoned.v0.1",
            preliminary_run_id=run_id,
            reason_code="INTERRUPTED",
        )
    else:
        assert result_id is not None
        payload = PreliminaryRunCompletedPayload(
            schema_version="preliminary-run-completed.v0.1",
            preliminary_run_id=run_id,
            preliminary_result_id=result_id,
        )
    return PreliminaryRunLifecycleEvent(
        schema_version="preliminary-run-event.v0.1",
        run_event_id=f"run-event-{run_id}-{sequence}",
        preliminary_run_id=run_id,
        journey_id="journey-1",
        event_sequence=sequence,
        event_type=event_type,
        occurred_at=FIXED_TIME,
        payload=payload,
    )


def _insert_run_event(
    connection: sqlite3.Connection, event: PreliminaryRunLifecycleEvent
) -> None:
    payload_json, payload_sha = serialize_preliminary_persistence_record(
        PreliminaryPersistenceRecordType.RUN_EVENT,
        event.schema_version,
        event,
    )
    result_id = getattr(event.payload, "preliminary_result_id", None)
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
            result_id,
            event.occurred_at.isoformat(),
            payload_json,
            payload_sha,
        ),
    )


def _seed_journey(prepared: PreparedJourney) -> PreliminaryJourneyEvent:
    connection = _connect(prepared.path)
    try:
        _insert_journey(connection, prepared.journey)
        created = _created_event()
        created = created.model_copy(
            update={
                "payload": created.payload.model_copy(
                    update={
                        "approved_review_artifact_id": prepared.approved_artifact_id
                    }
                )
            }
        )
        _insert_journey_event(connection, created)
        route = _route_event(2, AssessmentJourney.EXPLORE_PROCESS)
        _insert_journey_event(connection, route)
        connection.commit()
        return route
    finally:
        connection.close()


def test_schema_is_additive_for_new_and_existing_writable_databases(
    tmp_path: Path,
) -> None:
    prepared = _prepare(tmp_path)
    store = SQLitePreliminaryJourneyStore(prepared.path, clock=lambda: FIXED_TIME)
    connection = _connect(prepared.path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "preliminary_journeys",
            "preliminary_journey_events",
            "preliminary_run_manifests",
            "preliminary_run_events",
            "preliminary_run_state_index",
            "preliminary_results",
            "preliminary_result_supersessions",
            "preliminary_formal_lifecycles",
            "preliminary_formal_start_requests",
            "preliminary_route_requests",
        } <= tables
        assert store.migration_versions() == (1, 2, 3, 4, 5, 6)
        assert [
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ] == [1, 2, 3, 4]
        assert connection.execute("SELECT COUNT(*) FROM assessments").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM assessment_artifacts"
        ).fetchone()[0] == 2
    finally:
        connection.close()


def test_schema_installs_on_an_empty_new_strict_database(tmp_path: Path) -> None:
    path = tmp_path / "empty.db"
    strict = SQLiteAssessmentRepository(path, clock=lambda: FIXED_TIME)
    store = SQLitePreliminaryJourneyStore(path, clock=lambda: FIXED_TIME)

    assert store.migration_versions() == (1, 2, 3, 4, 5, 6)
    created = strict.create_assessment("Created after Slice 1", ExecutionMode.OFFLINE_DEMO)
    assert SQLiteAssessmentRepository(path).get_assessment(created.assessment_id) == created


def test_slice_two_migrates_a_writable_slice_one_database_additively(
    tmp_path: Path,
) -> None:
    path = tmp_path / "slice-one.db"
    repository = SQLiteAssessmentRepository(path, clock=lambda: FIXED_TIME)
    assessment = repository.create_assessment("Slice 1", ExecutionMode.OFFLINE_DEMO)
    connection = _connect(path)
    try:
        version, script = PRELIMINARY_JOURNEY_STORE_MIGRATIONS[0]
        connection.executescript("BEGIN IMMEDIATE;\n" + script)
        connection.execute(
            """INSERT INTO preliminary_journey_schema_migrations(
                   version, store_id, store_version, applied_at
               ) VALUES (?, ?, ?, ?)""",
            (
                version,
                "preliminary-journey-store.v0.1",
                "0.1.0",
                FIXED_TIME.isoformat(),
            ),
        )
        connection.commit()
        before = connection.execute(
            "SELECT * FROM assessments WHERE assessment_id = ?",
            (assessment.assessment_id,),
        ).fetchone()
    finally:
        connection.close()

    store = SQLitePreliminaryJourneyStore(path, clock=lambda: FIXED_TIME)
    connection = _connect(path)
    try:
        after = connection.execute(
            "SELECT * FROM assessments WHERE assessment_id = ?",
            (assessment.assessment_id,),
        ).fetchone()
        assert before == after
        assert store.migration_versions() == (1, 2, 3, 4, 5, 6)
        assert connection.execute(
            """SELECT 1 FROM sqlite_master
               WHERE type = 'table' AND name = 'preliminary_route_requests'"""
        ).fetchone() is not None
    finally:
        connection.close()


def test_slice_three_migrates_a_writable_slice_two_database_additively(
    tmp_path: Path,
) -> None:
    path = tmp_path / "slice-two.db"
    repository = SQLiteAssessmentRepository(path, clock=lambda: FIXED_TIME)
    assessment = repository.create_assessment("Slice 2", ExecutionMode.OFFLINE_DEMO)
    connection = _connect(path)
    try:
        for version, script in PRELIMINARY_JOURNEY_STORE_MIGRATIONS[:2]:
            connection.executescript("BEGIN IMMEDIATE;\n" + script)
            connection.execute(
                """INSERT INTO preliminary_journey_schema_migrations(
                       version, store_id, store_version, applied_at
                   ) VALUES (?, ?, ?, ?)""",
                (
                    version,
                    "preliminary-journey-store.v0.1",
                    "0.1.0",
                    FIXED_TIME.isoformat(),
                ),
            )
            connection.commit()
        before = tuple(
            connection.execute(
                "SELECT * FROM assessments WHERE assessment_id = ?",
                (assessment.assessment_id,),
            ).fetchone()
        )
    finally:
        connection.close()

    store = SQLitePreliminaryJourneyStore(path, clock=lambda: FIXED_TIME)
    connection = _connect(path)
    try:
        assert store.migration_versions() == (1, 2, 3, 4, 5, 6)
        assert tuple(
            connection.execute(
                "SELECT * FROM assessments WHERE assessment_id = ?",
                (assessment.assessment_id,),
            ).fetchone()
        ) == before
        assert connection.execute(
            """SELECT 1 FROM sqlite_master
               WHERE type = 'index'
                 AND name = 'idx_preliminary_one_predecessor_per_result'"""
        ).fetchone() is not None
    finally:
        connection.close()


def test_slice_four_migrates_a_writable_slice_three_database_additively(
    tmp_path: Path,
) -> None:
    path = tmp_path / "slice-three.db"
    repository = SQLiteAssessmentRepository(path, clock=lambda: FIXED_TIME)
    assessment = repository.create_assessment("Slice 3", ExecutionMode.OFFLINE_DEMO)
    connection = _connect(path)
    try:
        for version, script in PRELIMINARY_JOURNEY_STORE_MIGRATIONS[:3]:
            connection.executescript("BEGIN IMMEDIATE;\n" + script)
            connection.execute(
                """INSERT INTO preliminary_journey_schema_migrations(
                       version, store_id, store_version, applied_at
                   ) VALUES (?, ?, ?, ?)""",
                (
                    version,
                    "preliminary-journey-store.v0.1",
                    "0.1.0",
                    FIXED_TIME.isoformat(),
                ),
            )
            connection.commit()
        before = tuple(
            connection.execute(
                "SELECT * FROM assessments WHERE assessment_id = ?",
                (assessment.assessment_id,),
            ).fetchone()
        )
    finally:
        connection.close()

    store = SQLitePreliminaryJourneyStore(path, clock=lambda: FIXED_TIME)
    connection = _connect(path)
    try:
        assert store.migration_versions() == (1, 2, 3, 4, 5, 6)
        assert tuple(
            connection.execute(
                "SELECT * FROM assessments WHERE assessment_id = ?",
                (assessment.assessment_id,),
            ).fetchone()
        ) == before
        assert connection.execute(
            """SELECT 1 FROM sqlite_master
               WHERE type = 'index'
                 AND name = 'idx_preliminary_recovery_request_token'"""
        ).fetchone() is not None
    finally:
        connection.close()


def test_slice_five_migrates_a_writable_slice_four_database_additively(
    tmp_path: Path,
) -> None:
    path = tmp_path / "slice-four.db"
    repository = SQLiteAssessmentRepository(path, clock=lambda: FIXED_TIME)
    assessment = repository.create_assessment("Slice 4", ExecutionMode.OFFLINE_DEMO)
    connection = _connect(path)
    try:
        for version, script in PRELIMINARY_JOURNEY_STORE_MIGRATIONS[:4]:
            connection.executescript("BEGIN IMMEDIATE;\n" + script)
            connection.execute(
                """INSERT INTO preliminary_journey_schema_migrations(
                       version, store_id, store_version, applied_at
                   ) VALUES (?, ?, ?, ?)""",
                (
                    version,
                    "preliminary-journey-store.v0.1",
                    "0.1.0",
                    FIXED_TIME.isoformat(),
                ),
            )
            connection.commit()
        before = tuple(
            connection.execute(
                "SELECT * FROM assessments WHERE assessment_id = ?",
                (assessment.assessment_id,),
            ).fetchone()
        )
    finally:
        connection.close()

    store = SQLitePreliminaryJourneyStore(path, clock=lambda: FIXED_TIME)
    connection = _connect(path)
    try:
        assert store.migration_versions() == (1, 2, 3, 4, 5, 6)
        assert tuple(
            connection.execute(
                "SELECT * FROM assessments WHERE assessment_id = ?",
                (assessment.assessment_id,),
            ).fetchone()
        ) == before
        assert connection.execute(
            """SELECT 1 FROM sqlite_master
               WHERE type = 'table'
                 AND name = 'preliminary_formal_start_requests'"""
        ).fetchone() is not None
    finally:
        connection.close()


def test_legacy_rows_are_byte_for_byte_logically_invariant_after_migration(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy.db"
    repository = SQLiteAssessmentRepository(path, clock=lambda: FIXED_TIME)
    record = repository.create_assessment("Legacy", ExecutionMode.OFFLINE_DEMO)
    connection = _connect(path)
    try:
        before_assessments = connection.execute(
            "SELECT * FROM assessments ORDER BY assessment_id"
        ).fetchall()
        before_artifacts = connection.execute(
            "SELECT * FROM assessment_artifacts ORDER BY artifact_id"
        ).fetchall()
        before_active = connection.execute(
            "SELECT * FROM active_artifacts ORDER BY artifact_type"
        ).fetchall()
    finally:
        connection.close()

    SQLitePreliminaryJourneyStore(path, clock=lambda: FIXED_TIME)
    connection = _connect(path)
    try:
        assert connection.execute(
            "SELECT * FROM assessments ORDER BY assessment_id"
        ).fetchall() == before_assessments
        assert connection.execute(
            "SELECT * FROM assessment_artifacts ORDER BY artifact_id"
        ).fetchall() == before_artifacts
        assert connection.execute(
            "SELECT * FROM active_artifacts ORDER BY artifact_type"
        ).fetchall() == before_active
    finally:
        connection.close()
    assert SQLiteAssessmentRepository(path).get_assessment(record.assessment_id).title == "Legacy"


def test_journey_ownership_uniqueness_ordering_and_immutability_are_enforced(
    tmp_path: Path,
) -> None:
    prepared = _prepare(tmp_path)
    connection = _connect(prepared.path)
    try:
        wrong_source = prepared.journey.model_copy(
            update={
                "journey_id": "journey-wrong",
                "source": prepared.source.model_copy(
                    update={"source_assessment_id": "another-assessment"}
                ),
            }
        )
        with pytest.raises(sqlite3.IntegrityError, match="pinned source"):
            _insert_journey(connection, wrong_source)

        _insert_journey(connection, prepared.journey)
        with pytest.raises(sqlite3.IntegrityError):
            duplicate = prepared.journey.model_copy(update={"journey_id": "journey-2"})
            _insert_journey(connection, duplicate)

        created = _created_event().model_copy(
            update={
                "payload": _created_event().payload.model_copy(
                    update={
                        "approved_review_artifact_id": prepared.approved_artifact_id
                    }
                )
            }
        )
        _insert_journey_event(connection, created)
        with pytest.raises(sqlite3.IntegrityError, match="gap-free"):
            _insert_journey_event(
                connection,
                _route_event(3, AssessmentJourney.EXPLORE_PROCESS),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE preliminary_journeys SET created_at = ? WHERE journey_id = ?",
                (FIXED_TIME.isoformat(), prepared.journey.journey_id),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "DELETE FROM preliminary_journey_events WHERE event_id = ?",
                (created.event_id,),
            )
    finally:
        connection.close()


def test_event_type_payload_schema_and_payload_columns_fail_closed(
    tmp_path: Path,
) -> None:
    prepared = _prepare(tmp_path)
    connection = _connect(prepared.path)
    try:
        _insert_journey(connection, prepared.journey)
        created = _created_event().model_copy(
            update={
                "payload": _created_event().payload.model_copy(
                    update={
                        "approved_review_artifact_id": prepared.approved_artifact_id
                    }
                )
            }
        )
        _insert_journey_event(connection, created)
        route = _route_event(2, AssessmentJourney.EXPLORE_PROCESS)
        payload_json, payload_sha = serialize_preliminary_persistence_record(
            PreliminaryPersistenceRecordType.JOURNEY_EVENT,
            route.schema_version,
            route,
        )
        with pytest.raises(sqlite3.IntegrityError, match="payload schema"):
            connection.execute(
                """INSERT INTO preliminary_journey_events VALUES (
                       ?, ?, ?, ?, ?, ?, ?, ?, ?
                   )""",
                (
                    route.event_id,
                    route.journey_id,
                    route.event_sequence,
                    route.schema_version,
                    route.event_type.value,
                    "journey-created.v0.1",
                    route.occurred_at.isoformat(),
                    payload_json,
                    payload_sha,
                ),
            )
        with pytest.raises(sqlite3.IntegrityError, match="columns do not match"):
            connection.execute(
                """INSERT INTO preliminary_journey_events VALUES (
                       ?, ?, ?, ?, ?, ?, ?, ?, ?
                   )""",
                (
                    "event-route-wrong-column",
                    route.journey_id,
                    route.event_sequence,
                    route.schema_version,
                    route.event_type.value,
                    route.payload.schema_version,
                    route.occurred_at.isoformat(),
                    payload_json,
                    payload_sha,
                ),
            )
    finally:
        connection.close()


def test_route_pin_uses_latest_route_choice_not_latest_audit_event(
    tmp_path: Path,
) -> None:
    prepared = _prepare(tmp_path)
    route = _seed_journey(prepared)
    connection = _connect(prepared.path)
    try:
        first = _manifest(prepared, "run-1", "token-1", route_event=route)
        _insert_manifest(connection, first)
        linked = PreliminaryJourneyEvent(
            schema_version="preliminary-journey-event.v0.1",
            event_id="event-run-linked",
            journey_id="journey-1",
            event_sequence=3,
            event_type=PreliminaryJourneyEventType.RUN_LINKED,
            occurred_at=FIXED_TIME,
            payload=PreliminaryRunLinkedPayload(
                schema_version="preliminary-run-link.v0.1",
                preliminary_run_id="run-1",
                route_choice_event_id=route.event_id,
                route_choice_event_sequence=route.event_sequence,
            ),
        )
        _insert_journey_event(connection, linked)

        second = _manifest(prepared, "run-2", "token-2", route_event=route)
        _insert_manifest(connection, second)

        changed = _route_event(
            4,
            AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
            event_id="event-route-formal",
        )
        _insert_journey_event(connection, changed)
        with pytest.raises(sqlite3.IntegrityError, match="latest Explore"):
            _insert_manifest(
                connection,
                _manifest(prepared, "run-3", "token-3", route_event=route),
            )
    finally:
        connection.close()


def test_one_active_run_retry_lineage_and_original_token_are_enforced(
    tmp_path: Path,
) -> None:
    prepared = _prepare(tmp_path)
    route = _seed_journey(prepared)
    connection = _connect(prepared.path)
    try:
        first = _manifest(prepared, "run-1", "token-1", route_event=route)
        second = _manifest(prepared, "run-2", "token-2", route_event=route)
        _insert_manifest(connection, first)
        _insert_manifest(connection, second)
        _insert_run_event(
            connection,
            _run_event("run-1", 1, PreliminaryRunEventType.RUN_STARTED),
        )
        with pytest.raises(sqlite3.IntegrityError, match="one non-terminal"):
            _insert_run_event(
                connection,
                _run_event("run-2", 1, PreliminaryRunEventType.RUN_STARTED),
            )
        abandoned = _run_event(
            "run-1", 2, PreliminaryRunEventType.RUN_ABANDONED
        )
        _insert_run_event(connection, abandoned)

        retry = _manifest(
            prepared,
            "run-retry",
            "token-retry",
            route_event=route,
            retry_of="run-1",
        )
        _insert_manifest(connection, retry)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_manifest(
                connection,
                _manifest(
                    prepared,
                    "run-replayed-token",
                    "token-1",
                    route_event=route,
                    retry_of="run-1",
                ),
            )
        with pytest.raises(sqlite3.IntegrityError, match="failed or abandoned"):
            _insert_manifest(
                connection,
                _manifest(
                    prepared,
                    "run-invalid-retry",
                    "token-invalid-retry",
                    route_event=route,
                    retry_of="run-2",
                ),
            )
    finally:
        connection.close()


def test_projection_is_constrained_and_partial_unique_index_exists(
    tmp_path: Path,
) -> None:
    prepared = _prepare(tmp_path)
    route = _seed_journey(prepared)
    connection = _connect(prepared.path)
    try:
        manifest = _manifest(prepared, "run-1", "token-1", route_event=route)
        _insert_manifest(connection, manifest)
        start = _run_event("run-1", 1, PreliminaryRunEventType.RUN_STARTED)
        _insert_run_event(connection, start)
        projection = PreliminaryRunStateProjection(
            schema_version="preliminary-run-state-projection.v0.1",
            preliminary_run_id="run-1",
            journey_id="journey-1",
            projected_status=PreliminaryRunProjectedStatus.STARTED,
            projected_at=FIXED_TIME,
        )
        payload_json, payload_sha = serialize_preliminary_persistence_record(
            PreliminaryPersistenceRecordType.RUN_STATE_PROJECTION,
            projection.schema_version,
            projection,
        )
        connection.execute(
            """INSERT INTO preliminary_run_state_index VALUES (
                   ?, ?, ?, ?, ?, ?, ?, ?
               )""",
            (
                projection.preliminary_run_id,
                projection.journey_id,
                projection.schema_version,
                projection.projected_status.value,
                None,
                projection.projected_at.isoformat(),
                payload_json,
                payload_sha,
            ),
        )
        with pytest.raises(sqlite3.IntegrityError, match="must match"):
            connection.execute(
                """UPDATE preliminary_run_state_index
                   SET projected_status = 'FAILED', terminal_event_id = 'missing'
                   WHERE preliminary_run_id = 'run-1'"""
            )
        index_sql = connection.execute(
            """SELECT sql FROM sqlite_master
               WHERE name = 'idx_preliminary_one_started_run_per_journey'"""
        ).fetchone()[0]
        assert "WHERE projected_status = 'STARTED'" in index_sql
    finally:
        connection.close()


def test_completed_run_requires_exact_same_run_result_and_is_immutable(
    tmp_path: Path,
) -> None:
    prepared = _prepare(tmp_path)
    route = _seed_journey(prepared)
    connection = _connect(prepared.path)
    try:
        manifest = _manifest(prepared, "run-1", "token-1", route_event=route)
        _insert_manifest(connection, manifest)
        _insert_run_event(
            connection,
            _run_event("run-1", 1, PreliminaryRunEventType.RUN_STARTED),
        )
        completion = _run_event(
            "run-1",
            2,
            PreliminaryRunEventType.RUN_COMPLETED,
            result_id="result-1",
        )
        with pytest.raises(sqlite3.IntegrityError, match="immutable result"):
            _insert_run_event(connection, completion)

        evaluated = PreliminaryAssessmentEvaluator(
            clock=lambda: FIXED_TIME,
            id_factory=lambda: "run-1",
        ).evaluate(prepared.approved)
        assert isinstance(evaluated, PreliminaryEvaluationSuccess)
        result = PersistedPreliminaryResult(
            schema_version="preliminary-result.v0.1",
            preliminary_result_id="result-1",
            preliminary_run_id="run-1",
            journey_id="journey-1",
            completed_run_event_id=completion.run_event_id,
            source=prepared.source,
            evaluator=manifest.evaluator,
            rule_set=manifest.rule_set,
            output_schema_version="preliminary-assessment.v0.1",
            created_at=FIXED_TIME,
            assessment=evaluated.assessment,
        )
        result_json, result_sha = serialize_preliminary_persistence_record(
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
                result_json,
                result_sha,
            ),
        )
        _insert_run_event(connection, completion)
        connection.commit()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE preliminary_results SET created_at = created_at"
            )
    finally:
        connection.close()


def test_formal_record_requires_latest_organisational_route_and_context_only_use(
    tmp_path: Path,
) -> None:
    prepared = _prepare(tmp_path)
    route = _seed_journey(prepared)
    formal = PreliminaryFormalLifecycle(
        schema_version="preliminary-formal-lifecycle.v0.1",
        formal_lifecycle_id="formal-1",
        journey_id="journey-1",
        source=prepared.source,
        route_choice_event_id=route.event_id,
        route_choice_event_sequence=route.event_sequence,
        status="AWAITING_FORMAL_INPUTS",
        created_at=FIXED_TIME,
    )
    payload_json, payload_sha = serialize_preliminary_persistence_record(
        PreliminaryPersistenceRecordType.FORMAL_LIFECYCLE,
        formal.schema_version,
        formal,
    )
    source = formal.source
    connection = _connect(prepared.path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="organisational"):
            connection.execute(
                """INSERT INTO preliminary_formal_lifecycles VALUES (
                       ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                   )""",
                (
                    formal.formal_lifecycle_id,
                    formal.journey_id,
                    formal.schema_version,
                    source.source_assessment_id,
                    source.approved_review_artifact_id,
                    source.approved_review_payload_sha256,
                    source.source_document_id,
                    source.validated_process_id,
                    source.validated_process_fingerprint,
                    formal.route_choice_event_id,
                    formal.route_choice_event_sequence,
                    formal.status,
                    None,
                    None,
                    formal.created_at.isoformat(),
                    payload_json,
                    payload_sha,
                ),
            )
    finally:
        connection.close()


def test_frozen_workspace_refusal_is_byte_and_sidecar_invariant(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    SQLiteAssessmentRepository(source, clock=lambda: FIXED_TIME)
    protected = tmp_path / "evaluation" / "portfolio" / "case" / "workspace.db"
    protected.parent.mkdir(parents=True)
    shutil.copy2(source, protected)
    before = protected.read_bytes()
    before_entries = tuple(sorted(item.name for item in protected.parent.iterdir()))

    with pytest.raises(FrozenEvaluationWorkspaceError):
        SQLitePreliminaryJourneyStore(protected, clock=lambda: FIXED_TIME)

    assert protected.read_bytes() == before
    assert tuple(sorted(item.name for item in protected.parent.iterdir())) == before_entries
    assert not any(
        item.name.endswith(("-journal", "-wal", "-shm"))
        for item in protected.parent.iterdir()
    )


def test_strict_repository_remains_compatible_and_ignores_preliminary_tables(
    tmp_path: Path,
) -> None:
    prepared = _prepare(tmp_path)
    _seed_journey(prepared)
    reopened = SQLiteAssessmentRepository(prepared.path)
    workspace = reopened.load_workspace(prepared.source.source_assessment_id)
    assert workspace.assessment.current_stage is WorkflowStage.APPROVED
    assert set(workspace.active_artifacts) == {
        ArtifactType.REVIEW_SESSION,
        ArtifactType.APPROVED_REVIEW,
    }
    assert reopened.list_assessments()[0].assessment_id == (
        prepared.source.source_assessment_id
    )

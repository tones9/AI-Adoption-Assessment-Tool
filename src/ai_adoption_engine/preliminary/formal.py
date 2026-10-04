"""Explicit isolated formal-start boundary for a Preliminary journey."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from ai_adoption_engine.models.preliminary_assessment import (
    AssessmentJourney,
    JourneySelection,
)
from ai_adoption_engine.models.preliminary_journey import (
    FormalStartResult,
    PreliminaryCompatibilityIdentity,
)
from ai_adoption_engine.models.preliminary_persistence import (
    PRELIMINARY_FORMAL_LIFECYCLE_SCHEMA_VERSION,
    PRELIMINARY_FORMAL_START_REQUEST_SCHEMA_VERSION,
    PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
    PreliminaryFormalLifecycle,
    PreliminaryFormalLifecycleStartedPayload,
    PreliminaryFormalStartRequest,
    PreliminaryJourneyEvent,
    PreliminaryJourneyEventType,
    PreliminaryPersistenceRecordType,
    PreliminaryResultReferenceUse,
)
from ai_adoption_engine.persistence.base import PersistenceError
from ai_adoption_engine.persistence.preliminary import SQLitePreliminaryJourneyStore
from ai_adoption_engine.persistence.preliminary_serialization import (
    serialize_preliminary_persistence_record,
)
from ai_adoption_engine.preliminary.journey import (
    PreliminaryJourneyCorruptionError,
    PreliminaryJourneyService,
    current_preliminary_compatibility_identity,
)


Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]


class PreliminaryFormalStartServiceError(PersistenceError):
    """A formal-start operation failed without changing stored history."""


class PreliminaryFormalStartNotAllowedError(PreliminaryFormalStartServiceError):
    """The requested source, route, or context reference cannot authorise start."""


class PreliminaryFormalStartConflictError(PreliminaryFormalStartServiceError):
    """The journey already has a different immutable formal lifecycle."""


class PreliminaryFormalStartIdempotencyError(PreliminaryFormalStartServiceError):
    """A formal-start token was replayed with materially different parameters."""


class PreliminaryFormalStartWriteError(PreliminaryFormalStartServiceError):
    """The formal-start transaction did not commit atomically."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


class PreliminaryFormalStartService:
    """Create the isolated awaiting-inputs sibling lifecycle only."""

    def __init__(
        self,
        store: SQLitePreliminaryJourneyStore,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
        supported_identity: PreliminaryCompatibilityIdentity | None = None,
    ) -> None:
        self.store = store
        self.clock = clock or _utc_now
        self.id_factory = id_factory or _new_id
        self.supported_identity = (
            supported_identity or current_preliminary_compatibility_identity()
        )
        if self.supported_identity != current_preliminary_compatibility_identity():
            raise PreliminaryFormalStartNotAllowedError(
                "Formal lifecycle remains pinned to Preliminary v0.1"
            )
        self._journeys = PreliminaryJourneyService(
            store,
            clock=self.clock,
            id_factory=self.id_factory,
            supported_identity=self.supported_identity,
        )

    def start_formal_lifecycle(
        self,
        journey_id: str,
        *,
        request_token: str,
        route_choice_event_id: str,
        route_choice_event_sequence: int,
        preliminary_result_id: str | None = None,
        preliminary_result_use: PreliminaryResultReferenceUse | None = None,
    ) -> FormalStartResult:
        """Atomically create or replay one awaiting-inputs formal lifecycle."""

        if not request_token.strip():
            raise ValueError("Formal-start request token cannot be blank")
        if route_choice_event_sequence < 1:
            raise ValueError("Route-choice event sequence must be positive")
        if preliminary_result_id is None:
            if preliminary_result_use is not None:
                raise PreliminaryFormalStartNotAllowedError(
                    "A context classification requires a Preliminary result"
                )
        elif (
            preliminary_result_use
            is not PreliminaryResultReferenceUse.CONTEXT_ONLY_NOT_FORMAL_EVIDENCE
        ):
            raise PreliminaryFormalStartNotAllowedError(
                "A Preliminary result may be referenced only as context"
            )

        try:
            with self.store._transaction() as connection:
                journey = self._journeys._load_journey(connection, journey_id)
                self._journeys._validate_journey_source(
                    connection, journey, require_active=False
                )
                events = self._journeys._load_journey_events(
                    connection, journey_id, journey=journey
                )
                self._journeys._load_route_requests(
                    connection, journey_id, events
                )
                manifests = self._journeys._load_run_manifests(
                    connection, journey
                )
                run_events = self._journeys._load_run_events(
                    connection, journey_id, manifests
                )
                self._journeys._validate_run_state_projections(
                    connection, journey_id, manifests, run_events
                )
                run_order = self._journeys._run_order(events, manifests)
                self._journeys._validate_recovery_events(
                    events, manifests, run_events, run_order
                )
                results = self._journeys._load_results(
                    connection, journey, manifests, run_events
                )
                self._journeys._load_supersessions(
                    connection, journey, events, results, run_order
                )
                lifecycle = self._journeys._load_formal_lifecycle(
                    connection, journey, events
                )
                requests = self._journeys._load_formal_start_requests(
                    connection, journey_id
                )

                replay = requests.get(request_token)
                if replay is not None:
                    if lifecycle is None:
                        raise PreliminaryJourneyCorruptionError(
                            "Formal-start request has no lifecycle"
                        )
                    if (
                        replay.route_choice_event_id != route_choice_event_id
                        or replay.route_choice_event_sequence
                        != route_choice_event_sequence
                        or replay.preliminary_result_id != preliminary_result_id
                        or replay.preliminary_result_use
                        != (
                            preliminary_result_use.value
                            if preliminary_result_use is not None
                            else None
                        )
                    ):
                        raise PreliminaryFormalStartIdempotencyError(
                            "Formal-start token was already used for another request"
                        )
                    return FormalStartResult(
                        request=replay,
                        lifecycle=lifecycle,
                        start_event=self._formal_start_event(events),
                        replayed=True,
                    )

                if lifecycle is not None or requests:
                    raise PreliminaryFormalStartConflictError(
                        "This journey already has an immutable formal lifecycle"
                    )

                self._journeys._validate_journey_source(
                    connection, journey, require_active=True
                )
                latest_route = self._latest_route_choice(events)
                if (
                    latest_route is None
                    or not isinstance(latest_route.payload, JourneySelection)
                    or latest_route.payload.journey
                    is not AssessmentJourney.ORGANISATIONAL_ASSESSMENT
                ):
                    raise PreliminaryFormalStartNotAllowedError(
                        "The latest route choice must select Organisational Assessment"
                    )
                if (
                    latest_route.event_id != route_choice_event_id
                    or latest_route.event_sequence != route_choice_event_sequence
                ):
                    raise PreliminaryFormalStartNotAllowedError(
                        "The formal-start request pins a stale route-choice event"
                    )

                referenced_result = None
                if preliminary_result_id is not None:
                    if (
                        self.supported_identity
                        != current_preliminary_compatibility_identity()
                    ):
                        raise PreliminaryFormalStartNotAllowedError(
                            "Formal-start identity does not match the current Preliminary contract"
                        )
                    referenced_result = next(
                        (
                            result
                            for result in results
                            if result.preliminary_result_id
                            == preliminary_result_id
                        ),
                        None,
                    )
                    if (
                        referenced_result is None
                        or not self._journeys._result_is_compatible(
                            referenced_result, journey
                        )
                    ):
                        raise PreliminaryFormalStartNotAllowedError(
                            "Referenced Preliminary result is not compatible same-journey context"
                        )

                now = self._now()
                lifecycle = PreliminaryFormalLifecycle(
                    schema_version=PRELIMINARY_FORMAL_LIFECYCLE_SCHEMA_VERSION,
                    formal_lifecycle_id=self._id("formal-lifecycle"),
                    journey_id=journey_id,
                    source=journey.source,
                    route_choice_event_id=latest_route.event_id,
                    route_choice_event_sequence=latest_route.event_sequence,
                    status="AWAITING_FORMAL_INPUTS",
                    preliminary_result_id=(
                        referenced_result.preliminary_result_id
                        if referenced_result is not None
                        else None
                    ),
                    preliminary_result_use=(
                        preliminary_result_use.value
                        if preliminary_result_use is not None
                        else None
                    ),
                    created_at=now,
                )
                request = PreliminaryFormalStartRequest(
                    schema_version=(
                        PRELIMINARY_FORMAL_START_REQUEST_SCHEMA_VERSION
                    ),
                    formal_start_request_id=self._id("formal-start-request"),
                    journey_id=journey_id,
                    request_token=request_token,
                    formal_lifecycle_id=lifecycle.formal_lifecycle_id,
                    route_choice_event_id=latest_route.event_id,
                    route_choice_event_sequence=latest_route.event_sequence,
                    preliminary_result_id=lifecycle.preliminary_result_id,
                    preliminary_result_use=lifecycle.preliminary_result_use,
                    created_at=now,
                )
                start_event = PreliminaryJourneyEvent(
                    schema_version=PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
                    event_id=self._id("journey-event"),
                    journey_id=journey_id,
                    event_sequence=events[-1].event_sequence + 1,
                    event_type=(
                        PreliminaryJourneyEventType.FORMAL_LIFECYCLE_STARTED
                    ),
                    occurred_at=now,
                    payload=PreliminaryFormalLifecycleStartedPayload(
                        schema_version="formal-lifecycle-start.v0.1",
                        formal_lifecycle_id=lifecycle.formal_lifecycle_id,
                        route_choice_event_id=latest_route.event_id,
                        route_choice_event_sequence=latest_route.event_sequence,
                    ),
                )
                self._insert_lifecycle(connection, lifecycle)
                self._insert_request(connection, request)
                self._journeys._insert_journey_event(connection, start_event)
                return FormalStartResult(
                    request=request,
                    lifecycle=lifecycle,
                    start_event=start_event,
                    replayed=False,
                )
        except (
            PreliminaryFormalStartServiceError,
            PreliminaryJourneyCorruptionError,
            ValueError,
        ):
            raise
        except Exception as exc:
            raise PreliminaryFormalStartWriteError(
                "Formal-start records did not commit atomically"
            ) from exc

    @staticmethod
    def _latest_route_choice(
        events: list[PreliminaryJourneyEvent],
    ) -> PreliminaryJourneyEvent | None:
        choices = [
            event
            for event in events
            if event.event_type
            in {
                PreliminaryJourneyEventType.ROUTE_SELECTED,
                PreliminaryJourneyEventType.ROUTE_CHANGED,
            }
        ]
        return choices[-1] if choices else None

    @staticmethod
    def _formal_start_event(
        events: list[PreliminaryJourneyEvent],
    ) -> PreliminaryJourneyEvent:
        matches = [
            event
            for event in events
            if event.event_type
            is PreliminaryJourneyEventType.FORMAL_LIFECYCLE_STARTED
        ]
        if len(matches) != 1:
            raise PreliminaryJourneyCorruptionError(
                "Formal lifecycle requires one start event"
            )
        return matches[0]

    def _insert_lifecycle(
        self,
        connection: sqlite3.Connection,
        lifecycle: PreliminaryFormalLifecycle,
    ) -> None:
        payload_json, payload_sha = serialize_preliminary_persistence_record(
            PreliminaryPersistenceRecordType.FORMAL_LIFECYCLE,
            lifecycle.schema_version,
            lifecycle,
        )
        source = lifecycle.source
        connection.execute(
            """INSERT INTO preliminary_formal_lifecycles(
                   formal_lifecycle_id, journey_id, schema_version,
                   source_assessment_id, approved_review_artifact_id,
                   approved_review_payload_sha256, source_document_id,
                   validated_process_id, validated_process_fingerprint,
                   route_choice_event_id, route_choice_event_sequence, status,
                   preliminary_result_id, preliminary_result_use, created_at,
                   payload_json, payload_sha256
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lifecycle.formal_lifecycle_id,
                lifecycle.journey_id,
                lifecycle.schema_version,
                source.source_assessment_id,
                source.approved_review_artifact_id,
                source.approved_review_payload_sha256,
                source.source_document_id,
                source.validated_process_id,
                source.validated_process_fingerprint,
                lifecycle.route_choice_event_id,
                lifecycle.route_choice_event_sequence,
                lifecycle.status,
                lifecycle.preliminary_result_id,
                lifecycle.preliminary_result_use,
                lifecycle.created_at.isoformat(),
                payload_json,
                payload_sha,
            ),
        )

    @staticmethod
    def _insert_request(
        connection: sqlite3.Connection,
        request: PreliminaryFormalStartRequest,
    ) -> None:
        payload_json, payload_sha = serialize_preliminary_persistence_record(
            PreliminaryPersistenceRecordType.FORMAL_START_REQUEST,
            request.schema_version,
            request,
        )
        connection.execute(
            """INSERT INTO preliminary_formal_start_requests VALUES (
                   ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
               )""",
            (
                request.formal_start_request_id,
                request.journey_id,
                request.schema_version,
                request.request_token,
                request.formal_lifecycle_id,
                request.route_choice_event_id,
                request.route_choice_event_sequence,
                request.preliminary_result_id,
                request.preliminary_result_use,
                request.created_at.isoformat(),
                payload_json,
                payload_sha,
            ),
        )

    def _now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Injected clock must return a timezone-aware datetime")
        return now

    def _id(self, prefix: str) -> str:
        value = self.id_factory(prefix)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Injected ID factory must return a non-blank string")
        return value

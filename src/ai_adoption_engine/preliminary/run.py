"""Explicit Slice 3 evaluator-run and immutable-result persistence service."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel

from ai_adoption_engine.models.preliminary_assessment import (
    AssessmentJourney,
    JourneySelection,
)
from ai_adoption_engine.models.preliminary_evaluation import (
    PreliminaryEvaluationFailure,
    PreliminaryEvaluationSuccess,
)
from ai_adoption_engine.models.preliminary_assessment_v0_2 import (
    PreliminaryEvaluationFailureV2,
    PreliminaryEvaluationSuccessV2,
)
from ai_adoption_engine.models.preliminary_journey import (
    PreliminaryCompatibilityIdentity,
)
from ai_adoption_engine.models.preliminary_persistence import (
    PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
    PRELIMINARY_RESULT_SCHEMA_VERSION,
    PRELIMINARY_RESULT_SUPERSESSION_SCHEMA_VERSION,
    PRELIMINARY_RUN_EVENT_SCHEMA_VERSION,
    PRELIMINARY_RUN_MANIFEST_SCHEMA_VERSION,
    PRELIMINARY_RUN_STATE_PROJECTION_SCHEMA_VERSION,
    PersistedPreliminaryResult,
    PersistedPreliminaryRuleSetReference,
    PreliminaryEvaluatorReference,
    PreliminaryJourney,
    PreliminaryJourneyEvent,
    PreliminaryJourneyEventType,
    PreliminaryPersistenceRecordType,
    PreliminaryRecoveryAction,
    PreliminaryResultRecordedPayload,
    PreliminaryResultSupersession,
    PreliminaryResultSupersessionPayload,
    PreliminaryRunCompletedPayload,
    PreliminaryRunAbandonedPayload,
    PreliminaryRunEventType,
    PreliminaryRunFailedPayload,
    PreliminaryRunLifecycleEvent,
    PreliminaryRunLinkedPayload,
    PreliminaryRunManifest,
    PreliminaryRunProjectedStatus,
    PreliminaryRunRecoveryV2Payload,
    PreliminaryRunStartedPayload,
    PreliminaryRunStateProjection,
)
from ai_adoption_engine.models.preliminary_run import (
    PreliminaryRecoveryOperationResult,
    PreliminaryRunOperationResult,
)
from ai_adoption_engine.models.review import ApprovedProcessReview
from ai_adoption_engine.persistence.base import ArtifactCorruptionError, PersistenceError
from ai_adoption_engine.persistence.preliminary import SQLitePreliminaryJourneyStore
from ai_adoption_engine.persistence.preliminary_serialization import (
    serialize_preliminary_persistence_record,
)
from ai_adoption_engine.persistence.serialization import (
    deserialize_artifact_versioned,
)
from ai_adoption_engine.preliminary.evaluator import PreliminaryAssessmentEvaluator
from ai_adoption_engine.preliminary.evaluator_v0_2 import (
    PreliminaryAssessmentEvaluatorV2,
)
from ai_adoption_engine.preliminary.journey import (
    PreliminaryJourneyCorruptionError,
    PreliminaryJourneyService,
    UnsupportedPreliminaryCompatibilityIdentityError,
    current_preliminary_compatibility_identity,
    require_supported_preliminary_compatibility_identity,
)
from ai_adoption_engine.preliminary.rules import PRELIMINARY_EVALUATOR_RULES_V0_1
from ai_adoption_engine.workspace.models import ArtifactType


Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]
EvaluationClock = Callable[[], datetime]


class PreliminaryRunServiceError(PersistenceError):
    """A Preliminary run operation could not be completed safely."""


class PreliminaryRunNotAllowedError(PreliminaryRunServiceError):
    """Current journey state does not authorize a new evaluator run."""


class PreliminaryRunConcurrencyError(PreliminaryRunServiceError):
    """Another non-terminal run already owns the journey."""


class PreliminaryRunIdempotencyError(PreliminaryRunServiceError):
    """A run request token was replayed with different request content."""


class PreliminaryRunFinalizationError(PreliminaryRunServiceError):
    """The final transaction failed, leaving a valid non-terminal run."""


class PreliminaryRunRecoveryConflictError(PreliminaryRunServiceError):
    """The requested predecessor cannot undergo that recovery transition."""


class PreliminaryRunRecoveryIdempotencyError(PreliminaryRunServiceError):
    """A recovery token was replayed with different request content."""


class PreliminaryRunRecoveryWriteError(PreliminaryRunServiceError):
    """A recovery transaction failed without committing partial history."""


@dataclass(frozen=True)
class _History:
    journey: PreliminaryJourney
    journey_events: tuple[PreliminaryJourneyEvent, ...]
    manifests: dict[str, PreliminaryRunManifest]
    run_events: dict[str, list[PreliminaryRunLifecycleEvent]]
    run_order: dict[str, int]
    results: tuple[PersistedPreliminaryResult, ...]
    supersessions: tuple[PreliminaryResultSupersession, ...]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


class PreliminaryRunResultService:
    """Run the approved deterministic evaluator through explicit transactions."""

    def __init__(
        self,
        store: SQLitePreliminaryJourneyStore,
        *,
        clock: Clock | None = None,
        evaluation_clock: EvaluationClock | None = None,
        id_factory: IdFactory | None = None,
        supported_identity: PreliminaryCompatibilityIdentity | None = None,
    ) -> None:
        self.store = store
        self.clock = clock or _utc_now
        self.evaluation_clock = evaluation_clock or self.clock
        self.id_factory = id_factory or _new_id
        try:
            self.supported_identity = require_supported_preliminary_compatibility_identity(
                supported_identity or current_preliminary_compatibility_identity()
            )
        except UnsupportedPreliminaryCompatibilityIdentityError as exc:
            raise PreliminaryRunNotAllowedError(str(exc)) from exc
        self._journeys = PreliminaryJourneyService(
            store,
            clock=self.clock,
            id_factory=self.id_factory,
            supported_identity=self.supported_identity,
        )

    def evaluate_and_persist(
        self,
        journey_id: str,
        *,
        request_token: str,
        route_choice_event_id: str,
        route_choice_event_sequence: int,
    ) -> PreliminaryRunOperationResult:
        """Start, evaluate, and terminally persist one deliberate run request."""

        if not request_token.strip():
            raise ValueError("Run request token cannot be blank")
        if route_choice_event_sequence < 1:
            raise ValueError("Route-choice event sequence must be positive")
        self._require_current_supported_identity()

        with self.store._transaction() as connection:
            history = self._load_history(connection, journey_id, require_active=False)
            replay = next(
                (
                    manifest
                    for manifest in history.manifests.values()
                    if manifest.request_token == request_token
                ),
                None,
            )
            if replay is not None:
                if (
                    replay.route_choice_event_id != route_choice_event_id
                    or replay.route_choice_event_sequence
                    != route_choice_event_sequence
                ):
                    raise PreliminaryRunIdempotencyError(
                        "Run request token was already used with another route pin"
                    )
                if not self._journeys._manifest_is_compatible(
                    replay, history.journey
                ):
                    raise PreliminaryRunIdempotencyError(
                        "Run request token belongs to another compatibility identity"
                    )
                return self._operation(history, replay, replayed=True)

            self._journeys._validate_journey_source(
                connection, history.journey, require_active=True
            )
            route_event = self._latest_route_choice(history.journey_events)
            if (
                route_event is None
                or not isinstance(route_event.payload, JourneySelection)
                or route_event.payload.journey is not AssessmentJourney.EXPLORE_PROCESS
            ):
                raise PreliminaryRunNotAllowedError(
                    "The latest route choice must select Explore this process"
                )
            if (
                route_event.event_id != route_choice_event_id
                or route_event.event_sequence != route_choice_event_sequence
            ):
                raise PreliminaryRunNotAllowedError(
                    "The run request pins a stale route-choice event"
                )
            active = [
                run_id
                for run_id, events in history.run_events.items()
                if events[-1].event_type is PreliminaryRunEventType.RUN_STARTED
            ]
            if active:
                raise PreliminaryRunConcurrencyError(
                    "A non-terminal Preliminary run already exists"
                )
            compatible_manifests = [
                manifest
                for manifest in history.manifests.values()
                if self._journeys._manifest_is_compatible(
                    manifest, history.journey
                )
            ]
            if compatible_manifests:
                latest_manifest = max(
                    compatible_manifests,
                    key=lambda item: history.run_order[item.preliminary_run_id],
                )
                latest_terminal = history.run_events[
                    latest_manifest.preliminary_run_id
                ][-1]
                if latest_terminal.event_type in {
                    PreliminaryRunEventType.RUN_FAILED,
                    PreliminaryRunEventType.RUN_ABANDONED,
                }:
                    raise PreliminaryRunNotAllowedError(
                        "Retry orchestration for failed or abandoned runs is Slice 4"
                    )

            now = self._now()
            run_id = self._id("preliminary-run")
            identity = self.supported_identity
            manifest = PreliminaryRunManifest(
                schema_version=PRELIMINARY_RUN_MANIFEST_SCHEMA_VERSION,
                store_id=self.store.store_id,
                preliminary_run_id=run_id,
                journey_id=journey_id,
                request_token=request_token,
                retry_of_run_id=None,
                route_choice_event_id=route_event.event_id,
                route_choice_event_sequence=route_event.event_sequence,
                source=history.journey.source,
                evaluator=PreliminaryEvaluatorReference(
                    evaluator_id=identity.evaluator_id,
                    evaluator_version=identity.evaluator_version,
                ),
                rule_set=self._rule_reference(identity),
                output_schema_version=identity.output_schema_version,
                created_at=now,
            )
            linked = PreliminaryJourneyEvent(
                schema_version=PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
                event_id=self._id("journey-event"),
                journey_id=journey_id,
                event_sequence=history.journey_events[-1].event_sequence + 1,
                event_type=PreliminaryJourneyEventType.RUN_LINKED,
                occurred_at=now,
                payload=PreliminaryRunLinkedPayload(
                    schema_version="preliminary-run-link.v0.1",
                    preliminary_run_id=run_id,
                    route_choice_event_id=route_event.event_id,
                    route_choice_event_sequence=route_event.event_sequence,
                ),
            )
            started = PreliminaryRunLifecycleEvent(
                schema_version=PRELIMINARY_RUN_EVENT_SCHEMA_VERSION,
                run_event_id=self._id("run-event"),
                preliminary_run_id=run_id,
                journey_id=journey_id,
                event_sequence=1,
                event_type=PreliminaryRunEventType.RUN_STARTED,
                occurred_at=now,
                payload=PreliminaryRunStartedPayload(
                    schema_version="preliminary-run-started.v0.1",
                    preliminary_run_id=run_id,
                ),
            )
            projection = PreliminaryRunStateProjection(
                schema_version=PRELIMINARY_RUN_STATE_PROJECTION_SCHEMA_VERSION,
                preliminary_run_id=run_id,
                journey_id=journey_id,
                projected_status=PreliminaryRunProjectedStatus.STARTED,
                projected_at=now,
            )
            self._insert_manifest(connection, manifest)
            self._journeys._insert_journey_event(connection, linked)
            self._insert_run_event(connection, started)
            self._insert_projection(connection, projection)
            approved_review = self._load_approved_review(connection, history.journey)

        return self._evaluate_started(manifest, started, approved_review)

    def abandon_interrupted_run(
        self,
        journey_id: str,
        preliminary_run_id: str,
        *,
        recovery_request_token: str,
    ) -> PreliminaryRecoveryOperationResult:
        """Explicitly append abandonment to one genuinely non-terminal run."""

        if not recovery_request_token.strip():
            raise ValueError("Recovery request token cannot be blank")
        self._require_current_supported_identity()
        try:
            with self.store._transaction() as connection:
                history = self._load_history(
                    connection, journey_id, require_active=False
                )
                replay = self._recovery_event_by_token(
                    history, recovery_request_token
                )
                if replay is not None:
                    payload = replay.payload
                    if (
                        not isinstance(payload, PreliminaryRunRecoveryV2Payload)
                        or payload.action is not PreliminaryRecoveryAction.ABANDON
                        or payload.predecessor_run_id != preliminary_run_id
                    ):
                        raise PreliminaryRunRecoveryIdempotencyError(
                            "Recovery token was already used for another operation"
                        )
                    manifest = history.manifests.get(preliminary_run_id)
                    if manifest is None:
                        raise PreliminaryJourneyCorruptionError(
                            "Abandonment recovery manifest is missing"
                        )
                    if not self._journeys._manifest_is_compatible(
                        manifest, history.journey
                    ):
                        raise PreliminaryRunRecoveryIdempotencyError(
                            "Recovery token belongs to another compatibility identity"
                        )
                    return PreliminaryRecoveryOperationResult(
                        action=PreliminaryRecoveryAction.ABANDON,
                        recovery_event=replay,
                        operation=self._operation(
                            history, manifest, replayed=True
                        ),
                        replayed=True,
                    )

                self._journeys._validate_journey_source(
                    connection, history.journey, require_active=True
                )
                manifest = history.manifests.get(preliminary_run_id)
                if manifest is None:
                    raise PreliminaryRunRecoveryConflictError(
                        "Recovery predecessor is missing or belongs to another journey"
                    )
                if not self._journeys._manifest_is_compatible(
                    manifest, history.journey
                ):
                    raise PreliminaryRunRecoveryConflictError(
                        "Recovery predecessor is not current-compatible"
                    )
                events = history.run_events[preliminary_run_id]
                if (
                    len(events) != 1
                    or events[0].event_type
                    is not PreliminaryRunEventType.RUN_STARTED
                    or any(
                        result.preliminary_run_id == preliminary_run_id
                        for result in history.results
                    )
                ):
                    raise PreliminaryRunRecoveryConflictError(
                        "Only a genuinely non-terminal run can be abandoned"
                    )
                now = self._now()
                terminal = PreliminaryRunLifecycleEvent(
                    schema_version=PRELIMINARY_RUN_EVENT_SCHEMA_VERSION,
                    run_event_id=self._id("run-event"),
                    preliminary_run_id=preliminary_run_id,
                    journey_id=journey_id,
                    event_sequence=2,
                    event_type=PreliminaryRunEventType.RUN_ABANDONED,
                    occurred_at=now,
                    payload=PreliminaryRunAbandonedPayload(
                        schema_version="preliminary-run-abandoned.v0.1",
                        preliminary_run_id=preliminary_run_id,
                        reason_code="EXPLICIT_INTERRUPTED_RUN_ABANDONMENT",
                    ),
                )
                recovery_event = PreliminaryJourneyEvent(
                    schema_version=PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
                    event_id=self._id("journey-event"),
                    journey_id=journey_id,
                    event_sequence=history.journey_events[-1].event_sequence + 1,
                    event_type=PreliminaryJourneyEventType.RUN_RECOVERY_RECORDED,
                    occurred_at=now,
                    payload=PreliminaryRunRecoveryV2Payload(
                        schema_version="preliminary-run-recovery.v0.2",
                        action=PreliminaryRecoveryAction.ABANDON,
                        recovery_request_token=recovery_request_token,
                        predecessor_run_id=preliminary_run_id,
                        terminal_run_event_id=terminal.run_event_id,
                    ),
                )
                self._insert_run_event(connection, terminal)
                self._update_projection(
                    connection,
                    PreliminaryRunStateProjection(
                        schema_version=(
                            PRELIMINARY_RUN_STATE_PROJECTION_SCHEMA_VERSION
                        ),
                        preliminary_run_id=preliminary_run_id,
                        journey_id=journey_id,
                        projected_status=PreliminaryRunProjectedStatus.ABANDONED,
                        terminal_event_id=terminal.run_event_id,
                        projected_at=now,
                    ),
                )
                self._journeys._insert_journey_event(
                    connection, recovery_event
                )
                operation = PreliminaryRunOperationResult(
                    manifest=manifest,
                    started_event=events[0],
                    status=PreliminaryRunProjectedStatus.ABANDONED,
                    terminal_event=terminal,
                    terminal_code=terminal.payload.reason_code,
                )
                return PreliminaryRecoveryOperationResult(
                    action=PreliminaryRecoveryAction.ABANDON,
                    recovery_event=recovery_event,
                    operation=operation,
                )
        except (
            PreliminaryJourneyCorruptionError,
            PreliminaryRunRecoveryConflictError,
            PreliminaryRunRecoveryIdempotencyError,
            ValueError,
        ):
            raise
        except Exception as exc:
            raise PreliminaryRunRecoveryWriteError(
                "Interrupted-run abandonment did not commit"
            ) from exc

    def retry_and_persist(
        self,
        journey_id: str,
        predecessor_run_id: str,
        *,
        request_token: str,
        route_choice_event_id: str,
        route_choice_event_sequence: int,
    ) -> PreliminaryRecoveryOperationResult:
        """Create a new evaluator run linked to one failed or abandoned run."""

        if not request_token.strip():
            raise ValueError("Retry request token cannot be blank")
        if route_choice_event_sequence < 1:
            raise ValueError("Route-choice event sequence must be positive")
        self._require_current_supported_identity()
        try:
            with self.store._transaction() as connection:
                history = self._load_history(
                    connection, journey_id, require_active=False
                )
                replay_manifest = next(
                    (
                        manifest
                        for manifest in history.manifests.values()
                        if manifest.request_token == request_token
                    ),
                    None,
                )
                if replay_manifest is not None:
                    if (
                        replay_manifest.retry_of_run_id != predecessor_run_id
                        or replay_manifest.route_choice_event_id
                        != route_choice_event_id
                        or replay_manifest.route_choice_event_sequence
                        != route_choice_event_sequence
                    ):
                        raise PreliminaryRunRecoveryIdempotencyError(
                            "Retry token was already used for another operation"
                        )
                    if not self._journeys._manifest_is_compatible(
                        replay_manifest, history.journey
                    ):
                        raise PreliminaryRunRecoveryIdempotencyError(
                            "Retry token belongs to another compatibility identity"
                        )
                    recovery_event = self._recovery_event_by_token(
                        history, request_token
                    )
                    if (
                        recovery_event is None
                        or not isinstance(
                            recovery_event.payload,
                            PreliminaryRunRecoveryV2Payload,
                        )
                        or recovery_event.payload.action
                        is not PreliminaryRecoveryAction.RETRY
                        or recovery_event.payload.retry_run_id
                        != replay_manifest.preliminary_run_id
                    ):
                        raise PreliminaryJourneyCorruptionError(
                            "Retry manifest has no matching recovery audit event"
                        )
                    return PreliminaryRecoveryOperationResult(
                        action=PreliminaryRecoveryAction.RETRY,
                        recovery_event=recovery_event,
                        operation=self._operation(
                            history, replay_manifest, replayed=True
                        ),
                        replayed=True,
                    )
                if self._recovery_event_by_token(history, request_token) is not None:
                    raise PreliminaryRunRecoveryIdempotencyError(
                        "Retry token was already used for another recovery operation"
                    )

                self._journeys._validate_journey_source(
                    connection, history.journey, require_active=True
                )
                predecessor = history.manifests.get(predecessor_run_id)
                if predecessor is None:
                    raise PreliminaryRunRecoveryConflictError(
                        "Retry predecessor is missing or belongs to another journey"
                    )
                if not self._journeys._manifest_is_compatible(
                    predecessor, history.journey
                ):
                    raise PreliminaryRunRecoveryConflictError(
                        "Retry predecessor is not current-compatible"
                    )
                predecessor_events = history.run_events[predecessor_run_id]
                if predecessor_events[-1].event_type not in {
                    PreliminaryRunEventType.RUN_FAILED,
                    PreliminaryRunEventType.RUN_ABANDONED,
                }:
                    raise PreliminaryRunRecoveryConflictError(
                        "Only a failed or abandoned run can be retried"
                    )
                if any(
                    events[-1].event_type
                    is PreliminaryRunEventType.RUN_STARTED
                    for events in history.run_events.values()
                ):
                    raise PreliminaryRunConcurrencyError(
                        "A non-terminal Preliminary run already exists"
                    )
                route_event = self._latest_route_choice(history.journey_events)
                if (
                    route_event is None
                    or not isinstance(route_event.payload, JourneySelection)
                    or route_event.payload.journey
                    is not AssessmentJourney.EXPLORE_PROCESS
                ):
                    raise PreliminaryRunNotAllowedError(
                        "The latest route choice must select Explore this process"
                    )
                if (
                    route_event.event_id != route_choice_event_id
                    or route_event.event_sequence != route_choice_event_sequence
                ):
                    raise PreliminaryRunNotAllowedError(
                        "The retry request pins a stale route-choice event"
                    )

                now = self._now()
                run_id = self._id("preliminary-run")
                identity = self.supported_identity
                manifest = PreliminaryRunManifest(
                    schema_version=PRELIMINARY_RUN_MANIFEST_SCHEMA_VERSION,
                    store_id=self.store.store_id,
                    preliminary_run_id=run_id,
                    journey_id=journey_id,
                    request_token=request_token,
                    retry_of_run_id=predecessor_run_id,
                    route_choice_event_id=route_event.event_id,
                    route_choice_event_sequence=route_event.event_sequence,
                    source=history.journey.source,
                    evaluator=predecessor.evaluator,
                    rule_set=predecessor.rule_set,
                    output_schema_version=predecessor.output_schema_version,
                    created_at=now,
                )
                linked = PreliminaryJourneyEvent(
                    schema_version=PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
                    event_id=self._id("journey-event"),
                    journey_id=journey_id,
                    event_sequence=history.journey_events[-1].event_sequence + 1,
                    event_type=PreliminaryJourneyEventType.RUN_LINKED,
                    occurred_at=now,
                    payload=PreliminaryRunLinkedPayload(
                        schema_version="preliminary-run-link.v0.1",
                        preliminary_run_id=run_id,
                        route_choice_event_id=route_event.event_id,
                        route_choice_event_sequence=route_event.event_sequence,
                    ),
                )
                started = PreliminaryRunLifecycleEvent(
                    schema_version=PRELIMINARY_RUN_EVENT_SCHEMA_VERSION,
                    run_event_id=self._id("run-event"),
                    preliminary_run_id=run_id,
                    journey_id=journey_id,
                    event_sequence=1,
                    event_type=PreliminaryRunEventType.RUN_STARTED,
                    occurred_at=now,
                    payload=PreliminaryRunStartedPayload(
                        schema_version="preliminary-run-started.v0.1",
                        preliminary_run_id=run_id,
                    ),
                )
                recovery_event = PreliminaryJourneyEvent(
                    schema_version=PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
                    event_id=self._id("journey-event"),
                    journey_id=journey_id,
                    event_sequence=linked.event_sequence + 1,
                    event_type=PreliminaryJourneyEventType.RUN_RECOVERY_RECORDED,
                    occurred_at=now,
                    payload=PreliminaryRunRecoveryV2Payload(
                        schema_version="preliminary-run-recovery.v0.2",
                        action=PreliminaryRecoveryAction.RETRY,
                        recovery_request_token=request_token,
                        predecessor_run_id=predecessor_run_id,
                        retry_run_id=run_id,
                    ),
                )
                projection = PreliminaryRunStateProjection(
                    schema_version=(
                        PRELIMINARY_RUN_STATE_PROJECTION_SCHEMA_VERSION
                    ),
                    preliminary_run_id=run_id,
                    journey_id=journey_id,
                    projected_status=PreliminaryRunProjectedStatus.STARTED,
                    projected_at=now,
                )
                self._insert_manifest(connection, manifest)
                self._journeys._insert_journey_event(connection, linked)
                self._insert_run_event(connection, started)
                self._insert_projection(connection, projection)
                self._journeys._insert_journey_event(
                    connection, recovery_event
                )
                approved_review = self._load_approved_review(
                    connection, history.journey
                )
        except (
            PreliminaryJourneyCorruptionError,
            PreliminaryRunConcurrencyError,
            PreliminaryRunNotAllowedError,
            PreliminaryRunRecoveryConflictError,
            PreliminaryRunRecoveryIdempotencyError,
            ValueError,
        ):
            raise
        except Exception as exc:
            raise PreliminaryRunRecoveryWriteError(
                "Retry start did not commit"
            ) from exc

        operation = self._evaluate_started(manifest, started, approved_review)
        return PreliminaryRecoveryOperationResult(
            action=PreliminaryRecoveryAction.RETRY,
            recovery_event=recovery_event,
            operation=operation,
        )

    def _evaluate_started(
        self,
        manifest: PreliminaryRunManifest,
        started: PreliminaryRunLifecycleEvent,
        approved_review: ApprovedProcessReview,
    ) -> PreliminaryRunOperationResult:
        if manifest.evaluator.evaluator_id == "preliminary-evaluator.v0.1":
            evaluator = PreliminaryAssessmentEvaluator(
                clock=self.evaluation_clock,
                id_factory=lambda: manifest.preliminary_run_id,
            )
        elif manifest.evaluator.evaluator_id == "preliminary-evaluator.v0.2":
            evaluator = PreliminaryAssessmentEvaluatorV2()
        else:
            raise PreliminaryRunServiceError(
                "Run manifest has an unsupported evaluator identity"
            )
        evaluation = evaluator.evaluate(approved_review)
        if isinstance(
            evaluation, (PreliminaryEvaluationSuccess, PreliminaryEvaluationSuccessV2)
        ):
            return self._complete(manifest, started, evaluation)
        if isinstance(
            evaluation, (PreliminaryEvaluationFailure, PreliminaryEvaluationFailureV2)
        ):
            return self._fail(manifest, started, evaluation)
        raise PreliminaryRunServiceError("Evaluator returned an unsupported envelope")

    def _complete(
        self,
        manifest: PreliminaryRunManifest,
        started: PreliminaryRunLifecycleEvent,
        evaluation: PreliminaryEvaluationSuccess | PreliminaryEvaluationSuccessV2,
    ) -> PreliminaryRunOperationResult:
        try:
            with self.store._transaction() as connection:
                history = self._load_history(
                    connection, manifest.journey_id, require_active=False
                )
                self._require_open_run(history, manifest)
                now = self._now()
                result_id = self._id("preliminary-result")
                terminal = PreliminaryRunLifecycleEvent(
                    schema_version=PRELIMINARY_RUN_EVENT_SCHEMA_VERSION,
                    run_event_id=self._id("run-event"),
                    preliminary_run_id=manifest.preliminary_run_id,
                    journey_id=manifest.journey_id,
                    event_sequence=2,
                    event_type=PreliminaryRunEventType.RUN_COMPLETED,
                    occurred_at=now,
                    payload=PreliminaryRunCompletedPayload(
                        schema_version="preliminary-run-completed.v0.1",
                        preliminary_run_id=manifest.preliminary_run_id,
                        preliminary_result_id=result_id,
                    ),
                )
                result = PersistedPreliminaryResult(
                    schema_version=PRELIMINARY_RESULT_SCHEMA_VERSION,
                    preliminary_result_id=result_id,
                    preliminary_run_id=manifest.preliminary_run_id,
                    journey_id=manifest.journey_id,
                    completed_run_event_id=terminal.run_event_id,
                    source=manifest.source,
                    evaluator=manifest.evaluator,
                    rule_set=manifest.rule_set,
                    output_schema_version=manifest.output_schema_version,
                    created_at=now,
                    assessment=evaluation.assessment,
                )
                self._insert_result(connection, result)
                self._insert_run_event(connection, terminal)
                self._update_projection(
                    connection,
                    PreliminaryRunStateProjection(
                        schema_version=(
                            PRELIMINARY_RUN_STATE_PROJECTION_SCHEMA_VERSION
                        ),
                        preliminary_run_id=manifest.preliminary_run_id,
                        journey_id=manifest.journey_id,
                        projected_status=PreliminaryRunProjectedStatus.COMPLETED,
                        terminal_event_id=terminal.run_event_id,
                        projected_at=now,
                    ),
                )
                result_recorded = PreliminaryJourneyEvent(
                    schema_version=PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
                    event_id=self._id("journey-event"),
                    journey_id=manifest.journey_id,
                    event_sequence=history.journey_events[-1].event_sequence + 1,
                    event_type=PreliminaryJourneyEventType.RESULT_RECORDED,
                    occurred_at=now,
                    payload=PreliminaryResultRecordedPayload(
                        schema_version="preliminary-result-recorded.v0.1",
                        preliminary_run_id=manifest.preliminary_run_id,
                        preliminary_result_id=result_id,
                    ),
                )
                self._journeys._insert_journey_event(connection, result_recorded)

                predecessor = self._latest_compatible_result(history)
                supersession = None
                if predecessor is not None:
                    supersession = PreliminaryResultSupersession(
                        schema_version=(
                            PRELIMINARY_RESULT_SUPERSESSION_SCHEMA_VERSION
                        ),
                        supersession_id=self._id("result-supersession"),
                        journey_id=manifest.journey_id,
                        superseded_result_id=predecessor.preliminary_result_id,
                        superseding_result_id=result_id,
                        occurred_at=now,
                    )
                    self._insert_supersession(connection, supersession)
                    superseded_event = PreliminaryJourneyEvent(
                        schema_version=PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
                        event_id=self._id("journey-event"),
                        journey_id=manifest.journey_id,
                        event_sequence=result_recorded.event_sequence + 1,
                        event_type=PreliminaryJourneyEventType.RESULT_SUPERSEDED,
                        occurred_at=now,
                        payload=PreliminaryResultSupersessionPayload(
                            schema_version="preliminary-result-supersession.v0.1",
                            superseded_result_id=predecessor.preliminary_result_id,
                            superseding_result_id=result_id,
                        ),
                    )
                    self._journeys._insert_journey_event(connection, superseded_event)
                return PreliminaryRunOperationResult(
                    manifest=manifest,
                    started_event=started,
                    status=PreliminaryRunProjectedStatus.COMPLETED,
                    terminal_event=terminal,
                    result=result,
                    supersession=supersession,
                )
        except Exception as exc:
            if isinstance(exc, PreliminaryRunFinalizationError):
                raise
            raise PreliminaryRunFinalizationError(
                "Run completion could not be persisted atomically"
            ) from exc

    def _fail(
        self,
        manifest: PreliminaryRunManifest,
        started: PreliminaryRunLifecycleEvent,
        evaluation: PreliminaryEvaluationFailure | PreliminaryEvaluationFailureV2,
    ) -> PreliminaryRunOperationResult:
        error_code = evaluation.errors[0].code.value
        try:
            with self.store._transaction() as connection:
                history = self._load_history(
                    connection, manifest.journey_id, require_active=False
                )
                self._require_open_run(history, manifest)
                now = self._now()
                terminal = PreliminaryRunLifecycleEvent(
                    schema_version=PRELIMINARY_RUN_EVENT_SCHEMA_VERSION,
                    run_event_id=self._id("run-event"),
                    preliminary_run_id=manifest.preliminary_run_id,
                    journey_id=manifest.journey_id,
                    event_sequence=2,
                    event_type=PreliminaryRunEventType.RUN_FAILED,
                    occurred_at=now,
                    payload=PreliminaryRunFailedPayload(
                        schema_version="preliminary-run-failed.v0.1",
                        preliminary_run_id=manifest.preliminary_run_id,
                        error_code=error_code,
                    ),
                )
                self._insert_run_event(connection, terminal)
                self._update_projection(
                    connection,
                    PreliminaryRunStateProjection(
                        schema_version=(
                            PRELIMINARY_RUN_STATE_PROJECTION_SCHEMA_VERSION
                        ),
                        preliminary_run_id=manifest.preliminary_run_id,
                        journey_id=manifest.journey_id,
                        projected_status=PreliminaryRunProjectedStatus.FAILED,
                        terminal_event_id=terminal.run_event_id,
                        projected_at=now,
                    ),
                )
                return PreliminaryRunOperationResult(
                    manifest=manifest,
                    started_event=started,
                    status=PreliminaryRunProjectedStatus.FAILED,
                    terminal_event=terminal,
                    terminal_code=error_code,
                )
        except Exception as exc:
            raise PreliminaryRunFinalizationError(
                "Run failure could not be persisted atomically"
            ) from exc

    def _load_history(
        self,
        connection: sqlite3.Connection,
        journey_id: str,
        *,
        require_active: bool,
    ) -> _History:
        journey = self._journeys._load_journey(connection, journey_id)
        self._journeys._validate_journey_source(
            connection, journey, require_active=require_active
        )
        events = tuple(
            self._journeys._load_journey_events(
                connection, journey_id, journey=journey
            )
        )
        self._journeys._load_route_requests(connection, journey_id, events)
        manifests = self._journeys._load_run_manifests(connection, journey)
        run_events = self._journeys._load_run_events(
            connection, journey_id, manifests
        )
        self._journeys._validate_run_state_projections(
            connection, journey_id, manifests, run_events
        )
        run_order = self._journeys._run_order(events, manifests)
        self._journeys._validate_recovery_events(
            events,
            manifests,
            run_events,
            run_order,
        )
        results = tuple(
            self._journeys._load_results(
                connection, journey, manifests, run_events
            )
        )
        supersessions = tuple(
            self._journeys._load_supersessions(
                connection, journey, events, list(results), run_order
            )
        )
        self._journeys._load_formal_lifecycle(connection, journey, events)
        return _History(
            journey=journey,
            journey_events=events,
            manifests=manifests,
            run_events=run_events,
            run_order=run_order,
            results=results,
            supersessions=supersessions,
        )

    @staticmethod
    def _recovery_event_by_token(
        history: _History, request_token: str
    ) -> PreliminaryJourneyEvent | None:
        matches = [
            event
            for event in history.journey_events
            if event.event_type
            is PreliminaryJourneyEventType.RUN_RECOVERY_RECORDED
            and isinstance(event.payload, PreliminaryRunRecoveryV2Payload)
            and event.payload.recovery_request_token == request_token
        ]
        if len(matches) > 1:
            raise PreliminaryJourneyCorruptionError(
                "Recovery request token has duplicate audit events"
            )
        return matches[0] if matches else None

    def _require_open_run(
        self, history: _History, expected: PreliminaryRunManifest
    ) -> None:
        stored = history.manifests.get(expected.preliminary_run_id)
        events = history.run_events.get(expected.preliminary_run_id, [])
        if (
            stored != expected
            or not self._journeys._manifest_is_compatible(expected, history.journey)
            or len(events) != 1
            or events[0].event_type is not PreliminaryRunEventType.RUN_STARTED
        ):
            raise PreliminaryJourneyCorruptionError(
                "Run is missing, terminal, incompatible, or inconsistent"
            )

    def _operation(
        self,
        history: _History,
        manifest: PreliminaryRunManifest,
        *,
        replayed: bool,
    ) -> PreliminaryRunOperationResult:
        events = history.run_events[manifest.preliminary_run_id]
        started = events[0]
        if len(events) == 1:
            return PreliminaryRunOperationResult(
                manifest=manifest,
                started_event=started,
                status=PreliminaryRunProjectedStatus.STARTED,
                replayed=replayed,
            )
        terminal = events[1]
        status = PreliminaryRunProjectedStatus(
            terminal.event_type.value.removeprefix("RUN_")
        )
        result = next(
            (
                item
                for item in history.results
                if item.preliminary_run_id == manifest.preliminary_run_id
            ),
            None,
        )
        supersession = (
            next(
                (
                    item
                    for item in history.supersessions
                    if result is not None
                    and item.superseding_result_id
                    == result.preliminary_result_id
                ),
                None,
            )
        )
        terminal_code = None
        if status is PreliminaryRunProjectedStatus.FAILED:
            terminal_code = terminal.payload.error_code
        elif status is PreliminaryRunProjectedStatus.ABANDONED:
            terminal_code = terminal.payload.reason_code
        return PreliminaryRunOperationResult(
            manifest=manifest,
            started_event=started,
            status=status,
            terminal_event=terminal,
            result=result,
            supersession=supersession,
            terminal_code=terminal_code,
            replayed=replayed,
        )

    def _latest_compatible_result(
        self, history: _History
    ) -> PersistedPreliminaryResult | None:
        compatible = [
            result
            for result in history.results
            if self._journeys._result_is_compatible(result, history.journey)
        ]
        return (
            max(
                compatible,
                key=lambda item: history.run_order[item.preliminary_run_id],
            )
            if compatible
            else None
        )

    @staticmethod
    def _latest_route_choice(
        events: tuple[PreliminaryJourneyEvent, ...],
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

    def _load_approved_review(
        self, connection: sqlite3.Connection, journey: PreliminaryJourney
    ) -> ApprovedProcessReview:
        row = connection.execute(
            """SELECT artifact_schema_version, payload_json, payload_sha256
               FROM assessment_artifacts
               WHERE artifact_id = ? AND assessment_id = ?""",
            (
                journey.source.approved_review_artifact_id,
                journey.source.source_assessment_id,
            ),
        ).fetchone()
        if row is None:
            raise PreliminaryJourneyCorruptionError(
                "Pinned approved review is missing"
            )
        try:
            approved = deserialize_artifact_versioned(
                artifact_type=ArtifactType.APPROVED_REVIEW,
                artifact_schema_version=row["artifact_schema_version"],
                payload_json=row["payload_json"],
                expected_sha256=row["payload_sha256"],
            )
        except (ArtifactCorruptionError, ValueError, TypeError) as exc:
            raise PreliminaryJourneyCorruptionError(
                "Pinned approved review could not be hydrated"
            ) from exc
        if not isinstance(approved, ApprovedProcessReview):
            raise PreliminaryJourneyCorruptionError(
                "Pinned artifact is not an ApprovedProcessReview"
            )
        return approved

    def _require_current_supported_identity(self) -> None:
        require_supported_preliminary_compatibility_identity(
            self.supported_identity
        )

    @staticmethod
    def _rule_reference(
        identity: PreliminaryCompatibilityIdentity,
    ) -> PersistedPreliminaryRuleSetReference:
        if identity == current_preliminary_compatibility_identity():
            return PersistedPreliminaryRuleSetReference.model_validate(
                PRELIMINARY_EVALUATOR_RULES_V0_1.reference().model_dump()
            )
        return PersistedPreliminaryRuleSetReference(
            rule_set_id=identity.rule_set_id,
            rule_set_version=identity.rule_set_version,
            rule_set_status="PROVISIONAL EXPLORATION — NOT VALIDATED",
            rule_set_fingerprint=identity.rule_set_fingerprint,
        )

    @staticmethod
    def _versioned_table(base: str, output_schema_version: str) -> str:
        if output_schema_version == "preliminary-assessment.v0.1":
            return base
        if output_schema_version == "preliminary-assessment.v0.2":
            return f"{base}_v0_2"
        raise PreliminaryJourneyCorruptionError(
            "Unsupported Preliminary output identity"
        )

    @staticmethod
    def _table_for_run(
        connection: sqlite3.Connection, base: str, preliminary_run_id: str
    ) -> str:
        row = connection.execute(
            """SELECT 1 FROM preliminary_run_manifests_v0_2
               WHERE preliminary_run_id = ?""",
            (preliminary_run_id,),
        ).fetchone()
        return f"{base}_v0_2" if row is not None else base

    @staticmethod
    def _table_for_result(
        connection: sqlite3.Connection, base: str, preliminary_result_id: str
    ) -> str:
        row = connection.execute(
            """SELECT 1 FROM preliminary_results_v0_2
               WHERE preliminary_result_id = ?""",
            (preliminary_result_id,),
        ).fetchone()
        return f"{base}_v0_2" if row is not None else base

    def _insert_manifest(
        self, connection: sqlite3.Connection, manifest: PreliminaryRunManifest
    ) -> None:
        payload_json, payload_sha = self._serialize(
            PreliminaryPersistenceRecordType.RUN_MANIFEST,
            manifest.schema_version,
            manifest,
        )
        source = manifest.source
        table = self._versioned_table(
            "preliminary_run_manifests", manifest.output_schema_version
        )
        connection.execute(
            f"""INSERT INTO {table} VALUES (
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
        self, connection: sqlite3.Connection, event: PreliminaryRunLifecycleEvent
    ) -> None:
        payload_json, payload_sha = self._serialize(
            PreliminaryPersistenceRecordType.RUN_EVENT,
            event.schema_version,
            event,
        )
        table = self._table_for_run(
            connection, "preliminary_run_events", event.preliminary_run_id
        )
        connection.execute(
            f"""INSERT INTO {table} VALUES (
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

    def _insert_projection(
        self, connection: sqlite3.Connection, projection: PreliminaryRunStateProjection
    ) -> None:
        payload_json, payload_sha = self._serialize(
            PreliminaryPersistenceRecordType.RUN_STATE_PROJECTION,
            projection.schema_version,
            projection,
        )
        table = self._table_for_run(
            connection, "preliminary_run_state_index", projection.preliminary_run_id
        )
        connection.execute(
            f"""INSERT INTO {table} VALUES (
                   ?, ?, ?, ?, ?, ?, ?, ?
               )""",
            (
                projection.preliminary_run_id,
                projection.journey_id,
                projection.schema_version,
                projection.projected_status.value,
                projection.terminal_event_id,
                projection.projected_at.isoformat(),
                payload_json,
                payload_sha,
            ),
        )

    def _update_projection(
        self, connection: sqlite3.Connection, projection: PreliminaryRunStateProjection
    ) -> None:
        payload_json, payload_sha = self._serialize(
            PreliminaryPersistenceRecordType.RUN_STATE_PROJECTION,
            projection.schema_version,
            projection,
        )
        table = self._table_for_run(
            connection, "preliminary_run_state_index", projection.preliminary_run_id
        )
        cursor = connection.execute(
            f"""UPDATE {table} SET
                   schema_version = ?, projected_status = ?, terminal_event_id = ?,
                   projected_at = ?, payload_json = ?, payload_sha256 = ?
               WHERE preliminary_run_id = ? AND journey_id = ?""",
            (
                projection.schema_version,
                projection.projected_status.value,
                projection.terminal_event_id,
                projection.projected_at.isoformat(),
                payload_json,
                payload_sha,
                projection.preliminary_run_id,
                projection.journey_id,
            ),
        )
        if cursor.rowcount != 1:
            raise PreliminaryJourneyCorruptionError(
                "Run-state projection is missing"
            )

    def _insert_result(
        self, connection: sqlite3.Connection, result: PersistedPreliminaryResult
    ) -> None:
        payload_json, payload_sha = self._serialize(
            PreliminaryPersistenceRecordType.PRELIMINARY_RESULT,
            result.schema_version,
            result,
        )
        source = result.source
        table = self._versioned_table(
            "preliminary_results", result.output_schema_version
        )
        connection.execute(
            f"""INSERT INTO {table} VALUES (
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

    def _insert_supersession(
        self,
        connection: sqlite3.Connection,
        supersession: PreliminaryResultSupersession,
    ) -> None:
        payload_json, payload_sha = self._serialize(
            PreliminaryPersistenceRecordType.RESULT_SUPERSESSION,
            supersession.schema_version,
            supersession,
        )
        table = self._table_for_result(
            connection,
            "preliminary_result_supersessions",
            supersession.superseding_result_id,
        )
        connection.execute(
            f"""INSERT INTO {table} VALUES (
                   ?, ?, ?, ?, ?, ?, ?, ?
               )""",
            (
                supersession.supersession_id,
                supersession.journey_id,
                supersession.schema_version,
                supersession.superseded_result_id,
                supersession.superseding_result_id,
                supersession.occurred_at.isoformat(),
                payload_json,
                payload_sha,
            ),
        )

    @staticmethod
    def _serialize(
        record_type: PreliminaryPersistenceRecordType,
        schema_version: str,
        payload: BaseModel,
    ) -> tuple[str, str]:
        try:
            return serialize_preliminary_persistence_record(
                record_type, schema_version, payload
            )
        except ArtifactCorruptionError as exc:
            raise PreliminaryJourneyCorruptionError(
                "Preliminary run record could not be serialized"
            ) from exc

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

"""Explicit Slice 2 service for Preliminary journey choice and derived state."""

from __future__ import annotations

import hashlib
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from ai_adoption_engine.application.fingerprints import fingerprint_business_process
from ai_adoption_engine.models.candidate_process import ResolvedEvidenceReference
from ai_adoption_engine.models.evidence import EvidenceReference
from ai_adoption_engine.models.preliminary_assessment import (
    AssessmentJourney,
    JourneySelection,
)
from ai_adoption_engine.models.preliminary_journey import (
    ApprovedReviewArtifactPin,
    FormalLifecycleStatus,
    JourneyCreationResult,
    PreliminaryCompatibilityIdentity,
    PreliminaryCurrentRoute,
    PreliminaryJourneyHistory,
    PreliminaryJourneyState,
    PreliminaryJourneyStatus,
    PreliminaryRunHistoryItem,
    RouteSelectionResult,
)
from ai_adoption_engine.models.preliminary_persistence import (
    PRELIMINARY_EVALUATOR_ID,
    PRELIMINARY_EVALUATOR_VERSION,
    PRELIMINARY_EVALUATOR_V0_2_ID,
    PRELIMINARY_EVALUATOR_V0_2_VERSION,
    PRELIMINARY_RULE_SET_V0_2_FINGERPRINT,
    PRELIMINARY_RULE_SET_V0_2_ID,
    PRELIMINARY_RULE_SET_V0_2_VERSION,
    PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
    PRELIMINARY_JOURNEY_SCHEMA_VERSION,
    PRELIMINARY_RESULT_SCHEMA_VERSION,
    PRELIMINARY_ROUTE_REQUEST_SCHEMA_VERSION,
    JourneyCreatedPayload,
    PersistedPreliminaryResult,
    PreliminaryFormalLifecycle,
    PreliminaryFormalStartRequest,
    PreliminaryJourney,
    PreliminaryJourneyEvent,
    PreliminaryJourneyEventType,
    PreliminaryPersistenceRecordType,
    PreliminaryRecoveryAction,
    PreliminaryRouteRequest,
    PreliminaryResultSupersession,
    PreliminaryRunEventType,
    PreliminaryRunLifecycleEvent,
    PreliminaryRunManifest,
    PreliminaryRunProjectedStatus,
    PreliminaryRunRecoveryPayload,
    PreliminaryRunRecoveryV2Payload,
    PreliminaryRunStateProjection,
    PreliminarySourceSnapshot,
)
from ai_adoption_engine.models.review import (
    ApprovedProcessReview,
    ConflictStatus,
    ProcessReviewSession,
    ReviewAction,
    ReviewDisposition,
    ReviewStatus,
    ReviewedAssertion,
)
from ai_adoption_engine.persistence.base import (
    ArtifactCorruptionError,
    PersistenceError,
)
from ai_adoption_engine.persistence.preliminary import SQLitePreliminaryJourneyStore
from ai_adoption_engine.persistence.preliminary_serialization import (
    deserialize_preliminary_persistence_record,
    serialize_preliminary_persistence_record,
)
from ai_adoption_engine.persistence.serialization import (
    deserialize_artifact_versioned,
)
from ai_adoption_engine.preliminary.rules import PRELIMINARY_EVALUATOR_RULES_V0_1
from ai_adoption_engine.review.approval import approve_review, _project_business_process


Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]


class PreliminaryJourneyServiceError(PersistenceError):
    """A journey operation failed without changing stored history."""


class ApprovedReviewValidationError(PreliminaryJourneyServiceError):
    """The requested active approval does not satisfy its exact source pin."""


class PreliminaryJourneyNotFoundError(PreliminaryJourneyServiceError):
    """The requested Preliminary journey does not exist."""


class PreliminaryJourneyConcurrencyError(PreliminaryJourneyServiceError):
    """The caller's expected latest journey-event sequence is stale."""


class PreliminaryJourneyIdempotencyError(PreliminaryJourneyServiceError):
    """A route request token was replayed with different request content."""


class PreliminaryJourneyCorruptionError(PreliminaryJourneyServiceError):
    """Stored Preliminary records are unsupported or internally inconsistent."""


class UnsupportedPreliminaryCompatibilityIdentityError(
    PreliminaryJourneyServiceError
):
    """The requested evaluator/rule/output identity is not a supported whole."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def current_preliminary_compatibility_identity() -> PreliminaryCompatibilityIdentity:
    rules = PRELIMINARY_EVALUATOR_RULES_V0_1.reference()
    return PreliminaryCompatibilityIdentity(
        evaluator_id=PRELIMINARY_EVALUATOR_ID,
        evaluator_version=PRELIMINARY_EVALUATOR_VERSION,
        rule_set_id=rules.rule_set_id,
        rule_set_version=rules.rule_set_version,
        rule_set_fingerprint=rules.rule_set_fingerprint,
        output_schema_version="preliminary-assessment.v0.1",
    )


def preliminary_v0_2_compatibility_identity() -> PreliminaryCompatibilityIdentity:
    """Return the one exact opt-in v0.2 compatibility identity."""

    return PreliminaryCompatibilityIdentity(
        evaluator_id=PRELIMINARY_EVALUATOR_V0_2_ID,
        evaluator_version=PRELIMINARY_EVALUATOR_V0_2_VERSION,
        rule_set_id=PRELIMINARY_RULE_SET_V0_2_ID,
        rule_set_version=PRELIMINARY_RULE_SET_V0_2_VERSION,
        rule_set_fingerprint=PRELIMINARY_RULE_SET_V0_2_FINGERPRINT,
        output_schema_version="preliminary-assessment.v0.2",
    )


def require_supported_preliminary_compatibility_identity(
    identity: PreliminaryCompatibilityIdentity,
) -> PreliminaryCompatibilityIdentity:
    if identity not in {
        current_preliminary_compatibility_identity(),
        preliminary_v0_2_compatibility_identity(),
    }:
        raise UnsupportedPreliminaryCompatibilityIdentityError(
            "Unsupported or mixed Preliminary compatibility identity"
        )
    return identity


class PreliminaryJourneyService:
    """Persist route choices and derive journey state without running evaluation."""

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
        self.supported_identity = require_supported_preliminary_compatibility_identity(
            supported_identity or current_preliminary_compatibility_identity()
        )

    def create_or_reuse_journey(
        self,
        approved_review: ApprovedReviewArtifactPin,
    ) -> JourneyCreationResult:
        """Create or reuse the one journey for one exact active approval artifact."""

        with self.store._transaction() as connection:
            source = self._validated_source_snapshot(
                connection,
                approved_review,
                require_active=True,
            )
            existing = connection.execute(
                """SELECT * FROM preliminary_journeys
                   WHERE approved_review_artifact_id = ?""",
                (approved_review.artifact_id,),
            ).fetchone()
            if existing is not None:
                journey = self._journey(existing)
                if journey.source != source:
                    raise PreliminaryJourneyCorruptionError(
                        "Existing journey does not match its approved-review source"
                    )
                events = self._load_journey_events(
                    connection,
                    journey.journey_id,
                    journey=journey,
                )
                self._load_route_requests(connection, journey.journey_id, events)
                return JourneyCreationResult(journey=journey, created=False)

            now = self._now()
            journey = PreliminaryJourney(
                schema_version=PRELIMINARY_JOURNEY_SCHEMA_VERSION,
                store_id=self.store.store_id,
                store_version=self.store.store_version,
                journey_id=self._id("journey"),
                source=source,
                created_at=now,
            )
            created_event = PreliminaryJourneyEvent(
                schema_version=PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
                event_id=self._id("journey-event"),
                journey_id=journey.journey_id,
                event_sequence=1,
                event_type=PreliminaryJourneyEventType.JOURNEY_CREATED,
                occurred_at=now,
                payload=JourneyCreatedPayload(
                    schema_version="journey-created.v0.1",
                    journey_id=journey.journey_id,
                    source_assessment_id=source.source_assessment_id,
                    approved_review_artifact_id=source.approved_review_artifact_id,
                ),
            )
            self._insert_journey(connection, journey)
            self._insert_journey_event(connection, created_event)
            return JourneyCreationResult(journey=journey, created=True)

    def find_journey_for_approved_review(
        self,
        approved_review: ApprovedReviewArtifactPin,
    ) -> PreliminaryJourneyState | None:
        """Find, fully validate, and derive the journey for one exact approval."""

        with self.store._read() as connection:
            source = self._validated_source_snapshot(
                connection,
                approved_review,
                require_active=False,
            )
            row = connection.execute(
                """SELECT * FROM preliminary_journeys
                   WHERE approved_review_artifact_id = ?""",
                (approved_review.artifact_id,),
            ).fetchone()
            if row is None:
                return None
            journey = self._journey(row)
            if journey.source != source:
                raise PreliminaryJourneyCorruptionError(
                    "Journey does not match its exact approved-review source"
                )
            journey_id = journey.journey_id
        return self.get_state(journey_id)

    def journey_exists_for_approved_review_artifact(
        self,
        *,
        assessment_id: str,
        approved_review_artifact_id: str,
    ) -> bool:
        """Return the journey guard without interpreting its stored history."""

        with self.store._read() as connection:
            row = connection.execute(
                """SELECT 1 FROM preliminary_journeys
                   WHERE source_assessment_id = ?
                     AND approved_review_artifact_id = ?""",
                (assessment_id, approved_review_artifact_id),
            ).fetchone()
            return row is not None

    def get_history(self, journey_id: str) -> PreliminaryJourneyHistory:
        """Return validated immutable run/result history for presentation."""

        with self.store._read() as connection:
            journey = self._load_journey(connection, journey_id)
            self._validate_journey_source(connection, journey, require_active=False)
            events = tuple(
                self._load_journey_events(
                    connection,
                    journey_id,
                    journey=journey,
                )
            )
            self._load_route_requests(connection, journey_id, list(events))
            manifests = self._load_run_manifests(connection, journey)
            run_events = self._load_run_events(connection, journey_id, manifests)
            self._validate_run_state_projections(
                connection,
                journey_id,
                manifests,
                run_events,
            )
            run_order = self._run_order(events, manifests)
            self._validate_recovery_events(
                events,
                manifests,
                run_events,
                run_order,
            )
            results = self._load_results(
                connection,
                journey,
                manifests,
                run_events,
            )
            supersessions = tuple(
                self._load_supersessions(
                    connection,
                    journey,
                    events,
                    results,
                    run_order,
                )
            )
            self._load_formal_lifecycle(connection, journey, list(events))
            result_by_run = {
                result.preliminary_run_id: result for result in results
            }
            superseded_by = {
                link.superseded_result_id: link.superseding_result_id
                for link in supersessions
            }
            items: list[PreliminaryRunHistoryItem] = []
            for run_id in sorted(
                manifests,
                key=lambda item: run_order[item],
                reverse=True,
            ):
                lifecycle = tuple(run_events[run_id])
                terminal = lifecycle[-1]
                status = PreliminaryRunProjectedStatus(
                    terminal.event_type.value.removeprefix("RUN_")
                )
                result = result_by_run.get(run_id)
                terminal_code = None
                if terminal.event_type in {
                    PreliminaryRunEventType.RUN_FAILED,
                    PreliminaryRunEventType.RUN_ABANDONED,
                }:
                    terminal_code = getattr(
                        terminal.payload,
                        "error_code",
                        getattr(terminal.payload, "reason_code", None),
                    )
                items.append(
                    PreliminaryRunHistoryItem(
                        manifest=manifests[run_id],
                        lifecycle_events=lifecycle,
                        status=status,
                        result=result,
                        superseded_by_result_id=(
                            superseded_by.get(result.preliminary_result_id)
                            if result is not None
                            else None
                        ),
                        terminal_code=terminal_code,
                    )
                )
        return PreliminaryJourneyHistory(
            state=self.get_state(journey_id),
            journey_events=events,
            runs=tuple(items),
            supersessions=supersessions,
        )

    def select_route(
        self,
        journey_id: str,
        route: AssessmentJourney,
        *,
        request_token: str,
        expected_latest_sequence: int,
    ) -> RouteSelectionResult:
        """Append one route choice, or record an idempotent no-op selection."""

        if not request_token.strip():
            raise ValueError("Route request token cannot be blank")
        if expected_latest_sequence < 1:
            raise ValueError("Expected latest sequence must be positive")
        with self.store._transaction() as connection:
            journey = self._load_journey(connection, journey_id)
            self._validate_journey_source(connection, journey, require_active=True)
            events = self._load_journey_events(
                connection,
                journey_id,
                journey=journey,
            )
            requests = self._load_route_requests(connection, journey_id, events)
            request = requests.get(request_token)
            if request is not None:
                if (
                    request.requested_route is not route
                    or request.expected_latest_sequence != expected_latest_sequence
                ):
                    raise PreliminaryJourneyIdempotencyError(
                        "Route request token was already used for another request"
                    )
                effective = self._load_journey_event(
                    connection, request.effective_route_event_id
                )
                if effective.journey_id != journey_id:
                    raise PreliminaryJourneyCorruptionError(
                        "Route request event belongs to another journey"
                    )
                return RouteSelectionResult(
                    request=request,
                    effective_route_event=effective,
                    replayed=True,
                )
            latest_sequence = events[-1].event_sequence
            if latest_sequence != expected_latest_sequence:
                raise PreliminaryJourneyConcurrencyError(
                    "Expected latest journey-event sequence is stale"
                )
            route_events = [
                event
                for event in events
                if event.event_type
                in {
                    PreliminaryJourneyEventType.ROUTE_SELECTED,
                    PreliminaryJourneyEventType.ROUTE_CHANGED,
                }
            ]
            current = route_events[-1] if route_events else None
            current_route = (
                current.payload.journey
                if current is not None and isinstance(current.payload, JourneySelection)
                else None
            )
            now = self._now()
            appended = current_route is not route
            if appended:
                sequence = latest_sequence + 1
                effective = PreliminaryJourneyEvent(
                    schema_version=PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
                    event_id=self._id("journey-event"),
                    journey_id=journey_id,
                    event_sequence=sequence,
                    event_type=(
                        PreliminaryJourneyEventType.ROUTE_SELECTED
                        if current is None
                        else PreliminaryJourneyEventType.ROUTE_CHANGED
                    ),
                    occurred_at=now,
                    payload=JourneySelection(
                        schema_version="journey-selection.v0.1",
                        journey=route,
                    ),
                )
                self._insert_journey_event(connection, effective)
                latest_after = sequence
                resulting_event_id: str | None = effective.event_id
            else:
                assert current is not None
                effective = current
                latest_after = latest_sequence
                resulting_event_id = None

            request = PreliminaryRouteRequest(
                schema_version=PRELIMINARY_ROUTE_REQUEST_SCHEMA_VERSION,
                route_request_id=self._id("route-request"),
                journey_id=journey_id,
                request_token=request_token,
                requested_route=route,
                expected_latest_sequence=expected_latest_sequence,
                event_appended=appended,
                resulting_event_id=resulting_event_id,
                effective_route_event_id=effective.event_id,
                effective_route_event_sequence=effective.event_sequence,
                latest_sequence_after_request=latest_after,
                created_at=now,
            )
            self._insert_route_request(connection, request)
            return RouteSelectionResult(
                request=request,
                effective_route_event=effective,
                replayed=False,
            )

    def get_state(self, journey_id: str) -> PreliminaryJourneyState:
        """Derive the three independent journey-state dimensions."""

        with self.store._read() as connection:
            journey = self._load_journey(connection, journey_id)
            self._validate_journey_source(connection, journey, require_active=False)
            events = self._load_journey_events(
                connection,
                journey_id,
                journey=journey,
            )
            self._load_route_requests(connection, journey_id, events)
            route_events = [
                event
                for event in events
                if event.event_type
                in {
                    PreliminaryJourneyEventType.ROUTE_SELECTED,
                    PreliminaryJourneyEventType.ROUTE_CHANGED,
                }
            ]
            current_route_event = route_events[-1] if route_events else None
            current_route = (
                PreliminaryCurrentRoute(current_route_event.payload.journey.value)
                if current_route_event is not None
                and isinstance(current_route_event.payload, JourneySelection)
                else PreliminaryCurrentRoute.UNSELECTED
            )

            manifests = self._load_run_manifests(connection, journey)
            run_events = self._load_run_events(connection, journey_id, manifests)
            self._validate_run_state_projections(
                connection,
                journey_id,
                manifests,
                run_events,
            )
            run_order = self._run_order(events, manifests)
            self._validate_recovery_events(
                events,
                manifests,
                run_events,
                run_order,
            )
            results = self._load_results(connection, journey, manifests, run_events)
            self._load_supersessions(
                connection,
                journey,
                events,
                results,
                run_order,
            )
            compatible_results = [
                result
                for result in results
                if self._result_is_compatible(result, journey)
            ]
            latest_compatible = (
                max(
                    compatible_results,
                    key=lambda result: (
                        run_order[result.preliminary_run_id],
                        result.created_at,
                        result.preliminary_result_id,
                    ),
                )
                if compatible_results
                else None
            )
            preliminary_status = self._preliminary_status(
                manifests,
                run_events,
                run_order,
                results,
                latest_compatible,
                journey,
            )
            formal = self._load_formal_lifecycle(connection, journey, events)
            formal_status = (
                FormalLifecycleStatus.AWAITING_FORMAL_INPUTS
                if formal is not None
                else FormalLifecycleStatus.NOT_STARTED
            )
            active_result = (
                latest_compatible
                if current_route is PreliminaryCurrentRoute.EXPLORE_PROCESS
                else None
            )
            return PreliminaryJourneyState(
                journey=journey,
                latest_event_sequence=events[-1].event_sequence,
                current_route=current_route,
                current_route_event=current_route_event,
                preliminary_status=preliminary_status,
                formal_lifecycle_status=formal_status,
                latest_compatible_result=latest_compatible,
                active_preliminary_result=active_result,
                formal_lifecycle=formal,
            )

    def _validated_source_snapshot(
        self,
        connection: sqlite3.Connection,
        pin: ApprovedReviewArtifactPin,
        *,
        require_active: bool,
    ) -> PreliminarySourceSnapshot:
        row = connection.execute(
            """SELECT a.* FROM assessment_artifacts a
               JOIN assessments owner ON owner.assessment_id = a.assessment_id
               WHERE a.artifact_id = ? AND a.assessment_id = ?""",
            (pin.artifact_id, pin.assessment_id),
        ).fetchone()
        if row is None:
            raise ApprovedReviewValidationError(
                "Approved review does not belong to the requested assessment"
            )
        if require_active:
            active = connection.execute(
                """SELECT 1 FROM active_artifacts
                   WHERE assessment_id = ? AND artifact_type = 'APPROVED_REVIEW'
                     AND artifact_id = ?""",
                (pin.assessment_id, pin.artifact_id),
            ).fetchone()
            if active is None:
                raise ApprovedReviewValidationError(
                    "Journey creation and route changes require the active approval"
                )
        if (
            row["artifact_type"] != "APPROVED_REVIEW"
            or row["artifact_revision"] != pin.artifact_revision
            or row["artifact_schema_version"] != pin.artifact_schema_version
            or row["artifact_schema_version"] != "phase4-v0.1"
            or row["payload_sha256"] != pin.payload_sha256
        ):
            raise ApprovedReviewValidationError(
                "Approved-review revision, schema, or payload hash does not match"
            )
        if hashlib.sha256(row["payload_json"].encode()).hexdigest() != row[
            "payload_sha256"
        ]:
            raise ApprovedReviewValidationError(
                "Approved-review payload failed integrity validation"
            )
        parent = connection.execute(
            """SELECT artifact_type, artifact_schema_version, assessment_id,
                      payload_json, payload_sha256
               FROM assessment_artifacts WHERE artifact_id = ?""",
            (row["parent_artifact_id"],),
        ).fetchone()
        if (
            parent is None
            or parent["assessment_id"] != pin.assessment_id
            or parent["artifact_type"] != "REVIEW_SESSION"
            or parent["artifact_schema_version"] != "phase4-v0.1"
        ):
            raise ApprovedReviewValidationError(
                "Approved review has an invalid review-session parent"
            )
        try:
            approved = deserialize_artifact_versioned(
                artifact_type=_approved_artifact_type(),
                artifact_schema_version=row["artifact_schema_version"],
                payload_json=row["payload_json"],
                expected_sha256=row["payload_sha256"],
            )
            if not isinstance(approved, ApprovedProcessReview):
                raise TypeError("Stored approval did not hydrate correctly")
            review = deserialize_artifact_versioned(
                artifact_type=_review_artifact_type(),
                artifact_schema_version=parent["artifact_schema_version"],
                payload_json=parent["payload_json"],
                expected_sha256=parent["payload_sha256"],
            )
            if not isinstance(review, ProcessReviewSession):
                raise TypeError("Approved review parent did not hydrate correctly")
            exact_snapshot = (
                review.model_dump(mode="json")
                == approved.review.model_dump(mode="json")
            )
            replayed = None if exact_snapshot else approve_review(
                review,
                approved.approval,
            ).approved
            if not exact_snapshot and (
                replayed is None
                or replayed.model_dump(mode="json")
                != approved.model_dump(mode="json")
            ):
                raise TypeError(
                    "Approved review is not the exact deterministic approval of its review artifact"
                )
            return self._source_snapshot(pin, approved)
        except (ArtifactCorruptionError, ValidationError, TypeError, ValueError) as exc:
            raise ApprovedReviewValidationError(
                "Approved-review content or lineage is invalid"
            ) from exc

    def _source_snapshot(
        self,
        pin: ApprovedReviewArtifactPin,
        approved: ApprovedProcessReview,
    ) -> PreliminarySourceSnapshot:
        review = approved.review
        if review.status is not ReviewStatus.APPROVED:
            raise ValueError("Review is not approved")
        if any(
            conflict.blocking
            and conflict.status is ConflictStatus.OPEN
            for conflict in review.conflicts
        ):
            raise ValueError("Approved review has a blocking conflict")
        approval_events = [
            event for event in review.events if event.action is ReviewAction.APPROVE
        ]
        if len(approval_events) != 1:
            raise ValueError("Review must contain exactly one approval event")
        approval_event = approval_events[0]
        if approval_event.occurred_at != approved.approval.approved_at:
            raise ValueError("Approval event and declaration timestamps differ")
        retained_steps = [step for step in review.steps if step.retained]
        if (
            not review.order_accepted
            or not retained_steps
            or not _approval_confirmed(review.process_name)
            or any(not _approval_confirmed(step.activity) for step in retained_steps)
        ):
            raise ValueError("Approved review no longer satisfies approval invariants")
        projected = _project_business_process(review)
        if projected.model_dump(mode="json") != approved.business_process.model_dump(
            mode="json"
        ):
            raise ValueError("Validated process does not match the approved review")
        source_document_id = review.original_candidate.source_document_id
        if any(
            document_id != source_document_id
            for document_id in _document_evidence_ids(approved)
        ):
            raise ValueError("Approved review contains evidence from another document")
        return PreliminarySourceSnapshot(
            source_assessment_id=pin.assessment_id,
            approved_review_artifact_id=pin.artifact_id,
            approved_review_schema_version="phase4-v0.1",
            approved_review_payload_sha256=pin.payload_sha256,
            source_document_id=source_document_id,
            extraction_run_id=review.original_candidate.extraction_run_id,
            review_id=review.review_id,
            approval_event_id=approval_event.event_id,
            approved_at=approved.approval.approved_at,
            validated_process_id=approved.business_process.process_id,
            validated_process_fingerprint=fingerprint_business_process(
                approved.business_process
            ),
        )

    def _validate_journey_source(
        self,
        connection: sqlite3.Connection,
        journey: PreliminaryJourney,
        *,
        require_active: bool,
    ) -> None:
        row = connection.execute(
            """SELECT artifact_revision, artifact_schema_version, payload_sha256
               FROM assessment_artifacts
               WHERE artifact_id = ? AND assessment_id = ?""",
            (
                journey.source.approved_review_artifact_id,
                journey.source.source_assessment_id,
            ),
        ).fetchone()
        if row is None:
            raise PreliminaryJourneyCorruptionError(
                "Journey source approval is missing or has a different owner"
            )
        pin = ApprovedReviewArtifactPin(
            assessment_id=journey.source.source_assessment_id,
            artifact_id=journey.source.approved_review_artifact_id,
            artifact_revision=row["artifact_revision"],
            artifact_schema_version=row["artifact_schema_version"],
            payload_sha256=journey.source.approved_review_payload_sha256,
        )
        try:
            source = self._validated_source_snapshot(
                connection, pin, require_active=require_active
            )
        except ApprovedReviewValidationError as exc:
            raise PreliminaryJourneyCorruptionError(
                "Journey source approval no longer validates"
            ) from exc
        if source != journey.source:
            raise PreliminaryJourneyCorruptionError(
                "Journey source snapshot differs from its approved review"
            )

    def _load_journey(
        self, connection: sqlite3.Connection, journey_id: str
    ) -> PreliminaryJourney:
        row = connection.execute(
            "SELECT * FROM preliminary_journeys WHERE journey_id = ?",
            (journey_id,),
        ).fetchone()
        if row is None:
            raise PreliminaryJourneyNotFoundError("Preliminary journey does not exist")
        return self._journey(row)

    def _journey(self, row: sqlite3.Row) -> PreliminaryJourney:
        record = self._deserialize(
            PreliminaryPersistenceRecordType.JOURNEY,
            row["schema_version"],
            row["payload_json"],
            row["payload_sha256"],
        )
        assert isinstance(record, PreliminaryJourney)
        if (
            record.journey_id != row["journey_id"]
            or record.schema_version != row["schema_version"]
            or record.store_id != row["store_id"]
            or record.store_version != row["store_version"]
            or record.source.source_assessment_id != row["source_assessment_id"]
            or record.source.approved_review_artifact_id
            != row["approved_review_artifact_id"]
            or record.source.approved_review_payload_sha256
            != row["approved_review_payload_sha256"]
            or record.source.validated_process_fingerprint
            != row["validated_process_fingerprint"]
            or record.created_at.isoformat() != row["created_at"]
        ):
            raise PreliminaryJourneyCorruptionError(
                "Journey columns differ from the canonical payload"
            )
        return record

    def _load_journey_events(
        self,
        connection: sqlite3.Connection,
        journey_id: str,
        *,
        journey: PreliminaryJourney | None = None,
    ) -> list[PreliminaryJourneyEvent]:
        rows = connection.execute(
            """SELECT * FROM preliminary_journey_events
               WHERE journey_id = ? ORDER BY event_sequence""",
            (journey_id,),
        ).fetchall()
        if not rows:
            raise PreliminaryJourneyCorruptionError("Journey has no creation event")
        events = [self._journey_event(row) for row in rows]
        if [event.event_sequence for event in events] != list(
            range(1, len(events) + 1)
        ):
            raise PreliminaryJourneyCorruptionError(
                "Journey event sequence is not gap-free"
            )
        if events[0].event_type is not PreliminaryJourneyEventType.JOURNEY_CREATED:
            raise PreliminaryJourneyCorruptionError(
                "Journey history does not begin with JOURNEY_CREATED"
            )
        if journey is not None:
            created = events[0].payload
            if (
                not isinstance(created, JourneyCreatedPayload)
                or created.journey_id != journey.journey_id
                or created.source_assessment_id
                != journey.source.source_assessment_id
                or created.approved_review_artifact_id
                != journey.source.approved_review_artifact_id
            ):
                raise PreliminaryJourneyCorruptionError(
                    "JOURNEY_CREATED does not match the journey source"
                )
        previous_route: AssessmentJourney | None = None
        for event in events:
            if event.event_type not in {
                PreliminaryJourneyEventType.ROUTE_SELECTED,
                PreliminaryJourneyEventType.ROUTE_CHANGED,
            }:
                continue
            if not isinstance(event.payload, JourneySelection):
                raise PreliminaryJourneyCorruptionError(
                    "Route event has an invalid payload"
                )
            if previous_route is None:
                if event.event_type is not PreliminaryJourneyEventType.ROUTE_SELECTED:
                    raise PreliminaryJourneyCorruptionError(
                        "The first route choice must be ROUTE_SELECTED"
                    )
            elif (
                event.event_type is not PreliminaryJourneyEventType.ROUTE_CHANGED
                or event.payload.journey is previous_route
            ):
                raise PreliminaryJourneyCorruptionError(
                    "Later route choices must record a real ROUTE_CHANGED transition"
                )
            previous_route = event.payload.journey
        return events

    def _load_journey_event(
        self, connection: sqlite3.Connection, event_id: str
    ) -> PreliminaryJourneyEvent:
        row = connection.execute(
            "SELECT * FROM preliminary_journey_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            raise PreliminaryJourneyCorruptionError("Route request event is missing")
        return self._journey_event(row)

    def _journey_event(self, row: sqlite3.Row) -> PreliminaryJourneyEvent:
        record = self._deserialize(
            PreliminaryPersistenceRecordType.JOURNEY_EVENT,
            row["schema_version"],
            row["payload_json"],
            row["payload_sha256"],
        )
        assert isinstance(record, PreliminaryJourneyEvent)
        if (
            record.event_id != row["event_id"]
            or record.journey_id != row["journey_id"]
            or record.event_sequence != row["event_sequence"]
            or record.event_type.value != row["event_type"]
            or record.payload.schema_version != row["payload_schema_version"]
            or record.occurred_at.isoformat() != row["occurred_at"]
        ):
            raise PreliminaryJourneyCorruptionError(
                "Journey-event columns differ from the canonical payload"
            )
        return record

    def _route_request(self, row: sqlite3.Row) -> PreliminaryRouteRequest:
        record = self._deserialize(
            PreliminaryPersistenceRecordType.ROUTE_REQUEST,
            row["schema_version"],
            row["payload_json"],
            row["payload_sha256"],
        )
        assert isinstance(record, PreliminaryRouteRequest)
        if (
            record.route_request_id != row["route_request_id"]
            or record.journey_id != row["journey_id"]
            or record.schema_version != row["schema_version"]
            or record.request_token != row["request_token"]
            or record.requested_route.value != row["requested_route"]
            or record.expected_latest_sequence != row["expected_latest_sequence"]
            or int(record.event_appended) != row["event_appended"]
            or record.resulting_event_id != row["resulting_event_id"]
            or record.effective_route_event_id != row["effective_route_event_id"]
            or record.effective_route_event_sequence
            != row["effective_route_event_sequence"]
            or record.latest_sequence_after_request
            != row["latest_sequence_after_request"]
            or record.created_at.isoformat() != row["created_at"]
        ):
            raise PreliminaryJourneyCorruptionError(
                "Route-request columns differ from the canonical payload"
            )
        return record

    def _load_route_requests(
        self,
        connection: sqlite3.Connection,
        journey_id: str,
        events: list[PreliminaryJourneyEvent],
    ) -> dict[str, PreliminaryRouteRequest]:
        rows = connection.execute(
            """SELECT * FROM preliminary_route_requests
               WHERE journey_id = ? ORDER BY created_at, route_request_id""",
            (journey_id,),
        ).fetchall()
        events_by_id = {event.event_id: event for event in events}
        requests: dict[str, PreliminaryRouteRequest] = {}
        for row in rows:
            request = self._route_request(row)
            effective = events_by_id.get(request.effective_route_event_id)
            if (
                request.journey_id != journey_id
                or request.request_token in requests
                or request.latest_sequence_after_request
                > events[-1].event_sequence
                or effective is None
                or effective.event_sequence
                != request.effective_route_event_sequence
                or effective.event_type
                not in {
                    PreliminaryJourneyEventType.ROUTE_SELECTED,
                    PreliminaryJourneyEventType.ROUTE_CHANGED,
                }
                or not isinstance(effective.payload, JourneySelection)
                or effective.payload.journey is not request.requested_route
                or effective.event_sequence
                > request.latest_sequence_after_request
                or any(
                    event.event_type
                    in {
                        PreliminaryJourneyEventType.ROUTE_SELECTED,
                        PreliminaryJourneyEventType.ROUTE_CHANGED,
                    }
                    and effective.event_sequence
                    < event.event_sequence
                    <= request.latest_sequence_after_request
                    for event in events
                )
            ):
                raise PreliminaryJourneyCorruptionError(
                    "Route-request audit record does not match journey history"
                )
            requests[request.request_token] = request
        return requests

    def _load_run_manifests(
        self,
        connection: sqlite3.Connection,
        journey: PreliminaryJourney,
    ) -> dict[str, PreliminaryRunManifest]:
        rows = [
            *connection.execute(
                """SELECT * FROM preliminary_run_manifests
                   WHERE journey_id = ?""",
                (journey.journey_id,),
            ).fetchall(),
            *connection.execute(
                """SELECT * FROM preliminary_run_manifests_v0_2
                   WHERE journey_id = ?""",
                (journey.journey_id,),
            ).fetchall(),
        ]
        manifests: dict[str, PreliminaryRunManifest] = {}
        for row in rows:
            record = self._deserialize(
                PreliminaryPersistenceRecordType.RUN_MANIFEST,
                row["schema_version"],
                row["payload_json"],
                row["payload_sha256"],
            )
            assert isinstance(record, PreliminaryRunManifest)
            if (
                record.preliminary_run_id != row["preliminary_run_id"]
                or record.journey_id != row["journey_id"]
                or record.store_id != row["store_id"]
                or record.request_token != row["request_token"]
                or record.retry_of_run_id != row["retry_of_run_id"]
                or record.route_choice_event_id != row["route_choice_event_id"]
                or record.route_choice_event_sequence
                != row["route_choice_event_sequence"]
                or record.source != journey.source
                or record.source.source_assessment_id
                != row["source_assessment_id"]
                or record.source.approved_review_artifact_id
                != row["approved_review_artifact_id"]
                or record.source.approved_review_payload_sha256
                != row["approved_review_payload_sha256"]
                or record.source.source_document_id != row["source_document_id"]
                or record.source.validated_process_id
                != row["validated_process_id"]
                or record.source.validated_process_fingerprint
                != row["validated_process_fingerprint"]
                or record.evaluator.evaluator_id != row["evaluator_id"]
                or record.evaluator.evaluator_version != row["evaluator_version"]
                or record.rule_set.rule_set_id != row["rule_set_id"]
                or record.rule_set.rule_set_version != row["rule_set_version"]
                or record.rule_set.rule_set_fingerprint
                != row["rule_set_fingerprint"]
                or record.output_schema_version != row["output_schema_version"]
                or record.created_at.isoformat() != row["created_at"]
            ):
                raise PreliminaryJourneyCorruptionError(
                    "Run-manifest columns or source pins are inconsistent"
                )
            manifests[record.preliminary_run_id] = record
        return manifests

    def _load_run_events(
        self,
        connection: sqlite3.Connection,
        journey_id: str,
        manifests: dict[str, PreliminaryRunManifest],
    ) -> dict[str, list[PreliminaryRunLifecycleEvent]]:
        rows = [
            *connection.execute(
                """SELECT * FROM preliminary_run_events
                   WHERE journey_id = ?""",
                (journey_id,),
            ).fetchall(),
            *connection.execute(
                """SELECT * FROM preliminary_run_events_v0_2
                   WHERE journey_id = ?""",
                (journey_id,),
            ).fetchall(),
        ]
        rows.sort(key=lambda row: (row["preliminary_run_id"], row["event_sequence"]))
        grouped: dict[str, list[PreliminaryRunLifecycleEvent]] = defaultdict(list)
        for row in rows:
            record = self._deserialize(
                PreliminaryPersistenceRecordType.RUN_EVENT,
                row["schema_version"],
                row["payload_json"],
                row["payload_sha256"],
            )
            assert isinstance(record, PreliminaryRunLifecycleEvent)
            if (
                record.run_event_id != row["run_event_id"]
                or record.preliminary_run_id != row["preliminary_run_id"]
                or record.journey_id != row["journey_id"]
                or record.event_sequence != row["event_sequence"]
                or record.event_type.value != row["event_type"]
                or record.payload.schema_version != row["payload_schema_version"]
                or getattr(record.payload, "preliminary_result_id", None)
                != row["preliminary_result_id"]
                or record.occurred_at.isoformat() != row["occurred_at"]
                or record.preliminary_run_id not in manifests
            ):
                raise PreliminaryJourneyCorruptionError(
                    "Run-event columns or ownership are inconsistent"
                )
            grouped[record.preliminary_run_id].append(record)
        for run_id, manifest in manifests.items():
            events = grouped.get(run_id, [])
            if not events or events[0].event_type is not PreliminaryRunEventType.RUN_STARTED:
                raise PreliminaryJourneyCorruptionError(
                    "Every stored run manifest requires one RUN_STARTED event"
                )
            if [event.event_sequence for event in events] != list(
                range(1, len(events) + 1)
            ) or len(events) > 2:
                raise PreliminaryJourneyCorruptionError(
                    "Run lifecycle events are not a valid append-only sequence"
                )
            if manifest.journey_id != journey_id:
                raise PreliminaryJourneyCorruptionError("Run belongs to another journey")
            if manifest.retry_of_run_id is not None:
                predecessor = manifests.get(manifest.retry_of_run_id)
                predecessor_events = grouped.get(manifest.retry_of_run_id, [])
                if (
                    predecessor is None
                    or predecessor.request_token == manifest.request_token
                    or predecessor.evaluator != manifest.evaluator
                    or predecessor.rule_set != manifest.rule_set
                    or predecessor.output_schema_version
                    != manifest.output_schema_version
                    or not predecessor_events
                    or predecessor_events[-1].event_type
                    not in {
                        PreliminaryRunEventType.RUN_FAILED,
                        PreliminaryRunEventType.RUN_ABANDONED,
                    }
                ):
                    raise PreliminaryJourneyCorruptionError(
                        "Retry lineage is not a failed or abandoned same-journey run"
                    )
        return dict(grouped)

    def _validate_run_state_projections(
        self,
        connection: sqlite3.Connection,
        journey_id: str,
        manifests: dict[str, PreliminaryRunManifest],
        run_events: dict[str, list[PreliminaryRunLifecycleEvent]],
    ) -> None:
        rows = [
            *connection.execute(
                "SELECT * FROM preliminary_run_state_index WHERE journey_id = ?",
                (journey_id,),
            ).fetchall(),
            *connection.execute(
                "SELECT * FROM preliminary_run_state_index_v0_2 WHERE journey_id = ?",
                (journey_id,),
            ).fetchall(),
        ]
        projected_run_ids: set[str] = set()
        for row in rows:
            record = self._deserialize(
                PreliminaryPersistenceRecordType.RUN_STATE_PROJECTION,
                row["schema_version"],
                row["payload_json"],
                row["payload_sha256"],
            )
            assert isinstance(record, PreliminaryRunStateProjection)
            events = run_events.get(record.preliminary_run_id, [])
            if record.preliminary_run_id not in manifests or not events:
                raise PreliminaryJourneyCorruptionError(
                    "Run-state projection belongs to no valid run"
                )
            projected_run_ids.add(record.preliminary_run_id)
            terminal = events[-1]
            expected_status = PreliminaryRunProjectedStatus(
                terminal.event_type.value.removeprefix("RUN_")
            )
            expected_terminal_id = (
                None
                if expected_status is PreliminaryRunProjectedStatus.STARTED
                else terminal.run_event_id
            )
            if (
                record.preliminary_run_id != row["preliminary_run_id"]
                or record.journey_id != row["journey_id"]
                or record.journey_id != journey_id
                or record.projected_status.value != row["projected_status"]
                or record.terminal_event_id != row["terminal_event_id"]
                or record.projected_at.isoformat() != row["projected_at"]
                or record.projected_status is not expected_status
                or record.terminal_event_id != expected_terminal_id
            ):
                raise PreliminaryJourneyCorruptionError(
                    "Run-state projection differs from append-only run history"
                )
        if projected_run_ids != set(manifests):
            raise PreliminaryJourneyCorruptionError(
                "Every run requires exactly one constrained state projection"
            )

    def _load_results(
        self,
        connection: sqlite3.Connection,
        journey: PreliminaryJourney,
        manifests: dict[str, PreliminaryRunManifest],
        run_events: dict[str, list[PreliminaryRunLifecycleEvent]],
    ) -> list[PersistedPreliminaryResult]:
        rows = [
            *connection.execute(
                "SELECT * FROM preliminary_results WHERE journey_id = ?",
                (journey.journey_id,),
            ).fetchall(),
            *connection.execute(
                "SELECT * FROM preliminary_results_v0_2 WHERE journey_id = ?",
                (journey.journey_id,),
            ).fetchall(),
        ]
        results: list[PersistedPreliminaryResult] = []
        for row in rows:
            record = self._deserialize(
                PreliminaryPersistenceRecordType.PRELIMINARY_RESULT,
                row["schema_version"],
                row["payload_json"],
                row["payload_sha256"],
            )
            assert isinstance(record, PersistedPreliminaryResult)
            manifest = manifests.get(record.preliminary_run_id)
            events = run_events.get(record.preliminary_run_id, [])
            terminal = events[-1] if events else None
            if (
                record.preliminary_result_id != row["preliminary_result_id"]
                or record.preliminary_run_id != row["preliminary_run_id"]
                or record.journey_id != row["journey_id"]
                or record.completed_run_event_id
                != row["completed_run_event_id"]
                or record.source != journey.source
                or record.source.source_assessment_id
                != row["source_assessment_id"]
                or record.source.approved_review_artifact_id
                != row["approved_review_artifact_id"]
                or record.source.approved_review_payload_sha256
                != row["approved_review_payload_sha256"]
                or record.source.source_document_id != row["source_document_id"]
                or record.source.validated_process_id
                != row["validated_process_id"]
                or record.source.validated_process_fingerprint
                != row["validated_process_fingerprint"]
                or manifest is None
                or record.source != manifest.source
                or terminal is None
                or terminal.event_type is not PreliminaryRunEventType.RUN_COMPLETED
                or terminal.run_event_id != record.completed_run_event_id
                or getattr(terminal.payload, "preliminary_result_id", None)
                != record.preliminary_result_id
                or record.evaluator.evaluator_id != row["evaluator_id"]
                or record.evaluator.evaluator_version != row["evaluator_version"]
                or record.rule_set.rule_set_id != row["rule_set_id"]
                or record.rule_set.rule_set_version != row["rule_set_version"]
                or record.rule_set.rule_set_fingerprint
                != row["rule_set_fingerprint"]
                or record.output_schema_version != row["output_schema_version"]
                or record.evaluator != manifest.evaluator
                or record.rule_set != manifest.rule_set
                or record.output_schema_version != manifest.output_schema_version
                or record.created_at.isoformat() != row["created_at"]
            ):
                raise PreliminaryJourneyCorruptionError(
                    "Preliminary result pins or completed-run linkage are inconsistent"
                )
            results.append(record)
        completed_run_ids = {
            run_id
            for run_id, events in run_events.items()
            if events[-1].event_type is PreliminaryRunEventType.RUN_COMPLETED
        }
        if completed_run_ids != {result.preliminary_run_id for result in results}:
            raise PreliminaryJourneyCorruptionError(
                "Every completed run must have exactly one immutable result"
            )
        return results

    def _load_supersessions(
        self,
        connection: sqlite3.Connection,
        journey: PreliminaryJourney,
        events: Iterable[PreliminaryJourneyEvent],
        results: list[PersistedPreliminaryResult],
        run_order: dict[str, int],
    ) -> list[PreliminaryResultSupersession]:
        rows = [
            *connection.execute(
                """SELECT * FROM preliminary_result_supersessions
                   WHERE journey_id = ?""",
                (journey.journey_id,),
            ).fetchall(),
            *connection.execute(
                """SELECT * FROM preliminary_result_supersessions_v0_2
                   WHERE journey_id = ?""",
                (journey.journey_id,),
            ).fetchall(),
        ]
        rows.sort(key=lambda row: (row["occurred_at"], row["supersession_id"]))
        result_by_id = {result.preliminary_result_id: result for result in results}
        event_list = list(events)
        recorded_events = [
            event
            for event in event_list
            if event.event_type is PreliminaryJourneyEventType.RESULT_RECORDED
        ]
        for result in results:
            matching_recorded = [
                event
                for event in recorded_events
                if event.payload.preliminary_run_id == result.preliminary_run_id
                and event.payload.preliminary_result_id
                == result.preliminary_result_id
            ]
            if len(matching_recorded) != 1:
                raise PreliminaryJourneyCorruptionError(
                    "Every immutable result requires one RESULT_RECORDED event"
                )
        if len(recorded_events) != len(results):
            raise PreliminaryJourneyCorruptionError(
                "Result-recorded history has no matching immutable result"
            )
        links: list[PreliminaryResultSupersession] = []
        superseding_ids: set[str] = set()
        for row in rows:
            record = self._deserialize(
                PreliminaryPersistenceRecordType.RESULT_SUPERSESSION,
                row["schema_version"],
                row["payload_json"],
                row["payload_sha256"],
            )
            assert isinstance(record, PreliminaryResultSupersession)
            earlier = result_by_id.get(record.superseded_result_id)
            later = result_by_id.get(record.superseding_result_id)
            matching_events = [
                event
                for event in event_list
                if event.event_type
                is PreliminaryJourneyEventType.RESULT_SUPERSEDED
                and event.payload.superseded_result_id
                == record.superseded_result_id
                and event.payload.superseding_result_id
                == record.superseding_result_id
            ]
            if (
                record.supersession_id != row["supersession_id"]
                or record.journey_id != row["journey_id"]
                or record.journey_id != journey.journey_id
                or record.superseded_result_id != row["superseded_result_id"]
                or record.superseding_result_id != row["superseding_result_id"]
                or record.occurred_at.isoformat() != row["occurred_at"]
                or earlier is None
                or later is None
                or earlier.evaluator != later.evaluator
                or earlier.rule_set != later.rule_set
                or earlier.output_schema_version != later.output_schema_version
                or record.superseding_result_id in superseding_ids
                or run_order[earlier.preliminary_run_id]
                >= run_order[later.preliminary_run_id]
                or len(matching_events) != 1
            ):
                raise PreliminaryJourneyCorruptionError(
                    "Result supersession is not an ordered same-journey audit link"
                )
            superseding_ids.add(record.superseding_result_id)
            links.append(record)
        supersession_event_count = sum(
            event.event_type is PreliminaryJourneyEventType.RESULT_SUPERSEDED
            for event in event_list
        )
        if supersession_event_count != len(links):
            raise PreliminaryJourneyCorruptionError(
                "Result-superseded history has no matching immutable link"
            )
        return links

    def _run_order(
        self,
        events: Iterable[PreliminaryJourneyEvent],
        manifests: dict[str, PreliminaryRunManifest],
    ) -> dict[str, int]:
        order: dict[str, int] = {}
        event_list = list(events)
        events_by_id = {event.event_id: event for event in event_list}
        for event in event_list:
            if event.event_type is PreliminaryJourneyEventType.RUN_LINKED:
                run_id = event.payload.preliminary_run_id
                if run_id in order or run_id not in manifests:
                    raise PreliminaryJourneyCorruptionError(
                        "RUN_LINKED history is duplicated or references another journey"
                    )
                manifest = manifests[run_id]
                route_event = events_by_id.get(manifest.route_choice_event_id)
                if (
                    event.payload.route_choice_event_id
                    != manifest.route_choice_event_id
                    or event.payload.route_choice_event_sequence
                    != manifest.route_choice_event_sequence
                    or route_event is None
                    or route_event.event_sequence
                    != manifest.route_choice_event_sequence
                    or route_event.event_type
                    not in {
                        PreliminaryJourneyEventType.ROUTE_SELECTED,
                        PreliminaryJourneyEventType.ROUTE_CHANGED,
                    }
                    or not isinstance(route_event.payload, JourneySelection)
                    or route_event.payload.journey
                    is not AssessmentJourney.EXPLORE_PROCESS
                    or route_event.event_sequence >= event.event_sequence
                    or any(
                        candidate.event_type
                        in {
                            PreliminaryJourneyEventType.ROUTE_SELECTED,
                            PreliminaryJourneyEventType.ROUTE_CHANGED,
                        }
                        and route_event.event_sequence
                        < candidate.event_sequence
                        < event.event_sequence
                        for candidate in event_list
                    )
                ):
                    raise PreliminaryJourneyCorruptionError(
                        "RUN_LINKED does not pin the latest Explore route choice"
                    )
                order[run_id] = event.event_sequence
        if set(order) != set(manifests):
            raise PreliminaryJourneyCorruptionError(
                "Every run manifest must have one immutable RUN_LINKED event"
            )
        return order

    def _validate_recovery_events(
        self,
        events: Iterable[PreliminaryJourneyEvent],
        manifests: dict[str, PreliminaryRunManifest],
        run_events: dict[str, list[PreliminaryRunLifecycleEvent]],
        run_order: dict[str, int],
    ) -> None:
        """Validate closed recovery audit history against immutable run lineage."""

        recovery_events = [
            event
            for event in events
            if event.event_type
            is PreliminaryJourneyEventType.RUN_RECOVERY_RECORDED
        ]
        request_tokens: set[str] = set()
        abandoned_runs: set[str] = set()
        retry_runs: set[str] = set()
        for event in recovery_events:
            payload = event.payload
            if isinstance(payload, PreliminaryRunRecoveryPayload):
                predecessor = manifests.get(payload.abandoned_run_id)
                retry = manifests.get(payload.retry_run_id)
                predecessor_history = run_events.get(payload.abandoned_run_id, [])
                if (
                    predecessor is None
                    or retry is None
                    or retry.retry_of_run_id != payload.abandoned_run_id
                    or not predecessor_history
                    or predecessor_history[-1].event_type
                    is not PreliminaryRunEventType.RUN_ABANDONED
                    or payload.retry_run_id in retry_runs
                    or event.event_sequence <= run_order[payload.retry_run_id]
                ):
                    raise PreliminaryJourneyCorruptionError(
                        "Legacy recovery event has invalid same-journey lineage"
                    )
                retry_runs.add(payload.retry_run_id)
                continue
            if not isinstance(payload, PreliminaryRunRecoveryV2Payload):
                raise PreliminaryJourneyCorruptionError(
                    "Recovery event has an unsupported payload"
                )
            if payload.recovery_request_token in request_tokens:
                raise PreliminaryJourneyCorruptionError(
                    "Recovery request token is duplicated"
                )
            request_tokens.add(payload.recovery_request_token)
            predecessor = manifests.get(payload.predecessor_run_id)
            predecessor_history = run_events.get(payload.predecessor_run_id, [])
            if predecessor is None or not predecessor_history:
                raise PreliminaryJourneyCorruptionError(
                    "Recovery predecessor is missing from the journey"
                )
            if payload.action is PreliminaryRecoveryAction.ABANDON:
                terminal = predecessor_history[-1]
                if (
                    terminal.event_type
                    is not PreliminaryRunEventType.RUN_ABANDONED
                    or terminal.run_event_id != payload.terminal_run_event_id
                    or payload.predecessor_run_id in abandoned_runs
                    or event.event_sequence
                    <= run_order[payload.predecessor_run_id]
                ):
                    raise PreliminaryJourneyCorruptionError(
                        "Abandonment recovery does not match its terminal run"
                    )
                abandoned_runs.add(payload.predecessor_run_id)
                continue
            retry = manifests.get(payload.retry_run_id or "")
            if (
                retry is None
                or retry.retry_of_run_id != payload.predecessor_run_id
                or retry.request_token != payload.recovery_request_token
                or predecessor_history[-1].event_type
                not in {
                    PreliminaryRunEventType.RUN_FAILED,
                    PreliminaryRunEventType.RUN_ABANDONED,
                }
                or retry.preliminary_run_id in retry_runs
                or event.event_sequence <= run_order[retry.preliminary_run_id]
            ):
                raise PreliminaryJourneyCorruptionError(
                    "Retry recovery does not match its immutable run lineage"
                )
            retry_runs.add(retry.preliminary_run_id)
        expected_retry_runs = {
            manifest.preliminary_run_id
            for manifest in manifests.values()
            if manifest.retry_of_run_id is not None
        }
        if retry_runs != expected_retry_runs:
            raise PreliminaryJourneyCorruptionError(
                "Every retry run requires exactly one recovery audit event"
            )

    def _load_formal_lifecycle(
        self,
        connection: sqlite3.Connection,
        journey: PreliminaryJourney,
        events: Iterable[PreliminaryJourneyEvent],
    ) -> PreliminaryFormalLifecycle | None:
        rows = connection.execute(
            "SELECT * FROM preliminary_formal_lifecycles WHERE journey_id = ?",
            (journey.journey_id,),
        ).fetchall()
        formal_events = [
            event
            for event in events
            if event.event_type
            is PreliminaryJourneyEventType.FORMAL_LIFECYCLE_STARTED
        ]
        requests = self._load_formal_start_requests(
            connection, journey.journey_id
        )
        if not rows:
            if formal_events or requests:
                raise PreliminaryJourneyCorruptionError(
                    "Formal-start history has no immutable lifecycle record"
                )
            return None
        if len(rows) != 1 or len(formal_events) != 1 or len(requests) != 1:
            raise PreliminaryJourneyCorruptionError(
                "Formal lifecycle requires exactly one request, record, and event"
            )
        row = rows[0]
        record = self._deserialize(
            PreliminaryPersistenceRecordType.FORMAL_LIFECYCLE,
            row["schema_version"],
            row["payload_json"],
            row["payload_sha256"],
        )
        assert isinstance(record, PreliminaryFormalLifecycle)
        event = formal_events[0]
        request = next(iter(requests.values()))
        event_list = list(events)
        events_by_id = {item.event_id: item for item in event_list}
        route_event = events_by_id.get(record.route_choice_event_id)
        if (
            record.journey_id != journey.journey_id
            or record.source != journey.source
            or record.formal_lifecycle_id != row["formal_lifecycle_id"]
            or record.status != row["status"]
            or record.source.source_assessment_id != row["source_assessment_id"]
            or record.source.approved_review_artifact_id
            != row["approved_review_artifact_id"]
            or record.source.approved_review_payload_sha256
            != row["approved_review_payload_sha256"]
            or record.source.source_document_id != row["source_document_id"]
            or record.source.validated_process_id != row["validated_process_id"]
            or record.source.validated_process_fingerprint
            != row["validated_process_fingerprint"]
            or record.route_choice_event_id != row["route_choice_event_id"]
            or record.route_choice_event_sequence
            != row["route_choice_event_sequence"]
            or record.preliminary_result_id != row["preliminary_result_id"]
            or record.preliminary_result_use != row["preliminary_result_use"]
            or record.created_at.isoformat() != row["created_at"]
            or event.payload.formal_lifecycle_id != record.formal_lifecycle_id
            or event.payload.route_choice_event_id
            != record.route_choice_event_id
            or event.payload.route_choice_event_sequence
            != record.route_choice_event_sequence
            or request.formal_lifecycle_id != record.formal_lifecycle_id
            or request.route_choice_event_id != record.route_choice_event_id
            or request.route_choice_event_sequence
            != record.route_choice_event_sequence
            or request.preliminary_result_id != record.preliminary_result_id
            or request.preliminary_result_use != record.preliminary_result_use
            or request.created_at != record.created_at
            or route_event is None
            or route_event.event_sequence != record.route_choice_event_sequence
            or route_event.event_type
            not in {
                PreliminaryJourneyEventType.ROUTE_SELECTED,
                PreliminaryJourneyEventType.ROUTE_CHANGED,
            }
            or not isinstance(route_event.payload, JourneySelection)
            or route_event.payload.journey
            is not AssessmentJourney.ORGANISATIONAL_ASSESSMENT
            or route_event.event_sequence >= event.event_sequence
            or any(
                candidate.event_type
                in {
                    PreliminaryJourneyEventType.ROUTE_SELECTED,
                    PreliminaryJourneyEventType.ROUTE_CHANGED,
                }
                and route_event.event_sequence
                < candidate.event_sequence
                < event.event_sequence
                for candidate in event_list
            )
        ):
            raise PreliminaryJourneyCorruptionError(
                "Formal lifecycle columns or source pins are inconsistent"
            )
        return record

    def _load_formal_start_requests(
        self,
        connection: sqlite3.Connection,
        journey_id: str,
    ) -> dict[str, PreliminaryFormalStartRequest]:
        rows = connection.execute(
            """SELECT * FROM preliminary_formal_start_requests
               WHERE journey_id = ?
               ORDER BY created_at, formal_start_request_id""",
            (journey_id,),
        ).fetchall()
        requests: dict[str, PreliminaryFormalStartRequest] = {}
        for row in rows:
            record = self._deserialize(
                PreliminaryPersistenceRecordType.FORMAL_START_REQUEST,
                row["schema_version"],
                row["payload_json"],
                row["payload_sha256"],
            )
            assert isinstance(record, PreliminaryFormalStartRequest)
            if (
                record.formal_start_request_id
                != row["formal_start_request_id"]
                or record.journey_id != row["journey_id"]
                or record.journey_id != journey_id
                or record.request_token != row["request_token"]
                or record.formal_lifecycle_id != row["formal_lifecycle_id"]
                or record.route_choice_event_id != row["route_choice_event_id"]
                or record.route_choice_event_sequence
                != row["route_choice_event_sequence"]
                or record.preliminary_result_id != row["preliminary_result_id"]
                or record.preliminary_result_use
                != row["preliminary_result_use"]
                or record.created_at.isoformat() != row["created_at"]
                or record.request_token in requests
            ):
                raise PreliminaryJourneyCorruptionError(
                    "Formal-start request columns or ownership are inconsistent"
                )
            requests[record.request_token] = record
        return requests

    def _preliminary_status(
        self,
        manifests: dict[str, PreliminaryRunManifest],
        run_events: dict[str, list[PreliminaryRunLifecycleEvent]],
        run_order: dict[str, int],
        results: list[PersistedPreliminaryResult],
        latest_compatible: PersistedPreliminaryResult | None,
        journey: PreliminaryJourney,
    ) -> PreliminaryJourneyStatus:
        if any(
            events[-1].event_type is PreliminaryRunEventType.RUN_STARTED
            for events in run_events.values()
        ):
            return PreliminaryJourneyStatus.RUNNING
        if latest_compatible is not None:
            return PreliminaryJourneyStatus.AVAILABLE
        compatible_attempts = [
            manifest
            for manifest in manifests.values()
            if self._manifest_is_compatible(manifest, journey)
        ]
        if compatible_attempts:
            latest_attempt = max(
                compatible_attempts,
                key=lambda manifest: run_order[manifest.preliminary_run_id],
            )
            terminal = run_events[latest_attempt.preliminary_run_id][-1]
            if terminal.event_type in {
                PreliminaryRunEventType.RUN_FAILED,
                PreliminaryRunEventType.RUN_ABANDONED,
            }:
                return PreliminaryJourneyStatus.RETRY_AVAILABLE
            if terminal.event_type is PreliminaryRunEventType.RUN_COMPLETED:
                raise PreliminaryJourneyCorruptionError(
                    "A current-compatible completed run has no compatible result"
                )
        if results:
            return PreliminaryJourneyStatus.RERUN_REQUIRED
        return PreliminaryJourneyStatus.NOT_STARTED

    def _manifest_is_compatible(
        self, manifest: PreliminaryRunManifest, journey: PreliminaryJourney
    ) -> bool:
        identity = self.supported_identity
        return (
            manifest.source == journey.source
            and manifest.evaluator.evaluator_id == identity.evaluator_id
            and manifest.evaluator.evaluator_version == identity.evaluator_version
            and manifest.rule_set.rule_set_id == identity.rule_set_id
            and manifest.rule_set.rule_set_version == identity.rule_set_version
            and manifest.rule_set.rule_set_fingerprint
            == identity.rule_set_fingerprint
            and manifest.output_schema_version == identity.output_schema_version
        )

    def _result_is_compatible(
        self, result: PersistedPreliminaryResult, journey: PreliminaryJourney
    ) -> bool:
        identity = self.supported_identity
        return (
            result.source == journey.source
            and result.evaluator.evaluator_id == identity.evaluator_id
            and result.evaluator.evaluator_version == identity.evaluator_version
            and result.rule_set.rule_set_id == identity.rule_set_id
            and result.rule_set.rule_set_version == identity.rule_set_version
            and result.rule_set.rule_set_fingerprint == identity.rule_set_fingerprint
            and result.output_schema_version == identity.output_schema_version
        )

    def _insert_journey(
        self, connection: sqlite3.Connection, journey: PreliminaryJourney
    ) -> None:
        payload_json, payload_sha = self._serialize(
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
        self, connection: sqlite3.Connection, event: PreliminaryJourneyEvent
    ) -> None:
        payload_json, payload_sha = self._serialize(
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

    def _insert_route_request(
        self, connection: sqlite3.Connection, request: PreliminaryRouteRequest
    ) -> None:
        payload_json, payload_sha = self._serialize(
            PreliminaryPersistenceRecordType.ROUTE_REQUEST,
            request.schema_version,
            request,
        )
        connection.execute(
            """INSERT INTO preliminary_route_requests VALUES (
                   ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
               )""",
            (
                request.route_request_id,
                request.journey_id,
                request.schema_version,
                request.request_token,
                request.requested_route.value,
                request.expected_latest_sequence,
                int(request.event_appended),
                request.resulting_event_id,
                request.effective_route_event_id,
                request.effective_route_event_sequence,
                request.latest_sequence_after_request,
                request.created_at.isoformat(),
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
                "Preliminary record could not be serialized"
            ) from exc

    @staticmethod
    def _deserialize(
        record_type: PreliminaryPersistenceRecordType,
        schema_version: str,
        payload_json: str,
        payload_sha256: str,
    ) -> Any:
        try:
            return deserialize_preliminary_persistence_record(
                record_type,
                schema_version,
                payload_json,
                payload_sha256,
            )
        except (ArtifactCorruptionError, ValueError, TypeError) as exc:
            raise PreliminaryJourneyCorruptionError(
                f"Unsupported or corrupt {record_type.value} record"
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


def _approval_confirmed(assertion: ReviewedAssertion) -> bool:
    return (
        assertion.retained
        and assertion.value is not None
        and assertion.disposition
        in {ReviewDisposition.ACCEPTED, ReviewDisposition.CORRECTED}
    )


def _document_evidence_ids(value: Any) -> Iterable[str]:
    if isinstance(value, ResolvedEvidenceReference):
        yield value.document_id
        return
    if isinstance(value, EvidenceReference):
        yield value.source_id
        return
    if isinstance(value, BaseModel):
        for field_name in value.__class__.model_fields:
            yield from _document_evidence_ids(getattr(value, field_name))
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _document_evidence_ids(item)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _document_evidence_ids(item)


def _approved_artifact_type():
    from ai_adoption_engine.workspace.models import ArtifactType

    return ArtifactType.APPROVED_REVIEW


def _review_artifact_type():
    from ai_adoption_engine.workspace.models import ArtifactType

    return ArtifactType.REVIEW_SESSION

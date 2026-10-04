from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ai_adoption_engine.models.preliminary_assessment import (
    AssessmentJourney,
    JourneySelection,
)
from ai_adoption_engine.models.preliminary_persistence import (
    PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
    PRELIMINARY_JOURNEY_STORE_ID,
    PRELIMINARY_JOURNEY_STORE_VERSION,
    JourneyCreatedPayload,
    PreliminaryJourneyEvent,
    PreliminaryJourneyEventType,
    PreliminaryPersistenceRecordType,
    PreliminaryFormalStartRequest,
    PreliminaryRecoveryAction,
    PreliminaryRunAbandonedPayload,
    PreliminaryRunEventType,
    PreliminaryRunLifecycleEvent,
    PreliminaryRunRecoveryPayload,
    PreliminaryRunRecoveryV2Payload,
)
from ai_adoption_engine.persistence.base import ArtifactCorruptionError
from ai_adoption_engine.persistence.preliminary_serialization import (
    PRELIMINARY_PERSISTENCE_ADAPTERS,
    deserialize_preliminary_persistence_record,
    serialize_preliminary_persistence_record,
)


NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


def test_store_and_registered_contract_identities_are_exact() -> None:
    assert PRELIMINARY_JOURNEY_STORE_ID == "preliminary-journey-store.v0.1"
    assert PRELIMINARY_JOURNEY_STORE_VERSION == "0.1.0"
    assert set(PRELIMINARY_PERSISTENCE_ADAPTERS) == {
        (PreliminaryPersistenceRecordType.JOURNEY, "preliminary-journey.v0.1"),
        (
            PreliminaryPersistenceRecordType.JOURNEY_EVENT,
            "preliminary-journey-event.v0.1",
        ),
        (
            PreliminaryPersistenceRecordType.RUN_MANIFEST,
            "preliminary-run-manifest.v0.1",
        ),
        (
            PreliminaryPersistenceRecordType.RUN_EVENT,
            "preliminary-run-event.v0.1",
        ),
        (
            PreliminaryPersistenceRecordType.RUN_STATE_PROJECTION,
            "preliminary-run-state-projection.v0.1",
        ),
        (
            PreliminaryPersistenceRecordType.PRELIMINARY_RESULT,
            "preliminary-result.v0.1",
        ),
        (
            PreliminaryPersistenceRecordType.RESULT_SUPERSESSION,
            "preliminary-result-supersession.v0.1",
        ),
        (
            PreliminaryPersistenceRecordType.FORMAL_LIFECYCLE,
            "preliminary-formal-lifecycle.v0.1",
        ),
        (
            PreliminaryPersistenceRecordType.FORMAL_START_REQUEST,
            "preliminary-formal-start-request.v0.1",
        ),
        (
            PreliminaryPersistenceRecordType.ROUTE_REQUEST,
            "preliminary-route-request.v0.1",
        ),
    }


def test_route_events_alone_accept_journey_selection_payload() -> None:
    event = PreliminaryJourneyEvent(
        schema_version=PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
        event_id="event-route",
        journey_id="journey-1",
        event_sequence=2,
        event_type=PreliminaryJourneyEventType.ROUTE_SELECTED,
        occurred_at=NOW,
        payload=JourneySelection(
            schema_version="journey-selection.v0.1",
            journey=AssessmentJourney.EXPLORE_PROCESS,
        ),
    )
    assert event.payload.journey is AssessmentJourney.EXPLORE_PROCESS

    with pytest.raises(ValidationError, match="payload schema"):
        PreliminaryJourneyEvent(
            **event.model_dump(exclude={"event_type", "payload"}),
            event_type=PreliminaryJourneyEventType.JOURNEY_CREATED,
            payload=event.payload,
        )


def test_journey_created_is_first_and_payload_identity_is_closed() -> None:
    payload = JourneyCreatedPayload(
        schema_version="journey-created.v0.1",
        journey_id="journey-1",
        source_assessment_id="assessment-1",
        approved_review_artifact_id="artifact-approved",
    )
    with pytest.raises(ValidationError, match="first journey event"):
        PreliminaryJourneyEvent(
            schema_version=PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
            event_id="event-created",
            journey_id="journey-1",
            event_sequence=2,
            event_type=PreliminaryJourneyEventType.JOURNEY_CREATED,
            occurred_at=NOW,
            payload=payload,
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        JourneyCreatedPayload.model_validate(
            {**payload.model_dump(mode="json"), "unexpected": True}
        )


def test_retry_and_run_events_require_new_and_consistent_run_ids() -> None:
    with pytest.raises(ValidationError, match="new Preliminary run ID"):
        PreliminaryRunRecoveryPayload(
            schema_version="preliminary-run-recovery.v0.1",
            abandoned_run_id="run-1",
            retry_run_id="run-1",
        )


def test_formal_start_request_requires_exact_context_pair() -> None:
    request = PreliminaryFormalStartRequest(
        schema_version="preliminary-formal-start-request.v0.1",
        formal_start_request_id="formal-request-1",
        journey_id="journey-1",
        request_token="request-1",
        formal_lifecycle_id="formal-1",
        route_choice_event_id="route-1",
        route_choice_event_sequence=2,
        created_at=NOW,
    )
    assert request.preliminary_result_id is None
    invalid = request.model_dump()
    invalid["preliminary_result_id"] = "result-1"
    with pytest.raises(ValidationError, match="context-only"):
        PreliminaryFormalStartRequest.model_validate(invalid)

    abandonment = PreliminaryRunRecoveryV2Payload(
        schema_version="preliminary-run-recovery.v0.2",
        action=PreliminaryRecoveryAction.ABANDON,
        recovery_request_token="recover-1",
        predecessor_run_id="run-1",
        terminal_run_event_id="run-event-2",
    )
    assert abandonment.retry_run_id is None
    retry = PreliminaryRunRecoveryV2Payload(
        schema_version="preliminary-run-recovery.v0.2",
        action=PreliminaryRecoveryAction.RETRY,
        recovery_request_token="retry-1",
        predecessor_run_id="run-1",
        retry_run_id="run-2",
    )
    assert retry.terminal_run_event_id is None
    with pytest.raises(ValidationError, match="Abandonment recovery"):
        PreliminaryRunRecoveryV2Payload(
            **abandonment.model_dump(exclude={"terminal_run_event_id"})
        )
    with pytest.raises(ValidationError, match="Retry recovery"):
        PreliminaryRunRecoveryV2Payload(
            **retry.model_dump(exclude={"retry_run_id"})
        )

    with pytest.raises(ValidationError, match="payload must identify"):
        PreliminaryRunLifecycleEvent(
            schema_version="preliminary-run-event.v0.1",
            run_event_id="run-event-2",
            preliminary_run_id="run-1",
            journey_id="journey-1",
            event_sequence=2,
            event_type=PreliminaryRunEventType.RUN_ABANDONED,
            occurred_at=NOW,
            payload=PreliminaryRunAbandonedPayload(
                schema_version="preliminary-run-abandoned.v0.1",
                preliminary_run_id="run-other",
                reason_code="INTERRUPTED",
            ),
        )


def test_serialization_is_canonical_and_unknown_versions_fail_closed() -> None:
    event = PreliminaryJourneyEvent(
        schema_version=PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
        event_id="event-created",
        journey_id="journey-1",
        event_sequence=1,
        event_type=PreliminaryJourneyEventType.JOURNEY_CREATED,
        occurred_at=NOW,
        payload=JourneyCreatedPayload(
            schema_version="journey-created.v0.1",
            journey_id="journey-1",
            source_assessment_id="assessment-1",
            approved_review_artifact_id="artifact-approved",
        ),
    )
    first = serialize_preliminary_persistence_record(
        PreliminaryPersistenceRecordType.JOURNEY_EVENT,
        PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
        event,
    )
    second = serialize_preliminary_persistence_record(
        PreliminaryPersistenceRecordType.JOURNEY_EVENT,
        PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
        event,
    )
    assert first == second
    assert deserialize_preliminary_persistence_record(
        PreliminaryPersistenceRecordType.JOURNEY_EVENT,
        PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
        *first,
    ) == event

    with pytest.raises(ArtifactCorruptionError, match="Unsupported"):
        serialize_preliminary_persistence_record(
            PreliminaryPersistenceRecordType.JOURNEY_EVENT,
            "preliminary-journey-event.v9.9",
            event,
        )


def test_deserialization_rejects_hash_or_unknown_fields() -> None:
    event = PreliminaryJourneyEvent(
        schema_version=PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
        event_id="event-created",
        journey_id="journey-1",
        event_sequence=1,
        event_type=PreliminaryJourneyEventType.JOURNEY_CREATED,
        occurred_at=NOW,
        payload=JourneyCreatedPayload(
            schema_version="journey-created.v0.1",
            journey_id="journey-1",
            source_assessment_id="assessment-1",
            approved_review_artifact_id="artifact-approved",
        ),
    )
    payload_json, payload_sha = serialize_preliminary_persistence_record(
        PreliminaryPersistenceRecordType.JOURNEY_EVENT,
        PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
        event,
    )
    with pytest.raises(ArtifactCorruptionError, match="integrity"):
        deserialize_preliminary_persistence_record(
            PreliminaryPersistenceRecordType.JOURNEY_EVENT,
            PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
            payload_json,
            "0" * 64,
        )
    tampered = payload_json[:-1] + ',"unexpected":true}'
    import hashlib

    with pytest.raises(ArtifactCorruptionError, match="schema validation"):
        deserialize_preliminary_persistence_record(
            PreliminaryPersistenceRecordType.JOURNEY_EVENT,
            PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
            tampered,
            hashlib.sha256(tampered.encode()).hexdigest(),
        )

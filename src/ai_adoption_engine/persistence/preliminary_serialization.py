"""Exact serialization registry for ``preliminary-journey-store.v0.1``."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError

from ai_adoption_engine.models.preliminary_persistence import (
    PRELIMINARY_FORMAL_LIFECYCLE_SCHEMA_VERSION,
    PRELIMINARY_FORMAL_START_REQUEST_SCHEMA_VERSION,
    PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
    PRELIMINARY_JOURNEY_SCHEMA_VERSION,
    PRELIMINARY_RESULT_SCHEMA_VERSION,
    PRELIMINARY_RESULT_SUPERSESSION_SCHEMA_VERSION,
    PRELIMINARY_ROUTE_REQUEST_SCHEMA_VERSION,
    PRELIMINARY_RUN_EVENT_SCHEMA_VERSION,
    PRELIMINARY_RUN_MANIFEST_SCHEMA_VERSION,
    PRELIMINARY_RUN_STATE_PROJECTION_SCHEMA_VERSION,
    PersistedPreliminaryResult,
    PreliminaryFormalLifecycle,
    PreliminaryFormalStartRequest,
    PreliminaryJourney,
    PreliminaryJourneyEvent,
    PreliminaryPersistenceRecordType,
    PreliminaryResultSupersession,
    PreliminaryRouteRequest,
    PreliminaryRunLifecycleEvent,
    PreliminaryRunManifest,
    PreliminaryRunStateProjection,
)
from ai_adoption_engine.persistence.base import ArtifactCorruptionError


PreliminaryPersistenceContract = tuple[PreliminaryPersistenceRecordType, str]

PRELIMINARY_PERSISTENCE_ADAPTERS: dict[
    PreliminaryPersistenceContract, TypeAdapter[Any]
] = {
    (
        PreliminaryPersistenceRecordType.JOURNEY,
        PRELIMINARY_JOURNEY_SCHEMA_VERSION,
    ): TypeAdapter(PreliminaryJourney),
    (
        PreliminaryPersistenceRecordType.JOURNEY_EVENT,
        PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION,
    ): TypeAdapter(PreliminaryJourneyEvent),
    (
        PreliminaryPersistenceRecordType.RUN_MANIFEST,
        PRELIMINARY_RUN_MANIFEST_SCHEMA_VERSION,
    ): TypeAdapter(PreliminaryRunManifest),
    (
        PreliminaryPersistenceRecordType.RUN_EVENT,
        PRELIMINARY_RUN_EVENT_SCHEMA_VERSION,
    ): TypeAdapter(PreliminaryRunLifecycleEvent),
    (
        PreliminaryPersistenceRecordType.RUN_STATE_PROJECTION,
        PRELIMINARY_RUN_STATE_PROJECTION_SCHEMA_VERSION,
    ): TypeAdapter(PreliminaryRunStateProjection),
    (
        PreliminaryPersistenceRecordType.PRELIMINARY_RESULT,
        PRELIMINARY_RESULT_SCHEMA_VERSION,
    ): TypeAdapter(PersistedPreliminaryResult),
    (
        PreliminaryPersistenceRecordType.RESULT_SUPERSESSION,
        PRELIMINARY_RESULT_SUPERSESSION_SCHEMA_VERSION,
    ): TypeAdapter(PreliminaryResultSupersession),
    (
        PreliminaryPersistenceRecordType.FORMAL_LIFECYCLE,
        PRELIMINARY_FORMAL_LIFECYCLE_SCHEMA_VERSION,
    ): TypeAdapter(PreliminaryFormalLifecycle),
    (
        PreliminaryPersistenceRecordType.FORMAL_START_REQUEST,
        PRELIMINARY_FORMAL_START_REQUEST_SCHEMA_VERSION,
    ): TypeAdapter(PreliminaryFormalStartRequest),
    (
        PreliminaryPersistenceRecordType.ROUTE_REQUEST,
        PRELIMINARY_ROUTE_REQUEST_SCHEMA_VERSION,
    ): TypeAdapter(PreliminaryRouteRequest),
}


def validate_preliminary_persistence_contract(
    record_type: PreliminaryPersistenceRecordType,
    schema_version: str,
) -> None:
    if (record_type, schema_version) not in PRELIMINARY_PERSISTENCE_ADAPTERS:
        raise ArtifactCorruptionError(
            f"Unsupported Preliminary persistence contract: "
            f"{record_type.value}/{schema_version}"
        )


def serialize_preliminary_persistence_record(
    record_type: PreliminaryPersistenceRecordType,
    schema_version: str,
    payload: BaseModel,
) -> tuple[str, str]:
    """Validate and canonically serialize one exact registered record."""

    validate_preliminary_persistence_contract(record_type, schema_version)
    adapter = PRELIMINARY_PERSISTENCE_ADAPTERS[(record_type, schema_version)]
    try:
        candidate = (
            payload.model_dump(mode="json")
            if isinstance(payload, BaseModel)
            else payload
        )
        validated = adapter.validate_python(candidate)
    except ValidationError as exc:
        raise ArtifactCorruptionError(
            "Preliminary persistence record failed schema validation"
        ) from exc
    encoded = json.dumps(
        adapter.dump_python(validated, mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return encoded, hashlib.sha256(encoded.encode()).hexdigest()


def deserialize_preliminary_persistence_record(
    record_type: PreliminaryPersistenceRecordType,
    schema_version: str,
    payload_json: str,
    expected_sha256: str,
) -> Any:
    """Hydrate an exact registered record; unknown versions never fall back."""

    validate_preliminary_persistence_contract(record_type, schema_version)
    if hashlib.sha256(payload_json.encode()).hexdigest() != expected_sha256:
        raise ArtifactCorruptionError(
            "Preliminary persistence record failed integrity validation"
        )
    adapter = PRELIMINARY_PERSISTENCE_ADAPTERS[(record_type, schema_version)]
    try:
        return adapter.validate_json(payload_json)
    except ValidationError as exc:
        raise ArtifactCorruptionError(
            "Stored Preliminary persistence record failed schema validation"
        ) from exc

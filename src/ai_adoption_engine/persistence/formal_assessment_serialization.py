"""Exact canonical serialization for frozen formal-assessment contracts."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError

from ai_adoption_engine.models.formal_assessment import (
    FORMAL_ASSESSMENT_AUTHORIZATION_SCHEMA,
    FORMAL_ASSESSMENT_INPUT_CHOICE_SCHEMA,
    FORMAL_ASSESSMENT_INPUT_PROJECTION_SCHEMA,
    FORMAL_ASSESSMENT_RESULT_SCHEMA,
    FORMAL_ASSESSMENT_RESULT_SUPERSESSION_SCHEMA,
    FORMAL_ASSESSMENT_RUN_EVENT_SCHEMA,
    FORMAL_ASSESSMENT_RUN_MANIFEST_SCHEMA,
    FORMAL_ASSESSMENT_RUN_REQUEST_SCHEMA,
    FORMAL_ASSESSMENT_RUN_STATE_SCHEMA,
    FORMAL_EVIDENCE_GUIDANCE_SCHEMA,
    FORMAL_INPUT_CONFLICT_RESOLUTION_SCHEMA,
    FormalAssessmentAuthorization,
    FormalAssessmentInputChoice,
    FormalAssessmentInputProjection,
    FormalAssessmentResult,
    FormalAssessmentResultSupersession,
    FormalAssessmentRunEvent,
    FormalAssessmentRunManifest,
    FormalAssessmentRunRequest,
    FormalAssessmentRunState,
    FormalAssessmentTerminalFailure,
    FormalEvidenceGuidance,
    FormalInputConflictResolution,
)
from ai_adoption_engine.persistence.base import ArtifactCorruptionError


_RESULT_ADAPTER = TypeAdapter(FormalAssessmentResult | FormalAssessmentTerminalFailure)

FORMAL_ASSESSMENT_ADAPTERS: dict[str, TypeAdapter[Any]] = {
    FORMAL_ASSESSMENT_INPUT_CHOICE_SCHEMA: TypeAdapter(FormalAssessmentInputChoice),
    FORMAL_INPUT_CONFLICT_RESOLUTION_SCHEMA: TypeAdapter(FormalInputConflictResolution),
    FORMAL_ASSESSMENT_AUTHORIZATION_SCHEMA: TypeAdapter(FormalAssessmentAuthorization),
    FORMAL_ASSESSMENT_INPUT_PROJECTION_SCHEMA: TypeAdapter(
        FormalAssessmentInputProjection
    ),
    FORMAL_ASSESSMENT_RUN_REQUEST_SCHEMA: TypeAdapter(FormalAssessmentRunRequest),
    FORMAL_ASSESSMENT_RUN_MANIFEST_SCHEMA: TypeAdapter(FormalAssessmentRunManifest),
    FORMAL_ASSESSMENT_RUN_EVENT_SCHEMA: TypeAdapter(FormalAssessmentRunEvent),
    FORMAL_ASSESSMENT_RUN_STATE_SCHEMA: TypeAdapter(FormalAssessmentRunState),
    FORMAL_ASSESSMENT_RESULT_SCHEMA: _RESULT_ADAPTER,
    FORMAL_ASSESSMENT_RESULT_SUPERSESSION_SCHEMA: TypeAdapter(
        FormalAssessmentResultSupersession
    ),
    FORMAL_EVIDENCE_GUIDANCE_SCHEMA: TypeAdapter(FormalEvidenceGuidance),
}

_TYPES_BY_SCHEMA: dict[str, tuple[type[BaseModel], ...]] = {
    FORMAL_ASSESSMENT_INPUT_CHOICE_SCHEMA: (FormalAssessmentInputChoice,),
    FORMAL_INPUT_CONFLICT_RESOLUTION_SCHEMA: (FormalInputConflictResolution,),
    FORMAL_ASSESSMENT_AUTHORIZATION_SCHEMA: (FormalAssessmentAuthorization,),
    FORMAL_ASSESSMENT_INPUT_PROJECTION_SCHEMA: (FormalAssessmentInputProjection,),
    FORMAL_ASSESSMENT_RUN_REQUEST_SCHEMA: (FormalAssessmentRunRequest,),
    FORMAL_ASSESSMENT_RUN_MANIFEST_SCHEMA: (FormalAssessmentRunManifest,),
    FORMAL_ASSESSMENT_RUN_EVENT_SCHEMA: (FormalAssessmentRunEvent,),
    FORMAL_ASSESSMENT_RUN_STATE_SCHEMA: (FormalAssessmentRunState,),
    FORMAL_ASSESSMENT_RESULT_SCHEMA: (
        FormalAssessmentResult,
        FormalAssessmentTerminalFailure,
    ),
    FORMAL_ASSESSMENT_RESULT_SUPERSESSION_SCHEMA: (
        FormalAssessmentResultSupersession,
    ),
    FORMAL_EVIDENCE_GUIDANCE_SCHEMA: (FormalEvidenceGuidance,),
}


def validate_formal_assessment_schema(schema_version: str) -> None:
    if schema_version not in FORMAL_ASSESSMENT_ADAPTERS:
        raise ArtifactCorruptionError(
            f"Unsupported formal-assessment persistence contract: {schema_version}"
        )


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ArtifactCorruptionError(
            "Formal-assessment record is not canonical JSON"
        ) from exc


def serialize_formal_assessment_record(payload: BaseModel) -> tuple[str, str]:
    """Validate and encode exactly one frozen formal-assessment record."""

    schema_version = getattr(payload, "schema_version", None)
    if not isinstance(schema_version, str):
        raise ArtifactCorruptionError(
            "Formal-assessment persistence payload has no schema identity"
        )
    validate_formal_assessment_schema(schema_version)
    if not isinstance(payload, _TYPES_BY_SCHEMA[schema_version]):
        raise ArtifactCorruptionError(
            "Formal-assessment payload type does not match its schema identity"
        )
    adapter = FORMAL_ASSESSMENT_ADAPTERS[schema_version]
    try:
        validated = adapter.validate_python(payload.model_dump(mode="json"))
    except ValidationError as exc:
        raise ArtifactCorruptionError(
            "Formal-assessment persistence record failed schema validation"
        ) from exc
    encoded = _canonical_json(adapter.dump_python(validated, mode="json"))
    return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def deserialize_formal_assessment_record(
    schema_version: str,
    payload_json: str,
    expected_sha256: str,
) -> BaseModel:
    """Hydrate exact canonical bytes without fallback or version conversion."""

    validate_formal_assessment_schema(schema_version)
    actual_sha = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    if actual_sha != expected_sha256:
        raise ArtifactCorruptionError(
            "Formal-assessment persistence record failed integrity validation"
        )
    try:
        raw = json.loads(
            payload_json,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-canonical numeric constant: {value}")
            ),
        )
        validated = FORMAL_ASSESSMENT_ADAPTERS[schema_version].validate_python(raw)
    except (json.JSONDecodeError, TypeError, ValueError, ValidationError) as exc:
        raise ArtifactCorruptionError(
            "Stored formal-assessment record failed schema validation"
        ) from exc
    canonical = _canonical_json(
        FORMAL_ASSESSMENT_ADAPTERS[schema_version].dump_python(
            validated, mode="json"
        )
    )
    if canonical != payload_json:
        raise ArtifactCorruptionError(
            "Stored formal-assessment record is not in canonical byte form"
        )
    if not isinstance(validated, BaseModel):
        raise ArtifactCorruptionError(
            "Stored formal-assessment record did not hydrate a frozen contract"
        )
    return validated


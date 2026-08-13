"""Strict JSON serialization for existing Phase 1-6 artifacts."""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError

from ai_adoption_engine.workspace.models import ArtifactType
from ai_adoption_engine.models.decision_support import DecisionPackageGenerationResult
from ai_adoption_engine.models.document import IngestionResult
from ai_adoption_engine.models.extraction import CandidateExtractionResult
from ai_adoption_engine.models.integrated_assessment import IntegratedAssessmentResult
from ai_adoption_engine.models.review import ApprovedProcessReview, ProcessReviewSession
from ai_adoption_engine.persistence.base import ArtifactCorruptionError


_ADAPTERS: dict[ArtifactType, TypeAdapter[Any]] = {
    ArtifactType.INGESTION_RESULT: TypeAdapter(IngestionResult),
    ArtifactType.CANDIDATE_EXTRACTION_RESULT: TypeAdapter(CandidateExtractionResult),
    ArtifactType.REVIEW_SESSION: TypeAdapter(ProcessReviewSession),
    ArtifactType.APPROVED_REVIEW: TypeAdapter(ApprovedProcessReview),
    ArtifactType.INTEGRATED_ASSESSMENT_RESULT: TypeAdapter(IntegratedAssessmentResult),
    ArtifactType.DECISION_PACKAGE_RESULT: TypeAdapter(DecisionPackageGenerationResult),
}

_SUPPORTED_SCHEMA_VERSIONS = {
    ArtifactType.INGESTION_RESULT: {"phase2-v0.1"},
    ArtifactType.CANDIDATE_EXTRACTION_RESULT: {"phase3-v0.1"},
    ArtifactType.REVIEW_SESSION: {"phase4-v0.1"},
    ArtifactType.APPROVED_REVIEW: {"phase4-v0.1"},
    ArtifactType.INTEGRATED_ASSESSMENT_RESULT: {"phase5-v0.1"},
    ArtifactType.DECISION_PACKAGE_RESULT: {"phase6-v0.1"},
}


def validate_schema_version(
    artifact_type: ArtifactType, artifact_schema_version: str
) -> None:
    if artifact_schema_version not in _SUPPORTED_SCHEMA_VERSIONS[artifact_type]:
        raise ArtifactCorruptionError(
            f"Unsupported {artifact_type.value} schema version"
        )


def serialize_artifact(artifact_type: ArtifactType, payload: BaseModel) -> tuple[str, str]:
    adapter = _ADAPTERS[artifact_type]
    try:
        validated = adapter.validate_python(payload)
    except ValidationError as exc:
        raise ArtifactCorruptionError(
            f"Payload does not satisfy {artifact_type.value} schema"
        ) from exc
    encoded = adapter.dump_json(validated, by_alias=True, exclude_none=False).decode()
    return encoded, hashlib.sha256(encoded.encode()).hexdigest()


def deserialize_artifact(
    artifact_type: ArtifactType,
    payload_json: str,
    expected_sha256: str,
) -> Any:
    actual = hashlib.sha256(payload_json.encode()).hexdigest()
    if actual != expected_sha256:
        raise ArtifactCorruptionError(
            f"Stored {artifact_type.value} payload failed integrity validation"
        )
    try:
        return _ADAPTERS[artifact_type].validate_json(payload_json)
    except ValidationError as exc:
        raise ArtifactCorruptionError(
            f"Stored {artifact_type.value} payload failed schema validation"
        ) from exc

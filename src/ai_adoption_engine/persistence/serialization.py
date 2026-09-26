"""Strict JSON serialization for existing Phase 1-6 artifacts."""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError

from ai_adoption_engine.workspace.models import ArtifactType
from ai_adoption_engine.grw.models import GrwEvidenceReview, GrwEvidenceSubmission
from ai_adoption_engine.models.decision_support import DecisionPackageGenerationResult
from ai_adoption_engine.models.document import IngestionResult
from ai_adoption_engine.models.extraction import CandidateExtractionResult
from ai_adoption_engine.models.integrated_assessment import IntegratedAssessmentResult
from ai_adoption_engine.models.four_gate_decision_support import (
    FourGateDecisionPackageResult,
)
from ai_adoption_engine.models.four_gate_integrated_assessment import (
    FourGateIntegratedAssessmentResult,
)
from ai_adoption_engine.models.review import ApprovedProcessReview, ProcessReviewSession
from ai_adoption_engine.persistence.base import ArtifactCorruptionError


ArtifactContract = tuple[ArtifactType, str]

_ADAPTERS: dict[ArtifactContract, TypeAdapter[Any]] = {
    (ArtifactType.INGESTION_RESULT, "phase2-v0.1"): TypeAdapter(IngestionResult),
    (
        ArtifactType.CANDIDATE_EXTRACTION_RESULT,
        "phase3-v0.1",
    ): TypeAdapter(CandidateExtractionResult),
    (ArtifactType.REVIEW_SESSION, "phase4-v0.1"): TypeAdapter(
        ProcessReviewSession
    ),
    (ArtifactType.APPROVED_REVIEW, "phase4-v0.1"): TypeAdapter(
        ApprovedProcessReview
    ),
    (
        ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
        "phase5-v0.1",
    ): TypeAdapter(IntegratedAssessmentResult),
    (
        ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
        "phase5-v0.2",
    ): TypeAdapter(FourGateIntegratedAssessmentResult),
    (
        ArtifactType.DECISION_PACKAGE_RESULT,
        "phase6-v0.1",
    ): TypeAdapter(DecisionPackageGenerationResult),
    (
        ArtifactType.DECISION_PACKAGE_RESULT,
        "phase6-v0.2",
    ): TypeAdapter(FourGateDecisionPackageResult),
    (ArtifactType.GRW_EVIDENCE_SUBMISSION, "grw-m1-v0.1"): TypeAdapter(
        GrwEvidenceSubmission
    ),
    (ArtifactType.GRW_EVIDENCE_REVIEW, "grw-m1-v0.1"): TypeAdapter(
        GrwEvidenceReview
    ),
}

_LEGACY_SCHEMA_VERSION_BY_TYPE = {
    ArtifactType.INGESTION_RESULT: "phase2-v0.1",
    ArtifactType.CANDIDATE_EXTRACTION_RESULT: "phase3-v0.1",
    ArtifactType.REVIEW_SESSION: "phase4-v0.1",
    ArtifactType.APPROVED_REVIEW: "phase4-v0.1",
    ArtifactType.INTEGRATED_ASSESSMENT_RESULT: "phase5-v0.1",
    ArtifactType.DECISION_PACKAGE_RESULT: "phase6-v0.1",
    ArtifactType.GRW_EVIDENCE_SUBMISSION: "grw-m1-v0.1",
    ArtifactType.GRW_EVIDENCE_REVIEW: "grw-m1-v0.1",
}


def validate_schema_version(
    artifact_type: ArtifactType, artifact_schema_version: str
) -> None:
    if (artifact_type, artifact_schema_version) not in _ADAPTERS:
        raise ArtifactCorruptionError(
            f"Unsupported {artifact_type.value} schema version"
        )


def serialize_artifact_versioned(
    artifact_type: ArtifactType,
    artifact_schema_version: str,
    payload: BaseModel,
) -> tuple[str, str]:
    """Serialize through one exact artifact-type/schema-version adapter."""

    validate_schema_version(artifact_type, artifact_schema_version)
    adapter = _ADAPTERS[(artifact_type, artifact_schema_version)]
    try:
        candidate = (
            payload.model_dump(mode="json")
            if isinstance(payload, BaseModel)
            else payload
        )
        validated = adapter.validate_python(candidate)
    except ValidationError as exc:
        raise ArtifactCorruptionError(
            f"Payload does not satisfy {artifact_type.value} schema"
        ) from exc
    encoded = adapter.dump_json(validated, by_alias=True, exclude_none=False).decode()
    return encoded, hashlib.sha256(encoded.encode()).hexdigest()


def deserialize_artifact_versioned(
    artifact_type: ArtifactType,
    artifact_schema_version: str,
    payload_json: str,
    expected_sha256: str,
) -> Any:
    """Hydrate through one exact adapter; unknown pairs never fall back."""

    validate_schema_version(artifact_type, artifact_schema_version)
    actual = hashlib.sha256(payload_json.encode()).hexdigest()
    if actual != expected_sha256:
        raise ArtifactCorruptionError(
            f"Stored {artifact_type.value} payload failed integrity validation"
        )
    try:
        return _ADAPTERS[(artifact_type, artifact_schema_version)].validate_json(
            payload_json
        )
    except ValidationError as exc:
        raise ArtifactCorruptionError(
            f"Stored {artifact_type.value} payload failed schema validation"
        ) from exc


def serialize_artifact(
    artifact_type: ArtifactType,
    payload: BaseModel,
) -> tuple[str, str]:
    """Backward-compatible legacy serializer with an exact legacy mapping."""

    return serialize_artifact_versioned(
        artifact_type,
        _LEGACY_SCHEMA_VERSION_BY_TYPE[artifact_type],
        payload,
    )


def deserialize_artifact(
    artifact_type: ArtifactType,
    payload_json: str,
    expected_sha256: str,
) -> Any:
    """Backward-compatible legacy reader; never selects the successor."""

    return deserialize_artifact_versioned(
        artifact_type,
        _LEGACY_SCHEMA_VERSION_BY_TYPE[artifact_type],
        payload_json,
        expected_sha256,
    )

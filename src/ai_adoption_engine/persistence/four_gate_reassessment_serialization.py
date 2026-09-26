"""Exact artifact dispatch for ``grw-m2-four-gate-v0.1``."""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError

from ai_adoption_engine.grw.four_gate_m2.models import (
    SCHEMA_VERSION,
    FourGateM2ArtifactType,
    FourGateM2BaselineSuccessorComparison,
    FourGateM2DataReadinessResolution,
    FourGateM2DocumentSubmission,
    FourGateM2EvidenceReview,
    FourGateM2ReassessmentApproval,
    FourGateM2ReassessmentRequest,
    FourGateM2RunManifest,
    FourGateM2SuccessorApprovedReview,
    FourGateM2SuccessorAssessment,
    FourGateM2SuccessorDecisionPackage,
)
from ai_adoption_engine.persistence.base import ArtifactCorruptionError


_ADAPTERS: dict[tuple[FourGateM2ArtifactType, str], TypeAdapter[Any]] = {
    (FourGateM2ArtifactType.RUN_MANIFEST, SCHEMA_VERSION): TypeAdapter(
        FourGateM2RunManifest
    ),
    (FourGateM2ArtifactType.DOCUMENT_SUBMISSION, SCHEMA_VERSION): TypeAdapter(
        FourGateM2DocumentSubmission
    ),
    (FourGateM2ArtifactType.EVIDENCE_REVIEW, SCHEMA_VERSION): TypeAdapter(
        FourGateM2EvidenceReview
    ),
    (FourGateM2ArtifactType.DATA_READINESS_RESOLUTION, SCHEMA_VERSION): TypeAdapter(
        FourGateM2DataReadinessResolution
    ),
    (FourGateM2ArtifactType.REASSESSMENT_REQUEST, SCHEMA_VERSION): TypeAdapter(
        FourGateM2ReassessmentRequest
    ),
    (FourGateM2ArtifactType.REASSESSMENT_APPROVAL, SCHEMA_VERSION): TypeAdapter(
        FourGateM2ReassessmentApproval
    ),
    (FourGateM2ArtifactType.SUCCESSOR_APPROVED_REVIEW, SCHEMA_VERSION): TypeAdapter(
        FourGateM2SuccessorApprovedReview
    ),
    (
        FourGateM2ArtifactType.SUCCESSOR_INTEGRATED_ASSESSMENT,
        SCHEMA_VERSION,
    ): TypeAdapter(FourGateM2SuccessorAssessment),
    (FourGateM2ArtifactType.SUCCESSOR_DECISION_PACKAGE, SCHEMA_VERSION): TypeAdapter(
        FourGateM2SuccessorDecisionPackage
    ),
    (
        FourGateM2ArtifactType.BASELINE_SUCCESSOR_COMPARISON,
        SCHEMA_VERSION,
    ): TypeAdapter(FourGateM2BaselineSuccessorComparison),
}


def serialize_four_gate_m2_artifact(
    artifact_type: FourGateM2ArtifactType,
    schema_version: str,
    payload: BaseModel,
) -> tuple[str, str]:
    adapter = _adapter(artifact_type, schema_version)
    try:
        validated = adapter.validate_python(payload.model_dump(mode="json"))
    except ValidationError as exc:
        raise ArtifactCorruptionError(
            "Successor reassessment artifact failed schema validation"
        ) from exc
    encoded = adapter.dump_json(validated, exclude_none=False).decode()
    return encoded, hashlib.sha256(encoded.encode()).hexdigest()


def deserialize_four_gate_m2_artifact(
    artifact_type: FourGateM2ArtifactType,
    schema_version: str,
    payload_json: str,
    expected_sha256: str,
) -> Any:
    adapter = _adapter(artifact_type, schema_version)
    if hashlib.sha256(payload_json.encode()).hexdigest() != expected_sha256:
        raise ArtifactCorruptionError(
            "Successor reassessment artifact failed integrity validation"
        )
    try:
        return adapter.validate_json(payload_json)
    except ValidationError as exc:
        raise ArtifactCorruptionError(
            "Successor reassessment artifact failed schema validation"
        ) from exc


def _adapter(
    artifact_type: FourGateM2ArtifactType, schema_version: str
) -> TypeAdapter[Any]:
    try:
        return _ADAPTERS[(artifact_type, schema_version)]
    except KeyError as exc:
        raise ArtifactCorruptionError(
            "Unsupported successor reassessment artifact type/version"
        ) from exc

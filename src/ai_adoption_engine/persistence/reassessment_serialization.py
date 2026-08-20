"""Canonical JSON persistence for isolated M2 artefacts."""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError

from ai_adoption_engine.grw.m2.models import (
    M2BaselineSuccessorComparison,
    M2DataReadinessResolution,
    M2DocumentSubmission,
    M2EvidenceReview,
    M2ReassessmentApproval,
    M2ReassessmentRequest,
    M2SuccessorApprovedReview,
    M2SuccessorAssessment,
    M2SuccessorDecisionPackage,
)
from ai_adoption_engine.persistence.base import ArtifactCorruptionError


_ADAPTERS: dict[str, TypeAdapter[Any]] = {
    "RUN_MANIFEST": TypeAdapter(dict[str, Any]),
    "DOCUMENT_SUBMISSION": TypeAdapter(M2DocumentSubmission),
    "EVIDENCE_REVIEW": TypeAdapter(M2EvidenceReview),
    "DATA_READINESS_RESOLUTION": TypeAdapter(M2DataReadinessResolution),
    "REASSESSMENT_REQUEST": TypeAdapter(M2ReassessmentRequest),
    "REASSESSMENT_APPROVAL": TypeAdapter(M2ReassessmentApproval),
    "SUCCESSOR_APPROVED_REVIEW": TypeAdapter(M2SuccessorApprovedReview),
    "SUCCESSOR_INTEGRATED_ASSESSMENT": TypeAdapter(M2SuccessorAssessment),
    "SUCCESSOR_DECISION_PACKAGE": TypeAdapter(M2SuccessorDecisionPackage),
    "BASELINE_SUCCESSOR_COMPARISON": TypeAdapter(M2BaselineSuccessorComparison),
}


def serialize_m2_artifact(artifact_type: str, payload: BaseModel | dict[str, Any]) -> tuple[str, str]:
    try:
        validated = _ADAPTERS[artifact_type].validate_python(payload)
        encoded = _ADAPTERS[artifact_type].dump_json(validated, by_alias=True, exclude_none=False).decode("utf-8")
    except (KeyError, ValidationError) as exc:
        raise ArtifactCorruptionError(f"Payload does not satisfy M2 {artifact_type} schema") from exc
    return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def deserialize_m2_artifact(artifact_type: str, payload_json: str, expected_sha256: str) -> Any:
    actual = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    if actual != expected_sha256:
        raise ArtifactCorruptionError(f"Stored M2 {artifact_type} payload failed integrity validation")
    try:
        return _ADAPTERS[artifact_type].validate_json(payload_json)
    except (KeyError, ValidationError) as exc:
        raise ArtifactCorruptionError(f"Stored M2 {artifact_type} payload failed schema validation") from exc

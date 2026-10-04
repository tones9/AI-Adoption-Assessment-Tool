"""Exact canonical serialization for ``preliminary-formal-evidence.v0.1``."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError

from ai_adoption_engine.models.formal_evidence import (
    CONTEXT_NOTE_SCHEMA,
    EXTERNAL_PROVIDER_CONSENT_SCHEMA,
    FORMAL_EVIDENCE_READINESS_SCHEMA,
    FORMAL_EVIDENCE_WORKFLOW_EVENT_SCHEMA,
    FORMAL_INPUT_CANDIDATE_SET_SCHEMA,
    FORMAL_INPUT_MAPPING_SCHEMA,
    REVIEWER_DECLARATION_SCHEMA,
    SUPPORTING_DOCUMENT_INGESTION_ATTEMPT_SCHEMA,
    SUPPORTING_DOCUMENT_METADATA_REVISION_SCHEMA,
    SUPPORTING_DOCUMENT_SCHEMA,
    SUPPORTING_EVIDENCE_EXTRACTION_ATTEMPT_SCHEMA,
    SUPPORTING_EVIDENCE_PROPOSAL_SCHEMA,
    SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
    SUPPORTING_SOURCE_BLOB_SCHEMA,
    ContextNote,
    ExternalProviderConsent,
    FormalEvidenceReadiness,
    FormalEvidenceWorkflowEvent,
    FormalInputCandidateSet,
    FormalInputMapping,
    ReviewerDeclaration,
    SupportingDocument,
    SupportingDocumentIngestionAttempt,
    SupportingDocumentMetadataRevision,
    SupportingEvidenceExtractionAttempt,
    SupportingEvidenceProposal,
    SupportingEvidenceReviewRevision,
    SupportingSourceBlob,
)
from ai_adoption_engine.persistence.base import ArtifactCorruptionError


FORMAL_EVIDENCE_ADAPTERS: dict[str, TypeAdapter[Any]] = {
    SUPPORTING_SOURCE_BLOB_SCHEMA: TypeAdapter(SupportingSourceBlob),
    SUPPORTING_DOCUMENT_SCHEMA: TypeAdapter(SupportingDocument),
    SUPPORTING_DOCUMENT_METADATA_REVISION_SCHEMA: TypeAdapter(
        SupportingDocumentMetadataRevision
    ),
    SUPPORTING_DOCUMENT_INGESTION_ATTEMPT_SCHEMA: TypeAdapter(
        SupportingDocumentIngestionAttempt
    ),
    SUPPORTING_EVIDENCE_EXTRACTION_ATTEMPT_SCHEMA: TypeAdapter(
        SupportingEvidenceExtractionAttempt
    ),
    SUPPORTING_EVIDENCE_PROPOSAL_SCHEMA: TypeAdapter(SupportingEvidenceProposal),
    SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA: TypeAdapter(
        SupportingEvidenceReviewRevision
    ),
    FORMAL_INPUT_MAPPING_SCHEMA: TypeAdapter(FormalInputMapping),
    FORMAL_INPUT_CANDIDATE_SET_SCHEMA: TypeAdapter(FormalInputCandidateSet),
    FORMAL_EVIDENCE_READINESS_SCHEMA: TypeAdapter(FormalEvidenceReadiness),
    FORMAL_EVIDENCE_WORKFLOW_EVENT_SCHEMA: TypeAdapter(FormalEvidenceWorkflowEvent),
    REVIEWER_DECLARATION_SCHEMA: TypeAdapter(ReviewerDeclaration),
    EXTERNAL_PROVIDER_CONSENT_SCHEMA: TypeAdapter(ExternalProviderConsent),
    CONTEXT_NOTE_SCHEMA: TypeAdapter(ContextNote),
}


def validate_formal_evidence_schema(schema_version: str) -> None:
    if schema_version not in FORMAL_EVIDENCE_ADAPTERS:
        raise ArtifactCorruptionError(
            f"Unsupported formal-evidence persistence contract: {schema_version}"
        )


def serialize_formal_evidence_record(payload: BaseModel) -> tuple[str, str]:
    """Validate and serialize one exact Slice 1 record."""

    schema_version = getattr(payload, "schema_version", None)
    if not isinstance(schema_version, str):
        raise ArtifactCorruptionError(
            "Formal-evidence persistence payload has no schema identity"
        )
    validate_formal_evidence_schema(schema_version)
    adapter = FORMAL_EVIDENCE_ADAPTERS[schema_version]
    try:
        validated = adapter.validate_python(payload.model_dump(mode="json"))
    except ValidationError as exc:
        raise ArtifactCorruptionError(
            "Formal-evidence persistence record failed schema validation"
        ) from exc
    encoded = json.dumps(
        adapter.dump_python(validated, mode="json"),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def deserialize_formal_evidence_record(
    schema_version: str,
    payload_json: str,
    expected_sha256: str,
) -> Any:
    """Hydrate an exact Slice 1 record without version or family fallback."""

    validate_formal_evidence_schema(schema_version)
    if hashlib.sha256(payload_json.encode("utf-8")).hexdigest() != expected_sha256:
        raise ArtifactCorruptionError(
            "Formal-evidence persistence record failed integrity validation"
        )
    try:
        return FORMAL_EVIDENCE_ADAPTERS[schema_version].validate_json(payload_json)
    except ValidationError as exc:
        raise ArtifactCorruptionError(
            "Stored formal-evidence record failed schema validation"
        ) from exc

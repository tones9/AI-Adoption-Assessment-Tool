"""Phase 7 application-workspace and persistence contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecutionMode(StrEnum):
    OFFLINE_DEMO = "offline-demo"
    LIVE_PROVIDER = "live-provider"


class WorkflowStage(StrEnum):
    NEW = "new"
    INGESTED = "ingested"
    CANDIDATE_READY = "candidate-ready"
    IN_REVIEW = "in-review"
    APPROVED = "approved"
    ASSESSED = "assessed"
    PACKAGE_READY = "package-ready"


class ArtifactType(StrEnum):
    INGESTION_RESULT = "INGESTION_RESULT"
    CANDIDATE_EXTRACTION_RESULT = "CANDIDATE_EXTRACTION_RESULT"
    REVIEW_SESSION = "REVIEW_SESSION"
    APPROVED_REVIEW = "APPROVED_REVIEW"
    INTEGRATED_ASSESSMENT_RESULT = "INTEGRATED_ASSESSMENT_RESULT"
    DECISION_PACKAGE_RESULT = "DECISION_PACKAGE_RESULT"
    GRW_EVIDENCE_SUBMISSION = "GRW_EVIDENCE_SUBMISSION"
    GRW_EVIDENCE_REVIEW = "GRW_EVIDENCE_REVIEW"


IMMUTABLE_ARTIFACT_TYPES = frozenset(
    {
        ArtifactType.INGESTION_RESULT,
        ArtifactType.CANDIDATE_EXTRACTION_RESULT,
        ArtifactType.APPROVED_REVIEW,
        ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
        ArtifactType.DECISION_PACKAGE_RESULT,
        ArtifactType.GRW_EVIDENCE_SUBMISSION,
        ArtifactType.GRW_EVIDENCE_REVIEW,
    }
)


class OperationKind(StrEnum):
    INGEST = "ingest"
    EXTRACT = "extract"
    APPROVE = "approve"
    ASSESS = "assess"
    GENERATE_PACKAGE = "generate-package"
    GRW_SUBMIT = "grw-submit"
    GRW_REVIEW = "grw-review"


class OperationStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class AssessmentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    assessment_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    execution_mode: ExecutionMode
    current_stage: WorkflowStage
    source_filename: str | None = None
    source_input_type: str | None = None
    document_id: str | None = None
    created_at: datetime
    updated_at: datetime
    row_version: int = Field(ge=1)


class ArtifactReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(min_length=1)
    assessment_id: str = Field(min_length=1)
    artifact_type: ArtifactType
    artifact_revision: int = Field(ge=1)


class StoredArtifact(ArtifactReference):
    artifact_schema_version: str = Field(min_length=1)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parent_artifact_id: str | None = None
    created_at: datetime
    updated_at: datetime
    payload: Any


class OperationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: str = Field(min_length=1)
    assessment_id: str = Field(min_length=1)
    operation_kind: OperationKind
    idempotency_key: str = Field(min_length=1)
    status: OperationStatus
    produced_artifact_id: str | None = None
    sanitised_error_code: str | None = None
    started_at: datetime
    completed_at: datetime | None = None


class WorkspaceSnapshot(BaseModel):
    """Fully validated active workspace; no partial hydration is permitted."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    assessment: AssessmentRecord
    active_artifacts: dict[ArtifactType, StoredArtifact]

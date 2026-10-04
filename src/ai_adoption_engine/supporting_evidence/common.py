"""Stable identity helpers shared by the explicit Slice 3 services."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ai_adoption_engine.models.formal_evidence import (
    FORMAL_EVIDENCE_FAMILY,
    FORMAL_EVIDENCE_WORKFLOW_EVENT_SCHEMA,
    FormalEvidenceLineage,
    FormalEvidenceWorkflowEvent,
    RequestIdentity,
    WorkflowEventType,
)
from ai_adoption_engine.persistence.formal_evidence import (
    FormalEvidenceIdempotencyError,
    FormalEvidenceLineageError,
    FormalEvidenceOperationReplay,
    SQLiteFormalEvidenceRepository,
)
from ai_adoption_engine.supporting_evidence.errors import (
    SupportingEvidenceLineageError,
    SupportingEvidenceRequestConflictError,
    SupportingEvidenceServiceError,
)


Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def request_identity(token: str, canonical_value: Any) -> RequestIdentity:
    if not token.strip():
        raise ValueError("Supporting-evidence request token cannot be blank")
    return RequestIdentity(
        request_token=token,
        canonical_request_sha256=canonical_sha256(canonical_value),
    )


def require_lineage(
    repository: SQLiteFormalEvidenceRepository,
    lineage: FormalEvidenceLineage,
) -> None:
    repository.assert_writable()
    try:
        repository.validate_active_lineage(lineage)
    except FormalEvidenceLineageError as exc:
        raise SupportingEvidenceLineageError(
            "The formal lifecycle or approved-process lineage is no longer current."
        ) from exc


def replay_for_request(
    repository: SQLiteFormalEvidenceRepository,
    *,
    request: RequestIdentity,
    operation_type: str,
    lineage: FormalEvidenceLineage,
) -> FormalEvidenceOperationReplay | None:
    replay = repository.load_operation_replay(request.request_token)
    if replay is None:
        return None
    if (
        replay.canonical_request_sha256 != request.canonical_request_sha256
        or replay.operation_type != operation_type
        or replay.formal_lifecycle_id != lineage.formal_lifecycle_id
    ):
        raise SupportingEvidenceRequestConflictError(
            "This request token was already used for a different operation."
        )
    return replay


def next_workflow_event(
    repository: SQLiteFormalEvidenceRepository,
    *,
    lineage: FormalEvidenceLineage,
    event_type: WorkflowEventType,
    subject_id: str,
    request: RequestIdentity,
    payload_sha256: str,
    occurred_at: datetime,
    event_id: str,
) -> FormalEvidenceWorkflowEvent:
    latest = repository.latest_workflow_event(lineage.formal_lifecycle_id)
    return FormalEvidenceWorkflowEvent(
        schema_version=FORMAL_EVIDENCE_WORKFLOW_EVENT_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        event_id=event_id,
        lineage=lineage,
        lifecycle_sequence=1 if latest is None else latest.lifecycle_sequence + 1,
        prior_event_id=None if latest is None else latest.event_id,
        event_type=event_type,
        subject_id=subject_id,
        request=request,
        payload_sha256=payload_sha256,
        occurred_at=occurred_at,
    )


def translate_repository_conflict(exc: Exception) -> SupportingEvidenceServiceError:
    if isinstance(exc, FormalEvidenceIdempotencyError):
        return SupportingEvidenceRequestConflictError(
            "This request token was already used for a different operation."
        )
    return SupportingEvidenceLineageError(
        "The supporting-evidence operation did not match current immutable history."
    )

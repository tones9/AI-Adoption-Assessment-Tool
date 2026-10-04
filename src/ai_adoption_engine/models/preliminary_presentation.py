"""Frozen, versioned customer presentation for persisted Preliminary results."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


PRELIMINARY_PRESENTATION_SCHEMA_VERSION = "preliminary-result-presentation.v0.1"


class _FrozenPresentationContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PresentationSourceExcerpt(_FrozenPresentationContract):
    exact_excerpt: str = Field(min_length=1)
    source_locator: str = Field(min_length=1)


class PresentationEvidenceItem(_FrozenPresentationContract):
    statement: str = Field(min_length=1)
    source_excerpts: tuple[PresentationSourceExcerpt, ...] = ()


class PresentationInference(_FrozenPresentationContract):
    statement: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    source_excerpts: tuple[PresentationSourceExcerpt, ...] = ()


class PresentationOpenItem(_FrozenPresentationContract):
    statement: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    source_excerpts: tuple[PresentationSourceExcerpt, ...] = ()


class PresentationEvidenceSections(_FrozenPresentationContract):
    section_order: tuple[
        Literal[
            "Documented source",
            "Reviewed inference",
            "Engine inference",
            "Unknown",
            "Conflict",
            "Next evidence",
        ],
        ...,
    ] = (
        "Documented source",
        "Reviewed inference",
        "Engine inference",
        "Unknown",
        "Conflict",
        "Next evidence",
    )
    documented_source: tuple[PresentationEvidenceItem, ...] = ()
    reviewed_inference: tuple[PresentationInference, ...] = ()
    engine_inference: tuple[PresentationInference, ...] = ()
    unknown: tuple[PresentationOpenItem, ...] = ()
    conflict: tuple[PresentationOpenItem, ...] = ()
    next_evidence: tuple[str, ...] = ()


class PresentationOpportunity(_FrozenPresentationContract):
    heading: str = Field(min_length=1)
    provisional_direction: str = Field(min_length=1)
    evidence_coverage: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    evidence: PresentationEvidenceSections


class PresentationDiscoveryNeed(_FrozenPresentationContract):
    heading: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    evidence_coverage: str = Field(min_length=1)
    evidence: PresentationEvidenceSections


class PresentationActivity(_FrozenPresentationContract):
    heading: str = Field(min_length=1)
    state: str = Field(min_length=1)
    provisional_direction: str | None = Field(default=None, min_length=1)
    evidence_coverage: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    evidence: PresentationEvidenceSections
    opportunities: tuple[PresentationOpportunity, ...] = ()
    discovery_needs: tuple[PresentationDiscoveryNeed, ...] = ()


class PreliminaryCustomerPresentation(_FrozenPresentationContract):
    title: Literal["Preliminary Assessment"] = "Preliminary Assessment"
    provisional_warning: str = Field(min_length=1)
    process_name: str = Field(min_length=1)
    overall_evidence_coverage: str = Field(min_length=1)
    overall_direction_statement: Literal[
        "No single process-wide direction has been generated."
    ] = "No single process-wide direction has been generated."
    evidence_coverage_explanation: Literal[
        "Evidence coverage describes how much relevant documented support is available. It is not probability, safety, implementation readiness, or approval."
    ] = (
        "Evidence coverage describes how much relevant documented support is available. "
        "It is not probability, safety, implementation readiness, or approval."
    )
    activities: tuple[PresentationActivity, ...] = Field(min_length=1)


class PreliminaryPresentationSourceIdentity(_FrozenPresentationContract):
    persisted_result_schema_version: str = Field(min_length=1)
    output_schema_version: str = Field(min_length=1)
    preliminary_result_id: str = Field(min_length=1)
    preliminary_run_id: str = Field(min_length=1)
    journey_id: str = Field(min_length=1)
    completed_run_event_id: str = Field(min_length=1)
    result_created_at: datetime
    evaluator_id: str = Field(min_length=1)
    evaluator_version: str = Field(min_length=1)
    rule_set_id: str = Field(min_length=1)
    rule_set_version: str = Field(min_length=1)
    rule_set_status: str = Field(min_length=1)
    rule_set_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_assessment_id: str = Field(min_length=1)
    approved_review_artifact_id: str = Field(min_length=1)
    approved_review_schema_version: str = Field(min_length=1)
    approved_review_payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_document_id: str = Field(min_length=1)
    extraction_run_id: str = Field(min_length=1)
    review_id: str = Field(min_length=1)
    approval_event_id: str = Field(min_length=1)
    approved_at: datetime
    validated_process_id: str = Field(min_length=1)
    validated_process_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class PresentationAuditEntry(_FrozenPresentationContract):
    entry_type: str = Field(min_length=1)
    identifier: str = Field(min_length=1)
    codes: tuple[str, ...] = ()
    referenced_identifiers: tuple[str, ...] = ()
    decision_trace_json: tuple[str, ...] = ()


class PreliminaryPresentationAudit(_FrozenPresentationContract):
    source_identity: PreliminaryPresentationSourceIdentity
    entries: tuple[PresentationAuditEntry, ...] = ()


class PreliminaryResultPresentation(_FrozenPresentationContract):
    schema_version: Literal[
        "preliminary-result-presentation.v0.1"
    ] = PRELIMINARY_PRESENTATION_SCHEMA_VERSION
    customer: PreliminaryCustomerPresentation
    audit: PreliminaryPresentationAudit | None = None

    def canonical_json_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

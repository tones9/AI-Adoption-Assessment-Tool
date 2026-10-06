"""Frozen, versioned presentation contracts for formal assessment results."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_adoption_engine.models.formal_assessment import (
    FormalAssessmentResult,
    FormalAssessmentResultSupersession,
    FormalEvidenceGuidance,
)


FORMAL_ASSESSMENT_PRESENTATION_SCHEMA = "formal-assessment-result-presentation.v0.1"


class _FrozenPresentationContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FormalPresentationGuidance(_FrozenPresentationContract):
    label: Literal["Information requested for a possible future attempt"] = (
        "Information requested for a possible future attempt"
    )
    requested_information: str = Field(min_length=1)
    boundary_notice: Literal[
        "Requested information is not evidence; uploading a document does not guarantee a successful outcome."
    ]


class FormalPresentationGap(_FrozenPresentationContract):
    field_name: str = Field(min_length=1)
    question: str = Field(min_length=1)
    guidance: FormalPresentationGuidance | None = None


class FormalPresentationGate(_FrozenPresentationContract):
    name: str = Field(min_length=1)
    status: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    blocking_gaps: tuple[FormalPresentationGap, ...] = ()
    capabilities: tuple[str, ...] = ()


class FormalPresentationProvenance(_FrozenPresentationContract):
    field_name: str = Field(min_length=1)
    projection_origin: str = Field(min_length=1)
    knowledge_state: str = Field(min_length=1)
    evidence_status: str = Field(min_length=1)


class FormalPresentationPriority(_FrozenPresentationContract):
    status: str = Field(min_length=1)
    score: float | None = Field(default=None, ge=0, le=100)
    band: str | None = Field(default=None, min_length=1)


class FormalPresentationActivity(_FrozenPresentationContract):
    name: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    decision_status: str = Field(min_length=1)
    change_disposition: str = Field(min_length=1)
    readiness_disposition: str = Field(min_length=1)
    selected_intervention_family: str = Field(min_length=1)
    autonomy_ceiling: str = Field(min_length=1)
    priority: FormalPresentationPriority
    gates: tuple[FormalPresentationGate, ...] = Field(min_length=4, max_length=4)
    capabilities: tuple[str, ...] = ()
    provenance: tuple[FormalPresentationProvenance, ...] = Field(min_length=1)
    activity_evidence: str | None = Field(default=None, min_length=1)


class FormalAssessmentCustomerPresentation(_FrozenPresentationContract):
    title: Literal["Organisational Assessment"] = "Organisational Assessment"
    customer_status: Literal[
        "Organisational assessment completed — review required"
    ] = "Organisational assessment completed — review required"
    non_approval_notice: Literal[
        "This result is not formal approval or implementation authority."
    ] = "This result is not formal approval or implementation authority."
    process_name: str = Field(min_length=1)
    input_mode: str = Field(min_length=1)
    supporting_evidence_disposition: str = Field(min_length=1)
    activities: tuple[FormalPresentationActivity, ...] = Field(min_length=1)


class FormalAssessmentPresentationAudit(_FrozenPresentationContract):
    """Exact frozen sources, intentionally retained only on an audit request."""

    source_result: FormalAssessmentResult
    guidance: FormalEvidenceGuidance | None = None
    supersession: FormalAssessmentResultSupersession | None = None


class FormalAssessmentResultPresentation(_FrozenPresentationContract):
    schema_version: Literal[
        "formal-assessment-result-presentation.v0.1"
    ] = FORMAL_ASSESSMENT_PRESENTATION_SCHEMA
    customer: FormalAssessmentCustomerPresentation
    audit: FormalAssessmentPresentationAudit | None = None

    def canonical_json_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

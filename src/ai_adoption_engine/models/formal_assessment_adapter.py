"""Frozen contracts for the persistence-free formal input adapter."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_adoption_engine.models.enums import CriterionName
from ai_adoption_engine.models.formal_assessment import (
    FORMAL_INPUT_ADAPTER_ID,
    FORMAL_INPUT_ADAPTER_RULES_FINGERPRINT,
    FORMAL_INPUT_ADAPTER_RULES_ID,
    FORMAL_INPUT_ADAPTER_VERSION,
    FormalAssessmentInputProjection,
)
from ai_adoption_engine.models.four_gate_assessment import CapabilitySignalName


FORMAL_INPUT_ADAPTER_RULES_VERSION = "0.1.0"


class FormalFourGateInputAdapterRules(BaseModel):
    """Exact frozen D-037 projection rules; this is not executable policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rules_id: Literal["formal-four-gate-input-adapter-rules.v0.1"] = (
        FORMAL_INPUT_ADAPTER_RULES_ID
    )
    rules_version: Literal["0.1.0"] = FORMAL_INPUT_ADAPTER_RULES_VERSION
    rules_fingerprint: Literal[
        "0472d8517f0a6176ac56ed5599b11c7b22d94092a8a85083551837fd54ec8b5d"
    ] = FORMAL_INPUT_ADAPTER_RULES_FINGERPRINT
    adapter_id: Literal["formal-four-gate-input-adapter.v0.1"] = (
        FORMAL_INPUT_ADAPTER_ID
    )
    adapter_version: Literal["0.1.0"] = FORMAL_INPUT_ADAPTER_VERSION
    criterion_order: tuple[CriterionName, ...] = tuple(CriterionName)
    accountability_position: Literal["AFTER_CRITERIA"] = "AFTER_CRITERIA"
    capability_signal_order: tuple[CapabilitySignalName, ...] = tuple(
        CapabilitySignalName
    )
    no_mapping_rule: Literal["PRESERVE_SOURCE_ONLY"] = "PRESERVE_SOURCE_ONLY"
    fill_unknown_rule: Literal["ONE_DISTINCT_ELIGIBLE_VALUE"] = (
        "ONE_DISTINCT_ELIGIBLE_VALUE"
    )
    corroboration_rule: Literal[
        "EXACT_VALUE_KNOWLEDGE_STATE_AND_CONFIDENCE"
    ] = "EXACT_VALUE_KNOWLEDGE_STATE_AND_CONFIDENCE"
    conflict_rule: Literal["EXPLICIT_AUTHORIZED_HUMAN_SELECTION_ONLY"] = (
        "EXPLICIT_AUTHORIZED_HUMAN_SELECTION_ONLY"
    )
    unknown_rule: Literal["PRESERVE_NULL_NEVER_DEFAULT"] = (
        "PRESERVE_NULL_NEVER_DEFAULT"
    )
    activity_evidence_rule: Literal["PROVENANCE_ONLY_NO_SCALAR"] = (
        "PROVENANCE_ONLY_NO_SCALAR"
    )
    mutation_rule: Literal["IMMUTABLE_INPUTS"] = "IMMUTABLE_INPUTS"

    @model_validator(mode="after")
    def validate_exact_rule_order(self) -> Self:
        if self.criterion_order != tuple(CriterionName):
            raise ValueError("adapter criterion order must match the frozen catalogue")
        if self.capability_signal_order != tuple(CapabilitySignalName):
            raise ValueError(
                "adapter capability-signal order must match the frozen catalogue"
            )
        return self

    def canonical_json_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")


FORMAL_FOUR_GATE_INPUT_ADAPTER_RULES = FormalFourGateInputAdapterRules()


class FormalInputAdapterFailureCode(StrEnum):
    INVALID_AUTHORIZATION = "INVALID_AUTHORIZATION"
    INVALID_APPROVED_REVIEW = "INVALID_APPROVED_REVIEW"
    INVALID_APPROVED_LINEAGE = "INVALID_APPROVED_LINEAGE"
    INCOMPATIBLE_IDENTITY_OR_RULES = "INCOMPATIBLE_IDENTITY_OR_RULES"
    MODE_INPUT_MISMATCH = "MODE_INPUT_MISMATCH"
    INVALID_CANDIDATE_OR_READINESS_PIN = "INVALID_CANDIDATE_OR_READINESS_PIN"
    INVALID_SUPPORTING_PROVENANCE = "INVALID_SUPPORTING_PROVENANCE"
    UNRESOLVED_CONFLICT = "UNRESOLVED_CONFLICT"
    INVALID_CONFLICT_RESOLUTION = "INVALID_CONFLICT_RESOLUTION"
    PROJECTION_VALIDATION_FAILED = "PROJECTION_VALIDATION_FAILED"


class FormalInputAdapterError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: FormalInputAdapterFailureCode
    message: str = Field(min_length=1)
    field_path: str | None = Field(default=None, min_length=1)
    activity_id: str | None = Field(default=None, min_length=1)


class FormalInputAdapterSuccess(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["SUCCESS"] = "SUCCESS"
    adapter_id: Literal["formal-four-gate-input-adapter.v0.1"] = (
        FORMAL_INPUT_ADAPTER_ID
    )
    adapter_version: Literal["0.1.0"] = FORMAL_INPUT_ADAPTER_VERSION
    rules: FormalFourGateInputAdapterRules
    projection: FormalAssessmentInputProjection


class FormalInputAdapterFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["FAILURE"] = "FAILURE"
    adapter_id: Literal["formal-four-gate-input-adapter.v0.1"] = (
        FORMAL_INPUT_ADAPTER_ID
    )
    adapter_version: Literal["0.1.0"] = FORMAL_INPUT_ADAPTER_VERSION
    rules: FormalFourGateInputAdapterRules | None
    errors: tuple[FormalInputAdapterError, ...] = Field(min_length=1)
    projection: Literal[None] = None


FormalInputAdapterResult = Annotated[
    FormalInputAdapterSuccess | FormalInputAdapterFailure,
    Field(discriminator="status"),
]


"""Typed success and failure envelopes for Preliminary Assessment evaluation."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_adoption_engine.models.preliminary_assessment import (
    PreliminaryAssessment,
    PreliminaryRuleSetReference,
)


class PreliminaryEvaluationFailureCode(StrEnum):
    APPROVED_REVIEW_REQUIRED = "APPROVED_REVIEW_REQUIRED"
    INVALID_APPROVAL_ARTIFACT = "INVALID_APPROVAL_ARTIFACT"
    BLOCKING_REVIEW_CONFLICT = "BLOCKING_REVIEW_CONFLICT"
    INVALID_PROCESS_PROJECTION = "INVALID_PROCESS_PROJECTION"
    SOURCE_DOCUMENT_MISMATCH = "SOURCE_DOCUMENT_MISMATCH"
    INVALID_RULE_SET = "INVALID_RULE_SET"
    OUTPUT_VALIDATION_FAILED = "OUTPUT_VALIDATION_FAILED"


class PreliminaryEvaluationError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: PreliminaryEvaluationFailureCode
    message: str = Field(min_length=1)
    field_path: str | None = Field(default=None, min_length=1)


class PreliminaryEvaluationSuccess(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["SUCCESS"] = "SUCCESS"
    assessment: PreliminaryAssessment


class PreliminaryEvaluationFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["FAILURE"] = "FAILURE"
    rule_set: PreliminaryRuleSetReference
    errors: tuple[PreliminaryEvaluationError, ...] = Field(min_length=1)
    assessment: None = None

    @model_validator(mode="after")
    def forbid_partial_assessment(self) -> "PreliminaryEvaluationFailure":
        if self.assessment is not None:
            raise ValueError("A failed evaluation cannot return a partial assessment")
        return self


PreliminaryEvaluationResult = Annotated[
    PreliminaryEvaluationSuccess | PreliminaryEvaluationFailure,
    Field(discriminator="status"),
]

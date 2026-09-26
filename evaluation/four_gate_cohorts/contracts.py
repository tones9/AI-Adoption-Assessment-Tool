"""Strict contracts for synthetic four-gate cohort development fixtures."""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_adoption_engine.models.four_gate_assessment import OutcomeCode
from ai_adoption_engine.models.four_gate_decision_support import (
    FourGateDecisionPackageSuccess,
)
from ai_adoption_engine.models.four_gate_integrated_assessment import (
    FourGateIntegratedAssessmentSuccess,
)


COHORT_PROTOCOL_VERSION = "four-gate-evaluation-cohort.v0.1"
EXPECTED_POLICY_FINGERPRINT = (
    "0a2f0040f78e8a4a48b9cc1d9d72f79b4b980f75b85cbd4fcbd8d9ad556e08f2"
)
DEVELOPMENT_FIXTURE_EXCLUSION = (
    "Synthetic development fixture — excluded from real-world, governed-cohort, "
    "performance, effectiveness, ROI, deployment-safety, threshold-quality, and "
    "generalisation claims."
)


class CohortContractError(ValueError):
    """Raised before evaluation when a cohort contract cannot be trusted."""


class MeasureState(StrEnum):
    OBSERVED = "OBSERVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FourGateCohortPin(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cohort_protocol: Literal["four-gate-evaluation-cohort.v0.1"] = (
        COHORT_PROTOCOL_VERSION
    )
    framework_id: Literal["four-gate-framework.v0.1"] = (
        "four-gate-framework.v0.1"
    )
    framework_version: Literal["0.1"] = "0.1"
    decision_policy_id: Literal["decision_policy.v0.3"] = "decision_policy.v0.3"
    decision_policy_version: Literal["0.3.0"] = "0.3.0"
    decision_policy_fingerprint: Literal[
        "0a2f0040f78e8a4a48b9cc1d9d72f79b4b980f75b85cbd4fcbd8d9ad556e08f2"
    ] = EXPECTED_POLICY_FINGERPRINT
    phase1_contract_version: Literal["phase1-v0.4"] = "phase1-v0.4"
    phase5_schema_version: Literal["phase5-v0.2"] = "phase5-v0.2"
    phase6_schema_version: Literal["phase6-v0.2"] = "phase6-v0.2"


class FourGateSourcePin(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_identifier: str = Field(min_length=1)
    source_filename: str = Field(min_length=1)
    media_type: Literal["text/plain"] = "text/plain"
    byte_length: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class FourGateApprovedReviewPin(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    review_id: str = Field(min_length=1)
    approval_event_id: str = Field(min_length=1)
    source_document_id: str = Field(min_length=1)
    validated_process_id: str = Field(min_length=1)
    validated_process_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class FourGateDevelopmentCaseManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["four-gate-evaluation-case.v0.1"] = (
        "four-gate-evaluation-case.v0.1"
    )
    case_id: str = Field(pattern=r"^DEV-FG-[0-9]{3}$")
    title: str = Field(min_length=1)
    classification: Literal["DEVELOPMENT_FIXTURE"] = "DEVELOPMENT_FIXTURE"
    claim_eligibility: Literal["EXCLUDED_FROM_REAL_WORLD_CLAIMS"] = (
        "EXCLUDED_FROM_REAL_WORLD_CLAIMS"
    )
    frozen_before_at: datetime
    contract: FourGateCohortPin
    source: FourGateSourcePin
    approved_review: FourGateApprovedReviewPin
    development_fixture_exclusion: Literal[DEVELOPMENT_FIXTURE_EXCLUSION] = (
        DEVELOPMENT_FIXTURE_EXCLUSION
    )


class FourGateTraceabilityChecks(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_gate_valid: Literal[True] = True
    exact_contract_identity: Literal[True] = True
    ordered_step_coverage: Literal[True] = True
    four_ordered_gates: Literal[True] = True
    not_evaluated_behavior_valid: Literal[True] = True
    typed_outcome_combinations_valid: Literal[True] = True
    evidence_lineage_resolved: Literal[True] = True
    retained_unknowns_preserved: Literal[True] = True
    gap_classification_valid: Literal[True] = True
    report_sections_complete: Literal[True] = True
    source_and_review_lineage_valid: Literal[True] = True

    @property
    def passed_count(self) -> int:
        return sum(self.model_dump().values())

    @property
    def check_count(self) -> int:
        return len(type(self).model_fields)


class FourGateDeterministicRepeatability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["BYTE_STABLE_SEMANTIC_OUTPUT"] = (
        "BYTE_STABLE_SEMANTIC_OUTPUT"
    )
    first_semantic_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    repeated_semantic_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_equal: Literal[True] = True

    @model_validator(mode="after")
    def require_matching_hashes(self) -> Self:
        if self.first_semantic_sha256 != self.repeated_semantic_sha256:
            raise ValueError("Repeatability hashes must match")
        return self


class FourGateMeasure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    measure_id: str = Field(min_length=1)
    state: MeasureState
    numerator: int | None = Field(default=None, ge=0)
    denominator: int | None = Field(default=None, ge=1)
    not_applicable_reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def preserve_denominators_or_not_applicable(self) -> Self:
        if self.state is MeasureState.NOT_APPLICABLE:
            if self.numerator is not None or self.denominator is not None:
                raise ValueError("Not-applicable measures cannot use zero denominators")
            if self.not_applicable_reason is None:
                raise ValueError("Not-applicable measures require a reason")
            return self
        if self.numerator is None or self.denominator is None:
            raise ValueError("Observed measures require numerator and denominator")
        if self.numerator > self.denominator:
            raise ValueError("A measure numerator cannot exceed its denominator")
        if self.not_applicable_reason is not None:
            raise ValueError("Observed measures cannot have a not-applicable reason")
        return self


class FourGateCohortRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["four-gate-evaluation-run.v0.1"] = (
        "four-gate-evaluation-run.v0.1"
    )
    run_id: str = Field(pattern=r"^four-gate-cohort-run-[0-9a-f]{64}$")
    case_id: str = Field(pattern=r"^DEV-FG-[0-9]{3}$")
    classification: Literal["DEVELOPMENT_FIXTURE"] = "DEVELOPMENT_FIXTURE"
    contract: FourGateCohortPin
    source: FourGateSourcePin
    approved_review: FourGateApprovedReviewPin
    integrated_assessment: FourGateIntegratedAssessmentSuccess
    decision_package: FourGateDecisionPackageSuccess
    traceability: FourGateTraceabilityChecks
    repeatability: FourGateDeterministicRepeatability
    development_fixture_exclusion: Literal[DEVELOPMENT_FIXTURE_EXCLUSION] = (
        DEVELOPMENT_FIXTURE_EXCLUSION
    )

    @model_validator(mode="after")
    def require_exact_successor_chain(self) -> Self:
        integrated = self.integrated_assessment
        package = self.decision_package.package
        if (
            integrated.metadata.integration_schema_version
            != self.contract.phase5_schema_version
            or integrated.metadata.phase1_contract_version
            != self.contract.phase1_contract_version
            or integrated.process_assessment.framework_id
            != self.contract.framework_id
            or integrated.process_assessment.framework_version
            != self.contract.framework_version
            or integrated.policy.policy_id != self.contract.decision_policy_id
            or integrated.policy.policy_version
            != self.contract.decision_policy_version
            or integrated.policy.decision_policy_fingerprint
            != self.contract.decision_policy_fingerprint
            or package.package_schema_version != self.contract.phase6_schema_version
            or package.source.integration_schema_version
            != self.contract.phase5_schema_version
            or package.source.phase1_contract_version
            != self.contract.phase1_contract_version
            or package.source.policy != integrated.policy
            or package.source.lineage != integrated.lineage
            or package.source.integrated_assessment_run_id
            != integrated.metadata.assessment_run_id
        ):
            raise ValueError("Cohort run contains a mixed successor contract chain")
        return self


class FourGateDevelopmentCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["four-gate-evaluation-case-result.v0.1"] = (
        "four-gate-evaluation-case-result.v0.1"
    )
    status: Literal["VALID_DEVELOPMENT_FIXTURE"] = "VALID_DEVELOPMENT_FIXTURE"
    manifest: FourGateDevelopmentCaseManifest
    run: FourGateCohortRun
    outcomes: list[OutcomeCode]
    not_evaluated_gate_count: int = Field(ge=0)
    total_gate_count: int = Field(ge=4)
    measures: list[FourGateMeasure]
    development_fixture_exclusion: Literal[DEVELOPMENT_FIXTURE_EXCLUSION] = (
        DEVELOPMENT_FIXTURE_EXCLUSION
    )

    @model_validator(mode="after")
    def require_case_identity_and_measure_states(self) -> Self:
        if self.run.case_id != self.manifest.case_id:
            raise ValueError("Case result identity does not match its run")
        if self.run.contract != self.manifest.contract:
            raise ValueError("Case result contract does not match its manifest")
        if self.run.source != self.manifest.source:
            raise ValueError("Case result source does not match its manifest")
        if self.run.approved_review != self.manifest.approved_review:
            raise ValueError("Case result review does not match its manifest")
        expected_outcomes = [
            item.outcome_code
            for item in self.run.decision_package.package.portfolio.items
        ]
        if self.outcomes != expected_outcomes:
            raise ValueError("Case outcomes must preserve the successor package")
        if self.total_gate_count != 4 * len(expected_outcomes):
            raise ValueError("Case gate denominator must include every gate slot")
        return self

    def canonical_json_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


class FourGateCohortManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["four-gate-evaluation-cohort-manifest.v0.1"] = (
        "four-gate-evaluation-cohort-manifest.v0.1"
    )
    cohort_id: str = Field(pattern=r"^four-gate-development-[a-z0-9-]+$")
    classification: Literal["SYNTHETIC_DEVELOPMENT_FIXTURES_ONLY"] = (
        "SYNTHETIC_DEVELOPMENT_FIXTURES_ONLY"
    )
    contract: FourGateCohortPin
    case_ids: list[str] = Field(min_length=1)
    real_world_cases: Literal[0] = 0
    reference_annotations: Literal[0] = 0
    reassessment_sub_studies: Literal[0] = 0
    development_fixture_exclusion: Literal[DEVELOPMENT_FIXTURE_EXCLUSION] = (
        DEVELOPMENT_FIXTURE_EXCLUSION
    )

    @model_validator(mode="after")
    def require_unique_development_cases(self) -> Self:
        if len(self.case_ids) != len(set(self.case_ids)):
            raise ValueError("Cohort cases must be unique")
        if any(not item.startswith("DEV-FG-") for item in self.case_ids):
            raise ValueError("Initial cohort accepts development fixtures only")
        return self


class FourGateCohortSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["four-gate-evaluation-cohort-summary.v0.1"] = (
        "four-gate-evaluation-cohort-summary.v0.1"
    )
    cohort: FourGateCohortManifest
    case_count: int = Field(ge=1)
    valid_development_fixture_count: int = Field(ge=1)
    excluded_from_real_world_claim_count: int = Field(ge=1)
    outcome_counts: dict[OutcomeCode, int]
    not_evaluated_gate_count: int = Field(ge=0)
    total_gate_count: int = Field(ge=4)
    measures: list[FourGateMeasure]
    disclosures: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def preserve_counts_and_exclusions(self) -> Self:
        if self.case_count != len(self.cohort.case_ids):
            raise ValueError("Summary case count does not match the cohort")
        if self.valid_development_fixture_count != self.case_count:
            raise ValueError("Initial cohort may contain only valid fixtures")
        if self.excluded_from_real_world_claim_count != self.case_count:
            raise ValueError("Every development fixture must remain claim-excluded")
        if sum(self.outcome_counts.values()) * 4 != self.total_gate_count:
            raise ValueError("Summary gate denominator must preserve all case outputs")
        if DEVELOPMENT_FIXTURE_EXCLUSION not in self.disclosures:
            raise ValueError("Summary must disclose the development-fixture exclusion")
        return self

    def canonical_json_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


class FourGateFreezeFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_length: int = Field(ge=1)


class FourGateCaseFreezeManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["four-gate-evaluation-freeze.v0.1"] = (
        "four-gate-evaluation-freeze.v0.1"
    )
    case_id: str = Field(pattern=r"^DEV-FG-[0-9]{3}$")
    classification: Literal["DEVELOPMENT_FIXTURE"] = "DEVELOPMENT_FIXTURE"
    immutable: Literal[True] = True
    before_state_only: Literal[True] = True
    contract: FourGateCohortPin
    source: FourGateSourcePin
    approved_review: FourGateApprovedReviewPin
    files: list[FourGateFreezeFile] = Field(min_length=4)
    development_fixture_exclusion: Literal[DEVELOPMENT_FIXTURE_EXCLUSION] = (
        DEVELOPMENT_FIXTURE_EXCLUSION
    )

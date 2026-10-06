"""Pure, deterministic evidence-guidance derivation for formal results.

This module deliberately consumes an already-completed immutable result.  It
does not invoke an adapter, engine, repository, provider, or language model.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import hashlib
import json

from pydantic import ValidationError

from ai_adoption_engine.models.formal_assessment import (
    FORMAL_ASSESSMENT_RESULT_SCHEMA,
    FORMAL_ASSESSMENT_RUN_STORE_ID,
    FORMAL_ASSESSMENT_RUN_STORE_VERSION,
    FORMAL_EVIDENCE_GUIDANCE_CATALOGUE,
    FORMAL_EVIDENCE_GUIDANCE_SCHEMA,
    FORMAL_GUIDANCE_CATALOGUE_FINGERPRINT,
    FORMAL_GUIDANCE_CATALOGUE_ID,
    FORMAL_INPUT_ADAPTER_ID,
    FORMAL_INPUT_ADAPTER_RULES_FINGERPRINT,
    FORMAL_INPUT_ADAPTER_RULES_ID,
    FORMAL_INPUT_ADAPTER_VERSION,
    FOUR_GATE_POLICY_FINGERPRINT,
    FormalAssessmentResult,
    FormalEvidenceGuidance,
    FormalEvidenceGuidanceItem,
)
from ai_adoption_engine.models.four_gate_assessment import EvidenceProblemCode


_BOUNDARY_NOTICE = (
    "Requested information is not evidence; uploading a document does not "
    "guarantee a successful outcome."
)
_DERIVATION = "DETERMINISTIC_CATALOGUE_ONLY_NO_LLM"


class FormalGuidanceFailureCode(StrEnum):
    """Closed outcomes for expected guidance-derivation failures."""

    INVALID_SOURCE_RESULT = "INVALID_SOURCE_RESULT"
    UNSUPPORTED_COMPATIBILITY_IDENTITY = "UNSUPPORTED_COMPATIBILITY_IDENTITY"
    CATALOGUE_IDENTITY_DRIFT = "CATALOGUE_IDENTITY_DRIFT"
    UNSUPPORTED_PROBLEM_CODE = "UNSUPPORTED_PROBLEM_CODE"
    CORRUPT_BLOCKING_GAP_TRACE = "CORRUPT_BLOCKING_GAP_TRACE"
    OUTPUT_VALIDATION_FAILED = "OUTPUT_VALIDATION_FAILED"


@dataclass(frozen=True)
class FormalGuidanceSuccess:
    guidance: FormalEvidenceGuidance


@dataclass(frozen=True)
class FormalGuidanceFailure:
    code: FormalGuidanceFailureCode
    message: str
    guidance: None = None


FormalGuidanceOutcome = FormalGuidanceSuccess | FormalGuidanceFailure


def _canonical_catalogue_fingerprint(catalogue: Mapping[object, object]) -> str:
    """Fingerprint a catalogue using the frozen-contract JSON convention."""

    payload = {
        str(getattr(key, "value", key)): value
        for key, value in catalogue.items()
    }
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _exact_catalogue(
    catalogue: Mapping[object, object],
    *,
    catalogue_id: str,
    catalogue_fingerprint: str,
) -> bool:
    if (
        catalogue_id != FORMAL_GUIDANCE_CATALOGUE_ID
        or catalogue_fingerprint != FORMAL_GUIDANCE_CATALOGUE_FINGERPRINT
    ):
        return False
    if _canonical_catalogue_fingerprint(catalogue) != catalogue_fingerprint:
        return False
    normalized = {
        str(getattr(key, "value", key)): value
        for key, value in catalogue.items()
    }
    expected = {
        code.value: text for code, text in FORMAL_EVIDENCE_GUIDANCE_CATALOGUE.items()
    }
    return normalized == expected


def _has_v0_1_identity(result: FormalAssessmentResult) -> bool:
    """Require every compatibility pin supported by this closed handler."""

    manifest = result.manifest
    projection = manifest.projection
    authorization = manifest.authorization
    identity = authorization.compatibility
    return (
        result.schema_version == FORMAL_ASSESSMENT_RESULT_SCHEMA
        and result.store_contract == FORMAL_ASSESSMENT_RUN_STORE_ID
        and manifest.store_contract == FORMAL_ASSESSMENT_RUN_STORE_ID
        and projection.schema_version == "formal-assessment-input-projection.v0.1"
        and projection.store_contract == FORMAL_ASSESSMENT_RUN_STORE_ID
        and authorization.store_contract == FORMAL_ASSESSMENT_RUN_STORE_ID
        and FORMAL_ASSESSMENT_RUN_STORE_VERSION == "0.1.0"
        and identity.adapter_id == FORMAL_INPUT_ADAPTER_ID
        and identity.adapter_version == FORMAL_INPUT_ADAPTER_VERSION
        and identity.adapter_rules_id == FORMAL_INPUT_ADAPTER_RULES_ID
        and identity.adapter_rules_fingerprint
        == FORMAL_INPUT_ADAPTER_RULES_FINGERPRINT
        and identity.framework_id == "four-gate-framework.v0.1"
        and identity.framework_version == "0.1"
        and identity.policy_id == "decision_policy.v0.3"
        and identity.policy_version == "0.3.0"
        and identity.policy_fingerprint == FOUR_GATE_POLICY_FINGERPRINT
        and identity.engine_id == "four-gate-assessment-engine.v0.1"
        and identity.engine_version == "0.1.0"
        and identity.engine_input_contract == "phase1-v0.4"
        and identity.output_contract == "phase1-v0.4"
        and identity.guidance_catalogue_id == FORMAL_GUIDANCE_CATALOGUE_ID
        and identity.guidance_catalogue_fingerprint
        == FORMAL_GUIDANCE_CATALOGUE_FINGERPRINT
    )


def _validated_result(source: object) -> FormalAssessmentResult | FormalGuidanceFailure:
    if not isinstance(source, FormalAssessmentResult):
        return FormalGuidanceFailure(
            FormalGuidanceFailureCode.INVALID_SOURCE_RESULT,
            "Guidance requires a completed FormalAssessmentResult.",
        )
    try:
        if not _has_v0_1_identity(source):
            return FormalGuidanceFailure(
                FormalGuidanceFailureCode.UNSUPPORTED_COMPATIBILITY_IDENTITY,
                "The Formal Assessment result uses an unsupported or mixed compatibility identity.",
            )
    except (AttributeError, TypeError):
        return FormalGuidanceFailure(
            FormalGuidanceFailureCode.INVALID_SOURCE_RESULT,
            "The supplied Formal Assessment result has an invalid frozen structure.",
        )
    # ``model_construct`` can bypass Pydantic's enum validation.  Diagnose that
    # one closed condition specifically before the mandatory full revalidation.
    # A normal public caller cannot reach this branch with an invalid result.
    try:
        raw_codes = tuple(
            gap.problem_code
            for activity in source.assessment.step_assessments
            for gap in activity.blocking_gaps
        )
    except (AttributeError, TypeError):
        raw_codes = ()
    if any(not isinstance(code, EvidenceProblemCode) for code in raw_codes):
        return FormalGuidanceFailure(
            FormalGuidanceFailureCode.UNSUPPORTED_PROBLEM_CODE,
            "A blocking gap uses a problem code unsupported by the frozen catalogue.",
        )
    try:
        trace_matches = all(
            tuple(activity.blocking_gaps)
            == tuple(gap for gate in activity.gate_results for gap in gate.blocking_gaps)
            for activity in source.assessment.step_assessments
        )
    except (AttributeError, TypeError):
        trace_matches = False
    if not trace_matches:
        return FormalGuidanceFailure(
            FormalGuidanceFailureCode.CORRUPT_BLOCKING_GAP_TRACE,
            "The result blocking-gap trace is not the exact ordered gate trace.",
        )
    try:
        result = FormalAssessmentResult.model_validate(source.model_dump(mode="python"))
    except (ValidationError, ValueError, TypeError):
        return FormalGuidanceFailure(
            FormalGuidanceFailureCode.INVALID_SOURCE_RESULT,
            "The supplied Formal Assessment result failed frozen integrity validation.",
        )
    if not _has_v0_1_identity(result):
        return FormalGuidanceFailure(
            FormalGuidanceFailureCode.UNSUPPORTED_COMPATIBILITY_IDENTITY,
            "The Formal Assessment result uses an unsupported or mixed compatibility identity.",
        )
    return result


def derive_formal_evidence_guidance(
    source_result: object,
    *,
    guidance_id: str,
    generated_at: datetime,
    catalogue: Mapping[object, object] = FORMAL_EVIDENCE_GUIDANCE_CATALOGUE,
    catalogue_id: str = FORMAL_GUIDANCE_CATALOGUE_ID,
    catalogue_fingerprint: str = FORMAL_GUIDANCE_CATALOGUE_FINGERPRINT,
) -> FormalGuidanceOutcome:
    """Derive frozen, catalogue-only guidance for one validated formal result.

    ``guidance_id`` and ``generated_at`` are explicit deterministic seams.  All
    expected failures are represented by a closed outcome and never return a
    partially derived guidance record.
    """

    result = _validated_result(source_result)
    if isinstance(result, FormalGuidanceFailure):
        return result
    try:
        exact_catalogue = _exact_catalogue(
            catalogue,
            catalogue_id=catalogue_id,
            catalogue_fingerprint=catalogue_fingerprint,
        )
    except (AttributeError, TypeError, ValueError):
        exact_catalogue = False
    if not exact_catalogue:
        return FormalGuidanceFailure(
            FormalGuidanceFailureCode.CATALOGUE_IDENTITY_DRIFT,
            "The evidence-guidance catalogue identity, fingerprint, or text drifted.",
        )

    source_pairs = tuple(
        (activity.step_id, gap)
        for activity in result.assessment.step_assessments
        for gap in activity.blocking_gaps
    )
    source_gaps = tuple(gap for _, gap in source_pairs)
    items: list[FormalEvidenceGuidanceItem] = []
    for activity_id, gap in source_pairs:
        try:
            requested_information = catalogue[gap.problem_code]
        except (KeyError, TypeError):
            return FormalGuidanceFailure(
                FormalGuidanceFailureCode.UNSUPPORTED_PROBLEM_CODE,
                "A blocking gap uses a problem code unsupported by the frozen catalogue.",
            )
        if (
            not isinstance(gap.problem_code, EvidenceProblemCode)
            or not isinstance(requested_information, str)
            or not requested_information
        ):
            return FormalGuidanceFailure(
                FormalGuidanceFailureCode.UNSUPPORTED_PROBLEM_CODE,
                "A blocking gap uses a problem code unsupported by the frozen catalogue.",
            )
        try:
            items.append(
                FormalEvidenceGuidanceItem(
                    activity_id=activity_id,
                    gate=gap.gate,
                    field_name=gap.field_name,
                    problem_code=gap.problem_code.value,
                    blocking_question=gap.blocking_question,
                    evidence_ids=tuple(gap.evidence_ids),
                    requested_information=requested_information,
                    boundary_notice=_BOUNDARY_NOTICE,
                )
            )
        except (ValidationError, ValueError, TypeError):
            return FormalGuidanceFailure(
                FormalGuidanceFailureCode.CORRUPT_BLOCKING_GAP_TRACE,
                "A blocking gap could not be preserved in its frozen guidance trace.",
            )
    try:
        guidance = FormalEvidenceGuidance(
            schema_version=FORMAL_EVIDENCE_GUIDANCE_SCHEMA,
            store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
            guidance_id=guidance_id,
            source_result=result,
            catalogue_id=catalogue_id,
            catalogue_fingerprint=catalogue_fingerprint,
            source_gaps=source_gaps,
            items=tuple(items),
            generated_at=generated_at,
            derivation=_DERIVATION,
        )
    except (ValidationError, ValueError, TypeError):
        return FormalGuidanceFailure(
            FormalGuidanceFailureCode.OUTPUT_VALIDATION_FAILED,
            "The completed guidance record failed frozen output validation.",
        )
    return FormalGuidanceSuccess(guidance)

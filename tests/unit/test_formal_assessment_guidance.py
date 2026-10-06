from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from ai_adoption_engine.formal.guidance import (
    FormalGuidanceFailure,
    FormalGuidanceFailureCode,
    FormalGuidanceSuccess,
    derive_formal_evidence_guidance,
)
from ai_adoption_engine.models.formal_assessment import (
    FORMAL_EVIDENCE_GUIDANCE_CATALOGUE,
    FORMAL_GUIDANCE_CATALOGUE_FINGERPRINT,
    FORMAL_GUIDANCE_CATALOGUE_ID,
    FormalAssessmentResult,
)
from ai_adoption_engine.models.four_gate_assessment import EvidenceProblemCode
from tests.unit.test_formal_assessment_models import NOW, formal_result


def _replace_first_gap_code(result: FormalAssessmentResult, code: EvidenceProblemCode):
    payload = result.model_dump(mode="json")
    payload["assessment"]["step_assessments"][0]["blocking_gaps"][0][
        "problem_code"
    ] = code.value
    payload["assessment"]["step_assessments"][0]["gate_results"][0][
        "blocking_gaps"
    ][0]["problem_code"] = code.value
    return FormalAssessmentResult.model_validate(payload)


@pytest.mark.parametrize("code", list(EvidenceProblemCode))
def test_guidance_uses_the_exact_frozen_catalogue_for_every_problem_code(code) -> None:
    result = _replace_first_gap_code(formal_result(), code)

    outcome = derive_formal_evidence_guidance(
        result, guidance_id="guidance-1", generated_at=NOW
    )

    assert isinstance(outcome, FormalGuidanceSuccess)
    guidance = outcome.guidance
    assert guidance.catalogue_id == FORMAL_GUIDANCE_CATALOGUE_ID
    assert guidance.catalogue_fingerprint == FORMAL_GUIDANCE_CATALOGUE_FINGERPRINT
    assert len(guidance.items) == len(guidance.source_gaps)
    first = guidance.items[0]
    source = guidance.source_gaps[0]
    assert (
        first.activity_id,
        first.gate,
        first.field_name,
        first.problem_code,
        first.blocking_question,
        first.evidence_ids,
    ) == (
        result.assessment.step_assessments[0].step_id,
        source.gate,
        source.field_name,
        source.problem_code.value,
        source.blocking_question,
        tuple(source.evidence_ids),
    )
    assert first.requested_information == FORMAL_EVIDENCE_GUIDANCE_CATALOGUE[code]
    assert first.boundary_notice == (
        "Requested information is not evidence; uploading a document does not "
        "guarantee a successful outcome."
    )


def test_guidance_is_repeatable_and_does_not_modify_the_source_result() -> None:
    result = formal_result()
    before = result.canonical_json_bytes()

    first = derive_formal_evidence_guidance(
        result, guidance_id="guidance-1", generated_at=NOW
    )
    second = derive_formal_evidence_guidance(
        result, guidance_id="guidance-1", generated_at=NOW
    )
    changed_timestamp = derive_formal_evidence_guidance(
        result, guidance_id="guidance-1", generated_at=NOW + timedelta(seconds=1)
    )

    assert isinstance(first, FormalGuidanceSuccess)
    assert isinstance(second, FormalGuidanceSuccess)
    assert isinstance(changed_timestamp, FormalGuidanceSuccess)
    assert first.guidance.canonical_json_bytes() == second.guidance.canonical_json_bytes()
    assert first.guidance.canonical_json_bytes() != changed_timestamp.guidance.canonical_json_bytes()
    assert result.canonical_json_bytes() == before


def test_guidance_rejects_catalogue_drift_and_invalid_sources_without_partial_output() -> None:
    drifted = dict(FORMAL_EVIDENCE_GUIDANCE_CATALOGUE)
    drifted[EvidenceProblemCode.UNKNOWN] = "Different wording"

    catalogue_failure = derive_formal_evidence_guidance(
        formal_result(),
        guidance_id="guidance-1",
        generated_at=NOW,
        catalogue=drifted,
    )
    source_failure = derive_formal_evidence_guidance(
        object(), guidance_id="guidance-1", generated_at=NOW
    )

    assert isinstance(catalogue_failure, FormalGuidanceFailure)
    assert catalogue_failure.code is FormalGuidanceFailureCode.CATALOGUE_IDENTITY_DRIFT
    assert catalogue_failure.guidance is None
    assert isinstance(source_failure, FormalGuidanceFailure)
    assert source_failure.code is FormalGuidanceFailureCode.INVALID_SOURCE_RESULT
    assert source_failure.guidance is None


def test_guidance_rejects_a_mixed_identity_before_deriving_any_item() -> None:
    result = formal_result()
    compatibility = result.manifest.authorization.compatibility.model_copy(
        update={"engine_version": "9.9.9"}
    )
    authorization = result.manifest.authorization.model_copy(
        update={"compatibility": compatibility}
    )
    mixed = result.model_copy(
        update={"manifest": result.manifest.model_copy(update={"authorization": authorization})}
    )

    outcome = derive_formal_evidence_guidance(
        mixed, guidance_id="guidance-1", generated_at=NOW
    )

    assert isinstance(outcome, FormalGuidanceFailure)
    assert outcome.code is FormalGuidanceFailureCode.UNSUPPORTED_COMPATIBILITY_IDENTITY
    assert outcome.guidance is None


def test_guidance_closes_corrupt_gap_traces_unknown_codes_and_invalid_output() -> None:
    result = formal_result()
    first_step = result.assessment.step_assessments[0]
    first_gate = first_step.gate_results[0]
    corrupt_trace = result.model_copy(
        update={
            "assessment": result.assessment.model_copy(
                update={
                    "step_assessments": [
                        first_step.model_copy(update={"blocking_gaps": []}),
                        *result.assessment.step_assessments[1:],
                    ]
                }
            )
        }
    )
    unsupported_gap = first_gate.blocking_gaps[0].model_copy(
        update={"problem_code": "FUTURE_CODE"}
    )
    unsupported_gate = first_gate.model_copy(update={"blocking_gaps": [unsupported_gap]})
    unsupported_step = first_step.model_copy(
        update={
            "gate_results": [unsupported_gate, *first_step.gate_results[1:]],
            "blocking_gaps": [unsupported_gap],
        }
    )
    unsupported_code = result.model_copy(
        update={
            "assessment": result.assessment.model_copy(
                update={
                    "step_assessments": [
                        unsupported_step,
                        *result.assessment.step_assessments[1:],
                    ]
                }
            )
        }
    )

    trace_failure = derive_formal_evidence_guidance(
        corrupt_trace, guidance_id="guidance-1", generated_at=NOW
    )
    code_failure = derive_formal_evidence_guidance(
        unsupported_code, guidance_id="guidance-1", generated_at=NOW
    )
    output_failure = derive_formal_evidence_guidance(
        result, guidance_id="guidance-1", generated_at=datetime(2026, 10, 5, 12, 0)
    )

    assert isinstance(trace_failure, FormalGuidanceFailure)
    assert trace_failure.code is FormalGuidanceFailureCode.CORRUPT_BLOCKING_GAP_TRACE
    assert isinstance(code_failure, FormalGuidanceFailure)
    assert code_failure.code is FormalGuidanceFailureCode.UNSUPPORTED_PROBLEM_CODE
    assert isinstance(output_failure, FormalGuidanceFailure)
    assert output_failure.code is FormalGuidanceFailureCode.OUTPUT_VALIDATION_FAILED

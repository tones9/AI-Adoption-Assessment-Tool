from __future__ import annotations

import hashlib
import json
from datetime import timedelta

import pytest

from ai_adoption_engine.models.formal_assessment import (
    FORMAL_ASSESSMENT_RESULT_SUPERSESSION_SCHEMA,
    FORMAL_ASSESSMENT_RUN_STATE_SCHEMA,
    FORMAL_ASSESSMENT_RUN_STORE_ID,
    FORMAL_EVIDENCE_GUIDANCE_CATALOGUE,
    FORMAL_EVIDENCE_GUIDANCE_SCHEMA,
    FORMAL_GUIDANCE_CATALOGUE_FINGERPRINT,
    FORMAL_GUIDANCE_CATALOGUE_ID,
    FormalAssessmentResultSupersession,
    FormalAssessmentRunState,
    FormalAssessmentTerminalFailure,
    FormalEvidenceGuidance,
    FormalEvidenceGuidanceItem,
    FormalRunFailureDetails,
    FormalRunOperation,
    FormalRunStatus,
)
from ai_adoption_engine.persistence.base import ArtifactCorruptionError
from ai_adoption_engine.persistence.formal_assessment_serialization import (
    FORMAL_ASSESSMENT_ADAPTERS,
    deserialize_formal_assessment_record,
    serialize_formal_assessment_record,
)
from tests.unit.test_formal_assessment_models import (
    NOW,
    authorization,
    choice,
    conflict_resolution,
    event,
    formal_result,
    manifest,
    request,
    run_request,
    source_projection,
)


EXPECTED_SCHEMAS = {
    "formal-assessment-input-choice.v0.1",
    "formal-input-conflict-resolution.v0.1",
    "formal-assessment-authorization.v0.1",
    "formal-assessment-input-projection.v0.1",
    "formal-assessment-run-request.v0.1",
    "formal-assessment-run-manifest.v0.1",
    "formal-assessment-run-event.v0.1",
    "formal-assessment-run-state.v0.1",
    "formal-assessment-result.v0.1",
    "formal-assessment-result-supersession.v0.1",
    "formal-evidence-guidance.v0.1",
}


def state():
    started = event(
        1,
        FormalRunOperation.START,
        FormalRunStatus.AUTHORIZED,
        FormalRunStatus.RUNNING,
    )
    return FormalAssessmentRunState(
        schema_version=FORMAL_ASSESSMENT_RUN_STATE_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        manifest=manifest(),
        events=(started,),
        current_status=FormalRunStatus.RUNNING,
        projected_at=NOW + timedelta(minutes=2),
    )


def terminal_failure():
    return FormalAssessmentTerminalFailure(
        schema_version="formal-assessment-result.v0.1",
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        terminal_record_id="terminal-failure-1",
        manifest=manifest(),
        status=FormalRunStatus.FAILED,
        failure=FormalRunFailureDetails(
            code="ENGINE_ERROR", message="The engine failed.", retryable=True
        ),
        occurred_at=NOW + timedelta(minutes=3),
    )


def supersession():
    return FormalAssessmentResultSupersession(
        schema_version=FORMAL_ASSESSMENT_RESULT_SUPERSESSION_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        supersession_id="supersession-1",
        formal_lifecycle_id="formal-1",
        superseded_result_id="result-1",
        successor_result_id="result-2",
        superseded_run_id="run-1",
        successor_run_id="run-2",
        predecessor_status=FormalRunStatus.COMPLETED_PENDING_REVIEW,
        successor_status=FormalRunStatus.COMPLETED_PENDING_REVIEW,
        rationale="A later explicit run completed successfully.",
        request=request("supersede"),
        superseded_at=NOW,
    )


def guidance():
    result = formal_result()
    pairs = tuple(
        (step.step_id, gap)
        for step in result.assessment.step_assessments
        for gap in step.blocking_gaps
    )
    return FormalEvidenceGuidance(
        schema_version=FORMAL_EVIDENCE_GUIDANCE_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        guidance_id="guidance-1",
        source_result=result,
        catalogue_id=FORMAL_GUIDANCE_CATALOGUE_ID,
        catalogue_fingerprint=FORMAL_GUIDANCE_CATALOGUE_FINGERPRINT,
        source_gaps=tuple(gap for _, gap in pairs),
        items=tuple(
            FormalEvidenceGuidanceItem(
                activity_id=activity_id,
                gate=gap.gate,
                field_name=gap.field_name,
                problem_code=gap.problem_code.value,
                blocking_question=gap.blocking_question,
                evidence_ids=tuple(gap.evidence_ids),
                requested_information=FORMAL_EVIDENCE_GUIDANCE_CATALOGUE[
                    gap.problem_code
                ],
                boundary_notice="Requested information is not evidence; uploading a document does not guarantee a successful outcome.",
            )
            for activity_id, gap in pairs
        ),
        generated_at=NOW,
        derivation="DETERMINISTIC_CATALOGUE_ONLY_NO_LLM",
    )


def all_records():
    started = event(
        1,
        FormalRunOperation.START,
        FormalRunStatus.AUTHORIZED,
        FormalRunStatus.RUNNING,
    )
    return (
        choice(),
        conflict_resolution(),
        authorization(),
        source_projection(),
        run_request(FormalRunOperation.AUTHORIZE),
        manifest(),
        started,
        state(),
        formal_result(),
        terminal_failure(),
        supersession(),
        guidance(),
    )


def test_exact_formal_assessment_serialization_registry_is_closed() -> None:
    assert set(FORMAL_ASSESSMENT_ADAPTERS) == EXPECTED_SCHEMAS


@pytest.mark.parametrize("record", all_records())
def test_every_persisted_contract_round_trips_with_deterministic_bytes(record) -> None:
    first = serialize_formal_assessment_record(record)
    second = serialize_formal_assessment_record(record)
    assert first == second
    assert hashlib.sha256(first[0].encode()).hexdigest() == first[1]
    assert deserialize_formal_assessment_record(record.schema_version, *first) == record


def test_unknown_mixed_noncanonical_and_hash_drift_fail_closed() -> None:
    record = choice()
    payload_json, payload_sha = serialize_formal_assessment_record(record)
    with pytest.raises(ArtifactCorruptionError, match="Unsupported"):
        deserialize_formal_assessment_record("formal-assessment-input-choice.v9", payload_json, payload_sha)
    with pytest.raises(ArtifactCorruptionError, match="integrity"):
        deserialize_formal_assessment_record(record.schema_version, payload_json, "0" * 64)

    noncanonical = json.dumps(json.loads(payload_json), indent=2, sort_keys=False)
    with pytest.raises(ArtifactCorruptionError, match="canonical"):
        deserialize_formal_assessment_record(
            record.schema_version,
            noncanonical,
            hashlib.sha256(noncanonical.encode()).hexdigest(),
        )

    mixed = record.model_copy(update={"schema_version": "formal-assessment-authorization.v0.1"})
    with pytest.raises(ArtifactCorruptionError, match="type"):
        serialize_formal_assessment_record(mixed)


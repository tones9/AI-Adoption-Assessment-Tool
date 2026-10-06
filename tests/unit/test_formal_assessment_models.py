from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_adoption_engine.application.fingerprints import fingerprint_business_process
from ai_adoption_engine.decision.four_gate_engine import FourGateAssessmentEngine
from ai_adoption_engine.decision.four_gate_policy import load_four_gate_policy
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.formal_assessment import (
    FORMAL_ASSESSMENT_AUTHORIZATION_SCHEMA,
    FORMAL_ASSESSMENT_INPUT_CHOICE_SCHEMA,
    FORMAL_ASSESSMENT_INPUT_PROJECTION_SCHEMA,
    FORMAL_ASSESSMENT_RESULT_SCHEMA,
    FORMAL_ASSESSMENT_RESULT_SUPERSESSION_SCHEMA,
    FORMAL_ASSESSMENT_RUN_EVENT_SCHEMA,
    FORMAL_ASSESSMENT_RUN_MANIFEST_SCHEMA,
    FORMAL_ASSESSMENT_RUN_REQUEST_SCHEMA,
    FORMAL_ASSESSMENT_RUN_STATE_SCHEMA,
    FORMAL_ASSESSMENT_RUN_STORE_ID,
    FORMAL_ASSESSMENT_RUN_STORE_VERSION,
    FORMAL_EVIDENCE_GUIDANCE_SCHEMA,
    FORMAL_EVIDENCE_GUIDANCE_CATALOGUE,
    FORMAL_GUIDANCE_CATALOGUE_FINGERPRINT,
    FORMAL_GUIDANCE_CATALOGUE_ID,
    FORMAL_INPUT_ADAPTER_ID,
    FORMAL_INPUT_ADAPTER_RULES_FINGERPRINT,
    FORMAL_INPUT_ADAPTER_RULES_ID,
    FORMAL_INPUT_ADAPTER_VERSION,
    FORMAL_INPUT_CONFLICT_RESOLUTION_SCHEMA,
    FOUR_GATE_POLICY_FINGERPRINT,
    ApprovedProcessAuthorizationPin,
    CompetingFormalValue,
    FormalAssessmentActivityProjection,
    FormalAssessmentAuthorization,
    FormalAssessmentCompatibilityIdentity,
    FormalAssessmentInputChoice,
    FormalAssessmentInputMode,
    FormalAssessmentInputProjection,
    FormalAssessmentResult,
    FormalAssessmentResultSupersession,
    FormalAssessmentRunEvent,
    FormalAssessmentRunManifest,
    FormalAssessmentRunRequest,
    FormalAssessmentRunState,
    FormalEvidenceGuidance,
    FormalEvidenceGuidanceItem,
    FormalEvidenceReferencePin,
    FormalFieldResolutionTrace,
    FormalInputConflictResolution,
    FormalMappingReferencePin,
    FormalResultActivityTrace,
    FormalRunFailureDetails,
    FormalRunLineage,
    FormalRunOperation,
    FormalRunRecoveryLineage,
    FormalRunStatus,
    FormalValueOrigin,
    ProjectedValueOrigin,
    SupportingDocumentRevisionPin,
    SupportingEvidenceCandidatePin,
    SupportingEvidenceDisposition,
    SupportingHistoryExclusion,
)
from ai_adoption_engine.models.formal_evidence import (
    FORMAL_EVIDENCE_FAMILY,
    REVIEWER_DECLARATION_SCHEMA,
    CapabilitySignalFormalTarget,
    CriterionFormalTarget,
    FormalEvidenceLineage,
    FormalTargetKind,
    HumanAccountabilityFormalTarget,
    RequestIdentity,
    ReviewerDeclaration,
)
from ai_adoption_engine.models.four_gate_assessment import CapabilitySignalName
from tests.fakes.review import approved_review


NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64
ROOT = Path(__file__).resolve().parents[2]


def sha(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def request(token: str, operation: FormalRunOperation | None = None) -> RequestIdentity:
    suffix = operation.value if operation else "domain"
    return RequestIdentity(
        request_token=token,
        canonical_request_sha256=sha({"token": token, "operation": suffix}),
    )


def reviewer() -> ReviewerDeclaration:
    return ReviewerDeclaration(
        schema_version=REVIEWER_DECLARATION_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        reviewer_display_name="Alex Reviewer",
        declared_organisational_role="Process owner",
        identity_and_authority_locally_declared_not_authenticated=True,
        declared_at=NOW,
    )


def lineage() -> FormalEvidenceLineage:
    approved = approved_review()
    process = approved.business_process
    source_id = process.evidence[0].source_id
    source_hash = source_id.removeprefix("doc-")
    return FormalEvidenceLineage(
        formal_lifecycle_schema="preliminary-formal-lifecycle.v0.1",
        formal_lifecycle_id="formal-1",
        journey_id="journey-1",
        source_assessment_id="assessment-1",
        approved_review_artifact_id="approved-review-1",
        approved_review_schema_version="phase4-v0.1",
        approved_review_revision=1,
        approved_review_payload_sha256=sha(approved.model_dump(mode="json")),
        source_document_id=source_id,
        source_document_sha256=source_hash,
        validated_process_id=process.process_id,
        validated_process_fingerprint=fingerprint_business_process(process),
    )


def run_lineage(run_id: str = "run-1") -> FormalRunLineage:
    return FormalRunLineage(
        formal_lifecycle_id="formal-1",
        authorization_id="authorization-1",
        projection_id="projection-1",
        run_id=run_id,
    )


def compatibility(**changes: object) -> FormalAssessmentCompatibilityIdentity:
    values: dict[str, object] = {
        "adapter_id": FORMAL_INPUT_ADAPTER_ID,
        "adapter_version": FORMAL_INPUT_ADAPTER_VERSION,
        "adapter_rules_id": FORMAL_INPUT_ADAPTER_RULES_ID,
        "adapter_rules_fingerprint": FORMAL_INPUT_ADAPTER_RULES_FINGERPRINT,
        "engine_input_contract": "phase1-v0.4",
        "framework_id": "four-gate-framework.v0.1",
        "framework_version": "0.1",
        "policy_id": "decision_policy.v0.3",
        "policy_version": "0.3.0",
        "policy_fingerprint": FOUR_GATE_POLICY_FINGERPRINT,
        "engine_id": "four-gate-assessment-engine.v0.1",
        "engine_version": "0.1.0",
        "formal_evidence_contract": "preliminary-formal-evidence.v0.1",
        "candidate_contract": "formal-input-candidate-set.v0.1",
        "readiness_contract": "formal-evidence-readiness.v0.1",
        "output_contract": "phase1-v0.4",
        "guidance_catalogue_id": FORMAL_GUIDANCE_CATALOGUE_ID,
        "guidance_catalogue_fingerprint": FORMAL_GUIDANCE_CATALOGUE_FINGERPRINT,
    }
    values.update(changes)
    return FormalAssessmentCompatibilityIdentity(**values)


def exclusion() -> SupportingHistoryExclusion:
    return SupportingHistoryExclusion(
        lineage=lineage(),
        supporting_history_head_id="supporting-head-3",
        supporting_history_head_sha256=HASH_A,
        current_documents=(
            SupportingDocumentRevisionPin(
                document_id="supporting-doc-1",
                document_content_sha256=HASH_B,
                metadata_revision_id="metadata-2",
            ),
        ),
        confirmation="EXCLUDE CURRENT SUPPORTING EVIDENCE FROM THIS RUN",
        declarant=reviewer(),
        rationale="Use only the approved current-state process for this attempt.",
        excluded_at=NOW,
        request=request("exclude"),
    )


def candidate_pin() -> SupportingEvidenceCandidatePin:
    return SupportingEvidenceCandidatePin(
        lineage=lineage(),
        supporting_history_head_id="supporting-head-3",
        supporting_history_head_sha256=HASH_A,
        candidate_set_id="candidate-1",
        candidate_set_payload_sha256=HASH_A,
        readiness_id="readiness-1",
        readiness_payload_sha256=HASH_B,
        readiness_candidate_set_id="candidate-1",
        readiness_candidate_set_payload_sha256=HASH_A,
        readiness_status="READY_TO_ATTEMPT",
    )


def choice(
    mode: FormalAssessmentInputMode = FormalAssessmentInputMode.APPROVED_PROCESS_ONLY,
    disposition: SupportingEvidenceDisposition = SupportingEvidenceDisposition.NO_SUPPORTING_HISTORY,
    **changes: object,
) -> FormalAssessmentInputChoice:
    values: dict[str, object] = {
        "schema_version": FORMAL_ASSESSMENT_INPUT_CHOICE_SCHEMA,
        "store_contract": FORMAL_ASSESSMENT_RUN_STORE_ID,
        "lineage": lineage(),
        "mode": mode,
        "supporting_evidence_disposition": disposition,
        "explicit_user_confirmation": True,
        "selected_at": NOW,
        "request": request("choice"),
    }
    if mode is FormalAssessmentInputMode.APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE:
        values["supporting_candidate"] = candidate_pin()
    if disposition is SupportingEvidenceDisposition.CURRENT_SUPPORTING_EVIDENCE_EXPLICITLY_EXCLUDED:
        values["exclusion"] = exclusion()
    values.update(changes)
    return FormalAssessmentInputChoice(**values)


def authorization(
    input_choice: FormalAssessmentInputChoice | None = None,
    conflicts: tuple[FormalInputConflictResolution, ...] = (),
    rl: FormalRunLineage | None = None,
) -> FormalAssessmentAuthorization:
    rl = rl or run_lineage()
    return FormalAssessmentAuthorization(
        schema_version=FORMAL_ASSESSMENT_AUTHORIZATION_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        authorization_id=rl.authorization_id,
        run_lineage=rl,
        approved_process=ApprovedProcessAuthorizationPin(
            lineage=lineage(),
            source_extraction_run_id="phase4-fixture",
            approval_event_id="approval-5",
            approved_at=NOW,
        ),
        input_choice=input_choice or choice(),
        conflict_resolutions=conflicts,
        compatibility=compatibility(),
        explicit_run_confirmation="ATTEMPT ORGANISATIONAL ASSESSMENT",
        authorization_scope="ASSESSMENT_RUN_ATTEMPT_ONLY_NOT_APPROVAL_OR_IMPLEMENTATION_AUTHORITY",
        request=request("authorize"),
        authorized_at=NOW,
    )


def targets():
    yield from (
        CriterionFormalTarget(kind=FormalTargetKind.CRITERION, criterion=item)
        for item in CriterionName
    )
    yield HumanAccountabilityFormalTarget(
        kind=FormalTargetKind.HUMAN_ACCOUNTABILITY_REQUIRED
    )
    yield from (
        CapabilitySignalFormalTarget(
            kind=FormalTargetKind.CAPABILITY_SIGNAL, capability_signal=item
        )
        for item in CapabilitySignalName
    )


def path_for(step_id: str, target, prefix: str) -> str:
    base = f"{prefix}.steps[step_id={step_id}].characteristics"
    if target.kind is FormalTargetKind.CRITERION:
        return f"{base}.{target.criterion.value}"
    if target.kind is FormalTargetKind.HUMAN_ACCOUNTABILITY_REQUIRED:
        return f"{base}.human_accountability_required"
    return f"{base}.capability_signals.{target.capability_signal.value}"


def value_for(step, target):
    if target.kind is FormalTargetKind.CRITERION:
        return step.characteristics.criterion(target.criterion)
    if target.kind is FormalTargetKind.HUMAN_ACCOUNTABILITY_REQUIRED:
        return step.characteristics.human_accountability_required
    return getattr(step.characteristics.capability_signals, target.capability_signal.value)


def source_projection() -> FormalAssessmentInputProjection:
    approved = approved_review().business_process
    rl = run_lineage()
    activities = []
    evidence_by_id = {item.evidence_id: item for item in approved.evidence}
    for step in approved.steps:
        traces = []
        for target in targets():
            supplied = value_for(step, target)
            traces.append(
                FormalFieldResolutionTrace(
                    activity_id=step.step_id,
                    target=target,
                    approved_process_field_path=path_for(step.step_id, target, "approved_process"),
                    projected_field_path=path_for(step.step_id, target, "engine_input"),
                    approved_value=supplied.value,
                    approved_knowledge_state=supplied.knowledge_state,
                    projected_value=supplied.value,
                    projected_knowledge_state=supplied.knowledge_state,
                    projected_confidence=supplied.confidence,
                    origin=ProjectedValueOrigin.SOURCE_ONLY,
                    evidence_ids=tuple(supplied.evidence_ids),
                )
            )
        activities.append(
            FormalAssessmentActivityProjection(
                activity_id=step.step_id,
                sequence=step.sequence,
                engine_input=step,
                field_resolutions=tuple(traces),
                activity_evidence=tuple(evidence_by_id[item] for item in step.evidence_ids),
            )
        )
    return FormalAssessmentInputProjection(
        schema_version=FORMAL_ASSESSMENT_INPUT_PROJECTION_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        projection_id=rl.projection_id,
        run_lineage=rl,
        authorization=authorization(rl=rl),
        approved_process=approved,
        engine_input=approved,
        activities=tuple(activities),
        complete_evidence=tuple(approved.evidence),
    )


def run_request(operation: FormalRunOperation, rl: FormalRunLineage | None = None):
    rl = rl or run_lineage()
    return FormalAssessmentRunRequest(
        schema_version=FORMAL_ASSESSMENT_RUN_REQUEST_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        request=request(f"request-{operation.value}", operation),
        operation=operation,
        run_lineage=rl,
        canonical_operation_payload_sha256=sha(
            {"operation": operation.value, "run": rl.run_id}
        ),
        requested_at=NOW,
    )


def manifest() -> FormalAssessmentRunManifest:
    projection = source_projection()
    return FormalAssessmentRunManifest(
        schema_version=FORMAL_ASSESSMENT_RUN_MANIFEST_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        run_lineage=projection.run_lineage,
        attempt_number=1,
        authorization=projection.authorization,
        projection=projection,
        request=run_request(FormalRunOperation.AUTHORIZE),
        created_at=NOW,
    )


def event(
    sequence: int,
    operation: FormalRunOperation,
    before: FormalRunStatus,
    after: FormalRunStatus,
) -> FormalAssessmentRunEvent:
    projection = source_projection()
    return FormalAssessmentRunEvent(
        schema_version=FORMAL_ASSESSMENT_RUN_EVENT_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        event_id=f"event-{sequence}",
        sequence=sequence,
        run_lineage=projection.run_lineage,
        operation=operation,
        from_status=before,
        to_status=after,
        authorization_id=projection.authorization.authorization_id,
        projection_id=projection.projection_id,
        projection_fingerprint=projection.projection_fingerprint,
        failure=(
            FormalRunFailureDetails(
                code="ENGINE_ERROR", message="The engine failed.", retryable=True
            )
            if operation is FormalRunOperation.FAIL
            else None
        ),
        request=run_request(operation),
        occurred_at=NOW + timedelta(minutes=sequence),
    )


def test_contract_identity_catalogue_is_exact() -> None:
    assert FORMAL_ASSESSMENT_RUN_STORE_ID == "formal-assessment-run-store.v0.1"
    assert FORMAL_ASSESSMENT_RUN_STORE_VERSION == "0.1.0"
    assert {
        FORMAL_ASSESSMENT_INPUT_CHOICE_SCHEMA,
        FORMAL_ASSESSMENT_AUTHORIZATION_SCHEMA,
        FORMAL_INPUT_CONFLICT_RESOLUTION_SCHEMA,
        FORMAL_ASSESSMENT_INPUT_PROJECTION_SCHEMA,
        FORMAL_ASSESSMENT_RUN_MANIFEST_SCHEMA,
        FORMAL_ASSESSMENT_RUN_EVENT_SCHEMA,
        FORMAL_ASSESSMENT_RUN_STATE_SCHEMA,
        FORMAL_ASSESSMENT_RESULT_SCHEMA,
        FORMAL_ASSESSMENT_RESULT_SUPERSESSION_SCHEMA,
        FORMAL_ASSESSMENT_RUN_REQUEST_SCHEMA,
        FORMAL_EVIDENCE_GUIDANCE_SCHEMA,
    } == {
        "formal-assessment-input-choice.v0.1",
        "formal-assessment-authorization.v0.1",
        "formal-input-conflict-resolution.v0.1",
        "formal-assessment-input-projection.v0.1",
        "formal-assessment-run-manifest.v0.1",
        "formal-assessment-run-event.v0.1",
        "formal-assessment-run-state.v0.1",
        "formal-assessment-result.v0.1",
        "formal-assessment-result-supersession.v0.1",
        "formal-assessment-run-request.v0.1",
        "formal-evidence-guidance.v0.1",
    }


def test_process_only_mode_supports_absent_or_exactly_excluded_history() -> None:
    assert choice().supporting_candidate is None
    excluded = choice(
        disposition=SupportingEvidenceDisposition.CURRENT_SUPPORTING_EVIDENCE_EXPLICITLY_EXCLUDED
    )
    assert excluded.exclusion.current_documents[0].metadata_revision_id == "metadata-2"


def test_supporting_mode_requires_exact_ready_candidate() -> None:
    selected = choice(
        FormalAssessmentInputMode.APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE,
        SupportingEvidenceDisposition.CURRENT_SUPPORTING_EVIDENCE_INCLUDED,
    )
    assert selected.supporting_candidate.readiness_status == "READY_TO_ATTEMPT"
    assert selected.supporting_candidate.lineage == selected.lineage


@pytest.mark.parametrize(
    ("mode", "disposition", "candidate", "excluded"),
    [
        (
            FormalAssessmentInputMode.APPROVED_PROCESS_ONLY,
            SupportingEvidenceDisposition.CURRENT_SUPPORTING_EVIDENCE_INCLUDED,
            None,
            None,
        ),
        (
            FormalAssessmentInputMode.APPROVED_PROCESS_ONLY,
            SupportingEvidenceDisposition.NO_SUPPORTING_HISTORY,
            candidate_pin(),
            None,
        ),
        (
            FormalAssessmentInputMode.APPROVED_PROCESS_ONLY,
            SupportingEvidenceDisposition.CURRENT_SUPPORTING_EVIDENCE_EXPLICITLY_EXCLUDED,
            None,
            None,
        ),
        (
            FormalAssessmentInputMode.APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE,
            SupportingEvidenceDisposition.NO_SUPPORTING_HISTORY,
            candidate_pin(),
            None,
        ),
        (
            FormalAssessmentInputMode.APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE,
            SupportingEvidenceDisposition.CURRENT_SUPPORTING_EVIDENCE_INCLUDED,
            candidate_pin(),
            exclusion(),
        ),
    ],
)
def test_input_mode_mixed_fields_fail_closed(mode, disposition, candidate, excluded) -> None:
    with pytest.raises(ValidationError):
        choice(
            mode,
            disposition,
            supporting_candidate=candidate,
            exclusion=excluded,
        )


def test_choice_rejects_cross_lineage_candidate() -> None:
    pin = candidate_pin().model_copy(
        update={
            "lineage": candidate_pin().lineage.model_copy(
                update={"formal_lifecycle_id": "other"}
            )
        }
    )
    with pytest.raises(ValidationError, match="exact lineage"):
        choice(
            FormalAssessmentInputMode.APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE,
            SupportingEvidenceDisposition.CURRENT_SUPPORTING_EVIDENCE_INCLUDED,
            supporting_candidate=pin,
        )


def conflict_resolution(**changes: object) -> FormalInputConflictResolution:
    target = CriterionFormalTarget(
        kind=FormalTargetKind.CRITERION, criterion=CriterionName.BUSINESS_VALUE
    )
    source = CompetingFormalValue(
        lineage=lineage(),
        activity_id=approved_review().business_process.steps[0].step_id,
        target=target,
        origin=FormalValueOrigin.APPROVED_PROCESS,
        value=3,
        knowledge_state=KnowledgeState.KNOWN,
        approved_process_field_path="approved_process.steps[0].characteristics.business_value",
        evidence=(FormalEvidenceReferencePin(evidence_id="source-evidence", evidence_payload_sha256=HASH_A),),
    )
    supporting = CompetingFormalValue(
        lineage=lineage(),
        activity_id=source.activity_id,
        target=target,
        origin=FormalValueOrigin.SUPPORTING_MAPPING,
        value=5,
        knowledge_state=KnowledgeState.KNOWN,
        evidence=(FormalEvidenceReferencePin(evidence_id="supporting-evidence", evidence_payload_sha256=HASH_B),),
        supporting_mappings=(FormalMappingReferencePin(mapping_id="mapping-1", mapping_payload_sha256=HASH_A),),
    )
    values: dict[str, object] = {
        "schema_version": FORMAL_INPUT_CONFLICT_RESOLUTION_SCHEMA,
        "store_contract": FORMAL_ASSESSMENT_RUN_STORE_ID,
        "resolution_id": "resolution-1",
        "lineage": lineage(),
        "run_lineage": run_lineage(),
        "activity_id": source.activity_id,
        "target": target,
        "alternatives": (source, supporting),
        "selected_value": 5,
        "selected_knowledge_state": KnowledgeState.KNOWN,
        "reviewer": reviewer(),
        "explicit_human_selection": True,
        "rationale": "The current operational report is authoritative for this run.",
        "resolved_at": NOW,
        "request": request("resolve"),
    }
    values.update(changes)
    return FormalInputConflictResolution(**values)


def test_conflict_resolution_retains_all_alternatives_and_selection() -> None:
    resolution = conflict_resolution()
    assert len(resolution.alternatives) == 2
    assert resolution.selected_value == 5
    assert resolution.alternatives[1].supporting_mappings[0].mapping_id == "mapping-1"


def test_conflict_resolution_rejects_value_not_among_alternatives() -> None:
    with pytest.raises(ValidationError, match="one of the competing"):
        conflict_resolution(selected_value=4)


def test_identical_values_combine_provenance_without_resolution() -> None:
    original = conflict_resolution()
    duplicate = original.alternatives[1].model_copy(update={"value": 3})
    with pytest.raises(ValidationError, match="combine provenance"):
        conflict_resolution(
            alternatives=(original.alternatives[0], duplicate), selected_value=3
        )


def test_conflict_resolution_rejects_cross_lineage_alternative() -> None:
    original = conflict_resolution()
    other = original.alternatives[1].model_copy(
        update={
            "lineage": original.lineage.model_copy(
                update={"formal_lifecycle_id": "other"}
            )
        }
    )
    with pytest.raises(ValidationError, match="exact target and lineage"):
        conflict_resolution(alternatives=(original.alternatives[0], other))


def test_compatibility_identity_rejects_drift() -> None:
    with pytest.raises(ValidationError):
        compatibility(policy_fingerprint="f" * 64)
    with pytest.raises(ValidationError):
        compatibility(engine_input_contract="phase1-v0.3")


def test_authorization_is_attempt_only_and_source_mode_has_no_supporting_pins() -> None:
    item = authorization()
    assert item.authorization_scope.endswith("NOT_APPROVAL_OR_IMPLEMENTATION_AUTHORITY")
    assert item.input_choice.supporting_candidate is None
    assert item.compatibility.policy_fingerprint == FOUR_GATE_POLICY_FINGERPRINT


def test_source_only_authorization_rejects_conflict_resolutions() -> None:
    with pytest.raises(ValidationError, match="process-only"):
        authorization(conflicts=(conflict_resolution(),))


def test_projection_preserves_structure_unknowns_and_complete_inputs() -> None:
    projection = source_projection()
    assert projection.approved_process == projection.engine_input
    assert [item.activity_id for item in projection.activities] == [
        item.step_id for item in projection.approved_process.steps
    ]
    assert all(len(item.field_resolutions) == 21 for item in projection.activities)
    assert all(
        trace.projected_value is None
        and trace.projected_knowledge_state is KnowledgeState.UNKNOWN
        for item in projection.activities
        for trace in item.field_resolutions
    )
    assert len(projection.projection_fingerprint) == 64


def test_projection_is_byte_deterministic_and_fingerprint_is_content_derived() -> None:
    first = source_projection()
    second = source_projection()
    assert first.canonical_json_bytes() == second.canonical_json_bytes()
    assert first.projection_fingerprint == second.projection_fingerprint
    with pytest.raises(ValidationError, match="projection_fingerprint"):
        FormalAssessmentInputProjection.model_validate(
            {**first.model_dump(mode="json"), "projection_fingerprint": "f" * 64}
        )


def test_projection_rejects_structural_process_changes() -> None:
    projection = source_projection()
    changed = projection.engine_input.model_copy(deep=True)
    changed.steps[0].activity = "Changed activity"
    with pytest.raises(ValidationError, match="structure or order"):
        FormalAssessmentInputProjection.model_validate(
            {**projection.model_dump(mode="json"), "engine_input": changed.model_dump(mode="json"), "projection_fingerprint": None}
        )


def test_projection_rejects_unknown_to_zero_conversion_without_trace() -> None:
    projection = source_projection()
    changed = projection.engine_input.model_copy(deep=True)
    changed.steps[0].characteristics.business_value = changed.steps[0].characteristics.business_value.model_copy(
        update={"value": 0, "knowledge_state": KnowledgeState.KNOWN}
    )
    activities = list(projection.activities)
    activities[0] = activities[0].model_copy(
        update={"engine_input": changed.steps[0]}
    )
    with pytest.raises(ValidationError, match="field trace"):
        FormalAssessmentInputProjection.model_validate(
            {
                **projection.model_dump(mode="json"),
                "engine_input": changed.model_dump(mode="json"),
                "activities": [item.model_dump(mode="json") for item in activities],
                "projection_fingerprint": None,
            }
        )


def test_models_forbid_unknown_fields_and_non_utc_timestamps() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        FormalAssessmentInputChoice.model_validate(
            {**choice().model_dump(mode="json"), "unexpected": True}
        )
    payload = choice().model_dump(mode="json")
    payload["selected_at"] = "2026-10-05T12:00:00+05:30"
    with pytest.raises(ValidationError, match="explicit UTC"):
        FormalAssessmentInputChoice.model_validate(payload)


def test_manifest_pins_one_immutable_projection() -> None:
    item = manifest()
    assert item.initial_status is FormalRunStatus.AUTHORIZED
    assert item.projection.projection_fingerprint == source_projection().projection_fingerprint


def test_retry_requires_original_projection_and_mode() -> None:
    projection = source_projection()
    rl = projection.run_lineage
    recovery = FormalRunRecoveryLineage(
        run_id=rl.run_id,
        predecessor_attempt_number=1,
        authorization_id=projection.authorization.authorization_id,
        projection_id=projection.projection_id,
        projection_fingerprint=projection.projection_fingerprint,
        input_mode=projection.authorization.input_choice.mode,
    )
    retry = FormalAssessmentRunManifest(
        schema_version=FORMAL_ASSESSMENT_RUN_MANIFEST_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        run_lineage=rl,
        attempt_number=2,
        authorization=projection.authorization,
        projection=projection,
        recovery=recovery,
        request=run_request(FormalRunOperation.AUTHORIZE),
        created_at=NOW,
    )
    assert retry.recovery.projection_fingerprint == projection.projection_fingerprint
    with pytest.raises(ValidationError, match="original immutable projection"):
        FormalAssessmentRunManifest.model_validate(
            {
                **retry.model_dump(mode="json"),
                "recovery": {
                    **retry.recovery.model_dump(mode="json"),
                    "projection_fingerprint": "f" * 64,
                },
            }
        )


def test_run_event_state_machine_derives_contiguous_state() -> None:
    events = (
        event(1, FormalRunOperation.START, FormalRunStatus.AUTHORIZED, FormalRunStatus.RUNNING),
        event(2, FormalRunOperation.COMPLETE, FormalRunStatus.RUNNING, FormalRunStatus.COMPLETED_PENDING_REVIEW),
    )
    state = FormalAssessmentRunState(
        schema_version=FORMAL_ASSESSMENT_RUN_STATE_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        manifest=manifest(),
        events=events,
        current_status=FormalRunStatus.COMPLETED_PENDING_REVIEW,
        projected_at=NOW + timedelta(minutes=3),
    )
    assert state.current_status is FormalRunStatus.COMPLETED_PENDING_REVIEW


def test_invalid_run_transition_and_missing_failure_details_fail_closed() -> None:
    with pytest.raises(ValidationError, match="invalid formal run"):
        event(1, FormalRunOperation.COMPLETE, FormalRunStatus.AUTHORIZED, FormalRunStatus.COMPLETED_PENDING_REVIEW)
    failed = event(1, FormalRunOperation.FAIL, FormalRunStatus.RUNNING, FormalRunStatus.FAILED)
    with pytest.raises(ValidationError, match="exactly for"):
        FormalAssessmentRunEvent.model_validate(
            {**failed.model_dump(mode="json"), "failure": None}
        )


def test_run_state_rejects_non_contiguous_events() -> None:
    events = (
        event(1, FormalRunOperation.START, FormalRunStatus.AUTHORIZED, FormalRunStatus.RUNNING),
        event(2, FormalRunOperation.ABANDON, FormalRunStatus.INTERRUPTED, FormalRunStatus.ABANDONED),
    )
    with pytest.raises(ValidationError, match="chain"):
        FormalAssessmentRunState(
            schema_version=FORMAL_ASSESSMENT_RUN_STATE_SCHEMA,
            store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
            manifest=manifest(),
            events=events,
            current_status=FormalRunStatus.ABANDONED,
            projected_at=NOW,
        )


def formal_result() -> FormalAssessmentResult:
    projection = source_projection()
    policy = load_four_gate_policy(ROOT / "config/decision_policy.v0.3.json")
    assessment = FourGateAssessmentEngine(policy).assess(projection.engine_input)
    traces = tuple(
        FormalResultActivityTrace(
            activity_id=item.activity_id,
            projected_activity_path=f"activities[{index}]",
            assessment_activity_path=f"assessment.step_assessments[{index}]",
            projection_fingerprint=projection.projection_fingerprint,
            evidence_ids=tuple(item.engine_input.evidence_ids),
        )
        for index, item in enumerate(projection.activities)
    )
    return FormalAssessmentResult(
        schema_version=FORMAL_ASSESSMENT_RESULT_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        result_id="result-1",
        manifest=manifest(),
        assessment=assessment,
        activity_traces=traces,
        completed_at=NOW + timedelta(minutes=5),
    )


def test_result_wraps_existing_four_gate_output_without_approval() -> None:
    result = formal_result()
    assert result.customer_status == "Organisational assessment completed — review required"
    assert not result.implementation_approval_granted
    assert not result.decision_package_generated
    assert [item.step_id for item in result.assessment.step_assessments] == [
        item.activity_id for item in result.activity_traces
    ]


def test_result_rejects_missing_or_reordered_activity_trace() -> None:
    result = formal_result()
    with pytest.raises(ValidationError, match="exactly one ordered"):
        FormalAssessmentResult.model_validate(
            {**result.model_dump(mode="json"), "activity_traces": list(reversed(result.model_dump(mode="json")["activity_traces"]))}
        )


def test_result_rejects_engine_input_drift_from_projection() -> None:
    result = formal_result()
    payload = result.model_dump(mode="json")
    payload["assessment"]["step_assessments"][0]["criteria"][0]["rationale"] = (
        "Changed after projection."
    )
    with pytest.raises(ValidationError, match="criteria must exactly trace"):
        FormalAssessmentResult.model_validate(payload)


def test_supersession_accepts_only_distinct_successful_results() -> None:
    item = FormalAssessmentResultSupersession(
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
    assert item.formal_lifecycle_id == "formal-1"
    with pytest.raises(ValidationError, match="distinct"):
        FormalAssessmentResultSupersession.model_validate(
            {**item.model_dump(mode="json"), "successor_result_id": "result-1"}
        )


def test_guidance_is_exactly_derived_from_blocking_gaps_and_is_not_evidence() -> None:
    result = formal_result()
    pairs = tuple(
        (step.step_id, gap)
        for step in result.assessment.step_assessments
        for gap in step.blocking_gaps
    )
    items = tuple(
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
    )
    guidance = FormalEvidenceGuidance(
        schema_version=FORMAL_EVIDENCE_GUIDANCE_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        guidance_id="guidance-1",
        source_result=result,
        catalogue_id=FORMAL_GUIDANCE_CATALOGUE_ID,
        catalogue_fingerprint=FORMAL_GUIDANCE_CATALOGUE_FINGERPRINT,
        source_gaps=tuple(gap for _, gap in pairs),
        items=items,
        generated_at=NOW,
        derivation="DETERMINISTIC_CATALOGUE_ONLY_NO_LLM",
    )
    assert guidance.modifies_engine_result is False
    with pytest.raises(ValidationError, match="preserve"):
        FormalEvidenceGuidance.model_validate(
            {
                **guidance.model_dump(mode="json"),
                "items": [
                    {
                        **guidance.items[0].model_dump(mode="json"),
                        "blocking_question": "Changed",
                    },
                    *[
                        item.model_dump(mode="json")
                        for item in guidance.items[1:]
                    ],
                ],
            }
        )

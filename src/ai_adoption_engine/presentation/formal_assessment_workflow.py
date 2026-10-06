"""Explicit, default-off Organisational Assessment controller.

The controller mechanically builds only the frozen Slice 1 records and delegates
execution, recovery, and supersession to ``FormalAssessmentRunService``.  It
never invokes the strict engine, policy loader, or a projection algorithm
itself; conflicts are read through the adapter's public read-only preflight.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

import streamlit as st

from ai_adoption_engine.formal.guidance import (
    FormalGuidanceSuccess,
    derive_formal_evidence_guidance,
)
from ai_adoption_engine.formal.input_adapter import (
    FormalInputConflictPreflight,
    formal_assessment_compatibility_identity,
)
from ai_adoption_engine.formal.run_service import (
    FormalRunCompleted,
    FormalRunFailureCode,
    FormalRunPreRunRejection,
    FormalRunRecoveryRequired,
    FormalRunTerminalFailure,
)
from ai_adoption_engine.models.formal_assessment import (
    FORMAL_ASSESSMENT_AUTHORIZATION_SCHEMA,
    FORMAL_ASSESSMENT_INPUT_CHOICE_SCHEMA,
    FORMAL_ASSESSMENT_RUN_STORE_ID,
    ApprovedProcessAuthorizationPin,
    CompetingFormalValue,
    FormalAssessmentAuthorization,
    FormalAssessmentInputChoice,
    FormalAssessmentInputMode,
    FormalAssessmentResult,
    FormalAssessmentTerminalFailure,
    FormalInputConflictResolution,
    FormalRunLineage,
    FormalRunStatus,
    FormalValueOrigin,
    SupportingDocumentRevisionPin,
    SupportingEvidenceCandidatePin,
    SupportingEvidenceDisposition,
    SupportingHistoryExclusion,
)
from ai_adoption_engine.models.formal_assessment_adapter import FormalInputAdapterFailure
from ai_adoption_engine.models.formal_evidence import (
    FORMAL_EVIDENCE_FAMILY,
    REVIEWER_DECLARATION_SCHEMA,
    FormalTargetKind,
    ReadinessStatus,
    RequestIdentity,
    ReviewerDeclaration,
)
from ai_adoption_engine.persistence.base import ArtifactNotFoundError
from ai_adoption_engine.persistence.formal_evidence_serialization import (
    serialize_formal_evidence_record,
)
from ai_adoption_engine.presentation.formal_assessment_result import (
    FormalAssessmentPresentationError,
    present_formal_assessment_result,
)
from ai_adoption_engine.presentation.formal_assessment_ui import (
    clear_formal_assessment_action_token,
    formal_assessment_action_token,
    formal_assessment_services,
)
from ai_adoption_engine.presentation.supporting_evidence_ui import (
    supporting_evidence_ui_enabled,
)
from ai_adoption_engine.presentation.supporting_evidence_workflow import (
    render_supporting_evidence_workflow,
)


EXCLUSION_CONFIRMATION = "EXCLUDE CURRENT SUPPORTING EVIDENCE FROM THIS RUN"
RUN_CONFIRMATION = "ATTEMPT ORGANISATIONAL ASSESSMENT"
PROCESS_ONLY_LABEL = "Continue with current document"
SUPPORTING_LABEL = "Add/use supporting evidence"
SUPERSESSION_RATIONALE = (
    "A later explicitly authorized Organisational Assessment attempt completed "
    "successfully for this formal lifecycle. Supersession records currency only; "
    "it is not formal approval or implementation authority."
)
_DRAFT_KEY = "formal_assessment_pending_drafts"
_NOTICE_KEY = "formal_assessment_notices"

_STATUS_LABELS = {
    FormalRunStatus.AUTHORIZED: "Authorized — not started",
    FormalRunStatus.RUNNING: "Running — not completed",
    FormalRunStatus.COMPLETED_PENDING_REVIEW: "Completed — review required",
    FormalRunStatus.FAILED: "Failed — no completed result was created",
    FormalRunStatus.INTERRUPTED: "Interrupted — explicit recovery required",
    FormalRunStatus.ABANDONED: "Abandoned",
    FormalRunStatus.RETRY_AVAILABLE: "Retry available",
    FormalRunStatus.STALE: "Stale",
    FormalRunStatus.SUPERSEDED: "Superseded",
}
_MODE_LABELS = {
    FormalAssessmentInputMode.APPROVED_PROCESS_ONLY: "Approved process only",
    FormalAssessmentInputMode.APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE: (
        "Approved process with supporting evidence"
    ),
}
_DISPOSITION_LABELS = {
    SupportingEvidenceDisposition.NO_SUPPORTING_HISTORY: "No supporting evidence history exists",
    SupportingEvidenceDisposition.CURRENT_SUPPORTING_EVIDENCE_INCLUDED: (
        "Current ready supporting evidence is included"
    ),
    SupportingEvidenceDisposition.CURRENT_SUPPORTING_EVIDENCE_EXPLICITLY_EXCLUDED: (
        "Current supporting evidence is explicitly excluded from this run only"
    ),
}
_ORIGIN_LABELS = {
    FormalValueOrigin.APPROVED_PROCESS: "Approved process",
    FormalValueOrigin.SUPPORTING_MAPPING: "Reviewed supporting evidence",
    FormalValueOrigin.CORROBORATED: "Approved process corroborated by reviewed supporting evidence",
}
_REJECTION_MESSAGES = {
    FormalRunFailureCode.ADAPTER_PROJECTION_REJECTED: (
        "The selected inputs or conflict resolutions no longer match the exact current "
        "approved process or supporting evidence. Review them and prepare a new attempt."
    ),
    FormalRunFailureCode.COMPATIBILITY_OR_POLICY_DRIFT: (
        "The assessment configuration could not be verified as the approved version. "
        "No assessment was run."
    ),
    FormalRunFailureCode.INVALID_APPROVED_REVIEW: (
        "The approved process could not be verified exactly. No assessment was run."
    ),
    FormalRunFailureCode.STALE_OR_CONFLICTING_REQUEST: (
        "This attempt no longer matches its saved request. Prepare a new attempt."
    ),
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _request(token: str, purpose: str) -> RequestIdentity:
    encoded = json.dumps(
        {"request_token": token, "purpose": purpose},
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return RequestIdentity(
        request_token=token,
        canonical_request_sha256=hashlib.sha256(encoded).hexdigest(),
    )


def _derived_id(kind: str, token: str) -> str:
    """Stable per pending action: identical across reruns, distinct per draft."""

    digest = hashlib.sha256(f"{kind}\x00{token}".encode("utf-8")).hexdigest()
    return f"formal-ui-{kind}-{digest[:32]}"


def _notify(lifecycle_id: str, level: str, message: str) -> None:
    st.session_state.setdefault(_NOTICE_KEY, {})[lifecycle_id] = (level, message)


def _render_notice(lifecycle_id: str) -> None:
    notice = st.session_state.get(_NOTICE_KEY, {}).pop(lifecycle_id, None)
    if notice is None:
        return
    level, message = notice
    getattr(st, level)(message)


def _declaration_inputs(prefix: str) -> tuple[str, str, bool]:
    name = st.text_input("Reviewer name", key=f"{prefix}-name").strip()
    role = st.text_input("Declared organisational role", key=f"{prefix}-role").strip()
    acknowledged = st.checkbox(
        "I acknowledge that this identity and authority are locally declared and not authenticated.",
        key=f"{prefix}-local-authority",
    )
    return name, role, acknowledged


def _declaration(name: str, role: str, declared_at: datetime) -> ReviewerDeclaration:
    return ReviewerDeclaration(
        schema_version=REVIEWER_DECLARATION_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        reviewer_display_name=name,
        declared_organisational_role=role,
        identity_and_authority_locally_declared_not_authenticated=True,
        declared_at=declared_at,
    )


@dataclass(frozen=True)
class _SupportingSnapshot:
    documents: tuple[object, ...]
    head_id: str | None
    head_sha256: str | None
    candidate: object | None
    readiness: object | None
    reviews: tuple[object, ...]
    ready: bool
    blocker: str | None


@dataclass
class _Draft:
    """One pending, not-yet-executed attempt held only in this session."""

    token: str
    lifecycle_id: str
    mode: FormalAssessmentInputMode
    authorization: FormalAssessmentAuthorization
    request: RequestIdentity
    candidate: object | None
    readiness: object | None
    reviews: tuple[object, ...]
    conflicts: tuple[tuple[CompetingFormalValue, ...], ...]
    excluded_filenames: tuple[str, ...] = ()
    resolutions: dict[int, FormalInputConflictResolution] = field(default_factory=dict)
    final_authorization: FormalAssessmentAuthorization | None = None


def _supporting_snapshot(bundle, lifecycle_id: str) -> _SupportingSnapshot:
    """Read exact migration-7 history without constructing provider services."""

    repository = bundle.evidence_repository
    documents = repository.current_documents(lifecycle_id)
    event = repository.latest_workflow_event(lifecycle_id)
    head_id = event.event_id if event is not None else None
    head_sha256 = serialize_formal_evidence_record(event)[1] if event is not None else None
    if not documents:
        return _SupportingSnapshot(
            (), head_id, head_sha256, None, None, (), False,
            "No supporting evidence has been added for this organisational assessment.",
        )
    if event is None:
        return _SupportingSnapshot(
            documents, None, None, None, None, (), False,
            "Supporting history could not be pinned safely.",
        )
    candidates = repository.candidate_sets_for_lifecycle(lifecycle_id)
    readiness_records = repository.readiness_for_lifecycle(lifecycle_id)
    if not candidates:
        return _SupportingSnapshot(
            documents, head_id, head_sha256, None, None, (), False,
            "Supporting evidence has not yet been reviewed, mapped, and prepared as an input set.",
        )
    candidate = candidates[-1]
    matching = [item for item in readiness_records if item.candidate_set == candidate]
    readiness = matching[-1] if matching else None
    if readiness is None or readiness.status is not ReadinessStatus.READY_TO_ATTEMPT:
        return _SupportingSnapshot(
            documents, head_id, head_sha256, candidate, readiness, (), False,
            "The prepared supporting evidence is not ready to attempt an assessment.",
        )
    try:
        repository.validate_candidate_current(candidate)
        reviews = tuple(
            repository.load_record(
                "supporting-evidence-review-revision.v0.1", item.review_revision_id
            )
            for item in candidate.current_reviews
        )
    except Exception:
        return _SupportingSnapshot(
            documents, head_id, head_sha256, candidate, readiness, (), False,
            "Supporting evidence has changed since it was prepared, or its review history cannot be verified.",
        )
    return _SupportingSnapshot(
        documents, head_id, head_sha256, candidate, readiness, reviews, True, None
    )


def _current_document_pins(bundle, lifecycle_id: str, documents: tuple[object, ...]):
    pins: list[SupportingDocumentRevisionPin] = []
    for document in documents:
        revisions = bundle.evidence_repository.metadata_revisions_for_document(
            lifecycle_id, document.document_id
        )
        if not revisions:
            raise ValueError("A current supporting document has no metadata revision")
        pins.append(
            SupportingDocumentRevisionPin(
                document_id=document.document_id,
                document_content_sha256=document.source_blob_sha256,
                metadata_revision_id=revisions[-1].revision_id,
            )
        )
    return tuple(pins)


def _choice(
    *,
    bundle,
    lineage,
    snapshot: _SupportingSnapshot,
    mode: FormalAssessmentInputMode,
    token: str,
    exclusion_declarant: tuple[str, str, bool],
    exclusion_rationale: str,
    exclusion_confirmation: str,
    selected_at: datetime,
) -> FormalAssessmentInputChoice:
    common = dict(
        schema_version=FORMAL_ASSESSMENT_INPUT_CHOICE_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        lineage=lineage,
        mode=mode,
        explicit_user_confirmation=True,
        selected_at=selected_at,
        request=_request(f"{token}:choice", "input-choice"),
    )
    if mode is FormalAssessmentInputMode.APPROVED_PROCESS_ONLY:
        if not snapshot.documents:
            return FormalAssessmentInputChoice(
                **common,
                supporting_evidence_disposition=SupportingEvidenceDisposition.NO_SUPPORTING_HISTORY,
            )
        name, role, acknowledged = exclusion_declarant
        if (
            snapshot.head_id is None
            or snapshot.head_sha256 is None
            or not name
            or not role
            or not acknowledged
            or exclusion_confirmation != EXCLUSION_CONFIRMATION
            or not exclusion_rationale.strip()
        ):
            raise ValueError("Exact supporting-history exclusion confirmation is required")
        exclusion = SupportingHistoryExclusion(
            lineage=lineage,
            supporting_history_head_id=snapshot.head_id,
            supporting_history_head_sha256=snapshot.head_sha256,
            current_documents=_current_document_pins(
                bundle, lineage.formal_lifecycle_id, snapshot.documents
            ),
            confirmation=EXCLUSION_CONFIRMATION,
            declarant=_declaration(name, role, selected_at),
            rationale=exclusion_rationale.strip(),
            excluded_at=selected_at,
            request=_request(f"{token}:exclude", "supporting-history-exclusion"),
        )
        return FormalAssessmentInputChoice(
            **common,
            supporting_evidence_disposition=(
                SupportingEvidenceDisposition.CURRENT_SUPPORTING_EVIDENCE_EXPLICITLY_EXCLUDED
            ),
            exclusion=exclusion,
        )
    if not snapshot.ready or snapshot.candidate is None or snapshot.readiness is None:
        raise ValueError("Exact ready supporting evidence is required for this mode")
    if snapshot.head_id is None or snapshot.head_sha256 is None:
        raise ValueError("Supporting history head cannot be pinned")
    candidate_sha = serialize_formal_evidence_record(snapshot.candidate)[1]
    readiness_sha = serialize_formal_evidence_record(snapshot.readiness)[1]
    pin = SupportingEvidenceCandidatePin(
        lineage=lineage,
        supporting_history_head_id=snapshot.head_id,
        supporting_history_head_sha256=snapshot.head_sha256,
        candidate_set_id=snapshot.candidate.candidate_set_id,
        candidate_set_payload_sha256=candidate_sha,
        readiness_id=snapshot.readiness.readiness_id,
        readiness_payload_sha256=readiness_sha,
        readiness_candidate_set_id=snapshot.candidate.candidate_set_id,
        readiness_candidate_set_payload_sha256=candidate_sha,
        readiness_status="READY_TO_ATTEMPT",
    )
    return FormalAssessmentInputChoice(
        **common,
        supporting_evidence_disposition=SupportingEvidenceDisposition.CURRENT_SUPPORTING_EVIDENCE_INCLUDED,
        supporting_candidate=pin,
    )


def _authorization(
    *,
    approved,
    lineage,
    choice: FormalAssessmentInputChoice,
    token: str,
    authorized_at: datetime,
    resolutions: tuple[FormalInputConflictResolution, ...] = (),
) -> FormalAssessmentAuthorization:
    run_lineage = FormalRunLineage(
        formal_lifecycle_id=lineage.formal_lifecycle_id,
        authorization_id=_derived_id("authorization", token),
        projection_id=_derived_id("projection", token),
        run_id=_derived_id("run", token),
    )
    approval_events = [
        item for item in approved.review.events if item.action.value == "approve"
    ]
    if len(approval_events) != 1:
        raise ValueError("The approved review must contain exactly one approval event")
    return FormalAssessmentAuthorization(
        schema_version=FORMAL_ASSESSMENT_AUTHORIZATION_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        authorization_id=run_lineage.authorization_id,
        run_lineage=run_lineage,
        approved_process=ApprovedProcessAuthorizationPin(
            lineage=lineage,
            source_extraction_run_id=approved.review.original_candidate.extraction_run_id,
            approval_event_id=approval_events[0].event_id,
            approved_at=approved.approval.approved_at,
        ),
        input_choice=choice,
        conflict_resolutions=resolutions,
        compatibility=formal_assessment_compatibility_identity(),
        explicit_run_confirmation=RUN_CONFIRMATION,
        authorization_scope=(
            "ASSESSMENT_RUN_ATTEMPT_ONLY_NOT_APPROVAL_OR_IMPLEMENTATION_AUTHORITY"
        ),
        request=_request(f"{token}:authorize", "authorization"),
        authorized_at=authorized_at,
    )


def _drafts() -> dict[str, _Draft]:
    return st.session_state.setdefault(_DRAFT_KEY, {})


def _discard_draft(lifecycle_id: str) -> None:
    draft = _drafts().pop(lifecycle_id, None)
    if draft is not None:
        clear_formal_assessment_action_token(f"attempt:{lifecycle_id}")


def _target_label(target) -> str:
    if target.kind is FormalTargetKind.CRITERION:
        return target.criterion.value.replace("_", " ").capitalize()
    if target.kind is FormalTargetKind.CAPABILITY_SIGNAL:
        return "Capability: " + target.capability_signal.value.replace("_", " ")
    if target.kind is FormalTargetKind.HUMAN_ACCOUNTABILITY_REQUIRED:
        return "Human accountability required"
    return "Activity evidence"


def _value_label(alternative: CompetingFormalValue) -> str:
    if alternative.value is None:
        value = "Unknown"
    elif isinstance(alternative.value, bool):
        value = "Yes" if alternative.value else "No"
    else:
        value = str(alternative.value)
    state = alternative.knowledge_state.value.lower()
    confidence = (
        "" if alternative.confidence is None else f", confidence {alternative.confidence:g}"
    )
    return f"{value} ({state}{confidence}) — {_ORIGIN_LABELS[alternative.origin]}"


def _activity_names(approved) -> dict[str, str]:
    return {item.step_id: item.activity for item in approved.business_process.steps}


def _render_conflicts(draft: _Draft, approved) -> bool:
    """Collect one explicit frozen human resolution per conflict; True when complete."""

    if not draft.conflicts:
        return True
    names = _activity_names(approved)
    st.markdown("#### Resolve conflicting values")
    st.write(
        "Reviewed values disagree for the fields below. Choose the effective value for this "
        "assessment run only. Nothing is selected automatically, and the approved process, "
        "mappings, reviews, and documents are never rewritten."
    )
    prefix = f"formal-conflict-{draft.authorization.authorization_id}"
    for index, alternatives in enumerate(draft.conflicts):
        exemplar = alternatives[0]
        with st.container(border=True):
            st.markdown(
                f"**{names.get(exemplar.activity_id, 'Activity')} — "
                f"{_target_label(exemplar.target)}**"
            )
            for alternative in alternatives:
                st.caption(
                    f"{_value_label(alternative)}; {len(alternative.evidence)} evidence "
                    f"reference(s); {len(alternative.supporting_mappings)} supporting mapping(s)"
                )
            with st.expander("Provenance details"):
                for alternative in alternatives:
                    st.write(
                        f"{_value_label(alternative)} — evidence: "
                        + ", ".join(item.evidence_id for item in alternative.evidence)
                        + (
                            "; mappings: "
                            + ", ".join(item.mapping_id for item in alternative.supporting_mappings)
                            if alternative.supporting_mappings
                            else ""
                        )
                    )
            recorded = draft.resolutions.get(index)
            if recorded is not None:
                selected = next(
                    item
                    for item in alternatives
                    if (item.value, item.knowledge_state, item.confidence)
                    == (
                        recorded.selected_value,
                        recorded.selected_knowledge_state,
                        recorded.selected_confidence,
                    )
                )
                st.success(
                    f"Selected for this run: {_value_label(selected)} — recorded by "
                    f"{recorded.reviewer.reviewer_display_name} "
                    f"({recorded.reviewer.declared_organisational_role})."
                )
                if st.button("Change this selection", key=f"{prefix}-{index}-change"):
                    draft.resolutions.pop(index, None)
                    st.rerun()
                continue
            selected_index = st.radio(
                "Effective value for this run",
                options=list(range(len(alternatives))),
                index=None,
                format_func=lambda item, values=alternatives: _value_label(values[item]),
                key=f"{prefix}-{index}-selection",
            )
            name, role, acknowledged = _declaration_inputs(f"{prefix}-{index}")
            rationale = st.text_area(
                "Resolution rationale", key=f"{prefix}-{index}-rationale"
            ).strip()
            confirmed = st.checkbox(
                "I confirm this explicit human selection applies only to this assessment run.",
                key=f"{prefix}-{index}-confirm",
            )
            ready = (
                selected_index is not None
                and name
                and role
                and acknowledged
                and rationale
                and confirmed
            )
            if st.button(
                "Record conflict resolution",
                disabled=not ready,
                key=f"{prefix}-{index}-record",
            ):
                chosen = alternatives[selected_index]
                resolved_at = _utc_now()
                draft.resolutions[index] = FormalInputConflictResolution(
                    schema_version="formal-input-conflict-resolution.v0.1",
                    store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
                    resolution_id=_derived_id(f"resolution-{index}", draft.token),
                    lineage=exemplar.lineage,
                    run_lineage=draft.authorization.run_lineage,
                    activity_id=exemplar.activity_id,
                    target=exemplar.target,
                    alternatives=alternatives,
                    selected_value=chosen.value,
                    selected_knowledge_state=chosen.knowledge_state,
                    selected_confidence=chosen.confidence,
                    reviewer=_declaration(name, role, resolved_at),
                    explicit_human_selection=True,
                    rationale=rationale,
                    resolved_at=resolved_at,
                    request=_request(
                        f"{draft.token}:resolution:{index}", "conflict-resolution"
                    ),
                )
                st.rerun()
    return len(draft.resolutions) == len(draft.conflicts)


def _ensure_guidance(bundle, result: FormalAssessmentResult):
    """Load or derive-and-persist the exact Slice 5 guidance exactly once."""

    guidance_id = f"formal-guidance-{result.result_id}"
    try:
        return bundle.repository.load_evidence_guidance(guidance_id)
    except ArtifactNotFoundError:
        pass
    except Exception:
        st.warning("Information requested for a future attempt could not be read safely.")
        return None
    outcome = derive_formal_evidence_guidance(
        result,
        guidance_id=guidance_id,
        generated_at=result.completed_at,
    )
    if not isinstance(outcome, FormalGuidanceSuccess):
        st.warning("Information requested for a future attempt could not be derived safely.")
        return None
    try:
        return bundle.repository.append_evidence_guidance(
            outcome.guidance,
            request=_request(f"{guidance_id}:persist", "evidence-guidance"),
        ).record
    except Exception:
        st.warning("The assessment completed, but its requested-information guidance could not be saved safely.")
        return None


def _supersede_earlier_heads(bundle, result: FormalAssessmentResult) -> None:
    """Make one later successful explicit run current via Slice 4 only."""

    lifecycle_id = result.manifest.run_lineage.formal_lifecycle_id
    for head in bundle.repository.successful_result_heads(lifecycle_id):
        if head.result_id == result.result_id:
            continue
        bundle.runs.supersede_result(
            predecessor_result_id=head.result_id,
            successor_result_id=result.result_id,
            request=_request(
                f"formal-supersede:{head.result_id}:{result.result_id}",
                "result-supersession",
            ),
            rationale=SUPERSESSION_RATIONALE,
        )


def _finalize_completed(bundle, result: FormalAssessmentResult) -> None:
    _ensure_guidance(bundle, result)
    try:
        _supersede_earlier_heads(bundle, result)
    except Exception:
        st.warning("The completed result could not yet be recorded as current. It remains in history.")


def _handle_outcome(bundle, lifecycle_id: str, outcome) -> None:
    if isinstance(outcome, FormalRunCompleted):
        _finalize_completed(bundle, outcome.result)
        _notify(lifecycle_id, "success", "Organisational assessment completed — review required.")
    elif isinstance(outcome, FormalRunPreRunRejection):
        _notify(
            lifecycle_id,
            "warning",
            _REJECTION_MESSAGES.get(
                outcome.code,
                "The assessment was not started and nothing was saved. Review the inputs and prepare a new attempt.",
            ),
        )
    elif isinstance(outcome, FormalRunTerminalFailure):
        retry = (
            " A retry can be made available from the attempt history."
            if outcome.terminal_failure.failure.retryable
            else ""
        )
        _notify(
            lifecycle_id,
            "error",
            "No completed organisational assessment result was created." + retry,
        )
    elif isinstance(outcome, FormalRunRecoveryRequired):
        _notify(
            lifecycle_id,
            "warning",
            "This assessment attempt did not finish and needs an explicit recovery action. "
            "It will not be rerun automatically.",
        )


def _render_result(bundle, result: FormalAssessmentResult) -> None:
    guidance = _ensure_guidance(bundle, result)
    try:
        presentation = present_formal_assessment_result(result, guidance=guidance)
    except FormalAssessmentPresentationError:
        st.warning("The completed assessment could not be displayed safely.")
        return
    customer = presentation.customer
    st.success(customer.customer_status)
    st.caption(customer.non_approval_notice)
    st.write(f"**Process:** {customer.process_name}")
    st.write(f"**Input mode:** {customer.input_mode}")
    st.write(f"**Supporting evidence:** {customer.supporting_evidence_disposition}")
    for activity in customer.activities:
        with st.container(border=True):
            st.markdown(f"### {activity.name}")
            st.write(f"**Outcome:** {activity.outcome}")
            st.caption(
                f"Decision status: {activity.decision_status} · Change: "
                f"{activity.change_disposition} · Readiness: {activity.readiness_disposition} · "
                f"Intervention: {activity.selected_intervention_family} · Autonomy ceiling: "
                f"{activity.autonomy_ceiling}"
            )
            priority = activity.priority
            priority_text = f"Priority: {priority.status}"
            if priority.score is not None:
                priority_text += f" — score {priority.score:g}"
            if priority.band is not None:
                priority_text += f" ({priority.band})"
            st.caption(priority_text)
            for gate in activity.gates:
                st.markdown(f"**{gate.name}:** {gate.status} — {gate.decision}")
                st.write(gate.rationale)
                if gate.capabilities:
                    st.caption("Capabilities: " + ", ".join(gate.capabilities))
                for gap in gate.blocking_gaps:
                    st.write(f"- {gap.question}")
                    if gap.guidance is not None:
                        st.caption(
                            f"{gap.guidance.label}: {gap.guidance.requested_information}"
                        )
                        st.caption(gap.guidance.boundary_notice)
            if activity.capabilities:
                st.caption("Activity capabilities: " + ", ".join(activity.capabilities))
            if activity.activity_evidence is not None:
                st.caption(activity.activity_evidence)
            with st.expander("How the assessment inputs were sourced"):
                for item in activity.provenance:
                    st.write(
                        f"{item.field_name}: {item.projection_origin}; "
                        f"{item.knowledge_state}; {item.evidence_status}"
                    )
    with st.expander("Audit details", expanded=False):
        try:
            audit = present_formal_assessment_result(
                result, guidance=guidance, include_audit=True
            ).audit
        except FormalAssessmentPresentationError:
            st.warning("Audit details could not be displayed safely.")
            return
        st.json(audit.model_dump(mode="json") if audit is not None else {}, expanded=False)


def _is_stale(result: FormalAssessmentResult, snapshot: _SupportingSnapshot) -> bool:
    """A supporting-evidence result is stale when its exact candidate is no longer current."""

    pin = result.manifest.authorization.input_choice.supporting_candidate
    if pin is None:
        return False
    return not (
        snapshot.ready
        and snapshot.candidate is not None
        and snapshot.readiness is not None
        and snapshot.candidate.candidate_set_id == pin.candidate_set_id
        and snapshot.readiness.readiness_id == pin.readiness_id
    )


def _run_action(bundle, lifecycle_id: str, method, authorization, operation: str, **kwargs) -> None:
    attempt_key = f"{operation}:{authorization.authorization_id}:{kwargs.pop('attempt', 1)}"
    request = _request(formal_assessment_action_token(attempt_key), operation)
    try:
        outcome = method(authorization, request=request, **kwargs)
    except Exception:
        _notify(lifecycle_id, "error", "The recovery action could not be completed safely. Nothing was rerun.")
        st.rerun()
    _handle_outcome(bundle, lifecycle_id, outcome)
    st.rerun()


def _render_current_result(bundle, lifecycle_id: str, snapshot: _SupportingSnapshot) -> str | None:
    try:
        heads = bundle.repository.successful_result_heads(lifecycle_id)
    except Exception:
        st.warning("Completed assessment results could not be validated safely.")
        return None
    if not heads:
        return None
    current = heads[-1]
    st.subheader("Current organisational assessment result")
    if len(heads) > 1:
        st.warning(
            "More than one completed result is awaiting a currency record. The latest "
            "completed result is shown; earlier results remain in history."
        )
        if st.button("Record the latest completed result as current", key=f"supersede-{lifecycle_id}"):
            try:
                _supersede_earlier_heads(bundle, current)
            except Exception:
                _notify(lifecycle_id, "error", "The currency record could not be saved safely.")
            st.rerun()
    if _is_stale(current, snapshot):
        st.warning(
            "Stale: the supporting evidence used by this result has changed since it ran. "
            "The result remains unchanged; a new attempt is required to use the current evidence."
        )
    _render_result(bundle, current)
    return current.result_id


def _render_history(bundle, lifecycle_id: str, snapshot: _SupportingSnapshot, current_id: str | None) -> None:
    try:
        authorizations = bundle.repository.lifecycle_authorizations(lifecycle_id)
    except Exception:
        st.warning("Formal assessment history is unavailable because it could not be validated safely.")
        return
    if not authorizations:
        return
    st.subheader("Assessment attempt history")
    st.caption("Every attempt is kept as an immutable record. Nothing is deleted or overwritten.")
    for number, authorization in reversed(tuple(enumerate(authorizations, start=1))):
        try:
            history = bundle.repository.run_history(authorization.run_lineage.run_id)
        except Exception:
            st.warning("One historical assessment attempt could not be read safely.")
            continue
        status = history.states[-1].current_status if history.states else FormalRunStatus.AUTHORIZED
        attempt = history.manifests[-1].attempt_number if history.manifests else 1
        completed = next(
            (item for item in history.terminal_records if isinstance(item, FormalAssessmentResult)),
            None,
        )
        label = _STATUS_LABELS[status]
        if completed is not None and completed.result_id != current_id:
            label = "Superseded — kept as a historical result"
        elif completed is not None and _is_stale(completed, snapshot):
            label += " · Stale"
        mode = _MODE_LABELS[authorization.input_choice.mode]
        with st.container(border=True):
            st.markdown(f"**Attempt {number}** — {label}")
            st.caption(
                f"{mode}; authorized {authorization.authorized_at:%Y-%m-%d %H:%M} UTC"
                + (f"; retry attempt {attempt}" if attempt > 1 else "")
            )
            if completed is not None and completed.result_id != current_id:
                with st.expander("View historical result"):
                    _render_result(bundle, completed)
            key = authorization.authorization_id
            if status is FormalRunStatus.RUNNING:
                st.caption("If this attempt was interrupted, record that explicitly. It will not be rerun automatically.")
                if st.button("Mark attempt interrupted", key=f"interrupt-{key}"):
                    _run_action(bundle, lifecycle_id, bundle.runs.interrupt_running, authorization, "mark-interrupted", attempt=attempt)
            failure = next(
                (
                    item
                    for item in history.terminal_records
                    if isinstance(item, FormalAssessmentTerminalFailure)
                    and item.manifest.attempt_number == attempt
                ),
                None,
            )
            retry_permitted = status is FormalRunStatus.INTERRUPTED or (
                status is FormalRunStatus.FAILED
                and failure is not None
                and failure.failure.retryable
            )
            if retry_permitted and st.button("Make retry available", key=f"retry-available-{key}"):
                _run_action(bundle, lifecycle_id, bundle.runs.mark_retry_available, authorization, "mark-retry-available", attempt=attempt)
            if status is FormalRunStatus.RETRY_AVAILABLE:
                st.caption(
                    "Retry uses the original immutable inputs, input mode, and conflict resolutions. "
                    "To use newer evidence, prepare a new attempt instead."
                )
                if st.button("Retry with original inputs", key=f"retry-{key}"):
                    _run_action(bundle, lifecycle_id, bundle.runs.retry, authorization, "retry", attempt=attempt)
            if status in {
                FormalRunStatus.AUTHORIZED,
                FormalRunStatus.INTERRUPTED,
                FormalRunStatus.RETRY_AVAILABLE,
            }:
                rationale = st.text_input(
                    "Reason for abandoning this attempt", key=f"abandon-reason-{key}"
                ).strip()
                if st.button(
                    "Abandon this attempt",
                    disabled=not rationale,
                    key=f"abandon-{key}",
                ):
                    _run_action(
                        bundle,
                        lifecycle_id,
                        bundle.runs.abandon,
                        authorization,
                        "abandon",
                        attempt=attempt,
                        rationale=rationale,
                    )


def _prepare_draft(
    *,
    bundle,
    lifecycle_id: str,
    lineage,
    approved,
    snapshot: _SupportingSnapshot,
    mode: FormalAssessmentInputMode,
    exclusion_declarant: tuple[str, str, bool],
    exclusion_rationale: str,
    exclusion_confirmation: str,
) -> _Draft | str:
    _discard_draft(lifecycle_id)
    token = formal_assessment_action_token(f"attempt:{lifecycle_id}")
    created_at = _utc_now()
    try:
        choice = _choice(
            bundle=bundle,
            lineage=lineage,
            snapshot=snapshot,
            mode=mode,
            token=token,
            exclusion_declarant=exclusion_declarant,
            exclusion_rationale=exclusion_rationale,
            exclusion_confirmation=exclusion_confirmation,
            selected_at=created_at,
        )
        authorization = _authorization(
            approved=approved,
            lineage=lineage,
            choice=choice,
            token=token,
            authorized_at=created_at,
        )
    except Exception:
        clear_formal_assessment_action_token(f"attempt:{lifecycle_id}")
        return (
            "The assessment attempt could not be prepared. Complete every required "
            "declaration and confirmation, and check that the evidence is current."
        )
    conflicts: tuple[tuple[CompetingFormalValue, ...], ...] = ()
    if mode is FormalAssessmentInputMode.APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE:
        preflight = bundle.adapter.preflight_conflicts(
            authorization=authorization,
            approved_review=approved,
            candidate_set=snapshot.candidate,
            readiness=snapshot.readiness,
            supporting_reviews=snapshot.reviews,
        )
        if isinstance(preflight, FormalInputAdapterFailure) or not isinstance(
            preflight, FormalInputConflictPreflight
        ):
            clear_formal_assessment_action_token(f"attempt:{lifecycle_id}")
            return "The current supporting inputs cannot be used safely with the approved process."
        conflicts = preflight.conflicts
    excluded = ()
    if choice.exclusion is not None:
        excluded = tuple(item.original_filename for item in snapshot.documents)
    draft = _Draft(
        token=token,
        lifecycle_id=lifecycle_id,
        mode=mode,
        authorization=authorization,
        request=_request(token, "run-organisational-assessment"),
        candidate=snapshot.candidate if choice.supporting_candidate is not None else None,
        readiness=snapshot.readiness if choice.supporting_candidate is not None else None,
        reviews=snapshot.reviews if choice.supporting_candidate is not None else (),
        conflicts=conflicts,
        excluded_filenames=excluded,
    )
    _drafts()[lifecycle_id] = draft
    return draft


def _render_final_review(bundle, draft: _Draft, approved) -> None:
    choice = draft.authorization.input_choice
    st.subheader("Review this assessment attempt")
    with st.container(border=True):
        st.write(f"**Approved process:** {approved.business_process.name}")
        st.caption(f"Approved {draft.authorization.approved_process.approved_at:%Y-%m-%d %H:%M} UTC")
        st.write(f"**Input mode:** {_MODE_LABELS[choice.mode]}")
        st.write(f"**Supporting evidence:** {_DISPOSITION_LABELS[choice.supporting_evidence_disposition]}")
        if choice.supporting_candidate is not None and draft.candidate is not None:
            st.caption(
                f"The exact prepared supporting-evidence input set ({len(draft.reviews)} reviewed "
                "item(s)) and its Ready to attempt record are pinned for this attempt."
            )
        if choice.exclusion is not None:
            st.caption(
                "Excluded from this run only: "
                + ", ".join(draft.excluded_filenames)
                + ". These documents and their history remain unchanged and available for a future run."
            )
        if draft.resolutions:
            names = _activity_names(approved)
            for resolution in draft.resolutions.values():
                st.caption(
                    f"Conflict resolved for {names.get(resolution.activity_id, 'activity')} — "
                    f"{_target_label(resolution.target)}: "
                    + next(
                        _value_label(item)
                        for item in resolution.alternatives
                        if (item.value, item.knowledge_state, item.confidence)
                        == (
                            resolution.selected_value,
                            resolution.selected_knowledge_state,
                            resolution.selected_confidence,
                        )
                    )
                )
        st.info(
            "This permits only an assessment attempt. A completed result requires review and "
            "is not formal approval or implementation authority. It may still return Discovery Required."
        )
    confirmed = st.checkbox(
        "I confirm I want to attempt the Organisational Assessment with these exact inputs. "
        "This does not approve the result or authorize implementation.",
        value=False,
        key=f"final-formal-confirm-{draft.authorization.authorization_id}",
    )
    col_run, col_cancel = st.columns(2)
    with col_cancel:
        if st.button("Discard this prepared attempt", key=f"discard-formal-{draft.authorization.authorization_id}"):
            _discard_draft(draft.lifecycle_id)
            st.rerun()
    with col_run:
        clicked = st.button(
            "Attempt Organisational Assessment",
            type="primary",
            disabled=not confirmed,
            key=f"run-formal-{draft.authorization.authorization_id}",
        )
    if not clicked:
        return
    if draft.final_authorization is None:
        try:
            draft.final_authorization = _authorization(
                approved=approved,
                lineage=draft.authorization.approved_process.lineage,
                choice=choice,
                token=draft.token,
                authorized_at=_utc_now(),
                resolutions=tuple(draft.resolutions[index] for index in sorted(draft.resolutions)),
            )
        except Exception:
            _discard_draft(draft.lifecycle_id)
            _notify(draft.lifecycle_id, "warning", "The assessment attempt could not be authorized safely. Prepare a new attempt.")
            st.rerun()
    try:
        outcome = bundle.runs.execute(
            draft.final_authorization,
            approved_review=approved,
            request=draft.request,
            candidate_set=draft.candidate,
            readiness=draft.readiness,
            supporting_reviews=draft.reviews,
        )
    except Exception:
        st.error(
            "The assessment attempt could not be confirmed safely. Pressing the button again "
            "replays the same attempt and never runs it twice."
        )
        return
    _discard_draft(draft.lifecycle_id)
    _handle_outcome(bundle, draft.lifecycle_id, outcome)
    st.rerun()


def render_formal_assessment_workflow(formal_lifecycle_id: str, approved_review: object) -> None:
    """Render the only formal-run product entry point (Organisational route)."""

    try:
        bundle = formal_assessment_services()
        lineage = bundle.evidence_repository.load_active_lineage(formal_lifecycle_id)
        snapshot = _supporting_snapshot(bundle, formal_lifecycle_id)
    except Exception:
        st.warning(
            "Organisational assessment is unavailable because its active lineage could not "
            "be verified safely, or this workspace is read-only."
        )
        return

    st.subheader("Organisational Assessment")
    st.write(
        "Supporting evidence is optional and never changes the approved process. An "
        "assessment attempt may still produce Discovery Required. Authorization permits only "
        "that attempt; a completed result remains review-required and grants neither formal "
        "approval nor implementation authority."
    )
    _render_notice(formal_lifecycle_id)
    current_id = _render_current_result(bundle, formal_lifecycle_id, snapshot)
    _render_history(bundle, formal_lifecycle_id, snapshot, current_id)

    st.subheader("Start a new assessment attempt" if current_id else "Choose assessment inputs")
    mode_value = st.radio(
        "Choose assessment inputs",
        options=(
            FormalAssessmentInputMode.APPROVED_PROCESS_ONLY,
            FormalAssessmentInputMode.APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE,
        ),
        index=None,
        format_func=lambda item: (
            PROCESS_ONLY_LABEL
            if item is FormalAssessmentInputMode.APPROVED_PROCESS_ONLY
            else SUPPORTING_LABEL
        ),
        key=f"formal-input-mode-{formal_lifecycle_id}",
    )
    if mode_value is None:
        return

    exclusion_declarant: tuple[str, str, bool] = ("", "", False)
    exclusion_rationale = ""
    exclusion_confirmation = ""
    if mode_value is FormalAssessmentInputMode.APPROVED_PROCESS_ONLY and snapshot.documents:
        st.warning(
            "Supporting evidence already exists for this assessment. It cannot be silently "
            "ignored: exclude it explicitly from this run, or choose to use it."
        )
        st.caption(
            "Documents to exclude from this run only: "
            + ", ".join(item.original_filename for item in snapshot.documents)
            + ". They are not deleted, superseded, hidden, or changed, and remain available for a future run."
        )
        exclusion_declarant = _declaration_inputs(f"exclude-{formal_lifecycle_id}")
        exclusion_rationale = st.text_area(
            "Why exclude the current supporting evidence from this run?",
            key=f"exclude-reason-{formal_lifecycle_id}",
        )
        exclusion_confirmation = st.text_input(
            f"Type {EXCLUSION_CONFIRMATION} to confirm",
            key=f"exclude-confirm-{formal_lifecycle_id}",
        ).strip()
    elif mode_value is FormalAssessmentInputMode.APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE:
        if not snapshot.ready:
            _discard_draft(formal_lifecycle_id)
            st.warning(snapshot.blocker or "Supporting evidence is not ready to use.")
            st.caption(
                "Finish and use the supporting evidence below, or choose "
                f"“{PROCESS_ONLY_LABEL}”"
                + (" and explicitly exclude the current supporting history for that run." if snapshot.documents else ".")
            )
            if supporting_evidence_ui_enabled():
                render_supporting_evidence_workflow(formal_lifecycle_id)
            else:
                st.info(
                    "Supporting-evidence upload and processing are not available in this deployment."
                )
            return
        st.caption(
            f"Ready supporting evidence is available ({len(snapshot.reviews)} reviewed item(s))."
        )

    draft = _drafts().get(formal_lifecycle_id)
    if draft is not None and draft.mode is not mode_value:
        draft = None
    if st.button("Prepare assessment attempt", key=f"prepare-formal-{formal_lifecycle_id}-{mode_value.value}"):
        prepared = _prepare_draft(
            bundle=bundle,
            lifecycle_id=formal_lifecycle_id,
            lineage=lineage,
            approved=approved_review,
            snapshot=snapshot,
            mode=mode_value,
            exclusion_declarant=exclusion_declarant,
            exclusion_rationale=exclusion_rationale,
            exclusion_confirmation=exclusion_confirmation,
        )
        if isinstance(prepared, str):
            st.warning(prepared)
            return
        st.rerun()
    if draft is None:
        return
    if not _render_conflicts(draft, approved_review):
        st.info("Record a resolution for every conflict before the attempt can be reviewed.")
        return
    _render_final_review(bundle, draft, approved_review)

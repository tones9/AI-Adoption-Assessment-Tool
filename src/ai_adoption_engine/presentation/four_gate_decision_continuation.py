"""Decision-first DCW presentation for four-gate baselines and reassessment."""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st

from ai_adoption_engine.application.four_gate_decision_continuation import (
    DecisionContinuationContractView,
)
from ai_adoption_engine.grw.four_gate_m2.models import (
    FourGateM2ActorDeclaration,
    FourGateM2ArtifactType,
    FourGateM2ConflictStatus,
    FourGateM2DocumentLocator,
    FourGateM2EvidencePermission,
    FourGateM2RunStage,
)
from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.presentation import labels
from ai_adoption_engine.presentation.components.decision_header import (
    HeaderSection,
    render_decision_header,
)
from ai_adoption_engine.presentation.components.status import guard
from ai_adoption_engine.presentation.components.technical_details import (
    technical_details,
)
from ai_adoption_engine.presentation.four_gate_narrative import (
    build_four_gate_package_narrative,
)


_STAGE_LABELS = {
    FourGateM2RunStage.OPEN: "Supporting document required",
    FourGateM2RunStage.DOCUMENT_SUBMITTED: "Human evidence review required",
    FourGateM2RunStage.EVIDENCE_REVIEWED: "Data-readiness resolution required",
    FourGateM2RunStage.RESOLUTION_PROPOSED: "Reassessment request required",
    FourGateM2RunStage.REQUESTED: "Explicit approval required",
    FourGateM2RunStage.APPROVED: "Successor review creation available",
    FourGateM2RunStage.SUCCESSOR_REVIEW_READY: "Successor assessment available",
    FourGateM2RunStage.ASSESSED: "Successor Decision Package available",
    FourGateM2RunStage.PACKAGE_READY: "Same-contract comparison available",
    FourGateM2RunStage.COMPARED: "Controlled reassessment complete",
    FourGateM2RunStage.EVIDENCE_REJECTED: "Evidence rejected — run stopped",
    FourGateM2RunStage.INSUFFICIENT: "Evidence insufficient — run stopped",
    FourGateM2RunStage.BLOCKED_CONFLICT: "Evidence conflict — run stopped",
    FourGateM2RunStage.STALE: "Baseline changed — run stopped",
    FourGateM2RunStage.FAILED: "Reassessment stopped",
}

_TERMINAL_STAGES = {
    FourGateM2RunStage.COMPARED,
    FourGateM2RunStage.EVIDENCE_REJECTED,
    FourGateM2RunStage.INSUFFICIENT,
    FourGateM2RunStage.BLOCKED_CONFLICT,
    FourGateM2RunStage.STALE,
    FourGateM2RunStage.FAILED,
}

_PERMISSION_LABELS = {
    FourGateM2EvidencePermission.REJECTED: "Reject for this question",
    FourGateM2EvidencePermission.INSUFFICIENT_FOR_THIS_USE: (
        "Record as insufficient for this question"
    ),
    FourGateM2EvidencePermission.CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE: (
        "Permit for data-readiness resolution"
    ),
}

_CONFLICT_LABELS = {
    FourGateM2ConflictStatus.CONSISTENT: "Consistent with the reviewed baseline",
    FourGateM2ConflictStatus.PARTIALLY_OVERLAPPING: "Partially overlapping",
    FourGateM2ConflictStatus.CONTRADICTORY: "Contradictory",
    FourGateM2ConflictStatus.DIFFERENT_SCOPE: "Different scope",
    FourGateM2ConflictStatus.STALE_OR_SUPERSEDED: "Stale or superseded",
    FourGateM2ConflictStatus.UNRESOLVED: "Unresolved",
}


def render_four_gate_decision_continuation(
    view: DecisionContinuationContractView,
    *,
    service=None,
    workspace_writable: bool = False,
) -> None:
    """Present the official baseline before any optional successor action."""

    baseline = view.successor_baseline
    if baseline is None:
        guard("The saved baseline contract could not be verified.")
    narrative = build_four_gate_package_narrative(baseline.package)
    continuation_available = (
        view.successor_continuation_available
        and workspace_writable
        and service is not None
    )
    availability = (
        "One controlled, same-contract reassessment is available for a "
        "recorded data-readiness question."
        if continuation_available
        else "This four-gate baseline is available for read-only review."
    )
    requirement = (
        "No. Reassessment is optional and every evidence, review, request, "
        "and approval step requires an explicit action."
        if continuation_available
        else "No. The assessment is complete and no eligible successor "
        "reassessment is available here."
    )
    render_decision_header(
        context_line=f"Current official decision · {narrative.process_name}",
        headline=narrative.headline,
        headline_heading="Your current official decision",
        headline_note=(
            "This decision remains the immutable official baseline. The "
            "optional path below cannot edit or replace it. "
            + narrative.completeness_statement
        ),
        sections=(
            HeaderSection("What your decision covers", narrative.outcome_groups),
            HeaderSection("What is available now", (availability,)),
            HeaderSection("Do you need to do anything?", (requirement,)),
        ),
    )
    if continuation_available:
        _render_current_decisions(baseline)
        _render_activation(view, service)
    else:
        _render_unavailable(view, workspace_writable)
        _render_current_decisions(baseline)
    _render_technical(baseline, service=service)


def _render_current_decisions(baseline) -> None:
    st.subheader("Current activity decisions")
    for decision in baseline.decisions:
        with st.container(border=True):
            st.markdown(f"**{decision.sequence}. {decision.activity}**")
            st.write(
                "Final outcome: "
                f"{labels.four_gate_outcome_label(decision.outcome_code)}"
            )
            st.caption(f"Decision status: {decision.decision_status}")
            st.markdown("**Four-gate status**")
            for gate in decision.gates:
                st.caption(
                    f"{labels.four_gate_name_label(gate.gate)} — "
                    f"{labels.four_gate_status_label(gate.status)}"
                )


def _render_unavailable(view, workspace_writable: bool) -> None:
    st.subheader("Continuation unavailable")
    if not workspace_writable:
        message = (
            "This is a protected read-only workspace. Its official decision can "
            "be reviewed, but no reassessment record or artifact can be created."
        )
    elif view.eligible_step_ids:
        message = (
            "The controlled successor service could not be opened safely. No "
            "reassessment action is available and the baseline is unchanged."
        )
    else:
        message = (
            "This baseline has no single active Gate 2 data-readiness question "
            "eligible for the controlled successor path. Other gaps remain "
            "read-only in this version."
        )
    st.info(
        "The current Gap Resolution Workspace M1 and M2 reassessment and "
        "comparison workflows are legacy-only. They are unavailable for this "
        "four-gate baseline. This is a workflow limitation, not an assessment error."
    )
    st.write(message)
    st.caption(
        "No legacy continuation can be started, resumed, created, persisted, "
        "routed, or compared from this baseline."
    )


def _render_activation(view, service) -> None:
    baseline = view.successor_baseline
    eligible = [
        decision
        for decision in baseline.decisions
        if decision.step_id in view.eligible_step_ids
    ]
    st.subheader("Optional controlled reassessment")
    st.write(
        "This path can answer one recorded data-readiness question using a "
        "reviewed plain-text document. A completed result is a separate "
        "same-contract decision; the official baseline above stays unchanged."
    )
    if len(eligible) == 1:
        target_step_id = eligible[0].step_id
        st.write(f"Activity: {eligible[0].activity}")
    else:
        target_step_id = st.selectbox(
            "Choose the eligible activity",
            [item.step_id for item in eligible],
            format_func=lambda step_id: next(
                item.activity for item in eligible if item.step_id == step_id
            ),
            key="four-gate-m2-target-step",
        )
    if service.open_context(baseline.assessment_id, target_step_id) is None:
        st.info(
            "The eligibility check no longer matches the saved baseline. No "
            "continuation action is available."
        )
        return
    runs = _matching_runs(
        service, baseline.assessment_id, target_step_id, baseline.package_id
    )
    selected = _select_run(runs)
    if selected is None:
        st.markdown("**Start when you are ready**")
        st.write(
            "Starting creates only a pinned reassessment record. It does not "
            "accept evidence, approve anything, or create a successor."
        )
        if st.button(
            "Start controlled reassessment",
            type="primary",
            key=f"four-gate-m2-start-{target_step_id}",
        ):
            try:
                manifest = service.create_run(baseline.assessment_id, target_step_id)
                st.session_state.four_gate_m2_run_id = manifest.run_id
                st.rerun()
            except Exception as exc:
                _action_error("The reassessment could not be started", exc)
        return

    run_id, record = selected
    stage = FourGateM2RunStage(record["stage"])
    st.session_state.four_gate_m2_run_id = run_id
    st.markdown(f"**Current step: {_STAGE_LABELS[stage]}**")
    st.caption(
        "Each button records only the step it names. Later steps never run "
        "automatically."
    )
    if stage in _TERMINAL_STAGES:
        _render_terminal(service, run_id, stage)
        return
    _render_stage_control(service, run_id, stage)


def _matching_runs(service, assessment_id: str, target_step_id: str, package_id: str):
    matches = []
    for record in service.repository.list_runs(assessment_id):
        reference = service.repository.load_artifact_reference(
            record["run_id"], FourGateM2ArtifactType.RUN_MANIFEST
        )
        if reference is None:
            continue
        manifest = service.repository.load_artifact(reference.artifact_id)
        if (
            manifest.target.step_id == target_step_id
            and manifest.baseline.package_id == package_id
        ):
            matches.append((manifest.run_id, record))
    return matches


def _select_run(runs):
    if not runs:
        return None
    run_ids = [run_id for run_id, _ in runs]
    selected_id = st.session_state.get("four_gate_m2_run_id")
    if selected_id not in run_ids:
        selected_id = run_ids[-1]
    if len(runs) > 1:
        selected_id = st.selectbox(
            "Choose a reassessment record",
            run_ids,
            index=run_ids.index(selected_id),
            key="four-gate-m2-existing-run",
            format_func=lambda value: f"Reassessment {run_ids.index(value) + 1}",
        )
    return next(item for item in runs if item[0] == selected_id)


def _actor(label: str, role: str, acknowledged: bool) -> FourGateM2ActorDeclaration:
    if not acknowledged:
        raise ValueError("Acknowledge that the role is locally declared")
    return FourGateM2ActorDeclaration(
        label=label,
        declared_role=role,
        acknowledged_local_role_limitation=acknowledged,
        declared_at=datetime.now(UTC),
    )


def _render_stage_control(service, run_id: str, stage: FourGateM2RunStage) -> None:
    if stage is FourGateM2RunStage.OPEN:
        _render_document_form(service, run_id)
    elif stage is FourGateM2RunStage.DOCUMENT_SUBMITTED:
        _render_evidence_review_form(service, run_id)
    elif stage is FourGateM2RunStage.EVIDENCE_REVIEWED:
        _render_resolution_form(service, run_id)
    elif stage is FourGateM2RunStage.RESOLUTION_PROPOSED:
        st.write(
            "Requesting records the proposed one-field reassessment. It does "
            "not approve it or create a successor."
        )
        if st.button("Request reassessment", key=f"four-gate-m2-request-{run_id}"):
            _run_action(
                "The reassessment request could not be recorded",
                lambda: service.request_reassessment(run_id),
            )
    elif stage is FourGateM2RunStage.REQUESTED:
        _render_approval_form(service, run_id)
    elif stage is FourGateM2RunStage.APPROVED:
        st.write(
            "Approval is recorded. Creating the successor review applies only "
            "the approved data-readiness evidence to a separate review record."
        )
        if st.button(
            "Create separate successor review",
            key=f"four-gate-m2-project-{run_id}",
        ):
            _run_action(
                "The successor review could not be created",
                lambda: service.build_successor_review(run_id),
            )
    elif stage is FourGateM2RunStage.SUCCESSOR_REVIEW_READY:
        st.write("Run the explicit four-gate assessment over the approved successor review.")
        if st.button(
            "Run successor assessment", key=f"four-gate-m2-assess-{run_id}"
        ):
            _run_action(
                "The successor assessment could not be completed",
                lambda: service.assess_successor(run_id),
            )
    elif stage is FourGateM2RunStage.ASSESSED:
        st.write("Create the separate successor Decision Package from that assessment.")
        if st.button(
            "Create successor Decision Package", key=f"four-gate-m2-package-{run_id}"
        ):
            _run_action(
                "The successor Decision Package could not be created",
                lambda: service.generate_successor_package(run_id),
            )
    elif stage is FourGateM2RunStage.PACKAGE_READY:
        st.write(
            "Record a typed comparison between two snapshots of the same "
            "four-gate contract. A difference is not an improvement claim."
        )
        if st.button(
            "Create same-contract comparison", key=f"four-gate-m2-compare-{run_id}"
        ):
            _run_action(
                "The same-contract comparison could not be created",
                lambda: service.compare(run_id),
            )


def _render_document_form(service, run_id: str) -> None:
    with st.form(f"four-gate-m2-document-{run_id}"):
        uploaded = st.file_uploader(
            "One UTF-8 plain-text supporting document",
            type=["txt"],
            key=f"four-gate-m2-upload-{run_id}",
        )
        source = st.text_input("Document source or authority")
        label = st.text_input("Document submitter name or label")
        role = st.text_input("Document submitter role")
        acknowledged = st.checkbox(
            "I understand this is a locally declared role, not verified authority."
        )
        submitted = st.form_submit_button("Submit document for human review")
    st.caption(
        "The document remains a candidate until a human reviewer explicitly "
        "records whether it may be used. Only UTF-8 .txt files are accepted."
    )
    if submitted:
        try:
            if uploaded is None:
                raise ValueError("Select one .txt document")
            service.submit_supporting_document(
                run_id,
                content_bytes=uploaded.getvalue(),
                filename=uploaded.name,
                source_label=source,
                submitter=_actor(label, role, acknowledged),
            )
            st.rerun()
        except Exception as exc:
            _action_error("The supporting document could not be recorded", exc)


def _render_evidence_review_form(service, run_id: str) -> None:
    submission = _artifact(service, run_id, FourGateM2ArtifactType.DOCUMENT_SUBMISSION)
    text = service.repository.load_document_bytes(submission.document.document_id).decode(
        "utf-8"
    )
    st.text_area("Submitted document", text, disabled=True)
    with st.form(f"four-gate-m2-review-{run_id}"):
        start = st.number_input("Evidence excerpt start character", min_value=0, value=0)
        end = st.number_input(
            "Evidence excerpt end character", min_value=1, value=len(text)
        )
        reviewer = st.text_input("Evidence reviewer name or label")
        role = st.text_input("Evidence reviewer role")
        acknowledged = st.checkbox(
            "I understand the reviewer role is locally declared, not verified authority."
        )
        scope = st.text_input("Evidence scope")
        period = st.text_input("Evidence period")
        authority = st.text_input("Source authority")
        applicability = st.text_area("Why this evidence applies to this activity")
        rationale = st.text_area("Why the excerpt supports data readiness")
        limitations = st.text_area("Limitations that remain")
        conflict = st.selectbox(
            "Relationship to the approved baseline evidence",
            list(FourGateM2ConflictStatus),
            index=None,
            format_func=lambda value: _CONFLICT_LABELS[value],
        )
        conflict_rationale = st.text_area("Conflict or consistency rationale")
        permission = st.selectbox(
            "Human evidence-review decision",
            list(FourGateM2EvidencePermission),
            index=None,
            format_func=lambda value: _PERMISSION_LABELS[value],
        )
        reviewed = st.form_submit_button("Record human evidence review")
    if reviewed:
        try:
            if conflict is None or permission is None:
                raise ValueError("Select the relationship and review decision")
            start_value, end_value = int(start), int(end)
            excerpt = text[start_value:end_value]
            locator = FourGateM2DocumentLocator(
                start_offset=start_value,
                end_offset=end_value,
                line_start=text.count("\n", 0, start_value) + 1,
                line_end=text.count("\n", 0, end_value) + 1,
                exact_excerpt=excerpt,
            )
            service.review_document_evidence(
                run_id,
                reviewer=_actor(reviewer, role, acknowledged),
                locator=locator,
                scope_statement=scope,
                period_statement=period,
                source_authority=authority,
                applicability_statement=applicability,
                semantic_rationale=rationale,
                limitations=limitations,
                conflict_status=conflict,
                conflict_rationale=conflict_rationale,
                permission=permission,
            )
            st.rerun()
        except Exception as exc:
            _action_error("The human evidence review could not be recorded", exc)


def _render_resolution_form(service, run_id: str) -> None:
    with st.form(f"four-gate-m2-resolution-{run_id}"):
        value = st.selectbox("Reviewed data-readiness value", [0, 1, 2, 3, 4, 5])
        rationale = st.text_area("Evidence-to-value mapping rationale")
        owner = st.text_input("Declared data owner name or label")
        owner_role = st.text_input("Declared data owner role")
        owner_ack = st.checkbox(
            "I understand the data-owner role is locally declared, not verified."
        )
        reviewer = st.text_input("Criterion reviewer name or label")
        reviewer_role = st.text_input("Criterion reviewer role")
        reviewer_ack = st.checkbox(
            "I understand the criterion-reviewer role is locally declared, not verified."
        )
        proposed = st.form_submit_button("Record proposed data-readiness resolution")
    if proposed:
        try:
            service.propose_data_readiness_resolution(
                run_id,
                proposed_value=int(value),
                proposed_knowledge_state=KnowledgeState.KNOWN,
                mapping_rationale=rationale,
                data_owner=_actor(owner, owner_role, owner_ack),
                criterion_reviewer=_actor(reviewer, reviewer_role, reviewer_ack),
            )
            st.rerun()
        except Exception as exc:
            _action_error("The data-readiness resolution could not be recorded", exc)


def _render_approval_form(service, run_id: str) -> None:
    with st.form(f"four-gate-m2-approval-{run_id}"):
        approver = st.text_input("Reassessment approver name or label")
        role = st.text_input("Reassessment approver role")
        rationale = st.text_area("Approval rationale")
        role_ack = st.checkbox(
            "I understand the approver role is locally declared, not verified authority."
        )
        explicit = st.checkbox(
            "I explicitly approve the one-field successor reassessment."
        )
        approved = st.form_submit_button("Approve successor reassessment")
    if approved:
        try:
            if not explicit:
                raise ValueError("Explicit reassessment approval is required")
            service.approve_reassessment(
                run_id,
                approver=_actor(approver, role, role_ack),
                rationale=rationale,
            )
            st.rerun()
        except Exception as exc:
            _action_error("The reassessment approval could not be recorded", exc)


def _run_action(message: str, action) -> None:
    try:
        action()
        st.rerun()
    except Exception as exc:
        _action_error(message, exc)


def _action_error(message: str, exc: Exception) -> None:
    st.error(f"{message}. Check the required information and try again.")
    with technical_details():
        st.caption(f"{type(exc).__name__}: {exc}")


def _artifact(service, run_id: str, artifact_type: FourGateM2ArtifactType):
    reference = service.repository.load_artifact_reference(run_id, artifact_type)
    if reference is None:
        raise ValueError(f"Missing {artifact_type.value}")
    return service.repository.load_artifact(reference.artifact_id)


def _render_terminal(service, run_id: str, stage: FourGateM2RunStage) -> None:
    if stage is FourGateM2RunStage.COMPARED:
        comparison = _artifact(
            service, run_id, FourGateM2ArtifactType.BASELINE_SUCCESSOR_COMPARISON
        )
        st.success("A separate, explicitly approved reassessment is complete.")
        original, successor = st.columns(2)
        with original.container(border=True):
            st.markdown("**Official baseline decision**")
            st.write(
                labels.four_gate_outcome_label(
                    comparison.baseline_decision.outcome_code
                )
            )
        with successor.container(border=True):
            st.markdown("**Separate successor decision**")
            st.write(
                labels.four_gate_outcome_label(
                    comparison.successor_decision.outcome_code
                )
            )
        st.caption(
            "These are two immutable snapshots of the same four-gate contract. "
            "A difference does not establish improvement, deployment readiness, "
            "implementation success, or Return on Investment (ROI)."
        )
    else:
        st.info(
            "This reassessment stopped at the human evidence-review boundary. "
            "No successor was created and the official baseline remains unchanged."
        )


def _render_technical(baseline, *, service=None) -> None:
    with technical_details():
        st.markdown("**Contract identity**")
        st.code(
            "\n".join(
                (
                    f"Assessment: {baseline.assessment_id}",
                    f"Immutable official baseline: {str(baseline.immutable).lower()}",
                    f"Framework: {baseline.framework_id} {baseline.framework_version}",
                    f"Decision contract: {baseline.phase1_contract_version}",
                    f"Integrated assessment schema: {baseline.phase5_schema_version}",
                    f"Decision Package schema: {baseline.phase6_schema_version}",
                    f"Decision policy: {baseline.policy_id} {baseline.policy_version}",
                    f"Decision policy status: {baseline.policy_status}",
                    f"Decision policy fingerprint: {baseline.policy_fingerprint}",
                    f"Baseline package ID: {baseline.package_id}",
                    f"Package completeness: {baseline.package_completeness}",
                )
            ),
            language=None,
        )
        st.markdown("**Baseline artifact identity and lineage**")
        for label, artifact in (
            ("Approved review", baseline.approved_review),
            ("Integrated assessment", baseline.integrated_assessment),
            ("Decision Package", baseline.decision_package),
        ):
            st.caption(
                f"{label}: {artifact.artifact_id} · revision "
                f"{artifact.artifact_revision} · {artifact.artifact_schema_version}"
            )
            st.caption(f"{label} SHA-256: {artifact.payload_sha256}")
            if artifact.parent_artifact_id is not None:
                st.caption(f"{label} parent: {artifact.parent_artifact_id}")
        st.markdown("**Typed baseline decisions**")
        for decision in baseline.decisions:
            st.code(_typed_decision_text(decision), language=None)
        if service is not None:
            _render_run_technical(service, baseline.assessment_id)


def _render_run_technical(service, assessment_id: str) -> None:
    records = service.repository.list_runs(assessment_id)
    if not records:
        return
    st.markdown("**Successor reassessment artifacts**")
    for record in records:
        run_id = record["run_id"]
        st.caption(f"Run: {run_id} · stage: {record['stage']}")
        for artifact_type in FourGateM2ArtifactType:
            reference = service.repository.load_artifact_reference(run_id, artifact_type)
            if reference is None:
                continue
            st.caption(
                f"{artifact_type.value}: {reference.artifact_id} · revision "
                f"{reference.artifact_revision} · SHA-256 {reference.payload_sha256}"
            )
        review_ref = service.repository.load_artifact_reference(
            run_id, FourGateM2ArtifactType.EVIDENCE_REVIEW
        )
        if review_ref is not None:
            review = service.repository.load_artifact(review_ref.artifact_id)
            locator = review.locator
            st.caption(
                "Evidence locator: characters "
                f"{locator.start_offset}–{locator.end_offset}; lines "
                f"{locator.line_start}–{locator.line_end}"
            )
        comparison_ref = service.repository.load_artifact_reference(
            run_id, FourGateM2ArtifactType.BASELINE_SUCCESSOR_COMPARISON
        )
        if comparison_ref is not None:
            comparison = service.repository.load_artifact(comparison_ref.artifact_id)
            st.markdown("**Typed same-contract comparison**")
            st.code(
                "\n".join(
                    (
                        "baseline:",
                        _typed_snapshot_text(comparison.baseline_decision),
                        "successor:",
                        _typed_snapshot_text(comparison.successor_decision),
                        "categories: " + ", ".join(comparison.categories),
                    )
                ),
                language=None,
            )


def _typed_decision_text(decision) -> str:
    return "\n".join(
        (
            f"step_id: {decision.step_id}",
            f"decision_status: {decision.decision_status}",
            f"change_disposition: {decision.change_disposition}",
            f"readiness_disposition: {decision.readiness_disposition}",
            f"selected_intervention_family: {decision.selected_intervention_family}",
            f"autonomy_ceiling: {decision.autonomy_ceiling}",
            f"outcome_code (derived): {decision.outcome_code}",
        )
    )


def _typed_snapshot_text(snapshot) -> str:
    return "\n".join(
        (
            f"decision_status: {snapshot.decision_status.value}",
            f"change_disposition: {snapshot.change_disposition.value}",
            f"readiness_disposition: {snapshot.readiness_disposition.value}",
            "selected_intervention_family: "
            f"{snapshot.selected_intervention_family.value}",
            f"autonomy_ceiling: {snapshot.autonomy_ceiling.value}",
            f"outcome_code: {snapshot.outcome_code.value}",
            "gate_results: "
            + ", ".join(
                f"{gate.gate.value}={gate.status.value}" for gate in snapshot.gate_results
            ),
            f"priority_status: {snapshot.priority_status.value}",
            f"priority_score: {snapshot.priority_score}",
        )
    )

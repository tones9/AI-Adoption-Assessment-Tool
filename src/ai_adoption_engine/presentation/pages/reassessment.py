"""Small native Streamlit surface for the one-document GRW M2 M1 path."""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st

from ai_adoption_engine.grw.m2.models import (
    M2ActorDeclaration,
    M2ArtifactType,
    M2ConflictStatus,
    M2DocumentLocator,
    M2EvidencePermission,
)
from ai_adoption_engine.persistence.base import PersistenceError
from ai_adoption_engine.persistence.reassessment import M2FrozenWorkspaceError
from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.presentation.context import (
    decision_continuation_service,
    hydrate_workspace,
    m2_reassessment_service,
    refresh_workspace,
    switch_to_registered_page,
)
from ai_adoption_engine.workspace.models import ArtifactType


def _actor(label: str, role: str) -> M2ActorDeclaration:
    return M2ActorDeclaration(
        label=label,
        declared_role=role,
        acknowledged_local_role_limitation=True,
        declared_at=datetime.now(UTC),
    )


def render() -> None:
    st.title("Reassess with supporting document")
    if st.button(
        "Return to decision continuation",
        key="grw-m2-return-dcw",
        icon=":material/arrow_back:",
    ):
        if not switch_to_registered_page("decision-continuation"):
            st.info("Open Decision continuation from the sidebar to return.")
    snapshot = hydrate_workspace()
    if snapshot is None:
        st.info("Open a package-ready assessment first.")
        return
    try:
        service = m2_reassessment_service()
    except M2FrozenWorkspaceError:
        st.warning(
            "Reassessment is unavailable for protected evaluation workspaces. "
            "The baseline remains immutable."
        )
        return
    context = service.open_m2_m1_context(snapshot.assessment.assessment_id)
    if context is None:
        st.info("No eligible UNKNOWN data-readiness question is available for this Decision Package.")
        return
    baseline, gap = context
    package = snapshot.active_artifacts[ArtifactType.DECISION_PACKAGE_RESULT].payload.package
    item = next(x for x in package.portfolio.items if x.step_id == gap.step_id)
    st.info("Your baseline Decision Package remains active. A separate reassessment is created only after reviewed evidence, a reviewed resolution, and explicit approval.")
    with st.container(border=True):
        st.caption(f"Baseline package: {baseline.package_id}")
        st.write(f"Baseline recommendation: {item.recommendation_mode.value} (existing baseline)")
        st.write(f"Activity: {gap.current_activity}")
        st.write("What information is documented about the data available for this activity? You may provide one current plain-text system description, data dictionary, or procedure that identifies relevant fields and limits.")
        st.caption("Do not include credentials, secrets, or unnecessary personal data. A .txt document is the only M2 M1 intake type.")

    run_id = st.session_state.get("dcw_selected_m2_run_id") or st.session_state.get(
        "grw_m2_run_id"
    )
    unavailable_selection = False
    if run_id is not None:
        try:
            resumable = decision_continuation_service().resumable_run(
                snapshot.assessment.assessment_id, run_id
            )
        except (PersistenceError, ValueError):
            resumable = None
        if resumable is None:
            st.session_state.pop("dcw_selected_m2_run_id", None)
            st.session_state.pop("grw_m2_run_id", None)
            st.warning(
                "The selected reassessment is unavailable for lifecycle actions. "
                "It is complete or stopped and can be inspected in Decision continuation."
            )
            run_id = None
            unavailable_selection = True
        else:
            st.session_state.grw_m2_run_id = resumable.run_id
            st.session_state.dcw_selected_m2_run_id = resumable.run_id
            run_id = resumable.run_id
    if unavailable_selection:
        return
    if run_id is None:
        with st.form("grw-m2-open-run"):
            opened = st.form_submit_button("Open reassessment", type="primary")
        if opened:
            try:
                run_id, _, _ = service.create_run(snapshot.assessment.assessment_id)
                st.session_state.grw_m2_run_id = run_id
                st.rerun()
            except Exception as exc:
                st.error(f"Reassessment could not be opened: {type(exc).__name__}")
        return

    run = service.repository.load_run(run_id)
    st.caption(f"Separate reassessment run: {run_id}; state: {run['stage']}")
    if run["stage"] == "OPEN":
        with st.form("grw-m2-document-submit"):
            uploaded = st.file_uploader("One supporting plain-text document", type=["txt"], key="grw-m2-document")
            source_label = st.text_input("Document source or authority", key="grw-m2-source")
            submitter = st.text_input("Your name or label", key="grw-m2-submitter")
            submitted = st.form_submit_button("Submit supporting document", type="primary")
        if submitted:
            try:
                if uploaded is None:
                    raise ValueError("Select one .txt document")
                service.submit_supporting_document(run_id, content_bytes=uploaded.getvalue(), filename=uploaded.name, source_label=source_label, submitter=_actor(submitter, "document submitter"))
                st.rerun()
            except Exception as exc:
                st.error(f"Document could not be submitted: {type(exc).__name__}")
        return
    if run["stage"] == "DOCUMENT_SUBMITTED":
        submission_ref = service.repository.load_artifact_reference(run_id, M2ArtifactType.DOCUMENT_SUBMISSION)
        submission = service.repository.load_artifact(submission_ref.artifact_id)
        text = service.repository.load_document_bytes(submission.document.document_id).decode("utf-8")
        st.text_area("Stored document (read-only)", value=text, disabled=True, key="grw-m2-document-preview")
        with st.form("grw-m2-evidence-review"):
            start = st.number_input("Excerpt start character", min_value=0, value=0, key="grw-m2-start")
            end = st.number_input("Excerpt end character", min_value=1, value=len(text), key="grw-m2-end")
            reviewer = st.text_input("Evidence reviewer", key="grw-m2-reviewer")
            scope = st.text_input("Same-activity scope statement", key="grw-m2-scope")
            period = st.text_input("Period or explicit limitation", key="grw-m2-period")
            authority = st.text_input("Source authority", key="grw-m2-authority")
            rationale = st.text_area("Semantic-support rationale", key="grw-m2-rationale")
            limitations = st.text_area("Limitations retained", key="grw-m2-limitations")
            outcome = st.selectbox("Evidence-review outcome", [item.value for item in M2EvidencePermission], index=None, placeholder="Select the reviewed outcome", key="grw-m2-evidence-outcome")
            conflict = st.selectbox("Relationship to baseline evidence", [item.value for item in M2ConflictStatus], index=None, placeholder="Select the reviewed relationship", key="grw-m2-conflict-status")
            conflict_rationale = st.text_area("Conflict or consistency rationale", key="grw-m2-conflict-rationale")
            reconciliation = st.text_area("Reviewer reconciliation for contradictory evidence, if applicable", key="grw-m2-reconciliation")
            applicability = st.text_area("Why stale/superseded evidence applies to this target scope, if applicable", key="grw-m2-applicability")
            reviewed = st.form_submit_button("Record document evidence review", type="primary")
        if reviewed:
            try:
                if outcome is None or conflict is None:
                    raise ValueError("Select both the evidence-review outcome and its relationship to baseline evidence")
                excerpt = text[int(start):int(end)]
                locator = M2DocumentLocator(start_offset=int(start), end_offset=int(end), line_start=text.count("\n", 0, int(start)) + 1, line_end=text.count("\n", 0, int(end)) + 1, exact_excerpt=excerpt)
                service.review_document_evidence(run_id, reviewer=_actor(reviewer, "evidence reviewer"), locator=locator, scope_statement=scope, period_statement=period, source_authority=authority, semantic_rationale=rationale, limitations=limitations, conflict_status=M2ConflictStatus(conflict), conflict_rationale=conflict_rationale, reconciliation_statement=reconciliation or None, applicability_statement=applicability or None, permission=M2EvidencePermission(outcome))
                st.rerun()
            except Exception as exc:
                st.error(f"Evidence review could not be recorded: {type(exc).__name__}")
        return
    if run["stage"] == "EVIDENCE_REVIEWED":
        with st.form("grw-m2-resolution"):
            value = st.selectbox("Reviewed data-readiness value (document-only M2 M1 allows 0–4)", [0, 1, 2, 3, 4], key="grw-m2-value")
            rationale = st.text_area("Instrument mapping rationale", key="grw-m2-mapping")
            narrowed_scope = st.text_area("Narrowed evidence scope, if the review recorded a scope conflict", key="grw-m2-narrowed-scope")
            owner_reconciliation = st.text_area("Data-owner reconciliation for contradictory evidence, if applicable", key="grw-m2-owner-reconciliation")
            owner = st.text_input("Declared data owner", key="grw-m2-owner")
            reviewer = st.text_input("Criterion reviewer", key="grw-m2-criterion-reviewer")
            proposed = st.form_submit_button("Record reviewed criterion resolution", type="primary")
        if proposed:
            try:
                service.propose_data_readiness_resolution(run_id, proposed_value=int(value), proposed_knowledge_state=KnowledgeState.KNOWN, mapping_rationale=rationale, narrowed_scope_statement=narrowed_scope or None, data_owner_reconciliation=owner_reconciliation or None, data_owner=_actor(owner, "data owner"), criterion_reviewer=_actor(reviewer, "criterion reviewer"))
                st.rerun()
            except Exception as exc:
                st.error(f"Criterion resolution could not be recorded: {type(exc).__name__}")
        return
    if run["stage"] == "RESOLUTION_PROPOSED":
        if st.button("Request reassessment", type="primary", key="grw-m2-request"):
            try:
                service.request_reassessment(run_id); st.rerun()
            except Exception as exc:
                st.error(f"Reassessment request could not be recorded: {type(exc).__name__}")
        return
    if run["stage"] == "REQUESTED":
        with st.form("grw-m2-approval"):
            approver = st.text_input("Reassessment approver", key="grw-m2-approver")
            rationale = st.text_area("Approval rationale", key="grw-m2-approval-rationale")
            approved = st.form_submit_button("Explicitly approve reassessment", type="primary")
        if approved:
            try:
                service.approve_reassessment(run_id, approver=_actor(approver, "reassessment approver"), rationale=rationale); st.rerun()
            except Exception as exc:
                st.error(f"Reassessment could not be approved: {type(exc).__name__}")
        return
    if run["stage"] == "APPROVED":
        if st.button("Create separate successor review", type="primary", key="grw-m2-successor-review"):
            try:
                service.build_successor_review(run_id); st.rerun()
            except Exception as exc:
                st.error(f"Successor review could not be created: {type(exc).__name__}")
        return
    if run["stage"] == "SUCCESSOR_REVIEW_READY":
        if st.button("Run Phase 5 successor assessment", type="primary", key="grw-m2-assess"):
            try:
                service.assess_successor(run_id); st.rerun()
            except Exception as exc:
                st.error(f"Successor assessment could not be created: {type(exc).__name__}")
        return
    if run["stage"] == "ASSESSED":
        if st.button("Generate Phase 6 successor Decision Package", type="primary", key="grw-m2-package"):
            try:
                service.generate_successor_package(run_id); st.rerun()
            except Exception as exc:
                st.error(f"Successor Decision Package could not be created: {type(exc).__name__}")
        return
    if run["stage"] == "PACKAGE_READY":
        if st.button("Compare baseline and successor", type="primary", key="grw-m2-compare"):
            try:
                service.compare(run_id); st.rerun()
            except Exception as exc:
                st.error(f"Comparison could not be recorded: {type(exc).__name__}")
        return
    st.info("This reassessment run is complete or stopped. The baseline Decision Package remains the active historical baseline.")

"""Controlled reassessment (GRW M2), told as a journey rather than a form.

The lifecycle here is a real controlled evidence process, so operational detail
stays: the reviewer still chooses the authoritative permission and conflict
values, and the document locator still records exact character offsets.  What
changes is orientation.  The page states what it is for, that the original
Decision Package is untouched, the whole path this process requires, where the
run currently sits in that path, what this step asks, what follows it, and what
can be produced only after explicit approval.

Nothing here changes M2 semantics.  Every stage, every submitted value and
every eligibility rule is exactly what the service already defines; this module
chooses order and words, and keeps the authoritative tokens in the canonical
technical section.
"""

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
from ai_adoption_engine.presentation import labels
from ai_adoption_engine.presentation.components.technical_details import (
    technical_details,
)
from ai_adoption_engine.presentation.context import (
    decision_continuation_service,
    hydrate_workspace,
    m2_reassessment_service,
    switch_to_registered_page,
)
from ai_adoption_engine.workspace.models import ArtifactType
from ai_adoption_engine.presentation.components.page_header import (
    render_page_header,
)


PAGE_PURPOSE = (
    "You are supplying and reviewing additional evidence about one question "
    "the assessment recorded as open for this activity."
)

BASELINE_UNCHANGED = (
    "Your original Decision Package remains unchanged. Nothing on this page "
    "edits or replaces it."
)

END_STATE = (
    "If every requirement above is met, a separate successor Decision Package "
    "is produced using the approved evidence and placed next to your original "
    "decision. Your original Decision Package remains unchanged."
)

NO_GUARANTEE = (
    "Additional approved evidence may change the recorded assessment. It does "
    "not guarantee a different recommendation."
)

DOCUMENT_SCOPE = (
    "What information is documented about the data available for this "
    "activity? You may provide one current plain-text system description, data "
    "dictionary, or procedure that identifies relevant fields and limits."
)

DOCUMENT_INTAKE_NOTE = (
    "One .txt document is the only intake this route accepts. Do not include "
    "credentials, secrets, or unnecessary personal data."
)


# The controlled path, in the order the service enforces it.  These are
# descriptions of existing stages; no stage is added, renamed or removed.
JOURNEY: tuple[str, ...] = (
    "Provide the permitted supporting document.",
    "Review the evidence in that document.",
    "Review the permitted resolution of the open question.",
    "Request and explicitly approve the reassessment.",
    "Produce the separate successor Decision Package.",
    "Compare it with your original decision.",
)

# Compact headings for the visual strip.  The full stage descriptions above
# remain visible in every cell and continue to own the process meaning.
JOURNEY_LABELS: tuple[str, ...] = (
    "Source",
    "Reviewed",
    "Resolved",
    "Approved",
    "Successor",
    "Compared",
)

# Which journey step each recorded stage sits in.  Several stages share a step
# because the service records more than one immutable operation inside it.
_STAGE_STEP: dict[str, int] = {
    "OPEN": 0,
    "DOCUMENT_SUBMITTED": 1,
    "EVIDENCE_REVIEWED": 2,
    "RESOLUTION_PROPOSED": 3,
    "REQUESTED": 3,
    "APPROVED": 4,
    "SUCCESSOR_REVIEW_READY": 4,
    "ASSESSED": 4,
    "PACKAGE_READY": 5,
    "COMPARED": 6,
}

# What the current step asks of the reader, and what follows it.  Both are
# statements about stages that exist in the service.
_THIS_STEP: dict[str, str] = {
    "OPEN": (
        "Provide one supporting document about the data behind this activity, "
        "and say who supplied it. Supplying a document does not change your "
        "decision and does not start an assessment."
    ),
    "DOCUMENT_SUBMITTED": (
        "Review the stored document. You record which part of it you are "
        "relying on, what scope and period it covers, its source authority, "
        "why it supports the open question, what limitations remain, whether "
        "it may be used, and how it relates to the evidence already reviewed."
    ),
    "EVIDENCE_REVIEWED": (
        "Record the reviewed answer to the open question, and the reasoning "
        "that maps the reviewed evidence to it. This route permits a "
        "data-readiness value of 0 to 4 only."
    ),
    "RESOLUTION_PROPOSED": (
        "Request the reassessment. The request is recorded; it does not "
        "approve anything and it produces no successor."
    ),
    "REQUESTED": (
        "Approve the reassessment explicitly. You are approving a reassessment "
        "that uses the reviewed evidence and the reviewed resolution recorded "
        "above. Approval does not rewrite your original Decision Package."
    ),
    "APPROVED": (
        "Create the separate successor review from the approved evidence. Your "
        "original review and Decision Package are not modified."
    ),
    "SUCCESSOR_REVIEW_READY": (
        "Run the separate successor assessment over the approved review."
    ),
    "ASSESSED": (
        "Produce the separate successor Decision Package from that assessment."
    ),
    "PACKAGE_READY": (
        "Record the comparison between your original decision and the separate "
        "successor."
    ),
}

_WHAT_NEXT: dict[str, str] = {
    "OPEN": "The document you supply is then reviewed, before anything else happens.",
    "DOCUMENT_SUBMITTED": (
        "If the review permits it, you then record the reviewed resolution of "
        "the open question. If the review does not permit it, this "
        "reassessment stops and your original decision stands."
    ),
    "EVIDENCE_REVIEWED": "You then request, and separately approve, the reassessment.",
    "RESOLUTION_PROPOSED": "Approval is recorded separately, as an explicit step.",
    "REQUESTED": (
        "Only after approval can a separate successor Decision Package be produced."
    ),
    "APPROVED": "The successor assessment is then run over that separate review.",
    "SUCCESSOR_REVIEW_READY": (
        "The separate successor Decision Package is then produced from it."
    ),
    "ASSESSED": "It is then compared with your original decision.",
    "PACKAGE_READY": (
        "The comparison becomes the controlled reassessment report, which you "
        "read in Decision continuation."
    ),
}

# The three review outcomes that stop a run all stop it inside step 2, the
# evidence review.  A stale, withdrawn or failed run has no single recorded
# step, so none is claimed for it.
_STOPPED_STEP: dict[str, int] = {
    "EVIDENCE_REJECTED": 1,
    "INSUFFICIENT": 1,
    "BLOCKED_CONFLICT": 1,
}

_TERMINAL_DETAIL: dict[str, str] = {
    "EVIDENCE_REJECTED": (
        "The evidence review recorded that the document is rejected as "
        "evidence for this question. No successor Decision Package was "
        "produced, and your original decision stands."
    ),
    "INSUFFICIENT": (
        "The evidence review recorded that the document is not sufficient for "
        "this use. No successor Decision Package was produced, and your "
        "original decision stands."
    ),
    "BLOCKED_CONFLICT": (
        "The evidence review recorded that the relationship to the evidence "
        "already reviewed was left unresolved. No successor Decision Package "
        "was produced, and your original decision stands."
    ),
    "STALE": (
        "This reassessment was pinned to a decision that is no longer the "
        "current one, so it can be inspected but not continued."
    ),
    "WITHDRAWN": (
        "This reassessment was withdrawn. No successor Decision Package was "
        "produced, and your original decision stands."
    ),
    "FAILED": (
        "This reassessment did not complete. No successor Decision Package was "
        "produced, and your original decision stands."
    ),
    "COMPARED": (
        "This reassessment is complete. A separate successor Decision Package "
        "and its comparison were produced, and your original Decision Package "
        "remains unchanged."
    ),
}


def _actor(label: str, role: str) -> M2ActorDeclaration:
    return M2ActorDeclaration(
        label=label,
        declared_role=role,
        acknowledged_local_role_limitation=True,
        declared_at=datetime.now(UTC),
    )


def _permission_label(value: str) -> str:
    return labels.m2_evidence_permission_label(value)


def _conflict_label(value: str) -> str:
    return labels.m2_conflict_status_label(value)


def _render_journey(stage: str | None) -> None:
    """Show the whole controlled path, and where this run sits in it."""

    st.subheader("What this process requires")
    current = _STAGE_STEP.get(stage or "")
    stopped = _STOPPED_STEP.get(stage or "")
    cells = st.columns(len(JOURNEY), gap="small")
    for index, (label, description) in enumerate(zip(JOURNEY_LABELS, JOURNEY)):
        if stopped is not None:
            marker = "✓" if index < stopped else ("→" if index == stopped else "•")
        elif current is None:
            marker = "•"
        elif index < current:
            marker = "✓"
        elif index == current:
            marker = "→"
        else:
            marker = "•"
        with cells[index].container(border=True, height="stretch"):
            st.markdown(f"**{marker} {index + 1}. {label}**")
            st.caption(description)
    if stopped is not None:
        st.caption(f"This reassessment stopped at step {stopped + 1} of {len(JOURNEY)}.")
    elif stage is None:
        st.caption("No controlled reassessment is open for this question yet.")
    elif current is None:
        st.caption("No step of this path is in progress for this record.")
    elif current >= len(JOURNEY):
        st.caption(f"All {len(JOURNEY)} steps of this path were completed.")
    else:
        st.caption(f"You are on step {current + 1} of {len(JOURNEY)}.")


def _render_where_you_are(stage: str) -> None:
    st.subheader("Where you are now")
    st.write(labels.m2_stage_label(stage))


def _render_recorded(service, run_id: str) -> None:
    """Restate what the run already recorded, in the shared vocabulary.

    Every line here is a persisted value read back: the reviewer's outcome, the
    relationship they recorded, the limitations they retained, the reviewed
    answer and who approved the reassessment.  Nothing is inferred from the
    document's contents.
    """

    lines: list[str] = []
    review_ref = service.repository.load_artifact_reference(
        run_id, M2ArtifactType.EVIDENCE_REVIEW
    )
    if review_ref is not None:
        review = service.repository.load_artifact(review_ref.artifact_id)
        lines.append(
            "The evidence review recorded: "
            + _permission_label(review.permission.value)
            + "."
        )
        lines.append(
            "Relationship to the evidence already reviewed: "
            + _conflict_label(review.conflict_status.value)
            + "."
        )
        lines.append(f"Limitations retained: {review.limitations}")
    resolution_ref = service.repository.load_artifact_reference(
        run_id, M2ArtifactType.DATA_READINESS_RESOLUTION
    )
    if resolution_ref is not None:
        resolution = service.repository.load_artifact(resolution_ref.artifact_id)
        lines.append(
            "Reviewed answer to the open question: "
            + labels.criterion_value_display(
                resolution.proposed_value,
                resolution.proposed_knowledge_state.value,
            )
            + "."
        )
    approval_ref = service.repository.load_artifact_reference(
        run_id, M2ArtifactType.REASSESSMENT_APPROVAL
    )
    if approval_ref is not None:
        approval = service.repository.load_artifact(approval_ref.artifact_id)
        lines.append(
            "A separate reassessment using this reviewed evidence was approved by "
            + approval.approver.label
            + "."
        )
    if not lines:
        return
    st.subheader("What has been recorded so far")
    for line in lines:
        st.write(line)


def _render_decision_pair(item, run) -> None:
    """Keep the baseline and any successor visibly separate and equal."""

    if run.successor is None:
        return
    st.subheader("The two recorded decisions")
    original, successor = st.columns(2, gap="small")
    with original.container(border=True, height="stretch"):
        st.markdown("**Your original decision**")
        st.write(labels.recommendation_label(item.recommendation_mode.value))
        st.caption("Remains unchanged and is not replaced by the reassessment.")
    with successor.container(border=True, height="stretch"):
        st.markdown("**The separate reassessment decision**")
        st.write(labels.recommendation_label(run.successor.target_recommendation))
        st.caption("Sits alongside the original decision as a separate record.")


def _render_this_step(stage: str) -> None:
    description = _THIS_STEP.get(stage)
    if description is None:
        return
    st.subheader("This step")
    st.write(description)


def _render_what_next(stage: str) -> None:
    description = _WHAT_NEXT.get(stage)
    if description is None:
        return
    st.subheader("What happens next")
    st.write(description)


def _render_end_state() -> None:
    st.subheader("What can happen at the end")
    st.write(END_STATE)
    st.caption(NO_GUARANTEE)


def _render_return() -> None:
    if st.button(
        "Return to decision continuation",
        key="grw-m2-return-dcw",
        icon=":material/arrow_back:",
    ):
        if not switch_to_registered_page("decision-continuation"):
            st.info("Open Decision continuation from the sidebar to return.")
    st.caption(
        "Goes back to the page listing your decision and its continuation "
        "routes. Nothing is submitted or discarded."
    )


def _render_baseline_technical(baseline, gap, item) -> None:
    st.caption(f"Baseline package: {baseline.package_id}")
    st.caption(f"Baseline assessment: {baseline.assessment_id}")
    st.caption(f"Baseline source document: {baseline.source_document_id}")
    st.caption(f"Step ID: {gap.step_id}")
    st.caption(f"Information gap ID: {gap.information_gap.gap_id}")
    st.caption(f"Criterion: {gap.information_gap.field_name}")
    st.caption(
        f"Baseline value: {gap.baseline_value} "
        f"({gap.baseline_knowledge_state.value})"
    )
    st.caption(
        f"Baseline recommendation: {item.recommendation_mode.value} (existing baseline)"
    )


def _render_run_technical(run, record) -> None:
    st.caption(f"Separate reassessment run: {run.run_id}")
    st.caption(f"Raw lifecycle stage: {record['stage']}")
    st.caption(f"Run opened at: {run.created_at}")
    st.caption(f"Run updated at: {run.updated_at}")
    if run.successor is not None:
        st.caption(f"Successor Decision Package: {run.successor.package_id}")
        st.caption(
            f"Successor package artifact: {run.successor.package_artifact.artifact_id} "
            f"· revision {run.successor.package_artifact.artifact_revision} "
            f"· sha256 {run.successor.package_artifact.payload_sha256}"
        )
        st.caption(f"Successor recommendation: {run.successor.target_recommendation}")
    if run.comparison is not None:
        st.caption(
            f"Comparison artifact: {run.comparison.artifact.artifact_id} "
            f"· revision {run.comparison.artifact.artifact_revision} "
            f"· sha256 {run.comparison.artifact.payload_sha256}"
        )
        st.caption(
            "Comparison categories: " + ", ".join(run.comparison.categories)
        )
        st.caption(
            f"Baseline recommendation: {run.comparison.baseline_recommendation}"
        )
        st.caption(
            f"Successor recommendation: {run.comparison.successor_recommendation}"
        )
    if run.controlled_report is not None:
        for reference in run.controlled_report.lineage:
            st.caption(
                f"Lineage · {reference.label}: {reference.artifact_id} "
                f"· revision {reference.artifact_revision} "
                f"· sha256 {reference.payload_sha256}"
            )


def _render_document_technical(service, run_id: str) -> str | None:
    """Show the stored document's provenance, and return its decoded text."""

    reference = service.repository.load_artifact_reference(
        run_id, M2ArtifactType.DOCUMENT_SUBMISSION
    )
    if reference is None:
        return None
    submission = service.repository.load_artifact(reference.artifact_id)
    document = submission.document
    st.caption(f"Document submission artifact: {reference.artifact_id}")
    st.caption(f"Submission ID: {submission.submission_id}")
    st.caption(f"Submitted at: {submission.submitted_at.isoformat()}")
    st.caption(f"Document ID: {document.document_id}")
    st.caption(f"Document filename: {document.filename}")
    st.caption(f"Document SHA-256: {document.content_sha256}")
    st.caption(f"Document length: {document.byte_length} bytes")
    st.caption(f"Document source label: {document.source_label}")
    st.caption(f"Submitter: {submission.submitter.label}")
    return service.repository.load_document_bytes(document.document_id).decode("utf-8")


def _render_review_technical(service, run_id: str) -> None:
    reference = service.repository.load_artifact_reference(
        run_id, M2ArtifactType.EVIDENCE_REVIEW
    )
    if reference is None:
        return
    review = service.repository.load_artifact(reference.artifact_id)
    locator = review.locator
    st.caption(f"Evidence review artifact: {reference.artifact_id}")
    st.caption(f"Review ID: {review.review_id}")
    st.caption(f"Reviewed at: {review.reviewed_at.isoformat()}")
    st.caption(f"Evidence reviewer: {review.reviewer.label}")
    st.caption(f"Raw evidence permission: {review.permission.value}")
    st.caption(f"Raw conflict status: {review.conflict_status.value}")
    st.caption(
        f"Locator: characters {locator.start_offset}–{locator.end_offset}, "
        f"lines {locator.line_start}–{locator.line_end}"
    )
    st.caption(f"Scope statement: {review.scope_statement}")
    st.caption(f"Period statement: {review.period_statement}")
    st.caption(f"Source authority: {review.source_authority}")
    st.caption(f"Limitations retained: {review.limitations}")
    if review.evidence_class is not None:
        st.caption(f"Raw evidence class: {review.evidence_class.value}")


def _render_resolution_technical(service, run_id: str) -> None:
    reference = service.repository.load_artifact_reference(
        run_id, M2ArtifactType.DATA_READINESS_RESOLUTION
    )
    if reference is None:
        return
    resolution = service.repository.load_artifact(reference.artifact_id)
    st.caption(f"Criterion resolution artifact: {reference.artifact_id}")
    st.caption(f"Proposed value: {resolution.proposed_value}")
    st.caption(f"Proposed knowledge state: {resolution.proposed_knowledge_state.value}")
    st.caption(f"Data owner: {resolution.data_owner.label}")
    st.caption(f"Criterion reviewer: {resolution.criterion_reviewer.label}")


def _render_approval_technical(service, run_id: str) -> None:
    reference = service.repository.load_artifact_reference(
        run_id, M2ArtifactType.REASSESSMENT_APPROVAL
    )
    if reference is None:
        return
    approval = service.repository.load_artifact(reference.artifact_id)
    st.caption(f"Approval artifact: {reference.artifact_id}")
    st.caption(f"Approved at: {approval.approved_at.isoformat()}")
    st.caption(f"Approver: {approval.approver.label}")
    st.caption(f"Approval rationale: {approval.rationale}")


def _render_technical(*, baseline, gap, item, service, run=None, record=None) -> None:
    """The canonical technical section: everything authoritative, in one place."""

    with technical_details():
        _render_baseline_technical(baseline, gap, item)
        if run is None or record is None:
            return
        _render_run_technical(run, record)
        _render_document_technical(service, run.run_id)
        _render_review_technical(service, run.run_id)
        _render_resolution_technical(service, run.run_id)
        _render_approval_technical(service, run.run_id)


def _render_orientation(item, gap, *, stage: str | None) -> None:
    """The block every state opens with, before any form."""

    st.caption(f"Controlled reassessment · {gap.current_activity}")

    st.subheader("What this page is for")
    st.write(PAGE_PURPOSE)
    st.write(f"The question is: {DOCUMENT_SCOPE}")

    st.subheader("Your original decision remains unchanged")
    st.warning(BASELINE_UNCHANGED, icon="ℹ️")
    st.write(
        "Decision recorded for this activity: "
        + labels.recommendation_label(item.recommendation_mode.value)
        + "."
    )

    _render_journey(stage)


def render() -> None:
    render_page_header("Controlled reassessment")
    snapshot = hydrate_workspace()
    if snapshot is None:
        st.info("Open a package-ready assessment first.")
        return
    try:
        service = m2_reassessment_service()
    except M2FrozenWorkspaceError:
        st.warning(
            "Reassessment is unavailable for protected evaluation workspaces. "
            "Your original Decision Package remains unchanged."
        )
        return
    context = service.open_m2_m1_context(snapshot.assessment.assessment_id)
    if context is None:
        st.info(
            "No eligible open data-readiness question is available for this "
            "Decision Package, so a controlled reassessment cannot be started."
        )
        return
    baseline, gap = context
    package = snapshot.active_artifacts[
        ArtifactType.DECISION_PACKAGE_RESULT
    ].payload.package
    item = next(x for x in package.portfolio.items if x.step_id == gap.step_id)

    run_id = st.session_state.get("dcw_selected_m2_run_id") or st.session_state.get(
        "grw_m2_run_id"
    )
    selected = _selected_run(snapshot.assessment.assessment_id, run_id)
    if run_id is not None and (selected is None or selected.is_terminal):
        # Fail closed exactly as before: a terminal or unrecognised selection
        # clears itself and offers no lifecycle action.  What changes is that
        # the reader is told which recorded outcome this was.
        st.session_state.pop("dcw_selected_m2_run_id", None)
        st.session_state.pop("grw_m2_run_id", None)
        _render_orientation(item, gap, stage=selected.stage.value if selected else None)
        _render_stopped(selected)
        if selected is not None:
            _render_recorded(service, selected.run_id)
        # ``What can happen at the end`` describes a path still open to the
        # reader.  This record has already reached its end, and the block above
        # states which one, so repeating the future tense here would mislead.
        st.caption(NO_GUARANTEE)
        _render_return()
        _render_technical(
            baseline=baseline,
            gap=gap,
            item=item,
            service=service,
            run=selected,
            record=(
                service.repository.load_run(selected.run_id)
                if selected is not None
                else None
            ),
        )
        return

    if selected is None:
        _render_orientation(item, gap, stage=None)
        st.subheader("This step")
        st.write(
            "Open a controlled reassessment for this question. Opening it "
            "records nothing about the decision and produces no successor."
        )
        with st.container(border=True):
            with st.form("grw-m2-open-run", border=False):
                opened = st.form_submit_button("Open reassessment", type="primary")
        st.caption(
            "Starts the controlled path above at step 1. Your original "
            "Decision Package remains unchanged."
        )
        if opened:
            try:
                new_run_id, _, _ = service.create_run(snapshot.assessment.assessment_id)
                st.session_state.grw_m2_run_id = new_run_id
                st.rerun()
            except Exception as exc:
                st.error(f"Reassessment could not be opened: {type(exc).__name__}")
        _render_end_state()
        _render_return()
        _render_technical(baseline=baseline, gap=gap, item=item, service=service)
        return

    run_id = selected.run_id
    st.session_state.grw_m2_run_id = run_id
    st.session_state.dcw_selected_m2_run_id = run_id
    record = service.repository.load_run(run_id)
    stage = record["stage"]

    _render_orientation(item, gap, stage=stage)
    _render_where_you_are(stage)
    _render_recorded(service, run_id)
    _render_decision_pair(item, selected)
    _render_this_step(stage)
    with st.container(border=True):
        _render_stage_controls(service, run_id=run_id, stage=stage)
    _render_what_next(stage)
    _render_end_state()
    _render_return()
    _render_technical(
        baseline=baseline, gap=gap, item=item, service=service, run=selected, record=record
    )


def _selected_run(assessment_id: str, run_id: str | None):
    """Return this assessment's recorded run, or None when there is no match."""

    if run_id is None:
        return None
    try:
        view = decision_continuation_service().open(assessment_id)
    except (PersistenceError, ValueError):
        return None
    if view.m2_context is None or view.m2_discovery_error is not None:
        return None
    expected_baseline, expected_gap = view.m2_context
    for run in view.m2_runs:
        if run.run_id != run_id:
            continue
        if run.baseline != expected_baseline or run.gap != expected_gap:
            return None
        return run
    return None


def _render_stopped(run) -> None:
    """Explain a stopped or completed record accurately, never generically."""

    stage = run.stage.value if run is not None else None
    if stage is None:
        st.subheader("This reassessment is no longer available")
        st.warning(
            "The reassessment that was selected is not available for this "
            "decision, so no step is in progress. You can review the recorded "
            "reassessments in Decision continuation."
        )
        return
    with st.container(border=True):
        st.subheader(
            "This reassessment is complete"
            if stage == "COMPARED"
            else "This reassessment stopped"
        )
        st.write(labels.m2_stage_label(stage))
        detail = _TERMINAL_DETAIL.get(stage)
        if detail:
            st.write(detail)
        st.caption(
            "This record is available for inspection only. Its outcome and its "
            "comparison, where one exists, are shown in Decision continuation."
        )


def _render_stage_controls(service, *, run_id: str, stage: str) -> None:
    """Render the one control this stage permits, with its consequence."""

    if stage == "OPEN":
        with st.form("grw-m2-document-submit", border=False):
            uploaded = st.file_uploader(
                "One supporting plain-text document",
                type=["txt"],
                key="grw-m2-document",
            )
            source_label = st.text_input(
                "Document source or authority", key="grw-m2-source"
            )
            submitter = st.text_input("Your name or label", key="grw-m2-submitter")
            submitted = st.form_submit_button(
                "Submit supporting document", type="primary"
            )
        st.caption(DOCUMENT_INTAKE_NOTE)
        st.caption(
            "Stores the document against this reassessment for review. It does "
            "not change your decision and it does not start an assessment."
        )
        if submitted:
            try:
                if uploaded is None:
                    raise ValueError("Select one .txt document")
                service.submit_supporting_document(
                    run_id,
                    content_bytes=uploaded.getvalue(),
                    filename=uploaded.name,
                    source_label=source_label,
                    submitter=_actor(submitter, "document submitter"),
                )
                st.rerun()
            except Exception as exc:
                st.error(f"Document could not be submitted: {type(exc).__name__}")
        return

    if stage == "DOCUMENT_SUBMITTED":
        submission_ref = service.repository.load_artifact_reference(
            run_id, M2ArtifactType.DOCUMENT_SUBMISSION
        )
        submission = service.repository.load_artifact(submission_ref.artifact_id)
        text = service.repository.load_document_bytes(
            submission.document.document_id
        ).decode("utf-8")
        st.text_area(
            "Stored document (read-only)",
            value=text,
            disabled=True,
            key="grw-m2-document-preview",
        )
        with st.form("grw-m2-evidence-review", border=False):
            st.markdown("**Exact evidence excerpt**")
            st.caption(
                "The passage you rely on is recorded exactly, as its first and "
                "last character position in the stored document above. The "
                "whole document is selected by default."
            )
            start = st.number_input(
                "Excerpt start character", min_value=0, value=0, key="grw-m2-start"
            )
            end = st.number_input(
                "Excerpt end character",
                min_value=1,
                value=len(text),
                key="grw-m2-end",
            )
            st.markdown("**Reviewer and evidence scope**")
            reviewer = st.text_input("Evidence reviewer", key="grw-m2-reviewer")
            scope = st.text_input("Same-activity scope statement", key="grw-m2-scope")
            period = st.text_input(
                "Period or explicit limitation", key="grw-m2-period"
            )
            authority = st.text_input("Source authority", key="grw-m2-authority")
            rationale = st.text_area(
                "Semantic-support rationale", key="grw-m2-rationale"
            )
            limitations = st.text_area("Limitations retained", key="grw-m2-limitations")
            st.markdown("**Reviewed decision and relationship**")
            outcome = st.selectbox(
                "Evidence-review outcome",
                [item.value for item in M2EvidencePermission],
                index=None,
                format_func=_permission_label,
                placeholder="Select the reviewed outcome",
                key="grw-m2-evidence-outcome",
            )
            conflict = st.selectbox(
                "Relationship to baseline evidence",
                [item.value for item in M2ConflictStatus],
                index=None,
                format_func=_conflict_label,
                placeholder="Select the reviewed relationship",
                key="grw-m2-conflict-status",
            )
            conflict_rationale = st.text_area(
                "Conflict or consistency rationale", key="grw-m2-conflict-rationale"
            )
            reconciliation = st.text_area(
                "Reviewer reconciliation for contradictory evidence, if applicable",
                key="grw-m2-reconciliation",
            )
            applicability = st.text_area(
                "Why stale/superseded evidence applies to this target scope, if applicable",
                key="grw-m2-applicability",
            )
            reviewed = st.form_submit_button(
                "Record document evidence review", type="primary"
            )
        st.caption(
            "Records your review of this document. Only an outcome that admits "
            "the evidence allows the reassessment to continue; the other "
            "outcomes stop it, and your original decision stands."
        )
        if reviewed:
            try:
                if outcome is None or conflict is None:
                    raise ValueError(
                        "Select both the evidence-review outcome and its "
                        "relationship to baseline evidence"
                    )
                excerpt = text[int(start) : int(end)]
                locator = M2DocumentLocator(
                    start_offset=int(start),
                    end_offset=int(end),
                    line_start=text.count("\n", 0, int(start)) + 1,
                    line_end=text.count("\n", 0, int(end)) + 1,
                    exact_excerpt=excerpt,
                )
                service.review_document_evidence(
                    run_id,
                    reviewer=_actor(reviewer, "evidence reviewer"),
                    locator=locator,
                    scope_statement=scope,
                    period_statement=period,
                    source_authority=authority,
                    semantic_rationale=rationale,
                    limitations=limitations,
                    conflict_status=M2ConflictStatus(conflict),
                    conflict_rationale=conflict_rationale,
                    reconciliation_statement=reconciliation or None,
                    applicability_statement=applicability or None,
                    permission=M2EvidencePermission(outcome),
                )
                st.rerun()
            except Exception as exc:
                st.error(f"Evidence review could not be recorded: {type(exc).__name__}")
        return

    if stage == "EVIDENCE_REVIEWED":
        with st.form("grw-m2-resolution", border=False):
            value = st.selectbox(
                "Reviewed data-readiness value (document-only M2 M1 allows 0–4)",
                [0, 1, 2, 3, 4],
                key="grw-m2-value",
            )
            rationale = st.text_area(
                "Instrument mapping rationale", key="grw-m2-mapping"
            )
            narrowed_scope = st.text_area(
                "Narrowed evidence scope, if the review recorded a scope conflict",
                key="grw-m2-narrowed-scope",
            )
            owner_reconciliation = st.text_area(
                "Data-owner reconciliation for contradictory evidence, if applicable",
                key="grw-m2-owner-reconciliation",
            )
            owner = st.text_input("Declared data owner", key="grw-m2-owner")
            reviewer = st.text_input(
                "Criterion reviewer", key="grw-m2-criterion-reviewer"
            )
            proposed = st.form_submit_button(
                "Record reviewed criterion resolution", type="primary"
            )
        st.caption(
            "Records the reviewed answer to the open question. It is not "
            "applied to your original decision, and it is used only if the "
            "reassessment is explicitly approved."
        )
        if proposed:
            try:
                service.propose_data_readiness_resolution(
                    run_id,
                    proposed_value=int(value),
                    proposed_knowledge_state=KnowledgeState.KNOWN,
                    mapping_rationale=rationale,
                    narrowed_scope_statement=narrowed_scope or None,
                    data_owner_reconciliation=owner_reconciliation or None,
                    data_owner=_actor(owner, "data owner"),
                    criterion_reviewer=_actor(reviewer, "criterion reviewer"),
                )
                st.rerun()
            except Exception as exc:
                st.error(
                    f"Criterion resolution could not be recorded: {type(exc).__name__}"
                )
        return

    if stage == "RESOLUTION_PROPOSED":
        if st.button("Request reassessment", type="primary", key="grw-m2-request"):
            try:
                service.request_reassessment(run_id)
                st.rerun()
            except Exception as exc:
                st.error(
                    f"Reassessment request could not be recorded: {type(exc).__name__}"
                )
        st.caption(
            "Records the request. It approves nothing and produces no "
            "successor Decision Package."
        )
        return

    if stage == "REQUESTED":
        with st.form("grw-m2-approval", border=False):
            approver = st.text_input("Reassessment approver", key="grw-m2-approver")
            rationale = st.text_area(
                "Approval rationale", key="grw-m2-approval-rationale"
            )
            approved = st.form_submit_button(
                "Explicitly approve reassessment", type="primary"
            )
        st.caption(
            "Approves a reassessment that uses the reviewed evidence and the "
            "reviewed resolution recorded above. Your original Decision "
            "Package is not rewritten; a separate successor may then be "
            "produced."
        )
        if approved:
            try:
                service.approve_reassessment(
                    run_id,
                    approver=_actor(approver, "reassessment approver"),
                    rationale=rationale,
                )
                st.rerun()
            except Exception as exc:
                st.error(f"Reassessment could not be approved: {type(exc).__name__}")
        return

    if stage == "APPROVED":
        if st.button(
            "Create separate successor review",
            type="primary",
            key="grw-m2-successor-review",
        ):
            try:
                service.build_successor_review(run_id)
                st.rerun()
            except Exception as exc:
                st.error(f"Successor review could not be created: {type(exc).__name__}")
        st.caption(
            "Creates a separate review from the approved evidence. Your "
            "original review is not modified."
        )
        return

    if stage == "SUCCESSOR_REVIEW_READY":
        if st.button(
            "Run separate successor assessment", type="primary", key="grw-m2-assess"
        ):
            try:
                service.assess_successor(run_id)
                st.rerun()
            except Exception as exc:
                st.error(
                    f"Successor assessment could not be created: {type(exc).__name__}"
                )
        st.caption(
            "Assesses the separate successor review. Your original assessment "
            "is not re-run and not modified."
        )
        return

    if stage == "ASSESSED":
        if st.button(
            "Generate separate successor Decision Package",
            type="primary",
            key="grw-m2-package",
        ):
            try:
                service.generate_successor_package(run_id)
                st.rerun()
            except Exception as exc:
                st.error(
                    f"Successor Decision Package could not be created: {type(exc).__name__}"
                )
        st.caption(
            "Produces a separate successor Decision Package next to your "
            "original one. Your original Decision Package remains unchanged."
        )
        return

    if stage == "PACKAGE_READY":
        if st.button(
            "Compare original and successor", type="primary", key="grw-m2-compare"
        ):
            try:
                service.compare(run_id)
                st.rerun()
            except Exception as exc:
                st.error(f"Comparison could not be recorded: {type(exc).__name__}")
        st.caption(
            "Records the comparison between the two Decision Packages, which "
            "becomes the controlled reassessment report in Decision "
            "continuation."
        )
        return

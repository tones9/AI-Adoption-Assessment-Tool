"""Read-only Phase 7 projection for the guided Phase 4 review journey.

The module deliberately contains no service, persistence, assessment, package,
or GRW imports.  It explains the persisted review state; Phase 4 remains the
only authority that can change it or approve it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.models.review import (
    ApprovalError,
    ConflictStatus,
    InformationOrigin,
    ProcessReviewSession,
    ReviewAction,
    ReviewDisposition,
)
from ai_adoption_engine.presentation.review_progress import (
    OutstandingReviewItem,
    ReviewProgress,
    approval_errors,
    build_review_progress,
    document_supported_unreviewed,
    inferred_unreviewed,
    iter_process_assertions,
    iter_step_assertions,
    unknown_unreviewed_by_step,
)


@dataclass(frozen=True)
class ReviewJourneyDocumentGroup:
    """A presentation-only group of existing document-backed field paths."""

    scope_label: str
    step_id: str | None
    field_paths: tuple[str, ...]


@dataclass(frozen=True)
class ReviewJourneyUnknownGroup:
    step_id: str
    step_label: str
    count: int


@dataclass(frozen=True)
class ReviewJourneyAuditSummary:
    """Event-derived description for the final approval hand-off."""

    corrections: tuple[str, ...]
    rejections_or_removals: tuple[str, ...]
    structural_changes: tuple[str, ...]
    accepted_documented: tuple[str, ...]
    retained_unknowns: tuple[str, ...]
    human_supplied_fields: tuple[str, ...]


@dataclass(frozen=True)
class ReviewJourneyView:
    """Immutable, non-authoritative explanation of one persisted review session."""

    candidate_process_name: str | None
    candidate_activities: tuple[str, ...]
    reviewed_process_name: str | None
    reviewed_activities: tuple[str, ...]
    extraction_issue_messages: tuple[str, ...]
    progress: ReviewProgress
    approval_errors: tuple[ApprovalError, ...]
    required_items: tuple[OutstandingReviewItem, ...]
    document_groups: tuple[ReviewJourneyDocumentGroup, ...]
    unknown_groups: tuple[ReviewJourneyUnknownGroup, ...]
    inferred_field_paths: tuple[str, ...]
    open_blocking_conflict_ids: tuple[str, ...]
    invalid_dependency_field_paths: tuple[str, ...]
    audit: ReviewJourneyAuditSummary
    default_focus_item_id: str | None


def build_review_journey(
    session: ProcessReviewSession,
    *,
    selected_item_id: str | None = None,
) -> ReviewJourneyView:
    """Project exact Phase 4 preflight state without changing it.

    The required queue is copied directly from ``build_review_progress``, which
    itself invokes the real ``approve_review`` preflight.  This function does
    not calculate its own approval rules or mutate the supplied session.
    """

    progress = build_review_progress(session)
    errors = tuple(approval_errors(session))
    outstanding_ids = {item.item_id for item in progress.outstanding}
    default_focus = (
        selected_item_id
        if selected_item_id in outstanding_ids
        else (progress.outstanding[0].item_id if progress.outstanding else None)
    )

    groups: list[ReviewJourneyDocumentGroup] = []
    process_paths = tuple(
        target.field_path
        for target in document_supported_unreviewed(iter_process_assertions(session))
    )
    if process_paths:
        groups.append(
            ReviewJourneyDocumentGroup(
                scope_label="the process identity", step_id=None, field_paths=process_paths
            )
        )
    for step in sorted(session.steps, key=lambda value: value.sequence):
        paths = tuple(
            target.field_path
            for target in document_supported_unreviewed(
                iter_step_assertions(session, step.candidate_step_id)
            )
        )
        if paths:
            groups.append(
                ReviewJourneyDocumentGroup(
                    scope_label=f"Step {step.sequence}",
                    step_id=step.candidate_step_id,
                    field_paths=paths,
                )
            )

    unknown_by_step = unknown_unreviewed_by_step(session)
    unknown_groups = tuple(
        ReviewJourneyUnknownGroup(
            step_id=step.candidate_step_id,
            step_label=f"Step {step.sequence} — {step.activity.value or 'Unknown activity'}",
            count=unknown_by_step.get(step.candidate_step_id, 0),
        )
        for step in sorted(session.steps, key=lambda value: value.sequence)
        if unknown_by_step.get(step.candidate_step_id, 0)
    )
    inferred = tuple(item.field_path for item in inferred_unreviewed(session))
    error_paths = {error.field_path for error in errors if error.field_path}
    invalid_dependency_paths = tuple(
        path for path in error_paths if ".dependencies[" in path
    )

    return ReviewJourneyView(
        candidate_process_name=session.original_candidate.process_name.value,
        candidate_activities=tuple(
            str(step.activity.value or "Unknown activity")
            for step in session.original_candidate.steps
        ),
        reviewed_process_name=session.process_name.value,
        reviewed_activities=tuple(
            str(step.activity.value or "Unknown activity")
            for step in sorted(session.steps, key=lambda value: value.sequence)
            if step.retained
        ),
        extraction_issue_messages=tuple(issue.message for issue in session.extraction_issues),
        progress=progress,
        approval_errors=errors,
        required_items=progress.outstanding,
        document_groups=tuple(groups),
        unknown_groups=unknown_groups,
        inferred_field_paths=inferred,
        open_blocking_conflict_ids=tuple(
            conflict.conflict_id
            for conflict in session.conflicts
            if conflict.blocking and conflict.status is ConflictStatus.OPEN
        ),
        invalid_dependency_field_paths=invalid_dependency_paths,
        audit=_audit_summary(session),
        default_focus_item_id=default_focus,
    )


def _audit_summary(session: ProcessReviewSession) -> ReviewJourneyAuditSummary:
    corrections: list[str] = []
    rejections_or_removals: list[str] = []
    structural_changes: list[str] = []
    accepted_documented: list[str] = []
    retained_unknowns: list[str] = []

    for event in session.events:
        path = event.field_path
        if event.action in {ReviewAction.CORRECT, ReviewAction.RESOLVE_UNKNOWN}:
            corrections.append(path)
        elif event.action is ReviewAction.REJECT:
            rejections_or_removals.append(path)
        elif event.action in {
            ReviewAction.REORDER_STEPS,
            ReviewAction.ACCEPT_STEP_ORDER,
            ReviewAction.CORRECT_DEPENDENCY,
            ReviewAction.RESOLVE_CONFLICT,
            ReviewAction.SELECT_PRIMARY_ACTOR,
        }:
            structural_changes.append(path)
        elif event.action is ReviewAction.ACCEPT:
            accepted_documented.append(path)
        elif event.action is ReviewAction.RETAIN_UNKNOWN:
            retained_unknowns.append(path)

    human_supplied = tuple(
        target.field_path
        for target in _all_targets(session)
        if target.assertion.origin is InformationOrigin.HUMAN_SUPPLIED
        and target.assertion.knowledge_state is not KnowledgeState.UNKNOWN
        and target.assertion.retained
    )
    return ReviewJourneyAuditSummary(
        corrections=tuple(corrections),
        rejections_or_removals=tuple(rejections_or_removals),
        structural_changes=tuple(structural_changes),
        accepted_documented=tuple(accepted_documented),
        retained_unknowns=tuple(retained_unknowns),
        human_supplied_fields=human_supplied,
    )


def _all_targets(session: ProcessReviewSession):
    targets = iter_process_assertions(session)
    for step in session.steps:
        targets.extend(iter_step_assertions(session, step.candidate_step_id))
    return targets

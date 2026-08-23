"""Phase 7 review-progress projection over the authoritative Phase 4 state."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.models.review import (
    ApprovalError,
    ExplicitApproval,
    InformationOrigin,
    ProcessReviewSession,
    ReviewDisposition,
    ReviewedAssertion,
)
from ai_adoption_engine.review.approval import approve_review


@dataclass(frozen=True)
class AssertionTarget:
    field_path: str
    label: str
    assertion: ReviewedAssertion
    step_id: str | None = None
    step_sequence: int | None = None
    activity: str | None = None


@dataclass(frozen=True)
class OutstandingReviewItem:
    item_id: str
    field_path: str | None
    field_label: str
    reason: str
    step_id: str | None = None
    step_sequence: int | None = None
    activity: str | None = None

    @property
    def location_label(self) -> str:
        if self.step_sequence is not None:
            return f"Step {self.step_sequence} — {self.activity or 'Unknown activity'}"
        return "Process"


@dataclass(frozen=True)
class ReviewProgress:
    total_required: int
    completed_required: int
    outstanding: tuple[OutstandingReviewItem, ...]

    @property
    def remaining_required(self) -> int:
        return len(self.outstanding)

    @property
    def is_ready(self) -> bool:
        return not self.outstanding

    @property
    def completion_ratio(self) -> float:
        if self.total_required == 0:
            return 1.0
        return self.completed_required / self.total_required


def approval_errors(session: ProcessReviewSession) -> list[ApprovalError]:
    """Run the real Phase 4 approval boundary as a side-effect-free preflight."""

    return approve_review(
        session,
        ExplicitApproval(
            approval_statement="APPROVE CURRENT-STATE PROCESS",
            approved_at=session.updated_at,
        ),
    ).errors


def build_review_progress(session: ProcessReviewSession) -> ReviewProgress:
    """Describe only items that the Phase 4 approval boundary actually requires."""

    retained_steps = [item for item in session.steps if item.retained]
    base_required = 2 + len(retained_steps)  # process identity, order, each activity
    errors = approval_errors(session)
    outstanding = tuple(
        _outstanding_item(session, error, item_id=item_id)
        for error, item_id in zip(errors, _item_ids(errors), strict=True)
    )
    dynamic_codes = {
        "no-retained-steps",
        "invalid-retained-dependency",
        "unresolved-structural-conflict",
        "invalid-phase1-projection",
        "review-already-approved",
    }
    dynamic_required = sum(item.code in dynamic_codes for item in errors)
    total = base_required + dynamic_required
    return ReviewProgress(
        total_required=total,
        completed_required=max(0, total - len(outstanding)),
        outstanding=outstanding,
    )


def iter_process_assertions(session: ProcessReviewSession) -> list[AssertionTarget]:
    return [
        AssertionTarget("process.name", "Process name", session.process_name),
        AssertionTarget(
            "process.description",
            "Process description",
            session.process_description,
        ),
        AssertionTarget(
            "process.objective",
            "Process objective",
            session.process_objective,
        ),
    ]


def iter_step_assertions(session: ProcessReviewSession, step_id: str) -> list[AssertionTarget]:
    step = next(item for item in session.steps if item.candidate_step_id == step_id)
    prefix = f"steps.{step_id}"
    context = {
        "step_id": step_id,
        "step_sequence": step.sequence,
        "activity": str(step.activity.value or "Unknown activity"),
    }
    targets = [
        AssertionTarget(
            f"{prefix}.document_order", "Document order", step.document_order, **context
        ),
        AssertionTarget(f"{prefix}.activity", "Activity", step.activity, **context),
        AssertionTarget(
            f"{prefix}.description", "Description", step.description, **context
        ),
    ]
    for attribute, label in (
        ("actors", "Actor"),
        ("responsible_roles", "Responsible role"),
        ("systems", "System or tool"),
        ("inputs", "Input"),
        ("outputs", "Output"),
        ("exceptions", "Exception"),
        ("operational_characteristics", "Operational fact"),
    ):
        collection = getattr(step, attribute)
        targets.extend(
            AssertionTarget(
                f"{prefix}.{attribute}.items[{index}]",
                f"{label} {index + 1}",
                assertion,
                **context,
            )
            for index, assertion in enumerate(collection.items)
        )
    for index, decision in enumerate(step.decisions):
        targets.append(
            AssertionTarget(
                f"{prefix}.decisions[{index}].condition",
                f"Decision {index + 1} condition",
                decision.condition,
                **context,
            )
        )
        targets.extend(
            AssertionTarget(
                f"{prefix}.decisions[{index}].branches.items[{branch_index}]",
                f"Decision {index + 1} branch {branch_index + 1}",
                assertion,
                **context,
            )
            for branch_index, assertion in enumerate(decision.branches.items)
        )
    for index, dependency in enumerate(step.dependencies):
        targets.extend(
            [
                AssertionTarget(
                    f"{prefix}.dependencies[{index}].target_label",
                    f"Dependency {index + 1} target",
                    dependency.target_label,
                    **context,
                ),
                AssertionTarget(
                    f"{prefix}.dependencies[{index}].relationship",
                    f"Dependency {index + 1} relationship",
                    dependency.relationship,
                    **context,
                ),
            ]
        )
    targets.extend(
        AssertionTarget(
            f"{prefix}.criteria[{index}]",
            item.name.value.replace("_", " ").title(),
            item.assertion,
            **context,
        )
        for index, item in enumerate(step.criteria)
    )
    targets.append(
        AssertionTarget(
            f"{prefix}.human_accountability_required",
            "Human accountability required",
            step.human_accountability_required,
            **context,
        )
    )
    targets.extend(
        AssertionTarget(
            f"{prefix}.capability_signals[{index}]",
            item.name.replace("_", " ").title(),
            item.assertion,
            **context,
        )
        for index, item in enumerate(step.capability_signals)
    )
    return targets


def document_supported_unreviewed(
    targets: list[AssertionTarget],
) -> list[AssertionTarget]:
    return [
        item
        for item in targets
        if item.assertion.retained
        and item.assertion.knowledge_state is KnowledgeState.KNOWN
        and item.assertion.origin is InformationOrigin.DOCUMENT_SUPPORTED
        and item.assertion.disposition is ReviewDisposition.UNREVIEWED
    ]


def inferred_unreviewed(session: ProcessReviewSession) -> list[AssertionTarget]:
    targets = iter_process_assertions(session)
    for step in session.steps:
        targets.extend(iter_step_assertions(session, step.candidate_step_id))
    return [
        item
        for item in targets
        if item.assertion.retained
        and item.assertion.origin is InformationOrigin.MODEL_INFERRED
        and item.assertion.disposition is ReviewDisposition.UNREVIEWED
    ]


def unknown_unreviewed_by_step(session: ProcessReviewSession) -> dict[str, int]:
    return {
        step.candidate_step_id: sum(
            item.assertion.knowledge_state is KnowledgeState.UNKNOWN
            and item.assertion.disposition is ReviewDisposition.UNREVIEWED
            for item in iter_step_assertions(session, step.candidate_step_id)
        )
        for step in session.steps
        if step.retained
    }


def _base_item_id(error: ApprovalError) -> str:
    """Return the historical, non-disambiguated identifier for one requirement."""

    return f"{error.code}:{error.field_path or 'process'}"


def _item_ids(errors: list[ApprovalError]) -> list[str]:
    """Keep every already-unique identifier and disambiguate only collisions.

    Two approval errors can share a code and field path - for example two
    blocking structural conflicts recorded against the process itself.  Only
    those colliding identifiers receive a deterministic ``:<occurrence>``
    suffix, numbered in Phase 4 error order.  An identifier that is already
    unique is returned exactly as earlier revisions produced it, so persisted
    bookmarks and established widget keys keep working.
    """

    base_ids = [_base_item_id(error) for error in errors]
    counts = Counter(base_ids)
    occurrences: dict[str, int] = {}
    item_ids: list[str] = []
    for base_id in base_ids:
        if counts[base_id] == 1:
            item_ids.append(base_id)
            continue
        occurrence = occurrences.get(base_id, 0)
        occurrences[base_id] = occurrence + 1
        item_ids.append(f"{base_id}:{occurrence}")
    return item_ids


def _outstanding_item(
    session: ProcessReviewSession,
    error: ApprovalError,
    *,
    item_id: str,
) -> OutstandingReviewItem:
    step_id = _step_id(error.field_path)
    step = next(
        (item for item in session.steps if item.candidate_step_id == step_id),
        None,
    )
    labels = {
        "process-identity-unconfirmed": ("Process name", "Accept or correct the process name."),
        "step-order-unconfirmed": ("Step order", "Accept the displayed process-step order."),
        "step-activity-unconfirmed": ("Activity", "Accept or correct this retained activity."),
        "no-retained-steps": ("Retained activities", "Retain at least one process activity."),
        "invalid-retained-dependency": (
            "Dependency",
            "Choose another retained step as the target, or reject the dependency.",
        ),
        "unresolved-structural-conflict": (
            "Structural conflict",
            "Resolve the blocking structural conflict.",
        ),
        "invalid-phase1-projection": (
            "Validated process",
            "Correct the affected field so the validated process can be constructed safely.",
        ),
        "review-already-approved": ("Review status", error.message),
    }
    field_label, reason = labels.get(error.code, ("Review requirement", error.message))
    return OutstandingReviewItem(
        item_id=item_id,
        field_path=error.field_path,
        field_label=field_label,
        reason=reason,
        step_id=step_id,
        step_sequence=step.sequence if step else None,
        activity=str(step.activity.value or "Unknown activity") if step else None,
    )


def _step_id(field_path: str | None) -> str | None:
    if not field_path or not field_path.startswith("steps."):
        return None
    parts = field_path.split(".")
    return parts[1] if len(parts) > 1 else None

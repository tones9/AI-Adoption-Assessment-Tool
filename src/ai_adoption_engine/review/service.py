"""Controlled human-review operations with an append-only audit trail."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ai_adoption_engine.models.candidate_process import (
    CandidateAssertion,
    CollectionCompleteness,
    ResolvedEvidenceReference,
)
from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.models.extraction import (
    CandidateExtractionResult,
    ExtractionIssue,
    ExtractionIssueSeverity,
)
from ai_adoption_engine.models.review import (
    ConflictStatus,
    InformationOrigin,
    ProcessReviewSession,
    ReviewAction,
    ReviewConflict,
    ReviewDisposition,
    ReviewedAssertion,
    ReviewedCollection,
    ReviewEvent,
    reviewed_assertion,
    reviewed_step,
)


Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]

_STRUCTURAL_ISSUE_CODES = {
    "ambiguous-dependency",
    "multiple-processes-detected",
    "ordering-conflict",
    "possible-duplicate-step",
    "self-dependency",
    "step-activity-unverified",
}


def _default_id_factory(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


class ProcessReviewService:
    """Build and update review sessions without invoking assessment logic."""

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        self.clock = clock or (lambda: datetime.now(UTC))
        self.id_factory = id_factory or _default_id_factory

    def start_review(self, result: CandidateExtractionResult) -> ProcessReviewSession:
        if result.candidate is None:
            raise ValueError("A failed extraction cannot start human review")
        now = self.clock()
        conflicts = [
            ReviewConflict(
                conflict_id=self.id_factory("conflict"),
                code=issue.code,
                message=issue.message,
                blocking=_issue_is_blocking(issue),
                field_path=issue.field_path,
            )
            for issue in result.issues
            if _issue_is_blocking(issue)
        ]
        candidate = result.candidate
        return ProcessReviewSession(
            review_id=self.id_factory("review"),
            created_at=now,
            updated_at=now,
            original_candidate=candidate,
            extraction_issues=result.issues,
            process_name=reviewed_assertion(candidate.process_name),
            process_description=reviewed_assertion(candidate.process_description),
            process_objective=reviewed_assertion(candidate.process_objective),
            steps=[reviewed_step(step) for step in candidate.steps],
            conflicts=conflicts,
        )

    def accept_assertion(
        self,
        session: ProcessReviewSession,
        assertion: ReviewedAssertion,
        field_path: str,
        *,
        rationale: str | None = None,
    ) -> None:
        if assertion.knowledge_state is KnowledgeState.UNKNOWN:
            raise ValueError("Unknown assertions must be resolved or explicitly retained")
        before = assertion.model_dump(mode="json")
        assertion.disposition = ReviewDisposition.ACCEPTED
        assertion.retained = True
        self._record(
            session, ReviewAction.ACCEPT, field_path, before, assertion, rationale
        )

    def correct_assertion(
        self,
        session: ProcessReviewSession,
        assertion: ReviewedAssertion,
        field_path: str,
        value: Any,
        *,
        rationale: str,
        origin: InformationOrigin = InformationOrigin.HUMAN_SUPPLIED,
        evidence: list[ResolvedEvidenceReference] | None = None,
    ) -> None:
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("A corrected value must be non-empty")
        supplied_evidence = list(evidence or [])
        if origin is InformationOrigin.HUMAN_SUPPLIED and supplied_evidence:
            raise ValueError("Human-supplied corrections cannot claim document evidence")
        if origin is InformationOrigin.DOCUMENT_SUPPORTED:
            if not supplied_evidence:
                raise ValueError("Document-supported corrections require source evidence")
            if any(
                item.document_id != session.original_candidate.source_document_id
                for item in supplied_evidence
            ):
                raise ValueError("Correction evidence must belong to the reviewed document")
        elif origin is not InformationOrigin.HUMAN_SUPPLIED:
            raise ValueError(
                "Corrections may be HUMAN_SUPPLIED or DOCUMENT_SUPPORTED"
            )
        before = assertion.model_dump(mode="json")
        assertion.value = value
        assertion.knowledge_state = KnowledgeState.KNOWN
        assertion.origin = origin
        assertion.rationale = rationale
        assertion.evidence = supplied_evidence
        assertion.confidence = None
        assertion.disposition = ReviewDisposition.CORRECTED
        assertion.retained = True
        self._record(
            session, ReviewAction.CORRECT, field_path, before, assertion, rationale
        )

    def resolve_unknown(
        self,
        session: ProcessReviewSession,
        assertion: ReviewedAssertion,
        field_path: str,
        value: Any,
        *,
        rationale: str,
        origin: InformationOrigin = InformationOrigin.HUMAN_SUPPLIED,
        evidence: list[ResolvedEvidenceReference] | None = None,
    ) -> None:
        """Resolve an unknown assertion, optionally citing source evidence.

        ``origin`` and ``evidence`` are forwarded unchanged to
        :meth:`correct_assertion`, which owns every provenance rule. The defaults
        reproduce the original human-supplied behaviour, so existing callers are
        unaffected. The recorded action remains ``RESOLVE_UNKNOWN``.
        """

        if assertion.knowledge_state is not KnowledgeState.UNKNOWN:
            raise ValueError("Only an unknown assertion can be resolved as unknown")
        before = assertion.model_dump(mode="json")
        self.correct_assertion(
            session,
            assertion,
            field_path,
            value,
            rationale=rationale,
            origin=origin,
            evidence=evidence,
        )
        session.events.pop()
        self._record(
            session,
            ReviewAction.RESOLVE_UNKNOWN,
            field_path,
            before,
            assertion,
            rationale,
        )

    def retain_unknown(
        self,
        session: ProcessReviewSession,
        assertion: ReviewedAssertion,
        field_path: str,
        *,
        rationale: str | None = None,
    ) -> None:
        if assertion.knowledge_state is not KnowledgeState.UNKNOWN:
            raise ValueError("Only an unknown assertion can be retained as unknown")
        before = assertion.model_dump(mode="json")
        assertion.disposition = ReviewDisposition.UNKNOWN_RETAINED
        assertion.retained = True
        self._record(
            session,
            ReviewAction.RETAIN_UNKNOWN,
            field_path,
            before,
            assertion,
            rationale,
        )

    def reject_assertion(
        self,
        session: ProcessReviewSession,
        assertion: ReviewedAssertion,
        field_path: str,
        *,
        rationale: str,
    ) -> None:
        before = assertion.model_dump(mode="json")
        assertion.disposition = ReviewDisposition.REJECTED
        assertion.retained = False
        self._record(
            session, ReviewAction.REJECT, field_path, before, assertion, rationale
        )

    def add_human_collection_item(
        self,
        session: ProcessReviewSession,
        collection: ReviewedCollection,
        field_path: str,
        value: Any,
        *,
        rationale: str,
    ) -> ReviewedAssertion:
        original = CandidateAssertion[Any](
            value=None,
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="This item was absent from the extraction.",
        )
        item = reviewed_assertion(original)
        collection.items.append(item)
        collection.completeness = CollectionCompleteness.PARTIAL
        self.resolve_unknown(
            session,
            item,
            f"{field_path}.items[{len(collection.items) - 1}]",
            value,
            rationale=rationale,
        )
        return item

    def reorder_steps(
        self, session: ProcessReviewSession, ordered_step_ids: list[str], *, rationale: str
    ) -> None:
        retained = [step for step in session.steps if step.retained]
        expected = {step.candidate_step_id for step in retained}
        if len(ordered_step_ids) != len(set(ordered_step_ids)) or set(
            ordered_step_ids
        ) != expected:
            raise ValueError("Reordering must include every retained step exactly once")
        before = {"step_ids": [step.candidate_step_id for step in retained]}
        by_id = {step.candidate_step_id: step for step in retained}
        reordered = [by_id[item] for item in ordered_step_ids]
        for sequence, step in enumerate(reordered, start=1):
            step.sequence = sequence
        rejected = [step for step in session.steps if not step.retained]
        session.steps = reordered + rejected
        session.order_accepted = False
        self._record(
            session,
            ReviewAction.REORDER_STEPS,
            "process.steps.order",
            before,
            {"step_ids": ordered_step_ids},
            rationale,
        )

    def remove_step(
        self,
        session: ProcessReviewSession,
        step_id: str,
        *,
        rationale: str,
    ) -> None:
        step = self._step(session, step_id)
        before = step.model_dump(mode="json")
        step.retained = False
        session.order_accepted = False
        self._record(
            session,
            ReviewAction.REJECT,
            f"steps.{step_id}",
            before,
            step,
            rationale,
        )

    def accept_step_order(
        self, session: ProcessReviewSession, *, rationale: str | None = None
    ) -> None:
        before = {"order_accepted": session.order_accepted}
        session.order_accepted = True
        self._record(
            session,
            ReviewAction.ACCEPT_STEP_ORDER,
            "process.steps.order",
            before,
            {"order_accepted": True},
            rationale,
        )

    def correct_dependency(
        self,
        session: ProcessReviewSession,
        step_id: str,
        dependency_index: int,
        target_step_id: str | None,
        *,
        rationale: str,
    ) -> None:
        step = self._step(session, step_id)
        dependency = step.dependencies[dependency_index]
        before = dependency.model_dump(mode="json")
        dependency.target_candidate_step_id = target_step_id
        self._record(
            session,
            ReviewAction.CORRECT_DEPENDENCY,
            f"steps.{step_id}.dependencies[{dependency_index}]",
            before,
            dependency,
            rationale,
        )

    def reject_dependency(
        self,
        session: ProcessReviewSession,
        step_id: str,
        dependency_index: int,
        *,
        rationale: str,
    ) -> None:
        step = self._step(session, step_id)
        dependency = step.dependencies[dependency_index]
        before = dependency.model_dump(mode="json")
        dependency.retained = False
        self._record(
            session,
            ReviewAction.REJECT,
            f"steps.{step_id}.dependencies[{dependency_index}]",
            before,
            dependency,
            rationale,
        )

    def select_primary_actor(
        self,
        session: ProcessReviewSession,
        step_id: str,
        actor: str | None,
        *,
        rationale: str | None = None,
    ) -> None:
        step = self._step(session, step_id)
        retained_actors = [item.value for item in step.actors.items if item.retained]
        if actor is not None and actor not in retained_actors:
            raise ValueError("Primary actor must be a retained reviewed actor")
        before = {"primary_actor": step.primary_actor}
        step.primary_actor = actor
        self._record(
            session,
            ReviewAction.SELECT_PRIMARY_ACTOR,
            f"steps.{step_id}.primary_actor",
            before,
            {"primary_actor": actor},
            rationale,
        )

    def resolve_conflict(
        self, session: ProcessReviewSession, conflict_id: str, *, resolution: str
    ) -> None:
        conflict = next(
            (item for item in session.conflicts if item.conflict_id == conflict_id),
            None,
        )
        if conflict is None:
            raise ValueError("Unknown review conflict")
        before = conflict.model_dump(mode="json")
        conflict.status = ConflictStatus.RESOLVED
        conflict.resolution = resolution
        self._record(
            session,
            ReviewAction.RESOLVE_CONFLICT,
            f"conflicts.{conflict_id}",
            before,
            conflict,
            resolution,
        )

    def _step(self, session: ProcessReviewSession, step_id: str):
        step = next(
            (item for item in session.steps if item.candidate_step_id == step_id), None
        )
        if step is None:
            raise ValueError("Unknown reviewed step")
        return step

    def _record(
        self,
        session: ProcessReviewSession,
        action: ReviewAction,
        field_path: str,
        before: dict[str, Any] | None,
        after: Any,
        rationale: str | None,
    ) -> None:
        now = self.clock()
        after_dump = (
            after.model_dump(mode="json")
            if hasattr(after, "model_dump")
            else after
        )
        session.events.append(
            ReviewEvent(
                event_id=self.id_factory("event"),
                sequence=len(session.events) + 1,
                occurred_at=now,
                action=action,
                field_path=field_path,
                before_snapshot=(
                    json.dumps(before, sort_keys=True, separators=(",", ":"))
                    if before is not None
                    else None
                ),
                after_snapshot=(
                    json.dumps(after_dump, sort_keys=True, separators=(",", ":"))
                    if after_dump is not None
                    else None
                ),
                rationale=rationale,
            )
        )
        session.updated_at = now


def _issue_is_blocking(issue: ExtractionIssue) -> bool:
    if issue.code in _STRUCTURAL_ISSUE_CODES:
        return True
    path = issue.field_path or ""
    if issue.code == "process-field-conflict":
        return path == "process_name"
    if issue.severity is not ExtractionIssueSeverity.ERROR:
        return False
    if ".characteristics." in path:
        return False
    if any(
        name in path
        for name in (
            ".actors",
            ".responsible_roles",
            ".systems",
            ".inputs",
            ".outputs",
            ".exceptions",
            ".operational_characteristics",
            "process_description",
            "process_objective",
        )
    ):
        return False
    return True

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_adoption_engine.models.enums import CriterionName
from ai_adoption_engine.models.review import (
    ConflictStatus,
    InformationOrigin,
    ReviewConflict,
)
from ai_adoption_engine.presentation.review_journey import build_review_journey
from ai_adoption_engine.presentation.review_progress import (
    iter_process_assertions,
    iter_step_assertions,
)
from ai_adoption_engine.workspace.composition import build_workspace_service
from ai_adoption_engine.workspace.demo_extraction import demo_text
from ai_adoption_engine.workspace.models import ExecutionMode


_GENERATED_IDENTIFIERS_AND_TIMESTAMPS = {
    "approval_event_id",
    "approved_at",
    "assessed_at",
    "assessment_run_id",
    "created_at",
    "current_state_process_id",
    "event_id",
    "extraction_run_id",
    "integrated_assessment_run_id",
    "occurred_at",
    "package_id",
    "process_id",
    "review_id",
    "updated_at",
    "validated_process_id",
}
_P2_GROUP_CONFIRMATION_RATIONALE = (
    "Confirmed in a grouped review of document-supported facts."
)


def _new_review(path: Path):
    service = build_workspace_service(path)
    assessment = service.repository.create_assessment("P2 equivalence", ExecutionMode.OFFLINE_DEMO)
    service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    service.extract(assessment.assessment_id)
    return service, assessment.assessment_id, service.start_review(assessment.assessment_id)


def _accept_documented_direct(service, session) -> None:
    """The original detailed path confirms each documented assertion separately."""

    for target in iter_process_assertions(session):
        if target.assertion.origin is InformationOrigin.DOCUMENT_SUPPORTED:
            service.review_service.accept_assertion(session, target.assertion, target.field_path)
    for step in session.steps:
        for target in iter_step_assertions(session, step.candidate_step_id):
            if target.assertion.origin is InformationOrigin.DOCUMENT_SUPPORTED:
                service.review_service.accept_assertion(session, target.assertion, target.field_path)


def _accept_documented_guided(service, session) -> None:
    """The P2 grouping selects fields, then uses the same Phase 4 action once each."""

    for group in build_review_journey(session).document_groups:
        targets = (
            iter_process_assertions(session)
            if group.step_id is None
            else iter_step_assertions(session, group.step_id)
        )
        by_path = {target.field_path: target for target in targets}
        for field_path in group.field_paths:
            service.review_service.accept_assertion(
                session,
                by_path[field_path].assertion,
                field_path,
                rationale=_P2_GROUP_CONFIRMATION_RATIONALE,
            )


def _apply_shared_human_decisions(service, session) -> None:
    """Exercise existing Phase 4 operations available from both P2 and the old page."""

    first, second, dependent = session.steps[:3]
    session.conflicts.append(
        ReviewConflict(
            conflict_id="synthetic-structure-conflict",
            code="synthetic-structure-conflict",
            message="Synthetic fixture requires an explicit structural decision.",
            blocking=True,
            field_path="process.steps",
            status=ConflictStatus.OPEN,
        )
    )

    service.review_service.correct_assertion(
        session,
        session.process_description,
        "process.description",
        "Reviewer-confirmed description of the complaint workflow.",
        rationale="The process owner provided a clearer current-state description.",
    )
    service.review_service.add_human_collection_item(
        session,
        first.systems,
        f"steps.{first.candidate_step_id}.systems",
        "Customer correspondence queue",
        rationale="The process owner identified the queue used alongside the case system.",
    )

    criteria = {item.name: item.assertion for item in first.criteria}
    service.review_service.resolve_unknown(
        session,
        criteria[CriterionName.DATA_READINESS],
        f"steps.{first.candidate_step_id}.criteria[2]",
        3,
        rationale="The documented case-management workflow supports a limited readiness value.",
        origin=InformationOrigin.DOCUMENT_SUPPORTED,
        evidence=list(first.activity.evidence),
    )
    service.review_service.resolve_unknown(
        session,
        criteria[CriterionName.HUMAN_JUDGEMENT_REQUIREMENT],
        f"steps.{first.candidate_step_id}.criteria[4]",
        4,
        rationale="The process owner described the judgement required when reviewing complaints.",
    )
    service.review_service.retain_unknown(
        session,
        criteria[CriterionName.BUSINESS_VALUE],
        f"steps.{first.candidate_step_id}.criteria[5]",
        rationale="No trustworthy current business-value estimate was provided.",
    )

    capability = next(
        item
        for item in first.capability_signals
        if item.name == "categorises_items"
    )
    service.review_service.resolve_unknown(
        session,
        capability.assertion,
        f"steps.{first.candidate_step_id}.capability_signals[1]",
        True,
        rationale="The process owner confirmed that complaint categories are used.",
    )

    # The original candidate maps this dependency to the immediately preceding
    # activity. The reviewer deliberately corrects it to the first retained step.
    service.review_service.correct_dependency(
        session,
        dependent.candidate_step_id,
        0,
        first.candidate_step_id,
        rationale="The review meeting clarified that intake recording is the dependency.",
    )
    service.review_service.resolve_conflict(
        session,
        "synthetic-structure-conflict",
        resolution="The review meeting confirmed one current-state complaint workflow.",
    )

    ordered = [second.candidate_step_id, first.candidate_step_id] + [
        step.candidate_step_id for step in session.steps[2:]
    ]
    service.review_service.reorder_steps(
        session,
        ordered,
        rationale="The review meeting corrected the first two activity positions.",
    )
    service.review_service.accept_step_order(
        session,
        rationale="The corrected retained activity order was explicitly accepted.",
    )


def _apply_review_decisions(service, session, *, guided: bool) -> None:
    if guided:
        _accept_documented_guided(service, session)
    else:
        _accept_documented_direct(service, session)
    _apply_shared_human_decisions(service, session)


def _canonical(value: Any) -> Any:
    """Remove only generated IDs/timestamps and P2's truthful group-action wording."""

    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if not isinstance(value, dict):
        return value

    event_is_document_acceptance = value.get("action") == "accept"
    normalised: dict[str, Any] = {}
    for key, item in value.items():
        if key in _GENERATED_IDENTIFIERS_AND_TIMESTAMPS:
            continue
        # The old page records no rationale for individual acceptance while P2
        # records the truthful grouped-confirmation wording. It has no effect on
        # the reviewed assertion, provenance, approval, assessment, or package.
        if event_is_document_acceptance and key == "rationale":
            continue
        normalised[key] = _canonical(item)
    return normalised


def _approved_review_semantics(approved) -> dict[str, Any]:
    return _canonical(approved.model_dump(mode="json"))


def _assessment_semantics(result) -> dict[str, Any]:
    return _canonical(result.model_dump(mode="json"))


def _package_semantics(result) -> dict[str, Any]:
    return _canonical(result.package.model_dump(mode="json"))


def test_guided_phase4_actions_are_semantically_and_downstream_equivalent(tmp_path: Path) -> None:
    old_service, old_id, old_review = _new_review(tmp_path / "old.db")
    guided_service, guided_id, guided_review = _new_review(tmp_path / "guided.db")

    _apply_review_decisions(old_service, old_review, guided=False)
    _apply_review_decisions(guided_service, guided_review, guided=True)
    old_service.save_review(old_id, old_review)
    guided_service.save_review(guided_id, guided_review)
    old_approved = old_service.approve(
        old_id, rationale="Explicit approval of the reviewed current-state process."
    ).approved
    guided_approved = guided_service.approve(
        guided_id, rationale="Explicit approval of the reviewed current-state process."
    ).approved

    assert old_approved is not None and guided_approved is not None
    assert _approved_review_semantics(old_approved) == _approved_review_semantics(
        guided_approved
    )

    old_assessment = old_service.assess(old_id)
    guided_assessment = guided_service.assess(guided_id)
    assert _assessment_semantics(old_assessment) == _assessment_semantics(guided_assessment)

    old_package = old_service.generate_package(old_id)
    guided_package = guided_service.generate_package(guided_id)
    assert _package_semantics(old_package) == _package_semantics(guided_package)

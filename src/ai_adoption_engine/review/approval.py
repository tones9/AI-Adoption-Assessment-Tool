"""Explicit candidate-review approval and Phase 1 projection boundary."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from ai_adoption_engine.models.candidate_process import ResolvedEvidenceReference
from ai_adoption_engine.models.enums import KnowledgeState, UncertaintyStatus
from ai_adoption_engine.models.evidence import (
    BooleanCriterionInput,
    CriterionInput,
    EvidenceReference,
)
from ai_adoption_engine.models.process import (
    BusinessProcess,
    CapabilitySignalInput,
    CapabilitySignals,
    ProcessStep,
    TaskCharacteristics,
)
from ai_adoption_engine.models.review import (
    ApprovalError,
    ApprovalResult,
    ApprovedProcessReview,
    ConflictStatus,
    ExplicitApproval,
    InformationOrigin,
    ProcessReviewSession,
    ReviewAction,
    ReviewDisposition,
    ReviewEvent,
    ReviewedAssertion,
    ReviewedCollection,
    ReviewedProcessStep,
    ReviewStatus,
)


def approve_review(
    session: ProcessReviewSession,
    approval: ExplicitApproval | None,
) -> ApprovalResult:
    """Validate explicit human approval and construct the narrow Phase 1 model."""

    errors = _approval_errors(session, approval)
    if errors:
        return ApprovalResult(errors=errors)
    assert approval is not None

    try:
        business_process = _project_business_process(session)
    except ValidationError as exc:
        return ApprovalResult(
            errors=[
                ApprovalError(
                    code="invalid-phase1-projection",
                    message="The reviewed process does not satisfy the Phase 1 contract.",
                    field_path=".".join(str(item) for item in error["loc"]),
                )
                for error in exc.errors(include_url=False, include_input=False)
            ]
        )

    snapshot = session.model_copy(deep=True)
    snapshot.status = ReviewStatus.APPROVED
    snapshot.updated_at = approval.approved_at
    snapshot.events.append(
        ReviewEvent(
            event_id=f"approval-{len(snapshot.events) + 1}",
            sequence=len(snapshot.events) + 1,
            occurred_at=approval.approved_at,
            action=ReviewAction.APPROVE,
            field_path="process",
            before_snapshot=json.dumps({"status": session.status.value}),
            after_snapshot=json.dumps({"status": ReviewStatus.APPROVED.value}),
            rationale=approval.rationale,
        )
    )
    return ApprovalResult(
        approved=ApprovedProcessReview(
            approval=approval,
            review=snapshot,
            business_process=business_process,
        )
    )


def _approval_errors(
    session: ProcessReviewSession, approval: ExplicitApproval | None
) -> list[ApprovalError]:
    errors: list[ApprovalError] = []
    if approval is None:
        errors.append(
            ApprovalError(
                code="explicit-approval-required",
                message="An explicit human approval action is required.",
            )
        )
    if session.status is ReviewStatus.APPROVED:
        errors.append(
            ApprovalError(
                code="review-already-approved",
                message="This review session is already approved.",
            )
        )
    if not _confirmed(session.process_name):
        errors.append(
            ApprovalError(
                code="process-identity-unconfirmed",
                message="The process name must be accepted or corrected.",
                field_path="process.name",
            )
        )
    retained_steps = [step for step in session.steps if step.retained]
    if not retained_steps:
        errors.append(
            ApprovalError(
                code="no-retained-steps",
                message="At least one reviewed process step must be retained.",
                field_path="process.steps",
            )
        )
    if not session.order_accepted:
        errors.append(
            ApprovalError(
                code="step-order-unconfirmed",
                message="The retained step ordering must be explicitly accepted.",
                field_path="process.steps.order",
            )
        )
    for step in retained_steps:
        path = f"steps.{step.candidate_step_id}"
        if not _confirmed(step.activity):
            errors.append(
                ApprovalError(
                    code="step-activity-unconfirmed",
                    message="Each retained step requires an accepted or corrected activity.",
                    field_path=f"{path}.activity",
                )
            )
        for index, dependency in enumerate(step.dependencies):
            if not dependency.retained:
                continue
            target = dependency.target_candidate_step_id
            retained_ids = {item.candidate_step_id for item in retained_steps}
            if target is None or target not in retained_ids or target == step.candidate_step_id:
                errors.append(
                    ApprovalError(
                        code="invalid-retained-dependency",
                        message="A retained dependency must target another retained step.",
                        field_path=f"{path}.dependencies[{index}]",
                    )
                )
    errors.extend(
        ApprovalError(
            code="unresolved-structural-conflict",
            message=conflict.message,
            field_path=conflict.field_path,
        )
        for conflict in session.conflicts
        if conflict.blocking and conflict.status is ConflictStatus.OPEN
    )
    return errors


def _confirmed(assertion: ReviewedAssertion) -> bool:
    return (
        assertion.retained
        and assertion.value is not None
        and assertion.disposition
        in {ReviewDisposition.ACCEPTED, ReviewDisposition.CORRECTED}
    )


def _project_business_process(session: ProcessReviewSession) -> BusinessProcess:
    retained_steps = sorted(
        (step for step in session.steps if step.retained), key=lambda item: item.sequence
    )
    evidence_by_id: dict[str, EvidenceReference] = {}
    projected_steps = [
        _project_step(step, evidence_by_id) for step in retained_steps
    ]
    _collect_assertion_evidence(session.process_name, evidence_by_id)
    _collect_assertion_evidence(session.process_description, evidence_by_id)
    _collect_assertion_evidence(session.process_objective, evidence_by_id)
    return BusinessProcess(
        process_id=f"validated-{session.original_candidate.extraction_run_id}",
        name=str(session.process_name.value),
        description=_optional_text(session.process_description),
        business_objective=_optional_text(session.process_objective),
        organisation=None,
        evidence=list(evidence_by_id.values()),
        steps=projected_steps,
    )


def _project_step(
    step: ReviewedProcessStep,
    evidence_by_id: dict[str, EvidenceReference],
) -> ProcessStep:
    assertion_evidence: set[str] = set()
    for assertion in (
        step.activity,
        step.description,
        step.document_order,
        step.human_accountability_required,
    ):
        assertion_evidence.update(_collect_assertion_evidence(assertion, evidence_by_id))
    for collection in (
        step.actors,
        step.responsible_roles,
        step.systems,
        step.inputs,
        step.outputs,
        step.exceptions,
        step.operational_characteristics,
    ):
        assertion_evidence.update(_collect_collection_evidence(collection, evidence_by_id))
    for decision in step.decisions:
        if decision.retained:
            assertion_evidence.update(
                _collect_assertion_evidence(decision.condition, evidence_by_id)
            )
            assertion_evidence.update(
                _collect_collection_evidence(decision.branches, evidence_by_id)
            )
    for dependency in step.dependencies:
        if dependency.retained:
            assertion_evidence.update(
                _collect_assertion_evidence(dependency.target_label, evidence_by_id)
            )
            assertion_evidence.update(
                _collect_assertion_evidence(dependency.relationship, evidence_by_id)
            )

    criteria = {}
    for item in step.criteria:
        criteria[item.name.value] = _criterion(item.assertion, evidence_by_id)
    accountability = _boolean(step.human_accountability_required, evidence_by_id)
    signal_values = {
        item.name: _capability_signal(item.assertion, evidence_by_id)
        for item in step.capability_signals
    }
    characteristics = TaskCharacteristics(
        **criteria,
        human_accountability_required=accountability,
        capability_signals=CapabilitySignals(**signal_values),
    )
    dependencies = [
        item.target_candidate_step_id
        for item in step.dependencies
        if item.retained and item.target_candidate_step_id is not None
    ]
    return ProcessStep(
        step_id=step.candidate_step_id,
        sequence=step.sequence,
        activity=str(step.activity.value),
        description=_optional_text(step.description),
        actor=step.primary_actor,
        responsible_role=_first_collection_value(step.responsible_roles),
        systems=_collection_values(step.systems),
        inputs=_collection_values(step.inputs),
        outputs=_collection_values(step.outputs),
        dependencies=dependencies,
        exceptions=_collection_values(step.exceptions),
        evidence_ids=sorted(assertion_evidence),
        characteristics=characteristics,
    )


def _criterion(
    assertion: ReviewedAssertion,
    evidence_by_id: dict[str, EvidenceReference],
) -> CriterionInput:
    if not assertion.retained or assertion.value is None:
        return CriterionInput(
            value=None,
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale=_unknown_rationale(assertion),
        )
    return CriterionInput(
        value=int(assertion.value),
        knowledge_state=assertion.knowledge_state,
        rationale=assertion.rationale,
        evidence_ids=_collect_assertion_evidence(assertion, evidence_by_id),
        confidence=assertion.confidence,
    )


def _boolean(
    assertion: ReviewedAssertion,
    evidence_by_id: dict[str, EvidenceReference],
) -> BooleanCriterionInput:
    data = _boolean_data(assertion, evidence_by_id)
    return BooleanCriterionInput(**data)


def _capability_signal(
    assertion: ReviewedAssertion,
    evidence_by_id: dict[str, EvidenceReference],
) -> CapabilitySignalInput:
    data = _boolean_data(assertion, evidence_by_id)
    return CapabilitySignalInput(**data)


def _boolean_data(
    assertion: ReviewedAssertion,
    evidence_by_id: dict[str, EvidenceReference],
) -> dict[str, Any]:
    if not assertion.retained or assertion.value is None:
        return {
            "value": None,
            "knowledge_state": KnowledgeState.UNKNOWN,
            "rationale": _unknown_rationale(assertion),
            "evidence_ids": [],
            "confidence": None,
        }
    return {
        "value": bool(assertion.value),
        "knowledge_state": assertion.knowledge_state,
        "rationale": assertion.rationale,
        "evidence_ids": _collect_assertion_evidence(assertion, evidence_by_id),
        "confidence": assertion.confidence,
    }


def _unknown_rationale(assertion: ReviewedAssertion) -> str:
    if assertion.disposition is ReviewDisposition.REJECTED:
        return "The extracted assertion was rejected during human review."
    return assertion.rationale


def _optional_text(assertion: ReviewedAssertion) -> str | None:
    if not assertion.retained or assertion.value is None:
        return None
    value = str(assertion.value)
    return value if value.strip() else None


def _collection_values(collection: ReviewedCollection) -> list[str]:
    return [
        str(item.value)
        for item in collection.items
        if item.retained and item.value is not None
    ]


def _first_collection_value(collection: ReviewedCollection) -> str | None:
    values = _collection_values(collection)
    return values[0] if values else None


def _collect_collection_evidence(
    collection: ReviewedCollection,
    evidence_by_id: dict[str, EvidenceReference],
) -> list[str]:
    identifiers: list[str] = []
    for reference in collection.evidence:
        identifiers.append(_store_evidence(reference, evidence_by_id))
    for item in collection.items:
        identifiers.extend(_collect_assertion_evidence(item, evidence_by_id))
    return identifiers


def _collect_assertion_evidence(
    assertion: ReviewedAssertion,
    evidence_by_id: dict[str, EvidenceReference],
) -> list[str]:
    if not assertion.retained or assertion.origin is InformationOrigin.HUMAN_SUPPLIED:
        return []
    return [_store_evidence(reference, evidence_by_id) for reference in assertion.evidence]


def _store_evidence(
    reference: ResolvedEvidenceReference,
    evidence_by_id: dict[str, EvidenceReference],
) -> str:
    if reference.evidence_id not in evidence_by_id:
        evidence_by_id[reference.evidence_id] = EvidenceReference(
            evidence_id=reference.evidence_id,
            source_id=reference.document_id,
            source_locator=reference.source_locator,
            supporting_snippet=reference.exact_snippet,
            provenance="Phase 2 document-supported source evidence",
            knowledge_state=KnowledgeState.KNOWN,
            uncertainty_status=UncertaintyStatus.CERTAIN,
        )
    return reference.evidence_id

"""Conservative deterministic merge of resolved chunk candidates."""

from __future__ import annotations

import hashlib
import re

from ai_adoption_engine.extraction.evidence import (
    ResolvedChunkExtraction,
    ResolvedStepDraft,
)
from ai_adoption_engine.models.candidate_process import (
    CandidateAssertion,
    CandidateBusinessProcess,
    CandidateDependency,
    CandidateProcessStep,
    OrderBasis,
)
from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.models.extraction import (
    ExtractionIssue,
    ExtractionIssueSeverity,
)


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _earliest_position(step: ResolvedStepDraft) -> tuple[int, int]:
    references = step.activity.evidence
    if not references:
        return (10**9, 10**9)
    reference = min(
        references,
        key=lambda item: (item.document_start_offset, item.block_start_offset),
    )
    return (reference.document_start_offset, reference.block_start_offset)


def _same_supported_activity(
    left: ResolvedStepDraft, right: ResolvedStepDraft
) -> bool:
    if left.activity.value is None or right.activity.value is None:
        return False
    if _normalise(left.activity.value) != _normalise(right.activity.value):
        return False
    left_ids = {item.evidence_id for item in left.activity.evidence}
    right_ids = {item.evidence_id for item in right.activity.evidence}
    return bool(left_ids & right_ids)


def _select_process_assertion(
    values: list[CandidateAssertion[str]],
    field_name: str,
    issues: list[ExtractionIssue],
) -> CandidateAssertion[str]:
    supported = [
        item for item in values if item.knowledge_state is not KnowledgeState.UNKNOWN
    ]
    if not supported:
        return values[0]
    first = supported[0]
    different = {
        _normalise(item.value or "") for item in supported if item.value is not None
    }
    if len(different) > 1:
        issues.append(
            ExtractionIssue(
                severity=ExtractionIssueSeverity.WARNING,
                code="process-field-conflict",
                message="Conflicting supported process-level values require human review.",
                field_path=field_name,
            )
        )
    return first


def _candidate_step_id(document_id: str, step: ResolvedStepDraft) -> str:
    evidence_ids = sorted(item.evidence_id for item in step.activity.evidence)
    source = "\0".join((document_id, _normalise(step.activity.value or ""), *evidence_ids))
    return f"candidate-step-{hashlib.sha256(source.encode('utf-8')).hexdigest()[:16]}"


def merge_chunks(
    *,
    document_id: str,
    extraction_run_id: str,
    schema_version: str,
    prompt_version: str,
    chunks: list[ResolvedChunkExtraction],
) -> tuple[CandidateBusinessProcess, list[ExtractionIssue]]:
    issues: list[ExtractionIssue] = []
    if any(item.multiple_processes_detected for item in chunks):
        issues.append(
            ExtractionIssue(
                severity=ExtractionIssueSeverity.WARNING,
                code="multiple-processes-detected",
                message="The source may describe more than one process; human review is required.",
            )
        )

    retained: list[ResolvedStepDraft] = []
    for step in (item for chunk in chunks for item in chunk.steps):
        duplicate = next(
            (existing for existing in retained if _same_supported_activity(existing, step)),
            None,
        )
        if duplicate is not None:
            issues.append(
                ExtractionIssue(
                    severity=ExtractionIssueSeverity.WARNING,
                    code="duplicate-step-merged",
                    message="An overlapping duplicate candidate step was removed.",
                )
            )
            continue
        if any(
            _normalise(existing.activity.value or "")
            == _normalise(step.activity.value or "")
            for existing in retained
        ):
            issues.append(
                ExtractionIssue(
                    severity=ExtractionIssueSeverity.WARNING,
                    code="possible-duplicate-step",
                    message="Similarly named candidate steps were retained for human review.",
                )
            )
        retained.append(step)

    explicit_orders = [
        step.document_order.value
        for step in retained
        if step.document_order.knowledge_state is KnowledgeState.KNOWN
        and step.document_order.value is not None
    ]
    all_explicit = len(explicit_orders) == len(retained)
    unique_explicit = len(set(explicit_orders)) == len(explicit_orders)
    if all_explicit and unique_explicit:
        retained.sort(key=lambda item: item.document_order.value or 0)
        order_basis = OrderBasis.EXPLICIT
    else:
        if explicit_orders and not unique_explicit:
            issues.append(
                ExtractionIssue(
                    severity=ExtractionIssueSeverity.WARNING,
                    code="ordering-conflict",
                    message="Conflicting explicit step order was retained as an ambiguity.",
                )
            )
        retained.sort(key=_earliest_position)
        order_basis = OrderBasis.SOURCE_POSITION if retained else OrderBasis.UNRESOLVED

    ids = [_candidate_step_id(document_id, step) for step in retained]
    label_map: dict[str, list[str]] = {}
    for step_id, step in zip(ids, retained, strict=True):
        label_map.setdefault(_normalise(step.activity.value or ""), []).append(step_id)

    candidate_steps: list[CandidateProcessStep] = []
    for sequence, (step_id, draft) in enumerate(
        zip(ids, retained, strict=True), start=1
    ):
        dependencies: list[CandidateDependency] = []
        for dependency in draft.dependencies:
            matches = label_map.get(_normalise(dependency.target_label.value or ""), [])
            target_id = matches[0] if len(matches) == 1 else None
            if target_id is None:
                issues.append(
                    ExtractionIssue(
                        severity=ExtractionIssueSeverity.WARNING,
                        code="ambiguous-dependency",
                        message="A candidate dependency could not be resolved uniquely.",
                    )
                )
            elif target_id == step_id:
                target_id = None
                issues.append(
                    ExtractionIssue(
                        severity=ExtractionIssueSeverity.WARNING,
                        code="self-dependency",
                        message="A self-referential candidate dependency requires review.",
                    )
                )
            dependencies.append(
                dependency.model_copy(update={"target_candidate_step_id": target_id})
            )
        candidate_steps.append(
            CandidateProcessStep(
                candidate_step_id=step_id,
                sequence=sequence,
                order_basis=order_basis,
                document_order=draft.document_order,
                activity=draft.activity,
                description=draft.description,
                actors=draft.actors,
                responsible_roles=draft.responsible_roles,
                systems=draft.systems,
                inputs=draft.inputs,
                outputs=draft.outputs,
                decisions=draft.decisions,
                dependencies=dependencies,
                exceptions=draft.exceptions,
                operational_characteristics=draft.operational_characteristics,
                characteristics=draft.characteristics,
            )
        )

    candidate = CandidateBusinessProcess(
        extraction_run_id=extraction_run_id,
        source_document_id=document_id,
        schema_version=schema_version,
        prompt_version=prompt_version,
        process_name=_select_process_assertion(
            [item.process_name for item in chunks], "process_name", issues
        ),
        process_description=_select_process_assertion(
            [item.process_description for item in chunks],
            "process_description",
            issues,
        ),
        process_objective=_select_process_assertion(
            [item.process_objective for item in chunks],
            "process_objective",
            issues,
        ),
        steps=candidate_steps,
    )
    return candidate, issues

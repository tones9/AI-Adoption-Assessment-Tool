"""Resolve untrusted provider citations against the Phase 2 document contract."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TypeVar

from ai_adoption_engine.extraction.chunking import DocumentChunk
from ai_adoption_engine.models.candidate_process import (
    CandidateAssertion,
    CandidateCapabilitySignal,
    CandidateCharacteristic,
    CandidateCollection,
    CandidateDecision,
    CandidateDependency,
    CandidateOrdinalAssertion,
    CandidateTaskCharacteristics,
    ResolvedEvidenceReference,
)
from ai_adoption_engine.models.document import IngestedDocument, TextBlock
from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.models.extraction import (
    ExtractionIssue,
    ExtractionIssueSeverity,
    RawCandidateAssertion,
    RawCandidateCollection,
    RawCandidateDecision,
    RawCandidateDependency,
    RawCandidateProcessStep,
    RawCandidateTaskCharacteristics,
    RawChunkExtraction,
    RawEvidencePointer,
)


T = TypeVar("T")


@dataclass(frozen=True)
class ResolvedStepDraft:
    local_step_id: str
    document_order: CandidateAssertion[int]
    activity: CandidateAssertion[str]
    description: CandidateAssertion[str]
    actors: CandidateCollection[str]
    responsible_roles: CandidateCollection[str]
    systems: CandidateCollection[str]
    inputs: CandidateCollection[str]
    outputs: CandidateCollection[str]
    decisions: list[CandidateDecision]
    dependencies: list[CandidateDependency]
    exceptions: CandidateCollection[str]
    operational_characteristics: CandidateCollection[str]
    characteristics: CandidateTaskCharacteristics


@dataclass(frozen=True)
class ResolvedChunkExtraction:
    chunk_id: str
    process_name: CandidateAssertion[str]
    process_description: CandidateAssertion[str]
    process_objective: CandidateAssertion[str]
    steps: list[ResolvedStepDraft]
    multiple_processes_detected: bool


class EvidenceResolver:
    """The only component allowed to create trusted Phase 3 evidence offsets."""

    def __init__(self, document: IngestedDocument, chunk: DocumentChunk) -> None:
        self.document = document
        self.chunk = chunk
        self.blocks: dict[str, TextBlock] = {
            block.block_id: block for block in document.blocks
        }
        self.slices = {item.slice_id: item for item in chunk.slices}

    def resolve_pointer(
        self, pointer: RawEvidencePointer
    ) -> ResolvedEvidenceReference:
        block = self.blocks.get(pointer.block_id)
        if block is None:
            raise ValueError("unknown-block")

        starts: list[int] = []
        search_from = 0
        while True:
            start = block.extracted_text.find(pointer.exact_snippet, search_from)
            if start < 0:
                break
            starts.append(start)
            search_from = start + 1
        if not starts:
            raise ValueError("snippet-not-found")

        if pointer.occurrence is not None:
            if pointer.occurrence > len(starts):
                raise ValueError("invalid-occurrence")
            block_start = starts[pointer.occurrence - 1]
        elif pointer.slice_id is not None:
            document_slice = self.slices.get(pointer.slice_id)
            if document_slice is None or document_slice.block_id != pointer.block_id:
                raise ValueError("invalid-slice")
            matching_starts = [
                start
                for start in starts
                if start >= document_slice.block_start_offset
                and start + len(pointer.exact_snippet)
                <= document_slice.block_end_offset
            ]
            if len(matching_starts) != 1:
                raise ValueError("ambiguous-snippet")
            block_start = matching_starts[0]
        elif len(starts) == 1:
            block_start = starts[0]
        else:
            raise ValueError("ambiguous-snippet")

        block_end = block_start + len(pointer.exact_snippet)
        document_start = block.document_start_offset + block_start
        document_end = block.document_start_offset + block_end
        digest_source = "\0".join(
            (
                self.document.document_id,
                block.block_id,
                str(block_start),
                str(block_end),
                pointer.exact_snippet,
            )
        )
        evidence_id = f"cev-{hashlib.sha256(digest_source.encode('utf-8')).hexdigest()}"
        return ResolvedEvidenceReference(
            evidence_id=evidence_id,
            document_id=self.document.document_id,
            block_id=block.block_id,
            block_start_offset=block_start,
            block_end_offset=block_end,
            document_start_offset=document_start,
            document_end_offset=document_end,
            source_locator=block.source_locator,
            exact_snippet=pointer.exact_snippet,
        )

    def _unknown_assertion(
        self, rationale: str = "Provider evidence could not be verified."
    ) -> CandidateAssertion[object]:
        return CandidateAssertion(
            value=None,
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale=rationale,
            evidence=[],
            confidence=None,
        )

    def resolve_assertion(
        self,
        raw: RawCandidateAssertion[T],
        field_path: str,
    ) -> tuple[CandidateAssertion[T], list[ExtractionIssue]]:
        if raw.knowledge_state is KnowledgeState.UNKNOWN:
            return (
                CandidateAssertion(
                    value=None,
                    knowledge_state=KnowledgeState.UNKNOWN,
                    rationale=raw.rationale,
                    evidence=[],
                    confidence=None,
                ),
                [],
            )

        resolved: list[ResolvedEvidenceReference] = []
        issues: list[ExtractionIssue] = []
        for pointer in raw.evidence:
            try:
                resolved.append(self.resolve_pointer(pointer))
            except ValueError as exc:
                code = str(exc)
                issues.append(
                    ExtractionIssue(
                        severity=ExtractionIssueSeverity.ERROR,
                        code=code,
                        message="Provider evidence could not be resolved exactly.",
                        chunk_id=self.chunk.chunk_id,
                        block_id=pointer.block_id,
                        field_path=field_path,
                    )
                )
        if issues:
            unknown = self._unknown_assertion()
            return CandidateAssertion[T].model_validate(unknown.model_dump()), issues

        return (
            CandidateAssertion(
                value=raw.value,
                knowledge_state=raw.knowledge_state,
                rationale=raw.rationale,
                evidence=resolved,
                confidence=raw.confidence,
            ),
            [],
        )

    def resolve_collection(
        self,
        raw: RawCandidateCollection[T],
        field_path: str,
    ) -> tuple[CandidateCollection[T], list[ExtractionIssue]]:
        items: list[CandidateAssertion[T]] = []
        issues: list[ExtractionIssue] = []
        for index, item in enumerate(raw.items):
            resolved, item_issues = self.resolve_assertion(
                item, f"{field_path}.items[{index}]"
            )
            issues.extend(item_issues)
            if resolved.knowledge_state is not KnowledgeState.UNKNOWN:
                items.append(resolved)
        completeness = raw.completeness
        if issues and not items:
            completeness = type(raw.completeness).UNKNOWN
        elif issues:
            completeness = type(raw.completeness).PARTIAL
        return (
            CandidateCollection(
                completeness=completeness,
                rationale=raw.rationale,
                items=items,
            ),
            issues,
        )

    def resolve_characteristics(
        self,
        raw: RawCandidateTaskCharacteristics,
        field_path: str,
    ) -> tuple[CandidateTaskCharacteristics, list[ExtractionIssue]]:
        issues: list[ExtractionIssue] = []
        criteria: list[CandidateCharacteristic] = []
        for item in raw.criteria:
            assertion, item_issues = self.resolve_assertion(
                item.assertion, f"{field_path}.criteria.{item.name.value}"
            )
            issues.extend(item_issues)
            criteria.append(
                CandidateCharacteristic(
                    name=item.name,
                    assertion=CandidateOrdinalAssertion.model_validate(
                        assertion.model_dump()
                    ),
                )
            )
        accountability, accountability_issues = self.resolve_assertion(
            raw.human_accountability_required,
            f"{field_path}.human_accountability_required",
        )
        issues.extend(accountability_issues)
        signals: list[CandidateCapabilitySignal] = []
        for item in raw.capability_signals:
            assertion, item_issues = self.resolve_assertion(
                item.assertion,
                f"{field_path}.capability_signals.{item.name.value}",
            )
            issues.extend(item_issues)
            signals.append(
                CandidateCapabilitySignal(name=item.name, assertion=assertion)
            )
        return (
            CandidateTaskCharacteristics(
                criteria=criteria,
                human_accountability_required=accountability,
                capability_signals=signals,
            ),
            issues,
        )

    def resolve_step(
        self,
        raw: RawCandidateProcessStep,
        index: int,
    ) -> tuple[ResolvedStepDraft | None, list[ExtractionIssue]]:
        base = f"steps[{index}]"
        issues: list[ExtractionIssue] = []

        def assertion(value: RawCandidateAssertion[T], name: str) -> CandidateAssertion[T]:
            resolved, found = self.resolve_assertion(value, f"{base}.{name}")
            issues.extend(found)
            return resolved

        def collection(value: RawCandidateCollection[T], name: str) -> CandidateCollection[T]:
            resolved, found = self.resolve_collection(value, f"{base}.{name}")
            issues.extend(found)
            return resolved

        activity = assertion(raw.activity, "activity")
        if activity.knowledge_state is KnowledgeState.UNKNOWN:
            issues.append(
                ExtractionIssue(
                    severity=ExtractionIssueSeverity.ERROR,
                    code="step-activity-unverified",
                    message="Candidate step was discarded because its activity lacked verified evidence.",
                    chunk_id=self.chunk.chunk_id,
                    field_path=f"{base}.activity",
                )
            )
            return None, issues

        decisions: list[CandidateDecision] = []
        for decision_index, item in enumerate(raw.decisions):
            condition = assertion(
                item.condition, f"decisions[{decision_index}].condition"
            )
            branches = collection(
                item.branches, f"decisions[{decision_index}].branches"
            )
            if condition.knowledge_state is not KnowledgeState.UNKNOWN:
                decisions.append(CandidateDecision(condition=condition, branches=branches))

        dependencies: list[CandidateDependency] = []
        for dependency_index, item in enumerate(raw.dependencies):
            target = assertion(
                item.target_label,
                f"dependencies[{dependency_index}].target_label",
            )
            relationship = assertion(
                item.relationship,
                f"dependencies[{dependency_index}].relationship",
            )
            if target.knowledge_state is not KnowledgeState.UNKNOWN:
                dependencies.append(
                    CandidateDependency(
                        target_label=target,
                        relationship=relationship,
                    )
                )

        characteristics, characteristic_issues = self.resolve_characteristics(
            raw.characteristics, f"{base}.characteristics"
        )
        issues.extend(characteristic_issues)
        return (
            ResolvedStepDraft(
                local_step_id=raw.local_step_id,
                document_order=assertion(raw.document_order, "document_order"),
                activity=activity,
                description=assertion(raw.description, "description"),
                actors=collection(raw.actors, "actors"),
                responsible_roles=collection(
                    raw.responsible_roles, "responsible_roles"
                ),
                systems=collection(raw.systems, "systems"),
                inputs=collection(raw.inputs, "inputs"),
                outputs=collection(raw.outputs, "outputs"),
                decisions=decisions,
                dependencies=dependencies,
                exceptions=collection(raw.exceptions, "exceptions"),
                operational_characteristics=collection(
                    raw.operational_characteristics,
                    "operational_characteristics",
                ),
                characteristics=characteristics,
            ),
            issues,
        )

    def resolve_chunk(
        self, raw: RawChunkExtraction
    ) -> tuple[ResolvedChunkExtraction, list[ExtractionIssue]]:
        issues: list[ExtractionIssue] = []
        process_name, found = self.resolve_assertion(raw.process_name, "process_name")
        issues.extend(found)
        description, found = self.resolve_assertion(
            raw.process_description, "process_description"
        )
        issues.extend(found)
        objective, found = self.resolve_assertion(
            raw.process_objective, "process_objective"
        )
        issues.extend(found)
        steps: list[ResolvedStepDraft] = []
        for index, item in enumerate(raw.steps):
            step, found = self.resolve_step(item, index)
            issues.extend(found)
            if step is not None:
                steps.append(step)
        return (
            ResolvedChunkExtraction(
                chunk_id=self.chunk.chunk_id,
                process_name=process_name,
                process_description=description,
                process_objective=objective,
                steps=steps,
                multiple_processes_detected=raw.multiple_processes_detected,
            ),
            issues,
        )

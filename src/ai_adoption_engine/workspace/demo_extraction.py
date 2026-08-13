"""Fixture-bound offline demo provider; never analyses arbitrary documents."""

from __future__ import annotations

from pathlib import Path

from ai_adoption_engine.extraction.providers.base import (
    ExtractionRequest,
    ProviderExtractionResponse,
)
from ai_adoption_engine.ingestion.text import ingest_raw_text
from ai_adoption_engine.models.candidate_process import (
    CapabilitySignalName,
    CollectionCompleteness,
)
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.extraction import (
    ProviderInvocation,
    RawCandidateAssertion,
    RawCandidateCapabilitySignal,
    RawCandidateCharacteristic,
    RawCandidateCollection,
    RawCandidateDecision,
    RawCandidateDependency,
    RawCandidateOrdinalAssertion,
    RawCandidateProcessStep,
    RawCandidateTaskCharacteristics,
    RawChunkExtraction,
    RawEvidencePointer,
)


ROOT = Path(__file__).resolve().parents[3]
DEMO_DOCUMENT_PATH = ROOT / "data" / "demo" / "synthetic_complaint_process.txt"


class DemoDocumentMismatchError(ValueError):
    """The scripted response was requested for a non-demo document."""


def demo_text() -> str:
    return DEMO_DOCUMENT_PATH.read_text(encoding="utf-8")


def demo_document_id() -> str:
    result = ingest_raw_text(demo_text())
    assert result.document is not None
    return result.document.document_id


def _evidence(block_id: str, snippet: str) -> list[RawEvidencePointer]:
    return [
        RawEvidencePointer(
            block_id=block_id,
            exact_snippet=snippet,
            occurrence=None,
            slice_id=None,
        )
    ]


def _known(value, block_id: str, snippet: str) -> RawCandidateAssertion:
    return RawCandidateAssertion[type(value)](
        value=value,
        knowledge_state=KnowledgeState.KNOWN,
        rationale="Directly stated in the bundled synthetic source.",
        evidence=_evidence(block_id, snippet),
        confidence=None,
    )


def _unknown(value_type=str) -> RawCandidateAssertion:
    return RawCandidateAssertion[value_type](
        value=None,
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale="The bundled source does not state this information.",
        evidence=[],
        confidence=None,
    )


def _inferred(value, block_id: str, snippet: str) -> RawCandidateAssertion:
    return RawCandidateAssertion[type(value)](
        value=value,
        knowledge_state=KnowledgeState.INFERRED,
        rationale="A conservative label was inferred from the bundled source for human confirmation.",
        evidence=_evidence(block_id, snippet),
        confidence=0.82,
    )


def _unknown_collection() -> RawCandidateCollection[str]:
    return RawCandidateCollection[str](
        completeness=CollectionCompleteness.UNKNOWN,
        rationale="The bundled source does not provide a complete collection.",
        items=[],
        evidence=[],
    )


def _collection(value: str, block_id: str, snippet: str) -> RawCandidateCollection[str]:
    assertion = _known(value, block_id, snippet)
    return RawCandidateCollection[str](
        completeness=CollectionCompleteness.PARTIAL,
        rationale="The source directly identifies this item; other items may exist.",
        items=[assertion],
        evidence=assertion.evidence,
    )


def _collection_many(
    values: list[str], block_id: str, snippet: str
) -> RawCandidateCollection[str]:
    assertions = [_known(value, block_id, snippet) for value in values]
    return RawCandidateCollection[str](
        completeness=CollectionCompleteness.PARTIAL,
        rationale="The source directly identifies these items; other items may exist.",
        items=assertions,
        evidence=_evidence(block_id, snippet),
    )


def _characteristics() -> RawCandidateTaskCharacteristics:
    return RawCandidateTaskCharacteristics(
        criteria=[
            RawCandidateCharacteristic(
                name=name,
                assertion=RawCandidateOrdinalAssertion(
                    value=None,
                    knowledge_state=KnowledgeState.UNKNOWN,
                    rationale="The source does not provide enough evidence to assign this assessment value.",
                    evidence=[],
                    confidence=None,
                ),
            )
            for name in CriterionName
        ],
        human_accountability_required=_unknown(bool),
        capability_signals=[
            RawCandidateCapabilitySignal(name=name, assertion=_unknown(bool))
            for name in CapabilitySignalName
        ],
    )


def _step(
    sequence: int,
    activity: str,
    snippet: str,
    actor: str,
    *,
    system: str | None = None,
) -> RawCandidateProcessStep:
    block_id = f"t-b{sequence + 2:04d}"
    return RawCandidateProcessStep(
        local_step_id=f"demo-step-{sequence}",
        document_order=_known(sequence, block_id, snippet),
        activity=_known(activity, block_id, snippet),
        description=_known(snippet, block_id, snippet),
        actors=_collection(actor, block_id, snippet),
        responsible_roles=_collection(actor, block_id, snippet),
        systems=(
            _collection(system, block_id, snippet)
            if system
            else _unknown_collection()
        ),
        inputs=_unknown_collection(),
        outputs=_unknown_collection(),
        decisions=[],
        dependencies=[],
        exceptions=_unknown_collection(),
        operational_characteristics=_unknown_collection(),
        characteristics=_characteristics(),
    )


class ScriptedDemoExtractionProvider:
    """Deterministic provider restricted to the approved bundled fixture."""

    provider_name = "demo-scripted"
    model_name = "offline-fixture-v1"

    def extract_chunk(self, request: ExtractionRequest) -> ProviderExtractionResponse:
        if request.document_id != demo_document_id():
            raise DemoDocumentMismatchError(
                "Offline scripted extraction is available only for the bundled demo document."
            )
        if request.chunk.sequence != 1 or request.chunk.has_next:
            raise DemoDocumentMismatchError(
                "The bundled demo fixture must resolve to one extraction chunk."
            )
        paragraphs = [item.text for item in request.chunk.slices]
        if len(paragraphs) != 9:
            raise DemoDocumentMismatchError("The bundled demo document fingerprint changed.")
        steps = [
            _step(1, "Record the complaint", paragraphs[2], "Customer service agent", system="Case Management System"),
            _step(2, "Categorise complaint and check required information", paragraphs[3], "Customer service agent"),
            _step(3, "Review the categorised complaint", paragraphs[4], "Complaints manager"),
            _step(4, "Determine whether specialist review is required", paragraphs[5], "Complaints manager"),
            _step(5, "Draft a proposed response", paragraphs[6], "Assigned reviewer", system="Case Management System"),
            _step(6, "Approve or return the proposed response", paragraphs[7], "Complaints manager"),
            _step(7, "Send the response and close the case", paragraphs[8], "Customer service agent"),
        ]
        steps[0].inputs = _collection_many(
            ["Customer complaint", "Customer supporting information"],
            "t-b0003",
            paragraphs[2],
        )
        steps[1].decisions = [
            RawCandidateDecision(
                condition=_known(
                    "Required information is missing", "t-b0004", paragraphs[3]
                ),
                branches=_collection_many(
                    ["Ask the customer for clarification", "Continue intake check"],
                    "t-b0004",
                    paragraphs[3],
                ),
            )
        ]
        steps[2].dependencies = [
            RawCandidateDependency(
                target_label=_inferred(
                    "Categorise complaint and check required information",
                    "t-b0005",
                    paragraphs[4],
                ),
                relationship=_known("Occurs after", "t-b0005", paragraphs[4]),
            )
        ]
        steps[3].decisions = [
            RawCandidateDecision(
                condition=_known(
                    "Specialist review is required", "t-b0006", paragraphs[5]
                ),
                branches=_collection_many(
                    ["Assign to a subject-matter specialist", "Proceed to resolution drafting"],
                    "t-b0006",
                    paragraphs[5],
                ),
            )
        ]
        steps[5].exceptions = _collection(
            "Immediate customer harm requires escalation before normal approval",
            "t-b0008",
            paragraphs[7],
        )
        steps[6].outputs = _collection_many(
            ["Customer response", "Closed complaint record"],
            "t-b0009",
            paragraphs[8],
        )
        process_name = _known("Customer Complaint Handling", "t-b0001", paragraphs[0])
        process_description = _known(paragraphs[1], "t-b0002", paragraphs[1])
        extraction = RawChunkExtraction(
            process_name=process_name,
            process_description=process_description,
            process_objective=process_description,
            steps=steps,
            multiple_processes_detected=_unknown(bool),
        )
        return ProviderExtractionResponse(
            extraction=extraction,
            invocation=ProviderInvocation(
                provider_name=self.provider_name,
                requested_model=self.model_name,
                effective_model=self.model_name,
                request_id="offline-demo-scripted",
                chunk_id=request.chunk.chunk_id,
                attempt=request.attempt,
            ),
        )

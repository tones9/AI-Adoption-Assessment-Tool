"""Fake structured provider and raw candidate factories for Phase 3 tests."""

from __future__ import annotations

from collections.abc import Sequence

from ai_adoption_engine.extraction.providers.base import (
    ExtractionRequest,
    ProviderExtractionResponse,
)
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
    RawCandidateOrdinalAssertion,
    RawCandidateProcessStep,
    RawCandidateTaskCharacteristics,
    RawChunkExtraction,
    RawEvidencePointer,
)


def unknown(value_type: type = str) -> RawCandidateAssertion:
    return RawCandidateAssertion[value_type](
        value=None,
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale="The source does not state this information.",
        evidence=[],
    )


def known(
    value: object,
    *,
    block_id: str,
    snippet: str,
    occurrence: int | None = None,
    slice_id: str | None = None,
) -> RawCandidateAssertion:
    return RawCandidateAssertion[type(value)](
        value=value,
        knowledge_state=KnowledgeState.KNOWN,
        rationale="Directly stated in the source.",
        evidence=[
            RawEvidencePointer(
                block_id=block_id,
                exact_snippet=snippet,
                occurrence=occurrence,
                slice_id=slice_id,
            )
        ],
    )


def unknown_collection() -> RawCandidateCollection[str]:
    return RawCandidateCollection[str](
        completeness=CollectionCompleteness.UNKNOWN,
        rationale="The source does not provide this collection.",
        items=[],
    )


def unknown_characteristics() -> RawCandidateTaskCharacteristics:
    return RawCandidateTaskCharacteristics(
        criteria=[
            RawCandidateCharacteristic(
                name=name,
                assertion=RawCandidateOrdinalAssertion(
                    value=None,
                    knowledge_state=KnowledgeState.UNKNOWN,
                    rationale="The source does not state this information.",
                    evidence=[],
                ),
            )
            for name in CriterionName
        ],
        human_accountability_required=unknown(bool),
        capability_signals=[
            RawCandidateCapabilitySignal(name=name, assertion=unknown(bool))
            for name in CapabilitySignalName
        ],
    )


def raw_step(
    *,
    local_step_id: str,
    activity: str,
    block_id: str,
    snippet: str,
    occurrence: int | None = None,
    slice_id: str | None = None,
    document_order: RawCandidateAssertion[int] | None = None,
) -> RawCandidateProcessStep:
    return RawCandidateProcessStep(
        local_step_id=local_step_id,
        document_order=document_order or unknown(int),
        activity=known(
            activity,
            block_id=block_id,
            snippet=snippet,
            occurrence=occurrence,
            slice_id=slice_id,
        ),
        description=unknown(str),
        actors=unknown_collection(),
        responsible_roles=unknown_collection(),
        systems=unknown_collection(),
        inputs=unknown_collection(),
        outputs=unknown_collection(),
        decisions=[],
        dependencies=[],
        exceptions=unknown_collection(),
        operational_characteristics=unknown_collection(),
        characteristics=unknown_characteristics(),
    )


def raw_chunk(
    *steps: RawCandidateProcessStep,
    process_name: RawCandidateAssertion[str] | None = None,
    multiple_processes_detected: bool = False,
) -> RawChunkExtraction:
    return RawChunkExtraction(
        process_name=process_name or unknown(str),
        process_description=unknown(str),
        process_objective=unknown(str),
        steps=list(steps),
        multiple_processes_detected=multiple_processes_detected,
    )


class ScriptedExtractionProvider:
    provider_name = "fake"
    model_name = "fake-structured-v1"

    def __init__(self, responses: Sequence[RawChunkExtraction | Exception]) -> None:
        self.responses = list(responses)
        self.requests: list[ExtractionRequest] = []

    def extract_chunk(self, request: ExtractionRequest) -> ProviderExtractionResponse:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("Fake provider has no scripted response")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return ProviderExtractionResponse(
            extraction=response,
            invocation=ProviderInvocation(
                provider_name=self.provider_name,
                requested_model=self.model_name,
                effective_model=self.model_name,
                request_id=f"fake-{len(self.requests)}",
                chunk_id=request.chunk.chunk_id,
                attempt=request.attempt,
            ),
        )

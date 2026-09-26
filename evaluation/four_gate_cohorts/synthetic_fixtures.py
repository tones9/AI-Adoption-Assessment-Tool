"""Source-backed synthetic fixtures for development of the cohort harness only."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ai_adoption_engine.extraction.providers.base import (
    ExtractionRequest,
    ProviderExtractionResponse,
)
from ai_adoption_engine.extraction.service import ProcessExtractionService
from ai_adoption_engine.ingestion.text import ingest_raw_text
from ai_adoption_engine.models.candidate_process import (
    CapabilitySignalName as CandidateCapabilitySignalName,
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
from ai_adoption_engine.models.four_gate_assessment import OutcomeCode
from ai_adoption_engine.models.review import (
    ApprovedProcessReview,
    ExplicitApproval,
)
from ai_adoption_engine.review.approval import approve_review
from ai_adoption_engine.review.service import ProcessReviewService


FIXTURE_TIME = datetime(2026, 9, 6, 9, 0, tzinfo=UTC)
FIXTURE_ROOT = Path(__file__).resolve().parent / "development_fixtures"


@dataclass(frozen=True)
class SyntheticFixtureSpec:
    case_id: str
    filename: str
    title: str
    activity: str
    criteria: dict[CriterionName, int | None]
    human_accountability_required: bool
    true_capability_signals: frozenset[CandidateCapabilitySignalName]
    expected_outcome: OutcomeCode


@dataclass(frozen=True)
class SyntheticDevelopmentFixture:
    spec: SyntheticFixtureSpec
    source_bytes: bytes
    approved_review: ApprovedProcessReview


_BASE_CRITERIA = {
    CriterionName.REPETITION: 4,
    CriterionName.PREDICTABILITY: 5,
    CriterionName.DATA_READINESS: 4,
    CriterionName.AI_CAPABILITY_FIT: 4,
    CriterionName.HUMAN_JUDGEMENT_REQUIREMENT: 1,
    CriterionName.BUSINESS_VALUE: 4,
    CriterionName.RISK_CONSEQUENCE: 1,
    CriterionName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT: 1,
    CriterionName.IMPLEMENTATION_COMPLEXITY: 2,
    CriterionName.CONVENTIONAL_SOLUTION_FIT: 1,
}


def _spec(
    case_id: str,
    filename: str,
    title: str,
    activity: str,
    expected_outcome: OutcomeCode,
    *,
    changes: dict[CriterionName, int | None] | None = None,
    human_accountability_required: bool = False,
) -> SyntheticFixtureSpec:
    criteria = dict(_BASE_CRITERIA)
    criteria.update(changes or {})
    return SyntheticFixtureSpec(
        case_id=case_id,
        filename=filename,
        title=title,
        activity=activity,
        criteria=criteria,
        human_accountability_required=human_accountability_required,
        true_capability_signals=frozenset(
            {CandidateCapabilitySignalName.READS_UNSTRUCTURED_DOCUMENTS}
        ),
        expected_outcome=expected_outcome,
    )


SYNTHETIC_FIXTURE_SPECS: tuple[SyntheticFixtureSpec, ...] = (
    _spec(
        "DEV-FG-001",
        "dev-fg-001-no-change.txt",
        "No-change Gate 1 fixture",
        "Retain the already efficient archival check",
        OutcomeCode.NO_CHANGE_JUSTIFIED,
        changes={CriterionName.BUSINESS_VALUE: 1},
    ),
    _spec(
        "DEV-FG-002",
        "dev-fg-002-gate2-discovery.txt",
        "Gate 2 data-readiness discovery fixture",
        "Extract fields from incoming service documents",
        OutcomeCode.DISCOVERY_REQUIRED,
        changes={CriterionName.DATA_READINESS: None},
    ),
    _spec(
        "DEV-FG-003",
        "dev-fg-003-conventional-first.txt",
        "Conventional-first Gate 3 fixture",
        "Route complete records with maintained rules",
        OutcomeCode.CONVENTIONAL_AUTOMATION,
        changes={
            CriterionName.CONVENTIONAL_SOLUTION_FIT: 5,
            CriterionName.AI_CAPABILITY_FIT: None,
        },
    ),
    _spec(
        "DEV-FG-004",
        "dev-fg-004-ai-safety-veto.txt",
        "AI-candidate safety-veto fixture",
        "Recommend a consequential eligibility decision",
        OutcomeCode.KEEP_HUMAN_LED,
        changes={
            CriterionName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT: 5,
            CriterionName.RISK_CONSEQUENCE: 5,
            CriterionName.HUMAN_JUDGEMENT_REQUIREMENT: 5,
        },
        human_accountability_required=True,
    ),
    _spec(
        "DEV-FG-005",
        "dev-fg-005-process-first.txt",
        "Gate 2 process-improvement stop fixture",
        "Standardise fragmented operational records",
        OutcomeCode.PROCESS_IMPROVEMENT_FIRST,
        changes={CriterionName.DATA_READINESS: 1},
    ),
)


def _render_source(spec: SyntheticFixtureSpec) -> bytes:
    criteria = "; ".join(
        f"{name.value}={'unknown' if spec.criteria[name] is None else spec.criteria[name]}"
        for name in CriterionName
    )
    capabilities = "; ".join(
        f"{name.value}={'true' if name in spec.true_capability_signals else 'false'}"
        for name in CandidateCapabilitySignalName
    )
    return (
        f"Process: {spec.title}\n\n"
        f"Activity: {spec.activity}; human accountability required="
        f"{'true' if spec.human_accountability_required else 'false'}\n\n"
        f"Reviewed decision inputs (0-5): {criteria}\n\n"
        f"Reviewed capability signals: {capabilities}\n"
    ).encode("utf-8")


def load_synthetic_development_fixtures(
    root: str | Path = FIXTURE_ROOT,
) -> tuple[SyntheticDevelopmentFixture, ...]:
    fixture_root = Path(root)
    loaded: list[SyntheticDevelopmentFixture] = []
    for spec in SYNTHETIC_FIXTURE_SPECS:
        source_bytes = (fixture_root / spec.filename).read_bytes()
        if source_bytes != _render_source(spec):
            raise ValueError(f"Synthetic fixture source changed: {spec.filename}")
        loaded.append(
            SyntheticDevelopmentFixture(
                spec=spec,
                source_bytes=source_bytes,
                approved_review=_approved_review(spec, source_bytes),
            )
        )
    return tuple(loaded)


def _approved_review(
    spec: SyntheticFixtureSpec,
    source_bytes: bytes,
) -> ApprovedProcessReview:
    source_text = source_bytes.decode("utf-8")
    ingestion = ingest_raw_text(source_text)
    if ingestion.document is None:
        raise ValueError("Synthetic source could not be ingested")
    blocks = {
        block.extracted_text: block.block_id for block in ingestion.document.blocks
    }
    process_line, activity_line, criteria_line, capability_line = (
        block.extracted_text for block in ingestion.document.blocks
    )
    criteria = [
        RawCandidateCharacteristic(
            name=name,
            assertion=(
                _unknown_ordinal()
                if value is None
                else RawCandidateOrdinalAssertion(
                    value=value,
                    knowledge_state=KnowledgeState.KNOWN,
                    rationale="Explicit synthetic before-state fixture value.",
                    evidence=[_pointer(blocks[criteria_line], criteria_line)],
                    confidence=None,
                )
            ),
        )
        for name, value in spec.criteria.items()
    ]
    signals = [
        RawCandidateCapabilitySignal(
            name=name,
            assertion=RawCandidateAssertion[bool](
                value=name in spec.true_capability_signals,
                knowledge_state=KnowledgeState.KNOWN,
                rationale="Explicit synthetic before-state capability signal.",
                evidence=[_pointer(blocks[capability_line], capability_line)],
                confidence=None,
            ),
        )
        for name in CandidateCapabilitySignalName
    ]
    raw = RawChunkExtraction(
        process_name=_known_text(spec.title, blocks[process_line], process_line),
        process_description=_unknown_text(),
        process_objective=_unknown_text(),
        steps=[
            RawCandidateProcessStep(
                local_step_id=spec.case_id.lower(),
                document_order=RawCandidateAssertion[int](
                    value=None,
                    knowledge_state=KnowledgeState.UNKNOWN,
                    rationale="One activity; order is retained by source position.",
                    evidence=[],
                    confidence=None,
                ),
                activity=_known_text(
                    spec.activity, blocks[activity_line], activity_line
                ),
                description=_unknown_text(),
                actors=_unknown_collection(),
                responsible_roles=_unknown_collection(),
                systems=_unknown_collection(),
                inputs=_unknown_collection(),
                outputs=_unknown_collection(),
                decisions=[],
                dependencies=[],
                exceptions=_unknown_collection(),
                operational_characteristics=_unknown_collection(),
                characteristics=RawCandidateTaskCharacteristics(
                    criteria=criteria,
                    human_accountability_required=RawCandidateAssertion[bool](
                        value=spec.human_accountability_required,
                        knowledge_state=KnowledgeState.KNOWN,
                        rationale="Explicit synthetic before-state accountability value.",
                        evidence=[
                            _pointer(blocks[activity_line], activity_line)
                        ],
                        confidence=None,
                    ),
                    capability_signals=signals,
                ),
            )
        ],
        multiple_processes_detected=RawCandidateAssertion[bool](
            value=None,
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="The fixture defines one process.",
            evidence=[],
            confidence=None,
        ),
    )
    extracted = ProcessExtractionService(
        _SyntheticProvider([raw]),
        run_id_factory=lambda: f"four-gate-cohort-extraction-{spec.case_id.lower()}",
    ).extract(ingestion.document)
    review_ids = iter(range(1, 1000))
    service = ProcessReviewService(
        clock=lambda: FIXTURE_TIME,
        id_factory=lambda prefix: f"{spec.case_id.lower()}-{prefix}-{next(review_ids)}",
    )
    session = service.start_review(extracted)
    service.accept_assertion(session, session.process_name, "process.name")
    step = session.steps[0]
    service.accept_assertion(session, step.activity, f"steps.{step.candidate_step_id}.activity")
    for item in step.criteria:
        _record_review(service, session, item.assertion, f"criteria.{item.name.value}")
    _record_review(
        service,
        session,
        step.human_accountability_required,
        "human_accountability_required",
    )
    for item in step.capability_signals:
        _record_review(
            service,
            session,
            item.assertion,
            "capability_signals."
            f"{item.name.value if hasattr(item.name, 'value') else item.name}",
        )
    service.accept_step_order(session)
    approved = approve_review(
        session,
        ExplicitApproval(
            approval_statement="APPROVE CURRENT-STATE PROCESS",
            approved_at=FIXTURE_TIME,
            rationale="Synthetic development-fixture approval only.",
        ),
    ).approved
    if approved is None:
        raise ValueError(f"Synthetic fixture approval failed: {spec.case_id}")
    return approved


def _record_review(service, session, assertion, field_path: str) -> None:
    if assertion.knowledge_state is KnowledgeState.UNKNOWN:
        service.retain_unknown(
            session,
            assertion,
            field_path,
            rationale="Unknown deliberately retained in the development fixture.",
        )
    else:
        service.accept_assertion(
            session,
            assertion,
            field_path,
            rationale="Synthetic fixture value explicitly reviewed.",
        )


def _pointer(block_id: str, snippet: str) -> RawEvidencePointer:
    return RawEvidencePointer(
        block_id=block_id,
        exact_snippet=snippet,
        occurrence=None,
        slice_id=None,
    )


def _known_text(value: str, block_id: str, snippet: str):
    return RawCandidateAssertion[str](
        value=value,
        knowledge_state=KnowledgeState.KNOWN,
        rationale="Explicit synthetic before-state text.",
        evidence=[_pointer(block_id, snippet)],
        confidence=None,
    )


def _unknown_text():
    return RawCandidateAssertion[str](
        value=None,
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale="Not supplied by this synthetic development fixture.",
        evidence=[],
        confidence=None,
    )


def _unknown_ordinal():
    return RawCandidateOrdinalAssertion(
        value=None,
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale="Deliberately unknown in this synthetic development fixture.",
        evidence=[],
        confidence=None,
    )


def _unknown_collection():
    return RawCandidateCollection[str](
        completeness=CollectionCompleteness.UNKNOWN,
        rationale="Not supplied by this synthetic development fixture.",
        items=[],
        evidence=[],
    )


class _SyntheticProvider:
    provider_name = "four-gate-synthetic-development-fixture"
    model_name = "no-model-offline-fixture"

    def __init__(self, responses: Sequence[RawChunkExtraction]) -> None:
        self.responses = list(responses)

    def extract_chunk(self, request: ExtractionRequest) -> ProviderExtractionResponse:
        if not self.responses:
            raise ValueError("Synthetic fixture provider has no response")
        return ProviderExtractionResponse(
            extraction=self.responses.pop(0),
            invocation=ProviderInvocation(
                provider_name=self.provider_name,
                requested_model=self.model_name,
                effective_model=self.model_name,
                request_id=f"{request.chunk.chunk_id}-offline",
                chunk_id=request.chunk.chunk_id,
                attempt=request.attempt,
            ),
        )


__all__ = [
    "FIXTURE_TIME",
    "SYNTHETIC_FIXTURE_SPECS",
    "SyntheticDevelopmentFixture",
    "load_synthetic_development_fixtures",
]

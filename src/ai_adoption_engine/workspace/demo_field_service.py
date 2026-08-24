"""Second bundled demo fixture: a synthetic process whose facts are documented.

The original bundled fixture (:mod:`.demo_extraction`) deliberately leaves every
assessment criterion ``UNKNOWN``, because its source narrative never states one.
That is the honest conservative case and it stays exactly as it is.

This fixture is its complement.  The synthetic source records the operational
facts a process document would have to contain before an adoption decision could
be supported, so the scripted extraction can propose criterion values that each
cite the sentence stating them.  Nothing here changes the engine: the values are
asserted from the document, a human still reviews and approves them, and the
recommendation each activity receives is whatever the existing policy produces.

The fixture is SYNTHETIC DEMONSTRATION DATA.  It is not a customer process, not
research evidence, and not a record of any measured outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    RawCandidateOrdinalAssertion,
    RawCandidateProcessStep,
    RawCandidateTaskCharacteristics,
    RawChunkExtraction,
    RawEvidencePointer,
)


ROOT = Path(__file__).resolve().parents[3]
FIELD_SERVICE_DOCUMENT_PATH = (
    ROOT / "data" / "demo" / "synthetic_field_service_process.txt"
)

#: Paragraph count the scripted response is written against.
EXPECTED_PARAGRAPHS = 10


class FieldServiceDocumentMismatchError(ValueError):
    """The scripted response was requested for a different document."""


def field_service_text() -> str:
    return FIELD_SERVICE_DOCUMENT_PATH.read_text(encoding="utf-8")


def field_service_document_id() -> str:
    result = ingest_raw_text(field_service_text())
    assert result.document is not None
    return result.document.document_id


# ---------------------------------------------------------------------------
# The documented facts, and the exact sentence each one is taken from.
#
# Every criterion value below is a reading of the quoted sentence.  The quoted
# text is resolved against the ingested document by the existing evidence
# resolver, so a sentence that drifts fails extraction rather than producing an
# unsupported value.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Activity:
    """One synthetic activity, its narrative block and its documented facts."""

    local_id: str
    activity: str
    actor: str
    system: str | None
    narrative_block: str
    facts_block: str
    criteria: dict[CriterionName, tuple[int, str]]
    unknown_criteria: dict[CriterionName, str]
    accountability: tuple[bool, str]
    signals: dict[CapabilitySignalName, tuple[bool, str]]


_C = CriterionName
_S = CapabilitySignalName

_CLASSIFY_QUEUES = (
    "Assigning short free-text requests to a fixed set of queues is a "
    "well-established use of current classification technology."
)
_READ_CLAUSE = (
    "Reading a contract clause and assigning the request to a coverage category "
    "is a well-established use of current document and classification technology."
)
_DRAFT_NOTE = (
    "Drafting a structured note from existing records and reference material is a "
    "well-established use of current text generation and retrieval technology."
)
_RANK_CASES = (
    "Ranking a case against comparable past decisions is a plausible use of "
    "current decision-support technology."
)


ACTIVITIES: tuple[_Activity, ...] = (
    _Activity(
        local_id="field-service-step-1",
        activity="Sort incoming maintenance requests",
        actor="Service coordinator",
        system="Field Service System",
        narrative_block="t-b0003",
        facts_block="t-b0004",
        criteria={
            _C.REPETITION: (
                5,
                "The team sorts about four thousand requests every month and the "
                "task is carried out the same way each time.",
            ),
            _C.PREDICTABILITY: (
                4,
                "The sorting rules are stable and the correct queue can be "
                "determined from the request text in almost every case.",
            ),
            _C.DATA_READINESS: (
                4,
                "Every request already carries a structured equipment code, a "
                "customer identifier and a free-text description, and three years "
                "of correctly sorted history is retained in the Field Service "
                "System.",
            ),
            _C.AI_CAPABILITY_FIT: (4, _CLASSIFY_QUEUES),
            _C.HUMAN_JUDGEMENT_REQUIREMENT: (
                1,
                "A coordinator applies no personal judgement when sorting a request.",
            ),
            _C.BUSINESS_VALUE: (
                3,
                "Faster sorting would save the team a moderate amount of handling "
                "time each month.",
            ),
            _C.RISK_CONSEQUENCE: (
                1,
                "A wrongly sorted request is delayed by a few hours and is "
                "corrected by the receiving queue.",
            ),
            _C.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT: (
                1,
                "With a coordinator reviewing the queue each morning, the "
                "remaining risk of a request sitting in the wrong queue is "
                "negligible.",
            ),
            _C.IMPLEMENTATION_COMPLEXITY: (
                2,
                "Connecting a classifier to the existing queue interface is a "
                "contained piece of work for the platform team.",
            ),
            _C.CONVENTIONAL_SOLUTION_FIT: (
                1,
                "A fixed keyword rule was tried in the past and failed on "
                "free-text descriptions, so a conventional rules-only approach is "
                "a poor fit for this activity.",
            ),
        },
        unknown_criteria={},
        accountability=(
            False,
            "No individual is formally accountable for the sorting step itself.",
        ),
        signals={_S.CATEGORISES_ITEMS: (True, _CLASSIFY_QUEUES)},
    ),
    _Activity(
        local_id="field-service-step-2",
        activity="Check the request against the service contract",
        actor="Contracts administrator",
        system=None,
        narrative_block="t-b0005",
        facts_block="t-b0006",
        criteria={
            _C.REPETITION: (
                4,
                "The team checks about one thousand five hundred requests every "
                "month against a stable set of contract templates.",
            ),
            _C.PREDICTABILITY: (
                3,
                "Entitlement wording changes rarely and the same contract clauses "
                "decide most cases.",
            ),
            _C.AI_CAPABILITY_FIT: (4, _READ_CLAUSE),
            _C.HUMAN_JUDGEMENT_REQUIREMENT: (
                2,
                "An administrator applies limited personal judgement once the "
                "relevant clause has been located.",
            ),
            _C.BUSINESS_VALUE: (
                4,
                "Correct entitlement decisions protect a significant amount of "
                "recoverable revenue each month.",
            ),
            _C.RISK_CONSEQUENCE: (
                2,
                "A wrong coverage decision is corrected at invoicing and causes a "
                "short billing dispute.",
            ),
            _C.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT: (
                2,
                "With an administrator confirming each coverage decision, the "
                "remaining risk of an incorrect invoice is small.",
            ),
            _C.IMPLEMENTATION_COMPLEXITY: (
                3,
                "Integrating a contract reader with the entitlement record is a "
                "moderate piece of work.",
            ),
            _C.CONVENTIONAL_SOLUTION_FIT: (
                2,
                "Some straightforward cases could be handled by existing "
                "entitlement rules, so a conventional approach partly fits this "
                "activity.",
            ),
        },
        unknown_criteria={
            _C.DATA_READINESS: (
                "The source records that the condition of the stored contract "
                "documents, the retention of past coverage decisions and their "
                "access control are not known."
            ),
        },
        accountability=(
            False,
            "No individual is formally accountable for the entitlement check itself.",
        ),
        signals={
            _S.CATEGORISES_ITEMS: (True, _READ_CLAUSE),
            _S.READS_UNSTRUCTURED_DOCUMENTS: (True, _READ_CLAUSE),
        },
    ),
    _Activity(
        local_id="field-service-step-3",
        activity="Draft the scheduling note for the field engineer",
        actor="Scheduling planner",
        system="Field Service System",
        narrative_block="t-b0007",
        facts_block="t-b0008",
        criteria={
            _C.REPETITION: (
                4,
                "The team drafts about two thousand scheduling notes every month.",
            ),
            _C.PREDICTABILITY: (
                2,
                "The content of a note varies with the fault and the site, so the "
                "wording is not predictable from the request alone.",
            ),
            _C.DATA_READINESS: (
                3,
                "Past scheduling notes, parts lists and site access records are "
                "held in the Field Service System, and most fields are complete "
                "although free-text quality varies.",
            ),
            _C.AI_CAPABILITY_FIT: (4, _DRAFT_NOTE),
            _C.HUMAN_JUDGEMENT_REQUIREMENT: (
                3,
                "A planner applies substantial personal judgement about site access "
                "and likely parts.",
            ),
            _C.BUSINESS_VALUE: (
                4,
                "Better scheduling notes would materially reduce wasted engineer "
                "visits.",
            ),
            _C.RISK_CONSEQUENCE: (
                3,
                "An inaccurate note can send an engineer to a site without the "
                "right parts, which loses a working day.",
            ),
            _C.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT: (
                2,
                "With a planner reviewing every draft before it is sent, some risk "
                "of a wasted visit remains.",
            ),
            _C.IMPLEMENTATION_COMPLEXITY: (
                3,
                "Connecting a drafting assistant to the parts and site records is a "
                "moderate piece of work.",
            ),
            _C.CONVENTIONAL_SOLUTION_FIT: (
                1,
                "A template-only approach was rejected because notes vary too much "
                "between sites, so a conventional rules-only approach is a poor fit "
                "for this activity.",
            ),
        },
        unknown_criteria={},
        accountability=(
            True,
            "A named planner remains formally accountable for every note sent to a "
            "field engineer.",
        ),
        signals={
            _S.CREATES_NEW_CONTENT: (True, _DRAFT_NOTE),
            _S.SEARCHES_REFERENCE_KNOWLEDGE: (True, _DRAFT_NOTE),
        },
    ),
    _Activity(
        local_id="field-service-step-4",
        activity="Approve or refuse a goodwill repair",
        actor="Regional service manager",
        system=None,
        narrative_block="t-b0009",
        facts_block="t-b0010",
        criteria={
            _C.REPETITION: (
                3,
                "The team receives about three hundred goodwill requests every "
                "month and each one is considered on its own merits.",
            ),
            _C.PREDICTABILITY: (
                2,
                "The outcome depends on the customer relationship and the "
                "circumstances of the failure, so it is not predictable from the "
                "request record alone.",
            ),
            _C.DATA_READINESS: (
                3,
                "Past goodwill decisions, their stated reasons and the associated "
                "costs are retained in the Field Service System.",
            ),
            _C.AI_CAPABILITY_FIT: (3, _RANK_CASES),
            _C.HUMAN_JUDGEMENT_REQUIREMENT: (
                4,
                "A manager applies substantial personal judgement weighing "
                "commercial and relationship factors.",
            ),
            _C.BUSINESS_VALUE: (
                3,
                "Consistent goodwill decisions would deliver a moderate saving on "
                "disputed repairs.",
            ),
            _C.RISK_CONSEQUENCE: (
                4,
                "A wrong goodwill decision commits unrecovered cost and can damage "
                "a long-standing customer relationship.",
            ),
            _C.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT: (
                4,
                "Even with a manager reviewing every recommendation, the risk of an "
                "unjustified commitment remains material because the reasons behind "
                "past decisions are recorded inconsistently.",
            ),
            _C.IMPLEMENTATION_COMPLEXITY: (
                3,
                "Building a comparable-case tool over the goodwill record is a "
                "moderate piece of work.",
            ),
            _C.CONVENTIONAL_SOLUTION_FIT: (
                2,
                "Existing discount rules cover only a minority of cases, so a "
                "conventional approach fits this activity only partly.",
            ),
        },
        unknown_criteria={},
        accountability=(
            True,
            "A named regional service manager remains formally accountable for "
            "every goodwill decision.",
        ),
        signals={
            _S.SUPPORTS_COMPLEX_DECISIONS: (True, _RANK_CASES),
            _S.RANKS_OR_SUGGESTS_OPTIONS: (True, _RANK_CASES),
        },
    ),
)


def cited_snippets() -> tuple[tuple[str, str], ...]:
    """Return every (block_id, exact_snippet) pair this fixture asserts.

    Exposed so a test can prove each citation resolves in the bundled document
    without running an extraction.
    """

    pairs: list[tuple[str, str]] = []
    for activity in ACTIVITIES:
        for _, snippet in activity.criteria.values():
            pairs.append((activity.facts_block, snippet))
        pairs.append((activity.facts_block, activity.accountability[1]))
        for _, snippet in activity.signals.values():
            pairs.append((activity.facts_block, snippet))
    return tuple(pairs)


# ---------------------------------------------------------------------------
# Raw candidate construction
# ---------------------------------------------------------------------------


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


def _ordinal_known(
    value: int, block_id: str, snippet: str
) -> RawCandidateOrdinalAssertion:
    return RawCandidateOrdinalAssertion(
        value=value,
        knowledge_state=KnowledgeState.KNOWN,
        rationale=(
            "Read from the operational fact recorded in the bundled synthetic source."
        ),
        evidence=_evidence(block_id, snippet),
        confidence=None,
    )


def _ordinal_unknown(rationale: str) -> RawCandidateOrdinalAssertion:
    return RawCandidateOrdinalAssertion(
        value=None,
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale=rationale,
        evidence=[],
        confidence=None,
    )


def _characteristics(activity: _Activity) -> RawCandidateTaskCharacteristics:
    criteria: list[RawCandidateCharacteristic] = []
    for name in CriterionName:
        if name in activity.criteria:
            value, snippet = activity.criteria[name]
            assertion = _ordinal_known(value, activity.facts_block, snippet)
        elif name in activity.unknown_criteria:
            assertion = _ordinal_unknown(activity.unknown_criteria[name])
        else:
            assertion = _ordinal_unknown(
                "The source does not provide enough evidence to assign this "
                "assessment value."
            )
        criteria.append(RawCandidateCharacteristic(name=name, assertion=assertion))

    accountable, accountable_snippet = activity.accountability
    signals: list[RawCandidateCapabilitySignal] = []
    for name in CapabilitySignalName:
        if name in activity.signals:
            value, snippet = activity.signals[name]
            signal_assertion = _known(value, activity.facts_block, snippet)
        else:
            signal_assertion = _unknown(bool)
        signals.append(
            RawCandidateCapabilitySignal(name=name, assertion=signal_assertion)
        )

    return RawCandidateTaskCharacteristics(
        criteria=criteria,
        human_accountability_required=_known(
            accountable, activity.facts_block, accountable_snippet
        ),
        capability_signals=signals,
    )


def _step(sequence: int, activity: _Activity, narrative: str) -> RawCandidateProcessStep:
    block = activity.narrative_block
    return RawCandidateProcessStep(
        local_step_id=activity.local_id,
        document_order=_known(sequence, block, narrative),
        activity=_known(activity.activity, block, narrative),
        description=_known(narrative, block, narrative),
        actors=_collection(activity.actor, block, narrative),
        responsible_roles=_collection(activity.actor, block, narrative),
        systems=(
            _collection(activity.system, block, narrative)
            if activity.system
            else _unknown_collection()
        ),
        inputs=_unknown_collection(),
        outputs=_unknown_collection(),
        decisions=[],
        dependencies=[],
        exceptions=_unknown_collection(),
        operational_characteristics=_unknown_collection(),
        characteristics=_characteristics(activity),
    )


class ScriptedFieldServiceExtractionProvider:
    """Deterministic provider restricted to the bundled field-service fixture."""

    provider_name = "demo-scripted"
    model_name = "offline-fixture-field-service-v1"

    def extract_chunk(self, request: ExtractionRequest) -> ProviderExtractionResponse:
        if request.document_id != field_service_document_id():
            raise FieldServiceDocumentMismatchError(
                "This scripted extraction is available only for the bundled "
                "synthetic field-service document."
            )
        if request.chunk.sequence != 1 or request.chunk.has_next:
            raise FieldServiceDocumentMismatchError(
                "The bundled field-service fixture must resolve to one extraction chunk."
            )
        paragraphs = [item.text for item in request.chunk.slices]
        if len(paragraphs) != EXPECTED_PARAGRAPHS:
            raise FieldServiceDocumentMismatchError(
                "The bundled field-service document fingerprint changed."
            )
        steps = [
            _step(index + 1, activity, paragraphs[2 + index * 2])
            for index, activity in enumerate(ACTIVITIES)
        ]
        extraction = RawChunkExtraction(
            process_name=_known(
                "Synthetic Field Service Request Handling", "t-b0001", paragraphs[0]
            ),
            process_description=_known(paragraphs[1], "t-b0002", paragraphs[1]),
            process_objective=_known(paragraphs[1], "t-b0002", paragraphs[1]),
            steps=steps,
            multiple_processes_detected=_unknown(bool),
        )
        return ProviderExtractionResponse(
            extraction=extraction,
            invocation=ProviderInvocation(
                provider_name=self.provider_name,
                requested_model=self.model_name,
                effective_model=self.model_name,
                request_id="offline-demo-field-service",
                chunk_id=request.chunk.chunk_id,
                attempt=request.attempt,
            ),
        )

"""Persistence-free deterministic Preliminary Assessment v0.2 evaluator."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from typing import Any, Iterable

from pydantic import ValidationError

from ai_adoption_engine.application.fingerprints import fingerprint_business_process
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.preliminary_assessment_v0_2 import (
    EVALUATOR_ID,
    ActivityResultType,
    ComponentAction,
    DecisionTraceEntry,
    EvidenceCoverage,
    EvidenceRecord,
    KnowledgeClassification,
    MatchedSubSpan,
    Opportunity,
    PreliminaryActivityResultV2,
    PreliminaryAssessmentLineageV2,
    PreliminaryAssessmentV2,
    PreliminaryComponent,
    PreliminaryEvaluationErrorV2,
    PreliminaryEvaluationFailureCodeV2,
    PreliminaryEvaluationFailureV2,
    PreliminaryEvaluationResultV2,
    PreliminaryEvaluationSuccessV2,
    ProvisionalDirectionV2,
    RuleDerivedInference,
    ScopedDiscoveryNeed,
    SourceSpan,
    WorkNeed,
    WorkNeedType,
    content_id,
)
from ai_adoption_engine.models.review import (
    ApprovedProcessReview,
    ConflictStatus,
    InformationOrigin,
    ReviewAction,
    ReviewDisposition,
    ReviewStatus,
    ReviewedAssertion,
    ReviewedCollection,
    ReviewedProcessStep,
)
from ai_adoption_engine.preliminary.rules_v0_2 import (
    LITERAL_MANIFEST,
    PRELIMINARY_EVALUATOR_RULES_V0_2,
    WORK_NEED_BY_RULE_ACTION,
    LiteralFamily,
    PreliminaryEvaluatorRulesV2,
)
from ai_adoption_engine.review.approval import _project_business_process


SOURCE_FIELD_RANK = {
    "activity": 1,
    "description": 2,
    "inputs": 3,
    "outputs": 4,
    "decisions": 5,
    "dependencies": 6,
    "exceptions": 7,
    "operational_characteristics": 8,
    "roles": 9,
    "systems": 10,
    "criteria": 11,
    "capabilities": 12,
}
WORK_NEED_RANK = {item: index for index, item in enumerate(WorkNeedType)}
COVERAGE_RANK = {EvidenceCoverage.HIGH: 0, EvidenceCoverage.MEDIUM: 1, EvidenceCoverage.LOW: 2}
SEMANTIC_RULES = {f"PD2-{number:03d}" for number in (8, 9, 10, 11, 12, 13, 14)}
DIRECT_RULES = {f"PD2-{number:03d}" for number in range(1, 8)}
PROTECTED_ABBREVIATIONS = tuple(PRELIMINARY_EVALUATOR_RULES_V0_2.protected_abbreviations)
FUTURE_OR_OPTIONAL = re.compile(
    r"\b(will|would|may|might|could|can|proposed|proposal|planned|plan to|intends? to|optional|optionally|if desired)\b",
    re.IGNORECASE,
)
NEGATION = re.compile(r"\b(not|never|no longer|does not|do not|must not|should not|cannot|can't)\b", re.IGNORECASE)
VAGUE_UNSUPPORTED = re.compile(r"\b(handles?|deals? with|processes?)\b|\bappropriately\b", re.IGNORECASE)


@dataclass(frozen=True)
class Clause:
    index: int
    start: int
    end: int
    text: str
    inherited_actor: str | None = None


@dataclass(frozen=True)
class _AdmittedSource:
    source_field: str
    source_item_index: int
    classification: KnowledgeClassification
    record: EvidenceRecord
    span: SourceSpan


@dataclass(frozen=True)
class _Match:
    family: LiteralFamily
    clause: Clause
    start: int
    end: int
    token_start: int
    token_end: int
    exact: str
    actor: str | None
    obj: str | None
    input_artifact: str | None
    output_artifact: str | None
    recipient: str | None
    destination: str | None


@dataclass(frozen=True)
class _Draft:
    match: _Match
    source: _AdmittedSource
    owner_signature: tuple[str, ...]
    control_signature: tuple[str, ...]
    safety_signature: tuple[str, ...]
    accountability_signature: tuple[str, ...]
    conflict_signature: tuple[str, ...]


@dataclass(frozen=True)
class _Selection:
    component: PreliminaryComponent
    work_need_id: str
    direction: ProvisionalDirectionV2
    code: str
    trace: tuple[DecisionTraceEntry, ...]
    unknown_ids: tuple[str, ...] = ()


def normalize_matching_text(text: str, *, token_key: bool = True) -> str:
    """Apply the binding NFKC/casefold/whitespace/token normalization."""
    value = unicodedata.normalize("NFKC", text).casefold()
    value = re.sub(r"\s+", " ", value).strip()
    if token_key:
        value = "".join(
            " " if unicodedata.category(char)[0] in {"P", "S"} else char
            for char in value
        )
        value = re.sub(r" +", " ", value).strip()
    return value


def _normalized_with_map(text: str) -> tuple[str, tuple[int, ...]]:
    chars: list[str] = []
    positions: list[int] = []
    pending_space = False
    pending_position = 0
    for index, original in enumerate(text):
        for char in unicodedata.normalize("NFKC", original).casefold():
            is_space = char.isspace() or unicodedata.category(char)[0] in {"P", "S"}
            if is_space:
                if chars:
                    pending_space = True
                    pending_position = index
                continue
            if pending_space and chars and chars[-1] != " ":
                chars.append(" ")
                positions.append(pending_position)
            pending_space = False
            chars.append(char)
            positions.append(index)
    return "".join(chars), tuple(positions)


def _contains_action(text: str) -> bool:
    key = normalize_matching_text(text)
    return any(
        re.search(rf"(?<!\w){re.escape(form)}(?!\w)", key)
        for family in LITERAL_MANIFEST
        if family.component_action is not None
        for form in family.surface_forms
    )


def segment_clauses(text: str) -> tuple[Clause, ...]:
    """Deterministically apply hard boundaries followed by guarded conjunction splits."""
    hard: list[tuple[int, int]] = []
    start = 0
    lowered = text.casefold()
    index = 0
    while index < len(text):
        char = text[index]
        boundary = char in ";?!\n"
        if char == ".":
            prefix = lowered[max(0, index - 5) : index + 1]
            boundary = not any(prefix.endswith(item) for item in PROTECTED_ABBREVIATIONS)
        if char == ":" and index + 1 < len(text) and text[index + 1] == "\n":
            boundary = True
        if boundary:
            if text[start:index].strip():
                hard.append((start, index))
            start = index + 1
        index += 1
    if text[start:].strip():
        hard.append((start, len(text)))

    pieces: list[tuple[int, int, str | None]] = []
    conjunction = re.compile(r"\b(and then|then|and)\b", re.IGNORECASE)
    for hard_start, hard_end in hard:
        cursor = hard_start
        inherited: str | None = None
        for match in conjunction.finditer(text, hard_start, hard_end):
            right = text[match.end() : hard_end]
            if not _contains_action(right):
                continue
            left = text[cursor : match.start()]
            if left.strip():
                pieces.append((cursor, match.start(), inherited))
                inherited = _explicit_actor(left) or inherited
            cursor = match.end()
        if text[cursor:hard_end].strip():
            pieces.append((cursor, hard_end, inherited))

    clauses: list[Clause] = []
    for i, (piece_start, piece_end, actor) in enumerate(pieces):
        raw = text[piece_start:piece_end]
        leading = len(raw) - len(raw.lstrip())
        trailing = len(raw.rstrip())
        clauses.append(
            Clause(
                index=i,
                start=piece_start + leading,
                end=piece_start + trailing,
                text=raw.strip(),
                inherited_actor=actor,
            )
        )
    return tuple(clauses)


def _explicit_actor(text: str) -> str | None:
    normalized, positions = _normalized_with_map(text)
    starts: list[int] = []
    for family in LITERAL_MANIFEST:
        if family.component_action is None:
            continue
        for form in family.surface_forms:
            found = re.search(rf"(?<!\w){re.escape(normalize_matching_text(form))}(?!\w)", normalized)
            if found:
                starts.append(positions[found.start()])
    if not starts:
        return None
    return _actor_before_action(text[: min(starts)], None)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = normalize_matching_text(value)
    value = re.sub(r"^(the|a|an|any)\s+", "", value)
    value = re.sub(r"\s+(and then|then|and)$", "", value).strip()
    return value or None


def _actor_before_action(prefix: str, inherited: str | None) -> str | None:
    prefix = prefix.strip(" ,:-")
    if not prefix:
        return inherited
    if "," in prefix:
        prefix = prefix.rsplit(",", 1)[-1].strip()
    prefix = re.sub(r"^(using|based on|after|once)\s+.+?,\s*", "", prefix, flags=re.IGNORECASE)
    prefix = re.sub(r"^(and then|then|and)\s+", "", prefix, flags=re.IGNORECASE)
    words = prefix.split()
    if not words:
        return inherited
    if words[0].casefold() in {"using", "based", "after", "once"}:
        return inherited
    return _clean(" ".join(words[-5:])) or inherited


def _between(text: str, start: int, patterns: str) -> str:
    tail = text[start:]
    stop = re.search(patterns, tail, re.IGNORECASE)
    return tail[: stop.start()] if stop else tail


def _extract_fields(
    clause: Clause, family: LiteralFamily, local_start: int, local_end: int
) -> tuple[str | None, str | None, str | None, str | None, str | None, str | None]:
    text = clause.text
    before = text[:local_start]
    after = text[local_end:].strip(" ,:-")
    actor = _actor_before_action(before, clause.inherited_actor)
    input_artifact = None
    input_match = re.search(r"\b(?:using|based on)\s+(.+?),", before, re.IGNORECASE)
    if input_match:
        input_artifact = _clean(input_match.group(1))
    action = family.component_action
    obj = output = recipient = destination = None

    output_match = re.search(
        r"\bto\s+(?:create|produce|identify|establish|determine|generate|provide)\s+(.+)$",
        after,
        re.IGNORECASE,
    )
    if output_match:
        output = _clean(output_match.group(1))

    if action is ComponentAction.RECORD:
        obj = _clean(_between(after, 0, r"\s+(?:to create|in|into|on)\s+"))
        destination_match = re.search(r"\b(?:in|into)\s+(.+)$", after, re.IGNORECASE)
        if destination_match:
            destination = _clean(destination_match.group(1))
        if output is None and obj:
            if input_artifact and obj in {"category", "record", "item", "case"}:
                obj = input_artifact
            output = f"RECORDED_FORM:{obj}"
    elif action is ComponentAction.NOTIFY:
        if re.search(r"\s+of\s+", after, re.IGNORECASE):
            parts = re.split(
                r"\s+of\s+", after, maxsplit=1, flags=re.IGNORECASE
            )
            if after.casefold().count(" of ") > 1:
                before_subject, subject = re.split(
                    r"\s+of\s+", after, flags=re.IGNORECASE
                )[:-1], re.split(r"\s+of\s+", after, flags=re.IGNORECASE)[-1]
                parts = [" of ".join(before_subject), subject]
        else:
            parts = re.split(
                r"\s+(?:about|that)\s+", after, maxsplit=1, flags=re.IGNORECASE
            )
        recipient = _clean(parts[0]) if parts else None
        obj = _clean(parts[1]) if len(parts) == 2 else None
        output = obj
    elif action in {ComponentAction.ROUTE, ComponentAction.ASSIGN}:
        parts = re.split(r"\s+to\s+", after, maxsplit=1, flags=re.IGNORECASE)
        obj = _clean(parts[0])
        destination = _clean(parts[1]) if len(parts) == 2 else None
        output = destination
    elif action is ComponentAction.TRANSFORM:
        parts = re.split(r"\s+(?:to|into)\s+", after, maxsplit=1, flags=re.IGNORECASE)
        obj = input_artifact or _clean(parts[0])
        input_artifact = input_artifact or obj
        output = output or (_clean(parts[1]) if len(parts) == 2 else None)
    elif action in {ComponentAction.SCHEDULE, ComponentAction.MONITOR, ComponentAction.FOLLOW_UP}:
        obj = _clean(after)
        output = output or obj
    elif action is ComponentAction.INTERPRET:
        obj = _clean(_between(after, 0, r"\s+to\s+"))
        input_artifact = input_artifact or obj
    elif action is ComponentAction.INVESTIGATE:
        obj = _clean(_between(after, 0, r"\s+to\s+"))
        input_artifact = input_artifact or obj
    elif action is ComponentAction.CATEGORISE:
        object_match = re.match(
            r"of\s+(?:the\s+)?(.+?)\s+as\s+(.+)$", after, re.IGNORECASE
        )
        if object_match:
            obj = _clean(object_match.group(1))
            output = f"{obj} category" if obj else None
        else:
            obj = _clean(_between(after, 0, r"\s+(?:as|to)\s+")) or input_artifact
        category = re.search(r"\b(?:as|to)\s+(.+)$", after, re.IGNORECASE)
        output = output or (_clean(category.group(1)) if category else _clean(after))
    elif action is ComponentAction.RETRIEVE:
        obj = _clean(after)
        output = obj
    elif action in {ComponentAction.COMPARE, ComponentAction.RECOMMEND}:
        obj = _clean(_between(after, 0, r"\s+to\s+"))
        output = output or (_clean(after) if action is ComponentAction.RECOMMEND else None)
    elif action in {ComponentAction.DRAFT, ComponentAction.SUMMARISE}:
        obj = _clean(_between(after, 0, r"\s+to\s+"))
        output = output or obj
        if action is ComponentAction.SUMMARISE:
            input_artifact = input_artifact or obj
    elif action is ComponentAction.ASSESS:
        obj = _clean(_between(after, 0, r"\s+to\s+"))
        if family.pd2_rule_code == "PD2-017":
            obj = input_artifact or obj
        output = output or _clean(after)
    elif action in {ComponentAction.CONTACT, ComponentAction.NEGOTIATE}:
        parts = re.split(r"\s+to\s+", after, maxsplit=1, flags=re.IGNORECASE)
        recipient = _clean(parts[0])
        obj = recipient
        output = output or (_clean(parts[1]) if len(parts) == 2 else None)
    elif action in {ComponentAction.DECIDE, ComponentAction.APPROVE, ComponentAction.UPDATE}:
        obj = _clean(_between(after, 0, r"\s+(?:to|in|into)\s+"))
        if family.matched_literal_code in {
            "PD2-016-L003",
            "PD2-016-L004",
            "PD2-016-L009",
            "PD2-016-L010",
        }:
            obj = "final determination"
        output = output or obj
    else:
        obj = _clean(after)
        output = output or obj
    return actor, obj, input_artifact, output, recipient, destination


def _required_fields_pass(match: _Match) -> bool:
    action = match.family.component_action
    if not match.actor:
        return False
    if action in {ComponentAction.RECORD, ComponentAction.UPDATE}:
        return bool(match.obj and match.output_artifact)
    if action is ComponentAction.FOLLOW_UP:
        return bool(
            match.obj
            and match.obj not in {"appropriately", "as appropriate", "special"}
            and not re.search(r"\bspecial\s+follow[- ]up\b", match.clause.text, re.IGNORECASE)
        )
    if action is ComponentAction.NOTIFY:
        return bool(match.recipient and match.obj)
    if action in {ComponentAction.ROUTE, ComponentAction.ASSIGN}:
        return bool(match.obj and match.destination)
    if action is ComponentAction.TRANSFORM:
        return bool(match.input_artifact and match.output_artifact)
    if match.family.pd2_rule_code == "PD2-008" and match.family.matched_literal_code == "PD2-008-L001":
        return bool(match.obj and match.output_artifact)
    if action is ComponentAction.INVESTIGATE:
        return bool(match.obj and match.output_artifact)
    if action is ComponentAction.CATEGORISE:
        return bool(match.obj and match.output_artifact)
    if action is ComponentAction.RETRIEVE:
        return bool(match.obj)
    if action is ComponentAction.COMPARE:
        return bool(match.obj and match.output_artifact)
    if action is ComponentAction.RECOMMEND:
        return bool(match.obj and match.output_artifact)
    if action in {ComponentAction.DRAFT, ComponentAction.SUMMARISE}:
        return bool(match.output_artifact and (action is not ComponentAction.SUMMARISE or match.input_artifact))
    if match.family.pd2_rule_code == "PD2-014":
        return bool(match.output_artifact)
    if match.family.pd2_rule_code == "PD2-015":
        return bool(match.recipient and match.output_artifact)
    if match.family.pd2_rule_code == "PD2-016":
        return bool(match.obj and match.actor and not re.search(r"\b(system|model|software|service)\b", match.actor))
    if match.family.pd2_rule_code in {"PD2-017", "PD2-018", "PD2-019"}:
        return bool(match.obj and match.output_artifact)
    return bool(match.obj)


def _match_clause(clause: Clause) -> tuple[_Match, ...]:
    normalized, positions = _normalized_with_map(clause.text)
    candidates: list[tuple[int, int, LiteralFamily, str]] = []
    for family in LITERAL_MANIFEST:
        if family.component_action is None:
            continue
        for form in family.surface_forms:
            normalized_form = normalize_matching_text(form)
            for found in re.finditer(rf"(?<!\w){re.escape(normalized_form)}(?!\w)", normalized):
                candidates.append((found.start(), found.end(), family, normalized_form))
    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2].matched_literal_code))
    chosen: list[tuple[int, int, LiteralFamily, str]] = []
    occupied: set[int] = set()
    for candidate in candidates:
        start, end, _, _ = candidate
        if any(index in occupied for index in range(start, end)):
            continue
        chosen.append(candidate)
        occupied.update(range(start, end))

    matches: list[_Match] = []
    for start, end, family, normalized_form in sorted(chosen):
        original_start = positions[start]
        original_end = positions[end - 1] + 1
        prefix = clause.text[:original_start]
        if re.search(r"\bto\s*$", prefix, re.IGNORECASE) and _contains_action(
            re.sub(r"\bto\s*$", "", prefix, flags=re.IGNORECASE)
        ):
            # An accepted token used as the explicit purpose/output of an earlier
            # current-state action is not a second asserted action.
            continue
        local_context = clause.text[max(0, original_start - 45) : original_end + 90]
        if NEGATION.search(prefix[-30:]):
            continue
        future = FUTURE_OR_OPTIONAL.search(clause.text)
        has_should = bool(re.search(r"\bshould\b", clause.text, re.IGNORECASE))
        if future and not has_should:
            continue
        if has_should:
            prohibited = FUTURE_OR_OPTIONAL.search(re.sub(r"\bshould\b", "", clause.text, flags=re.IGNORECASE))
            if prohibited or NEGATION.search(clause.text):
                continue
        if _inside_unqualified_quote(clause.text, original_start):
            continue
        actor, obj, input_artifact, output, recipient, destination = _extract_fields(
            clause, family, original_start, original_end
        )
        token_start = len(normalize_matching_text(prefix).split())
        token_end = token_start + len(normalized_form.split())
        match = _Match(
            family=family,
            clause=clause,
            start=original_start,
            end=original_end,
            token_start=token_start,
            token_end=token_end,
            exact=clause.text[original_start:original_end],
            actor=actor,
            obj=obj,
            input_artifact=input_artifact,
            output_artifact=output,
            recipient=recipient,
            destination=destination,
        )
        if has_should and not _required_fields_pass(match):
            continue
        if not _required_fields_pass(match):
            continue
        matches.append(match)
    return tuple(matches)


def _inside_unqualified_quote(text: str, index: int) -> bool:
    pairs = (("\"", "\""), ("“", "”"), ("'", "'"))
    for left, right in pairs:
        before = text.rfind(left, 0, index)
        after = text.find(right, index + 1)
        if before >= 0 and after >= 0:
            surrounding = text[:before]
            if not re.search(r"\b(instructs?|requires?|procedure says|must)\b", surrounding, re.IGNORECASE):
                return True
    return False


def _source_span_signature(span: SourceSpan) -> list[Any]:
    return list(span.signature())


def _inference_payload(draft: _Draft, fingerprint: str) -> dict[str, Any]:
    match = draft.match
    source = draft.source
    fact_ids = [source.record.item_id] if source.classification is KnowledgeClassification.DOCUMENTED_FACT else []
    reviewed_ids = [source.record.item_id] if source.classification is KnowledgeClassification.REVIEWED_INFERENCE else []
    return {
        "activity_identity": draft.source.span.fact_or_reviewed_inference_id.split(":", 1)[0],
        "matched_literal_code": match.family.matched_literal_code,
        "normalized_derived_characteristic": {
            "component_action": match.family.component_action.value,
            "normalized_actor": match.actor,
            "normalized_destination": match.destination,
            "normalized_input_artifact": match.input_artifact,
            "normalized_object": match.obj,
            "normalized_output_artifact": match.output_artifact,
            "normalized_recipient": match.recipient,
        },
        "pd2_rule_code": match.family.pd2_rule_code,
        "rule_set_fingerprint": fingerprint,
        "schema": "preliminary-rule-derived-inference-id.v0.2",
        "source_fact_ids": sorted(set(fact_ids)),
        "source_reviewed_inference_ids": sorted(set(reviewed_ids)),
        "source_span_signatures": [_source_span_signature(source.span)],
    }


def _component_payload(component: dict[str, Any]) -> dict[str, Any]:
    return {"schema": "preliminary-component-id.v0.2", **component}


def _component_sort_key(item: PreliminaryComponent) -> tuple[Any, ...]:
    starts = [span.document_start for span in item.source_spans]
    ends = [span.document_end for span in item.source_spans]
    return (
        item.parent_step_sequence,
        SOURCE_FIELD_RANK[item.source_field],
        item.source_item_index,
        item.clause_index,
        item.matched_token_start,
        min(starts),
        max(ends),
        item.pd2_rule_code,
        item.component_action.value,
        item.component_id,
    )


class PreliminaryAssessmentEvaluatorV2:
    """Evaluate exactly one approved review under the explicit v0.2 contract."""

    def __init__(self, *, rules: PreliminaryEvaluatorRulesV2 = PRELIMINARY_EVALUATOR_RULES_V0_2) -> None:
        self._rules = rules
        self._fingerprint = rules.fingerprint()

    def evaluate(self, approved_review: ApprovedProcessReview) -> PreliminaryEvaluationResultV2:
        if self._rules.canonical_json_bytes() != PRELIMINARY_EVALUATOR_RULES_V0_2.canonical_json_bytes():
            return self._failure(PreliminaryEvaluationFailureCodeV2.INVALID_RULE_SET, "The v0.2 rule artifact or fingerprint is not canonical.", "rules")
        if not isinstance(approved_review, ApprovedProcessReview):
            return self._failure(PreliminaryEvaluationFailureCodeV2.APPROVED_REVIEW_REQUIRED, "Evaluation requires exactly one ApprovedProcessReview.")
        try:
            approved = ApprovedProcessReview.model_validate(approved_review.model_dump(mode="python"))
            error = self._validate_approved(approved)
            if error:
                return error
            activity_results = tuple(
                self._evaluate_activity(step, approved)
                for step in sorted((item for item in approved.review.steps if item.retained), key=lambda item: item.sequence)
            )
            counts = {coverage: sum(item.evidence_coverage is coverage for item in activity_results) for coverage in EvidenceCoverage}
            weakest = max((item.evidence_coverage for item in activity_results), key=COVERAGE_RANK.get)
            approval_event = next(item for item in approved.review.events if item.action is ReviewAction.APPROVE)
            lineage = PreliminaryAssessmentLineageV2(
                source_document_id=approved.review.original_candidate.source_document_id,
                extraction_run_id=approved.review.original_candidate.extraction_run_id,
                approved_review_artifact_id=approved.review.review_id,
                approval_event_id=approval_event.event_id,
                validated_process_id=approved.business_process.process_id,
                validated_process_fingerprint=fingerprint_business_process(approved.business_process),
            )
            assessment_seed = {
                "schema": "preliminary-assessment-identity.v0.2",
                "lineage": lineage.model_dump(mode="json"),
                "rule_set_fingerprint": self._fingerprint,
                "activity_result_ids": [
                    [item.activity_identity, [op.opportunity_id for op in item.opportunities], [dis.scoped_discovery_id for dis in item.scoped_discoveries]]
                    for item in activity_results
                ],
            }
            assessment = PreliminaryAssessmentV2(
                preliminary_assessment_id=content_id("pa2-", assessment_seed),
                rule_set_fingerprint=self._fingerprint,
                lineage=lineage,
                process_id=approved.business_process.process_id,
                process_name=approved.business_process.name,
                activity_results=activity_results,
                evidence_coverage=weakest,
                high_activity_count=counts[EvidenceCoverage.HIGH],
                medium_activity_count=counts[EvidenceCoverage.MEDIUM],
                low_activity_count=counts[EvidenceCoverage.LOW],
            )
            return PreliminaryEvaluationSuccessV2(assessment=assessment)
        except (ValidationError, ValueError, TypeError, KeyError, StopIteration) as exc:
            return self._failure(PreliminaryEvaluationFailureCodeV2.OUTPUT_VALIDATION_FAILED, f"v0.2 output validation failed: {exc}")

    def _failure(self, code: PreliminaryEvaluationFailureCodeV2, message: str, field_path: str | None = None) -> PreliminaryEvaluationFailureV2:
        return PreliminaryEvaluationFailureV2(
            rule_set_fingerprint=self._fingerprint,
            errors=(PreliminaryEvaluationErrorV2(code=code, message=message, field_path=field_path),),
        )

    def _validate_approved(self, approved: ApprovedProcessReview) -> PreliminaryEvaluationFailureV2 | None:
        review = approved.review
        if review.status is not ReviewStatus.APPROVED or not review.order_accepted:
            return self._failure(PreliminaryEvaluationFailureCodeV2.INVALID_APPROVAL_ARTIFACT, "The review is not an approved, ordered current-state process.", "review")
        approval_events = [item for item in review.events if item.action is ReviewAction.APPROVE]
        if len(approval_events) != 1 or approval_events[0].occurred_at != approved.approval.approved_at:
            return self._failure(PreliminaryEvaluationFailureCodeV2.INVALID_APPROVAL_ARTIFACT, "Approval event identity is invalid.", "review.events")
        if any(item.blocking and item.status is ConflictStatus.OPEN for item in review.conflicts):
            return self._failure(PreliminaryEvaluationFailureCodeV2.INVALID_APPROVAL_ARTIFACT, "Approved review contains an open blocking conflict.", "review.conflicts")
        expected = _project_business_process(review)
        if expected.model_dump(mode="json") != approved.business_process.model_dump(mode="json"):
            return self._failure(PreliminaryEvaluationFailureCodeV2.INVALID_PROCESS_PROJECTION, "Validated process does not match the approved review.", "business_process")
        trusted = _candidate_evidence(review.original_candidate)
        source_document_id = review.original_candidate.source_document_id
        for path, assertion, _, _ in _all_assertions(review.steps):
            for reference in assertion.evidence:
                if reference.document_id != source_document_id:
                    return self._failure(PreliminaryEvaluationFailureCodeV2.INVALID_SOURCE_LINEAGE, "Evidence is not from the pinned approved source document.", path)
                original = trusted.get(reference.evidence_id)
                if original is None or original.model_dump(mode="json") != reference.model_dump(mode="json"):
                    return self._failure(PreliminaryEvaluationFailureCodeV2.INVALID_SOURCE_SPAN, "Evidence offsets or exact text do not match the immutable extraction lineage.", path)
        return None

    def _evaluate_activity(self, step: ReviewedProcessStep, approved: ApprovedProcessReview) -> PreliminaryActivityResultV2:
        activity_identity = step.candidate_step_id
        sources, documented, reviewed, unknowns = _admitted_sources(step, approved.review.review_id, approved.review.original_candidate.source_document_id)
        conflicts = tuple(
            EvidenceRecord(item_id=item.conflict_id, classification=KnowledgeClassification.CONFLICT, statement=item.message)
            for item in approved.review.conflicts
            if item.status is ConflictStatus.OPEN and (item.field_path or "").startswith(f"steps.{step.candidate_step_id}")
        )
        drafts: list[_Draft] = []
        unsupported_sources: list[_AdmittedSource] = []
        for source in sources:
            found = False
            for clause in segment_clauses(source.span.exact_text):
                matches = _match_clause(clause)
                found = found or bool(matches)
                for match in matches:
                    drafts.append(
                        _Draft(
                            match=match,
                            source=source,
                            owner_signature=_owner_signature(step, match.actor),
                            control_signature=_control_signature(step, match.family.pd2_rule_code),
                            safety_signature=_safety_signature(step),
                            accountability_signature=_accountability_signature(step, match.actor, match.family.pd2_rule_code),
                            conflict_signature=tuple(item.item_id for item in conflicts),
                        )
                    )
                if VAGUE_UNSUPPORTED.search(clause.text):
                    unsupported_sources.append(source)
            if not found and source.source_field in {"activity", "description", "operational_characteristics", "decisions", "exceptions"}:
                unsupported_sources.append(source)

        drafts.sort(key=lambda item: (
            step.sequence,
            SOURCE_FIELD_RANK[item.source.source_field],
            item.source.source_item_index,
            item.match.clause.index,
            item.match.token_start,
            item.source.span.document_start,
            item.match.family.pd2_rule_code,
            item.match.family.component_action.value,
        ))
        components, inferences = self._materialize_components(activity_identity, step.sequence, drafts)
        work_needs = self._construct_work_needs(activity_identity, components)

        if conflicts:
            discovery = self._discovery(activity_identity, "MATERIAL_EVIDENCE_CONFLICT", ("RESOLVE_CONFLICT",), components, work_needs, tuple(item.item_id for item in conflicts), ())
            return self._activity(ActivityResultType.DISCOVERY_REQUIRED, "PAR2-003", activity_identity, approved, documented, reviewed, inferences, unknowns, conflicts, components, work_needs, (), (discovery,), "PA2-003", "Material direction-bearing evidence remains conflicted.")

        if not components:
            if _affirmative_no_change(step, sources):
                trace = (_trace("affirmative_no_change_bundle", True, KnowledgeClassification.DOCUMENTED_FACT, (), "STAGE_7", "ALL", True, True, None, "PA2-010", "SELECTED", "PA2-010"),)
                return PreliminaryActivityResultV2(
                    result_type=ActivityResultType.NO_CHANGE,
                    construction_code="PAR2-004",
                    activity_identity=activity_identity,
                    source_document_id=approved.review.original_candidate.source_document_id,
                    rule_set_fingerprint=self._fingerprint,
                    documented_facts=documented,
                    reviewed_inferences=reviewed,
                    unknowns=unknowns,
                    decision_input_trace=trace,
                    evidence_coverage=EvidenceCoverage.HIGH,
                    rationale="Complete affirmative documentary no-change bundle selected PA2-010.",
                    deciding_rule_code="PA2-010",
                )
            discovery = self._discovery(activity_identity, "NO_DIRECTION_BEARING_EVIDENCE", ("CLARIFY_CURRENT_ACTIVITY",), (), (), (), tuple(item.item_id for item in unknowns))
            return self._activity(ActivityResultType.DISCOVERY_REQUIRED, "PAR2-003", activity_identity, approved, documented, reviewed, (), unknowns, conflicts, (), (), (), (discovery,), "PA2-002", "No admissible direction-bearing evidence was found.")

        need_by_component = {component_id: need.work_need_id for need in work_needs for component_id in need.component_ids}
        selections = tuple(self._select(component, need_by_component[component.component_id], step) for component in components)
        actionable_selections = tuple(
            item for item in selections if item.code not in {"PA2-001", "PA2-002", "PA2-003", "PA2-004"}
        )
        opportunities = self._group_opportunities(
            activity_identity, actionable_selections, work_needs
        )
        discoveries: list[ScopedDiscoveryNeed] = []
        unresolved_selections = tuple(
            item for item in selections if item.code in {"PA2-001", "PA2-002", "PA2-003", "PA2-004"}
        )
        if unresolved_selections:
            unresolved_components = tuple(item.component for item in unresolved_selections)
            unresolved_need_ids = {item.work_need_id for item in unresolved_selections}
            discoveries.append(
                self._discovery(
                    activity_identity,
                    "INSEPARABLE_SCOPE",
                    ("CLARIFY_INPUT", "CLARIFY_OUTPUT"),
                    unresolved_components,
                    tuple(item for item in work_needs if item.work_need_id in unresolved_need_ids),
                    (),
                    (),
                )
            )
        if unsupported_sources:
            spans = tuple(sorted({item.span.signature(): item.span for item in unsupported_sources}.values(), key=lambda item: item.signature()))
            discoveries.append(self._discovery(activity_identity, "UNSUPPORTED_CHARACTERISTIC", ("CLARIFY_CURRENT_ACTIVITY", "CLARIFY_OUTPUT"), (), (), (), (), spans=spans))
        if any(item.code == "PA2-051" for item in selections):
            semantic = tuple(item.component for item in selections if item.code == "PA2-051")
            related_need_ids = tuple(dict.fromkeys(item.work_need_id for item in selections if item.code == "PA2-051"))
            discoveries.append(self._discovery(activity_identity, "MISSING_REQUIRED_COMPONENT_FIELD", ("RESOLVE_RISK_AND_GOVERNANCE",), semantic, tuple(item for item in work_needs if item.work_need_id in related_need_ids), (), tuple(f"unknown:governance:{item.component.component_id}" for item in selections if item.code == "PA2-051")))

        if len(opportunities) > 5:
            discovery = self._discovery(activity_identity, "OPPORTUNITY_PARTITION_EXCEEDS_LIMIT", ("SPLIT_OR_CLARIFY_ACTIVITY_SCOPE",), components, work_needs, (), ())
            return self._activity(ActivityResultType.DISCOVERY_REQUIRED, "PAR2-003", activity_identity, approved, documented, reviewed, inferences, unknowns, conflicts, components, work_needs, (), (discovery,), "PA2-004", "More than five independently governed opportunities require the activity to be split or clarified.", candidate_partition=tuple(item.opportunity_id for item in opportunities))

        if not opportunities:
            return self._activity(
                ActivityResultType.DISCOVERY_REQUIRED,
                "PAR2-003",
                activity_identity,
                approved,
                documented,
                reviewed,
                inferences,
                unknowns,
                conflicts,
                components,
                work_needs,
                (),
                tuple(discoveries),
                "PA2-004",
                "The admitted components do not establish an actionable direction without clarification.",
            )
        construction = "PAR2-001" if len(opportunities) == 1 else "PAR2-002"
        coverage = max([item.evidence_coverage for item in opportunities] + [item.evidence_coverage for item in discoveries], key=COVERAGE_RANK.get)
        trace = tuple(entry for item in opportunities for entry in item.decision_input_trace) + tuple(entry for item in discoveries for entry in item.decision_input_trace)
        return PreliminaryActivityResultV2(
            result_type=ActivityResultType.ACTIONABLE,
            construction_code=construction,
            activity_identity=activity_identity,
            source_document_id=approved.review.original_candidate.source_document_id,
            rule_set_fingerprint=self._fingerprint,
            documented_facts=documented,
            reviewed_inferences=reviewed,
            rule_derived_inferences=inferences,
            unknowns=unknowns,
            conflicts=conflicts,
            components=components,
            work_needs=work_needs,
            opportunities=opportunities,
            scoped_discoveries=tuple(discoveries),
            decision_input_trace=trace,
            evidence_coverage=coverage,
            rationale=f"Deterministic partition produced {len(opportunities)} independently governed opportunity result(s).",
            next_evidence_to_collect=tuple(dict.fromkeys(code for item in discoveries for code in item.evidence_request_codes)),
        )

    def _materialize_components(self, activity_identity: str, sequence: int, drafts: list[_Draft]) -> tuple[tuple[PreliminaryComponent, ...], tuple[RuleDerivedInference, ...]]:
        components: list[PreliminaryComponent] = []
        inferences: list[RuleDerivedInference] = []
        prior_outputs: dict[str, str] = {}
        for draft in drafts:
            match = draft.match
            source = draft.source
            inferred_payload = _inference_payload(draft, self._fingerprint)
            inferred_payload["activity_identity"] = activity_identity
            inference_id = content_id("pri2-", inferred_payload)
            fact_ids = (source.record.item_id,) if source.classification is KnowledgeClassification.DOCUMENTED_FACT else ()
            reviewed_ids = (source.record.item_id,) if source.classification is KnowledgeClassification.REVIEWED_INFERENCE else ()
            inference = RuleDerivedInference(
                inference_id=inference_id,
                pd2_rule_code=match.family.pd2_rule_code,
                matched_literal_code=match.family.matched_literal_code,
                normalized_derived_characteristic=inferred_payload["normalized_derived_characteristic"],
                source_fact_ids=fact_ids,
                source_reviewed_inference_ids=reviewed_ids,
                source_spans=(source.span,),
            )
            dependencies: list[str] = []
            input_key = match.input_artifact or (
                match.obj if match.family.component_action is ComponentAction.NOTIFY else None
            )
            if input_key:
                canonical_input = _canonical_dependency_artifact(input_key)
                if canonical_input in prior_outputs:
                    dependencies.append(prior_outputs[canonical_input])
            elif (
                match.clause.inherited_actor is not None
                or re.search(r"\b(after|once|using|based on|then|and then)\b", match.clause.text, re.IGNORECASE)
            ) and components:
                dependencies.append(components[-1].component_id)
            span = source.span
            sub_start = match.clause.start + match.start
            sub_end = match.clause.start + match.end
            subspan = MatchedSubSpan(
                parent_source_span_signature=span.signature(),
                match_start_in_span=sub_start,
                match_end_in_span=sub_end,
                exact_matched_text=span.exact_text[sub_start:sub_end],
                normalized_matched_key=normalize_matching_text(match.exact),
                matched_literal_code=match.family.matched_literal_code,
            )
            payload = {
                "activity_identity": activity_identity,
                "accountability_signature": list(draft.accountability_signature),
                "clause_index": match.clause.index,
                "component_action": match.family.component_action.value,
                "conflict_signature": list(draft.conflict_signature),
                "control_signature": list(draft.control_signature),
                "dependency_component_ids": dependencies,
                "matched_literal_code": match.family.matched_literal_code,
                "matched_token_end": match.token_end,
                "matched_token_start": match.token_start,
                "normalized_actor": match.actor,
                "normalized_destination": match.destination,
                "normalized_input_artifact": match.input_artifact,
                "normalized_object": match.obj,
                "normalized_output_artifact": match.output_artifact,
                "normalized_recipient": match.recipient,
                "owner_signature": list(draft.owner_signature),
                "parent_step_sequence": sequence,
                "pd2_rule_code": match.family.pd2_rule_code,
                "rule_derived_inference_id": inference_id,
                "safety_signature": list(draft.safety_signature),
                "source_fact_ids": list(fact_ids),
                "source_field": source.source_field,
                "source_item_index": source.source_item_index,
                "source_reviewed_inference_ids": list(reviewed_ids),
                "source_span_signatures": [_source_span_signature(span)],
            }
            component_id = content_id("pac2-", _component_payload(payload))
            component = PreliminaryComponent(
                component_id=component_id,
                activity_identity=activity_identity,
                parent_step_sequence=sequence,
                source_field=source.source_field,
                source_item_index=source.source_item_index,
                clause_index=match.clause.index,
                matched_token_start=match.token_start,
                matched_token_end=match.token_end,
                pd2_rule_code=match.family.pd2_rule_code,
                matched_literal_code=match.family.matched_literal_code,
                component_action=match.family.component_action,
                normalized_actor=match.actor,
                normalized_object=match.obj,
                normalized_input_artifact=match.input_artifact,
                normalized_output_artifact=match.output_artifact,
                normalized_recipient=match.recipient,
                normalized_destination=match.destination,
                source_fact_ids=fact_ids,
                source_reviewed_inference_ids=reviewed_ids,
                rule_derived_inference_id=inference_id,
                source_spans=(span,),
                matched_sub_spans=(subspan,),
                dependency_component_ids=tuple(dependencies),
                source_document_id=span.source_document_id,
                owner_signature=draft.owner_signature,
                control_signature=draft.control_signature,
                safety_signature=draft.safety_signature,
                accountability_signature=draft.accountability_signature,
                conflict_signature=draft.conflict_signature,
            )
            components.append(component)
            inferences.append(inference)
            if match.output_artifact:
                prior_outputs[_canonical_dependency_artifact(match.output_artifact)] = component_id
        ordered = tuple(sorted(components, key=_component_sort_key))
        by_inference = {item.inference_id: item for item in inferences}
        return ordered, tuple(by_inference[item.rule_derived_inference_id] for item in ordered)

    def _construct_work_needs(self, activity_identity: str, components: tuple[PreliminaryComponent, ...]) -> tuple[WorkNeed, ...]:
        groups: list[list[PreliminaryComponent]] = []
        for component in components:
            if not groups or not _work_need_mergeable(groups[-1], component):
                groups.append([component])
            else:
                groups[-1].append(component)
        needs: list[WorkNeed] = []
        for group in groups:
            need_type = WORK_NEED_BY_RULE_ACTION[(group[0].pd2_rule_code, group[0].component_action)]
            objects = tuple(sorted({_object_key(item) for item in group}))
            payload = {
                "activity_identity": activity_identity,
                "component_ids": [item.component_id for item in group],
                "normalized_object_keys": list(objects),
                "pd2_rule_codes": list(dict.fromkeys(item.pd2_rule_code for item in group)),
                "schema": "preliminary-work-need-id.v0.2",
                "work_need_type": need_type.value,
            }
            needs.append(WorkNeed(work_need_id=content_id("pwn2-", payload), activity_identity=activity_identity, work_need_type=need_type, component_ids=tuple(payload["component_ids"]), normalized_object_keys=objects, pd2_rule_codes=tuple(payload["pd2_rule_codes"])))
        return tuple(sorted(needs, key=lambda item: (WORK_NEED_RANK[item.work_need_type], min(_component_sort_key(next(c for c in components if c.component_id == cid)) for cid in item.component_ids), item.work_need_id)))

    def _select(self, component: PreliminaryComponent, work_need_id: str, step: ReviewedProcessStep) -> _Selection:
        pd2 = component.pd2_rule_code
        documentary_text = _documented_text(step)
        high_risk = (
            _criterion_value(step, CriterionName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT)
            in {4, 5}
            or _criterion_value(step, CriterionName.RISK_CONSEQUENCE) in {4, 5}
            or bool(
                re.search(
                    r"\b(?:residual risk|error consequence)\s*[:=]?\s*[45]\b",
                    documentary_text,
                )
            )
        )
        veto = _documented_phrase(step, ("ai assistance is prohibited", "assistance is prohibited", "must not use ai"))
        if veto and pd2 in SEMANTIC_RULES:
            direction, code, stage = ProvisionalDirectionV2.LIKELY_HUMAN_LED, "PA2-020", "STAGE_1"
        elif pd2 == "PD2-016":
            direction, code, stage = ProvisionalDirectionV2.LIKELY_HUMAN_LED, "PA2-020", "STAGE_2"
        elif pd2 in {"PD2-018", "PD2-019"}:
            direction, code, stage = ProvisionalDirectionV2.LIKELY_PROCESS_IMPROVEMENT_FIRST, "PA2-030", "STAGE_3"
        elif (pd2 in DIRECT_RULES and _conventional_sufficiency(component)) or (
            pd2 in {"PD2-010", "PD2-011"}
            and _closed_deterministic(step, component)
            and _conventional_sufficiency(component)
        ):
            code = "PA2-041" if pd2 == "PD2-007" else "PA2-040"
            direction, stage = ProvisionalDirectionV2.LIKELY_CONVENTIONAL_AUTOMATION, "STAGE_4"
        elif pd2 in SEMANTIC_RULES and not high_risk and _autonomy_bundle(step):
            direction, code, stage = ProvisionalDirectionV2.POTENTIAL_AI_AUTOMATION, "PA2-052", "STAGE_5"
        elif pd2 in SEMANTIC_RULES and not high_risk and _assistance_bundle(step):
            direction, code, stage = ProvisionalDirectionV2.POTENTIAL_AI_ASSISTED_WORK, "PA2-050", "STAGE_5"
        elif pd2 in SEMANTIC_RULES and not high_risk and pd2 != "PD2-017":
            direction, code, stage = ProvisionalDirectionV2.POTENTIAL_AI_ASSISTED_WORK, "PA2-051", "STAGE_5"
        elif pd2 in {"PD2-015", "PD2-017"}:
            direction, code, stage = ProvisionalDirectionV2.LIKELY_HUMAN_LED, "PA2-021", "STAGE_6"
        else:
            direction, code, stage = ProvisionalDirectionV2.INSUFFICIENT_BASIS_TO_SUGGEST_A_DIRECTION, "PA2-004", "STAGE_7"
        trace = (
            _trace(
                f"component:{component.component_id}",
                component.component_action.value,
                KnowledgeClassification.RULE_DERIVED_INFERENCE,
                (*component.source_fact_ids, *component.source_reviewed_inference_ids, component.rule_derived_inference_id),
                stage,
                "PD2_TO_PA2_AND_PRECEDENCE",
                code,
                True,
                pd2,
                code,
                "SELECTED",
                code,
            ),
        )
        unknown_ids = (f"unknown:governance:{component.component_id}",) if code == "PA2-051" else ()
        return _Selection(component=component, work_need_id=work_need_id, direction=direction, code=code, trace=trace, unknown_ids=unknown_ids)

    def _group_opportunities(self, activity_identity: str, selections: tuple[_Selection, ...], work_needs: tuple[WorkNeed, ...]) -> tuple[Opportunity, ...]:
        groups: list[list[_Selection]] = []
        for item in selections:
            if not groups or not _opportunity_mergeable(groups[-1], item):
                groups.append([item])
            else:
                groups[-1].append(item)
        opportunities: list[Opportunity] = []
        for group in groups:
            components = tuple(item.component for item in group)
            need_ids = tuple(dict.fromkeys(item.work_need_id for item in group))
            spans = tuple(sorted({span.signature(): span for item in components for span in item.source_spans}.values(), key=lambda item: item.signature()))
            evidence_ids = tuple(sorted({*{fid for item in components for fid in item.source_fact_ids}, *{rid for item in components for rid in item.source_reviewed_inference_ids}}))
            inference_ids = tuple(
                sorted(
                    {
                        *{item.rule_derived_inference_id for item in components},
                        *{
                            inference_id
                            for item in components
                            for inference_id in item.source_reviewed_inference_ids
                        },
                    }
                )
            )
            unknown_ids = tuple(sorted({unknown for item in group for unknown in item.unknown_ids}))
            if len(group) == 1:
                construction = "POG2-001"
            elif any(item.component.dependency_component_ids for item in group[1:]):
                construction = "POG2-003"
            elif len(need_ids) == 1:
                construction = "POG2-002"
            else:
                construction = "POG2-004"
            payload = {
                "accountability_signature": list(components[0].accountability_signature),
                "activity_identity": activity_identity,
                "component_ids": [item.component_id for item in components],
                "conflict_ids": list(components[0].conflict_signature),
                "construction_code": construction,
                "control_signature": list(components[0].control_signature),
                "deciding_rule_code": group[0].code,
                "direction": group[0].direction.value,
                "material_evidence_item_ids": list(evidence_ids),
                "material_inference_ids": list(inference_ids),
                "material_unknown_ids": list(unknown_ids),
                "owner_signature": list(components[0].owner_signature),
                "rule_set_fingerprint": self._fingerprint,
                "safety_signature": list(components[0].safety_signature),
                "schema": "preliminary-opportunity-id.v0.2",
                "source_span_signatures": [_source_span_signature(span) for span in spans],
                "work_need_ids": list(need_ids),
            }
            coverage = EvidenceCoverage.LOW if len(inference_ids) >= 2 or unknown_ids or group[0].code == "PA2-051" else EvidenceCoverage.MEDIUM if len(inference_ids) == 1 else EvidenceCoverage.HIGH
            opportunities.append(Opportunity(
                opportunity_id=content_id("pop2-", payload),
                activity_identity=activity_identity,
                direction=group[0].direction,
                deciding_rule_code=group[0].code,
                construction_code=construction,
                component_ids=tuple(payload["component_ids"]),
                work_need_ids=need_ids,
                owner_signature=components[0].owner_signature,
                control_signature=components[0].control_signature,
                safety_signature=components[0].safety_signature,
                accountability_signature=components[0].accountability_signature,
                conflict_ids=components[0].conflict_signature,
                material_evidence_item_ids=evidence_ids,
                material_inference_ids=inference_ids,
                material_unknown_ids=unknown_ids,
                source_spans=spans,
                decision_input_trace=tuple(entry for item in group for entry in item.trace),
                evidence_coverage=coverage,
                rationale=f"{group[0].code} selected deterministically for {len(components)} component(s).",
            ))
        return tuple(opportunities)

    def _discovery(self, activity_identity: str, reason: str, requests: tuple[str, ...], components: Iterable[PreliminaryComponent], work_needs: Iterable[WorkNeed], conflict_ids: tuple[str, ...], unknown_ids: tuple[str, ...], *, spans: tuple[SourceSpan, ...] = ()) -> ScopedDiscoveryNeed:
        components = tuple(components)
        work_needs = tuple(work_needs)
        if not spans:
            spans = tuple(sorted({span.signature(): span for item in components for span in item.source_spans}.values(), key=lambda item: item.signature()))
        evidence_ids = tuple(sorted({*{fid for item in components for fid in item.source_fact_ids}, *{rid for item in components for rid in item.source_reviewed_inference_ids}}))
        payload = {
            "activity_identity": activity_identity,
            "conflict_ids": list(sorted(set(conflict_ids))),
            "discovery_reason_code": reason,
            "evidence_request_codes": list(dict.fromkeys(requests)),
            "material_evidence_item_ids": list(evidence_ids),
            "related_component_ids": [item.component_id for item in components],
            "related_work_need_ids": [item.work_need_id for item in work_needs],
            "rule_set_fingerprint": self._fingerprint,
            "schema": "preliminary-scoped-discovery-id.v0.2",
            "source_span_signatures": [_source_span_signature(span) for span in spans],
            "unknown_ids": list(sorted(set(unknown_ids))),
        }
        trace = (_trace(f"discovery:{reason}", None, KnowledgeClassification.UNKNOWN, evidence_ids, "STAGE_0" if "CONFLICT" in reason or "SCOPE" in reason else "STAGE_7", "REQUIRES_DISCOVERY", reason, False, None, "PA2-004" if reason != "NO_DIRECTION_BEARING_EVIDENCE" else "PA2-002", "SELECTED", reason),)
        return ScopedDiscoveryNeed(
            scoped_discovery_id=content_id("psd2-", payload),
            activity_identity=activity_identity,
            discovery_reason_code=reason,
            evidence_request_codes=tuple(payload["evidence_request_codes"]),
            related_component_ids=tuple(payload["related_component_ids"]),
            related_work_need_ids=tuple(payload["related_work_need_ids"]),
            material_evidence_item_ids=evidence_ids,
            unknown_ids=tuple(payload["unknown_ids"]),
            conflict_ids=tuple(payload["conflict_ids"]),
            source_spans=spans,
            decision_input_trace=trace,
            rationale=f"Scoped discovery is required: {reason}.",
        )

    def _activity(self, result_type: ActivityResultType, construction: str, activity_identity: str, approved: ApprovedProcessReview, documented: tuple[EvidenceRecord, ...], reviewed: tuple[EvidenceRecord, ...], inferences: tuple[RuleDerivedInference, ...], unknowns: tuple[EvidenceRecord, ...], conflicts: tuple[EvidenceRecord, ...], components: tuple[PreliminaryComponent, ...], work_needs: tuple[WorkNeed, ...], opportunities: tuple[Opportunity, ...], discoveries: tuple[ScopedDiscoveryNeed, ...], deciding: str, rationale: str, *, candidate_partition: tuple[str, ...] = ()) -> PreliminaryActivityResultV2:
        trace = tuple(entry for item in discoveries for entry in item.decision_input_trace)
        return PreliminaryActivityResultV2(
            result_type=result_type,
            construction_code=construction,
            activity_identity=activity_identity,
            source_document_id=approved.review.original_candidate.source_document_id,
            rule_set_fingerprint=self._fingerprint,
            documented_facts=documented,
            reviewed_inferences=reviewed,
            rule_derived_inferences=inferences,
            unknowns=unknowns,
            conflicts=conflicts,
            components=components,
            work_needs=work_needs,
            opportunities=opportunities,
            scoped_discoveries=discoveries,
            candidate_partition_trace=candidate_partition,
            decision_input_trace=trace,
            evidence_coverage=EvidenceCoverage.LOW,
            rationale=rationale,
            next_evidence_to_collect=tuple(dict.fromkeys(code for item in discoveries for code in item.evidence_request_codes)),
            deciding_rule_code=deciding,
        )


def _trace(name: str, value: str | int | bool | None, classification: KnowledgeClassification, evidence_ids: Iterable[str], stage: str, operator: str, comparison_value: str | int | bool | None, result: bool | None, pd2: str | None, pa2: str | None, status: str, precedence: str) -> DecisionTraceEntry:
    return DecisionTraceEntry(input_name=name, normalized_value=value, knowledge_classification=classification, evidence_item_ids=tuple(sorted(set(evidence_ids))), material=True, evaluation_stage=stage, comparison_operator=operator, comparison_value=comparison_value, comparison_result=result, producing_pd2_code=pd2, candidate_pa2_code=pa2, selection_status=status, precedence_or_rejection_code=precedence)


def _candidate_evidence(candidate: Any) -> dict[str, Any]:
    found: dict[str, Any] = {}
    def walk(value: Any) -> None:
        if hasattr(value, "evidence_id") and hasattr(value, "exact_snippet"):
            found[value.evidence_id] = value
        elif isinstance(value, dict):
            for item in value.values(): walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value: walk(item)
        elif hasattr(value, "model_dump"):
            for item in value.__dict__.values(): walk(item)
    walk(candidate)
    return found


def _all_assertions(steps: Iterable[ReviewedProcessStep]) -> Iterable[tuple[str, ReviewedAssertion, str, int]]:
    for step in steps:
        prefix = f"steps.{step.candidate_step_id}"
        yield f"{prefix}.activity", step.activity, "activity", 0
        yield f"{prefix}.description", step.description, "description", 0
        for field, collection in (("inputs", step.inputs), ("outputs", step.outputs), ("exceptions", step.exceptions), ("operational_characteristics", step.operational_characteristics), ("roles", step.responsible_roles), ("systems", step.systems)):
            for index, item in enumerate(collection.items):
                yield f"{prefix}.{field}.{index}", item, field, index
        for index, decision in enumerate(step.decisions):
            yield f"{prefix}.decisions.{index}.condition", decision.condition, "decisions", index
            for subindex, item in enumerate(decision.branches.items):
                yield f"{prefix}.decisions.{index}.branches.{subindex}", item, "decisions", index + subindex + 1
        for index, dependency in enumerate(step.dependencies):
            yield f"{prefix}.dependencies.{index}.relationship", dependency.relationship, "dependencies", index
        for index, characteristic in enumerate(step.criteria):
            yield f"{prefix}.criteria.{characteristic.name.value}", characteristic.assertion, "criteria", index
        for index, signal in enumerate(step.capability_signals):
            yield f"{prefix}.capabilities.{signal.name}", signal.assertion, "capabilities", index


def _admitted_sources(step: ReviewedProcessStep, review_id: str, source_document_id: str) -> tuple[tuple[_AdmittedSource, ...], tuple[EvidenceRecord, ...], tuple[EvidenceRecord, ...], tuple[EvidenceRecord, ...]]:
    sources: list[_AdmittedSource] = []
    documented: dict[str, EvidenceRecord] = {}
    reviewed: dict[str, EvidenceRecord] = {}
    unknowns: dict[str, EvidenceRecord] = {}
    seen: set[tuple[str, KnowledgeClassification]] = set()
    for path, assertion, field, item_index in _all_assertions((step,)):
        if not assertion.retained or assertion.disposition not in {ReviewDisposition.ACCEPTED, ReviewDisposition.CORRECTED, ReviewDisposition.UNKNOWN_RETAINED}:
            continue
        if assertion.knowledge_state is KnowledgeState.UNKNOWN:
            unknown_id = content_id("pu2-", {"schema": "preliminary-unknown.v0.2", "activity_identity": step.candidate_step_id, "field_path": path})
            unknowns[unknown_id] = EvidenceRecord(item_id=unknown_id, classification=KnowledgeClassification.UNKNOWN, statement=f"{path} remains unknown")
            continue
        if assertion.origin is InformationOrigin.HUMAN_SUPPLIED:
            continue
        classification = KnowledgeClassification.DOCUMENTED_FACT if assertion.origin is InformationOrigin.DOCUMENT_SUPPORTED else KnowledgeClassification.REVIEWED_INFERENCE
        for reference in assertion.evidence:
            key = (reference.evidence_id, classification)
            if key in seen:
                continue
            seen.add(key)
            item_id = content_id("pdf2-" if classification is KnowledgeClassification.DOCUMENTED_FACT else "pin2-", {"schema": "preliminary-admitted-source.v0.2", "activity_identity": step.candidate_step_id, "classification": classification.value, "evidence_id": reference.evidence_id, "field_path": path, "statement": str(assertion.value)})
            span = SourceSpan(
                source_document_id=source_document_id,
                approved_review_artifact_id=review_id,
                approved_evidence_item_id=reference.evidence_id,
                source_block_id=reference.block_id,
                document_start=reference.document_start_offset,
                document_end=reference.document_end_offset,
                block_start=reference.block_start_offset,
                block_end=reference.block_end_offset,
                exact_text=reference.exact_snippet,
                source_locator=reference.source_locator,
                fact_or_reviewed_inference_id=item_id,
            )
            record = EvidenceRecord(item_id=item_id, classification=classification, statement=str(assertion.value), source_spans=(span,))
            (documented if classification is KnowledgeClassification.DOCUMENTED_FACT else reviewed)[item_id] = record
            sources.append(_AdmittedSource(source_field=field, source_item_index=item_index, classification=classification, record=record, span=span))
    sources.sort(key=lambda item: (SOURCE_FIELD_RANK[item.source_field], item.source_item_index, item.span.signature()))
    return tuple(sources), tuple(documented.values()), tuple(reviewed.values()), tuple(unknowns.values())


def _owner_signature(step: ReviewedProcessStep, actor: str | None) -> tuple[str, ...]:
    owners = [normalize_matching_text(str(item.value), token_key=False) for item in (*step.responsible_roles.items, *step.actors.items) if item.retained and item.value]
    if step.primary_actor:
        owners.append(normalize_matching_text(step.primary_actor, token_key=False))
    if not owners and actor:
        owners.append(actor)
    return tuple(sorted({item for item in owners if item})) or ("OWNER_UNKNOWN",)


def _control_signature(step: ReviewedProcessStep, pd2: str) -> tuple[str, ...]:
    values: list[str] = []
    if pd2 == "PD2-017": values.append("CONTROL_MATERIAL_DISCRETION")
    if pd2 == "PD2-016": values.append("CONTROL_MANDATORY_HUMAN_DECISION")
    text = _documented_text(step)
    if "mandatory human review" in text: values.append("CONTROL_MANDATORY_HUMAN_REVIEW")
    if "autonomous operation explicitly permitted" in text: values.append("CONTROL_EXPLICIT_AUTONOMY")
    rank = {"CONTROL_MATERIAL_DISCRETION": 1, "CONTROL_MANDATORY_HUMAN_DECISION": 2, "CONTROL_MANDATORY_HUMAN_REVIEW": 3, "CONTROL_EXPLICIT_AUTONOMY": 4, "CONTROL_UNKNOWN": 5}
    return tuple(sorted(set(values), key=rank.get)) or ("CONTROL_UNKNOWN",)


def _safety_signature(step: ReviewedProcessStep) -> tuple[str, ...]:
    text = _documented_text(step)
    values: list[str] = []
    if "assistance is prohibited" in text or "must not use ai" in text: values.append("ASSISTANCE_VETO")
    if "autonomy is prohibited" in text: values.append("AUTONOMY_VETO")
    if all(f"{item} resolved" in text for item in ("safety", "legal", "privacy", "regulatory")): values.append("RESOLVED_FOR_SCOPE")
    return tuple(values) or ("UNKNOWN",)


def _accountability_signature(step: ReviewedProcessStep, actor: str | None, pd2: str) -> tuple[str, ...]:
    if pd2 == "PD2-016": return ("MANDATORY_HUMAN",)
    owners = _owner_signature(step, actor)
    if owners != ("OWNER_UNKNOWN",): return tuple(f"OWNER:{item}" for item in owners)
    return ("UNKNOWN",)


def _work_need_mergeable(current: list[PreliminaryComponent], following: PreliminaryComponent) -> bool:
    first = current[0]
    if WORK_NEED_BY_RULE_ACTION[(first.pd2_rule_code, first.component_action)] != WORK_NEED_BY_RULE_ACTION[(following.pd2_rule_code, following.component_action)]: return False
    if any(getattr(first, name) != getattr(following, name) for name in ("owner_signature", "control_signature", "safety_signature", "accountability_signature", "conflict_signature")): return False
    return _object_key(first) == _object_key(following) or any(dep in {item.component_id for item in current} for dep in following.dependency_component_ids)


def _object_key(component: PreliminaryComponent) -> str:
    return component.normalized_object or f"NO_OBJECT:{component.component_id}"


def _opportunity_mergeable(current: list[_Selection], following: _Selection) -> bool:
    first = current[0]
    if first.direction is not following.direction or first.code != following.code: return False
    a, b = current[-1].component, following.component
    if a.conflict_signature or b.conflict_signature: return False
    if any(getattr(a, name) != getattr(b, name) for name in ("owner_signature", "control_signature", "safety_signature", "accountability_signature")): return False
    dependency = any(dep in {item.component.component_id for item in current} for dep in b.dependency_component_ids)
    return (first.work_need_id == following.work_need_id or dependency) and (_object_key(a) == _object_key(b) or dependency or _canonical_dependency_artifact(a.normalized_output_artifact or "") == _canonical_dependency_artifact(b.normalized_input_artifact or ""))


def _canonical_dependency_artifact(value: str) -> str:
    explicit_recorded_form = re.fullmatch(
        r"RECORDED_FORM:(.+)", value, flags=re.IGNORECASE
    )
    if explicit_recorded_form:
        return f"RECORDED_FORM:{normalize_matching_text(explicit_recorded_form.group(1))}"
    value = normalize_matching_text(value)
    recorded = re.fullmatch(r"recorded\s+(.+)", value)
    return f"RECORDED_FORM:{recorded.group(1)}" if recorded else value


def _documented_text(step: ReviewedProcessStep) -> str:
    values: list[str] = []
    for _, assertion, _, _ in _all_assertions((step,)):
        if assertion.origin is InformationOrigin.DOCUMENT_SUPPORTED and assertion.disposition in {ReviewDisposition.ACCEPTED, ReviewDisposition.CORRECTED} and assertion.value is not None:
            values.append(str(assertion.value))
            values.extend(reference.exact_snippet for reference in assertion.evidence)
    return normalize_matching_text(" ".join(values), token_key=False)


def _documented_phrase(step: ReviewedProcessStep, phrases: tuple[str, ...]) -> bool:
    text = _documented_text(step)
    return any(normalize_matching_text(item, token_key=False) in text for item in phrases)


def _closed_deterministic(step: ReviewedProcessStep, component: PreliminaryComponent) -> bool:
    text = _documented_text(step)
    return (component.pd2_rule_code == "PD2-010" and ("closed deterministic mapping" in text or "fixed mapping" in text)) or (component.pd2_rule_code == "PD2-011" and ("exact deterministic lookup" in text or "exact lookup" in text))


def _conventional_sufficiency(component: PreliminaryComponent) -> bool:
    """Apply CS1-CS7 to the admitted component using only its exact traceable fields."""
    text = normalize_matching_text(_component_clause_text(component), token_key=False)
    full_text = normalize_matching_text(
        " ".join(span.exact_text for span in component.source_spans), token_key=False
    )
    # CS1: a concrete input/object/fixed condition is explicit.
    cs1 = bool(component.normalized_input_artifact or component.normalized_object)
    # CS2 and CS4: only the closed deterministic operation vocabulary is allowed.
    deterministic = {
        ComponentAction.RECORD,
        ComponentAction.UPDATE,
        ComponentAction.NOTIFY,
        ComponentAction.ROUTE,
        ComponentAction.ASSIGN,
        ComponentAction.SCHEDULE,
        ComponentAction.MONITOR,
        ComponentAction.FOLLOW_UP,
        ComponentAction.TRANSFORM,
        ComponentAction.CATEGORISE,
        ComponentAction.RETRIEVE,
    }
    cs2 = component.component_action in deterministic
    cs4 = component.pd2_rule_code not in SEMANTIC_RULES or component.pd2_rule_code in {
        "PD2-010",
        "PD2-011",
    }
    # CS3 and CS7: PD2 admission already checked required fields; retain an explicit
    # output/object check here so the conventional result has a complete work need.
    cs3 = bool(
        component.normalized_output_artifact
        or component.normalized_destination
        or component.normalized_recipient
        or component.normalized_object
    )
    cs7 = cs3
    # CS5: an explicit semantic-looking upstream reference must have resolved to a
    # prior component; fixed source records remain admissible without a dependency.
    linked_wording = bool(re.search(r"\b(using|based on|after|once)\b", text))
    cs5 = bool(component.dependency_component_ids) or not linked_wording
    # CS6: open-ended exceptions are never conventionally sufficient.
    cs6 = not re.search(
        r"\b(as appropriate|where necessary|exceptional circumstances|case by case|case-by-case)\b",
        text,
    )
    if component.pd2_rule_code == "PD2-006":
        fixed = bool(re.search(r"\b(when|if|every|daily|weekly|monthly|condition|threshold|status)\b", full_text))
        response = bool(re.search(r"\b(then|notify|notifies|route|routes|follow up|escalate|escalates|record|records)\b", full_text))
        cs2 = cs2 and fixed and response
    return all((cs1, cs2, cs3, cs4, cs5, cs6, cs7))


def _component_clause_text(component: PreliminaryComponent) -> str:
    parent = component.source_spans[0].exact_text
    match_start = component.matched_sub_spans[0].match_start_in_span
    for clause in segment_clauses(parent):
        if clause.start <= match_start < clause.end:
            return clause.text
    return parent


def _assistance_bundle(step: ReviewedProcessStep) -> bool:
    text = _documented_text(step)
    required = ("assistance scope defined", "mandatory human review", "human reviewer", "accountability owner", "escalation route", "assistance explicitly permitted", "safety resolved", "legal resolved", "privacy resolved", "regulatory resolved")
    risk = re.search(r"residual risk(?: with mandatory human review)?\s*[:=]?\s*[0-3]\b", text)
    consequence = re.search(r"assistance error consequence\s*[:=]?\s*[0-3]\b", text)
    return all(item in text for item in required) and bool(risk and consequence)


def _autonomy_bundle(step: ReviewedProcessStep) -> bool:
    text = _documented_text(step)
    required = ("required data available", "data suitable", "data quality acceptable", "no material human judgment", "no mandatory human decision", "no mandatory human review", "accountability owner", "escalation route", "autonomous operation explicitly permitted", "safety resolved", "legal resolved", "privacy resolved", "regulatory resolved")
    predictability = re.search(r"predictability\s*[:=]?\s*[45]\b", text)
    risk = re.search(r"autonomous residual risk\s*[:=]?\s*[0-2]\b", text)
    consequence = re.search(r"autonomous error consequence\s*[:=]?\s*[0-2]\b", text)
    return all(item in text for item in required) and bool(predictability and risk and consequence)


def _criterion_value(step: ReviewedProcessStep, name: CriterionName) -> int | None:
    for item in step.criteria:
        if item.name is name and item.assertion.origin is InformationOrigin.DOCUMENT_SUPPORTED and item.assertion.disposition in {ReviewDisposition.ACCEPTED, ReviewDisposition.CORRECTED} and isinstance(item.assertion.value, int):
            return item.assertion.value
    return None


def _affirmative_no_change(step: ReviewedProcessStep, sources: tuple[_AdmittedSource, ...]) -> bool:
    text = " ".join(item.span.exact_text for item in sources if item.classification is KnowledgeClassification.DOCUMENTED_FACT).casefold()
    required_groups = (
        ("current purpose is explicit", "purpose is"),
        ("purpose is being achieved", "purpose achieved"),
        ("performance is acceptable",),
        ("controls are acceptable",),
        ("no material process problem",),
        ("no intervention need", "no intervention is needed"),
    )
    return all(any(phrase in text for phrase in group) for group in required_groups)

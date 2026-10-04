"""Deterministic, version-aware presentation of persisted Preliminary results.

This module is deliberately disconnected from Streamlit.  It dispatches only
on the complete persisted compatibility identity and never on payload shape.
"""

from __future__ import annotations

from collections.abc import Iterable
import re

from pydantic import ValidationError

from ai_adoption_engine.models.preliminary_assessment import PreliminaryAssessment
from ai_adoption_engine.models.preliminary_assessment_v0_2 import (
    ActivityResultType,
    EvidenceRecord,
    KnowledgeClassification,
    PreliminaryAssessmentV2,
    PreliminaryActivityResultV2,
    RuleDerivedInference,
    SourceSpan,
)
from ai_adoption_engine.models.preliminary_persistence import (
    PRELIMINARY_EVALUATOR_ID,
    PRELIMINARY_EVALUATOR_VERSION,
    PRELIMINARY_EVALUATOR_V0_2_ID,
    PRELIMINARY_EVALUATOR_V0_2_VERSION,
    PRELIMINARY_RULE_SET_V0_1_FINGERPRINT,
    PRELIMINARY_RULE_SET_V0_1_ID,
    PRELIMINARY_RULE_SET_V0_1_VERSION,
    PRELIMINARY_RULE_SET_V0_2_FINGERPRINT,
    PRELIMINARY_RULE_SET_V0_2_ID,
    PRELIMINARY_RULE_SET_V0_2_VERSION,
    PersistedPreliminaryResult,
)
from ai_adoption_engine.models.preliminary_presentation import (
    PreliminaryCustomerPresentation,
    PreliminaryPresentationAudit,
    PreliminaryPresentationSourceIdentity,
    PreliminaryResultPresentation,
    PresentationActivity,
    PresentationAuditEntry,
    PresentationDiscoveryNeed,
    PresentationEvidenceItem,
    PresentationEvidenceSections,
    PresentationInference,
    PresentationOpenItem,
    PresentationOpportunity,
    PresentationSourceExcerpt,
)


PROVISIONAL_WARNING = (
    "Provisional exploration only. This Preliminary Assessment is not an "
    "organisational decision, formal outcome, gate result, Decision Package, or "
    "approval to implement. It does not satisfy formal evidence requirements."
)


class PreliminaryPresentationError(ValueError):
    """Base typed failure for unsafe or unsupported presentation input."""


class UnsupportedPreliminaryPresentationIdentity(PreliminaryPresentationError):
    """The persisted evaluator/rule/output identity is not supported."""


class CorruptPreliminaryPresentationRecord(PreliminaryPresentationError):
    """The stored result is internally mixed or corrupt."""


_V0_1_IDENTITY = (
    PRELIMINARY_EVALUATOR_ID,
    PRELIMINARY_EVALUATOR_VERSION,
    PRELIMINARY_RULE_SET_V0_1_ID,
    PRELIMINARY_RULE_SET_V0_1_VERSION,
    PRELIMINARY_RULE_SET_V0_1_FINGERPRINT,
    "preliminary-assessment.v0.1",
)
_V0_2_IDENTITY = (
    PRELIMINARY_EVALUATOR_V0_2_ID,
    PRELIMINARY_EVALUATOR_V0_2_VERSION,
    PRELIMINARY_RULE_SET_V0_2_ID,
    PRELIMINARY_RULE_SET_V0_2_VERSION,
    PRELIMINARY_RULE_SET_V0_2_FINGERPRINT,
    "preliminary-assessment.v0.2",
)

_DIRECTION_LABELS = {
    "LIKELY_NO_CHANGE": "No change indicated",
    "LIKELY_PROCESS_IMPROVEMENT_FIRST": "Improve the process first",
    "LIKELY_CONVENTIONAL_AUTOMATION": "Consider conventional automation",
    "LIKELY_HUMAN_LED": "Keep this work human-led",
    "POTENTIAL_AI_ASSISTED_WORK": "Potential AI assistance",
    "POTENTIAL_AI_AUTOMATION": "Potential AI automation",
    "INSUFFICIENT_BASIS_TO_SUGGEST_A_DIRECTION": "More evidence is needed.",
}
_DIRECTION_EXPLANATIONS = {
    "LIKELY_NO_CHANGE": "The documented basis indicates that no change is currently needed.",
    "LIKELY_PROCESS_IMPROVEMENT_FIRST": "The current process needs improvement before a technology direction is considered.",
    "LIKELY_CONVENTIONAL_AUTOMATION": "The documented work appears suitable for a conventional automation option.",
    "LIKELY_HUMAN_LED": "The documented work requires human responsibility or judgement to remain central.",
    "POTENTIAL_AI_ASSISTED_WORK": "The documented work may support bounded AI assistance with human oversight.",
    "POTENTIAL_AI_AUTOMATION": "The documented work may support an AI automation opportunity, subject to later validation and approval.",
    "INSUFFICIENT_BASIS_TO_SUGGEST_A_DIRECTION": "The documented basis is not sufficient to suggest a direction.",
}
_DISCOVERY_EXPLANATIONS = {
    "NO_DIRECTION_BEARING_EVIDENCE": "The documented source does not yet establish work characteristics that support a provisional direction.",
    "MATERIAL_EVIDENCE_CONFLICT": "Material source evidence conflicts and must be resolved before a provisional direction can be shown.",
    "INSEPARABLE_SCOPE": "The activity scope cannot yet be separated into independently assessable work.",
    "UNSUPPORTED_CHARACTERISTIC": "Part of the activity is not described precisely enough to assess.",
    "MISSING_REQUIRED_COMPONENT_FIELD": "Required risk or governance information is not yet documented.",
    "UNRESOLVED_HIGH_RISK": "A material risk remains unresolved and requires evidence.",
    "OPPORTUNITY_PARTITION_EXCEEDS_LIMIT": "The activity contains too many independent opportunities and should be split or clarified.",
}
_EVIDENCE_REQUESTS = {
    "RESOLVE_CONFLICT": "Resolve the conflicting source evidence.",
    "CLARIFY_CURRENT_ACTIVITY": "Clarify what the activity currently does.",
    "CLARIFY_OUTPUT": "Document the output produced by the activity.",
    "CLARIFY_INPUT": "Document the input used by the activity.",
    "RESOLVE_RISK_AND_GOVERNANCE": "Document the required risk and governance controls.",
    "SPLIT_OR_CLARIFY_ACTIVITY_SCOPE": "Split the activity into independently assessable work or clarify its scope.",
}
_CHARACTERISTIC_LABELS = {
    "component_action": "Action",
    "normalized_actor": "Actor",
    "normalized_destination": "Destination",
    "normalized_input_artifact": "Input",
    "normalized_object": "Object",
    "normalized_output_artifact": "Output",
    "normalized_recipient": "Recipient",
}


def _identity(result: PersistedPreliminaryResult) -> tuple[str, ...]:
    return (
        result.evaluator.evaluator_id,
        result.evaluator.evaluator_version,
        result.rule_set.rule_set_id,
        result.rule_set.rule_set_version,
        result.rule_set.rule_set_fingerprint,
        result.output_schema_version,
    )


def _source_identity(result: PersistedPreliminaryResult) -> PreliminaryPresentationSourceIdentity:
    return PreliminaryPresentationSourceIdentity(
        persisted_result_schema_version=result.schema_version,
        output_schema_version=result.output_schema_version,
        preliminary_result_id=result.preliminary_result_id,
        preliminary_run_id=result.preliminary_run_id,
        journey_id=result.journey_id,
        completed_run_event_id=result.completed_run_event_id,
        result_created_at=result.created_at,
        evaluator_id=result.evaluator.evaluator_id,
        evaluator_version=result.evaluator.evaluator_version,
        rule_set_id=result.rule_set.rule_set_id,
        rule_set_version=result.rule_set.rule_set_version,
        rule_set_status=result.rule_set.rule_set_status,
        rule_set_fingerprint=result.rule_set.rule_set_fingerprint,
        source_assessment_id=result.source.source_assessment_id,
        approved_review_artifact_id=result.source.approved_review_artifact_id,
        approved_review_schema_version=result.source.approved_review_schema_version,
        approved_review_payload_sha256=result.source.approved_review_payload_sha256,
        source_document_id=result.source.source_document_id,
        extraction_run_id=result.source.extraction_run_id,
        review_id=result.source.review_id,
        approval_event_id=result.source.approval_event_id,
        approved_at=result.source.approved_at,
        validated_process_id=result.source.validated_process_id,
        validated_process_fingerprint=result.source.validated_process_fingerprint,
    )


def _coverage(value: object) -> str:
    raw = str(getattr(value, "value", value))
    return f"{raw.title()} evidence coverage"


def _customer_text(value: str) -> str:
    """Remove stored field notation without changing the underlying statement."""

    return re.sub(
        r"\b[a-z]+(?:[._][a-z_]+)+\b",
        lambda match: match.group(0).replace(".", " ").replace("_", " "),
        value,
    )


def _span(span: SourceSpan) -> PresentationSourceExcerpt:
    return PresentationSourceExcerpt(
        exact_excerpt=span.exact_text,
        source_locator=span.source_locator,
    )


def _spans(spans: Iterable[SourceSpan]) -> tuple[PresentationSourceExcerpt, ...]:
    return tuple(_span(item) for item in spans)


def _record(item: EvidenceRecord) -> PresentationEvidenceItem:
    return PresentationEvidenceItem(
        statement=item.statement,
        source_excerpts=_spans(item.source_spans),
    )


def _reviewed(item: EvidenceRecord) -> PresentationInference:
    return PresentationInference(
        statement=item.statement,
        explanation="This inference was reviewed by a person and retains its documented source lineage.",
        source_excerpts=_spans(item.source_spans),
    )


def _engine(item: RuleDerivedInference) -> PresentationInference:
    details = tuple(
        f"{_CHARACTERISTIC_LABELS[key]}: {str(value).replace('_', ' ').lower()}"
        for key, value in item.normalized_derived_characteristic.items()
        if value is not None and key in _CHARACTERISTIC_LABELS
    )
    statement = "Detected work characteristic"
    if details:
        statement += ": " + "; ".join(details) + "."
    return PresentationInference(
        statement=statement,
        explanation="This characteristic was derived by the deterministic assessment engine from the cited source.",
        source_excerpts=_spans(item.source_spans),
    )


def _open(item: EvidenceRecord, *, conflict: bool) -> PresentationOpenItem:
    explanation = (
        "Conflicting evidence is shown without choosing one account as true."
        if conflict
        else "Unknown means not established; it does not mean zero, false, low, or not applicable."
    )
    return PresentationOpenItem(
        statement=item.statement,
        explanation=explanation,
        source_excerpts=_spans(item.source_spans),
    )


def _request(code: str) -> str:
    try:
        return _EVIDENCE_REQUESTS[code]
    except KeyError as exc:
        raise CorruptPreliminaryPresentationRecord(
            f"Unsupported v0.2 evidence request code: {code}"
        ) from exc


def _v2_sections(
    activity: PreliminaryActivityResultV2,
    *,
    evidence_ids: tuple[str, ...] | None = None,
    inference_ids: tuple[str, ...] | None = None,
    unknown_ids: tuple[str, ...] | None = None,
    conflict_ids: tuple[str, ...] | None = None,
    next_evidence: tuple[str, ...] | None = None,
) -> PresentationEvidenceSections:
    evidence = set(evidence_ids) if evidence_ids is not None else None
    inferences = set(inference_ids) if inference_ids is not None else None
    unknowns = set(unknown_ids) if unknown_ids is not None else None
    conflicts = set(conflict_ids) if conflict_ids is not None else None
    known_evidence_ids = {
        item.item_id
        for item in (*activity.documented_facts, *activity.reviewed_inferences)
    }
    known_inference_ids = {
        item.inference_id for item in activity.rule_derived_inferences
    }
    known_unknown_ids = {item.item_id for item in activity.unknowns}
    known_conflict_ids = {item.item_id for item in activity.conflicts}
    if evidence is not None and not evidence <= known_evidence_ids:
        raise CorruptPreliminaryPresentationRecord(
            "A v0.2 presentation evidence reference cannot be resolved"
        )
    if inferences is not None and not inferences <= known_inference_ids:
        raise CorruptPreliminaryPresentationRecord(
            "A v0.2 presentation inference reference cannot be resolved"
        )
    unresolved_unknowns = (unknowns or set()) - known_unknown_ids
    if any(not item.startswith("unknown:governance:") for item in unresolved_unknowns):
        raise CorruptPreliminaryPresentationRecord(
            "A v0.2 presentation unknown reference cannot be resolved"
        )
    if conflicts is not None and not conflicts <= known_conflict_ids:
        raise CorruptPreliminaryPresentationRecord(
            "A v0.2 presentation conflict reference cannot be resolved"
        )
    return PresentationEvidenceSections(
        documented_source=tuple(
            _record(item)
            for item in activity.documented_facts
            if evidence is None or item.item_id in evidence
        ),
        reviewed_inference=tuple(
            _reviewed(item)
            for item in activity.reviewed_inferences
            if evidence is None or item.item_id in evidence
        ),
        engine_inference=tuple(
            _engine(item)
            for item in activity.rule_derived_inferences
            if inferences is None or item.inference_id in inferences
        ),
        unknown=tuple(
            _open(item, conflict=False)
            for item in activity.unknowns
            if unknowns is None or item.item_id in unknowns
        )
        + tuple(
            PresentationOpenItem(
                statement="Required risk and governance information is not yet documented.",
                explanation="Unknown means not established; it does not mean zero, false, low, or not applicable.",
            )
            for _ in sorted(unresolved_unknowns)
        ),
        conflict=tuple(
            _open(item, conflict=True)
            for item in activity.conflicts
            if conflicts is None or item.item_id in conflicts
        ),
        next_evidence=tuple(_request(code) for code in (next_evidence or ())),
    )


def _validate_v2_activity_integrity(
    assessment: PreliminaryAssessmentV2,
    activity: PreliminaryActivityResultV2,
) -> None:
    if (
        activity.evaluator_id != assessment.evaluator_id
        or activity.evaluator_version != assessment.evaluator_version
        or activity.rule_set_id != assessment.rule_set_id
        or activity.rule_set_version != assessment.rule_set_version
        or activity.rule_set_fingerprint != assessment.rule_set_fingerprint
        or activity.output_schema_id != assessment.schema_version
    ):
        raise CorruptPreliminaryPresentationRecord(
            "A v0.2 activity has a mixed compatibility identity"
        )
    classified = (
        (activity.documented_facts, KnowledgeClassification.DOCUMENTED_FACT),
        (activity.reviewed_inferences, KnowledgeClassification.REVIEWED_INFERENCE),
        (activity.unknowns, KnowledgeClassification.UNKNOWN),
        (activity.conflicts, KnowledgeClassification.CONFLICT),
    )
    evidence_ids: list[str] = []
    for items, expected in classified:
        if any(item.classification is not expected for item in items):
            raise CorruptPreliminaryPresentationRecord(
                "A v0.2 evidence record is stored in the wrong presentation section"
            )
        evidence_ids.extend(item.item_id for item in items)
    if len(evidence_ids) != len(set(evidence_ids)):
        raise CorruptPreliminaryPresentationRecord(
            "A v0.2 activity contains duplicate evidence identities"
        )
    all_spans = (
        span
        for group in (
            activity.documented_facts,
            activity.reviewed_inferences,
            activity.unknowns,
            activity.conflicts,
            activity.rule_derived_inferences,
        )
        for item in group
        for span in item.source_spans
    )
    if any(span.source_document_id != activity.source_document_id for span in all_spans):
        raise CorruptPreliminaryPresentationRecord(
            "A v0.2 evidence span has mixed source lineage"
        )
    if any(item.activity_identity != activity.activity_identity for item in activity.opportunities):
        raise CorruptPreliminaryPresentationRecord(
            "A v0.2 opportunity has mixed activity identity"
        )
    if any(item.activity_identity != activity.activity_identity for item in activity.scoped_discoveries):
        raise CorruptPreliminaryPresentationRecord(
            "A v0.2 discovery has mixed activity identity"
        )


def _v0_1(result: PersistedPreliminaryResult) -> PreliminaryResultPresentation:
    assessment = result.assessment
    if not isinstance(assessment, PreliminaryAssessment):
        raise CorruptPreliminaryPresentationRecord(
            "The v0.1 identity does not contain a v0.1 assessment"
        )
    if assessment.schema_version != result.output_schema_version:
        raise CorruptPreliminaryPresentationRecord("The v0.1 output identity is mixed")
    if assessment.rule_set.model_dump() != result.rule_set.model_dump():
        raise CorruptPreliminaryPresentationRecord("The v0.1 rule identity has drifted")

    activities: list[PresentationActivity] = []
    audit_entries: list[PresentationAuditEntry] = []
    for activity in assessment.activity_results:
        facts = {item.fact_id: item for item in activity.documented_facts}
        sections = PresentationEvidenceSections(
            documented_source=tuple(
                PresentationEvidenceItem(
                    statement=_customer_text(item.statement),
                    source_excerpts=(
                        PresentationSourceExcerpt(
                            exact_excerpt=item.exact_excerpt,
                            source_locator=item.source_locator,
                        ),
                    ),
                )
                for item in activity.documented_facts
            ),
            reviewed_inference=tuple(
                PresentationInference(
                    statement=_customer_text(item.statement),
                    explanation=_customer_text(item.rationale),
                    source_excerpts=tuple(
                        PresentationSourceExcerpt(
                            exact_excerpt=facts[fact_id].exact_excerpt,
                            source_locator=facts[fact_id].source_locator,
                        )
                        for fact_id in item.derived_from_fact_ids
                    ),
                )
                for item in activity.reasonable_inferences
            ),
            unknown=tuple(
                PresentationOpenItem(
                    statement=_customer_text(item.unresolved_question),
                    explanation=(
                        "Unknown means not established; it does not mean zero, false, low, or not applicable."
                        + (
                            f" Evidence needed: {_customer_text(item.evidence_needed)}."
                            if item.evidence_needed
                            else ""
                        )
                        + (
                            f" Owner needed: {_customer_text(item.owner_needed)}."
                            if item.owner_needed
                            else ""
                        )
                    ),
                )
                for item in activity.unknowns
            ),
            next_evidence=tuple(
                (
                    _customer_text(item.description)
                    if item.suggested_owner is None
                    else (
                        f"{_customer_text(item.description)} Suggested owner: "
                        f"{_customer_text(item.suggested_owner)}."
                    )
                )
                for item in activity.next_evidence_to_collect
            ),
        )
        activities.append(
            PresentationActivity(
                heading=activity.activity,
                state="Provisional direction identified",
                provisional_direction=activity.provisional_direction.value,
                evidence_coverage=_coverage(activity.confidence.level),
                explanation=_customer_text(activity.rationale),
                evidence=sections,
            )
        )
        audit_entries.append(
            PresentationAuditEntry(
                entry_type="activity",
                identifier=activity.step_id,
                codes=(activity.deciding_rule_code.value,),
                referenced_identifiers=tuple(facts),
                decision_trace_json=tuple(
                    item.model_dump_json() for item in activity.decision_input_trace
                ),
            )
        )
    return PreliminaryResultPresentation(
        customer=PreliminaryCustomerPresentation(
            provisional_warning=PROVISIONAL_WARNING,
            process_name=assessment.process_name,
            overall_evidence_coverage=_coverage(assessment.confidence.level),
            activities=tuple(activities),
        ),
        audit=PreliminaryPresentationAudit(
            source_identity=_source_identity(result),
            entries=tuple(audit_entries),
        ),
    )


def _direction(value: object) -> tuple[str, str]:
    code = str(getattr(value, "value", value))
    try:
        return _DIRECTION_LABELS[code], _DIRECTION_EXPLANATIONS[code]
    except KeyError as exc:
        raise CorruptPreliminaryPresentationRecord(
            f"Unsupported v0.2 provisional direction: {code}"
        ) from exc


def _v0_2(result: PersistedPreliminaryResult) -> PreliminaryResultPresentation:
    assessment = result.assessment
    if not isinstance(assessment, PreliminaryAssessmentV2):
        raise CorruptPreliminaryPresentationRecord(
            "The v0.2 identity does not contain a v0.2 assessment"
        )
    if (
        assessment.schema_version != result.output_schema_version
        or assessment.evaluator_id != result.evaluator.evaluator_id
        or assessment.evaluator_version != result.evaluator.evaluator_version
        or assessment.rule_set_id != result.rule_set.rule_set_id
        or assessment.rule_set_version != result.rule_set.rule_set_version
        or assessment.rule_set_fingerprint != result.rule_set.rule_set_fingerprint
    ):
        raise CorruptPreliminaryPresentationRecord(
            "The v0.2 assessment identity is mixed or has drifted"
        )

    activities: list[PresentationActivity] = []
    audit_entries: list[PresentationAuditEntry] = []
    for activity_number, activity in enumerate(assessment.activity_results, start=1):
        _validate_v2_activity_integrity(assessment, activity)
        opportunities: list[PresentationOpportunity] = []
        for opportunity_number, opportunity in enumerate(activity.opportunities, start=1):
            label, explanation = _direction(opportunity.direction)
            related_requests = tuple(
                code
                for discovery in activity.scoped_discoveries
                if set(discovery.related_component_ids) & set(opportunity.component_ids)
                for code in discovery.evidence_request_codes
            )
            opportunities.append(
                PresentationOpportunity(
                    heading=f"Opportunity {opportunity_number}",
                    provisional_direction=label,
                    evidence_coverage=_coverage(opportunity.evidence_coverage),
                    explanation=explanation,
                    evidence=_v2_sections(
                        activity,
                        evidence_ids=opportunity.material_evidence_item_ids,
                        inference_ids=opportunity.material_inference_ids,
                        unknown_ids=opportunity.material_unknown_ids,
                        conflict_ids=opportunity.conflict_ids,
                        next_evidence=tuple(dict.fromkeys(related_requests)),
                    ),
                )
            )
            audit_entries.append(
                PresentationAuditEntry(
                    entry_type="opportunity",
                    identifier=opportunity.opportunity_id,
                    codes=(opportunity.deciding_rule_code, opportunity.construction_code),
                    referenced_identifiers=(
                        *opportunity.component_ids,
                        *opportunity.work_need_ids,
                        *opportunity.material_evidence_item_ids,
                        *opportunity.material_inference_ids,
                        *opportunity.material_unknown_ids,
                        *opportunity.conflict_ids,
                    ),
                    decision_trace_json=tuple(
                        item.model_dump_json()
                        for item in opportunity.decision_input_trace
                    ),
                )
            )

        discoveries: list[PresentationDiscoveryNeed] = []
        for discovery_number, discovery in enumerate(activity.scoped_discoveries, start=1):
            try:
                explanation = _DISCOVERY_EXPLANATIONS[discovery.discovery_reason_code]
            except KeyError as exc:
                raise CorruptPreliminaryPresentationRecord(
                    f"Unsupported v0.2 discovery reason: {discovery.discovery_reason_code}"
                ) from exc
            discovery_sections = _v2_sections(
                activity,
                evidence_ids=discovery.material_evidence_item_ids,
                unknown_ids=discovery.unknown_ids,
                conflict_ids=discovery.conflict_ids,
                next_evidence=discovery.evidence_request_codes,
            )
            if discovery.source_spans and not (
                discovery_sections.documented_source
                or discovery_sections.reviewed_inference
            ):
                discovery_sections = discovery_sections.model_copy(
                    update={
                        "documented_source": (
                            PresentationEvidenceItem(
                                statement="Source text requiring clarification.",
                                source_excerpts=_spans(discovery.source_spans),
                            ),
                        )
                    }
                )
            discoveries.append(
                PresentationDiscoveryNeed(
                    heading=f"Evidence need {discovery_number}",
                    explanation=explanation,
                    evidence_coverage=_coverage(discovery.evidence_coverage),
                    evidence=discovery_sections,
                )
            )
            audit_entries.append(
                PresentationAuditEntry(
                    entry_type="discovery",
                    identifier=discovery.scoped_discovery_id,
                    codes=(discovery.discovery_reason_code, *discovery.evidence_request_codes),
                    referenced_identifiers=(
                        *discovery.related_component_ids,
                        *discovery.related_work_need_ids,
                        *discovery.material_evidence_item_ids,
                        *discovery.unknown_ids,
                        *discovery.conflict_ids,
                    ),
                    decision_trace_json=tuple(
                        item.model_dump_json()
                        for item in discovery.decision_input_trace
                    ),
                )
            )

        if activity.result_type is ActivityResultType.ACTIONABLE:
            state = "Provisional opportunities identified"
            explanation = (
                f"The documented activity contains {len(opportunities)} independently assessed provisional "
                f"opportunit{'y' if len(opportunities) == 1 else 'ies'}."
            )
            direction = None
        elif activity.result_type is ActivityResultType.DISCOVERY_REQUIRED:
            state = "More evidence is needed"
            explanation = "The documented basis is not sufficient to show an actionable provisional direction."
            direction = "More evidence is needed"
        elif activity.result_type is ActivityResultType.NO_CHANGE:
            state = "No change indicated"
            explanation = "The documented basis affirmatively indicates that no intervention is currently needed."
            direction = "No change indicated"
        else:
            raise CorruptPreliminaryPresentationRecord(
                f"Unsupported v0.2 activity result type: {activity.result_type}"
            )

        activities.append(
            PresentationActivity(
                heading=f"Activity {activity_number}",
                state=state,
                provisional_direction=direction,
                evidence_coverage=_coverage(activity.evidence_coverage),
                explanation=explanation,
                evidence=_v2_sections(
                    activity,
                    next_evidence=activity.next_evidence_to_collect,
                ),
                opportunities=tuple(opportunities),
                discovery_needs=tuple(discoveries),
            )
        )
        audit_entries.append(
            PresentationAuditEntry(
                entry_type="activity",
                identifier=activity.activity_identity,
                codes=tuple(
                    code
                    for code in (activity.construction_code, activity.deciding_rule_code)
                    if code is not None
                ),
                referenced_identifiers=tuple(
                    item.item_id
                    for group in (
                        activity.documented_facts,
                        activity.reviewed_inferences,
                        activity.unknowns,
                        activity.conflicts,
                    )
                    for item in group
                ),
                decision_trace_json=tuple(
                    item.model_dump_json() for item in activity.decision_input_trace
                ),
            )
        )
        audit_entries.extend(
            PresentationAuditEntry(
                entry_type="rule-derived inference",
                identifier=item.inference_id,
                codes=(item.pd2_rule_code, item.matched_literal_code),
                referenced_identifiers=(
                    *item.source_fact_ids,
                    *item.source_reviewed_inference_ids,
                ),
            )
            for item in activity.rule_derived_inferences
        )

    return PreliminaryResultPresentation(
        customer=PreliminaryCustomerPresentation(
            provisional_warning=PROVISIONAL_WARNING,
            process_name=assessment.process_name,
            overall_evidence_coverage=_coverage(assessment.evidence_coverage),
            activities=tuple(activities),
        ),
        audit=PreliminaryPresentationAudit(
            source_identity=_source_identity(result),
            entries=tuple(audit_entries),
        ),
    )


def present_preliminary_result(
    result: PersistedPreliminaryResult,
    *,
    include_audit: bool = False,
) -> PreliminaryResultPresentation:
    """Build the frozen presentation for one exact persisted compatibility identity."""

    if not isinstance(result, PersistedPreliminaryResult):
        raise CorruptPreliminaryPresentationRecord(
            "Presentation requires a persisted Preliminary result"
        )
    identity = _identity(result)
    if identity not in {_V0_1_IDENTITY, _V0_2_IDENTITY}:
        raise UnsupportedPreliminaryPresentationIdentity(
            "Unsupported or mixed Preliminary presentation compatibility identity"
        )
    try:
        result = PersistedPreliminaryResult.model_validate(
            result.model_dump(mode="python")
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise CorruptPreliminaryPresentationRecord(
            "The persisted Preliminary result failed integrity validation"
        ) from exc
    if identity == _V0_1_IDENTITY:
        presentation = _v0_1(result)
    elif identity == _V0_2_IDENTITY:
        presentation = _v0_2(result)
    else:
        raise AssertionError("Closed compatibility dispatch became unreachable")
    if include_audit:
        return presentation
    return presentation.model_copy(update={"audit": None})


def render_preliminary_customer_text(
    presentation: PreliminaryResultPresentation,
) -> str:
    """Render deterministic nontechnical text without audit identifiers or codes."""

    lines = [
        presentation.customer.title,
        presentation.customer.provisional_warning,
        f"Process: {presentation.customer.process_name}",
        f"Overall: {presentation.customer.overall_evidence_coverage}",
        presentation.customer.overall_direction_statement,
        presentation.customer.evidence_coverage_explanation,
    ]
    for activity in presentation.customer.activities:
        lines.extend((activity.heading, activity.state, activity.evidence_coverage, activity.explanation))
        if activity.provisional_direction:
            lines.append(activity.provisional_direction)
        for opportunity in activity.opportunities:
            lines.extend(
                (
                    opportunity.heading,
                    opportunity.provisional_direction,
                    opportunity.evidence_coverage,
                    opportunity.explanation,
                )
            )
            _append_sections(lines, opportunity.evidence)
        for discovery in activity.discovery_needs:
            lines.extend((discovery.heading, discovery.evidence_coverage, discovery.explanation))
            _append_sections(lines, discovery.evidence)
        _append_sections(lines, activity.evidence)
    return "\n".join(lines)


def _append_sections(lines: list[str], sections: PresentationEvidenceSections) -> None:
    groups = (
        ("Documented source", sections.documented_source),
        ("Reviewed inference", sections.reviewed_inference),
        ("Engine inference", sections.engine_inference),
        ("Unknown", sections.unknown),
        ("Conflict", sections.conflict),
    )
    for heading, items in groups:
        lines.append(heading)
        for item in items:
            lines.append(f"- {item.statement}")
            explanation = getattr(item, "explanation", None)
            if explanation:
                lines.append(explanation)
            for excerpt in item.source_excerpts:
                lines.extend((f"Source: {excerpt.source_locator}", f'Excerpt: "{excerpt.exact_excerpt}"'))
    lines.append("Next evidence")
    lines.extend(f"- {item}" for item in sections.next_evidence)

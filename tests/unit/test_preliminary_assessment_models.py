from datetime import UTC, datetime
import inspect

import pytest
from pydantic import TypeAdapter, ValidationError

import ai_adoption_engine.models.preliminary_assessment as preliminary_models
from ai_adoption_engine.models.preliminary_assessment import (
    PRELIMINARY_ASSESSMENT_DISCLAIMER,
    AssessmentJourney,
    DocumentedFact,
    EvidenceCoverageConfidence,
    JourneySelection,
    NextEvidenceToCollect,
    PreliminaryActivityResult,
    PreliminaryAssessment,
    PreliminaryAssessmentLineage,
    PreliminaryConfidence,
    PreliminaryComparisonClause,
    PreliminaryComparisonOperator,
    PreliminaryDecidingRuleCode,
    PreliminaryDecisionInputTrace,
    PreliminaryEvaluationStage,
    PreliminaryEvidence,
    PreliminaryEvidenceClassification,
    PreliminaryInputName,
    PreliminaryRuleComparison,
    PreliminaryUnknown,
    PreliminaryValueType,
    ProvisionalDirection,
    RULE_DIRECTION_BY_CODE,
    RULE_MATERIAL_MANIFESTS,
    ReasonableInference,
)
from ai_adoption_engine.preliminary.rules import PRELIMINARY_EVALUATOR_RULES_V0_1


FIXED_TIME = datetime(2026, 9, 26, 9, 0, tzinfo=UTC)
DOCUMENT_ID = f"doc-{'a' * 64}"
OTHER_DOCUMENT_ID = f"doc-{'c' * 64}"
PROCESS_FINGERPRINT = "b" * 64


def _confidence(
    level: PreliminaryConfidence = PreliminaryConfidence.LOW,
) -> EvidenceCoverageConfidence:
    return EvidenceCoverageConfidence(
        level=level,
        basis="Coverage reflects the documentary evidence available for this result.",
    )


def _fact(**updates) -> DocumentedFact:
    payload = {
        "fact_id": "fact-1",
        "statement": "The agent records each complaint.",
        "source_document_id": DOCUMENT_ID,
        "exact_excerpt": "Agent records the complaint.",
        "source_locator": "paragraph 2",
    }
    payload.update(updates)
    return DocumentedFact(**payload)


def _inference(**updates) -> ReasonableInference:
    payload = {
        "inference_id": "inference-1",
        "statement": "Complaint capture is likely repetitive.",
        "derived_from_fact_ids": ("fact-1",),
        "rationale": "The documented action occurs for each complaint.",
        "confidence": _confidence(),
    }
    payload.update(updates)
    return ReasonableInference(**payload)


def _unknown(**updates) -> PreliminaryUnknown:
    payload = {
        "unknown_id": "unknown-1",
        "unresolved_question": "How many complaints arrive each week?",
        "evidence_needed": "A recent complaint-volume report.",
    }
    payload.update(updates)
    return PreliminaryUnknown(**payload)


_DECIDING_INPUT = {
    PreliminaryDecidingRuleCode.INSUFFICIENT_ACTIVITY_IDENTITY: PreliminaryInputName.ACTIVITY_IDENTITY,
    PreliminaryDecidingRuleCode.INSUFFICIENT_CHANGE_CASE: PreliminaryInputName.BUSINESS_VALUE,
    PreliminaryDecidingRuleCode.LIKELY_NO_CHANGE: PreliminaryInputName.BUSINESS_VALUE,
    PreliminaryDecidingRuleCode.LIKELY_PROCESS_IMPROVEMENT_FIRST: PreliminaryInputName.DATA_READINESS,
    PreliminaryDecidingRuleCode.INSUFFICIENT_READINESS: PreliminaryInputName.DATA_READINESS,
    PreliminaryDecidingRuleCode.INSUFFICIENT_CONVENTIONAL_FIT: PreliminaryInputName.CONVENTIONAL_SOLUTION_FIT,
    PreliminaryDecidingRuleCode.LIKELY_CONVENTIONAL_AUTOMATION: PreliminaryInputName.CONVENTIONAL_SOLUTION_FIT,
    PreliminaryDecidingRuleCode.INSUFFICIENT_AI_FIT: PreliminaryInputName.AI_CAPABILITY_FIT,
    PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_LOW_AI_FIT: PreliminaryInputName.AI_CAPABILITY_FIT,
    PreliminaryDecidingRuleCode.INSUFFICIENT_AI_CAPABILITY: PreliminaryInputName.CAPABILITY_READS_UNSTRUCTURED_DOCUMENTS,
    PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_NO_CAPABILITY: PreliminaryInputName.CAPABILITY_READS_UNSTRUCTURED_DOCUMENTS,
    PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_SAFETY_VETO: PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT,
    PreliminaryDecidingRuleCode.INSUFFICIENT_RESIDUAL_RISK: PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT,
    PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_CONSTRAINT: PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT,
    PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_AUTONOMY_UNKNOWN: PreliminaryInputName.HUMAN_JUDGEMENT_REQUIREMENT,
    PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION: PreliminaryInputName.PREDICTABILITY,
}


_DECIDING_COMPARISON = {
    PreliminaryDecidingRuleCode.INSUFFICIENT_ACTIVITY_IDENTITY: (PreliminaryComparisonClause.ACTIVITY_UNRESOLVED, PreliminaryComparisonOperator.IS_UNKNOWN, None),
    PreliminaryDecidingRuleCode.INSUFFICIENT_CHANGE_CASE: (PreliminaryComparisonClause.BUSINESS_UNRESOLVED, PreliminaryComparisonOperator.IS_UNKNOWN, None),
    PreliminaryDecidingRuleCode.LIKELY_NO_CHANGE: (PreliminaryComparisonClause.BUSINESS_LT_MINIMUM, PreliminaryComparisonOperator.LT, 2),
    PreliminaryDecidingRuleCode.LIKELY_PROCESS_IMPROVEMENT_FIRST: (PreliminaryComparisonClause.DATA_LT_MINIMUM, PreliminaryComparisonOperator.LT, 2),
    PreliminaryDecidingRuleCode.INSUFFICIENT_READINESS: (PreliminaryComparisonClause.DATA_UNRESOLVED, PreliminaryComparisonOperator.IS_UNKNOWN, None),
    PreliminaryDecidingRuleCode.INSUFFICIENT_CONVENTIONAL_FIT: (PreliminaryComparisonClause.CONVENTIONAL_UNRESOLVED, PreliminaryComparisonOperator.IS_UNKNOWN, None),
    PreliminaryDecidingRuleCode.LIKELY_CONVENTIONAL_AUTOMATION: (PreliminaryComparisonClause.CONVENTIONAL_GTE_CUTOFF, PreliminaryComparisonOperator.GTE, 4),
    PreliminaryDecidingRuleCode.INSUFFICIENT_AI_FIT: (PreliminaryComparisonClause.AI_FIT_UNRESOLVED, PreliminaryComparisonOperator.IS_UNKNOWN, None),
    PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_LOW_AI_FIT: (PreliminaryComparisonClause.AI_FIT_LT_MINIMUM, PreliminaryComparisonOperator.LT, 3),
    PreliminaryDecidingRuleCode.INSUFFICIENT_AI_CAPABILITY: (PreliminaryComparisonClause.CAPABILITY_UNRESOLVED, PreliminaryComparisonOperator.IS_UNKNOWN, None),
    PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_NO_CAPABILITY: (PreliminaryComparisonClause.CAPABILITY_FALSE, PreliminaryComparisonOperator.IS_FALSE, None),
    PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_SAFETY_VETO: (PreliminaryComparisonClause.RESIDUAL_GTE_VETO, PreliminaryComparisonOperator.GTE, 4),
    PreliminaryDecidingRuleCode.INSUFFICIENT_RESIDUAL_RISK: (PreliminaryComparisonClause.RESIDUAL_UNRESOLVED, PreliminaryComparisonOperator.IS_UNKNOWN, None),
    PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_CONSTRAINT: (PreliminaryComparisonClause.RESIDUAL_EQ_ASSISTANCE, PreliminaryComparisonOperator.EQ, 3),
    PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_AUTONOMY_UNKNOWN: (PreliminaryComparisonClause.JUDGEMENT_UNRESOLVED, PreliminaryComparisonOperator.IS_UNKNOWN, None),
    PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION: (PreliminaryComparisonClause.PREDICTABILITY_GTE_AUTOMATION, PreliminaryComparisonOperator.GTE, 4),
}


def _value_type(name: PreliminaryInputName) -> PreliminaryValueType:
    if name is PreliminaryInputName.ACTIVITY_IDENTITY:
        return PreliminaryValueType.TEXT
    if name.value.startswith("capability.") or name is PreliminaryInputName.HUMAN_ACCOUNTABILITY_REQUIRED:
        return PreliminaryValueType.BOOLEAN
    return PreliminaryValueType.ORDINAL


def _resolved_comparison(name: PreliminaryInputName):
    return {
        PreliminaryInputName.ACTIVITY_IDENTITY: ("Record complaint", PreliminaryComparisonClause.ACTIVITY_PRESENT, PreliminaryComparisonOperator.PRESENT, None),
        PreliminaryInputName.BUSINESS_VALUE: (3, PreliminaryComparisonClause.BUSINESS_GTE_MINIMUM, PreliminaryComparisonOperator.GTE, 2),
        PreliminaryInputName.DATA_READINESS: (4, PreliminaryComparisonClause.DATA_GTE_AUTOMATION, PreliminaryComparisonOperator.GTE, 4),
        PreliminaryInputName.IMPLEMENTATION_COMPLEXITY: (2, PreliminaryComparisonClause.COMPLEXITY_LTE_AUTOMATION_MAX, PreliminaryComparisonOperator.LTE, 3),
        PreliminaryInputName.CONVENTIONAL_SOLUTION_FIT: (1, PreliminaryComparisonClause.CONVENTIONAL_LT_CUTOFF, PreliminaryComparisonOperator.LT, 4),
        PreliminaryInputName.AI_CAPABILITY_FIT: (4, PreliminaryComparisonClause.AI_FIT_GTE_MINIMUM, PreliminaryComparisonOperator.GTE, 3),
        PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT: (2, PreliminaryComparisonClause.RESIDUAL_LTE_AUTOMATION_MAX, PreliminaryComparisonOperator.LTE, 2),
        PreliminaryInputName.HUMAN_JUDGEMENT_REQUIREMENT: (2, PreliminaryComparisonClause.JUDGEMENT_LT_ASSISTANCE, PreliminaryComparisonOperator.LTE, 2),
        PreliminaryInputName.RISK_CONSEQUENCE: (2, PreliminaryComparisonClause.CONSEQUENCE_LT_ASSISTANCE, PreliminaryComparisonOperator.LTE, 2),
        PreliminaryInputName.HUMAN_ACCOUNTABILITY_REQUIRED: (False, PreliminaryComparisonClause.ACCOUNTABILITY_FALSE, PreliminaryComparisonOperator.IS_FALSE, None),
        PreliminaryInputName.PREDICTABILITY: (4, PreliminaryComparisonClause.PREDICTABILITY_GTE_AUTOMATION, PreliminaryComparisonOperator.GTE, 4),
    }.get(name, (True, PreliminaryComparisonClause.CAPABILITY_TRUE, PreliminaryComparisonOperator.IS_TRUE, None))


def _trace_for(code: PreliminaryDecidingRuleCode) -> tuple[PreliminaryDecisionInputTrace, ...]:
    required, any_groups, _ = RULE_MATERIAL_MANIFESTS[code]
    material = set(required)
    material.update(next(iter(group)) for group in any_groups)
    deciding_input = _DECIDING_INPUT[code]
    material.add(deciding_input)
    clause, operator, threshold = _DECIDING_COMPARISON[code]
    trace = []
    for name in preliminary_models.PRELIMINARY_INPUT_ORDER:
        if name not in material:
            continue
        value_type = _value_type(name)
        value, resolved_clause, resolved_operator, resolved_threshold = _resolved_comparison(name)
        if code in {
            PreliminaryDecidingRuleCode.INSUFFICIENT_AI_CAPABILITY,
            PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_NO_CAPABILITY,
        } and name.value.startswith("capability."):
            value, resolved_clause, resolved_operator, resolved_threshold = (
                False,
                PreliminaryComparisonClause.CAPABILITY_FALSE,
                PreliminaryComparisonOperator.IS_FALSE,
                None,
            )
        unresolved = name is deciding_input and operator is PreliminaryComparisonOperator.IS_UNKNOWN
        if unresolved:
            value = None
            classification = PreliminaryEvidenceClassification.UNKNOWN
            evidence_ids = ("unknown-1",)
        elif value_type is PreliminaryValueType.TEXT:
            classification = PreliminaryEvidenceClassification.DOCUMENTED
            evidence_ids = ("fact-1",)
        elif value_type is PreliminaryValueType.BOOLEAN:
            if name is deciding_input:
                value = operator is not PreliminaryComparisonOperator.IS_FALSE
            classification = PreliminaryEvidenceClassification.DOCUMENTED
            evidence_ids = ("fact-1",)
        else:
            if name is deciding_input:
                if operator is PreliminaryComparisonOperator.LT:
                    value = int(threshold) - 1
                elif operator is PreliminaryComparisonOperator.GTE:
                    value = int(threshold)
                elif operator is PreliminaryComparisonOperator.EQ:
                    value = int(threshold)
            classification = PreliminaryEvidenceClassification.DOCUMENTED
            evidence_ids = ("fact-1",)
        comparison = PreliminaryRuleComparison(
            clause_code=clause if name is deciding_input else resolved_clause,
            operator=operator if name is deciding_input else resolved_operator,
            threshold_value=threshold if name is deciding_input else resolved_threshold,
            matched=True,
        )
        trace.append(
            PreliminaryDecisionInputTrace(
                input_name=name,
                reviewed_field_path=f"steps.step-1.{name.value}",
                value_type=value_type,
                normalized_value=value,
                classification=classification,
                evidence_item_ids=evidence_ids,
                material=True,
                material_stage=PreliminaryEvaluationStage.AUTONOMY,
                comparison=comparison,
            )
        )
    return tuple(trace)


def _activity(**updates) -> PreliminaryActivityResult:
    code = updates.pop(
        "deciding_rule_code",
        PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_AUTONOMY_UNKNOWN,
    )
    direction = updates.pop("provisional_direction", RULE_DIRECTION_BY_CODE[code])
    confidence = updates.pop(
        "confidence",
        _confidence(
            PreliminaryConfidence.LOW
            if direction is ProvisionalDirection.INSUFFICIENT_BASIS
            or code is PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_AUTONOMY_UNKNOWN
            else PreliminaryConfidence.HIGH
        ),
    )
    payload = {
        "step_id": "step-1",
        "activity": "Record complaint",
        "provisional_direction": direction,
        "deciding_rule_code": code,
        "confidence": confidence,
        "rationale": "Evidence supports exploration, while volume remains unknown.",
        "documented_facts": (_fact(),),
        "reasonable_inferences": (_inference(),),
        "unknowns": (_unknown(),),
        "next_evidence_to_collect": (
            NextEvidenceToCollect(
                request_id="request-1",
                description="Collect the latest complaint-volume report.",
                resolves_unknown_ids=("unknown-1",),
                suggested_owner="Operations manager",
            ),
        ),
        "decision_input_trace": _trace_for(code),
    }
    payload.update(updates)
    return PreliminaryActivityResult(**payload)


def _lineage(**updates) -> PreliminaryAssessmentLineage:
    payload = {
        "source_document_id": DOCUMENT_ID,
        "extraction_run_id": "extraction-1",
        "review_id": "review-1",
        "approval_event_id": "approval-event-1",
        "approval_statement": "APPROVE CURRENT-STATE PROCESS",
        "approved_at": FIXED_TIME,
        "validated_process_id": "process-1",
        "validated_process_fingerprint": PROCESS_FINGERPRINT,
    }
    payload.update(updates)
    return PreliminaryAssessmentLineage(**payload)


def _assessment(**updates) -> PreliminaryAssessment:
    payload = {
        "schema_version": "preliminary-assessment.v0.1",
        "assessment_kind": "PRELIMINARY_ASSESSMENT",
        "preliminary_assessment_id": "preliminary-1",
        "created_at": FIXED_TIME,
        "rule_set": PRELIMINARY_EVALUATOR_RULES_V0_1.reference(),
        "journey_selection": JourneySelection(
            schema_version="journey-selection.v0.1",
            journey=AssessmentJourney.EXPLORE_PROCESS,
        ),
        "lineage": _lineage(),
        "process_id": "process-1",
        "process_name": "Complaint handling",
        "confidence": _confidence(),
        "activity_results": (_activity(),),
        "disclaimer": PRELIMINARY_ASSESSMENT_DISCLAIMER,
    }
    payload.update(updates)
    return PreliminaryAssessment(**payload)


def test_all_evidence_classes_validate_with_explicit_semantics() -> None:
    adapter = TypeAdapter(PreliminaryEvidence)

    fact = adapter.validate_python(_fact().model_dump(mode="json"))
    inference = adapter.validate_python(_inference().model_dump(mode="json"))
    unknown = adapter.validate_python(_unknown().model_dump(mode="json"))

    assert isinstance(fact, DocumentedFact)
    assert fact.exact_excerpt == "Agent records the complaint."
    assert isinstance(inference, ReasonableInference)
    assert inference.derived_from_fact_ids == ("fact-1",)
    assert isinstance(unknown, PreliminaryUnknown)
    assert unknown.evidence_needed == "A recent complaint-volume report."


def test_inference_cannot_validate_as_a_documented_fact() -> None:
    payload = _inference().model_dump(mode="json")

    with pytest.raises(ValidationError):
        DocumentedFact.model_validate(payload)


def test_documented_fact_requires_document_identity_excerpt_and_locator() -> None:
    for missing_field in (
        "source_document_id",
        "exact_excerpt",
        "source_locator",
    ):
        payload = _fact().model_dump(mode="json")
        payload.pop(missing_field)
        with pytest.raises(ValidationError):
            DocumentedFact.model_validate(payload)


def test_human_supplied_information_cannot_claim_document_supported_origin() -> None:
    payload = _fact().model_dump(mode="json")
    payload["information_origin"] = "HUMAN_SUPPLIED"

    with pytest.raises(ValidationError):
        DocumentedFact.model_validate(payload)


@pytest.mark.parametrize("forbidden_field", ["value", "supporting_evidence"])
def test_unknown_cannot_contain_an_invented_value_or_supporting_evidence(
    forbidden_field: str,
) -> None:
    payload = _unknown().model_dump(mode="json")
    payload[forbidden_field] = "invented"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PreliminaryUnknown.model_validate(payload)


def test_unknown_requires_evidence_or_owner_needed_to_resolve_it() -> None:
    with pytest.raises(ValidationError, match="requires evidence or an owner"):
        _unknown(evidence_needed=None, owner_needed=None)


@pytest.mark.parametrize("missing_field", ["derived_from_fact_ids", "rationale"])
def test_inference_requires_documented_fact_lineage_and_rationale(
    missing_field: str,
) -> None:
    payload = _inference().model_dump(mode="json")
    payload.pop(missing_field)

    with pytest.raises(ValidationError):
        ReasonableInference.model_validate(payload)


def test_activity_rejects_inference_lineage_not_present_in_its_facts() -> None:
    with pytest.raises(ValidationError, match="unknown documented facts"):
        _activity(
            reasonable_inferences=(
                _inference(derived_from_fact_ids=("fact-not-present",)),
            )
        )


@pytest.mark.parametrize(
    ("direction", "code"),
    [
        (ProvisionalDirection.LIKELY_NO_CHANGE, PreliminaryDecidingRuleCode.LIKELY_NO_CHANGE),
        (ProvisionalDirection.LIKELY_PROCESS_IMPROVEMENT_FIRST, PreliminaryDecidingRuleCode.LIKELY_PROCESS_IMPROVEMENT_FIRST),
        (ProvisionalDirection.LIKELY_CONVENTIONAL_AUTOMATION, PreliminaryDecidingRuleCode.LIKELY_CONVENTIONAL_AUTOMATION),
        (ProvisionalDirection.LIKELY_HUMAN_LED, PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_LOW_AI_FIT),
        (ProvisionalDirection.POTENTIAL_AI_ASSISTED_WORK, PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_CONSTRAINT),
        (ProvisionalDirection.POTENTIAL_AI_AUTOMATION, PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION),
        (ProvisionalDirection.INSUFFICIENT_BASIS, PreliminaryDecidingRuleCode.INSUFFICIENT_CHANGE_CASE),
    ],
)
def test_all_seven_provisional_directions_are_valid(
    direction: ProvisionalDirection,
    code: PreliminaryDecidingRuleCode,
) -> None:
    assert _activity(deciding_rule_code=code).provisional_direction is direction


@pytest.mark.parametrize(
    "level", [PreliminaryConfidence.MEDIUM, PreliminaryConfidence.HIGH]
)
def test_insufficient_basis_cannot_have_medium_or_high_confidence(
    level: PreliminaryConfidence,
) -> None:
    with pytest.raises(ValidationError, match="requires Low confidence"):
        _activity(
            deciding_rule_code=PreliminaryDecidingRuleCode.INSUFFICIENT_CHANGE_CASE,
            provisional_direction=ProvisionalDirection.INSUFFICIENT_BASIS,
            confidence=_confidence(level),
        )


@pytest.mark.parametrize("level", list(PreliminaryConfidence))
def test_preliminary_confidence_is_explicitly_evidence_coverage_only(
    level: PreliminaryConfidence,
) -> None:
    confidence = _confidence(level)

    assert confidence.level is level
    assert confidence.meaning == "EVIDENCE_COVERAGE_ONLY"


def test_journey_selection_supports_both_approved_choices() -> None:
    selections = {
        JourneySelection(
            schema_version="journey-selection.v0.1", journey=journey
        ).journey
        for journey in AssessmentJourney
    }

    assert selections == {
        AssessmentJourney.EXPLORE_PROCESS,
        AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
    }


def test_preliminary_assessment_requires_explore_process_selection() -> None:
    selection = JourneySelection(
        schema_version="journey-selection.v0.1",
        journey=AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
    )

    with pytest.raises(ValidationError, match="requires the EXPLORE_PROCESS journey"):
        _assessment(journey_selection=selection)


@pytest.mark.parametrize(
    "missing_field",
    [
        "source_document_id",
        "extraction_run_id",
        "review_id",
        "approval_event_id",
        "approval_statement",
        "approved_at",
        "validated_process_id",
        "validated_process_fingerprint",
    ],
)
def test_approved_process_lineage_requires_every_identity_field(
    missing_field: str,
) -> None:
    payload = _lineage().model_dump(mode="json")
    payload.pop(missing_field)

    with pytest.raises(ValidationError):
        PreliminaryAssessmentLineage.model_validate(payload)


def test_lineage_requires_exact_approval_and_validated_process_fingerprint() -> None:
    with pytest.raises(ValidationError):
        _lineage(approval_statement="approve")
    with pytest.raises(ValidationError):
        _lineage(validated_process_fingerprint="not-a-sha256")
    with pytest.raises(ValidationError, match="must match approved lineage"):
        _assessment(process_id="another-process")


def test_documented_fact_matching_approved_process_document_validates() -> None:
    assessment = _assessment()

    assert assessment.activity_results[0].documented_facts[0].source_document_id == (
        assessment.lineage.source_document_id
    )


def test_documented_fact_from_a_different_document_is_rejected() -> None:
    activity = _activity(
        documented_facts=(_fact(source_document_id=OTHER_DOCUMENT_ID),)
    )

    with pytest.raises(
        ValidationError,
        match="must reference the approved current-state process document",
    ):
        _assessment(activity_results=(activity,))


@pytest.mark.parametrize("mismatched_activity_index", [0, 1])
def test_document_lineage_check_applies_to_every_activity_result(
    mismatched_activity_index: int,
) -> None:
    activities = [
        _activity(step_id="step-1", activity="Record complaint"),
        _activity(step_id="step-2", activity="Review complaint"),
    ]
    activities[mismatched_activity_index] = activities[
        mismatched_activity_index
    ].model_copy(
        update={
            "documented_facts": (
                _fact(source_document_id=OTHER_DOCUMENT_ID),
            )
        }
    )

    with pytest.raises(
        ValidationError,
        match="must reference the approved current-state process document",
    ):
        _assessment(activity_results=tuple(activities))


def test_contracts_are_immutable_and_reject_unknown_fields() -> None:
    assessment = _assessment()

    with pytest.raises(ValidationError, match="frozen"):
        assessment.process_name = "Changed"  # type: ignore[misc]
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PreliminaryAssessment.model_validate(
            {**assessment.model_dump(mode="json"), "official_outcome": "AUTOMATE"}
        )
    assert isinstance(assessment.activity_results, tuple)
    assert isinstance(assessment.activity_results[0].documented_facts, tuple)


def test_contract_has_no_formal_outcome_gate_status_or_package_fields() -> None:
    forbidden_fields = {
        "outcome_code",
        "gate_results",
        "decision_status",
        "decision_package",
        "implementation_approval",
    }
    field_names = set(PreliminaryAssessment.model_fields)
    field_names.update(PreliminaryActivityResult.model_fields)
    serialized = _assessment().model_dump(mode="json")
    source = inspect.getsource(preliminary_models)

    assert forbidden_fields.isdisjoint(field_names)
    assert forbidden_fields.isdisjoint(serialized)
    assert "models.four_gate_assessment" not in source
    assert "models.four_gate_integrated_assessment" not in source
    assert "models.decision_support" not in source


def test_disclaimer_is_mandatory_and_exact() -> None:
    payload = _assessment().model_dump(mode="json")
    payload.pop("disclaimer")
    with pytest.raises(ValidationError):
        PreliminaryAssessment.model_validate(payload)

    payload["disclaimer"] = "Preliminary only."
    with pytest.raises(ValidationError):
        PreliminaryAssessment.model_validate(payload)


def test_identical_preliminary_assessments_serialize_deterministically() -> None:
    first = _assessment()
    second = PreliminaryAssessment.model_validate(first.model_dump(mode="json"))

    assert first.canonical_json_bytes() == second.canonical_json_bytes()


def test_next_evidence_must_reference_an_activity_unknown() -> None:
    with pytest.raises(ValidationError, match="unknown unresolved questions"):
        _activity(
            next_evidence_to_collect=(
                NextEvidenceToCollect(
                    request_id="request-2",
                    description="Collect evidence.",
                    resolves_unknown_ids=("unknown-not-present",),
                ),
            )
        )


def test_rule_set_reference_and_activity_audit_fields_are_mandatory() -> None:
    assessment_payload = _assessment().model_dump(mode="json")
    assessment_payload.pop("rule_set")
    with pytest.raises(ValidationError):
        PreliminaryAssessment.model_validate(assessment_payload)

    activity_payload = _activity().model_dump(mode="json")
    activity_payload.pop("deciding_rule_code")
    with pytest.raises(ValidationError):
        PreliminaryActivityResult.model_validate(activity_payload)
    activity_payload = _activity().model_dump(mode="json")
    activity_payload.pop("decision_input_trace")
    with pytest.raises(ValidationError):
        PreliminaryActivityResult.model_validate(activity_payload)


def test_rule_set_reference_requires_the_approved_fingerprint() -> None:
    payload = _assessment().model_dump(mode="json")
    payload["rule_set"]["rule_set_fingerprint"] = "f" * 64

    with pytest.raises(ValidationError):
        PreliminaryAssessment.model_validate(payload)


def test_deciding_rule_direction_and_material_manifest_are_closed() -> None:
    with pytest.raises(ValidationError, match="does not produce"):
        _activity(
            deciding_rule_code=PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION,
            provisional_direction=ProvisionalDirection.LIKELY_NO_CHANGE,
        )

    trace = tuple(
        item
        for item in _trace_for(PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION)
        if item.input_name is not PreliminaryInputName.ACTIVITY_IDENTITY
    )
    with pytest.raises(ValidationError, match="omits inputs required"):
        _activity(
            deciding_rule_code=PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION,
            decision_input_trace=trace,
        )


def test_trace_evidence_reference_must_resolve_by_classification() -> None:
    trace = list(_trace_for(PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION))
    trace[0] = trace[0].model_copy(update={"evidence_item_ids": ("missing",)})

    with pytest.raises(ValidationError, match="do not resolve"):
        _activity(
            deciding_rule_code=PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION,
            decision_input_trace=tuple(trace),
        )


def test_unknown_and_conflict_values_are_null_and_resolved_values_are_not() -> None:
    base = {
        "input_name": PreliminaryInputName.BUSINESS_VALUE,
        "reviewed_field_path": "steps.step-1.criteria.business_value",
        "value_type": PreliminaryValueType.ORDINAL,
        "evidence_item_ids": ("unknown-1",),
        "material": False,
    }
    with pytest.raises(ValidationError, match="cannot carry a value"):
        PreliminaryDecisionInputTrace(
            **base,
            normalized_value=3,
            classification=PreliminaryEvidenceClassification.UNKNOWN,
        )
    with pytest.raises(ValidationError, match="require a value"):
        PreliminaryDecisionInputTrace(
            **base,
            normalized_value=None,
            classification=PreliminaryEvidenceClassification.DOCUMENTED,
        )


def test_trace_order_and_non_material_context_are_enforced() -> None:
    trace = _trace_for(PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION)
    with pytest.raises(ValidationError, match="ordering must be deterministic"):
        _activity(
            deciding_rule_code=PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION,
            decision_input_trace=tuple(reversed(trace)),
        )

    with pytest.raises(ValidationError, match="non-material inputs cannot carry"):
        PreliminaryDecisionInputTrace(
            input_name=PreliminaryInputName.ACTIVITY_IDENTITY,
            reviewed_field_path="steps.step-1.activity",
            value_type=PreliminaryValueType.TEXT,
            normalized_value="Record complaint",
            classification=PreliminaryEvidenceClassification.DOCUMENTED,
            evidence_item_ids=("fact-1",),
            material=False,
            material_stage=PreliminaryEvaluationStage.CHANGE_CASE,
            comparison=PreliminaryRuleComparison(
                clause_code=PreliminaryComparisonClause.ACTIVITY_PRESENT,
                operator=PreliminaryComparisonOperator.PRESENT,
                matched=True,
            ),
        )


def test_activity_confidence_is_derived_from_material_inferences() -> None:
    trace = list(_trace_for(PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION))
    business_index = next(
        index
        for index, item in enumerate(trace)
        if item.input_name is PreliminaryInputName.BUSINESS_VALUE
    )
    trace[business_index] = trace[business_index].model_copy(
        update={
            "classification": PreliminaryEvidenceClassification.REASONABLE_INFERENCE,
            "evidence_item_ids": ("inference-1",),
        }
    )

    activity = _activity(
        deciding_rule_code=PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION,
        confidence=_confidence(PreliminaryConfidence.MEDIUM),
        decision_input_trace=tuple(trace),
    )
    assert activity.confidence.level is PreliminaryConfidence.MEDIUM

    with pytest.raises(ValidationError, match="path-material evidence coverage"):
        _activity(
            deciding_rule_code=PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION,
            confidence=_confidence(PreliminaryConfidence.HIGH),
            decision_input_trace=tuple(trace),
        )

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_adoption_engine.models.preliminary_assessment_v0_2 import (
    EvidenceRecord,
    KnowledgeClassification,
    PreliminaryAssessmentV2,
    PreliminaryEvaluationSuccessV2,
)
from ai_adoption_engine.models.preliminary_persistence import (
    PersistedPreliminaryResult,
    PreliminaryPersistenceRecordType,
)
from ai_adoption_engine.persistence.preliminary_serialization import (
    deserialize_preliminary_persistence_record,
    serialize_preliminary_persistence_record,
)
from ai_adoption_engine.preliminary.evaluator_v0_2 import (
    PreliminaryAssessmentEvaluatorV2,
)
from ai_adoption_engine.preliminary.journey import (
    preliminary_v0_2_compatibility_identity,
)
from ai_adoption_engine.presentation.preliminary_result import (
    CorruptPreliminaryPresentationRecord,
    UnsupportedPreliminaryPresentationIdentity,
    present_preliminary_result,
    render_preliminary_customer_text,
)
from tests.fakes.preliminary_v2 import approved_review_for
from tests.unit.test_preliminary_journey_service import _context, _select_explore
from tests.unit.test_preliminary_run_service import RunIds, _run, _service


DIRECTION_LABELS = {
    "LIKELY_NO_CHANGE": "No change indicated",
    "LIKELY_PROCESS_IMPROVEMENT_FIRST": "Improve the process first",
    "LIKELY_CONVENTIONAL_AUTOMATION": "Consider conventional automation",
    "LIKELY_HUMAN_LED": "Keep this work human-led",
    "POTENTIAL_AI_ASSISTED_WORK": "Potential AI assistance",
    "POTENTIAL_AI_AUTOMATION": "Potential AI automation",
    "INSUFFICIENT_BASIS_TO_SUGGEST_A_DIRECTION": "More evidence is needed.",
}


@pytest.fixture
def persisted_results(tmp_path: Path):
    context = _context(tmp_path)
    _select_explore(context)
    ids = RunIds()
    v0_1 = _run(_service(context, id_factory=ids), context, "presentation-v0-1")
    v0_2 = _run(
        _service(
            context,
            id_factory=ids,
            supported_identity=preliminary_v0_2_compatibility_identity(),
        ),
        context,
        "presentation-v0-2",
    )
    assert v0_1.result is not None
    assert v0_2.result is not None
    hydrated = []
    for result in (v0_1.result, v0_2.result):
        payload, digest = serialize_preliminary_persistence_record(
            PreliminaryPersistenceRecordType.PRELIMINARY_RESULT,
            result.schema_version,
            result,
        )
        hydrated.append(
            deserialize_preliminary_persistence_record(
                PreliminaryPersistenceRecordType.PRELIMINARY_RESULT,
                result.schema_version,
                payload,
                digest,
            )
        )
    return tuple(hydrated)


def _evaluated(*sentences: str) -> PreliminaryAssessmentV2:
    evaluated = PreliminaryAssessmentEvaluatorV2().evaluate(
        approved_review_for(*sentences)
    )
    assert isinstance(evaluated, PreliminaryEvaluationSuccessV2)
    return evaluated.assessment


def _replace_source_document(value, source_document_id: str):
    if isinstance(value, dict):
        return {
            key: (
                source_document_id
                if key == "source_document_id"
                else _replace_source_document(item, source_document_id)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_source_document(item, source_document_id) for item in value]
    if isinstance(value, tuple):
        if len(value) == 5 and isinstance(value[0], str) and value[0].startswith("doc-"):
            return (source_document_id, *value[1:])
        return tuple(_replace_source_document(item, source_document_id) for item in value)
    return value


def _with_assessment(
    base: PersistedPreliminaryResult,
    assessment: PreliminaryAssessmentV2,
) -> PersistedPreliminaryResult:
    payload = _replace_source_document(
        assessment.model_dump(mode="python"), base.source.source_document_id
    )
    payload["process_id"] = base.source.validated_process_id
    payload["lineage"].update(
        {
            "source_document_id": base.source.source_document_id,
            "extraction_run_id": base.source.extraction_run_id,
            "approved_review_artifact_id": base.source.approved_review_artifact_id,
            "approval_event_id": base.source.approval_event_id,
            "validated_process_id": base.source.validated_process_id,
            "validated_process_fingerprint": base.source.validated_process_fingerprint,
        }
    )
    aligned = PreliminaryAssessmentV2.model_validate(payload)
    return PersistedPreliminaryResult.model_validate(
        base.model_copy(update={"assessment": aligned}).model_dump(mode="python")
    )


def _with_first_direction(
    result: PersistedPreliminaryResult, direction: str
) -> PersistedPreliminaryResult:
    payload = result.model_dump(mode="python")
    activity = next(
        item for item in payload["assessment"]["activity_results"] if item["opportunities"]
    )
    activity["opportunities"][0]["direction"] = direction
    return PersistedPreliminaryResult.model_validate(payload)


def test_v0_1_customer_meaning_is_preserved(persisted_results) -> None:
    v0_1, _ = persisted_results
    presentation = present_preliminary_result(v0_1)

    assert presentation.customer.title == "Preliminary Assessment"
    assert presentation.customer.overall_evidence_coverage == (
        f"{v0_1.assessment.confidence.level.value} evidence coverage"
    )
    assert [item.heading for item in presentation.customer.activities] == [
        item.activity for item in v0_1.assessment.activity_results
    ]
    assert [item.provisional_direction for item in presentation.customer.activities] == [
        item.provisional_direction.value for item in v0_1.assessment.activity_results
    ]
    assert [item.explanation for item in presentation.customer.activities] == [
        item.rationale for item in v0_1.assessment.activity_results
    ]
    rendered = render_preliminary_customer_text(presentation)
    assert "activity_identity" not in rendered
    assert "business_value" not in rendered
    assert "capability." not in rendered


@pytest.mark.parametrize("code,label", DIRECTION_LABELS.items())
def test_v0_2_direction_labels_are_exact_and_nontechnical(
    persisted_results, code: str, label: str
) -> None:
    _, v0_2 = persisted_results
    changed = _with_first_direction(v0_2, code)
    presentation = present_preliminary_result(changed)
    opportunity = next(
        opportunity
        for activity in presentation.customer.activities
        for opportunity in activity.opportunities
    )

    assert opportunity.provisional_direction == label
    assert code not in render_preliminary_customer_text(presentation)


def test_v0_2_actionable_hierarchy_keeps_independent_opportunities_separate(
    persisted_results,
) -> None:
    _, base = persisted_results
    assessment = _evaluated(
        "The officer meets the complainant to produce agreed points. "
        "Using the agreed points, the officer weighs exceptional circumstances to determine the exception treatment. "
        "Using the exception treatment, the officer makes the final determination and signs the final determination. "
        "Using the final determination, the officer records the final determination in the complaints register."
    )
    result = _with_assessment(base, assessment)
    presentation = present_preliminary_result(result)
    activity = presentation.customer.activities[0]

    assert activity.heading == "Activity 1"
    assert activity.state == "Provisional opportunities identified"
    assert [item.heading for item in activity.opportunities] == [
        "Opportunity 1",
        "Opportunity 2",
        "Opportunity 3",
        "Opportunity 4",
    ]
    assert [item.provisional_direction for item in activity.opportunities] == [
        "Keep this work human-led",
        "Keep this work human-led",
        "Keep this work human-led",
        "Consider conventional automation",
    ]
    assert all(item.evidence.documented_source for item in activity.opportunities)
    assert all(item.evidence.engine_inference for item in activity.opportunities)


def test_v0_2_discovery_and_no_change_are_explicit_without_invented_direction(
    persisted_results,
) -> None:
    _, base = persisted_results
    discovery = present_preliminary_result(
        _with_assessment(
            base,
            _evaluated("The officer handles the complaint appropriately."),
        )
    ).customer.activities[0]
    no_change = present_preliminary_result(
        _with_assessment(
            base,
            _evaluated(
                "Current purpose is explicit; purpose is being achieved; performance is acceptable; controls are acceptable; "
                "no material process problem exists; no intervention is needed."
            ),
        )
    ).customer.activities[0]

    assert discovery.state == "More evidence is needed"
    assert discovery.provisional_direction == "More evidence is needed"
    assert discovery.opportunities == ()
    assert discovery.discovery_needs[0].evidence.next_evidence == (
        "Clarify what the activity currently does.",
    )
    assert no_change.state == "No change indicated"
    assert no_change.provisional_direction == "No change indicated"
    assert no_change.opportunities == ()
    assert no_change.discovery_needs == ()


def test_scoped_discovery_preserves_its_exact_source_excerpt(persisted_results) -> None:
    _, base = persisted_results
    activity = present_preliminary_result(
        _with_assessment(
            base,
            _evaluated(
                "The officer records the complaint and handles any special follow-up appropriately."
            ),
        )
    ).customer.activities[0]

    discovery_source = activity.discovery_needs[0].evidence.documented_source[0]
    assert discovery_source.statement == "Source text requiring clarification."
    assert discovery_source.source_excerpts[0].exact_excerpt == (
        "The officer records the complaint and handles any special follow-up appropriately."
    )
    assert discovery_source.source_excerpts[0].source_locator


def test_v0_2_sections_keep_sources_inferences_unknowns_conflicts_and_next_evidence_distinct(
    persisted_results,
) -> None:
    _, base = persisted_results
    payload = base.model_dump(mode="python")
    activity = payload["assessment"]["activity_results"][0]
    activity["unknowns"] = [
        EvidenceRecord(
            item_id="unknown-presentation",
            classification=KnowledgeClassification.UNKNOWN,
            statement="Whether the control is mandatory is not established.",
        ).model_dump(mode="python")
    ]
    activity["conflicts"] = [
        EvidenceRecord(
            item_id="conflict-presentation",
            classification=KnowledgeClassification.CONFLICT,
            statement="The reviewed sources describe different control owners.",
        ).model_dump(mode="python")
    ]
    activity["reviewed_inferences"] = [
        EvidenceRecord(
            item_id="reviewed-inference-presentation",
            classification=KnowledgeClassification.REVIEWED_INFERENCE,
            statement="A reviewer confirmed the activity owner.",
            source_spans=activity["documented_facts"][0]["source_spans"],
        ).model_dump(mode="python")
    ]
    activity["next_evidence_to_collect"] = ["RESOLVE_CONFLICT"]
    result = PersistedPreliminaryResult.model_validate(payload)
    sections = present_preliminary_result(result).customer.activities[0].evidence

    assert sections.section_order == (
        "Documented source",
        "Reviewed inference",
        "Engine inference",
        "Unknown",
        "Conflict",
        "Next evidence",
    )
    assert sections.documented_source[0].source_excerpts[0].exact_excerpt
    assert sections.documented_source[0].source_excerpts[0].source_locator
    assert sections.engine_inference
    assert sections.reviewed_inference[0].statement.startswith("A reviewer")
    assert sections.unknown[0].statement.startswith("Whether")
    assert "does not mean zero" in sections.unknown[0].explanation
    assert sections.conflict[0].statement.startswith("The reviewed sources")
    assert sections.next_evidence == ("Resolve the conflicting source evidence.",)


def test_customer_text_hides_internal_identity_but_audit_retains_it(
    persisted_results,
) -> None:
    _, result = persisted_results
    presentation = present_preliminary_result(result, include_audit=True)
    rendered = render_preliminary_customer_text(presentation)
    assert presentation.audit is not None
    source = presentation.audit.source_identity

    assert source.preliminary_result_id == result.preliminary_result_id
    assert source.preliminary_run_id == result.preliminary_run_id
    assert source.evaluator_id == result.evaluator.evaluator_id
    assert source.rule_set_fingerprint == result.rule_set.rule_set_fingerprint
    for hidden in (
        result.preliminary_result_id,
        result.preliminary_run_id,
        result.evaluator.evaluator_id,
        result.rule_set.rule_set_id,
        result.rule_set.rule_set_fingerprint,
        "PA2-",
        "PD2-",
        "ACTIONABLE",
        "activity_identity",
    ):
        assert hidden not in rendered

    assert present_preliminary_result(result).audit is None


def test_presentation_is_frozen_versioned_ordered_and_deterministic(
    persisted_results,
) -> None:
    _, result = persisted_results
    first = present_preliminary_result(result)
    second = present_preliminary_result(result)

    assert first.schema_version == "preliminary-result-presentation.v0.1"
    assert first.canonical_json_bytes() == second.canonical_json_bytes()
    assert [item.heading for item in first.customer.activities] == [
        f"Activity {index}"
        for index in range(1, len(result.assessment.activity_results) + 1)
    ]
    with pytest.raises(ValidationError):
        first.customer.process_name = "Changed"


def test_unknown_mixed_drifted_and_corrupt_records_fail_closed_with_typed_errors(
    persisted_results,
) -> None:
    _, result = persisted_results
    unknown_evaluator = result.evaluator.model_copy(
        update={"evaluator_id": "preliminary-evaluator.v9"}
    )
    with pytest.raises(UnsupportedPreliminaryPresentationIdentity):
        present_preliminary_result(
            result.model_copy(update={"evaluator": unknown_evaluator})
        )

    drifted_rule = result.rule_set.model_copy(
        update={"rule_set_fingerprint": "0" * 64}
    )
    with pytest.raises(UnsupportedPreliminaryPresentationIdentity):
        present_preliminary_result(result.model_copy(update={"rule_set": drifted_rule}))

    mixed = result.model_copy(update={"output_schema_version": "preliminary-assessment.v0.1"})
    with pytest.raises(UnsupportedPreliminaryPresentationIdentity):
        present_preliminary_result(mixed)

    corrupt_assessment = result.assessment.model_copy(
        update={"rule_set_fingerprint": "0" * 64}
    )
    with pytest.raises(CorruptPreliminaryPresentationRecord):
        present_preliminary_result(
            result.model_copy(update={"assessment": corrupt_assessment})
        )


def test_mixed_activity_identity_and_unresolved_material_references_fail_closed(
    persisted_results,
) -> None:
    _, result = persisted_results
    mixed_payload = result.model_dump(mode="python")
    mixed_payload["assessment"]["activity_results"][0]["rule_set_fingerprint"] = (
        "0" * 64
    )
    mixed_activity = PersistedPreliminaryResult.model_validate(mixed_payload)
    with pytest.raises(CorruptPreliminaryPresentationRecord, match="activity"):
        present_preliminary_result(mixed_activity)

    reference_payload = result.model_dump(mode="python")
    opportunity = next(
        item
        for item in reference_payload["assessment"]["activity_results"]
        if item["opportunities"]
    )["opportunities"][0]
    opportunity["material_evidence_item_ids"] = ["missing-evidence"]
    unresolved = PersistedPreliminaryResult.model_validate(reference_payload)
    with pytest.raises(CorruptPreliminaryPresentationRecord, match="reference"):
        present_preliminary_result(unresolved)

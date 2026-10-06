from __future__ import annotations

from pathlib import Path

import pytest

from ai_adoption_engine.decision.four_gate_engine import FourGateAssessmentEngine
from ai_adoption_engine.decision.four_gate_policy import load_four_gate_policy
from ai_adoption_engine.formal.guidance import FormalGuidanceSuccess, derive_formal_evidence_guidance
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.formal_assessment import (
    FORMAL_ASSESSMENT_RESULT_SCHEMA,
    FORMAL_ASSESSMENT_RUN_MANIFEST_SCHEMA,
    FORMAL_ASSESSMENT_RUN_STORE_ID,
    FormalAssessmentInputProjection,
    FormalAssessmentResult,
    FormalAssessmentRunManifest,
    FormalResultActivityTrace,
    FormalRunOperation,
)
from ai_adoption_engine.models.four_gate_assessment import CapabilitySignalName
from ai_adoption_engine.presentation.formal_assessment_result import (
    CorruptFormalAssessmentPresentationRecord,
    InvalidFormalAssessmentPresentationGuidance,
    UnsupportedFormalAssessmentPresentationIdentity,
    present_formal_assessment_result,
)
from tests.unit.test_formal_assessment_models import (
    NOW,
    formal_result,
    run_request,
    source_projection,
)


ROOT = Path(__file__).resolve().parents[2]


def _guidance(result):
    outcome = derive_formal_evidence_guidance(
        result, guidance_id="guidance-1", generated_at=NOW
    )
    assert isinstance(outcome, FormalGuidanceSuccess)
    return outcome.guidance


def _result_with_values(overrides: dict[str, int | None]) -> FormalAssessmentResult:
    """Make one fully revalidated result fixture with a selected outcome path."""

    original = source_projection()
    process = original.engine_input.model_copy(deep=True)
    default_values = {
        "repetition": 5,
        "predictability": 5,
        "data_readiness": 5,
        "ai_capability_fit": 5,
        "human_judgement_requirement": 1,
        "business_value": 5,
        "risk_consequence": 1,
        "residual_risk_with_human_oversight": 1,
        "implementation_complexity": 1,
        "conventional_solution_fit": 1,
    }
    default_values.update(overrides)
    for step in process.steps:
        evidence_ids = [step.evidence_ids[0]]
        for criterion in CriterionName:
            value = default_values[criterion.value]
            supplied = step.characteristics.criterion(criterion)
            supplied.value = value
            supplied.knowledge_state = (
                KnowledgeState.UNKNOWN if value is None else KnowledgeState.KNOWN
            )
            supplied.confidence = None
            supplied.evidence_ids = [] if value is None else evidence_ids
            supplied.rationale = "Reviewed fixture value."
        accountability = step.characteristics.human_accountability_required
        accountability.value = False
        accountability.knowledge_state = KnowledgeState.KNOWN
        accountability.confidence = None
        accountability.evidence_ids = evidence_ids
        accountability.rationale = "Reviewed fixture value."
        for signal in CapabilitySignalName:
            supplied = getattr(step.characteristics.capability_signals, signal.value)
            supplied.value = signal is CapabilitySignalName.READS_UNSTRUCTURED_DOCUMENTS
            supplied.knowledge_state = KnowledgeState.KNOWN
            supplied.confidence = None
            supplied.evidence_ids = evidence_ids
            supplied.rationale = "Reviewed fixture value."

    activities = []
    for old_activity, step in zip(original.activities, process.steps, strict=True):
        traces = []
        for trace in old_activity.field_resolutions:
            target = trace.target
            if target.kind.value == "criterion":
                supplied = step.characteristics.criterion(target.criterion)
            elif target.kind.value == "human_accountability_required":
                supplied = step.characteristics.human_accountability_required
            else:
                supplied = getattr(
                    step.characteristics.capability_signals,
                    target.capability_signal.value,
                )
            traces.append(
                trace.model_copy(
                    update={
                        "approved_value": supplied.value,
                        "approved_knowledge_state": supplied.knowledge_state,
                        "projected_value": supplied.value,
                        "projected_knowledge_state": supplied.knowledge_state,
                        "projected_confidence": supplied.confidence,
                        "evidence_ids": tuple(supplied.evidence_ids),
                    }
                )
            )
        activities.append(
            old_activity.model_copy(
                update={"engine_input": step, "field_resolutions": tuple(traces)}
            )
        )
    projection = FormalAssessmentInputProjection(
        schema_version="formal-assessment-input-projection.v0.1",
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        projection_id=original.projection_id,
        run_lineage=original.run_lineage,
        authorization=original.authorization,
        approved_process=process.model_copy(deep=True),
        engine_input=process,
        activities=tuple(activities),
        complete_evidence=original.complete_evidence,
    )
    manifest = FormalAssessmentRunManifest(
        schema_version=FORMAL_ASSESSMENT_RUN_MANIFEST_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        run_lineage=projection.run_lineage,
        attempt_number=1,
        authorization=projection.authorization,
        projection=projection,
        request=run_request(
            operation=FormalRunOperation.AUTHORIZE, rl=projection.run_lineage
        ),
        created_at=NOW,
    )
    assessment = FourGateAssessmentEngine(
        load_four_gate_policy(ROOT / "config" / "decision_policy.v0.3.json")
    ).assess(process)
    traces = tuple(
        FormalResultActivityTrace(
            activity_id=activity.activity_id,
            projected_activity_path=f"activities[{index}]",
            assessment_activity_path=f"assessment.step_assessments[{index}]",
            projection_fingerprint=projection.projection_fingerprint,
            evidence_ids=tuple(activity.engine_input.evidence_ids),
        )
        for index, activity in enumerate(projection.activities)
    )
    return FormalAssessmentResult(
        schema_version=FORMAL_ASSESSMENT_RESULT_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        result_id="result-with-values",
        manifest=manifest,
        assessment=assessment,
        activity_traces=traces,
        completed_at=NOW,
    )


@pytest.mark.parametrize(
    ("overrides", "expected_outcome", "expected_priority"),
    [
        ({"business_value": 1}, "No Change Justified", "Not Applicable"),
        ({"data_readiness": 1}, "Process Improvement First", "Not Applicable"),
        ({"conventional_solution_fit": 5}, "Conventional Automation", "Not Applicable"),
        ({"ai_capability_fit": 2}, "Keep Human-Led", "Not Applicable"),
        ({"residual_risk_with_human_oversight": 4}, "Keep Human-Led", "Not Applicable"),
        ({"repetition": None}, "AI Automation", "Incomplete"),
        ({"human_judgement_requirement": 3}, "AI-Assisted Work", "Complete"),
        ({}, "AI Automation", "Complete"),
    ],
)
def test_presentation_preserves_every_closed_outcome_path(
    overrides, expected_outcome, expected_priority
) -> None:
    presentation = present_formal_assessment_result(_result_with_values(overrides))
    activity = presentation.customer.activities[0]

    assert activity.outcome == expected_outcome
    assert activity.priority.status == expected_priority
    assert [gate.name for gate in activity.gates] == [
        "Gate 1 — Should we change?",
        "Gate 2 — Is it ready?",
        "Gate 3 — Best intervention",
        "Gate 4 — Safe autonomy",
    ]


def test_gate_three_human_led_and_gate_four_safety_veto_remain_distinct() -> None:
    gate_three = present_formal_assessment_result(
        _result_with_values({"ai_capability_fit": 2})
    ).customer.activities[0]
    gate_four = present_formal_assessment_result(
        _result_with_values({"residual_risk_with_human_oversight": 4})
    ).customer.activities[0]

    assert gate_three.gates[2].decision == "Keep human-led selected"
    assert gate_three.gates[3].decision.startswith("Not evaluated")
    assert gate_four.gates[2].decision == "AI selected"
    assert gate_four.gates[3].decision == "AI not permitted by the Gate 4 safety boundary"


def test_default_presentation_is_customer_safe_and_preserves_ordered_gaps() -> None:
    result = formal_result()
    presentation = present_formal_assessment_result(result, guidance=_guidance(result))

    assert presentation.schema_version == "formal-assessment-result-presentation.v0.1"
    assert presentation.audit is None
    customer = presentation.customer
    assert customer.title == "Organisational Assessment"
    assert customer.customer_status == "Organisational assessment completed — review required"
    assert customer.non_approval_notice == (
        "This result is not formal approval or implementation authority."
    )
    assert customer.input_mode == "Approved process only"
    assert [item.name for item in customer.activities] == [
        item.activity for item in result.assessment.step_assessments
    ]
    first = customer.activities[0]
    assert first.outcome == "Discovery Required"
    assert [gate.name for gate in first.gates] == [
        "Gate 1 — Should we change?",
        "Gate 2 — Is it ready?",
        "Gate 3 — Best intervention",
        "Gate 4 — Safe autonomy",
    ]
    assert first.gates[0].blocking_gaps[0].guidance is not None
    default_bytes = presentation.canonical_json_bytes()
    for forbidden in ("result-1", "formal-run", "authorization", "fingerprint", "sha256"):
        assert forbidden.encode() not in default_bytes


def test_audit_retains_the_exact_frozen_sources_without_altering_customer_view() -> None:
    result = formal_result()
    presentation = present_formal_assessment_result(
        result, guidance=_guidance(result), include_audit=True
    )

    assert presentation.audit is not None
    assert presentation.audit.source_result == result
    assert presentation.audit.guidance is not None
    default = present_formal_assessment_result(result, guidance=_guidance(result))
    assert default.customer == presentation.customer
    assert result.result_id.encode() not in default.canonical_json_bytes()


def test_presentation_rejects_result_or_guidance_that_is_not_exact() -> None:
    result = formal_result()
    guidance = _guidance(result)
    reordered = result.model_copy(
        update={"activity_traces": tuple(reversed(result.activity_traces))}
    )

    with pytest.raises(CorruptFormalAssessmentPresentationRecord):
        present_formal_assessment_result(reordered)
    unrelated = result.model_copy(update={"result_id": "different-result"})
    with pytest.raises(InvalidFormalAssessmentPresentationGuidance):
        present_formal_assessment_result(
            result,
            guidance=guidance.model_copy(update={"source_result": unrelated}),
        )


def test_presentation_requires_an_explicit_supported_identity_handler() -> None:
    result = formal_result()
    compatibility = result.manifest.authorization.compatibility.model_copy(
        update={"policy_version": "9.9.9"}
    )
    authorization = result.manifest.authorization.model_copy(
        update={"compatibility": compatibility}
    )
    mixed = result.model_copy(
        update={"manifest": result.manifest.model_copy(update={"authorization": authorization})}
    )

    with pytest.raises(UnsupportedFormalAssessmentPresentationIdentity):
        present_formal_assessment_result(mixed)

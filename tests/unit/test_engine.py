from ai_adoption_engine.decision.engine import AssessmentEngine
from ai_adoption_engine.models.enums import (
    CriterionName,
    PriorityStatus,
    RecommendationMode,
)
from ai_adoption_engine.models.process import BusinessProcess


def test_sample_exercises_all_recommendation_modes(
    process: BusinessProcess, engine: AssessmentEngine
) -> None:
    assessment = engine.assess(process)
    by_step = {item.step_id: item for item in assessment.step_assessments}
    assert by_step["S1"].recommendation_mode is RecommendationMode.AUTOMATE
    assert by_step["S2"].recommendation_mode is RecommendationMode.DO_NOT_RECOMMEND
    assert by_step["S3"].recommendation_mode is RecommendationMode.AUGMENT
    assert by_step["S4"].recommendation_mode is RecommendationMode.INVESTIGATE_FURTHER
    assert by_step["S5"].recommendation_mode is RecommendationMode.DO_NOT_RECOMMEND


def test_only_qualifying_modes_receive_priority_scores(
    process: BusinessProcess, engine: AssessmentEngine
) -> None:
    assessment = engine.assess(process)
    for step in assessment.step_assessments:
        if step.recommendation_mode in {
            RecommendationMode.AUTOMATE,
            RecommendationMode.AUGMENT,
        }:
            assert step.priority is not None
        else:
            assert step.priority is None


def test_output_contains_policy_warning_reasoning_and_evidence(
    process: BusinessProcess, engine: AssessmentEngine
) -> None:
    assessment = engine.assess(process)
    assert "NOT YET ACADEMICALLY VALIDATED" in assessment.policy_status
    for step in assessment.step_assessments:
        assert step.evidence
        assert step.gate_results
        assert any("Final mode" in reason for reason in step.reasoning)


def test_engine_is_deterministic(
    process: BusinessProcess, engine: AssessmentEngine
) -> None:
    first = engine.assess(process).model_dump(mode="json")
    second = engine.assess(process).model_dump(mode="json")
    assert first == second


def test_complete_criterion_and_accountability_provenance_is_exposed(
    process: BusinessProcess, engine: AssessmentEngine
) -> None:
    step = engine.assess(process).step_assessments[2]
    assert {item.criterion for item in step.criteria} == set(CriterionName)
    judgement = next(
        item
        for item in step.criteria
        if item.criterion is CriterionName.HUMAN_JUDGEMENT_REQUIREMENT
    )
    predictability = next(
        item
        for item in step.criteria
        if item.criterion is CriterionName.PREDICTABILITY
    )
    assert judgement.evidence_ids == ["E5"]
    assert judgement.material_to_recommendation is True
    assert predictability.material_to_recommendation is False
    assert step.human_accountability.value is True
    assert step.human_accountability.material_to_recommendation is True


def test_nonmaterial_unknown_allows_recommendation_but_makes_priority_incomplete(
    process: BusinessProcess, engine: AssessmentEngine
) -> None:
    step = process.steps[2]
    step.characteristics.repetition.value = None
    step.characteristics.repetition.knowledge_state = "unknown"
    assessed = engine.assess(process).step_assessments[2]
    assert assessed.recommendation_mode is RecommendationMode.AUGMENT
    assert assessed.priority is None
    assert assessed.priority_status is PriorityStatus.INCOMPLETE
    assert assessed.priority_missing_criteria == [CriterionName.REPETITION]
    repetition = next(
        item for item in assessed.criteria if item.criterion is CriterionName.REPETITION
    )
    assert repetition.value is None
    assert repetition.material_to_recommendation is False
    assert repetition.material_to_priority is True

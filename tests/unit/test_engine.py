from ai_adoption_engine.decision.engine import AssessmentEngine
from ai_adoption_engine.models.enums import RecommendationMode
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


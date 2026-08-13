from datetime import timedelta

from ai_adoption_engine.decision_support import DecisionSupportPackageService
from ai_adoption_engine.models.decision_support import (
    CapabilityUseStatus,
    DecisionPackageFailure,
    DecisionPackageFailureCode,
    DecisionPackageSuccess,
    HumanRoleType,
    InterventionType,
    PackageCompleteness,
    RoadmapStageType,
    RoadmapStatus,
)
from ai_adoption_engine.models.enums import (
    CriterionName,
    GateName,
    GateStatus,
    KnowledgeState,
    PriorityStatus,
    RecommendationMode,
)
from ai_adoption_engine.models.review import InformationOrigin
from tests.fakes.decision_support import sample_integrated_assessment


def _package():
    result = DecisionSupportPackageService().generate(sample_integrated_assessment())
    assert isinstance(result, DecisionPackageSuccess)
    return result.package


def _single_step_integrated(index: int):
    integrated = sample_integrated_assessment().model_copy(deep=True)
    assessment = integrated.process_assessment.step_assessments[index]
    trace = integrated.step_traceability[index]
    integrated.process_assessment.step_assessments = [assessment]
    return integrated.model_copy(update={"step_traceability": [trace]})


def test_portfolio_retains_every_assessment_exactly_once_and_unchanged() -> None:
    integrated = sample_integrated_assessment()
    result = DecisionSupportPackageService().generate(integrated)
    assert isinstance(result, DecisionPackageSuccess)
    items = result.package.portfolio.items
    assert [item.step_id for item in items] == [
        item.step_id for item in integrated.process_assessment.step_assessments
    ]
    for item, assessed in zip(
        items, integrated.process_assessment.step_assessments, strict=True
    ):
        assert item.recommendation_mode is assessed.recommendation_mode
        assert item.capabilities == assessed.capabilities
        assert item.gate_results == assessed.gate_results
        assert item.priority == assessed.priority
        assert item.priority_status is assessed.priority_status
        assert item.rationale == assessed.reasoning


def test_all_four_modes_have_the_approved_future_state_mapping() -> None:
    package = _package()
    by_mode = {
        item.recommendation_mode: item for item in package.future_state.steps
    }
    assert by_mode[RecommendationMode.AUTOMATE].intervention_type is (
        InterventionType.AI_ENABLED_EXECUTION
    )
    assert by_mode[RecommendationMode.AUGMENT].intervention_type is (
        InterventionType.AI_ASSISTED_HUMAN_EXECUTION
    )
    assert by_mode[RecommendationMode.INVESTIGATE_FURTHER].intervention_type is (
        InterventionType.CURRENT_STEP_WITH_INVESTIGATION_MARKER
    )
    for item in package.future_state.steps:
        if item.recommendation_mode is RecommendationMode.DO_NOT_RECOMMEND:
            assert item.intervention_type is (
                InterventionType.CURRENT_OR_CONVENTIONAL_EXECUTION
            )
            assert item.capability_use_status is CapabilityUseStatus.NOT_APPLIED
            assert "No AI intervention" in item.controls_and_constraints[-1]


def test_capabilities_remain_separate_from_intervention_pattern() -> None:
    package = _package()
    automated = next(
        item
        for item in package.future_state.steps
        if item.recommendation_mode is RecommendationMode.AUTOMATE
    )
    source = next(
        item for item in package.portfolio.items if item.step_id == automated.source_step_id
    )
    assert automated.capabilities == source.capabilities
    assert automated.capability_use_status is CapabilityUseStatus.PROPOSED
    assert automated.intervention_type.value not in {
        capability.value for capability in automated.capabilities
    }


def test_augment_and_automate_retain_functional_human_controls() -> None:
    package = _package()
    roles_by_mode = {
        item.recommendation_mode: {role.role_type for role in item.human_roles}
        for item in package.future_state.steps
    }
    assert HumanRoleType.EXCEPTION_HANDLER in roles_by_mode[
        RecommendationMode.AUTOMATE
    ]
    assert HumanRoleType.PRIMARY_OPERATOR in roles_by_mode[
        RecommendationMode.AUGMENT
    ]
    assert HumanRoleType.REVIEWER in roles_by_mode[RecommendationMode.AUGMENT]
    assert all(
        role.confirmation_status.value == "NEEDS_CONFIRMATION"
        for item in package.future_state.steps
        for role in item.human_roles
    )


def test_roadmaps_include_stop_decisions_and_respect_negative_modes() -> None:
    package = _package()
    for item in package.roadmap.opportunities:
        if item.recommendation_mode in {
            RecommendationMode.AUTOMATE,
            RecommendationMode.AUGMENT,
        }:
            decisions = [stage for stage in item.stages if stage.decision_point]
            assert len(decisions) == 2
            assert all("STOP" in stage.possible_outcomes for stage in decisions)
            assert item.status is RoadmapStatus.QUALIFYING_OPPORTUNITY
        elif item.recommendation_mode is RecommendationMode.INVESTIGATE_FURTHER:
            assert item.status is RoadmapStatus.INVESTIGATION_ONLY
            assert RoadmapStageType.PROOF_OF_CONCEPT not in {
                stage.stage_type for stage in item.stages
            }
            assert item.stages[-1].possible_outcomes == ["GO", "REVISE", "STOP"]
        else:
            assert item.status is RoadmapStatus.AI_DEPLOYMENT_NOT_APPLICABLE
            assert item.stages == []


def test_inference_alone_does_not_make_package_incomplete() -> None:
    integrated = _single_step_integrated(1)
    inferred = next(
        item
        for item in integrated.process_assessment.step_assessments[0].criteria
        if item.knowledge_state is KnowledgeState.INFERRED
    )
    assert inferred.material_to_recommendation is False
    assert inferred.material_to_priority is False
    result = DecisionSupportPackageService().generate(integrated)
    assert isinstance(result, DecisionPackageSuccess)
    assert result.package.completeness is PackageCompleteness.COMPLETE
    trace = next(
        item
        for item in result.package.portfolio.items[0].source_traceability.criteria
        if item.knowledge_state is KnowledgeState.INFERRED
    )
    assert trace.origin is InformationOrigin.MODEL_INFERRED


def test_incomplete_priority_remains_visible_and_marks_package_incomplete() -> None:
    integrated = _single_step_integrated(0)
    step = integrated.process_assessment.step_assessments[0]
    step.priority = None
    step.priority_status = PriorityStatus.INCOMPLETE
    step.priority_missing_criteria = [CriterionName.REPETITION]
    result = DecisionSupportPackageService().generate(integrated)
    assert isinstance(result, DecisionPackageSuccess)
    assert result.package.completeness is (
        PackageCompleteness.COMPLETE_WITH_INFORMATION_GAPS
    )
    item = result.package.portfolio.items[0]
    assert item.priority is None
    assert item.priority_status is PriorityStatus.INCOMPLETE
    assert any(gap.field_name == "priority" for gap in item.missing_information)


def test_human_supplied_and_document_provenance_remain_distinct() -> None:
    integrated = _single_step_integrated(1)
    assessed = integrated.process_assessment.step_assessments[0]
    trace = integrated.step_traceability[0]
    index = next(
        index
        for index, item in enumerate(assessed.criteria)
        if item.criterion.value == "implementation_complexity"
    )
    assessed.criteria[index].knowledge_state = KnowledgeState.KNOWN
    assessed.criteria[index].evidence_ids = []
    assessed.criteria[index].confidence = None
    criteria = list(trace.criteria)
    criteria[index] = criteria[index].model_copy(
        update={
            "knowledge_state": KnowledgeState.KNOWN,
            "origin": InformationOrigin.HUMAN_SUPPLIED,
            "evidence": [],
        }
    )
    integrated = integrated.model_copy(
        update={
            "step_traceability": [trace.model_copy(update={"criteria": criteria})]
        }
    )
    result = DecisionSupportPackageService().generate(integrated)
    assert isinstance(result, DecisionPackageSuccess)
    source_trace = result.package.portfolio.items[0].source_traceability
    assert source_trace.activity.origin is InformationOrigin.DOCUMENT_SUPPORTED
    assert source_trace.activity.evidence
    assert source_trace.criteria[index].origin is InformationOrigin.HUMAN_SUPPLIED
    assert source_trace.criteria[index].evidence == []


def test_future_state_rule_conflict_fails_instead_of_overriding_risk() -> None:
    integrated = sample_integrated_assessment().model_copy(deep=True)
    automate = next(
        item
        for item in integrated.process_assessment.step_assessments
        if item.recommendation_mode is RecommendationMode.AUTOMATE
    )
    risk = next(
        item for item in automate.gate_results if item.gate is GateName.RISK_AND_AUTONOMY
    )
    risk.status = GateStatus.FAILED
    result = DecisionSupportPackageService().generate(integrated)
    assert isinstance(result, DecisionPackageFailure)
    assert result.errors[0].code is (
        DecisionPackageFailureCode.FUTURE_STATE_RULE_CONFLICT
    )


def test_roi_disclosure_methodology_fingerprints_and_report_sections_are_mandatory() -> None:
    package = _package()
    assert package.roi_statement == (
        "ROI / quantified benefit unavailable with current evidence."
    )
    assert package.methodology.policy_is_provisional is True
    assert package.methodology.academically_validated is False
    assert package.methodology.proposed_future_state_deployed is False
    assert len(package.methodology.disclosure_statements) == 4
    assert package.source.lineage.validated_process_fingerprint
    assert package.source.policy.decision_policy_fingerprint
    assert len(package.report_content.sections) == 13


def test_current_state_is_referenced_separately_and_never_overwritten() -> None:
    package = _package()
    assert package.current_state.process_id == package.future_state.current_state_process_id
    assert package.current_state.ordered_step_ids == [
        item.source_step_id for item in package.future_state.steps
    ]
    assert all(
        item.current_activity == portfolio.current_activity
        for item, portfolio in zip(
            package.future_state.steps, package.portfolio.items, strict=True
        )
    )
    assert package.future_state.status.value == "PROPOSED / NOT DEPLOYED"


def test_deterministic_semantic_content_ignores_phase5_run_metadata() -> None:
    first = sample_integrated_assessment()
    second = sample_integrated_assessment().model_copy(deep=True)
    second = second.model_copy(
        update={
            "metadata": second.metadata.model_copy(
                update={
                    "assessment_run_id": "another-assessment-run",
                    "assessed_at": second.metadata.assessed_at + timedelta(days=1),
                }
            )
        }
    )
    first_result = DecisionSupportPackageService().generate(first)
    second_result = DecisionSupportPackageService().generate(second)
    assert isinstance(first_result, DecisionPackageSuccess)
    assert isinstance(second_result, DecisionPackageSuccess)
    assert first_result.package.package_id == second_result.package.package_id
    assert first_result.package.portfolio == second_result.package.portfolio
    assert first_result.package.future_state == second_result.package.future_state
    assert first_result.package.roadmap == second_result.package.roadmap


def test_non_success_input_is_a_generation_failure() -> None:
    result = DecisionSupportPackageService().generate({})  # type: ignore[arg-type]
    assert isinstance(result, DecisionPackageFailure)
    assert result.errors[0].code is (
        DecisionPackageFailureCode.INTEGRATED_SUCCESS_REQUIRED
    )

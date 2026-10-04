from ai_adoption_engine.models.preliminary_assessment_v0_2 import (
    ActivityResultType,
    PreliminaryEvaluationFailureV2,
    PreliminaryEvaluationSuccessV2,
)
from ai_adoption_engine.models.preliminary_evaluation import PreliminaryEvaluationSuccess
from ai_adoption_engine.preliminary.dispatch import (
    PRELIMINARY_EVALUATOR_V0_2_ID,
    UnsupportedPreliminaryEvaluatorVersion,
    evaluate_preliminary,
)
from ai_adoption_engine.preliminary.evaluator_v0_2 import PreliminaryAssessmentEvaluatorV2
from ai_adoption_engine.preliminary.evaluator_v0_2 import _conventional_sufficiency
from ai_adoption_engine.preliminary.rules import PRELIMINARY_EVALUATOR_RULES_V0_1
from tests.fakes.preliminary_v2 import approved_review_for
import pytest


def _evaluate(*sentences):
    result = PreliminaryAssessmentEvaluatorV2().evaluate(approved_review_for(*sentences))
    assert isinstance(result, PreliminaryEvaluationSuccessV2)
    return result.assessment


def test_direct_recording_has_errata_default_output_and_stable_ids() -> None:
    review = approved_review_for("The officer records the complaint.")
    first = PreliminaryAssessmentEvaluatorV2().evaluate(review)
    second = PreliminaryAssessmentEvaluatorV2().evaluate(review)
    assert isinstance(first, PreliminaryEvaluationSuccessV2)
    assert isinstance(second, PreliminaryEvaluationSuccessV2)
    component = first.assessment.activity_results[0].components[0]
    assert component.normalized_output_artifact == "RECORDED_FORM:complaint"
    assert component.rule_derived_inference_id.startswith("pri2-")
    assert component.component_id.startswith("pac2-")
    assert first.assessment.canonical_json_bytes() == second.assessment.canonical_json_bytes()


def test_atomic_actions_dependencies_work_needs_and_opportunity_grouping() -> None:
    assessment = _evaluate("The officer records the complaint to create the complaint record, then notifies staff of the complaint record.")
    activity = assessment.activity_results[0]
    assert [item.pd2_rule_code for item in activity.components] == ["PD2-001", "PD2-003"]
    assert activity.components[1].dependency_component_ids == (activity.components[0].component_id,)
    assert all(item.work_need_id.startswith("pwn2-") for item in activity.work_needs)
    assert len(activity.opportunities) == 1
    assert activity.opportunities[0].construction_code == "POG2-003"


def test_exact_worked_example_one() -> None:
    activity = _evaluate(
        "The officer records the complaint to create the complaint record, then notifies any staff complained about of the complaint record."
    ).activity_results[0]
    assert [item.pd2_rule_code for item in activity.components] == ["PD2-001", "PD2-003"]
    assert len(activity.opportunities) == 1
    assert activity.opportunities[0].deciding_rule_code == "PA2-040"


def test_semantic_support_and_accountable_approval_remain_independent() -> None:
    assessment = _evaluate(
        "The case officer reads the complaint to identify the points raised.",
        "Using the points raised, the case officer investigates the evidence to establish findings.",
        "Using the findings, the case officer drafts the final response.",
        "The complaints officer approves the final response.",
    )
    codes = [item.deciding_rule_code for activity in assessment.activity_results for item in activity.opportunities]
    assert codes == ["PA2-051", "PA2-051", "PA2-051", "PA2-020"]
    assert assessment.low_activity_count == 3
    assert assessment.medium_activity_count == 1


def test_exact_worked_example_two_groups_semantic_chain_beside_approval() -> None:
    activity = _evaluate(
        "The case officer reads the complaint and supporting material to identify the points raised. "
        "Using the points raised, the case officer investigates the evidence to establish findings. "
        "Using the findings, the case officer drafts the final response. "
        "The complaints officer approves the final response."
    ).activity_results[0]
    assert [item.pd2_rule_code for item in activity.components] == [
        "PD2-008", "PD2-009", "PD2-013", "PD2-016"
    ]
    assert [item.deciding_rule_code for item in activity.opportunities] == ["PA2-051", "PA2-020"]
    assert len(activity.opportunities[0].component_ids) == 3


def test_scoped_discovery_coexists_with_supported_recording() -> None:
    assessment = _evaluate("The officer records the complaint and handles any special follow-up appropriately.")
    activity = assessment.activity_results[0]
    assert activity.result_type is ActivityResultType.ACTIONABLE
    assert activity.opportunities[0].deciding_rule_code == "PA2-040"
    assert activity.scoped_discoveries[0].discovery_reason_code == "UNSUPPORTED_CHARACTERISTIC"


def test_no_admissible_characteristic_returns_discovery_not_failure() -> None:
    assessment = _evaluate("The officer handles the complaint appropriately.")
    activity = assessment.activity_results[0]
    assert activity.result_type is ActivityResultType.DISCOVERY_REQUIRED
    assert activity.deciding_rule_code == "PA2-002"


def test_more_than_five_opportunities_returns_valid_overflow_discovery() -> None:
    sentence = (
        "The officer records item one. The manager updates item two. The analyst routes item three to team three. "
        "The clerk schedules item four. The reviewer notifies team five of item five. The agent copies item six to produce output six."
    )
    assessment = _evaluate(sentence)
    activity = assessment.activity_results[0]
    assert activity.result_type is ActivityResultType.DISCOVERY_REQUIRED
    assert activity.deciding_rule_code == "PA2-004"
    assert len(activity.candidate_partition_trace) == 6
    assert activity.scoped_discoveries[0].discovery_reason_code == "OPPORTUNITY_PARTITION_EXCEEDS_LIMIT"


def test_corrupt_source_lineage_is_typed_failure_without_partial_output() -> None:
    review = approved_review_for("The officer records the complaint.").model_copy(deep=True)
    review.review.steps[0].activity.evidence[0].exact_snippet = "altered"
    result = PreliminaryAssessmentEvaluatorV2().evaluate(review)
    assert isinstance(result, PreliminaryEvaluationFailureV2)
    assert result.assessment is None


def test_explicit_dispatch_and_unchanged_v0_1_default() -> None:
    review = approved_review_for("The officer records the complaint.")
    default = evaluate_preliminary(review)
    successor = evaluate_preliminary(review, evaluator_id=PRELIMINARY_EVALUATOR_V0_2_ID)
    assert isinstance(default, PreliminaryEvaluationSuccess)
    assert isinstance(successor, PreliminaryEvaluationSuccessV2)
    assert default.assessment.schema_version == "preliminary-assessment.v0.1"
    assert PRELIMINARY_EVALUATOR_RULES_V0_1.fingerprint() == "3db8a54561bcfe263a5483e5d4c49e203bfac40eafbc8bc778cf773ed6ad1790"


def test_unknown_dispatch_fails_closed() -> None:
    try:
        evaluate_preliminary(approved_review_for("The officer records the complaint."), evaluator_id="preliminary-evaluator.v9")
    except UnsupportedPreliminaryEvaluatorVersion:
        pass
    else:
        raise AssertionError("Unsupported evaluator identity must fail closed")


def test_v0_2_modules_have_no_formal_four_gate_dependency() -> None:
    import inspect
    import ai_adoption_engine.preliminary.evaluator_v0_2 as module
    source = inspect.getsource(module)
    assert "FourGateAssessmentEngine" not in source
    assert "OutcomeCode" not in source
    assert "DecisionSupportPackage" not in source


@pytest.mark.parametrize(
    ("source", "rule", "code"),
    [
        ("The officer records the complaint.", "PD2-001", "PA2-040"),
        ("The officer updates the complaint record.", "PD2-002", "PA2-040"),
        ("The officer notifies staff of the complaint.", "PD2-003", "PA2-040"),
        ("The officer transfers the complaint to the team.", "PD2-004", "PA2-040"),
        ("The officer schedules the hearing.", "PD2-005", "PA2-040"),
        ("Every day, the officer monitors case status, then notifies the manager of case status.", "PD2-006", "PA2-040"),
        ("The officer converts the form to produce the digital record.", "PD2-007", "PA2-041"),
        ("The officer reads the complaint to identify the issue.", "PD2-008", "PA2-051"),
        ("The officer investigates the complaint to establish findings.", "PD2-009", "PA2-051"),
        ("The officer determines the category of the complaint as Stage 1 or Stage 2.", "PD2-010", "PA2-051"),
        ("The officer retrieves the policy register.", "PD2-011", "PA2-051"),
        ("The officer compares the options to produce the ranking.", "PD2-012", "PA2-051"),
        ("The officer drafts the response.", "PD2-013", "PA2-051"),
        ("The officer predicts the demand to produce the forecast.", "PD2-014", "PA2-051"),
        ("The officer meets the complainant to produce agreed points.", "PD2-015", "PA2-021"),
        ("The officer approves the final response.", "PD2-016", "PA2-020"),
        ("Using the facts, the officer weighs exceptional circumstances to determine treatment.", "PD2-017", "PA2-021"),
        ("The officer reworks the complaint to produce the corrected record.", "PD2-018", "PA2-030"),
        ("The officer delays the complaint to produce the queued state.", "PD2-019", "PA2-030"),
    ],
)
def test_complete_pd2_to_pa2_default_mapping(source, rule, code) -> None:
    activity = _evaluate(source).activity_results[0]
    component = next(item for item in activity.components if item.pd2_rule_code == rule)
    opportunity = next(item for item in activity.opportunities if component.component_id in item.component_ids)
    assert opportunity.deciding_rule_code == code


def test_deterministic_categorisation_and_lookup_use_pa2_040() -> None:
    categorise = _evaluate(
        "A fixed mapping applies. The officer determines the category of the complaint as Stage 1 or Stage 2."
    ).activity_results[0]
    lookup = _evaluate(
        "An exact lookup applies. The officer retrieves the policy register."
    ).activity_results[0]
    assert categorise.opportunities[0].deciding_rule_code == "PA2-040"
    assert lookup.opportunities[0].deciding_rule_code == "PA2-040"


def test_assistance_veto_and_high_risk_precedence() -> None:
    veto = _evaluate(
        "AI assistance is prohibited. The officer reads the complaint to identify the issue."
    ).activity_results[0]
    assert veto.opportunities[0].deciding_rule_code == "PA2-020"
    high_risk = _evaluate(
        "Residual risk = 5. The officer reads the complaint to identify the issue."
    ).activity_results[0]
    assert high_risk.result_type is ActivityResultType.DISCOVERY_REQUIRED
    assert high_risk.deciding_rule_code == "PA2-004"


def test_resolved_assistance_and_positive_autonomy_governance() -> None:
    assistance = _evaluate(
        "Assistance scope defined; residual risk with mandatory human review = 2; assistance error consequence = 2; "
        "mandatory human review; human reviewer: team lead; accountability owner: director; escalation route: panel; "
        "assistance explicitly permitted; safety resolved; legal resolved; privacy resolved; regulatory resolved. "
        "The officer reads the complaint to identify the issue."
    ).activity_results[0]
    assert assistance.opportunities[0].deciding_rule_code == "PA2-050"
    autonomy = _evaluate(
        "Predictability = 4; required data available; data suitable; data quality acceptable; autonomous residual risk = 2; "
        "autonomous error consequence = 2; no material human judgment; no mandatory human decision; no mandatory human review; "
        "accountability owner: director; escalation route: panel; autonomous operation explicitly permitted; safety resolved; "
        "legal resolved; privacy resolved; regulatory resolved. The officer reads the complaint to identify the issue."
    ).activity_results[0]
    assert autonomy.opportunities[0].deciding_rule_code == "PA2-052"


def test_affirmative_documentary_no_change() -> None:
    activity = _evaluate(
        "Current purpose is explicit; purpose is being achieved; performance is acceptable; controls are acceptable; "
        "no material process problem exists; no intervention is needed."
    ).activity_results[0]
    assert activity.result_type is ActivityResultType.NO_CHANGE
    assert activity.deciding_rule_code == "PA2-010"


def test_exactly_five_opportunities_remain_actionable() -> None:
    activity = _evaluate(
        "The officer records item one. The manager updates item two. The analyst routes item three to team three. "
        "The clerk schedules item four. The reviewer notifies team five of item five."
    ).activity_results[0]
    assert activity.result_type is ActivityResultType.ACTIONABLE
    assert len(activity.opportunities) == 5


def test_corrected_worked_example_three() -> None:
    activity = _evaluate(
        "The officer reads the complaint to identify the complaint issue. "
        "Using the complaint issue, the officer determines the category of the complaint as Stage 1 or Stage 2. "
        "Using the complaint category, the officer records the category. "
        "Using the recorded complaint category, the officer routes the complaint to the relevant team."
    ).activity_results[0]
    assert [item.pd2_rule_code for item in activity.components] == [
        "PD2-008", "PD2-010", "PD2-001", "PD2-004"
    ]
    assert [item.deciding_rule_code for item in activity.opportunities] == ["PA2-051", "PA2-040"]
    assert activity.components[1].normalized_object == "complaint"
    assert activity.components[1].normalized_output_artifact == "complaint category"
    assert activity.components[3].dependency_component_ids == (activity.components[2].component_id,)


def test_worked_example_four_has_four_independent_opportunities() -> None:
    activity = _evaluate(
        "The officer meets the complainant to produce agreed points. "
        "Using the agreed points, the officer weighs exceptional circumstances to determine the exception treatment. "
        "Using the exception treatment, the officer makes the final determination and signs the final determination. "
        "Using the final determination, the officer records the final determination in the complaints register."
    ).activity_results[0]
    assert [item.pd2_rule_code for item in activity.components] == [
        "PD2-015", "PD2-017", "PD2-016", "PD2-016", "PD2-001"
    ]
    assert [item.deciding_rule_code for item in activity.opportunities] == [
        "PA2-021", "PA2-021", "PA2-020", "PA2-040"
    ]


def test_content_ids_change_with_material_content_not_repeat_runs() -> None:
    one = _evaluate("The officer records the complaint.")
    repeat = _evaluate("The officer records the complaint.")
    changed = _evaluate("The officer records the request.")
    assert one.preliminary_assessment_id == repeat.preliminary_assessment_id
    assert one.activity_results[0].components[0].component_id == repeat.activity_results[0].components[0].component_id
    assert one.activity_results[0].opportunities[0].opportunity_id == repeat.activity_results[0].opportunities[0].opportunity_id
    assert one.preliminary_assessment_id != changed.preliminary_assessment_id
    assert one.activity_results[0].components[0].component_id != changed.activity_results[0].components[0].component_id


def test_cs1_to_cs7_each_fail_closed() -> None:
    base = _evaluate("The officer records the complaint.").activity_results[0].components[0]
    assert _conventional_sufficiency(base)
    assert not _conventional_sufficiency(
        base.model_copy(update={"normalized_object": None, "normalized_input_artifact": None})
    )  # CS1
    assert not _conventional_sufficiency(
        base.model_copy(update={"component_action": "INTERPRET", "pd2_rule_code": "PD2-008"})
    )  # CS2 / CS4
    assert not _conventional_sufficiency(
        base.model_copy(update={"normalized_object": None, "normalized_output_artifact": None})
    )  # CS3 / CS7
    unresolved = _evaluate(
        "Using the unresolved semantic finding, the officer records the complaint."
    ).activity_results[0].components[0]
    assert not _conventional_sufficiency(unresolved)  # CS5
    exception = _evaluate(
        "The officer records the complaint as appropriate."
    ).activity_results[0].components[0]
    assert not _conventional_sufficiency(exception)  # CS6


def test_high_medium_and_low_coverage_and_process_weakest_aggregation() -> None:
    high = _evaluate(
        "Current purpose is explicit; purpose is being achieved; performance is acceptable; controls are acceptable; "
        "no material process problem exists; no intervention is needed."
    )
    medium = _evaluate("The officer records the complaint.")
    low = _evaluate(
        "The officer records the complaint to create the complaint record, then notifies staff of the complaint record."
    )
    assert high.evidence_coverage.value == "HIGH"
    assert medium.evidence_coverage.value == "MEDIUM"
    assert low.evidence_coverage.value == "LOW"
    mixed = _evaluate(
        "The officer records the complaint.",
        "The officer reads the complaint to identify the issue.",
    )
    assert mixed.evidence_coverage.value == "LOW"
    assert mixed.medium_activity_count == 1
    assert mixed.low_activity_count == 1

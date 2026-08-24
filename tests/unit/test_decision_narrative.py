"""Unit tests for the read-only business decision narrative projection.

These tests protect the Stage 2 contract in
``docs/portfolio-v1-decision-experience-design-v0.1.md``: every Layer 1 sentence
restates structured fields, nothing is invented, and UNKNOWN never becomes a
negative factual claim.
"""

from __future__ import annotations

from ai_adoption_engine.models.assessment import (
    AccountabilityAssessment,
    CriterionAssessment,
    GateResult,
    StepAssessment,
)
from ai_adoption_engine.models.decision_support import InformationGapKind
from ai_adoption_engine.models.enums import (
    Capability,
    CriterionName,
    GateName,
    GateStatus,
    KnowledgeState,
    PriorityStatus,
    RecommendationMode,
)
from ai_adoption_engine.presentation.decision_narrative import (
    NO_AUTHORISATION,
    ROI_LIMITATION,
    build_activity_narrative,
    build_package_narrative,
    build_process_narrative,
    gap_business_statement,
    portfolio_reason_statement,
)
from ai_adoption_engine.decision_support import DecisionSupportPackageService
from tests.fakes.decision_support import sample_integrated_assessment


# ---------------------------------------------------------------------------
# Controlled fixtures
# ---------------------------------------------------------------------------


def _criterion(
    name: CriterionName,
    state: KnowledgeState,
    *,
    value: int | None = None,
    recommendation: bool = False,
    priority: bool = False,
) -> CriterionAssessment:
    return CriterionAssessment(
        criterion=name,
        value=value,
        knowledge_state=state,
        rationale="Synthetic fixture rationale.",
        evidence_ids=[],
        confidence=None,
        material_to_recommendation=recommendation,
        material_to_priority=priority,
        material_at_gates=[],
    )


def _accountability(state: KnowledgeState = KnowledgeState.KNOWN) -> AccountabilityAssessment:
    return AccountabilityAssessment(
        value=None if state is KnowledgeState.UNKNOWN else False,
        knowledge_state=state,
        rationale="Synthetic fixture rationale.",
        evidence_ids=[],
        confidence=None,
        material_to_recommendation=False,
        material_at_gates=[],
    )


def _step(
    *,
    recommendation: RecommendationMode,
    criteria: list[CriterionAssessment],
    gate_results: list[GateResult],
    priority_status: PriorityStatus = PriorityStatus.NOT_APPLICABLE,
    priority_missing: list[CriterionName] | None = None,
    accountability: AccountabilityAssessment | None = None,
) -> StepAssessment:
    return StepAssessment(
        step_id="step-fixture-1",
        activity="Assess a synthetic activity",
        recommendation_mode=recommendation,
        capabilities=[Capability.CLASSIFICATION],
        criteria=criteria,
        human_accountability=accountability or _accountability(),
        gate_results=gate_results,
        priority=None,
        priority_status=priority_status,
        priority_missing_criteria=priority_missing or [],
        reasoning=["Synthetic fixture reasoning."],
        evidence=[],
    )


def _gate(
    gate: GateName,
    status: GateStatus,
    *,
    material: list[CriterionName] | None = None,
    rationale: str = "Synthetic fixture rationale.",
) -> GateResult:
    return GateResult(
        gate=gate,
        status=status,
        rationale=rationale,
        evidence_ids=[],
        material_criteria=material or [],
        accountability_material=False,
    )


def _activity(narrative, name: str):
    return next(item for item in narrative.activities if item.activity == name)


# ---------------------------------------------------------------------------
# A. INVESTIGATE_FURTHER caused by missing evidence
# ---------------------------------------------------------------------------


def test_investigate_further_names_only_the_unestablished_criterion() -> None:
    narrative = build_process_narrative(sample_integrated_assessment())
    activity = _activity(narrative, "Identify customers at risk of churn")

    assert activity.recommendation == RecommendationMode.INVESTIGATE_FURTHER.value
    assert activity.outcome_statement == (
        "More information is needed before an AI adoption recommendation can be "
        "made for this activity."
    )
    assert activity.reason_statement == (
        "The Technical fit check could not be completed because the available "
        "evidence does not establish whether the data this activity relies on is "
        "ready for AI use."
    )
    assert [item.field_name for item in activity.missing_facts] == ["data_readiness"]
    assert activity.missing_facts[0].statement == (
        "Data readiness: the available evidence does not establish whether the "
        "data this activity relies on is ready for AI use."
    )
    assert activity.missing_facts[0].affects_recommendation is True


def test_unknown_criterion_is_never_turned_into_a_negative_factual_claim() -> None:
    step = _step(
        recommendation=RecommendationMode.INVESTIGATE_FURTHER,
        criteria=[
            _criterion(
                CriterionName.DATA_READINESS,
                KnowledgeState.UNKNOWN,
                recommendation=True,
            )
        ],
        gate_results=[
            _gate(GateName.EVIDENCE_SUFFICIENCY, GateStatus.PASSED),
            _gate(
                GateName.TECHNICAL_FIT,
                GateStatus.FAILED,
                material=[CriterionName.DATA_READINESS],
            ),
            _gate(GateName.BUSINESS_VALUE, GateStatus.NOT_EVALUATED),
            _gate(GateName.RISK_AND_AUTONOMY, GateStatus.NOT_EVALUATED),
        ],
    )

    text = " ".join(build_activity_narrative(step).business_lines()).lower()

    for claim in (
        "data is poor",
        "poor data",
        "data is not ready",
        "not ready for ai",
        "unsuitable",
        "inadequate",
        "insufficient data",
        "failed",
    ):
        assert claim not in text


# ---------------------------------------------------------------------------
# B. Recommendation supported
# ---------------------------------------------------------------------------


def test_supported_recommendation_does_not_imply_deployment_approval() -> None:
    narrative = build_process_narrative(sample_integrated_assessment())
    automate = _activity(narrative, "Capture and categorise complaint details")
    augment = _activity(narrative, "Prepare the customer response")

    assert automate.recommendation == RecommendationMode.AUTOMATE.value
    assert automate.outcome_statement == (
        "The current evidence supports considering a defined automation "
        "opportunity for this activity."
    )
    assert augment.recommendation == RecommendationMode.AUGMENT.value
    assert "human responsibility retained" in augment.outcome_statement
    assert augment.reason_statement == (
        "The Risk and autonomy check passed with conditions, so material human "
        "involvement is expected to remain."
    )
    assert (
        "A supported recommendation means the recorded evidence met the "
        "assessment's checks. It is not approval to deploy or implement anything."
    ) in narrative.what_this_means


# ---------------------------------------------------------------------------
# C. Do-not-recommend outcome
# ---------------------------------------------------------------------------


def test_do_not_recommend_is_bounded_to_the_current_evidence() -> None:
    narrative = build_process_narrative(sample_integrated_assessment())
    activity = _activity(narrative, "Approve regulated compensation or redress")

    assert activity.outcome_statement == (
        "AI adoption is not recommended for this activity on the current evidence."
    )
    assert activity.reason_statement == (
        "The Risk and autonomy check was not met by the values recorded in the "
        "approved evidence."
    )
    assert activity.next_action == (
        "No further action is required for this activity unless the recorded "
        "evidence changes."
    )
    assert (
        "'Not recommended' reflects the evidence recorded today and can change "
        "if the recorded evidence changes."
    ) in narrative.what_this_means
    text = " ".join(narrative.business_lines()).lower()
    for claim in ("never suitable", "permanently", "cannot ever", "unsuitable for ai"):
        assert claim not in text


# ---------------------------------------------------------------------------
# D. Mixed portfolio
# ---------------------------------------------------------------------------


def test_process_summary_states_the_situation_rather_than_counts() -> None:
    narrative = build_process_narrative(sample_integrated_assessment())

    assert narrative.headline == (
        "This process has a mixed result: some activities have a supported AI "
        "adoption recommendation, and others need more information before one "
        "can be made."
    )
    assert not any(character.isdigit() for character in narrative.headline)
    assert narrative.what_we_found == (
        "Recommendation supported on the current evidence: Capture and categorise "
        "complaint details and Prepare the customer response.",
        "More information needed first: Identify customers at risk of churn.",
        "Not recommended on the current evidence: Route the case to the "
        "responsible queue and Approve regulated compensation or redress.",
    )
    # Counts remain available as supporting data only.
    assert dict(narrative.outcome_counts) == {
        "AUTOMATE": 1,
        "AUGMENT": 1,
        "INVESTIGATE_FURTHER": 1,
        "DO_NOT_RECOMMEND": 2,
    }


def test_headline_distinguishes_every_process_level_situation() -> None:
    integrated = sample_integrated_assessment()
    steps = integrated.process_assessment.step_assessments

    def headline_for(modes: list[RecommendationMode]) -> str:
        rebuilt = [
            step.model_copy(update={"recommendation_mode": mode})
            for step, mode in zip(steps, modes, strict=True)
        ]
        assessment = integrated.process_assessment.model_copy(
            update={"step_assessments": rebuilt}
        )
        return build_process_narrative(
            integrated.model_copy(update={"process_assessment": assessment})
        ).headline

    investigate = RecommendationMode.INVESTIGATE_FURTHER
    automate = RecommendationMode.AUTOMATE
    refuse = RecommendationMode.DO_NOT_RECOMMEND

    assert headline_for([investigate] * 5).startswith(
        "No AI adoption recommendation can be made for this process yet."
    )
    assert headline_for([refuse] * 5).startswith(
        "AI adoption is not recommended for any assessed activity"
    )
    assert headline_for([automate] * 5).startswith(
        "Every assessed activity has a supported AI adoption recommendation"
    )
    assert headline_for([automate, automate, refuse, refuse, refuse]).startswith(
        "Some activities have a supported AI adoption recommendation"
    )
    assert headline_for([investigate, investigate, refuse, refuse, refuse]).startswith(
        "No activity has a supported AI adoption recommendation."
    )


# ---------------------------------------------------------------------------
# E. NOT_EVALUATED gates
# ---------------------------------------------------------------------------


def test_not_evaluated_gates_are_not_described_as_failure_or_inability() -> None:
    narrative = build_process_narrative(sample_integrated_assessment())
    activity = _activity(narrative, "Route the case to the responsible queue")

    unreached = [item for item in activity.gates if not item.was_reached]
    assert [item.gate for item in unreached] == ["business_value", "risk_and_autonomy"]
    for gate in unreached:
        assert gate.status == "not_evaluated"
        assert gate.status_label == (
            "Not needed — an earlier check already decided the outcome"
        )
        assert "could not" not in gate.status_label.lower()
        assert "unable" not in gate.status_label.lower()
        assert "fail" not in gate.status_label.lower()

    text = " ".join(activity.business_lines()).lower()
    assert "business value" not in text
    assert "could not be evaluated" not in text


# ---------------------------------------------------------------------------
# F. Inferred / unconfirmed evidence
# ---------------------------------------------------------------------------


def test_inferred_material_criterion_is_described_as_an_assumption() -> None:
    narrative = build_process_narrative(sample_integrated_assessment())
    activity = _activity(narrative, "Prepare the customer response")

    assert [item.field_name for item in activity.unconfirmed_facts] == [
        "implementation_complexity"
    ]
    assert activity.unconfirmed_facts[0].statement == (
        "Implementation complexity: this is recorded as an assumption and still "
        "requires confirmation."
    )
    assert activity.unconfirmed_facts[0].knowledge_state == "inferred"

    text = " ".join(narrative.business_lines()).lower()
    for threshold in ("confidence", "threshold", "0.6", "0.60", "minimum"):
        assert threshold not in text


# ---------------------------------------------------------------------------
# G. Priority incomplete
# ---------------------------------------------------------------------------


def test_incomplete_priority_names_exactly_the_recorded_missing_criteria() -> None:
    step = _step(
        recommendation=RecommendationMode.AUGMENT,
        criteria=[
            _criterion(CriterionName.REPETITION, KnowledgeState.UNKNOWN, priority=True),
            _criterion(
                CriterionName.BUSINESS_VALUE, KnowledgeState.KNOWN, value=4
            ),
        ],
        gate_results=[
            _gate(GateName.EVIDENCE_SUFFICIENCY, GateStatus.PASSED),
            _gate(GateName.TECHNICAL_FIT, GateStatus.PASSED),
            _gate(GateName.BUSINESS_VALUE, GateStatus.PASSED),
            _gate(GateName.RISK_AND_AUTONOMY, GateStatus.PASSED_WITH_CONSTRAINTS),
        ],
        priority_status=PriorityStatus.INCOMPLETE,
        priority_missing=[CriterionName.REPETITION],
    )

    narrative = build_activity_narrative(step)

    assert narrative.priority_statement == (
        "A priority score could not be calculated because the available evidence "
        "does not establish: Task repetition."
    )
    text = " ".join(narrative.business_lines())
    for uninvolved in ("Predictability", "Data readiness", "Risk consequence"):
        assert uninvolved not in text


# ---------------------------------------------------------------------------
# H. Determinism
# ---------------------------------------------------------------------------


def test_identical_authoritative_input_produces_identical_narrative() -> None:
    first = build_process_narrative(sample_integrated_assessment())
    second = build_process_narrative(sample_integrated_assessment())

    assert first == second
    assert first.business_lines() == second.business_lines()


# ---------------------------------------------------------------------------
# No-invention safeguards
# ---------------------------------------------------------------------------


def test_a_broad_unknown_criterion_does_not_introduce_sub_gaps() -> None:
    step = _step(
        recommendation=RecommendationMode.INVESTIGATE_FURTHER,
        criteria=[
            _criterion(
                CriterionName.DATA_READINESS,
                KnowledgeState.UNKNOWN,
                recommendation=True,
            )
        ],
        gate_results=[
            _gate(GateName.EVIDENCE_SUFFICIENCY, GateStatus.PASSED),
            _gate(
                GateName.TECHNICAL_FIT,
                GateStatus.FAILED,
                material=[CriterionName.DATA_READINESS],
            ),
            _gate(GateName.BUSINESS_VALUE, GateStatus.NOT_EVALUATED),
            _gate(GateName.RISK_AND_AUTONOMY, GateStatus.NOT_EVALUATED),
        ],
    )

    text = " ".join(build_activity_narrative(step).business_lines()).lower()

    assert "data readiness" in text
    for invented in (
        "data quality",
        "accuracy",
        "exception",
        "completeness",
        "volume",
        "provenance",
        "access",
        "retention",
    ):
        assert invented not in text


def test_only_recorded_missing_facts_are_reported() -> None:
    step = _step(
        recommendation=RecommendationMode.INVESTIGATE_FURTHER,
        criteria=[
            _criterion(
                CriterionName.AI_CAPABILITY_FIT,
                KnowledgeState.UNKNOWN,
                recommendation=True,
            ),
            _criterion(CriterionName.DATA_READINESS, KnowledgeState.KNOWN, value=3),
            _criterion(CriterionName.BUSINESS_VALUE, KnowledgeState.KNOWN, value=4),
        ],
        gate_results=[
            _gate(GateName.EVIDENCE_SUFFICIENCY, GateStatus.PASSED),
            _gate(
                GateName.TECHNICAL_FIT,
                GateStatus.FAILED,
                material=[CriterionName.AI_CAPABILITY_FIT],
            ),
            _gate(GateName.BUSINESS_VALUE, GateStatus.NOT_EVALUATED),
            _gate(GateName.RISK_AND_AUTONOMY, GateStatus.NOT_EVALUATED),
        ],
    )

    narrative = build_activity_narrative(step)

    assert [item.field_name for item in narrative.missing_facts] == ["ai_capability_fit"]
    assert "Data readiness" not in " ".join(narrative.business_lines())


def test_unknown_accountability_is_reported_from_its_own_field() -> None:
    step = _step(
        recommendation=RecommendationMode.INVESTIGATE_FURTHER,
        criteria=[_criterion(CriterionName.DATA_READINESS, KnowledgeState.KNOWN, value=3)],
        gate_results=[
            _gate(GateName.EVIDENCE_SUFFICIENCY, GateStatus.PASSED),
            _gate(GateName.TECHNICAL_FIT, GateStatus.PASSED),
            _gate(GateName.BUSINESS_VALUE, GateStatus.PASSED),
            _gate(GateName.RISK_AND_AUTONOMY, GateStatus.FAILED),
        ],
        accountability=_accountability(KnowledgeState.UNKNOWN),
    )

    narrative = build_activity_narrative(step)

    assert [item.field_name for item in narrative.missing_facts] == [
        "human_accountability_required"
    ]
    assert narrative.missing_facts[0].statement == (
        "Human accountability: the available evidence does not establish whether "
        "a person must remain accountable for this activity."
    )


# ---------------------------------------------------------------------------
# Unsupported-claim safeguards and the two-layer split
# ---------------------------------------------------------------------------


def test_layer_one_carries_no_unsupported_positive_claim() -> None:
    narrative = build_process_narrative(sample_integrated_assessment())
    text = " ".join(narrative.business_lines()).lower()

    for claim in (
        "will improve",
        "will reduce",
        "will increase",
        "proven suitable",
        "proven",
        "safe to deploy",
        "ready for deployment",
        "deployment ready",
        "guaranteed automation",
        "improved the decision",
        "best practice",
        "recommended for deployment",
    ):
        assert claim not in text


def test_limitations_are_stated_and_roi_is_not_a_forbidden_word() -> None:
    narrative = build_process_narrative(sample_integrated_assessment())

    assert ROI_LIMITATION in narrative.what_this_means
    assert NO_AUTHORISATION in narrative.next_action
    assert "Return on Investment (ROI)" in " ".join(narrative.business_lines())


def test_engine_rationale_is_kept_verbatim_for_layer_two_only() -> None:
    integrated = sample_integrated_assessment()
    narrative = build_process_narrative(integrated)
    activity = _activity(narrative, "Identify customers at risk of churn")
    source = next(
        step
        for step in integrated.process_assessment.step_assessments
        if step.activity == "Identify customers at risk of churn"
    )

    persisted = {item.rationale for item in source.gate_results}
    assert {item.rationale for item in activity.gates} == persisted

    business = " ".join(activity.business_lines())
    for rationale in persisted:
        assert rationale not in business
    # The raw criterion token only ever appears in the technical layer.
    assert "data_readiness" not in business
    assert activity.deciding_gate is not None
    # The check treats two criteria as material, but only the one the evidence
    # does not establish is named in Layer 1.
    assert activity.deciding_gate.material_criteria == (
        "ai_capability_fit",
        "data_readiness",
    )
    assert [item.field_name for item in activity.missing_facts] == ["data_readiness"]
    assert "ai capability fit" not in activity.reason_statement.lower()


def test_policy_reference_is_technical_and_absent_from_layer_one() -> None:
    integrated = sample_integrated_assessment()
    narrative = build_process_narrative(integrated)

    assert any(
        integrated.policy.policy_id in item for item in narrative.policy_reference
    )
    assert integrated.policy.policy_id not in " ".join(narrative.business_lines())
# ---------------------------------------------------------------------------
# Decision Package projection
# ---------------------------------------------------------------------------


def _package():
    integrated = sample_integrated_assessment()
    generated = DecisionSupportPackageService().generate(integrated)
    assert generated.status == "success"
    return integrated, generated.package


def test_package_narrative_agrees_with_the_assessment_it_came_from() -> None:
    integrated, package = _package()

    package_narrative = build_package_narrative(package)
    process_narrative = build_process_narrative(integrated)

    assert package_narrative.headline == process_narrative.headline
    assert package_narrative.what_this_means == process_narrative.what_this_means
    assert package_narrative.process_name == process_narrative.process_name
    assert package_narrative.why[: len(process_narrative.what_we_found)] == (
        process_narrative.what_we_found
    )


def test_package_limitations_come_from_typed_guarantees_not_prose() -> None:
    _, package = _package()

    narrative = build_package_narrative(package)

    assert narrative.limitations[0] == package.roi_statement
    assert (
        "This package is decision support. It does not approve deployment or "
        "implementation."
    ) in narrative.limitations
    assert (
        "The decision policy used is provisional and is not academically validated."
    ) in narrative.limitations
    assert (
        "This package provides no legal conclusion, no security approval and no "
        "judgement that anything is ready for deployment."
    ) in narrative.limitations
    # The Engine's own disclosure prose is not restated in Layer 1; it stays
    # available verbatim for the technical layer.
    for statement in package.methodology.disclosure_statements:
        assert statement not in narrative.business_lines()


def test_package_narrative_names_only_gaps_with_a_business_phrase() -> None:
    _, package = _package()

    narrative = build_package_narrative(package)
    business = " ".join(narrative.business_lines())

    recorded = {
        gap.field_name
        for item in package.portfolio.items
        for gap in item.missing_information
    }
    # The package records capability-signal, priority and investigation markers
    # that have no business phrase; they must not be paraphrased.
    assert any(name.startswith("synthetic_") for name in recorded)
    for field_name in recorded:
        if field_name.startswith("synthetic_") or field_name in {
            "priority",
            "recommendation_mode",
        }:
            assert field_name not in business

    assert (
        "Data readiness: the available evidence does not establish whether the "
        "data this activity relies on is ready for AI use."
    ) in business


def test_package_identifiers_are_technical_only() -> None:
    _, package = _package()

    narrative = build_package_narrative(package)
    business = " ".join(narrative.business_lines())
    technical = " ".join(narrative.technical_reference)

    for token in (
        package.package_id,
        package.source.policy.policy_id,
        package.source.policy.decision_policy_fingerprint,
        package.source.integrated_assessment_run_id,
        package.completeness.value,
    ):
        assert token in technical
        assert token not in business


def test_package_next_action_presents_continuation_as_optional() -> None:
    _, package = _package()

    narrative = build_package_narrative(package)

    assert narrative.next_action[0] == (
        "This Decision Package is a complete decision. You can act on it now."
    )
    assert any("optional" in line for line in narrative.next_action)
    assert not any("must" in line for line in narrative.next_action)


def test_gap_business_statement_restates_only_named_criterion_gaps() -> None:
    _, package = _package()

    gaps = {
        (gap.kind, gap.field_name): gap
        for item in package.portfolio.items
        for gap in item.missing_information
    }
    unknown = next(
        gap
        for (kind, field), gap in gaps.items()
        if kind is InformationGapKind.UNKNOWN_INPUT and field == "data_readiness"
    )
    assert gap_business_statement(unknown) == (
        "Data readiness: the available evidence does not establish whether the "
        "data this activity relies on is ready for AI use."
    )

    inferred = next(
        gap
        for (kind, field), gap in gaps.items()
        if kind is InformationGapKind.INFERRED_REQUIRES_CONFIRMATION
        and field == "implementation_complexity"
    )
    assert gap_business_statement(inferred) == (
        "Implementation complexity: this is recorded as an assumption and still "
        "requires confirmation."
    )

    # Fields without a business phrase are never paraphrased: no invention.
    for (kind, field), gap in gaps.items():
        if field.startswith("synthetic_") or field in {
            "priority",
            "recommendation_mode",
        }:
            assert gap_business_statement(gap) is None


def test_portfolio_reason_statement_matches_the_step_level_reason() -> None:
    integrated, package = _package()

    process = build_process_narrative(integrated)
    by_activity = {item.activity: item for item in process.activities}
    for item in package.portfolio.items:
        assert portfolio_reason_statement(item) == (
            by_activity[item.current_activity].reason_statement
        )


def test_portfolio_reason_statement_never_reads_engine_rationale() -> None:
    _, package = _package()

    for item in package.portfolio.items:
        reason = portfolio_reason_statement(item)
        for gate in item.gate_results:
            assert gate.rationale not in reason


def test_package_narrative_is_deterministic() -> None:
    _, first_package = _package()
    _, second_package = _package()

    assert build_package_narrative(first_package) == build_package_narrative(
        second_package
    )

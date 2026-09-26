import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_adoption_engine.decision.four_gate_engine import FourGateAssessmentEngine
from ai_adoption_engine.decision.four_gate_policy import load_four_gate_policy
from ai_adoption_engine.decision_support.four_gate_service import (
    FourGateDecisionSupportPackageService,
)
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.four_gate_assessment import (
    CapabilitySignalName,
    DecisionStatus,
    FourGateName,
    FourGatePriorityStatus,
    OutcomeCode,
)
from ai_adoption_engine.models.four_gate_decision_support import (
    FourGateCapabilityUseStatus,
    FourGateDecisionPackageFailure,
    FourGateDecisionPackageFailureCode,
    FourGateDecisionPackageSuccess,
    FourGateInformationGapKind,
    FourGatePackageCompleteness,
    FourGateReportSectionId,
)
from ai_adoption_engine.models.four_gate_integrated_assessment import (
    FourGateAssessedPolicyReference,
    FourGateAssessmentRunMetadata,
    FourGateIntegratedAssessmentSuccess,
    FourGateStepAssessmentTrace,
)
from ai_adoption_engine.models.integrated_assessment import (
    AssessmentLineage,
    EvidenceTraceReference,
    IntegratedAssessmentSuccess,
    ReviewedValueTrace,
)
from ai_adoption_engine.models.process import BusinessProcess, CapabilitySignalInput
from ai_adoption_engine.models.review import InformationOrigin, ReviewDisposition
from tests.fakes.decision_support import sample_integrated_assessment


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "decision_policy.v0.3.json"
PROCESS_PATH = (
    ROOT
    / "data"
    / "sample_processes"
    / "synthetic_customer_complaint_process.json"
)
SOURCE_DOCUMENT_ID = f"doc-{'2' * 64}"
FIXED_TIME = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


def _unknown(value) -> None:
    value.value = None
    value.knowledge_state = KnowledgeState.UNKNOWN
    value.evidence_ids = []
    value.confidence = None


def _source_process() -> BusinessProcess:
    with PROCESS_PATH.open(encoding="utf-8") as handle:
        process = BusinessProcess.model_validate(json.load(handle))
    process = process.model_copy(deep=True)
    process.steps = [process.steps[0]]
    step = process.steps[0]
    step.step_id = "successor-step"
    step.activity = "Assess successor activity"
    step.evidence_ids = ["E1"]
    for evidence in process.evidence:
        evidence.source_id = SOURCE_DOCUMENT_ID

    common = {
        CriterionName.REPETITION: 5,
        CriterionName.PREDICTABILITY: 5,
        CriterionName.DATA_READINESS: 5,
        CriterionName.AI_CAPABILITY_FIT: 5,
        CriterionName.HUMAN_JUDGEMENT_REQUIREMENT: 1,
        CriterionName.BUSINESS_VALUE: 5,
        CriterionName.RISK_CONSEQUENCE: 1,
        CriterionName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT: 1,
        CriterionName.IMPLEMENTATION_COMPLEXITY: 2,
        CriterionName.CONVENTIONAL_SOLUTION_FIT: 1,
    }
    for name, value in common.items():
        criterion = step.characteristics.criterion(name)
        criterion.value = value
        criterion.knowledge_state = KnowledgeState.KNOWN
        criterion.rationale = f"Reviewed {name.value}."
        criterion.evidence_ids = ["E1"]
        criterion.confidence = None
    accountability = step.characteristics.human_accountability_required
    accountability.value = False
    accountability.knowledge_state = KnowledgeState.KNOWN
    accountability.rationale = "Reviewed accountability."
    accountability.evidence_ids = ["E1"]
    accountability.confidence = None
    for signal_name in CapabilitySignalName:
        setattr(
            step.characteristics.capability_signals,
            signal_name.value,
            CapabilitySignalInput(
                value=(
                    signal_name
                    is CapabilitySignalName.READS_UNSTRUCTURED_DOCUMENTS
                ),
                knowledge_state=KnowledgeState.KNOWN,
                rationale=f"Reviewed {signal_name.value}.",
                evidence_ids=["E1"],
            ),
        )
    return process


def _reviewed_trace(value, evidence_by_id, *, validated, review, assessed):
    references = [evidence_by_id[item] for item in value.evidence_ids]
    if value.knowledge_state is KnowledgeState.UNKNOWN:
        origin = InformationOrigin.UNKNOWN
        disposition = ReviewDisposition.UNKNOWN_RETAINED
    elif value.knowledge_state is KnowledgeState.INFERRED:
        origin = InformationOrigin.MODEL_INFERRED
        disposition = ReviewDisposition.ACCEPTED
    else:
        origin = (
            InformationOrigin.DOCUMENT_SUPPORTED
            if references
            else InformationOrigin.HUMAN_SUPPLIED
        )
        disposition = ReviewDisposition.ACCEPTED
    return ReviewedValueTrace(
        validated_process_field_path=validated,
        review_field_path=review,
        assessment_field_path=assessed,
        origin=origin,
        knowledge_state=value.knowledge_state,
        review_disposition=disposition,
        evidence=references,
    )


def _trace_for(process, assessed):
    step = process.steps[0]
    evidence_by_id = {
        evidence.evidence_id: EvidenceTraceReference(
            evidence_id=evidence.evidence_id,
            document_id=SOURCE_DOCUMENT_ID,
            block_id=f"block-{evidence.evidence_id}",
            block_start_offset=0,
            block_end_offset=max(1, len(evidence.supporting_snippet)),
            source_locator=evidence.source_locator,
        )
        for evidence in process.evidence
    }
    base = f"process_assessment.step_assessments[step_id={step.step_id}]"
    process_base = f"business_process.steps[step_id={step.step_id}]"
    review_base = f"review.steps[candidate_step_id={step.step_id}]"
    criteria = []
    for item in assessed.criteria:
        supplied = step.characteristics.criterion(item.criterion)
        criteria.append(
            _reviewed_trace(
                supplied,
                evidence_by_id,
                validated=f"{process_base}.characteristics.{item.criterion.value}",
                review=f"{review_base}.criteria[name={item.criterion.value}]",
                assessed=f"{base}.criteria[criterion={item.criterion.value}]",
            )
        )
    signals = []
    for item in assessed.capability_signals:
        supplied = getattr(
            step.characteristics.capability_signals,
            item.signal.value,
        )
        signals.append(
            _reviewed_trace(
                supplied,
                evidence_by_id,
                validated=(
                    f"{process_base}.characteristics.capability_signals."
                    f"{item.signal.value}"
                ),
                review=f"{review_base}.capability_signals[name={item.signal.value}]",
                assessed=f"{base}.capability_signals[signal={item.signal.value}]",
            )
        )
    activity_value = type("ActivityValue", (), {})()
    activity_value.knowledge_state = KnowledgeState.KNOWN
    activity_value.evidence_ids = step.evidence_ids
    accountability = step.characteristics.human_accountability_required
    return FourGateStepAssessmentTrace(
        step_id=step.step_id,
        assessment_step_path=base,
        decision_status_path=f"{base}.decision_status",
        change_disposition_path=f"{base}.change_disposition",
        readiness_disposition_path=f"{base}.readiness_disposition",
        selected_intervention_family_path=(
            f"{base}.selected_intervention_family"
        ),
        autonomy_ceiling_path=f"{base}.autonomy_ceiling",
        outcome_code_path=f"{base}.outcome_code",
        gate_results_path=f"{base}.gate_results",
        validated_step_path=process_base,
        review_step_path=review_base,
        activity=_reviewed_trace(
            activity_value,
            evidence_by_id,
            validated=f"{process_base}.activity",
            review=f"{review_base}.activity",
            assessed=f"{base}.activity",
        ),
        criteria=criteria,
        human_accountability=_reviewed_trace(
            accountability,
            evidence_by_id,
            validated=(
                f"{process_base}.characteristics.human_accountability_required"
            ),
            review=f"{review_base}.human_accountability_required",
            assessed=f"{base}.human_accountability",
        ),
        capability_signals=signals,
    )


def _integrated(scenario: str = "ai_automation"):
    process = _source_process()
    step = process.steps[0]
    if scenario == "discovery":
        _unknown(step.characteristics.business_value)
    elif scenario == "no_change":
        step.characteristics.business_value.value = 1
    elif scenario == "process_improvement":
        step.characteristics.data_readiness.value = 1
        _unknown(step.characteristics.implementation_complexity)
        _unknown(step.characteristics.repetition)
        _unknown(step.characteristics.predictability)
        _unknown(step.characteristics.ai_capability_fit)
    elif scenario == "conventional":
        step.characteristics.conventional_solution_fit.value = 4
        _unknown(step.characteristics.ai_capability_fit)
    elif scenario == "human_led":
        step.characteristics.ai_capability_fit.value = 2
    elif scenario == "safety_veto":
        step.characteristics.residual_risk_with_human_oversight.value = 4
    elif scenario == "ai_assisted":
        step.characteristics.human_judgement_requirement.value = 3
    elif scenario == "priority_incomplete":
        _unknown(step.characteristics.repetition)

    policy = load_four_gate_policy(POLICY_PATH)
    assessment = FourGateAssessmentEngine(policy).assess(process)
    assessed = assessment.step_assessments[0]
    trace = _trace_for(process, assessed)
    return FourGateIntegratedAssessmentSuccess(
        metadata=FourGateAssessmentRunMetadata(
            assessment_run_id="successor-phase5-fixture",
            assessed_at=FIXED_TIME,
        ),
        lineage=AssessmentLineage(
            source_document_id=SOURCE_DOCUMENT_ID,
            extraction_run_id="successor-extraction",
            review_id="successor-review",
            approval_event_id="successor-approval",
            approved_at=FIXED_TIME,
            validated_process_id=process.process_id,
            validated_process_fingerprint="1" * 64,
        ),
        policy=FourGateAssessedPolicyReference(
            policy_status=policy.status,
            decision_policy_fingerprint="3" * 64,
        ),
        process_assessment=assessment,
        step_traceability=[trace],
    )


def _package(scenario="ai_automation"):
    result = FourGateDecisionSupportPackageService().generate(
        _integrated(scenario)
    )
    assert isinstance(result, FourGateDecisionPackageSuccess)
    return result.package


@pytest.mark.parametrize(
    ("scenario", "outcome"),
    [
        ("discovery", OutcomeCode.DISCOVERY_REQUIRED),
        ("no_change", OutcomeCode.NO_CHANGE_JUSTIFIED),
        ("process_improvement", OutcomeCode.PROCESS_IMPROVEMENT_FIRST),
        ("conventional", OutcomeCode.CONVENTIONAL_AUTOMATION),
        ("human_led", OutcomeCode.KEEP_HUMAN_LED),
        ("ai_assisted", OutcomeCode.AI_ASSISTED_WORK),
        ("ai_automation", OutcomeCode.AI_AUTOMATION),
    ],
)
def test_all_seven_outcomes_are_packaged_losslessly(scenario, outcome) -> None:
    integrated = _integrated(scenario)
    generated = FourGateDecisionSupportPackageService().generate(integrated)
    assert isinstance(generated, FourGateDecisionPackageSuccess)
    package = generated.package
    item = package.portfolio.items[0]
    assessed = integrated.process_assessment.step_assessments[0]

    assert package.package_schema_version == "phase6-v0.2"
    assert package.source.integration_schema_version == "phase5-v0.2"
    assert package.source.phase1_contract_version == "phase1-v0.4"
    assert item.outcome_code is outcome
    assert item.outcome_code is assessed.outcome_code
    assert item.decision_status is assessed.decision_status
    assert item.change_disposition is assessed.change_disposition
    assert item.readiness_disposition is assessed.readiness_disposition
    assert item.selected_intervention_family is (
        assessed.selected_intervention_family
    )
    assert item.autonomy_ceiling is assessed.autonomy_ceiling
    assert item.gate_results == assessed.gate_results
    assert [gate.gate for gate in item.gate_results] == list(FourGateName)
    assert item.criteria == assessed.criteria
    assert item.human_accountability == assessed.human_accountability
    assert item.capability_signals == assessed.capability_signals
    assert item.material_evidence == assessed.evidence
    assert item.source_traceability == integrated.step_traceability[0]


def test_package_has_thirteen_ordered_sections_and_source_disclosures() -> None:
    package = _package()
    assert package.completeness is FourGatePackageCompleteness.COMPLETE
    assert [section.section_id for section in package.report_content.sections] == list(
        FourGateReportSectionId
    )
    assert len(package.report_content.sections) == 13
    assert package.source.lineage.validated_process_fingerprint == "1" * 64
    assert package.source.policy.decision_policy_fingerprint == "3" * 64
    assert package.methodology.policy_fingerprint == "3" * 64
    assert package.methodology.policy_is_provisional is True
    assert package.methodology.academically_validated is False
    assert package.methodology.decision_support_only is True
    disclosure = " ".join(package.methodology.disclosure_statements).lower()
    assert "provisional" in disclosure
    assert "not academically validated" in disclosure
    assert "decision support only" in disclosure


def test_blocking_context_and_priority_gaps_remain_separate() -> None:
    discovery = _package("discovery")
    discovery_section = discovery.report_content.sections[
        list(FourGateReportSectionId).index(
            FourGateReportSectionId.DISCOVERY_REQUIRED
        )
    ]
    assert all(
        "business_value" in statement.text
        for statement in discovery_section.statements
    )

    process_first = _package("process_improvement")
    assert process_first.completeness is (
        FourGatePackageCompleteness.COMPLETE_WITH_INFORMATION_GAPS
    )
    kinds = {gap.kind for gap in process_first.missing_information}
    assert FourGateInformationGapKind.ACTIVE_DECISION_BLOCKER not in kinds
    assert FourGateInformationGapKind.CONTEXTUAL_UNKNOWN in kinds
    assert "established Gate 2 blocker(s): data_readiness" in (
        process_first.portfolio.items[0].final_recommendation
    )
    assert "missing" not in process_first.portfolio.items[0].final_recommendation.lower()

    incomplete = _package("priority_incomplete")
    item = incomplete.portfolio.items[0]
    assert item.decision_status is DecisionStatus.COMPLETE
    assert item.priority_status is FourGatePriorityStatus.INCOMPLETE
    assert any(
        gap.kind is FourGateInformationGapKind.PRIORITY_ONLY
        for gap in item.information_gaps
    )


def test_outcome_specific_wording_and_safety_veto_are_unambiguous() -> None:
    no_change = _package("no_change").portfolio.items[0]
    assert "No Change Justified" in no_change.final_recommendation
    assert "human-led" not in no_change.final_recommendation.lower()

    conventional = _package("conventional").portfolio.items[0]
    assert "Conventional Automation" in conventional.final_recommendation
    assert "AI fit" not in conventional.final_recommendation
    assert "missing" not in conventional.final_recommendation.lower()

    candidate = _package("human_led").portfolio.items[0]
    assert "selected at Gate 3" in candidate.final_recommendation
    assert "Gate 4" not in candidate.final_recommendation

    veto_package = _package("safety_veto")
    veto = veto_package.portfolio.items[0]
    assert veto.outcome_code is OutcomeCode.KEEP_HUMAN_LED
    assert veto.selected_intervention_family.value == "AI"
    assert veto.autonomy_ceiling.value == "AI_NOT_PERMITTED"
    assert "AI was selected as the Gate 3 candidate" in veto.final_recommendation
    assert "rejected by the Gate 4 safety veto" in veto.final_recommendation
    assert "sole final recommendation" in veto.final_recommendation
    assert veto_package.future_state.steps[0].capability_use_status is (
        FourGateCapabilityUseStatus.REJECTED_AT_SAFETY_GATE
    )
    veto_statements = [
        statement
        for section in veto_package.report_content.sections
        for statement in section.statements
        if veto.step_id in statement.step_ids
    ]
    assert all(
        statement.final_outcome in {None, OutcomeCode.KEEP_HUMAN_LED}
        for statement in veto_statements
    )
    assert any(
        statement.final_outcome is OutcomeCode.KEEP_HUMAN_LED
        for statement in veto_statements
    )
    assert not any(
        statement.final_outcome
        in {OutcomeCode.AI_AUTOMATION, OutcomeCode.AI_ASSISTED_WORK}
        for statement in veto_statements
    )


def test_only_complete_ai_outcomes_are_priority_eligible() -> None:
    for scenario in (
        "discovery",
        "no_change",
        "process_improvement",
        "conventional",
        "human_led",
        "safety_veto",
    ):
        item = _package(scenario).portfolio.items[0]
        assert item.priority_eligible is False
        assert item.priority_status is FourGatePriorityStatus.NOT_APPLICABLE
    assert _package("ai_automation").portfolio.items[0].priority_eligible is True
    assert _package("ai_assisted").portfolio.items[0].priority_eligible is True


def test_package_identity_is_deterministic_and_ignores_run_metadata() -> None:
    first = _integrated()
    second = first.model_copy(
        update={
            "metadata": first.metadata.model_copy(
                update={
                    "assessment_run_id": "another-successor-run",
                    "assessed_at": first.metadata.assessed_at + timedelta(days=1),
                }
            )
        }
    )
    first_result = FourGateDecisionSupportPackageService().generate(first)
    second_result = FourGateDecisionSupportPackageService().generate(second)
    assert isinstance(first_result, FourGateDecisionPackageSuccess)
    assert isinstance(second_result, FourGateDecisionPackageSuccess)
    assert first_result.package.package_id == second_result.package.package_id
    assert first_result.package.portfolio == second_result.package.portfolio


def test_legacy_malformed_mixed_and_inconsistent_inputs_fail_closed() -> None:
    service = FourGateDecisionSupportPackageService()
    for legacy in (sample_integrated_assessment(), {}):
        result = service.generate(legacy)
        assert isinstance(result, FourGateDecisionPackageFailure)
        assert result.package_schema_version == "phase6-v0.2"
        assert result.errors[0].code is (
            FourGateDecisionPackageFailureCode.INTEGRATED_SUCCESS_REQUIRED
        )

    malformed = _integrated().model_copy(
        update={"step_traceability": []}
    )
    result = service.generate(malformed)
    assert isinstance(result, FourGateDecisionPackageFailure)
    assert result.errors[0].code is (
        FourGateDecisionPackageFailureCode.INVALID_INTEGRATED_ASSESSMENT
    )

    inconsistent = _integrated().model_copy(deep=True)
    criterion = inconsistent.process_assessment.step_assessments[0].criteria[0]
    criterion.evidence_ids = []
    result = service.generate(inconsistent)
    assert isinstance(result, FourGateDecisionPackageFailure)
    assert result.errors[0].code is (
        FourGateDecisionPackageFailureCode.INVALID_TRACEABILITY
    )

    mixed = _integrated().model_copy(
        update={
            "metadata": _integrated().metadata.model_copy(
                update={"integration_schema_version": "phase5-v0.1"}
            )
        }
    )
    result = service.generate(mixed)
    assert isinstance(result, FourGateDecisionPackageFailure)
    assert result.errors[0].code is (
        FourGateDecisionPackageFailureCode.INVALID_INTEGRATED_ASSESSMENT
    )

    bad_lineage = _integrated().model_copy(deep=True)
    bad_lineage.process_assessment.step_assessments[0].evidence[0].source_locator = (
        "unreviewed locator"
    )
    result = service.generate(bad_lineage)
    assert isinstance(result, FourGateDecisionPackageFailure)
    assert result.errors[0].code is (
        FourGateDecisionPackageFailureCode.INVALID_EVIDENCE_LINEAGE
    )

    assert not isinstance(_integrated(), IntegratedAssessmentSuccess)

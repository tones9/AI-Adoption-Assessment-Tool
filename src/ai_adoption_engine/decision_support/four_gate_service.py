"""Explicit deterministic Phase 6 service for four-gate Phase 5 results."""

from __future__ import annotations

import hashlib
import json
from collections import Counter

from pydantic import ValidationError

from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.models.four_gate_assessment import (
    AutonomyCeiling,
    DecisionStatus,
    FourGateName,
    FourGatePriorityStatus,
    OutcomeCode,
    SelectedInterventionFamily,
)
from ai_adoption_engine.models.four_gate_decision_support import (
    FourGateCapabilityUseStatus,
    FourGateCurrentStateReference,
    FourGateDecisionPackageError,
    FourGateDecisionPackageFailure,
    FourGateDecisionPackageFailureCode,
    FourGateDecisionPackageResult,
    FourGateDecisionPackageSuccess,
    FourGateDecisionPortfolio,
    FourGateDecisionPortfolioItem,
    FourGateDecisionReportContent,
    FourGateDecisionSupportPackage,
    FourGateFutureStateStep,
    FourGateGovernanceItem,
    FourGateInformationGap,
    FourGateInformationGapKind,
    FourGateMethodologyDisclosure,
    FourGatePackageCompleteness,
    FourGatePackageSource,
    FourGateProposedFutureStateWorkflow,
    FourGateReportOrigin,
    FourGateReportSection,
    FourGateReportSectionId,
    FourGateReportStatement,
    FourGateRoadmapItem,
)
from ai_adoption_engine.models.four_gate_integrated_assessment import (
    FourGateIntegratedAssessmentSuccess,
)


PACKAGE_SCHEMA_VERSION = "phase6-v0.2"


class FourGateDecisionSupportPackageService:
    """Project a validated successor assessment; never reassess or call providers."""

    def generate(self, integrated: object) -> FourGateDecisionPackageResult:
        if not isinstance(integrated, FourGateIntegratedAssessmentSuccess):
            return self._failure(
                FourGateDecisionPackageFailureCode.INTEGRATED_SUCCESS_REQUIRED,
                "Phase 6 successor generation requires "
                "FourGateIntegratedAssessmentSuccess.",
            )
        source_run_id = getattr(
            getattr(integrated, "metadata", None),
            "assessment_run_id",
            None,
        )
        try:
            validated = FourGateIntegratedAssessmentSuccess.model_validate(
                integrated.model_dump(mode="json")
            )
        except (AttributeError, TypeError, ValueError, ValidationError):
            return self._failure(
                FourGateDecisionPackageFailureCode.INVALID_INTEGRATED_ASSESSMENT,
                "The Phase 5 successor result is malformed or internally inconsistent.",
                source_run_id=source_run_id,
            )

        contract_error = _validate_source_contract(validated)
        if contract_error is not None:
            code, message, field_path, step_id = contract_error
            return self._failure(
                code,
                message,
                field_path=field_path,
                step_id=step_id,
                source_run_id=validated.metadata.assessment_run_id,
            )

        try:
            portfolio = _build_portfolio(validated)
            gaps = [
                gap for item in portfolio.items for gap in item.information_gaps
            ]
            completeness = (
                FourGatePackageCompleteness.COMPLETE_WITH_INFORMATION_GAPS
                if gaps
                else FourGatePackageCompleteness.COMPLETE
            )
            future_state = _build_future_state(validated, portfolio)
            roadmap = _build_roadmap(portfolio)
            governance = _build_governance(portfolio)
            methodology = _methodology(validated)
            appendix = _evidence_appendix(validated)
            report = _build_report(
                process_name=validated.process_assessment.process_name,
                completeness=completeness,
                portfolio=portfolio,
                future_state=future_state,
                roadmap=roadmap,
                governance=governance,
                methodology=methodology,
                evidence_appendix=appendix,
            )
            package = FourGateDecisionSupportPackage(
                package_id=_package_id(validated),
                completeness=completeness,
                source=FourGatePackageSource(
                    integrated_assessment_run_id=(
                        validated.metadata.assessment_run_id
                    ),
                    integration_schema_version=(
                        validated.metadata.integration_schema_version
                    ),
                    phase1_contract_version=(
                        validated.metadata.phase1_contract_version
                    ),
                    lineage=validated.lineage,
                    policy=validated.policy,
                ),
                current_state=FourGateCurrentStateReference(
                    process_id=validated.process_assessment.process_id,
                    process_name=validated.process_assessment.process_name,
                    framework_id=validated.process_assessment.framework_id,
                    framework_version=validated.process_assessment.framework_version,
                    review_id=validated.lineage.review_id,
                    approval_event_id=validated.lineage.approval_event_id,
                    source_document_id=validated.lineage.source_document_id,
                    ordered_step_ids=[item.step_id for item in portfolio.items],
                ),
                portfolio=portfolio,
                future_state=future_state,
                roadmap=roadmap,
                governance=governance,
                missing_information=gaps,
                methodology=methodology,
                evidence_appendix=appendix,
                report_content=report,
            )
        except (KeyError, TypeError, ValueError, ValidationError):
            return self._failure(
                FourGateDecisionPackageFailureCode.PACKAGE_GENERATION_FAILED,
                "The deterministic Phase 6 successor package could not be constructed.",
                source_run_id=validated.metadata.assessment_run_id,
            )
        return FourGateDecisionPackageSuccess(package=package)

    @staticmethod
    def _failure(
        code: FourGateDecisionPackageFailureCode,
        message: str,
        *,
        field_path: str | None = None,
        step_id: str | None = None,
        source_run_id: str | None = None,
    ) -> FourGateDecisionPackageFailure:
        return FourGateDecisionPackageFailure(
            source_assessment_run_id=source_run_id,
            errors=[
                FourGateDecisionPackageError(
                    code=code,
                    message=message,
                    field_path=field_path,
                    step_id=step_id,
                )
            ],
        )


ContractError = tuple[
    FourGateDecisionPackageFailureCode,
    str,
    str | None,
    str | None,
]


def _validate_source_contract(
    integrated: FourGateIntegratedAssessmentSuccess,
) -> ContractError | None:
    assessment = integrated.process_assessment
    if (
        integrated.metadata.integration_schema_version != "phase5-v0.2"
        or integrated.metadata.phase1_contract_version != "phase1-v0.4"
        or assessment.decision_contract_version != "phase1-v0.4"
        or assessment.framework_id != "four-gate-framework.v0.1"
        or assessment.framework_version != "0.1"
        or assessment.policy_id != "decision_policy.v0.3"
        or assessment.policy_version != "0.3.0"
    ):
        return (
            FourGateDecisionPackageFailureCode.UNSUPPORTED_CONTRACT,
            "Phase 6 accepts only the complete phase5-v0.2 / phase1-v0.4 chain.",
            "metadata",
            None,
        )
    if (
        assessment.policy_id != integrated.policy.policy_id
        or assessment.policy_version != integrated.policy.policy_version
        or assessment.policy_status != integrated.policy.policy_status
    ):
        return (
            FourGateDecisionPackageFailureCode.UNSUPPORTED_CONTRACT,
            "Embedded assessment and policy identities do not agree.",
            "policy",
            None,
        )
    assessed_ids = [item.step_id for item in assessment.step_assessments]
    traced_ids = [item.step_id for item in integrated.step_traceability]
    if (
        not assessed_ids
        or assessed_ids != traced_ids
        or len(assessed_ids) != len(set(assessed_ids))
    ):
        return (
            FourGateDecisionPackageFailureCode.INCOMPLETE_STEP_COVERAGE,
            "Every assessed step requires exactly one ordered traceability record.",
            "step_traceability",
            None,
        )
    if assessment.process_id != integrated.lineage.validated_process_id:
        return (
            FourGateDecisionPackageFailureCode.INVALID_INTEGRATED_ASSESSMENT,
            "The assessed process identity does not match approved-review lineage.",
            "process_assessment.process_id",
            None,
        )

    all_trace_references = {}
    for trace in integrated.step_traceability:
        for value in [
            trace.activity,
            *trace.criteria,
            trace.human_accountability,
            *trace.capability_signals,
        ]:
            for reference in value.evidence:
                # Phase 5 has already validated every trace reference against the
                # approved review. A controlled successor review may add a second,
                # content-addressed supporting document; it is not required to be
                # the original extraction document recorded in process lineage.
                previous = all_trace_references.get(reference.evidence_id)
                if previous is not None and previous != reference:
                    return (
                        FourGateDecisionPackageFailureCode.INVALID_EVIDENCE_LINEAGE,
                        "One evidence ID resolves to conflicting reviewed references.",
                        value.review_field_path,
                        trace.step_id,
                    )
                all_trace_references[reference.evidence_id] = reference

    for assessed, trace in zip(
        assessment.step_assessments,
        integrated.step_traceability,
        strict=True,
    ):
        error = _validate_step_trace(assessed, trace, all_trace_references)
        if error is not None:
            return error
    return None


def _validate_step_trace(assessed, trace, all_trace_references) -> ContractError | None:
    base = f"process_assessment.step_assessments[step_id={assessed.step_id}]"
    if assessed.step_id != trace.step_id:
        return (
            FourGateDecisionPackageFailureCode.INVALID_TRACEABILITY,
            "Assessment and traceability step IDs do not match.",
            "step_traceability",
            assessed.step_id,
        )
    if [result.gate for result in assessed.gate_results] != list(FourGateName):
        return (
            FourGateDecisionPackageFailureCode.UNSUPPORTED_CONTRACT,
            "Each successor step must retain exactly four ordered gates.",
            f"{base}.gate_results",
            assessed.step_id,
        )

    gate_material = {
        criterion: [
            result.gate
            for result in assessed.gate_results
            if criterion in result.material_criteria
        ]
        for criterion in (item.criterion for item in assessed.criteria)
    }
    gate_context = {
        criterion: [
            result.gate
            for result in assessed.gate_results
            if criterion in result.context_criteria
        ]
        for criterion in (item.criterion for item in assessed.criteria)
    }
    for criterion, value_trace in zip(
        assessed.criteria,
        trace.criteria,
        strict=True,
    ):
        if (
            criterion.knowledge_state is not value_trace.knowledge_state
            or criterion.evidence_ids
            != [reference.evidence_id for reference in value_trace.evidence]
            or criterion.material_at_gates != gate_material[criterion.criterion]
            or criterion.context_at_gates != gate_context[criterion.criterion]
        ):
            return (
                FourGateDecisionPackageFailureCode.INVALID_TRACEABILITY,
                "Criterion value, evidence, or materiality differs from its review trace.",
                value_trace.review_field_path,
                assessed.step_id,
            )

    accountability_gates = [
        result.gate
        for result in assessed.gate_results
        if result.accountability_material
    ]
    if (
        assessed.human_accountability.knowledge_state
        is not trace.human_accountability.knowledge_state
        or assessed.human_accountability.evidence_ids
        != [
            reference.evidence_id
            for reference in trace.human_accountability.evidence
        ]
        or assessed.human_accountability.material_at_gates
        != accountability_gates
    ):
        return (
            FourGateDecisionPackageFailureCode.INVALID_TRACEABILITY,
            "Accountability evidence or materiality differs from its review trace.",
            trace.human_accountability.review_field_path,
            assessed.step_id,
        )

    signal_gates = {
        signal.signal: [
            result.gate
            for result in assessed.gate_results
            if signal.signal in result.material_capability_signals
        ]
        for signal in assessed.capability_signals
    }
    for signal, value_trace in zip(
        assessed.capability_signals,
        trace.capability_signals,
        strict=True,
    ):
        if (
            signal.knowledge_state is not value_trace.knowledge_state
            or signal.evidence_ids
            != [reference.evidence_id for reference in value_trace.evidence]
            or signal.material_at_gates != signal_gates[signal.signal]
        ):
            return (
                FourGateDecisionPackageFailureCode.INVALID_TRACEABILITY,
                "Capability evidence or materiality differs from its review trace.",
                value_trace.review_field_path,
                assessed.step_id,
            )

    expected_material_ids = {
        reference.evidence_id for reference in trace.activity.evidence
    }
    expected_material_ids.update(
        evidence_id
        for criterion in assessed.criteria
        if criterion.material_to_decision
        for evidence_id in criterion.evidence_ids
    )
    if assessed.human_accountability.material_to_decision:
        expected_material_ids.update(assessed.human_accountability.evidence_ids)
    expected_material_ids.update(
        evidence_id
        for signal in assessed.capability_signals
        if signal.material_to_decision
        for evidence_id in signal.evidence_ids
    )
    actual_material_ids = [item.evidence_id for item in assessed.evidence]
    if (
        len(actual_material_ids) != len(set(actual_material_ids))
        or set(actual_material_ids) != expected_material_ids
    ):
        return (
            FourGateDecisionPackageFailureCode.INVALID_EVIDENCE_LINEAGE,
            "Step material evidence does not match its reached decision path.",
            f"{base}.evidence",
            assessed.step_id,
        )
    for evidence in assessed.evidence:
        reference = all_trace_references.get(evidence.evidence_id)
        if (
            reference is None
            or evidence.source_id != reference.document_id
            or evidence.source_locator != reference.source_locator
        ):
            return (
                FourGateDecisionPackageFailureCode.INVALID_EVIDENCE_LINEAGE,
                "Material evidence cannot be resolved through reviewed lineage.",
                f"{base}.evidence",
                assessed.step_id,
            )
    if any(
        evidence_id not in expected_material_ids
        for result in assessed.gate_results
        for evidence_id in result.evidence_ids
    ):
        return (
            FourGateDecisionPackageFailureCode.INVALID_EVIDENCE_LINEAGE,
            "A gate references evidence outside the material decision set.",
            f"{base}.gate_results",
            assessed.step_id,
        )
    return None


def _build_portfolio(
    integrated: FourGateIntegratedAssessmentSuccess,
) -> FourGateDecisionPortfolio:
    items = []
    for sequence, (assessed, trace) in enumerate(
        zip(
            integrated.process_assessment.step_assessments,
            integrated.step_traceability,
            strict=True,
        ),
        start=1,
    ):
        gaps = _information_gaps(assessed, trace)
        items.append(
            FourGateDecisionPortfolioItem(
                sequence=sequence,
                step_id=assessed.step_id,
                activity=assessed.activity,
                decision_status=assessed.decision_status,
                change_disposition=assessed.change_disposition,
                readiness_disposition=assessed.readiness_disposition,
                selected_intervention_family=(
                    assessed.selected_intervention_family
                ),
                autonomy_ceiling=assessed.autonomy_ceiling,
                outcome_code=assessed.outcome_code,
                gate_results=assessed.gate_results,
                blocking_gaps=assessed.blocking_gaps,
                capabilities=assessed.capabilities,
                capability_signals=assessed.capability_signals,
                criteria=assessed.criteria,
                human_accountability=assessed.human_accountability,
                priority_status=assessed.priority_status,
                priority=assessed.priority,
                priority_missing_criteria=assessed.priority_missing_criteria,
                priority_eligible=assessed.outcome_code
                in {OutcomeCode.AI_AUTOMATION, OutcomeCode.AI_ASSISTED_WORK},
                rationale=assessed.reasoning,
                material_evidence=assessed.evidence,
                information_gaps=gaps,
                source_traceability=trace,
                final_recommendation=_final_recommendation(assessed),
            )
        )
    return FourGateDecisionPortfolio(items=items)


def _information_gaps(assessed, trace) -> list[FourGateInformationGap]:
    gaps = []
    for index, gap in enumerate(assessed.blocking_gaps, start=1):
        gaps.append(
            FourGateInformationGap(
                gap_id=f"{assessed.step_id}:blocker:{index}",
                step_id=assessed.step_id,
                kind=FourGateInformationGapKind.ACTIVE_DECISION_BLOCKER,
                field_name=gap.field_name,
                message=gap.blocking_question,
                gate=gap.gate,
                evidence_ids=gap.evidence_ids,
                assessment_paths=[trace.gate_results_path],
                review_paths=_review_paths_for_field(trace, gap.field_name),
            )
        )

    blocked_fields = {gap.field_name for gap in assessed.blocking_gaps}
    for criterion, value_trace in zip(
        assessed.criteria,
        trace.criteria,
        strict=True,
    ):
        if (
            criterion.knowledge_state is KnowledgeState.UNKNOWN
            and criterion.criterion.value not in blocked_fields
        ):
            gaps.append(
                FourGateInformationGap(
                    gap_id=(
                        f"{assessed.step_id}:context:{criterion.criterion.value}"
                    ),
                    step_id=assessed.step_id,
                    kind=FourGateInformationGapKind.CONTEXTUAL_UNKNOWN,
                    field_name=criterion.criterion.value,
                    message=(
                        f"{criterion.criterion.value} is unknown context and did "
                        "not block the reached decision."
                    ),
                    assessment_paths=[value_trace.assessment_field_path or ""],
                    review_paths=[value_trace.review_field_path],
                )
            )
    if (
        assessed.human_accountability.knowledge_state is KnowledgeState.UNKNOWN
        and "human_accountability_required" not in blocked_fields
    ):
        gaps.append(
            FourGateInformationGap(
                gap_id=f"{assessed.step_id}:context:human_accountability_required",
                step_id=assessed.step_id,
                kind=FourGateInformationGapKind.CONTEXTUAL_UNKNOWN,
                field_name="human_accountability_required",
                message=(
                    "Human accountability is unknown context and did not block "
                    "the reached decision."
                ),
                assessment_paths=[
                    trace.human_accountability.assessment_field_path or ""
                ],
                review_paths=[trace.human_accountability.review_field_path],
            )
        )
    for signal, value_trace in zip(
        assessed.capability_signals,
        trace.capability_signals,
        strict=True,
    ):
        if (
            signal.knowledge_state is KnowledgeState.UNKNOWN
            and "capability_signals" not in blocked_fields
        ):
            gaps.append(
                FourGateInformationGap(
                    gap_id=f"{assessed.step_id}:context:{signal.signal.value}",
                    step_id=assessed.step_id,
                    kind=FourGateInformationGapKind.CONTEXTUAL_UNKNOWN,
                    field_name=signal.signal.value,
                    message=(
                        f"Capability signal {signal.signal.value} is unknown "
                        "context and did not block the reached decision."
                    ),
                    assessment_paths=[value_trace.assessment_field_path or ""],
                    review_paths=[value_trace.review_field_path],
                )
            )
    for criterion in assessed.priority_missing_criteria:
        value_trace = next(
            item
            for item in trace.criteria
            if f"criterion={criterion.value}" in (item.assessment_field_path or "")
        )
        gaps.append(
            FourGateInformationGap(
                gap_id=f"{assessed.step_id}:priority:{criterion.value}",
                step_id=assessed.step_id,
                kind=FourGateInformationGapKind.PRIORITY_ONLY,
                field_name=criterion.value,
                message=(
                    f"{criterion.value} is required to complete AI priority, "
                    "but does not change the final decision."
                ),
                assessment_paths=[value_trace.assessment_field_path or ""],
                review_paths=[value_trace.review_field_path],
            )
        )
    return gaps


def _review_paths_for_field(trace, field_name: str) -> list[str]:
    if field_name == "activity":
        return [trace.activity.review_field_path]
    if field_name == "human_accountability_required":
        return [trace.human_accountability.review_field_path]
    if field_name == "capability_signals":
        return [item.review_field_path for item in trace.capability_signals]
    return [
        item.review_field_path
        for item in trace.criteria
        if f"name={field_name}]" in item.review_field_path
    ]


def _final_recommendation(assessed) -> str:
    outcome = assessed.outcome_code
    if outcome is OutcomeCode.DISCOVERY_REQUIRED:
        questions = "; ".join(gap.blocking_question for gap in assessed.blocking_gaps)
        return f"Discovery Required. Active decision blocker(s): {questions}"
    if outcome is OutcomeCode.NO_CHANGE_JUSTIFIED:
        return (
            "No Change Justified is the sole final outcome; the current "
            "operating model is not inferred."
        )
    if outcome is OutcomeCode.PROCESS_IMPROVEMENT_FIRST:
        gate = assessed.gate_results[1]
        blockers = ", ".join(item.value for item in gate.material_criteria)
        return (
            "Process Improvement First is the sole final outcome based on "
            f"established Gate 2 blocker(s): {blockers}."
        )
    if outcome is OutcomeCode.CONVENTIONAL_AUTOMATION:
        return (
            "Conventional Automation is the sole final outcome under the "
            "evidenced Gate 3 comparison."
        )
    if (
        assessed.selected_intervention_family is SelectedInterventionFamily.AI
        and assessed.autonomy_ceiling is AutonomyCeiling.AI_NOT_PERMITTED
    ):
        return (
            "AI was selected as the Gate 3 candidate and rejected by the Gate 4 "
            "safety veto. Keep Human-Led is the sole final recommendation."
        )
    if outcome is OutcomeCode.KEEP_HUMAN_LED:
        return (
            "Keep Human-Led was selected at Gate 3 and is the sole final outcome."
        )
    if outcome is OutcomeCode.AI_ASSISTED_WORK:
        return (
            "AI-Assisted Work is the sole final outcome and remains proposed, "
            "not deployed."
        )
    return (
        "AI Automation is the sole final outcome and remains proposed, not deployed."
    )


def _build_future_state(integrated, portfolio):
    steps = []
    for item in portfolio.items:
        veto = (
            item.selected_intervention_family is SelectedInterventionFamily.AI
            and item.autonomy_ceiling is AutonomyCeiling.AI_NOT_PERMITTED
        )
        if item.outcome_code in {
            OutcomeCode.AI_AUTOMATION,
            OutcomeCode.AI_ASSISTED_WORK,
        }:
            capability_status = FourGateCapabilityUseStatus.PROPOSED_NOT_DEPLOYED
        elif veto:
            capability_status = FourGateCapabilityUseStatus.REJECTED_AT_SAFETY_GATE
        else:
            capability_status = FourGateCapabilityUseStatus.NOT_APPLICABLE
        controls = []
        if item.outcome_code is OutcomeCode.AI_ASSISTED_WORK:
            controls.append("Human review and responsibility remain required.")
        elif item.outcome_code is OutcomeCode.AI_AUTOMATION:
            controls.append("Exception handling and monitored human oversight remain required.")
        elif veto:
            controls.append("Gate 4 prohibits the proposed AI role under current evidence.")
        steps.append(
            FourGateFutureStateStep(
                sequence=item.sequence,
                step_id=item.step_id,
                current_activity=item.activity,
                proposed_activity=item.final_recommendation,
                final_outcome=item.outcome_code,
                capability_use_status=capability_status,
                capabilities=item.capabilities,
                controls_and_constraints=controls,
            )
        )
    return FourGateProposedFutureStateWorkflow(
        process_id=integrated.process_assessment.process_id,
        process_name=integrated.process_assessment.process_name,
        steps=steps,
    )


def _build_roadmap(portfolio):
    guidance = {
        OutcomeCode.DISCOVERY_REQUIRED: "Resolve active decision blockers before reassessment.",
        OutcomeCode.NO_CHANGE_JUSTIFIED: "Retain the current approach unless evidence materially changes.",
        OutcomeCode.PROCESS_IMPROVEMENT_FIRST: "Address the established readiness blocker before intervention selection.",
        OutcomeCode.CONVENTIONAL_AUTOMATION: "Validate the conventional solution and its controls before implementation.",
        OutcomeCode.KEEP_HUMAN_LED: "Retain human-led execution and revisit only if evidence materially changes.",
        OutcomeCode.AI_ASSISTED_WORK: "Validate controls, capability use, and a human-reviewed pilot before deployment.",
        OutcomeCode.AI_AUTOMATION: "Validate controls, exception handling, and a monitored pilot before deployment.",
    }
    return [
        FourGateRoadmapItem(
            sequence=item.sequence,
            step_id=item.step_id,
            final_outcome=item.outcome_code,
            priority_status=item.priority_status,
            ai_priority_eligible=item.priority_eligible,
            guidance=guidance[item.outcome_code],
        )
        for item in portfolio.items
    ]


def _build_governance(portfolio):
    items = []
    for item in portfolio.items:
        gate_four = item.gate_results[3]
        if gate_four.status.value == "NOT_EVALUATED":
            statement = (
                "Gate 4 was not evaluated; this package makes no safety or "
                "autonomy finding for the activity."
            )
            evaluated_gate = None
            evidence_ids = []
        else:
            statement = gate_four.rationale
            evaluated_gate = FourGateName.SAFE_AUTONOMY
            evidence_ids = gate_four.evidence_ids
        items.append(
            FourGateGovernanceItem(
                step_id=item.step_id,
                final_outcome=item.outcome_code,
                statement=statement,
                evaluated_gate=evaluated_gate,
                evidence_ids=evidence_ids,
            )
        )
    return items


def _methodology(integrated):
    assessment = integrated.process_assessment
    return FourGateMethodologyDisclosure(
        framework_id=assessment.framework_id,
        framework_version=assessment.framework_version,
        decision_contract_version=assessment.decision_contract_version,
        policy_id=integrated.policy.policy_id,
        policy_version=integrated.policy.policy_version,
        policy_fingerprint=integrated.policy.decision_policy_fingerprint,
        disclosure_statements=[
            "Inherited thresholds, weights, bands, and the implementation-complexity ceiling are provisional and not academically validated.",
            "This package is decision support only; it is not implementation or deployment approval.",
            "Every future-state statement is PROPOSED / NOT DEPLOYED.",
        ],
    )


def _evidence_appendix(integrated):
    references = {}
    for trace in integrated.step_traceability:
        for value in [
            trace.activity,
            *trace.criteria,
            trace.human_accountability,
            *trace.capability_signals,
        ]:
            for reference in value.evidence:
                references[reference.evidence_id] = reference
    return [references[key] for key in sorted(references)]


def _statement(
    text,
    *,
    origin,
    item=None,
    step_ids=None,
    evidence_ids=None,
):
    return FourGateReportStatement(
        text=text,
        origin=origin,
        step_ids=step_ids or ([item.step_id] if item else []),
        evidence_ids=evidence_ids or [],
        final_outcome=item.outcome_code if item else None,
        selected_intervention_family=(
            item.selected_intervention_family if item else None
        ),
        autonomy_ceiling=item.autonomy_ceiling if item else None,
    )


def _build_report(
    *,
    process_name,
    completeness,
    portfolio,
    future_state,
    roadmap,
    governance,
    methodology,
    evidence_appendix,
):
    counts = Counter(item.outcome_code for item in portfolio.items)
    executive = [
        _statement(
            f"{len(portfolio.items)} activities were assessed; "
            + ", ".join(
                f"{outcome.value}={counts[outcome]}" for outcome in OutcomeCode
            )
            + f". Package completeness is {completeness.value}.",
            origin=FourGateReportOrigin.ASSESSMENT_FINDING,
            step_ids=[item.step_id for item in portfolio.items],
        )
    ]
    process = [
        _statement(
            f"The assessed current-state process is {process_name}.",
            origin=FourGateReportOrigin.ASSESSMENT_FINDING,
            step_ids=[item.step_id for item in portfolio.items],
        )
    ]
    decisions = [
        _statement(
            f"{item.activity}: {item.final_recommendation}",
            origin=FourGateReportOrigin.ASSESSMENT_FINDING,
            item=item,
            evidence_ids=[e.evidence_id for e in item.material_evidence],
        )
        for item in portfolio.items
    ]
    prioritised = sorted(
        (
            item
            for item in portfolio.items
            if item.priority_eligible
            and item.priority_status is FourGatePriorityStatus.COMPLETE
            and item.priority is not None
        ),
        key=lambda item: (-item.priority.score, item.sequence),
    )
    highest = [
        _statement(
            f"{item.activity}: AI priority {item.priority.score:.2f} ({item.priority.band}).",
            origin=FourGateReportOrigin.ASSESSMENT_FINDING,
            item=item,
        )
        for item in prioritised
    ] or [
        _statement(
            "No complete, eligible AI priority is available.",
            origin=FourGateReportOrigin.ASSESSMENT_FINDING,
        )
    ]
    discovery = [
        _statement(
            f"{item.activity}: {gap.message}",
            origin=FourGateReportOrigin.ASSESSMENT_FINDING,
            item=item,
            evidence_ids=gap.evidence_ids,
        )
        for item in portfolio.items
        for gap in item.information_gaps
        if gap.kind is FourGateInformationGapKind.ACTIVE_DECISION_BLOCKER
    ] or [
        _statement(
            "No activity has an active decision blocker.",
            origin=FourGateReportOrigin.ASSESSMENT_FINDING,
        )
    ]
    other = [
        _statement(
            f"{item.activity}: {item.final_recommendation}",
            origin=FourGateReportOrigin.ASSESSMENT_FINDING,
            item=item,
        )
        for item in portfolio.items
        if item.outcome_code
        not in {
            OutcomeCode.DISCOVERY_REQUIRED,
            OutcomeCode.AI_AUTOMATION,
            OutcomeCode.AI_ASSISTED_WORK,
        }
    ] or [
        _statement(
            "No other intervention or no-change outcome was reached.",
            origin=FourGateReportOrigin.ASSESSMENT_FINDING,
        )
    ]
    future = [
        _statement(
            f"{step.proposed_activity} [{step.status}]",
            origin=FourGateReportOrigin.DERIVED_REPORT_GUIDANCE,
            item=portfolio.items[step.sequence - 1],
        )
        for step in future_state.steps
    ]
    roles = [
        _statement(
            _role_statement(item),
            origin=FourGateReportOrigin.DERIVED_REPORT_GUIDANCE,
            item=item,
        )
        for item in portfolio.items
    ]
    risks = [
        _statement(
            item.statement,
            origin=FourGateReportOrigin.ASSESSMENT_FINDING,
            item=portfolio.items[index],
            evidence_ids=item.evidence_ids,
        )
        for index, item in enumerate(governance)
    ]
    roadmap_statements = [
        _statement(
            item.guidance,
            origin=FourGateReportOrigin.DERIVED_REPORT_GUIDANCE,
            item=portfolio.items[item.sequence - 1],
        )
        for item in roadmap
    ]
    missing = [
        _statement(
            f"{gap.kind.value}: {gap.message}",
            origin=FourGateReportOrigin.ASSESSMENT_FINDING,
            item=item,
            evidence_ids=gap.evidence_ids,
        )
        for item in portfolio.items
        for gap in item.information_gaps
    ] or [
        _statement(
            "No blocking, contextual, or priority-only gap is recorded.",
            origin=FourGateReportOrigin.ASSESSMENT_FINDING,
        )
    ]
    methodology_statements = [
        _statement(
            (
                f"Framework {methodology.framework_id} {methodology.framework_version}; "
                f"decision contract {methodology.decision_contract_version}; policy "
                f"{methodology.policy_id} {methodology.policy_version}; fingerprint "
                f"{methodology.policy_fingerprint}."
            ),
            origin=FourGateReportOrigin.DISCLOSURE,
        ),
        *[
        _statement(text, origin=FourGateReportOrigin.DISCLOSURE)
        for text in methodology.disclosure_statements
        ],
    ]
    appendix = [
        _statement(
            f"{reference.evidence_id}: {reference.document_id} / {reference.block_id} / {reference.source_locator}.",
            origin=FourGateReportOrigin.ASSESSMENT_FINDING,
            evidence_ids=[reference.evidence_id],
        )
        for reference in evidence_appendix
    ]
    appendix.extend(
        _statement(
            (
                f"{item.step_id}: four ordered gates retained as "
                + ", ".join(
                    f"{gate.gate.value}={gate.status.value}"
                    for gate in item.gate_results
                )
                + "; typed output paths, 10 criterion traces, accountability "
                "trace, and 10 capability-signal traces are preserved."
            ),
            origin=FourGateReportOrigin.ASSESSMENT_FINDING,
            item=item,
        )
        for item in portfolio.items
    )
    sections = [
        (FourGateReportSectionId.EXECUTIVE_SUMMARY, "Executive summary", executive),
        (FourGateReportSectionId.PROCESS_ASSESSED, "Process assessed", process),
        (FourGateReportSectionId.ACTIVITY_DECISION_PORTFOLIO, "Activity decision portfolio", decisions),
        (FourGateReportSectionId.HIGHEST_PRIORITY_AI_OPPORTUNITIES, "Highest-priority AI opportunities", highest),
        (FourGateReportSectionId.DISCOVERY_REQUIRED, "Discovery required", discovery),
        (FourGateReportSectionId.OTHER_INTERVENTIONS_AND_NO_CHANGE, "Other interventions and no change", other),
        (FourGateReportSectionId.PROPOSED_FUTURE_STATE_WORKFLOW, "Proposed future-state workflow", future),
        (FourGateReportSectionId.HUMAN_ROLES_AND_CONTROLS, "Human roles and controls", roles),
        (FourGateReportSectionId.RISKS_AND_GOVERNANCE, "Risks and governance", risks),
        (FourGateReportSectionId.ADOPTION_ROADMAP, "Adoption roadmap", roadmap_statements),
        (FourGateReportSectionId.MISSING_INFORMATION, "Missing information", missing),
        (FourGateReportSectionId.METHODOLOGY_AND_POLICY_DISCLOSURE, "Methodology and policy disclosure", methodology_statements),
        (FourGateReportSectionId.EVIDENCE_AND_TRACEABILITY_APPENDIX, "Evidence and traceability appendix", appendix),
    ]
    return FourGateDecisionReportContent(
        sections=[
            FourGateReportSection(
                section_id=section_id,
                title=title,
                statements=statements,
                item_references=list(
                    dict.fromkeys(
                        step_id
                        for statement in statements
                        for step_id in statement.step_ids
                    )
                ),
            )
            for section_id, title, statements in sections
        ]
    )


def _role_statement(item):
    if item.outcome_code is OutcomeCode.NO_CHANGE_JUSTIFIED:
        return (
            f"{item.activity}: no operating-role change is inferred from the "
            "No Change Justified outcome."
        )
    if item.outcome_code is OutcomeCode.AI_AUTOMATION:
        return f"{item.activity}: retain exception handling and accountable oversight."
    if item.outcome_code is OutcomeCode.AI_ASSISTED_WORK:
        return f"{item.activity}: a human operator reviews and remains responsible."
    if (
        item.selected_intervention_family is SelectedInterventionFamily.AI
        and item.autonomy_ceiling is AutonomyCeiling.AI_NOT_PERMITTED
    ):
        return f"{item.activity}: human execution remains because Gate 4 rejected the AI candidate."
    if item.outcome_code is OutcomeCode.KEEP_HUMAN_LED:
        return f"{item.activity}: Gate 3 selected continued human-led execution."
    if item.outcome_code is OutcomeCode.PROCESS_IMPROVEMENT_FIRST:
        return f"{item.activity}: a process owner should address the established readiness blocker."
    if item.outcome_code is OutcomeCode.DISCOVERY_REQUIRED:
        return f"{item.activity}: an evidence owner should resolve only the active blockers."
    return f"{item.activity}: operating roles and controls require confirmation for conventional automation."


def _package_id(integrated):
    semantic_payload = {
        "package_schema_version": PACKAGE_SCHEMA_VERSION,
        "validated_process_fingerprint": (
            integrated.lineage.validated_process_fingerprint
        ),
        "decision_policy_fingerprint": (
            integrated.policy.decision_policy_fingerprint
        ),
        "process_assessment": integrated.process_assessment.model_dump(mode="json"),
        "step_traceability": [
            item.model_dump(mode="json") for item in integrated.step_traceability
        ],
    }
    canonical = json.dumps(
        semantic_payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"four-gate-decision-package-{hashlib.sha256(canonical).hexdigest()}"

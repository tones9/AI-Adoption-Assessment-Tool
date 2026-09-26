"""Deterministic, rule-path-specific evaluation for the four-gate successor."""

from dataclasses import dataclass

from ai_adoption_engine.decision.four_gate_policy import FourGateDecisionPolicy
from ai_adoption_engine.models.enums import Capability, CriterionName, KnowledgeState
from ai_adoption_engine.models.evidence import BooleanCriterionInput, CriterionInput
from ai_adoption_engine.models.four_gate_assessment import (
    AutonomyCeiling,
    BlockingEvidenceGap,
    CapabilitySignalName,
    ChangeDisposition,
    DecisionStatus,
    EvidenceProblemCode,
    FourGateName,
    FourGateResult,
    FourGateStatus,
    GateDecisionCode,
    ReadinessDisposition,
    SelectedInterventionFamily,
)
from ai_adoption_engine.models.process import CapabilitySignals, ProcessStep


_SIGNAL_MAP: tuple[tuple[CapabilitySignalName, Capability], ...] = (
    (
        CapabilitySignalName.READS_UNSTRUCTURED_DOCUMENTS,
        Capability.DOCUMENT_INFORMATION_EXTRACTION,
    ),
    (CapabilitySignalName.CATEGORISES_ITEMS, Capability.CLASSIFICATION),
    (
        CapabilitySignalName.PREDICTS_FUTURE_OUTCOMES,
        Capability.PREDICTION_FORECASTING,
    ),
    (
        CapabilitySignalName.DETECTS_ANOMALIES_OR_PATTERNS,
        Capability.ANOMALY_PATTERN_DETECTION,
    ),
    (CapabilitySignalName.CREATES_NEW_CONTENT, Capability.GENERATIVE_AI),
    (
        CapabilitySignalName.SEARCHES_REFERENCE_KNOWLEDGE,
        Capability.KNOWLEDGE_RETRIEVAL,
    ),
    (CapabilitySignalName.RANKS_OR_SUGGESTS_OPTIONS, Capability.RECOMMENDATION),
    (
        CapabilitySignalName.SUPPORTS_COMPLEX_DECISIONS,
        Capability.DECISION_SUPPORT,
    ),
    (CapabilitySignalName.INTERPRETS_IMAGES_OR_VIDEO, Capability.COMPUTER_VISION),
    (
        CapabilitySignalName.ROUTES_OR_ORCHESTRATES_WORK,
        Capability.WORKFLOW_AUTOMATION,
    ),
)


@dataclass(frozen=True)
class FourGateEvaluation:
    decision_status: DecisionStatus
    change_disposition: ChangeDisposition
    readiness_disposition: ReadinessDisposition
    selected_intervention_family: SelectedInterventionFamily
    autonomy_ceiling: AutonomyCeiling
    gate_results: list[FourGateResult]
    capabilities: list[Capability]

    @property
    def blocking_gaps(self) -> list[BlockingEvidenceGap]:
        return [gap for result in self.gate_results for gap in result.blocking_gaps]


def input_problem_code(
    item: CriterionInput | BooleanCriterionInput,
    policy: FourGateDecisionPolicy,
    *,
    require_evidence: bool,
) -> EvidenceProblemCode | None:
    """Return the first deterministic sufficiency failure for an input."""

    if item.knowledge_state is KnowledgeState.UNKNOWN:
        return EvidenceProblemCode.UNKNOWN
    if item.value is None:
        return EvidenceProblemCode.VALUE_MISSING
    if (
        item.knowledge_state is KnowledgeState.INFERRED
        and (
            item.confidence is None
            or item.confidence < policy.evidence.minimum_inferred_confidence
        )
    ):
        return EvidenceProblemCode.INFERRED_CONFIDENCE_TOO_LOW
    if require_evidence and not item.evidence_ids:
        return EvidenceProblemCode.EVIDENCE_REFERENCE_MISSING
    return None


def map_supported_capabilities(
    signals: CapabilitySignals,
    policy: FourGateDecisionPolicy,
) -> list[Capability]:
    """Map only sufficiently evidenced true signals in stable taxonomy order."""

    capabilities: list[Capability] = []
    for signal_name, capability in _SIGNAL_MAP:
        item = getattr(signals, signal_name.value)
        problem = input_problem_code(
            item,
            policy,
            require_evidence=(
                policy.evidence.require_material_capability_signal_evidence_reference
            ),
        )
        if problem is None and item.value is True:
            capabilities.append(capability)
    return capabilities


def _criterion_gap(
    step: ProcessStep,
    criterion: CriterionName,
    gate: FourGateName,
    policy: FourGateDecisionPolicy,
) -> BlockingEvidenceGap | None:
    item = step.characteristics.criterion(criterion)
    problem = input_problem_code(
        item,
        policy,
        require_evidence=policy.evidence.require_material_criterion_evidence_reference,
    )
    if problem is None:
        return None
    return BlockingEvidenceGap(
        field_name=criterion.value,
        gate=gate,
        problem_code=problem,
        blocking_question=(
            f"What sufficiently supported value is available for {criterion.value}?"
        ),
        evidence_ids=list(item.evidence_ids),
    )


def _accountability_gap(
    step: ProcessStep,
    policy: FourGateDecisionPolicy,
) -> BlockingEvidenceGap | None:
    item = step.characteristics.human_accountability_required
    problem = input_problem_code(
        item,
        policy,
        require_evidence=policy.evidence.require_material_criterion_evidence_reference,
    )
    if problem is None:
        return None
    return BlockingEvidenceGap(
        field_name="human_accountability_required",
        gate=FourGateName.SAFE_AUTONOMY,
        problem_code=problem,
        blocking_question="Must a person remain accountable for the final outcome?",
        evidence_ids=list(item.evidence_ids),
    )


def _signal_problem_code(
    signals: CapabilitySignals,
    signal_name: CapabilitySignalName,
    policy: FourGateDecisionPolicy,
) -> EvidenceProblemCode | None:
    return input_problem_code(
        getattr(signals, signal_name.value),
        policy,
        require_evidence=(
            policy.evidence.require_material_capability_signal_evidence_reference
        ),
    )


def _criterion_evidence_ids(
    step: ProcessStep,
    criteria: list[CriterionName],
    *,
    include_step: bool = False,
    include_accountability: bool = False,
    signals: list[CapabilitySignalName] | None = None,
) -> list[str]:
    evidence_ids: set[str] = set(step.evidence_ids if include_step else [])
    for criterion in criteria:
        evidence_ids.update(step.characteristics.criterion(criterion).evidence_ids)
    if include_accountability:
        evidence_ids.update(
            step.characteristics.human_accountability_required.evidence_ids
        )
    for signal_name in signals or []:
        evidence_ids.update(
            getattr(step.characteristics.capability_signals, signal_name.value).evidence_ids
        )
    return sorted(evidence_ids)


def _not_evaluated(after: FourGateName) -> list[FourGateResult]:
    order = list(FourGateName)
    return [
        FourGateResult(
            gate=gate,
            status=FourGateStatus.NOT_EVALUATED,
            decision_code=GateDecisionCode.NOT_EVALUATED,
            rationale=(
                f"Not evaluated because {after.value} already determined the active path."
            ),
            decided_by=after,
        )
        for gate in order[order.index(after) + 1 :]
    ]


def _finish(
    results: list[FourGateResult],
    *,
    decision_status: DecisionStatus,
    change: ChangeDisposition,
    readiness: ReadinessDisposition,
    selected: SelectedInterventionFamily,
    autonomy: AutonomyCeiling,
    capabilities: list[Capability],
) -> FourGateEvaluation:
    deciding_gate = results[-1].gate
    completed_results = [*results, *_not_evaluated(deciding_gate)]
    return FourGateEvaluation(
        decision_status=decision_status,
        change_disposition=change,
        readiness_disposition=readiness,
        selected_intervention_family=selected,
        autonomy_ceiling=autonomy,
        gate_results=completed_results,
        capabilities=capabilities,
    )


def evaluate_four_gates(
    step: ProcessStep,
    policy: FourGateDecisionPolicy,
) -> FourGateEvaluation:
    """Evaluate one activity with ordered, path-specific successor rules."""

    characteristics = step.characteristics
    capabilities = map_supported_capabilities(
        characteristics.capability_signals,
        policy,
    )
    results: list[FourGateResult] = []

    if policy.evidence.require_step_evidence_reference and not step.evidence_ids:
        gap = BlockingEvidenceGap(
            field_name="activity",
            gate=FourGateName.SHOULD_WE_CHANGE,
            problem_code=EvidenceProblemCode.ACTIVITY_EVIDENCE_MISSING,
            blocking_question="What source evidence supports this activity?",
        )
        results.append(
            FourGateResult(
                gate=FourGateName.SHOULD_WE_CHANGE,
                status=FourGateStatus.BLOCKED_BY_EVIDENCE,
                decision_code=GateDecisionCode.DISCOVERY_REQUIRED,
                rationale="The activity itself has no source evidence reference.",
                blocking_gaps=[gap],
            )
        )
        return _finish(
            results,
            decision_status=DecisionStatus.DISCOVERY_REQUIRED,
            change=ChangeDisposition.NOT_DETERMINED,
            readiness=ReadinessDisposition.NOT_EVALUATED,
            selected=SelectedInterventionFamily.NOT_DETERMINED,
            autonomy=AutonomyCeiling.NOT_DETERMINED,
            capabilities=capabilities,
        )

    business_gap = _criterion_gap(
        step,
        CriterionName.BUSINESS_VALUE,
        FourGateName.SHOULD_WE_CHANGE,
        policy,
    )
    if business_gap:
        results.append(
            FourGateResult(
                gate=FourGateName.SHOULD_WE_CHANGE,
                status=FourGateStatus.BLOCKED_BY_EVIDENCE,
                decision_code=GateDecisionCode.DISCOVERY_REQUIRED,
                rationale="Business-value evidence is insufficient for Gate 1.",
                material_criteria=[CriterionName.BUSINESS_VALUE],
                context_criteria=[CriterionName.REPETITION],
                evidence_ids=_criterion_evidence_ids(
                    step,
                    [CriterionName.BUSINESS_VALUE],
                    include_step=True,
                ),
                blocking_gaps=[business_gap],
            )
        )
        return _finish(
            results,
            decision_status=DecisionStatus.DISCOVERY_REQUIRED,
            change=ChangeDisposition.NOT_DETERMINED,
            readiness=ReadinessDisposition.NOT_EVALUATED,
            selected=SelectedInterventionFamily.NOT_DETERMINED,
            autonomy=AutonomyCeiling.NOT_DETERMINED,
            capabilities=capabilities,
        )

    business_value = characteristics.business_value.value
    assert business_value is not None
    if business_value < policy.gates.minimum_business_value:
        results.append(
            FourGateResult(
                gate=FourGateName.SHOULD_WE_CHANGE,
                status=FourGateStatus.COMPLETED,
                decision_code=GateDecisionCode.NO_CHANGE_JUSTIFIED,
                rationale=(
                    f"Business value is {business_value}/5, below the provisional "
                    f"{policy.gates.minimum_business_value}/5 change threshold."
                ),
                material_criteria=[CriterionName.BUSINESS_VALUE],
                context_criteria=[CriterionName.REPETITION],
                evidence_ids=_criterion_evidence_ids(
                    step,
                    [CriterionName.BUSINESS_VALUE],
                    include_step=True,
                ),
            )
        )
        return _finish(
            results,
            decision_status=DecisionStatus.COMPLETE,
            change=ChangeDisposition.NO_CHANGE_JUSTIFIED,
            readiness=ReadinessDisposition.NOT_EVALUATED,
            selected=SelectedInterventionFamily.NOT_APPLICABLE,
            autonomy=AutonomyCeiling.NOT_APPLICABLE,
            capabilities=capabilities,
        )

    results.append(
        FourGateResult(
            gate=FourGateName.SHOULD_WE_CHANGE,
            status=FourGateStatus.COMPLETED,
            decision_code=GateDecisionCode.CHANGE_JUSTIFIED,
            rationale=(
                f"Business value is {business_value}/5, meeting the provisional "
                f"{policy.gates.minimum_business_value}/5 change threshold."
            ),
            material_criteria=[CriterionName.BUSINESS_VALUE],
            context_criteria=[CriterionName.REPETITION],
            evidence_ids=_criterion_evidence_ids(
                step,
                [CriterionName.BUSINESS_VALUE],
                include_step=True,
            ),
        )
    )

    gate_two_inputs = [
        CriterionName.DATA_READINESS,
        CriterionName.IMPLEMENTATION_COMPLEXITY,
    ]
    gate_two_gaps = {
        criterion: _criterion_gap(
            step,
            criterion,
            FourGateName.IS_IT_READY,
            policy,
        )
        for criterion in gate_two_inputs
    }
    blockers: list[CriterionName] = []
    data_readiness = characteristics.data_readiness.value
    complexity = characteristics.implementation_complexity.value
    if (
        gate_two_gaps[CriterionName.DATA_READINESS] is None
        and data_readiness is not None
        and data_readiness < policy.gates.minimum_data_readiness
    ):
        blockers.append(CriterionName.DATA_READINESS)
    if (
        gate_two_gaps[CriterionName.IMPLEMENTATION_COMPLEXITY] is None
        and complexity is not None
        and complexity
        > policy.gates.maximum_implementation_complexity_for_readiness
    ):
        blockers.append(CriterionName.IMPLEMENTATION_COMPLEXITY)

    gate_two_context = [
        CriterionName.REPETITION,
        CriterionName.PREDICTABILITY,
        CriterionName.AI_CAPABILITY_FIT,
    ]
    if blockers:
        non_blocking_inputs = [
            criterion for criterion in gate_two_inputs if criterion not in blockers
        ]
        blocker_descriptions = []
        if CriterionName.DATA_READINESS in blockers:
            blocker_descriptions.append(
                f"data readiness is {data_readiness}/5 below the provisional minimum"
            )
        if CriterionName.IMPLEMENTATION_COMPLEXITY in blockers:
            blocker_descriptions.append(
                f"implementation complexity is {complexity}/5 above the provisional ceiling"
            )
        results.append(
            FourGateResult(
                gate=FourGateName.IS_IT_READY,
                status=FourGateStatus.COMPLETED_WITH_CONSTRAINTS,
                decision_code=GateDecisionCode.PROCESS_IMPROVEMENT_FIRST,
                rationale=(
                    "Process improvement is required because "
                    + "; ".join(blocker_descriptions)
                    + ". Unrelated unknowns cannot change this readiness result."
                ),
                material_criteria=blockers,
                context_criteria=[*non_blocking_inputs, *gate_two_context],
                evidence_ids=_criterion_evidence_ids(step, blockers),
            )
        )
        return _finish(
            results,
            decision_status=DecisionStatus.COMPLETE,
            change=ChangeDisposition.CHANGE_JUSTIFIED,
            readiness=ReadinessDisposition.PROCESS_IMPROVEMENT_FIRST,
            selected=SelectedInterventionFamily.NOT_APPLICABLE,
            autonomy=AutonomyCeiling.NOT_APPLICABLE,
            capabilities=capabilities,
        )

    unresolved_gate_two = [
        gap for gap in gate_two_gaps.values() if gap is not None
    ]
    if unresolved_gate_two:
        results.append(
            FourGateResult(
                gate=FourGateName.IS_IT_READY,
                status=FourGateStatus.BLOCKED_BY_EVIDENCE,
                decision_code=GateDecisionCode.DISCOVERY_REQUIRED,
                rationale=(
                    "No readiness blocker is established, and material Gate 2 "
                    "evidence remains insufficient."
                ),
                material_criteria=gate_two_inputs,
                context_criteria=gate_two_context,
                evidence_ids=_criterion_evidence_ids(step, gate_two_inputs),
                blocking_gaps=unresolved_gate_two,
            )
        )
        return _finish(
            results,
            decision_status=DecisionStatus.DISCOVERY_REQUIRED,
            change=ChangeDisposition.CHANGE_JUSTIFIED,
            readiness=ReadinessDisposition.NOT_DETERMINED,
            selected=SelectedInterventionFamily.NOT_DETERMINED,
            autonomy=AutonomyCeiling.NOT_DETERMINED,
            capabilities=capabilities,
        )

    assert data_readiness is not None and complexity is not None
    results.append(
        FourGateResult(
            gate=FourGateName.IS_IT_READY,
            status=FourGateStatus.COMPLETED,
            decision_code=GateDecisionCode.READY_FOR_INTERVENTION_SELECTION,
            rationale=(
                f"Data readiness ({data_readiness}/5) and implementation complexity "
                f"({complexity}/5) meet the provisional readiness contract."
            ),
            material_criteria=gate_two_inputs,
            context_criteria=gate_two_context,
            evidence_ids=_criterion_evidence_ids(step, gate_two_inputs),
        )
    )

    conventional_gap = _criterion_gap(
        step,
        CriterionName.CONVENTIONAL_SOLUTION_FIT,
        FourGateName.BEST_INTERVENTION,
        policy,
    )
    if conventional_gap:
        results.append(
            FourGateResult(
                gate=FourGateName.BEST_INTERVENTION,
                status=FourGateStatus.BLOCKED_BY_EVIDENCE,
                decision_code=GateDecisionCode.DISCOVERY_REQUIRED,
                rationale="Conventional-solution fit is required first at Gate 3.",
                material_criteria=[CriterionName.CONVENTIONAL_SOLUTION_FIT],
                evidence_ids=_criterion_evidence_ids(
                    step, [CriterionName.CONVENTIONAL_SOLUTION_FIT]
                ),
                blocking_gaps=[conventional_gap],
            )
        )
        return _finish(
            results,
            decision_status=DecisionStatus.DISCOVERY_REQUIRED,
            change=ChangeDisposition.CHANGE_JUSTIFIED,
            readiness=ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
            selected=SelectedInterventionFamily.NOT_DETERMINED,
            autonomy=AutonomyCeiling.NOT_DETERMINED,
            capabilities=capabilities,
        )

    conventional_fit = characteristics.conventional_solution_fit.value
    assert conventional_fit is not None
    if conventional_fit >= policy.gates.conventional_solution_fit_cutoff:
        results.append(
            FourGateResult(
                gate=FourGateName.BEST_INTERVENTION,
                status=FourGateStatus.COMPLETED,
                decision_code=GateDecisionCode.CONVENTIONAL_AUTOMATION_SELECTED,
                rationale=(
                    f"Conventional-solution fit is {conventional_fit}/5, meeting the "
                    f"provisional {policy.gates.conventional_solution_fit_cutoff}/5 "
                    "cutoff before AI evidence becomes material."
                ),
                material_criteria=[CriterionName.CONVENTIONAL_SOLUTION_FIT],
                evidence_ids=_criterion_evidence_ids(
                    step, [CriterionName.CONVENTIONAL_SOLUTION_FIT]
                ),
            )
        )
        return _finish(
            results,
            decision_status=DecisionStatus.COMPLETE,
            change=ChangeDisposition.CHANGE_JUSTIFIED,
            readiness=ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
            selected=SelectedInterventionFamily.CONVENTIONAL_AUTOMATION,
            autonomy=AutonomyCeiling.NOT_APPLICABLE,
            capabilities=capabilities,
        )

    ai_fit_gap = _criterion_gap(
        step,
        CriterionName.AI_CAPABILITY_FIT,
        FourGateName.BEST_INTERVENTION,
        policy,
    )
    gate_three_criteria = [
        CriterionName.CONVENTIONAL_SOLUTION_FIT,
        CriterionName.AI_CAPABILITY_FIT,
    ]
    if ai_fit_gap:
        results.append(
            FourGateResult(
                gate=FourGateName.BEST_INTERVENTION,
                status=FourGateStatus.BLOCKED_BY_EVIDENCE,
                decision_code=GateDecisionCode.DISCOVERY_REQUIRED,
                rationale=(
                    "Conventional automation is ruled out, so AI capability fit is now "
                    "material and insufficient."
                ),
                material_criteria=gate_three_criteria,
                evidence_ids=_criterion_evidence_ids(step, gate_three_criteria),
                blocking_gaps=[ai_fit_gap],
            )
        )
        return _finish(
            results,
            decision_status=DecisionStatus.DISCOVERY_REQUIRED,
            change=ChangeDisposition.CHANGE_JUSTIFIED,
            readiness=ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
            selected=SelectedInterventionFamily.NOT_DETERMINED,
            autonomy=AutonomyCeiling.NOT_DETERMINED,
            capabilities=capabilities,
        )

    ai_fit = characteristics.ai_capability_fit.value
    assert ai_fit is not None
    if ai_fit < policy.gates.minimum_ai_capability_fit:
        results.append(
            FourGateResult(
                gate=FourGateName.BEST_INTERVENTION,
                status=FourGateStatus.COMPLETED,
                decision_code=GateDecisionCode.KEEP_HUMAN_LED_SELECTED,
                rationale=(
                    f"AI capability fit is {ai_fit}/5, below the provisional "
                    f"{policy.gates.minimum_ai_capability_fit}/5 threshold."
                ),
                material_criteria=gate_three_criteria,
                evidence_ids=_criterion_evidence_ids(step, gate_three_criteria),
            )
        )
        return _finish(
            results,
            decision_status=DecisionStatus.COMPLETE,
            change=ChangeDisposition.CHANGE_JUSTIFIED,
            readiness=ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
            selected=SelectedInterventionFamily.KEEP_HUMAN_LED,
            autonomy=AutonomyCeiling.NOT_APPLICABLE,
            capabilities=capabilities,
        )

    signals = characteristics.capability_signals
    supported_true_signals = [
        signal_name
        for signal_name, _ in _SIGNAL_MAP
        if getattr(signals, signal_name.value).value is True
        and _signal_problem_code(signals, signal_name, policy) is None
    ]
    if supported_true_signals:
        results.append(
            FourGateResult(
                gate=FourGateName.BEST_INTERVENTION,
                status=FourGateStatus.COMPLETED,
                decision_code=GateDecisionCode.AI_SELECTED,
                rationale=(
                    "AI is the selected Gate 3 candidate because conventional automation "
                    "is ruled out and at least one provenance-supported capability maps."
                ),
                material_criteria=gate_three_criteria,
                material_capability_signals=supported_true_signals,
                evidence_ids=_criterion_evidence_ids(
                    step,
                    gate_three_criteria,
                    signals=supported_true_signals,
                ),
            )
        )
    else:
        unresolved_signals = [
            signal_name
            for signal_name, _ in _SIGNAL_MAP
            if _signal_problem_code(signals, signal_name, policy) is not None
        ]
        if unresolved_signals:
            signal_problems = [
                _signal_problem_code(signals, signal_name, policy)
                for signal_name in unresolved_signals
            ]
            aggregate_problem = next(
                problem for problem in signal_problems if problem is not None
            )
            signal_evidence_ids = sorted(
                {
                    evidence_id
                    for signal_name in unresolved_signals
                    for evidence_id in getattr(signals, signal_name.value).evidence_ids
                }
            )
            gap = BlockingEvidenceGap(
                field_name="capability_signals",
                gate=FourGateName.BEST_INTERVENTION,
                problem_code=aggregate_problem,
                blocking_question=(
                    "Which concrete AI capability applies to this activity?"
                ),
                evidence_ids=signal_evidence_ids,
            )
            results.append(
                FourGateResult(
                    gate=FourGateName.BEST_INTERVENTION,
                    status=FourGateStatus.BLOCKED_BY_EVIDENCE,
                    decision_code=GateDecisionCode.DISCOVERY_REQUIRED,
                    rationale=(
                        "AI fit meets threshold, but no concrete capability can be "
                        "determined while potentially relevant signals remain unresolved."
                    ),
                    material_criteria=gate_three_criteria,
                    material_capability_signals=unresolved_signals,
                    evidence_ids=_criterion_evidence_ids(
                        step,
                        gate_three_criteria,
                        signals=unresolved_signals,
                    ),
                    blocking_gaps=[gap],
                )
            )
            return _finish(
                results,
                decision_status=DecisionStatus.DISCOVERY_REQUIRED,
                change=ChangeDisposition.CHANGE_JUSTIFIED,
                readiness=ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
                selected=SelectedInterventionFamily.NOT_DETERMINED,
                autonomy=AutonomyCeiling.NOT_DETERMINED,
                capabilities=capabilities,
            )

        all_signal_names = [signal_name for signal_name, _ in _SIGNAL_MAP]
        results.append(
            FourGateResult(
                gate=FourGateName.BEST_INTERVENTION,
                status=FourGateStatus.COMPLETED,
                decision_code=GateDecisionCode.KEEP_HUMAN_LED_SELECTED,
                rationale=(
                    "All capability signals are sufficiently evidenced false, so no "
                    "concrete AI capability supports the activity."
                ),
                material_criteria=gate_three_criteria,
                material_capability_signals=all_signal_names,
                evidence_ids=_criterion_evidence_ids(
                    step,
                    gate_three_criteria,
                    signals=all_signal_names,
                ),
            )
        )
        return _finish(
            results,
            decision_status=DecisionStatus.COMPLETE,
            change=ChangeDisposition.CHANGE_JUSTIFIED,
            readiness=ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
            selected=SelectedInterventionFamily.KEEP_HUMAN_LED,
            autonomy=AutonomyCeiling.NOT_APPLICABLE,
            capabilities=capabilities,
        )

    residual_criterion = CriterionName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT
    residual_gap = _criterion_gap(
        step,
        residual_criterion,
        FourGateName.SAFE_AUTONOMY,
        policy,
    )
    if residual_gap:
        results.append(
            FourGateResult(
                gate=FourGateName.SAFE_AUTONOMY,
                status=FourGateStatus.BLOCKED_BY_EVIDENCE,
                decision_code=GateDecisionCode.DISCOVERY_REQUIRED,
                rationale="Residual risk is required first because it can veto AI.",
                material_criteria=[residual_criterion],
                evidence_ids=_criterion_evidence_ids(step, [residual_criterion]),
                blocking_gaps=[residual_gap],
            )
        )
        return _finish(
            results,
            decision_status=DecisionStatus.DISCOVERY_REQUIRED,
            change=ChangeDisposition.CHANGE_JUSTIFIED,
            readiness=ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
            selected=SelectedInterventionFamily.AI,
            autonomy=AutonomyCeiling.NOT_DETERMINED,
            capabilities=capabilities,
        )

    residual_risk = characteristics.residual_risk_with_human_oversight.value
    assert residual_risk is not None
    if residual_risk >= policy.gates.unacceptable_residual_risk:
        results.append(
            FourGateResult(
                gate=FourGateName.SAFE_AUTONOMY,
                status=FourGateStatus.COMPLETED_WITH_CONSTRAINTS,
                decision_code=GateDecisionCode.AI_NOT_PERMITTED,
                rationale=(
                    "AI was selected as the Gate 3 candidate but rejected at the safety "
                    f"gate because residual risk is {residual_risk}/5. Keep Human-Led is "
                    "the sole final outcome."
                ),
                material_criteria=[residual_criterion],
                evidence_ids=_criterion_evidence_ids(step, [residual_criterion]),
            )
        )
        return _finish(
            results,
            decision_status=DecisionStatus.COMPLETE,
            change=ChangeDisposition.CHANGE_JUSTIFIED,
            readiness=ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
            selected=SelectedInterventionFamily.AI,
            autonomy=AutonomyCeiling.AI_NOT_PERMITTED,
            capabilities=capabilities,
        )

    judgement_criterion = CriterionName.HUMAN_JUDGEMENT_REQUIREMENT
    risk_criterion = CriterionName.RISK_CONSEQUENCE
    judgement_gap = _criterion_gap(
        step, judgement_criterion, FourGateName.SAFE_AUTONOMY, policy
    )
    risk_gap = _criterion_gap(
        step, risk_criterion, FourGateName.SAFE_AUTONOMY, policy
    )
    accountability_gap = _accountability_gap(step, policy)
    judgement = characteristics.human_judgement_requirement.value
    risk = characteristics.risk_consequence.value
    accountability = characteristics.human_accountability_required.value

    constraints: list[str] = []
    constraint_criteria = [residual_criterion]
    accountability_constraint = False
    if residual_risk >= policy.gates.augment_residual_risk:
        constraints.append(f"residual risk is {residual_risk}/5")
    if (
        judgement_gap is None
        and judgement is not None
        and judgement >= policy.gates.augment_human_judgement
    ):
        constraints.append(f"human judgement is {judgement}/5")
        constraint_criteria.append(judgement_criterion)
    if (
        risk_gap is None
        and risk is not None
        and risk >= policy.gates.augment_risk_consequence
    ):
        constraints.append(f"risk consequence is {risk}/5")
        constraint_criteria.append(risk_criterion)
    if accountability_gap is None and accountability is True:
        constraints.append("human accountability is explicitly required")
        accountability_constraint = True

    if constraints:
        results.append(
            FourGateResult(
                gate=FourGateName.SAFE_AUTONOMY,
                status=FourGateStatus.COMPLETED_WITH_CONSTRAINTS,
                decision_code=GateDecisionCode.AI_ASSISTED_REQUIRED,
                rationale=(
                    "AI assistance is the maximum safe role because "
                    + "; ".join(constraints)
                    + ". Missing peer inputs cannot relax this established ceiling."
                ),
                material_criteria=constraint_criteria,
                accountability_material=accountability_constraint,
                evidence_ids=_criterion_evidence_ids(
                    step,
                    constraint_criteria,
                    include_accountability=accountability_constraint,
                ),
            )
        )
        return _finish(
            results,
            decision_status=DecisionStatus.COMPLETE,
            change=ChangeDisposition.CHANGE_JUSTIFIED,
            readiness=ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
            selected=SelectedInterventionFamily.AI,
            autonomy=AutonomyCeiling.AI_ASSISTED,
            capabilities=capabilities,
        )

    peer_gaps = [
        gap for gap in (judgement_gap, risk_gap, accountability_gap) if gap is not None
    ]
    gate_four_base_criteria = [
        residual_criterion,
        judgement_criterion,
        risk_criterion,
    ]
    if peer_gaps:
        results.append(
            FourGateResult(
                gate=FourGateName.SAFE_AUTONOMY,
                status=FourGateStatus.BLOCKED_BY_EVIDENCE,
                decision_code=GateDecisionCode.DISCOVERY_REQUIRED,
                rationale=(
                    "No assistance constraint is established, and evidence that could "
                    "still change the autonomy ceiling is insufficient."
                ),
                material_criteria=gate_four_base_criteria,
                accountability_material=True,
                evidence_ids=_criterion_evidence_ids(
                    step,
                    gate_four_base_criteria,
                    include_accountability=True,
                ),
                blocking_gaps=peer_gaps,
            )
        )
        return _finish(
            results,
            decision_status=DecisionStatus.DISCOVERY_REQUIRED,
            change=ChangeDisposition.CHANGE_JUSTIFIED,
            readiness=ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
            selected=SelectedInterventionFamily.AI,
            autonomy=AutonomyCeiling.NOT_DETERMINED,
            capabilities=capabilities,
        )

    assert judgement is not None and risk is not None and accountability is not None
    strict_criteria = [
        judgement_criterion,
        risk_criterion,
        residual_criterion,
    ]
    strict_failures: list[str] = []
    if data_readiness < policy.gates.automate_minimum_data_readiness:
        strict_failures.append(
            "the validated Gate 2 data-readiness finding is "
            f"{data_readiness}/5, below the provisional automation minimum"
        )
    if judgement > policy.gates.automate_maximum_human_judgement:
        strict_failures.append(f"human judgement is {judgement}/5")
    if risk > policy.gates.automate_maximum_risk_consequence:
        strict_failures.append(f"risk consequence is {risk}/5")
    if residual_risk > policy.gates.automate_maximum_residual_risk:
        strict_failures.append(f"residual risk is {residual_risk}/5")
    if accountability:
        strict_failures.append("human accountability is required")
    if strict_failures:
        results.append(
            FourGateResult(
                gate=FourGateName.SAFE_AUTONOMY,
                status=FourGateStatus.COMPLETED_WITH_CONSTRAINTS,
                decision_code=GateDecisionCode.AI_ASSISTED_REQUIRED,
                rationale=(
                    "AI assistance is required because strict automation conditions fail: "
                    + "; ".join(strict_failures)
                    + ". Predictability cannot restore automation on this path."
                ),
                material_criteria=strict_criteria,
                accountability_material=True,
                evidence_ids=_criterion_evidence_ids(
                    step,
                    strict_criteria,
                    include_accountability=True,
                ),
            )
        )
        return _finish(
            results,
            decision_status=DecisionStatus.COMPLETE,
            change=ChangeDisposition.CHANGE_JUSTIFIED,
            readiness=ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
            selected=SelectedInterventionFamily.AI,
            autonomy=AutonomyCeiling.AI_ASSISTED,
            capabilities=capabilities,
        )

    predictability_criterion = CriterionName.PREDICTABILITY
    predictability_gap = _criterion_gap(
        step,
        predictability_criterion,
        FourGateName.SAFE_AUTONOMY,
        policy,
    )
    final_material_criteria = [*strict_criteria, predictability_criterion]
    if predictability_gap:
        results.append(
            FourGateResult(
                gate=FourGateName.SAFE_AUTONOMY,
                status=FourGateStatus.BLOCKED_BY_EVIDENCE,
                decision_code=GateDecisionCode.DISCOVERY_REQUIRED,
                rationale=(
                    "Every other automation condition passes, so predictability is now "
                    "material and insufficient."
                ),
                material_criteria=final_material_criteria,
                accountability_material=True,
                evidence_ids=_criterion_evidence_ids(
                    step,
                    final_material_criteria,
                    include_accountability=True,
                ),
                blocking_gaps=[predictability_gap],
            )
        )
        return _finish(
            results,
            decision_status=DecisionStatus.DISCOVERY_REQUIRED,
            change=ChangeDisposition.CHANGE_JUSTIFIED,
            readiness=ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
            selected=SelectedInterventionFamily.AI,
            autonomy=AutonomyCeiling.NOT_DETERMINED,
            capabilities=capabilities,
        )

    predictability = characteristics.predictability.value
    assert predictability is not None
    if predictability < policy.gates.automate_minimum_predictability:
        status = FourGateStatus.COMPLETED_WITH_CONSTRAINTS
        decision_code = GateDecisionCode.AI_ASSISTED_REQUIRED
        autonomy = AutonomyCeiling.AI_ASSISTED
        rationale = (
            "The validated Gate 2 data-readiness finding remains sufficient for "
            f"automation, but predictability is {predictability}/5, below the "
            "provisional automation minimum, so AI-Assisted Work is the maximum "
            "safe role."
        )
    else:
        status = FourGateStatus.COMPLETED
        decision_code = GateDecisionCode.AI_AUTOMATION_PERMITTED
        autonomy = AutonomyCeiling.AI_AUTOMATION
        rationale = (
            "Every provisional automation condition is satisfied, including the "
            f"validated Gate 2 data-readiness finding at {data_readiness}/5 and "
            f"predictability at {predictability}/5."
        )
    results.append(
        FourGateResult(
            gate=FourGateName.SAFE_AUTONOMY,
            status=status,
            decision_code=decision_code,
            rationale=rationale,
            material_criteria=final_material_criteria,
            accountability_material=True,
            evidence_ids=_criterion_evidence_ids(
                step,
                final_material_criteria,
                include_accountability=True,
            ),
        )
    )
    return _finish(
        results,
        decision_status=DecisionStatus.COMPLETE,
        change=ChangeDisposition.CHANGE_JUSTIFIED,
        readiness=ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
        selected=SelectedInterventionFamily.AI,
        autonomy=autonomy,
        capabilities=capabilities,
    )

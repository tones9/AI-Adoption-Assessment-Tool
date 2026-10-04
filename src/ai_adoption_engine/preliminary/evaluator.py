"""Deterministic, persistence-free Preliminary Assessment evaluator."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from ai_adoption_engine.application.fingerprints import fingerprint_business_process
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.preliminary_assessment import (
    CAPABILITY_INPUT_NAMES,
    PRELIMINARY_ASSESSMENT_DISCLAIMER,
    PRELIMINARY_INPUT_ORDER,
    AssessmentJourney,
    DocumentedFact,
    EvidenceCoverageConfidence,
    JourneySelection,
    NextEvidenceToCollect,
    PreliminaryActivityResult,
    PreliminaryAssessment,
    PreliminaryAssessmentLineage,
    PreliminaryComparisonClause,
    PreliminaryComparisonOperator,
    PreliminaryConfidence,
    PreliminaryDecidingRuleCode,
    PreliminaryDecisionInputTrace,
    PreliminaryEvaluationStage,
    PreliminaryEvidenceClassification,
    PreliminaryInputName,
    PreliminaryRuleComparison,
    PreliminaryUnknown,
    PreliminaryValueType,
    ProvisionalDirection,
    ReasonableInference,
)
from ai_adoption_engine.models.preliminary_evaluation import (
    PreliminaryEvaluationError,
    PreliminaryEvaluationFailure,
    PreliminaryEvaluationFailureCode,
    PreliminaryEvaluationResult,
    PreliminaryEvaluationSuccess,
)
from ai_adoption_engine.models.review import (
    ApprovedProcessReview,
    ConflictStatus,
    InformationOrigin,
    ReviewAction,
    ReviewDisposition,
    ReviewStatus,
    ReviewedAssertion,
    ReviewedProcessStep,
)
from ai_adoption_engine.preliminary.rules import (
    PRELIMINARY_EVALUATOR_RULES_V0_1,
    PreliminaryEvaluatorRules,
)
from ai_adoption_engine.review.approval import _project_business_process


_CAPABILITY_FIELD_NAMES = tuple(
    item.value.removeprefix("capability.") for item in CAPABILITY_INPUT_NAMES
)


@dataclass(frozen=True)
class _Input:
    name: PreliminaryInputName
    path: str
    value_type: PreliminaryValueType
    value: int | bool | str | None
    classification: PreliminaryEvidenceClassification
    evidence_item_ids: tuple[str, ...]
    facts: tuple[DocumentedFact, ...]
    inference: ReasonableInference | None
    unknown: PreliminaryUnknown | None


@dataclass(frozen=True)
class _Material:
    stage: PreliminaryEvaluationStage
    comparison: PreliminaryRuleComparison


class PreliminaryAssessmentEvaluator:
    """Evaluate one immutable approved review without persistence or formal gates."""

    def __init__(
        self,
        *,
        rules: PreliminaryEvaluatorRules = PRELIMINARY_EVALUATOR_RULES_V0_1,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._rules = rules
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: f"pa-{uuid4()}")

    def evaluate(self, approved_review: ApprovedProcessReview) -> PreliminaryEvaluationResult:
        rule_error = self._validate_rules()
        if rule_error is not None:
            return self._failure(rule_error)
        if not isinstance(approved_review, ApprovedProcessReview):
            return self._failure(
                PreliminaryEvaluationError(
                    code=PreliminaryEvaluationFailureCode.APPROVED_REVIEW_REQUIRED,
                    message="Evaluation requires an ApprovedProcessReview.",
                )
            )

        try:
            approved = ApprovedProcessReview.model_validate(
                approved_review.model_dump(mode="python")
            )
        except (AttributeError, ValidationError) as exc:
            return self._failure(
                PreliminaryEvaluationError(
                    code=PreliminaryEvaluationFailureCode.INVALID_APPROVAL_ARTIFACT,
                    message=f"The approved review artifact is invalid: {exc}",
                )
            )

        approval_error = self._validate_approval(approved)
        if approval_error is not None:
            return self._failure(approval_error)
        projection_error = self._validate_projection(approved)
        if projection_error is not None:
            return self._failure(projection_error)

        candidate = approved.review.original_candidate
        source_error = self._validate_source_documents(approved)
        if source_error is not None:
            return self._failure(source_error)

        activity_results: list[PreliminaryActivityResult] = []
        try:
            retained_steps = sorted(
                (step for step in approved.review.steps if step.retained),
                key=lambda item: item.sequence,
            )
            for step in retained_steps:
                activity_results.append(
                    self._evaluate_activity(step, approved.review.conflicts)
                )

            created_at = self._clock()
            if created_at.tzinfo is None or created_at.utcoffset() is None:
                raise ValueError("Injected clock must return a timezone-aware datetime")
            assessment_id = self._id_factory()
            if not isinstance(assessment_id, str) or not assessment_id.strip():
                raise ValueError("Injected ID factory must return a non-blank string")
            approval_event = next(
                event
                for event in approved.review.events
                if event.action is ReviewAction.APPROVE
            )
            process_confidence = min(
                (item.confidence.level for item in activity_results),
                key=_confidence_rank,
            )
            assessment = PreliminaryAssessment(
                schema_version="preliminary-assessment.v0.1",
                assessment_kind="PRELIMINARY_ASSESSMENT",
                preliminary_assessment_id=assessment_id,
                created_at=created_at,
                rule_set=self._rules.reference(),
                journey_selection=JourneySelection(
                    schema_version="journey-selection.v0.1",
                    journey=AssessmentJourney.EXPLORE_PROCESS,
                ),
                lineage=PreliminaryAssessmentLineage(
                    source_document_id=candidate.source_document_id,
                    extraction_run_id=candidate.extraction_run_id,
                    review_id=approved.review.review_id,
                    approval_event_id=approval_event.event_id,
                    approval_statement=approved.approval.approval_statement,
                    approved_at=approved.approval.approved_at,
                    validated_process_id=approved.business_process.process_id,
                    validated_process_fingerprint=fingerprint_business_process(
                        approved.business_process
                    ),
                ),
                process_id=approved.business_process.process_id,
                process_name=approved.business_process.name,
                confidence=EvidenceCoverageConfidence(
                    level=process_confidence,
                    basis="Weakest activity evidence-coverage confidence.",
                ),
                activity_results=tuple(activity_results),
                disclaimer=PRELIMINARY_ASSESSMENT_DISCLAIMER,
            )
        except (StopIteration, ValidationError, ValueError, TypeError) as exc:
            return self._failure(
                PreliminaryEvaluationError(
                    code=PreliminaryEvaluationFailureCode.OUTPUT_VALIDATION_FAILED,
                    message=f"Preliminary Assessment output validation failed: {exc}",
                )
            )
        return PreliminaryEvaluationSuccess(assessment=assessment)

    def _validate_rules(self) -> PreliminaryEvaluationError | None:
        if (
            self._rules.canonical_json_bytes()
            != PRELIMINARY_EVALUATOR_RULES_V0_1.canonical_json_bytes()
        ):
            return PreliminaryEvaluationError(
                code=PreliminaryEvaluationFailureCode.INVALID_RULE_SET,
                message="The evaluator rule set is not the approved v0.1 artifact.",
                field_path="rules",
            )
        return None

    def _validate_approval(
        self, approved: ApprovedProcessReview
    ) -> PreliminaryEvaluationError | None:
        review = approved.review
        if review.status is not ReviewStatus.APPROVED:
            return PreliminaryEvaluationError(
                code=PreliminaryEvaluationFailureCode.INVALID_APPROVAL_ARTIFACT,
                message="The review artifact is not marked approved.",
                field_path="review.status",
            )
        if any(
            item.blocking and item.status is ConflictStatus.OPEN
            for item in review.conflicts
        ):
            return PreliminaryEvaluationError(
                code=PreliminaryEvaluationFailureCode.BLOCKING_REVIEW_CONFLICT,
                message="The approved review contains an unresolved blocking conflict.",
                field_path="review.conflicts",
            )
        approval_events = [
            event for event in review.events if event.action is ReviewAction.APPROVE
        ]
        if len(approval_events) != 1:
            return PreliminaryEvaluationError(
                code=PreliminaryEvaluationFailureCode.INVALID_APPROVAL_ARTIFACT,
                message="The review must contain exactly one approval event.",
                field_path="review.events",
            )
        if approval_events[0].occurred_at != approved.approval.approved_at:
            return PreliminaryEvaluationError(
                code=PreliminaryEvaluationFailureCode.INVALID_APPROVAL_ARTIFACT,
                message="Approval event time does not match explicit approval metadata.",
                field_path="approval.approved_at",
            )
        retained_steps = [item for item in review.steps if item.retained]
        if (
            not review.order_accepted
            or not retained_steps
            or not _approval_confirmed(review.process_name)
            or any(not _approval_confirmed(item.activity) for item in retained_steps)
        ):
            return PreliminaryEvaluationError(
                code=PreliminaryEvaluationFailureCode.INVALID_APPROVAL_ARTIFACT,
                message=(
                    "The approved snapshot no longer satisfies its process identity, "
                    "retained-step, activity, and ordering approval invariants."
                ),
                field_path="review",
            )
        retained_ids = {item.candidate_step_id for item in retained_steps}
        if any(
            dependency.target_candidate_step_id is None
            or dependency.target_candidate_step_id not in retained_ids
            or dependency.target_candidate_step_id == step.candidate_step_id
            for step in retained_steps
            for dependency in step.dependencies
            if dependency.retained
        ):
            return PreliminaryEvaluationError(
                code=PreliminaryEvaluationFailureCode.INVALID_APPROVAL_ARTIFACT,
                message="The approved snapshot contains an invalid retained dependency.",
                field_path="review.steps.dependencies",
            )
        return None

    def _validate_projection(
        self, approved: ApprovedProcessReview
    ) -> PreliminaryEvaluationError | None:
        expected_process = _project_business_process(approved.review)
        if expected_process.model_dump(mode="json") != approved.business_process.model_dump(
            mode="json"
        ):
            return PreliminaryEvaluationError(
                code=PreliminaryEvaluationFailureCode.INVALID_PROCESS_PROJECTION,
                message=(
                    "The validated process projection is inconsistent with its "
                    "approved review snapshot."
                ),
                field_path="business_process",
            )
        return None

    def _validate_source_documents(
        self, approved: ApprovedProcessReview
    ) -> PreliminaryEvaluationError | None:
        expected = approved.review.original_candidate.source_document_id
        for step in approved.review.steps:
            for path, assertion in _evaluation_assertions(step):
                if not assertion.retained:
                    continue
                if assertion.disposition not in {
                    ReviewDisposition.ACCEPTED,
                    ReviewDisposition.CORRECTED,
                }:
                    continue
                if assertion.origin not in {
                    InformationOrigin.DOCUMENT_SUPPORTED,
                    InformationOrigin.MODEL_INFERRED,
                }:
                    continue
                for evidence in assertion.evidence:
                    if evidence.document_id != expected:
                        return PreliminaryEvaluationError(
                            code=PreliminaryEvaluationFailureCode.SOURCE_DOCUMENT_MISMATCH,
                            message=(
                                "Preliminary Assessment inputs must come from the "
                                "approved current-state process document."
                            ),
                            field_path=path,
                        )
        return None

    def _failure(
        self, error: PreliminaryEvaluationError
    ) -> PreliminaryEvaluationFailure:
        return PreliminaryEvaluationFailure(
            rule_set=PRELIMINARY_EVALUATOR_RULES_V0_1.reference(), errors=(error,)
        )

    def _evaluate_activity(
        self, step: ReviewedProcessStep, conflicts: list[Any]
    ) -> PreliminaryActivityResult:
        inputs = self._activity_inputs(step, conflicts)
        code, material = self._select(inputs)
        direction = _direction(code)
        material_inferences = sum(
            inputs[name].classification
            is PreliminaryEvidenceClassification.REASONABLE_INFERENCE
            for name in material
        )
        if (
            direction is ProvisionalDirection.INSUFFICIENT_BASIS
            or code
            is PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_AUTONOMY_UNKNOWN
            or material_inferences >= 2
        ):
            confidence = PreliminaryConfidence.LOW
        elif material_inferences == 1:
            confidence = PreliminaryConfidence.MEDIUM
        else:
            confidence = PreliminaryConfidence.HIGH

        facts = _unique_facts(inputs)
        inferences = tuple(
            item.inference for item in inputs.values() if item.inference is not None
        )
        unknowns = tuple(
            item.unknown for item in inputs.values() if item.unknown is not None
        )
        trace = tuple(
            PreliminaryDecisionInputTrace(
                input_name=name,
                reviewed_field_path=inputs[name].path,
                value_type=inputs[name].value_type,
                normalized_value=inputs[name].value,
                classification=inputs[name].classification,
                evidence_item_ids=inputs[name].evidence_item_ids,
                material=name in material,
                material_stage=material[name].stage if name in material else None,
                comparison=material[name].comparison if name in material else None,
            )
            for name in PRELIMINARY_INPUT_ORDER
        )
        requests = tuple(
            NextEvidenceToCollect(
                request_id=_stable_id("request", step.candidate_step_id, item.unknown_id),
                description=item.evidence_needed or item.unresolved_question,
                resolves_unknown_ids=(item.unknown_id,),
                suggested_owner=item.owner_needed,
            )
            for item in unknowns
        )
        return PreliminaryActivityResult(
            step_id=step.candidate_step_id,
            activity=str(step.activity.value),
            provisional_direction=direction,
            deciding_rule_code=code,
            confidence=EvidenceCoverageConfidence(
                level=confidence,
                basis=_confidence_basis(confidence, code, material_inferences),
            ),
            rationale=_rationale(code),
            documented_facts=facts,
            reasonable_inferences=inferences,
            unknowns=unknowns,
            next_evidence_to_collect=requests,
            decision_input_trace=trace,
        )

    def _activity_inputs(
        self, step: ReviewedProcessStep, conflicts: list[Any]
    ) -> dict[PreliminaryInputName, _Input]:
        base = f"steps.{step.candidate_step_id}"
        assertions: dict[PreliminaryInputName, tuple[str, PreliminaryValueType, ReviewedAssertion]] = {
            PreliminaryInputName.ACTIVITY_IDENTITY: (
                f"{base}.activity",
                PreliminaryValueType.TEXT,
                step.activity,
            ),
            PreliminaryInputName.HUMAN_ACCOUNTABILITY_REQUIRED: (
                f"{base}.human_accountability_required",
                PreliminaryValueType.BOOLEAN,
                step.human_accountability_required,
            ),
        }
        criteria = {item.name: item.assertion for item in step.criteria}
        for input_name in (
            PreliminaryInputName.BUSINESS_VALUE,
            PreliminaryInputName.DATA_READINESS,
            PreliminaryInputName.IMPLEMENTATION_COMPLEXITY,
            PreliminaryInputName.CONVENTIONAL_SOLUTION_FIT,
            PreliminaryInputName.AI_CAPABILITY_FIT,
            PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT,
            PreliminaryInputName.HUMAN_JUDGEMENT_REQUIREMENT,
            PreliminaryInputName.RISK_CONSEQUENCE,
            PreliminaryInputName.PREDICTABILITY,
            PreliminaryInputName.REPETITION,
        ):
            criterion = CriterionName(input_name.value)
            assertions[input_name] = (
                f"{base}.criteria.{input_name.value}",
                PreliminaryValueType.ORDINAL,
                criteria[criterion],
            )
        signals = {item.name: item.assertion for item in step.capability_signals}
        for input_name, field_name in zip(
            CAPABILITY_INPUT_NAMES, _CAPABILITY_FIELD_NAMES, strict=True
        ):
            assertions[input_name] = (
                f"{base}.capability_signals.{field_name}",
                PreliminaryValueType.BOOLEAN,
                signals[field_name],
            )

        inputs: dict[PreliminaryInputName, _Input] = {}
        for name in PRELIMINARY_INPUT_ORDER:
            path, value_type, assertion = assertions[name]
            conflicted = any(
                item.status is ConflictStatus.OPEN and item.field_path == path
                for item in conflicts
            )
            inputs[name] = _input_from_assertion(
                step.candidate_step_id,
                name,
                path,
                value_type,
                assertion,
                conflicted=conflicted,
            )
        return inputs

    def _select(
        self, inputs: dict[PreliminaryInputName, _Input]
    ) -> tuple[PreliminaryDecidingRuleCode, dict[PreliminaryInputName, _Material]]:
        t = self._rules.thresholds
        material: dict[PreliminaryInputName, _Material] = {}

        def mark(
            name: PreliminaryInputName,
            stage: PreliminaryEvaluationStage,
            clause: PreliminaryComparisonClause,
            operator: PreliminaryComparisonOperator,
            threshold: int | bool | str | None = None,
        ) -> None:
            material[name] = _Material(
                stage,
                PreliminaryRuleComparison(
                    clause_code=clause,
                    operator=operator,
                    threshold_value=threshold,
                    matched=True,
                ),
            )

        activity = inputs[PreliminaryInputName.ACTIVITY_IDENTITY]
        if _unresolved(activity):
            mark(
                PreliminaryInputName.ACTIVITY_IDENTITY,
                PreliminaryEvaluationStage.CHANGE_CASE,
                PreliminaryComparisonClause.ACTIVITY_UNRESOLVED,
                _unresolved_operator(activity),
            )
            return PreliminaryDecidingRuleCode.INSUFFICIENT_ACTIVITY_IDENTITY, material
        mark(
            PreliminaryInputName.ACTIVITY_IDENTITY,
            PreliminaryEvaluationStage.CHANGE_CASE,
            PreliminaryComparisonClause.ACTIVITY_PRESENT,
            PreliminaryComparisonOperator.PRESENT,
        )

        business = inputs[PreliminaryInputName.BUSINESS_VALUE]
        if _unresolved(business):
            mark(
                PreliminaryInputName.BUSINESS_VALUE,
                PreliminaryEvaluationStage.CHANGE_CASE,
                PreliminaryComparisonClause.BUSINESS_UNRESOLVED,
                _unresolved_operator(business),
            )
            return PreliminaryDecidingRuleCode.INSUFFICIENT_CHANGE_CASE, material
        if business.value < t.business_value_minimum:  # type: ignore[operator]
            mark(
                PreliminaryInputName.BUSINESS_VALUE,
                PreliminaryEvaluationStage.CHANGE_CASE,
                PreliminaryComparisonClause.BUSINESS_LT_MINIMUM,
                PreliminaryComparisonOperator.LT,
                t.business_value_minimum,
            )
            return PreliminaryDecidingRuleCode.LIKELY_NO_CHANGE, material
        mark(
            PreliminaryInputName.BUSINESS_VALUE,
            PreliminaryEvaluationStage.CHANGE_CASE,
            PreliminaryComparisonClause.BUSINESS_GTE_MINIMUM,
            PreliminaryComparisonOperator.GTE,
            t.business_value_minimum,
        )

        data = inputs[PreliminaryInputName.DATA_READINESS]
        complexity = inputs[PreliminaryInputName.IMPLEMENTATION_COMPLEXITY]
        if _unresolved(data) or _unresolved(complexity):
            for name, item, clause in (
                (PreliminaryInputName.DATA_READINESS, data, PreliminaryComparisonClause.DATA_UNRESOLVED),
                (PreliminaryInputName.IMPLEMENTATION_COMPLEXITY, complexity, PreliminaryComparisonClause.COMPLEXITY_UNRESOLVED),
            ):
                if _unresolved(item):
                    mark(name, PreliminaryEvaluationStage.READINESS, clause, _unresolved_operator(item))
                else:
                    mark(name, PreliminaryEvaluationStage.READINESS, _readiness_pass_clause(name), _readiness_pass_operator(name), _readiness_threshold(name, t))
            return PreliminaryDecidingRuleCode.INSUFFICIENT_READINESS, material
        data_blocked = data.value < t.data_readiness_minimum  # type: ignore[operator]
        complexity_blocked = complexity.value > t.implementation_complexity_ready_maximum  # type: ignore[operator]
        if data_blocked or complexity_blocked:
            mark(
                PreliminaryInputName.DATA_READINESS,
                PreliminaryEvaluationStage.READINESS,
                PreliminaryComparisonClause.DATA_LT_MINIMUM if data_blocked else PreliminaryComparisonClause.DATA_GTE_MINIMUM,
                PreliminaryComparisonOperator.LT if data_blocked else PreliminaryComparisonOperator.GTE,
                t.data_readiness_minimum,
            )
            mark(
                PreliminaryInputName.IMPLEMENTATION_COMPLEXITY,
                PreliminaryEvaluationStage.READINESS,
                PreliminaryComparisonClause.COMPLEXITY_GT_READY_MAX if complexity_blocked else PreliminaryComparisonClause.COMPLEXITY_LTE_READY_MAX,
                PreliminaryComparisonOperator.GT if complexity_blocked else PreliminaryComparisonOperator.LTE,
                t.implementation_complexity_ready_maximum,
            )
            return PreliminaryDecidingRuleCode.LIKELY_PROCESS_IMPROVEMENT_FIRST, material
        mark(PreliminaryInputName.DATA_READINESS, PreliminaryEvaluationStage.READINESS, PreliminaryComparisonClause.DATA_GTE_MINIMUM, PreliminaryComparisonOperator.GTE, t.data_readiness_minimum)
        mark(PreliminaryInputName.IMPLEMENTATION_COMPLEXITY, PreliminaryEvaluationStage.READINESS, PreliminaryComparisonClause.COMPLEXITY_LTE_READY_MAX, PreliminaryComparisonOperator.LTE, t.implementation_complexity_ready_maximum)

        conventional = inputs[PreliminaryInputName.CONVENTIONAL_SOLUTION_FIT]
        if _unresolved(conventional):
            mark(PreliminaryInputName.CONVENTIONAL_SOLUTION_FIT, PreliminaryEvaluationStage.INTERVENTION_SELECTION, PreliminaryComparisonClause.CONVENTIONAL_UNRESOLVED, _unresolved_operator(conventional))
            return PreliminaryDecidingRuleCode.INSUFFICIENT_CONVENTIONAL_FIT, material
        if conventional.value >= t.conventional_solution_fit_cutoff:  # type: ignore[operator]
            mark(PreliminaryInputName.CONVENTIONAL_SOLUTION_FIT, PreliminaryEvaluationStage.INTERVENTION_SELECTION, PreliminaryComparisonClause.CONVENTIONAL_GTE_CUTOFF, PreliminaryComparisonOperator.GTE, t.conventional_solution_fit_cutoff)
            return PreliminaryDecidingRuleCode.LIKELY_CONVENTIONAL_AUTOMATION, material
        mark(PreliminaryInputName.CONVENTIONAL_SOLUTION_FIT, PreliminaryEvaluationStage.INTERVENTION_SELECTION, PreliminaryComparisonClause.CONVENTIONAL_LT_CUTOFF, PreliminaryComparisonOperator.LT, t.conventional_solution_fit_cutoff)

        ai_fit = inputs[PreliminaryInputName.AI_CAPABILITY_FIT]
        if _unresolved(ai_fit):
            mark(PreliminaryInputName.AI_CAPABILITY_FIT, PreliminaryEvaluationStage.AI_CAPABILITY, PreliminaryComparisonClause.AI_FIT_UNRESOLVED, _unresolved_operator(ai_fit))
            return PreliminaryDecidingRuleCode.INSUFFICIENT_AI_FIT, material
        if ai_fit.value < t.ai_capability_fit_minimum:  # type: ignore[operator]
            mark(PreliminaryInputName.AI_CAPABILITY_FIT, PreliminaryEvaluationStage.AI_CAPABILITY, PreliminaryComparisonClause.AI_FIT_LT_MINIMUM, PreliminaryComparisonOperator.LT, t.ai_capability_fit_minimum)
            return PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_LOW_AI_FIT, material
        mark(PreliminaryInputName.AI_CAPABILITY_FIT, PreliminaryEvaluationStage.AI_CAPABILITY, PreliminaryComparisonClause.AI_FIT_GTE_MINIMUM, PreliminaryComparisonOperator.GTE, t.ai_capability_fit_minimum)

        capabilities = [inputs[name] for name in CAPABILITY_INPUT_NAMES]
        true_capability = next((item for item in capabilities if item.value is True and not _unresolved(item)), None)
        if true_capability is None:
            unresolved_capabilities = [item for item in capabilities if _unresolved(item)]
            for name, item in zip(CAPABILITY_INPUT_NAMES, capabilities, strict=True):
                if _unresolved(item):
                    mark(name, PreliminaryEvaluationStage.AI_CAPABILITY, PreliminaryComparisonClause.CAPABILITY_UNRESOLVED, _unresolved_operator(item))
                else:
                    mark(name, PreliminaryEvaluationStage.AI_CAPABILITY, PreliminaryComparisonClause.CAPABILITY_FALSE, PreliminaryComparisonOperator.IS_FALSE)
            if unresolved_capabilities:
                return PreliminaryDecidingRuleCode.INSUFFICIENT_AI_CAPABILITY, material
            return PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_NO_CAPABILITY, material
        capability_name = next(
            name for name in CAPABILITY_INPUT_NAMES if inputs[name] is true_capability
        )
        mark(capability_name, PreliminaryEvaluationStage.AI_CAPABILITY, PreliminaryComparisonClause.CAPABILITY_TRUE, PreliminaryComparisonOperator.IS_TRUE)

        residual = inputs[PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT]
        if _unresolved(residual):
            mark(PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT, PreliminaryEvaluationStage.SAFETY_PERMISSION, PreliminaryComparisonClause.RESIDUAL_UNRESOLVED, _unresolved_operator(residual))
            return PreliminaryDecidingRuleCode.INSUFFICIENT_RESIDUAL_RISK, material
        if residual.value >= t.residual_risk_veto_minimum:  # type: ignore[operator]
            mark(PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT, PreliminaryEvaluationStage.SAFETY_PERMISSION, PreliminaryComparisonClause.RESIDUAL_GTE_VETO, PreliminaryComparisonOperator.GTE, t.residual_risk_veto_minimum)
            return PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_SAFETY_VETO, material
        mark(PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT, PreliminaryEvaluationStage.SAFETY_PERMISSION, PreliminaryComparisonClause.RESIDUAL_LT_VETO, PreliminaryComparisonOperator.LT, t.residual_risk_veto_minimum)

        autonomy = (
            PreliminaryInputName.HUMAN_JUDGEMENT_REQUIREMENT,
            PreliminaryInputName.RISK_CONSEQUENCE,
            PreliminaryInputName.HUMAN_ACCOUNTABILITY_REQUIRED,
            PreliminaryInputName.PREDICTABILITY,
        )
        unresolved_autonomy = [name for name in autonomy if _unresolved(inputs[name])]
        if unresolved_autonomy:
            for name in unresolved_autonomy:
                mark(name, PreliminaryEvaluationStage.AUTONOMY, _autonomy_unknown_clause(name), _unresolved_operator(inputs[name]))
            return PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_AUTONOMY_UNKNOWN, material

        constraint = _first_assistance_constraint(inputs, t)
        if constraint is not None:
            name, clause, operator, threshold = constraint
            mark(name, PreliminaryEvaluationStage.AUTONOMY, clause, operator, threshold)
            return PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_CONSTRAINT, material

        mark(PreliminaryInputName.DATA_READINESS, PreliminaryEvaluationStage.AUTONOMY, PreliminaryComparisonClause.DATA_GTE_AUTOMATION, PreliminaryComparisonOperator.GTE, t.automation_data_readiness_minimum)
        mark(PreliminaryInputName.IMPLEMENTATION_COMPLEXITY, PreliminaryEvaluationStage.AUTONOMY, PreliminaryComparisonClause.COMPLEXITY_LTE_AUTOMATION_MAX, PreliminaryComparisonOperator.LTE, t.automation_complexity_maximum)
        mark(PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT, PreliminaryEvaluationStage.AUTONOMY, PreliminaryComparisonClause.RESIDUAL_LTE_AUTOMATION_MAX, PreliminaryComparisonOperator.LTE, t.automation_residual_risk_maximum)
        mark(PreliminaryInputName.HUMAN_JUDGEMENT_REQUIREMENT, PreliminaryEvaluationStage.AUTONOMY, PreliminaryComparisonClause.JUDGEMENT_LT_ASSISTANCE, PreliminaryComparisonOperator.LTE, t.automation_human_judgement_maximum)
        mark(PreliminaryInputName.RISK_CONSEQUENCE, PreliminaryEvaluationStage.AUTONOMY, PreliminaryComparisonClause.CONSEQUENCE_LT_ASSISTANCE, PreliminaryComparisonOperator.LTE, t.automation_risk_consequence_maximum)
        mark(PreliminaryInputName.HUMAN_ACCOUNTABILITY_REQUIRED, PreliminaryEvaluationStage.AUTONOMY, PreliminaryComparisonClause.ACCOUNTABILITY_FALSE, PreliminaryComparisonOperator.IS_FALSE)
        mark(PreliminaryInputName.PREDICTABILITY, PreliminaryEvaluationStage.AUTONOMY, PreliminaryComparisonClause.PREDICTABILITY_GTE_AUTOMATION, PreliminaryComparisonOperator.GTE, t.automation_predictability_minimum)
        return PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION, material


def _input_from_assertion(
    step_id: str,
    name: PreliminaryInputName,
    path: str,
    value_type: PreliminaryValueType,
    assertion: ReviewedAssertion,
    *,
    conflicted: bool,
) -> _Input:
    if conflicted:
        return _unknown_input(step_id, name, path, value_type, conflict=True)
    admissible = (
        assertion.retained
        and assertion.disposition
        in {ReviewDisposition.ACCEPTED, ReviewDisposition.CORRECTED}
    )
    if not admissible or assertion.value is None:
        return _unknown_input(step_id, name, path, value_type, conflict=False)
    if assertion.origin is InformationOrigin.HUMAN_SUPPLIED:
        return _unknown_input(step_id, name, path, value_type, conflict=False)
    if assertion.origin not in {
        InformationOrigin.DOCUMENT_SUPPORTED,
        InformationOrigin.MODEL_INFERRED,
    }:
        return _unknown_input(step_id, name, path, value_type, conflict=False)

    facts = tuple(
        DocumentedFact(
            fact_id=_stable_id("fact", step_id, name.value, evidence.evidence_id),
            statement=f"Source evidence for {name.value}.",
            source_document_id=evidence.document_id,
            exact_excerpt=evidence.exact_snippet,
            source_locator=evidence.source_locator,
        )
        for evidence in assertion.evidence
    )
    if not facts:
        return _unknown_input(step_id, name, path, value_type, conflict=False)
    normalized = _normalize(assertion.value, value_type)
    if (
        assertion.knowledge_state is KnowledgeState.INFERRED
        and assertion.origin is InformationOrigin.MODEL_INFERRED
    ):
        inference = ReasonableInference(
            inference_id=_stable_id("inference", step_id, name.value),
            statement=f"Reviewed reasonable inference for {name.value}: {normalized!r}.",
            derived_from_fact_ids=tuple(item.fact_id for item in facts),
            rationale=assertion.rationale,
            confidence=EvidenceCoverageConfidence(
                level=PreliminaryConfidence.MEDIUM,
                basis="Explicitly reviewed inference with documentary lineage.",
            ),
        )
        return _Input(
            name, path, value_type, normalized,
            PreliminaryEvidenceClassification.REASONABLE_INFERENCE,
            (inference.inference_id,), facts, inference, None,
        )
    if (
        assertion.knowledge_state is KnowledgeState.KNOWN
        and assertion.origin is InformationOrigin.DOCUMENT_SUPPORTED
    ):
        return _Input(
            name, path, value_type, normalized,
            PreliminaryEvidenceClassification.DOCUMENTED,
            tuple(item.fact_id for item in facts), facts, None, None,
        )
    return _unknown_input(step_id, name, path, value_type, conflict=False)


def _approval_confirmed(assertion: ReviewedAssertion) -> bool:
    return (
        assertion.retained
        and assertion.value is not None
        and assertion.disposition
        in {ReviewDisposition.ACCEPTED, ReviewDisposition.CORRECTED}
    )


def _unknown_input(
    step_id: str,
    name: PreliminaryInputName,
    path: str,
    value_type: PreliminaryValueType,
    *,
    conflict: bool,
) -> _Input:
    unknown = PreliminaryUnknown(
        unknown_id=_stable_id("unknown", step_id, name.value, "conflict" if conflict else "unknown"),
        unresolved_question=(
            f"Resolve conflicting reviewed evidence for {name.value}."
            if conflict else f"What is the reviewed value for {name.value}?"
        ),
        evidence_needed=f"Reviewed documentary evidence for {name.value}.",
        owner_needed="Process owner",
    )
    return _Input(
        name, path, value_type, None,
        PreliminaryEvidenceClassification.CONFLICT if conflict else PreliminaryEvidenceClassification.UNKNOWN,
        (unknown.unknown_id,), (), None, unknown,
    )


def _normalize(value: Any, value_type: PreliminaryValueType) -> int | bool | str:
    if value_type is PreliminaryValueType.ORDINAL:
        if isinstance(value, bool):
            raise ValueError("Ordinal reviewed values cannot be booleans")
        return int(value)
    if value_type is PreliminaryValueType.BOOLEAN:
        if not isinstance(value, bool):
            raise ValueError("Boolean reviewed values must be booleans")
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Activity identity must be non-blank text")
    return value


def _evaluation_assertions(
    step: ReviewedProcessStep,
) -> tuple[tuple[str, ReviewedAssertion], ...]:
    base = f"steps.{step.candidate_step_id}"
    values: list[tuple[str, ReviewedAssertion]] = [(f"{base}.activity", step.activity)]
    values.extend(
        (f"{base}.criteria.{item.name.value}", item.assertion)
        for item in step.criteria
    )
    values.append((f"{base}.human_accountability_required", step.human_accountability_required))
    values.extend(
        (f"{base}.capability_signals.{item.name}", item.assertion)
        for item in step.capability_signals
    )
    return tuple(values)


def _stable_id(kind: str, *parts: str) -> str:
    payload = json.dumps((kind, *parts), separators=(",", ":"), ensure_ascii=False)
    return f"{kind}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _unique_facts(inputs: dict[PreliminaryInputName, _Input]) -> tuple[DocumentedFact, ...]:
    result: list[DocumentedFact] = []
    seen: set[str] = set()
    for item in inputs.values():
        for fact in item.facts:
            if fact.fact_id not in seen:
                seen.add(fact.fact_id)
                result.append(fact)
    return tuple(result)


def _unresolved(item: _Input) -> bool:
    return item.classification in {
        PreliminaryEvidenceClassification.UNKNOWN,
        PreliminaryEvidenceClassification.CONFLICT,
    }


def _unresolved_operator(item: _Input) -> PreliminaryComparisonOperator:
    if item.classification is PreliminaryEvidenceClassification.CONFLICT:
        return PreliminaryComparisonOperator.IS_CONFLICT
    return PreliminaryComparisonOperator.IS_UNKNOWN


def _direction(code: PreliminaryDecidingRuleCode) -> ProvisionalDirection:
    from ai_adoption_engine.models.preliminary_assessment import RULE_DIRECTION_BY_CODE

    return RULE_DIRECTION_BY_CODE[code]


def _confidence_rank(level: PreliminaryConfidence) -> int:
    return {
        PreliminaryConfidence.LOW: 0,
        PreliminaryConfidence.MEDIUM: 1,
        PreliminaryConfidence.HIGH: 2,
    }[level]


def _confidence_basis(
    confidence: PreliminaryConfidence,
    code: PreliminaryDecidingRuleCode,
    inference_count: int,
) -> str:
    if confidence is PreliminaryConfidence.HIGH:
        return "Every path-material input is documented and resolved."
    if confidence is PreliminaryConfidence.MEDIUM:
        return "Exactly one path-material input is a reviewed reasonable inference."
    if code is PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_AUTONOMY_UNKNOWN:
        return "The narrow assisted-work fallback depends on unresolved autonomy inputs."
    if _direction(code) is ProvisionalDirection.INSUFFICIENT_BASIS:
        return "The deciding path contains an unknown, conflict, or insufficient basis."
    return f"The deciding path depends on {inference_count} reviewed inferences."


def _rationale(code: PreliminaryDecidingRuleCode) -> str:
    return {
        PreliminaryDecidingRuleCode.INSUFFICIENT_ACTIVITY_IDENTITY: "The activity identity is not admissibly supported.",
        PreliminaryDecidingRuleCode.INSUFFICIENT_CHANGE_CASE: "Business value is unresolved, so the change case cannot be established.",
        PreliminaryDecidingRuleCode.LIKELY_NO_CHANGE: "Documented business value is below the provisional change threshold.",
        PreliminaryDecidingRuleCode.LIKELY_PROCESS_IMPROVEMENT_FIRST: "A readiness blocker should be addressed before selecting an intervention.",
        PreliminaryDecidingRuleCode.INSUFFICIENT_READINESS: "Readiness is unresolved and must be established before intervention selection.",
        PreliminaryDecidingRuleCode.INSUFFICIENT_CONVENTIONAL_FIT: "Conventional-solution fit is unresolved.",
        PreliminaryDecidingRuleCode.LIKELY_CONVENTIONAL_AUTOMATION: "Conventional automation meets the provisional fit threshold and precedes AI selection.",
        PreliminaryDecidingRuleCode.INSUFFICIENT_AI_FIT: "AI capability fit is unresolved.",
        PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_LOW_AI_FIT: "AI capability fit is below the provisional minimum.",
        PreliminaryDecidingRuleCode.INSUFFICIENT_AI_CAPABILITY: "No positive AI capability is established and at least one capability signal is unresolved.",
        PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_NO_CAPABILITY: "All reviewed AI capability signals are false.",
        PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_SAFETY_VETO: "Residual risk reaches the provisional AI safety-veto threshold.",
        PreliminaryDecidingRuleCode.INSUFFICIENT_RESIDUAL_RISK: "Residual risk is unknown or conflicted, so AI is not yet permitted.",
        PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_CONSTRAINT: "AI is plausible, but a resolved constraint requires human-led assistance.",
        PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_AUTONOMY_UNKNOWN: "Residual risk is below the veto threshold, but autonomy evidence remains unresolved.",
        PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION: "Every provisional automation input is resolved within its continuity threshold.",
    }[code]


def _readiness_pass_clause(name: PreliminaryInputName) -> PreliminaryComparisonClause:
    if name is PreliminaryInputName.DATA_READINESS:
        return PreliminaryComparisonClause.DATA_GTE_MINIMUM
    return PreliminaryComparisonClause.COMPLEXITY_LTE_READY_MAX


def _readiness_pass_operator(name: PreliminaryInputName) -> PreliminaryComparisonOperator:
    if name is PreliminaryInputName.DATA_READINESS:
        return PreliminaryComparisonOperator.GTE
    return PreliminaryComparisonOperator.LTE


def _readiness_threshold(name: PreliminaryInputName, thresholds: Any) -> int:
    if name is PreliminaryInputName.DATA_READINESS:
        return thresholds.data_readiness_minimum
    return thresholds.implementation_complexity_ready_maximum


def _autonomy_unknown_clause(name: PreliminaryInputName) -> PreliminaryComparisonClause:
    return {
        PreliminaryInputName.HUMAN_JUDGEMENT_REQUIREMENT: PreliminaryComparisonClause.JUDGEMENT_UNRESOLVED,
        PreliminaryInputName.RISK_CONSEQUENCE: PreliminaryComparisonClause.CONSEQUENCE_UNRESOLVED,
        PreliminaryInputName.HUMAN_ACCOUNTABILITY_REQUIRED: PreliminaryComparisonClause.ACCOUNTABILITY_UNRESOLVED,
        PreliminaryInputName.PREDICTABILITY: PreliminaryComparisonClause.PREDICTABILITY_UNRESOLVED,
    }[name]


def _first_assistance_constraint(inputs: dict[PreliminaryInputName, _Input], thresholds: Any) -> tuple[PreliminaryInputName, PreliminaryComparisonClause, PreliminaryComparisonOperator, int | None] | None:
    checks = (
        (PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT, inputs[PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT].value == thresholds.assistance_residual_risk, PreliminaryComparisonClause.RESIDUAL_EQ_ASSISTANCE, PreliminaryComparisonOperator.EQ, thresholds.assistance_residual_risk),
        (PreliminaryInputName.DATA_READINESS, inputs[PreliminaryInputName.DATA_READINESS].value < thresholds.automation_data_readiness_minimum, PreliminaryComparisonClause.DATA_LT_AUTOMATION, PreliminaryComparisonOperator.LT, thresholds.automation_data_readiness_minimum),
        (PreliminaryInputName.IMPLEMENTATION_COMPLEXITY, inputs[PreliminaryInputName.IMPLEMENTATION_COMPLEXITY].value > thresholds.automation_complexity_maximum, PreliminaryComparisonClause.COMPLEXITY_GT_AUTOMATION_MAX, PreliminaryComparisonOperator.GT, thresholds.automation_complexity_maximum),
        (PreliminaryInputName.HUMAN_JUDGEMENT_REQUIREMENT, inputs[PreliminaryInputName.HUMAN_JUDGEMENT_REQUIREMENT].value >= thresholds.assistance_human_judgement_minimum, PreliminaryComparisonClause.JUDGEMENT_GTE_ASSISTANCE, PreliminaryComparisonOperator.GTE, thresholds.assistance_human_judgement_minimum),
        (PreliminaryInputName.RISK_CONSEQUENCE, inputs[PreliminaryInputName.RISK_CONSEQUENCE].value >= thresholds.assistance_risk_consequence_minimum, PreliminaryComparisonClause.CONSEQUENCE_GTE_ASSISTANCE, PreliminaryComparisonOperator.GTE, thresholds.assistance_risk_consequence_minimum),
        (PreliminaryInputName.HUMAN_ACCOUNTABILITY_REQUIRED, inputs[PreliminaryInputName.HUMAN_ACCOUNTABILITY_REQUIRED].value is True, PreliminaryComparisonClause.ACCOUNTABILITY_TRUE, PreliminaryComparisonOperator.IS_TRUE, None),
        (PreliminaryInputName.PREDICTABILITY, inputs[PreliminaryInputName.PREDICTABILITY].value < thresholds.automation_predictability_minimum, PreliminaryComparisonClause.PREDICTABILITY_LT_AUTOMATION, PreliminaryComparisonOperator.LT, thresholds.automation_predictability_minimum),
    )
    return next((item[0], item[2], item[3], item[4]) for item in checks if item[1]) if any(item[1] for item in checks) else None

"""Deterministic IntegratedAssessmentSuccess to DecisionSupportPackage service."""

from __future__ import annotations

import hashlib
import json

from pydantic import ValidationError

from ai_adoption_engine.decision_support.future_state import build_future_state
from ai_adoption_engine.decision_support.governance import build_governance
from ai_adoption_engine.decision_support.portfolio import build_portfolio
from ai_adoption_engine.decision_support.report import (
    ROI_UNAVAILABLE,
    build_report,
    methodology_disclosure,
)
from ai_adoption_engine.decision_support.roadmap import build_roadmap
from ai_adoption_engine.models.decision_support import (
    CurrentStateReference,
    DecisionPackageError,
    DecisionPackageFailure,
    DecisionPackageFailureCode,
    DecisionPackageGenerationResult,
    DecisionPackageSource,
    DecisionPackageSuccess,
    DecisionSupportPackage,
    PackageCompleteness,
)
from ai_adoption_engine.models.enums import GateName, PriorityStatus, RecommendationMode
from ai_adoption_engine.models.integrated_assessment import IntegratedAssessmentSuccess


PACKAGE_SCHEMA_VERSION = "phase6-v0.1"


class DecisionSupportPackageService:
    """Create deterministic planning content without rerunning assessment logic."""

    def generate(
        self, integrated: IntegratedAssessmentSuccess
    ) -> DecisionPackageGenerationResult:
        if not isinstance(integrated, IntegratedAssessmentSuccess):
            return self._failure(
                DecisionPackageFailureCode.INTEGRATED_SUCCESS_REQUIRED,
                "Decision-package generation requires IntegratedAssessmentSuccess.",
            )
        try:
            validated = IntegratedAssessmentSuccess.model_validate(
                integrated.model_dump(mode="json")
            )
        except (AttributeError, TypeError, ValueError, ValidationError):
            return self._failure(
                DecisionPackageFailureCode.INVALID_INTEGRATED_ASSESSMENT,
                "The integrated assessment is malformed or internally inconsistent.",
                source_run_id=getattr(
                    getattr(integrated, "metadata", None),
                    "assessment_run_id",
                    None,
                ),
            )
        contract_error = _validate_input_contract(validated)
        if contract_error is not None:
            return self._failure(
                contract_error[0],
                contract_error[1],
                field_path=contract_error[2],
                step_id=contract_error[3],
                source_run_id=validated.metadata.assessment_run_id,
            )
        try:
            portfolio = build_portfolio(
                validated.process_assessment.step_assessments,
                validated.step_traceability,
            )
            future_state = build_future_state(
                portfolio,
                process_id=validated.lineage.validated_process_id,
                process_name=validated.process_assessment.process_name,
            )
        except ValueError:
            return self._failure(
                DecisionPackageFailureCode.FUTURE_STATE_RULE_CONFLICT,
                "The assessment cannot be represented by the approved future-state rules.",
                source_run_id=validated.metadata.assessment_run_id,
            )
        try:
            roadmap = build_roadmap(portfolio)
            governance = build_governance(
                portfolio, validated.process_assessment.step_assessments
            )
            gaps = [
                gap for opportunity in portfolio.items for gap in opportunity.missing_information
            ]
            completeness = (
                PackageCompleteness.COMPLETE_WITH_INFORMATION_GAPS
                if _material_package_gap(portfolio)
                else PackageCompleteness.COMPLETE
            )
            methodology = methodology_disclosure(
                validated.policy.policy_id, validated.policy.policy_version
            )
            evidence_appendix = _evidence_appendix(validated)
            report = build_report(
                process_name=validated.process_assessment.process_name,
                completeness=completeness,
                portfolio=portfolio,
                future_state=future_state,
                roadmap=roadmap,
                governance=governance,
                methodology=methodology,
            )
            package = DecisionSupportPackage(
                package_id=_package_id(validated),
                package_schema_version=PACKAGE_SCHEMA_VERSION,
                completeness=completeness,
                source=DecisionPackageSource(
                    integrated_assessment_run_id=(
                        validated.metadata.assessment_run_id
                    ),
                    lineage=validated.lineage,
                    policy=validated.policy,
                ),
                current_state=CurrentStateReference(
                    process_id=validated.lineage.validated_process_id,
                    process_name=validated.process_assessment.process_name,
                    review_id=validated.lineage.review_id,
                    approval_event_id=validated.lineage.approval_event_id,
                    source_document_id=validated.lineage.source_document_id,
                    ordered_step_ids=[
                        item.step_id
                        for item in validated.process_assessment.step_assessments
                    ],
                ),
                portfolio=portfolio,
                future_state=future_state,
                roadmap=roadmap,
                governance=governance,
                missing_information=gaps,
                roi_statement=ROI_UNAVAILABLE,
                methodology=methodology,
                evidence_appendix=evidence_appendix,
                report_content=report,
            )
        except (KeyError, TypeError, ValueError, ValidationError):
            return self._failure(
                DecisionPackageFailureCode.PACKAGE_GENERATION_FAILED,
                "The deterministic decision package could not be constructed.",
                source_run_id=validated.metadata.assessment_run_id,
            )
        return DecisionPackageSuccess(package=package)

    @staticmethod
    def _failure(
        code: DecisionPackageFailureCode,
        message: str,
        *,
        field_path: str | None = None,
        step_id: str | None = None,
        source_run_id: str | None = None,
    ) -> DecisionPackageFailure:
        return DecisionPackageFailure(
            source_assessment_run_id=source_run_id,
            errors=[
                DecisionPackageError(
                    code=code,
                    message=message,
                    field_path=field_path,
                    step_id=step_id,
                )
            ],
        )


def _validate_input_contract(
    integrated: IntegratedAssessmentSuccess,
) -> tuple[DecisionPackageFailureCode, str, str | None, str | None] | None:
    assessments = integrated.process_assessment.step_assessments
    traces = integrated.step_traceability
    if len(assessments) != len(traces):
        return (
            DecisionPackageFailureCode.INCOMPLETE_STEP_COVERAGE,
            "Every assessed step requires exactly one traceability record.",
            "step_traceability",
            None,
        )
    for assessment, trace in zip(assessments, traces, strict=True):
        if assessment.step_id != trace.step_id:
            return (
                DecisionPackageFailureCode.INVALID_TRACEABILITY,
                "Assessment and traceability step IDs do not match.",
                "step_traceability",
                assessment.step_id,
            )
        gates = [item.gate for item in assessment.gate_results]
        if len(gates) != len(set(gates)) or set(gates) != set(GateName):
            return (
                DecisionPackageFailureCode.UNSUPPORTED_ASSESSMENT_CONTRACT,
                "Each assessed step must retain every Phase 1 gate exactly once.",
                f"process_assessment.steps.{assessment.step_id}.gate_results",
                assessment.step_id,
            )
        if len(assessment.criteria) != len(trace.criteria):
            return (
                DecisionPackageFailureCode.INVALID_TRACEABILITY,
                "Every assessed criterion requires a reviewed-value trace.",
                f"step_traceability.{assessment.step_id}.criteria",
                assessment.step_id,
            )
        for criterion, value_trace in zip(
            assessment.criteria, trace.criteria, strict=True
        ):
            if criterion.knowledge_state is not value_trace.knowledge_state:
                return (
                    DecisionPackageFailureCode.INVALID_TRACEABILITY,
                    "Criterion knowledge state does not match its reviewed trace.",
                    value_trace.review_field_path,
                    assessment.step_id,
                )
            if set(criterion.evidence_ids) != {
                item.evidence_id for item in value_trace.evidence
            }:
                return (
                    DecisionPackageFailureCode.INVALID_TRACEABILITY,
                    "Criterion evidence does not match its reviewed trace.",
                    value_trace.review_field_path,
                    assessment.step_id,
                )
        if (
            assessment.human_accountability.knowledge_state
            is not trace.human_accountability.knowledge_state
            or set(assessment.human_accountability.evidence_ids)
            != {item.evidence_id for item in trace.human_accountability.evidence}
        ):
            return (
                DecisionPackageFailureCode.INVALID_TRACEABILITY,
                "Accountability evidence or knowledge state does not match its trace.",
                trace.human_accountability.review_field_path,
                assessment.step_id,
            )
    if integrated.process_assessment.process_id != integrated.lineage.validated_process_id:
        return (
            DecisionPackageFailureCode.INVALID_INTEGRATED_ASSESSMENT,
            "The assessed process ID does not match Phase 5 lineage.",
            "process_assessment.process_id",
            None,
        )
    return None


def _material_package_gap(portfolio) -> bool:
    for item in portfolio.items:
        if item.recommendation_mode is RecommendationMode.INVESTIGATE_FURTHER:
            return True
        if item.priority_status is PriorityStatus.INCOMPLETE:
            return True
        if any(
            gap.material_to_recommendation
            or gap.material_to_priority
            or gap.material_to_planning
            for gap in item.missing_information
        ):
            return True
    return False


def _evidence_appendix(
    integrated: IntegratedAssessmentSuccess,
):
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


def _package_id(integrated: IntegratedAssessmentSuccess) -> str:
    semantic_payload = {
        "package_schema_version": PACKAGE_SCHEMA_VERSION,
        "validated_process_fingerprint": (
            integrated.lineage.validated_process_fingerprint
        ),
        "decision_policy_fingerprint": (
            integrated.policy.decision_policy_fingerprint
        ),
        "process_name": integrated.process_assessment.process_name,
        "step_assessments": [
            item.model_dump(mode="json")
            for item in integrated.process_assessment.step_assessments
        ],
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
    return f"decision-package-{hashlib.sha256(canonical).hexdigest()}"

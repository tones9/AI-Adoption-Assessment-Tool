"""Explicit approval-gated Phase 5 orchestration for the four-gate successor."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from pydantic import ValidationError

from ai_adoption_engine.application.assessment import (
    _lineage,
    _validate_approval_artifact,
    _validate_assessment_input_consistency,
    _value_trace,
)
from ai_adoption_engine.application.fingerprints import (
    fingerprint_four_gate_policy,
)
from ai_adoption_engine.decision.four_gate_engine import FourGateAssessmentEngine
from ai_adoption_engine.decision.four_gate_policy import FourGateDecisionPolicy
from ai_adoption_engine.models.enums import CriterionName
from ai_adoption_engine.models.four_gate_assessment import (
    CapabilitySignalName,
    FourGateName,
    FourGateProcessAssessment,
)
from ai_adoption_engine.models.four_gate_integrated_assessment import (
    FourGateAssessedPolicyReference,
    FourGateAssessmentRunMetadata,
    FourGateIntegratedAssessmentFailure,
    FourGateIntegratedAssessmentResult,
    FourGateIntegratedAssessmentSuccess,
    FourGateStepAssessmentTrace,
)
from ai_adoption_engine.models.integrated_assessment import (
    AssessmentLineage,
    IntegrationError,
    IntegrationFailureCode,
    ReviewedValueTrace,
)
from ai_adoption_engine.models.process import BusinessProcess
from ai_adoption_engine.models.review import ApprovedProcessReview


INTEGRATION_SCHEMA_VERSION = "phase5-v0.2"
PHASE1_CONTRACT_VERSION = "phase1-v0.4"


class FourGateAssessmentEngineLike(Protocol):
    def assess(self, process: BusinessProcess) -> FourGateProcessAssessment: ...


PolicyLoader = Callable[[], FourGateDecisionPolicy]
EngineFactory = Callable[
    [FourGateDecisionPolicy],
    FourGateAssessmentEngineLike,
]
Clock = Callable[[], datetime]
RunIdFactory = Callable[[], str]


class FourGateIntegratedAssessmentService:
    """Run the successor only through an explicitly supplied v0.3 policy loader."""

    def __init__(
        self,
        *,
        policy_loader: PolicyLoader,
        engine_factory: EngineFactory | None = None,
        clock: Clock | None = None,
        run_id_factory: RunIdFactory | None = None,
    ) -> None:
        self.policy_loader = policy_loader
        self.engine_factory = engine_factory or FourGateAssessmentEngine
        self.clock = clock or (lambda: datetime.now(UTC))
        self.run_id_factory = run_id_factory or (
            lambda: f"four-gate-assessment-{uuid4().hex}"
        )

    def assess(
        self,
        approved_review: ApprovedProcessReview,
    ) -> FourGateIntegratedAssessmentResult:
        metadata = FourGateAssessmentRunMetadata(
            assessment_run_id=self.run_id_factory(),
            assessed_at=self.clock(),
            integration_schema_version=INTEGRATION_SCHEMA_VERSION,
            phase1_contract_version=PHASE1_CONTRACT_VERSION,
        )
        if not isinstance(approved_review, ApprovedProcessReview):
            return self._failure(
                metadata,
                IntegrationFailureCode.APPROVAL_REQUIRED,
                "Four-gate assessment requires an ApprovedProcessReview.",
            )

        try:
            approval_error = _validate_approval_artifact(approved_review)
        except (AttributeError, TypeError, ValueError):
            approval_error = (
                IntegrationFailureCode.INVALID_APPROVAL_ARTIFACT,
                "The approval artifact is malformed or internally inconsistent.",
                None,
            )
        if approval_error is not None:
            return self._failure(metadata, *approval_error)

        raw_projection = getattr(approved_review, "business_process", None)
        if raw_projection is None:
            return self._failure(
                metadata,
                IntegrationFailureCode.PROJECTION_UNAVAILABLE,
                "The approved review has no validated process projection.",
            )
        try:
            payload = (
                raw_projection.model_dump(mode="json")
                if hasattr(raw_projection, "model_dump")
                else raw_projection
            )
            process = BusinessProcess.model_validate(payload)
        except (TypeError, ValueError, ValidationError):
            return self._failure(
                metadata,
                IntegrationFailureCode.INVALID_PROCESS_PROJECTION,
                "The approved process projection does not satisfy the Phase 1 "
                "input contract.",
                field_path="business_process",
            )

        try:
            consistency_error = _validate_assessment_input_consistency(
                approved_review,
                process,
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            consistency_error = (
                IntegrationFailureCode.INVALID_APPROVAL_ARTIFACT,
                "The approval artifact is malformed or internally inconsistent.",
                None,
            )
        if consistency_error is not None:
            return self._failure(metadata, *consistency_error)

        try:
            lineage = _lineage(approved_review, process)
        except (AttributeError, StopIteration, TypeError, ValueError):
            return self._failure(
                metadata,
                IntegrationFailureCode.INVALID_APPROVAL_ARTIFACT,
                "The approval artifact does not contain valid lineage metadata.",
            )
        try:
            traceability = _build_four_gate_traceability(approved_review)
        except (AttributeError, KeyError, TypeError, ValueError):
            return self._failure(
                metadata,
                IntegrationFailureCode.TRACEABILITY_BUILD_FAILED,
                "Successor traceability could not be constructed from the "
                "approval artifact.",
            )

        try:
            loaded_policy = self.policy_loader()
            policy_payload = (
                loaded_policy.model_dump(mode="json")
                if hasattr(loaded_policy, "model_dump")
                else loaded_policy
            )
            policy = FourGateDecisionPolicy.model_validate(policy_payload)
        except Exception:
            return self._failure(
                metadata,
                IntegrationFailureCode.POLICY_LOAD_FAILED,
                "The explicitly selected four-gate policy could not be validated.",
                lineage=lineage,
            )

        policy_reference = FourGateAssessedPolicyReference(
            policy_id=policy.policy_id,
            policy_version=policy.version,
            policy_status=policy.status,
            decision_policy_fingerprint=fingerprint_four_gate_policy(policy),
        )
        try:
            engine = self.engine_factory(policy)
            raw_assessment = engine.assess(process)
        except Exception:
            return self._failure(
                metadata,
                IntegrationFailureCode.ASSESSMENT_ENGINE_FAILED,
                "The deterministic four-gate engine could not complete the run.",
                lineage=lineage,
                policy=policy_reference,
            )

        try:
            assessment_payload = (
                raw_assessment.model_dump(mode="json")
                if hasattr(raw_assessment, "model_dump")
                else raw_assessment
            )
            assessment = FourGateProcessAssessment.model_validate(assessment_payload)
        except (AttributeError, TypeError, ValueError, ValidationError):
            return self._failure(
                metadata,
                IntegrationFailureCode.INVALID_ENGINE_OUTPUT,
                "The four-gate engine returned malformed successor output.",
                lineage=lineage,
                policy=policy_reference,
            )

        expected_ids = [step.step_id for step in process.steps]
        assessed_ids = [step.step_id for step in assessment.step_assessments]
        if assessed_ids != expected_ids or len(assessed_ids) != len(set(assessed_ids)):
            return self._failure(
                metadata,
                IntegrationFailureCode.INVALID_ENGINE_OUTPUT,
                "The successor output did not contain exactly one ordered result "
                "per process step.",
                field_path="process_assessment.step_assessments",
                lineage=lineage,
                policy=policy_reference,
            )
        if (
            assessment.process_id != process.process_id
            or assessment.process_name != process.name
            or assessment.framework_id != policy.framework_id
            or assessment.framework_version != policy.framework_version
            or assessment.decision_contract_version != policy.decision_contract_version
            or assessment.policy_id != policy.policy_id
            or assessment.policy_version != policy.version
            or assessment.policy_status != policy.status
        ):
            return self._failure(
                metadata,
                IntegrationFailureCode.INVALID_ENGINE_OUTPUT,
                "The successor output did not match its process, framework, "
                "contract, or policy.",
                lineage=lineage,
                policy=policy_reference,
            )

        engine_contract_error = _validate_four_gate_engine_step_contracts(
            process,
            assessment,
        )
        if engine_contract_error is not None:
            return self._failure(
                metadata,
                IntegrationFailureCode.INVALID_ENGINE_OUTPUT,
                engine_contract_error[0],
                field_path=engine_contract_error[1],
                lineage=lineage,
                policy=policy_reference,
                step_id=engine_contract_error[2],
            )

        if [item.step_id for item in traceability] != assessed_ids:
            return self._failure(
                metadata,
                IntegrationFailureCode.TRACEABILITY_BUILD_FAILED,
                "Successor traceability did not match the assessed step order.",
                lineage=lineage,
                policy=policy_reference,
            )

        try:
            return FourGateIntegratedAssessmentSuccess(
                metadata=metadata,
                lineage=lineage,
                policy=policy_reference,
                process_assessment=assessment,
                step_traceability=traceability,
            )
        except ValidationError:
            return self._failure(
                metadata,
                IntegrationFailureCode.TRACEABILITY_BUILD_FAILED,
                "The successor result failed its integrated traceability contract.",
                lineage=lineage,
                policy=policy_reference,
            )

    @staticmethod
    def _failure(
        metadata: FourGateAssessmentRunMetadata,
        code: IntegrationFailureCode,
        message: str,
        field_path: str | None = None,
        *,
        lineage: AssessmentLineage | None = None,
        policy: FourGateAssessedPolicyReference | None = None,
        step_id: str | None = None,
    ) -> FourGateIntegratedAssessmentFailure:
        return FourGateIntegratedAssessmentFailure(
            metadata=metadata,
            lineage=lineage,
            policy=policy,
            errors=[
                IntegrationError(
                    code=code,
                    message=message,
                    field_path=field_path,
                    step_id=step_id,
                )
            ],
        )


def _validate_four_gate_engine_step_contracts(
    process: BusinessProcess,
    assessment: FourGateProcessAssessment,
) -> tuple[str, str, str] | None:
    known_evidence = {item.evidence_id: item for item in process.evidence}
    for projected, assessed in zip(
        process.steps,
        assessment.step_assessments,
        strict=True,
    ):
        base = f"process_assessment.step_assessments[step_id={assessed.step_id}]"
        if assessed.activity != projected.activity:
            return (
                "An assessed activity did not match its approved process step.",
                f"{base}.activity",
                assessed.step_id,
            )

        for item in assessed.criteria:
            supplied = projected.characteristics.criterion(item.criterion)
            if (
                item.value != supplied.value
                or item.knowledge_state is not supplied.knowledge_state
                or item.rationale != supplied.rationale
                or item.evidence_ids != supplied.evidence_ids
                or item.confidence != supplied.confidence
            ):
                return (
                    "An assessed criterion did not preserve its approved input.",
                    f"{base}.criteria[criterion={item.criterion.value}]",
                    assessed.step_id,
                )

        supplied_accountability = (
            projected.characteristics.human_accountability_required
        )
        accountability = assessed.human_accountability
        if (
            accountability.value != supplied_accountability.value
            or accountability.knowledge_state
            is not supplied_accountability.knowledge_state
            or accountability.rationale != supplied_accountability.rationale
            or accountability.evidence_ids != supplied_accountability.evidence_ids
            or accountability.confidence != supplied_accountability.confidence
        ):
            return (
                "The accountability result did not preserve its approved input.",
                f"{base}.human_accountability",
                assessed.step_id,
            )

        for item in assessed.capability_signals:
            supplied_signal = getattr(
                projected.characteristics.capability_signals,
                item.signal.value,
            )
            if (
                item.value != supplied_signal.value
                or item.knowledge_state is not supplied_signal.knowledge_state
                or item.rationale != supplied_signal.rationale
                or item.evidence_ids != supplied_signal.evidence_ids
                or item.confidence != supplied_signal.confidence
            ):
                return (
                    "A capability signal did not preserve its approved input.",
                    f"{base}.capability_signals[signal={item.signal.value}]",
                    assessed.step_id,
                )

        returned_ids = [item.evidence_id for item in assessed.evidence]
        if len(returned_ids) != len(set(returned_ids)) or any(
            known_evidence.get(item.evidence_id) != item
            for item in assessed.evidence
        ):
            return (
                "An assessed step returned invalid or duplicate evidence.",
                f"{base}.evidence",
                assessed.step_id,
            )
        for gate_result in assessed.gate_results:
            referenced_ids = {
                *gate_result.evidence_ids,
                *(
                    evidence_id
                    for gap in gate_result.blocking_gaps
                    for evidence_id in gap.evidence_ids
                ),
            }
            if not referenced_ids.issubset(known_evidence):
                return (
                    "A gate result referenced evidence outside the approved process.",
                    f"{base}.gate_results[gate={gate_result.gate.value}]",
                    assessed.step_id,
                )
        if [item.gate for item in assessed.gate_results] != list(FourGateName):
            return (
                "An assessed step did not preserve canonical four-gate order.",
                f"{base}.gate_results",
                assessed.step_id,
            )
    return None


def _build_four_gate_traceability(
    approved: ApprovedProcessReview,
) -> list[FourGateStepAssessmentTrace]:
    reviewed_by_id = {
        step.candidate_step_id: step
        for step in approved.review.steps
        if step.retained
    }
    traces: list[FourGateStepAssessmentTrace] = []
    for step in approved.business_process.steps:
        reviewed = reviewed_by_id[step.step_id]
        assessed_base = (
            f"process_assessment.step_assessments[step_id={step.step_id}]"
        )
        process_base = f"business_process.steps[step_id={step.step_id}]"
        review_base = f"review.steps[candidate_step_id={step.step_id}]"
        reviewed_criteria = {
            item.name: item.assertion for item in reviewed.criteria
        }
        reviewed_signals = {
            item.name: item.assertion for item in reviewed.capability_signals
        }

        criteria: list[ReviewedValueTrace] = []
        for criterion in CriterionName:
            criteria.append(
                _value_trace(
                    reviewed_criteria[criterion],
                    validated_path=(
                        f"{process_base}.characteristics.{criterion.value}"
                    ),
                    review_path=(
                        f"{review_base}.criteria[name={criterion.value}]"
                    ),
                    assessment_path=(
                        f"{assessed_base}.criteria[criterion={criterion.value}]"
                    ),
                )
            )

        capability_signals: list[ReviewedValueTrace] = []
        for signal in CapabilitySignalName:
            capability_signals.append(
                _value_trace(
                    reviewed_signals[signal.value],
                    validated_path=(
                        f"{process_base}.characteristics.capability_signals."
                        f"{signal.value}"
                    ),
                    review_path=(
                        f"{review_base}.capability_signals[name={signal.value}]"
                    ),
                    assessment_path=(
                        f"{assessed_base}.capability_signals[signal={signal.value}]"
                    ),
                )
            )

        traces.append(
            FourGateStepAssessmentTrace(
                step_id=step.step_id,
                assessment_step_path=assessed_base,
                decision_status_path=f"{assessed_base}.decision_status",
                change_disposition_path=f"{assessed_base}.change_disposition",
                readiness_disposition_path=f"{assessed_base}.readiness_disposition",
                selected_intervention_family_path=(
                    f"{assessed_base}.selected_intervention_family"
                ),
                autonomy_ceiling_path=f"{assessed_base}.autonomy_ceiling",
                outcome_code_path=f"{assessed_base}.outcome_code",
                gate_results_path=f"{assessed_base}.gate_results",
                validated_step_path=process_base,
                review_step_path=review_base,
                activity=_value_trace(
                    reviewed.activity,
                    validated_path=f"{process_base}.activity",
                    review_path=f"{review_base}.activity",
                    assessment_path=f"{assessed_base}.activity",
                ),
                criteria=criteria,
                human_accountability=_value_trace(
                    reviewed.human_accountability_required,
                    validated_path=(
                        f"{process_base}.characteristics."
                        "human_accountability_required"
                    ),
                    review_path=f"{review_base}.human_accountability_required",
                    assessment_path=f"{assessed_base}.human_accountability",
                ),
                capability_signals=capability_signals,
            )
        )
    return traces

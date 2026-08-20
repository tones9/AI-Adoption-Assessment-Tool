"""Approval-gated orchestration of the deterministic Phase 1 assessment engine."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import ValidationError

from ai_adoption_engine.application.fingerprints import (
    fingerprint_business_process,
    fingerprint_decision_policy,
)
from ai_adoption_engine.decision.engine import AssessmentEngine
from ai_adoption_engine.decision.policy import DecisionPolicy, load_policy
from ai_adoption_engine.models.assessment import ProcessAssessment
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.evidence import (
    BooleanCriterionInput,
    CriterionInput,
    EvidenceReference,
)
from ai_adoption_engine.models.integrated_assessment import (
    AssessedPolicyReference,
    AssessmentLineage,
    AssessmentRunMetadata,
    EvidenceTraceReference,
    IntegratedAssessmentFailure,
    IntegratedAssessmentResult,
    IntegratedAssessmentSuccess,
    IntegrationError,
    IntegrationFailureCode,
    ReviewedValueTrace,
    StepAssessmentTrace,
)
from ai_adoption_engine.models.process import (
    BusinessProcess,
    CapabilitySignalInput,
)
from ai_adoption_engine.models.review import (
    ApprovedProcessReview,
    ConflictStatus,
    InformationOrigin,
    ReviewAction,
    ReviewedAssertion,
    ReviewedCollection,
    ReviewedProcessStep,
    ReviewDisposition,
    ReviewStatus,
)


INTEGRATION_SCHEMA_VERSION = "phase5-v0.1"
PHASE1_CONTRACT_VERSION = "phase1-v0.3"
DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "decision_policy.v0.2.json"
)


class AssessmentEngineLike(Protocol):
    def assess(self, process: BusinessProcess) -> ProcessAssessment: ...


PolicyLoader = Callable[[], DecisionPolicy]
EngineFactory = Callable[[DecisionPolicy], AssessmentEngineLike]
Clock = Callable[[], datetime]
RunIdFactory = Callable[[], str]


def _default_policy_loader() -> DecisionPolicy:
    return load_policy(DEFAULT_POLICY_PATH)


class IntegratedAssessmentService:
    """Run Phase 1 only for a verified Phase 4 approval artifact."""

    def __init__(
        self,
        *,
        policy_loader: PolicyLoader | None = None,
        engine_factory: EngineFactory | None = None,
        clock: Clock | None = None,
        run_id_factory: RunIdFactory | None = None,
    ) -> None:
        self.policy_loader = policy_loader or _default_policy_loader
        self.engine_factory = engine_factory or AssessmentEngine
        self.clock = clock or (lambda: datetime.now(UTC))
        self.run_id_factory = run_id_factory or (
            lambda: f"assessment-{uuid4().hex}"
        )

    def assess(
        self, approved_review: ApprovedProcessReview
    ) -> IntegratedAssessmentResult:
        metadata = AssessmentRunMetadata(
            assessment_run_id=self.run_id_factory(),
            assessed_at=self.clock(),
            integration_schema_version=INTEGRATION_SCHEMA_VERSION,
            phase1_contract_version=PHASE1_CONTRACT_VERSION,
        )
        if not isinstance(approved_review, ApprovedProcessReview):
            return self._failure(
                metadata,
                IntegrationFailureCode.APPROVAL_REQUIRED,
                "Integrated assessment requires an ApprovedProcessReview.",
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
                "The approved process projection does not satisfy the Phase 1 contract.",
                field_path="business_process",
            )

        try:
            consistency_error = _validate_assessment_input_consistency(
                approved_review, process
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
            traceability = _build_traceability(approved_review, None)
        except Exception:
            return self._failure(
                metadata,
                IntegrationFailureCode.TRACEABILITY_BUILD_FAILED,
                "Traceability could not be constructed for every assessed step.",
                lineage=lineage,
            )
        return self._assess_validated_input(metadata, process, lineage, traceability)

    def assess_successor(
        self, successor, *, reassessment_repository=None
    ) -> IntegratedAssessmentResult:
        """Assess the sole approved M2 successor shape through the normal engine.

        This deliberately bypasses neither Phase 5 validation nor policy loading.  It
        accepts only the M2 projection type, validates its one-field contract, then
        reuses the same deterministic execution helper as ordinary assessment.
        """

        from ai_adoption_engine.grw.m2.models import M2SuccessorApprovedReview

        metadata = AssessmentRunMetadata(
            assessment_run_id=self.run_id_factory(),
            assessed_at=self.clock(),
            integration_schema_version=INTEGRATION_SCHEMA_VERSION,
            phase1_contract_version=PHASE1_CONTRACT_VERSION,
        )
        if not isinstance(successor, M2SuccessorApprovedReview):
            return self._failure(
                metadata,
                IntegrationFailureCode.APPROVAL_REQUIRED,
                "Successor assessment requires an M2SuccessorApprovedReview.",
            )
        if reassessment_repository is None or not reassessment_repository.verify_successor_for_phase5(successor):
            return self._failure(
                metadata,
                IntegrationFailureCode.APPROVAL_REQUIRED,
                "Successor assessment requires a persisted, verified M2 approval lineage.",
            )
        process = successor.successor_process
        if fingerprint_business_process(process) != successor.successor_process_fingerprint:
            return self._failure(
                metadata,
                IntegrationFailureCode.INVALID_APPROVAL_ARTIFACT,
                "The M2 successor process fingerprint does not match its payload.",
            )
        if successor.changed_field_path != f"steps.{successor.target_step_id}.characteristics.data_readiness":
            return self._failure(
                metadata,
                IntegrationFailureCode.INVALID_APPROVAL_ARTIFACT,
                "M2 successor may change data_readiness only.",
            )
        if not _valid_m2_successor_projection(successor):
            return self._failure(
                metadata,
                IntegrationFailureCode.INVALID_APPROVAL_ARTIFACT,
                "The M2 successor does not preserve the hash-pinned baseline except for the approved data-readiness patch.",
            )
        try:
            baseline_traceability = _build_traceability(successor.baseline_approved, None)
            lineage = _lineage(successor.baseline_approved, successor.baseline_approved.business_process).model_copy(
                update={
                    "review_id": successor.successor_review_id,
                    "approval_event_id": successor.successor_approval_event_id,
                    "approved_at": metadata.assessed_at,
                    "validated_process_id": process.process_id,
                    "validated_process_fingerprint": successor.successor_process_fingerprint,
                }
            )
            traceability = _m2_successor_traceability(successor, baseline_traceability)
        except Exception:
            return self._failure(
                metadata,
                IntegrationFailureCode.TRACEABILITY_BUILD_FAILED,
                "M2 successor traceability could not be constructed.",
                lineage=None,
            )
        return self._assess_validated_input(metadata, process, lineage, traceability)

    def _assess_validated_input(
        self,
        metadata: AssessmentRunMetadata,
        process: BusinessProcess,
        lineage: AssessmentLineage,
        traceability_template: list[StepAssessmentTrace],
    ) -> IntegratedAssessmentResult:
        try:
            loaded_policy = self.policy_loader()
            policy_payload = (
                loaded_policy.model_dump(mode="json")
                if hasattr(loaded_policy, "model_dump")
                else loaded_policy
            )
            policy = DecisionPolicy.model_validate(policy_payload)
        except Exception:
            return self._failure(
                metadata,
                IntegrationFailureCode.POLICY_LOAD_FAILED,
                "The configured decision policy could not be loaded and validated.",
                lineage=lineage,
            )

        policy_reference = AssessedPolicyReference(
            policy_id=policy.policy_id,
            policy_version=policy.version,
            policy_status=policy.status,
            decision_policy_fingerprint=fingerprint_decision_policy(policy),
        )
        try:
            engine = self.engine_factory(policy)
            raw_assessment = engine.assess(process)
        except Exception:
            return self._failure(
                metadata,
                IntegrationFailureCode.ASSESSMENT_ENGINE_FAILED,
                "The deterministic assessment engine could not complete the run.",
                lineage=lineage,
                policy=policy_reference,
            )

        try:
            assessment_payload = (
                raw_assessment.model_dump(mode="json")
                if hasattr(raw_assessment, "model_dump")
                else raw_assessment
            )
            assessment = ProcessAssessment.model_validate(assessment_payload)
        except (TypeError, ValueError, ValidationError):
            return self._failure(
                metadata,
                IntegrationFailureCode.INVALID_ENGINE_OUTPUT,
                "The assessment engine returned malformed output.",
                lineage=lineage,
                policy=policy_reference,
            )

        expected_ids = [step.step_id for step in process.steps]
        assessed_ids = [step.step_id for step in assessment.step_assessments]
        if assessed_ids != expected_ids or len(assessed_ids) != len(set(assessed_ids)):
            return self._failure(
                metadata,
                IntegrationFailureCode.INVALID_ENGINE_OUTPUT,
                "The assessment output did not contain exactly one result per process step.",
                field_path="process_assessment.step_assessments",
                lineage=lineage,
                policy=policy_reference,
            )
        if (
            assessment.process_id != process.process_id
            or assessment.process_name != process.name
            or assessment.policy_id != policy.policy_id
            or assessment.policy_version != policy.version
            or assessment.policy_status != policy.status
        ):
            return self._failure(
                metadata,
                IntegrationFailureCode.INVALID_ENGINE_OUTPUT,
                "The assessment output did not match its validated process or policy.",
                lineage=lineage,
                policy=policy_reference,
            )
        engine_contract_error = _validate_engine_step_contracts(process, assessment)
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

        try:
            traceability = _apply_assessment_paths(traceability_template, assessment)
        except Exception:
            return self._failure(
                metadata,
                IntegrationFailureCode.TRACEABILITY_BUILD_FAILED,
                "Traceability could not be constructed for every assessed step.",
                lineage=lineage,
                policy=policy_reference,
            )

        return IntegratedAssessmentSuccess(
            metadata=metadata,
            lineage=lineage,
            policy=policy_reference,
            process_assessment=assessment,
            step_traceability=traceability,
        )

    @staticmethod
    def _failure(
        metadata: AssessmentRunMetadata,
        code: IntegrationFailureCode,
        message: str,
        field_path: str | None = None,
        *,
        lineage: AssessmentLineage | None = None,
        policy: AssessedPolicyReference | None = None,
        step_id: str | None = None,
    ) -> IntegratedAssessmentFailure:
        return IntegratedAssessmentFailure(
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


def _validate_approval_artifact(
    approved: ApprovedProcessReview,
) -> tuple[IntegrationFailureCode, str, str | None] | None:
    review = approved.review
    if review.status is not ReviewStatus.APPROVED:
        return (
            IntegrationFailureCode.INVALID_APPROVAL_ARTIFACT,
            "The review artifact is not marked as approved.",
            "review.status",
        )
    if any(
        item.blocking and item.status is ConflictStatus.OPEN
        for item in review.conflicts
    ):
        return (
            IntegrationFailureCode.BLOCKED_REVIEW,
            "The approved artifact contains an unresolved blocking conflict.",
            "review.conflicts",
        )
    approval_events = [
        event for event in review.events if event.action is ReviewAction.APPROVE
    ]
    if len(approval_events) != 1:
        return (
            IntegrationFailureCode.INVALID_APPROVAL_ARTIFACT,
            "The review artifact must contain exactly one approval event.",
            "review.events",
        )
    event = approval_events[0]
    if event.occurred_at != approved.approval.approved_at:
        return (
            IntegrationFailureCode.INVALID_APPROVAL_ARTIFACT,
            "The approval event does not match the explicit approval metadata.",
            "approval.approved_at",
        )
    return None


def _validate_assessment_input_consistency(
    approved: ApprovedProcessReview,
    process: BusinessProcess,
) -> tuple[IntegrationFailureCode, str, str | None] | None:
    review = approved.review
    if (
        process.name != review.process_name.value
        or process.description != _optional_reviewed_text(review.process_description)
        or process.business_objective
        != _optional_reviewed_text(review.process_objective)
        or process.organisation is not None
    ):
        return _forged_projection("business_process.name")
    retained_steps = sorted(
        (step for step in review.steps if step.retained), key=lambda item: item.sequence
    )
    if len(retained_steps) != len(process.steps):
        return _forged_projection("business_process.steps")
    for reviewed, projected in zip(retained_steps, process.steps, strict=True):
        base = f"business_process.steps.{projected.step_id}"
        if (
            reviewed.candidate_step_id != projected.step_id
            or reviewed.sequence != projected.sequence
            or reviewed.activity.value != projected.activity
            or projected.description != _optional_reviewed_text(reviewed.description)
            or projected.actor != reviewed.primary_actor
            or projected.responsible_role
            != _first_reviewed_collection_value(reviewed.responsible_roles)
            or projected.systems != _reviewed_collection_values(reviewed.systems)
            or projected.inputs != _reviewed_collection_values(reviewed.inputs)
            or projected.outputs != _reviewed_collection_values(reviewed.outputs)
            or projected.exceptions != _reviewed_collection_values(reviewed.exceptions)
            or projected.dependencies
            != [
                item.target_candidate_step_id
                for item in reviewed.dependencies
                if item.retained and item.target_candidate_step_id is not None
            ]
        ):
            return _forged_projection(base)
        expected_step_evidence = _expected_step_evidence_ids(reviewed)
        if sorted(projected.evidence_ids) != sorted(expected_step_evidence):
            return _forged_projection(f"{base}.evidence_ids")
        reviewed_criteria = {item.name: item.assertion for item in reviewed.criteria}
        for name in CriterionName:
            if not _criterion_matches(
                reviewed_criteria[name], projected.characteristics.criterion(name)
            ):
                return _forged_projection(f"{base}.characteristics.{name.value}")
        if not _boolean_matches(
            reviewed.human_accountability_required,
            projected.characteristics.human_accountability_required,
        ):
            return _forged_projection(
                f"{base}.characteristics.human_accountability_required"
            )
        reviewed_signals = {
            item.name: item.assertion for item in reviewed.capability_signals
        }
        for name, field in projected.characteristics.capability_signals:
            if not _boolean_matches(reviewed_signals[name], field):
                return _forged_projection(
                    f"{base}.characteristics.capability_signals.{name}"
                )
    expected_evidence = _expected_process_evidence(review)
    actual_evidence = {item.evidence_id: item for item in process.evidence}
    if actual_evidence != expected_evidence:
        return _forged_projection("business_process.evidence")
    return None


def _forged_projection(
    field_path: str,
) -> tuple[IntegrationFailureCode, str, str]:
    return (
        IntegrationFailureCode.INVALID_APPROVAL_ARTIFACT,
        "The validated projection is inconsistent with its approved review record.",
        field_path,
    )


def _projected_evidence_ids(assertion: ReviewedAssertion) -> list[str]:
    if (
        not assertion.retained
        or assertion.value is None
        or assertion.origin is InformationOrigin.HUMAN_SUPPLIED
    ):
        return []
    return [item.evidence_id for item in assertion.evidence]


def _criterion_matches(
    reviewed: ReviewedAssertion, projected: CriterionInput
) -> bool:
    if not reviewed.retained or reviewed.value is None:
        return (
            projected.value is None
            and projected.knowledge_state is KnowledgeState.UNKNOWN
            and projected.evidence_ids == []
            and projected.confidence is None
        )
    return (
        projected.value == int(reviewed.value)
        and projected.knowledge_state is reviewed.knowledge_state
        and projected.confidence == reviewed.confidence
        and projected.evidence_ids == _projected_evidence_ids(reviewed)
    )


def _boolean_matches(
    reviewed: ReviewedAssertion,
    projected: BooleanCriterionInput | CapabilitySignalInput,
) -> bool:
    if not reviewed.retained or reviewed.value is None:
        return (
            projected.value is None
            and projected.knowledge_state is KnowledgeState.UNKNOWN
            and projected.evidence_ids == []
            and projected.confidence is None
        )
    return (
        projected.value is bool(reviewed.value)
        and projected.knowledge_state is reviewed.knowledge_state
        and projected.confidence == reviewed.confidence
        and projected.evidence_ids == _projected_evidence_ids(reviewed)
    )


def _expected_step_evidence_ids(step: ReviewedProcessStep) -> list[str]:
    evidence_ids: set[str] = set()

    def assertion(item: ReviewedAssertion) -> None:
        evidence_ids.update(_projected_evidence_ids(item))

    def collection(item: ReviewedCollection) -> None:
        evidence_ids.update(reference.evidence_id for reference in item.evidence)
        for value in item.items:
            assertion(value)

    for value in (
        step.activity,
        step.description,
        step.document_order,
        step.human_accountability_required,
    ):
        assertion(value)
    for item in (
        step.actors,
        step.responsible_roles,
        step.systems,
        step.inputs,
        step.outputs,
        step.exceptions,
        step.operational_characteristics,
    ):
        collection(item)
    for decision in step.decisions:
        if decision.retained:
            assertion(decision.condition)
            collection(decision.branches)
    for dependency in step.dependencies:
        if dependency.retained:
            assertion(dependency.target_label)
            assertion(dependency.relationship)
    return sorted(evidence_ids)


def _optional_reviewed_text(assertion: ReviewedAssertion) -> str | None:
    if not assertion.retained or assertion.value is None:
        return None
    value = str(assertion.value)
    return value if value.strip() else None


def _reviewed_collection_values(collection: ReviewedCollection) -> list[str]:
    return [
        str(item.value)
        for item in collection.items
        if item.retained and item.value is not None
    ]


def _first_reviewed_collection_value(collection: ReviewedCollection) -> str | None:
    values = _reviewed_collection_values(collection)
    return values[0] if values else None


def _expected_process_evidence(review) -> dict[str, EvidenceReference]:
    references = {}

    def add_assertion(assertion: ReviewedAssertion) -> None:
        if (
            not assertion.retained
            or assertion.origin is InformationOrigin.HUMAN_SUPPLIED
        ):
            return
        for item in assertion.evidence:
            references[item.evidence_id] = EvidenceReference(
                evidence_id=item.evidence_id,
                source_id=item.document_id,
                source_locator=item.source_locator,
                supporting_snippet=item.exact_snippet,
                provenance="Phase 2 document-supported source evidence",
                knowledge_state=KnowledgeState.KNOWN,
                uncertainty_status="certain",
            )

    def add_collection(collection: ReviewedCollection) -> None:
        for item in collection.evidence:
            references[item.evidence_id] = EvidenceReference(
                evidence_id=item.evidence_id,
                source_id=item.document_id,
                source_locator=item.source_locator,
                supporting_snippet=item.exact_snippet,
                provenance="Phase 2 document-supported source evidence",
                knowledge_state=KnowledgeState.KNOWN,
                uncertainty_status="certain",
            )
        for item in collection.items:
            add_assertion(item)

    for item in (
        review.process_name,
        review.process_description,
        review.process_objective,
    ):
        add_assertion(item)
    for step in (item for item in review.steps if item.retained):
        for item in (
            step.activity,
            step.description,
            step.document_order,
            step.human_accountability_required,
        ):
            add_assertion(item)
        for collection in (
            step.actors,
            step.responsible_roles,
            step.systems,
            step.inputs,
            step.outputs,
            step.exceptions,
            step.operational_characteristics,
        ):
            add_collection(collection)
        for decision in step.decisions:
            if decision.retained:
                add_assertion(decision.condition)
                add_collection(decision.branches)
        for dependency in step.dependencies:
            if dependency.retained:
                add_assertion(dependency.target_label)
                add_assertion(dependency.relationship)
        for characteristic in step.criteria:
            add_assertion(characteristic.assertion)
        add_assertion(step.human_accountability_required)
        for signal in step.capability_signals:
            add_assertion(signal.assertion)
    return references


def _lineage(
    approved: ApprovedProcessReview, process: BusinessProcess
) -> AssessmentLineage:
    approval_event = next(
        event for event in approved.review.events if event.action is ReviewAction.APPROVE
    )
    candidate = approved.review.original_candidate
    return AssessmentLineage(
        source_document_id=candidate.source_document_id,
        extraction_run_id=candidate.extraction_run_id,
        review_id=approved.review.review_id,
        approval_event_id=approval_event.event_id,
        approved_at=approved.approval.approved_at,
        validated_process_id=process.process_id,
        validated_process_fingerprint=fingerprint_business_process(process),
    )


def _validate_engine_step_contracts(
    process: BusinessProcess,
    assessment: ProcessAssessment,
) -> tuple[str, str, str] | None:
    known_evidence_ids = {item.evidence_id for item in process.evidence}
    for projected, assessed in zip(
        process.steps, assessment.step_assessments, strict=True
    ):
        base = f"process_assessment.step_assessments[step_id={assessed.step_id}]"
        if assessed.activity != projected.activity:
            return (
                "An assessed activity did not match its validated process step.",
                f"{base}.activity",
                assessed.step_id,
            )
        assessed_criteria = [item.criterion for item in assessed.criteria]
        if (
            len(assessed_criteria) != len(set(assessed_criteria))
            or set(assessed_criteria) != set(CriterionName)
        ):
            return (
                "An assessed step did not contain every criterion exactly once.",
                f"{base}.criteria",
                assessed.step_id,
            )
        for item in assessed.criteria:
            supplied = projected.characteristics.criterion(item.criterion)
            if (
                item.value != supplied.value
                or item.knowledge_state is not supplied.knowledge_state
                or item.evidence_ids != supplied.evidence_ids
                or item.confidence != supplied.confidence
            ):
                return (
                    "An assessed criterion did not preserve its validated input.",
                    f"{base}.criteria[criterion={item.criterion.value}]",
                    assessed.step_id,
                )
        accountability = projected.characteristics.human_accountability_required
        if (
            assessed.human_accountability.value != accountability.value
            or assessed.human_accountability.knowledge_state
            is not accountability.knowledge_state
            or assessed.human_accountability.evidence_ids
            != accountability.evidence_ids
            or assessed.human_accountability.confidence != accountability.confidence
        ):
            return (
                "The accountability assessment did not preserve its validated input.",
                f"{base}.human_accountability",
                assessed.step_id,
            )
        if not assessed.gate_results:
            return (
                "An assessed step did not contain deterministic gate results.",
                f"{base}.gate_results",
                assessed.step_id,
            )
        returned_evidence_ids = {item.evidence_id for item in assessed.evidence}
        if not returned_evidence_ids.issubset(known_evidence_ids):
            return (
                "An assessed step returned evidence outside the validated process.",
                f"{base}.evidence",
                assessed.step_id,
            )
    return None


def _build_traceability(
    approved: ApprovedProcessReview,
    assessment: ProcessAssessment | None,
) -> list[StepAssessmentTrace]:
    reviewed_by_id = {
        step.candidate_step_id: step
        for step in approved.review.steps
        if step.retained
    }
    traces: list[StepAssessmentTrace] = []
    iterated_steps = assessment.step_assessments if assessment is not None else approved.business_process.steps
    for assessed in iterated_steps:
        reviewed = reviewed_by_id[assessed.step_id]
        assessed_base = (
            f"process_assessment.step_assessments[step_id={assessed.step_id}]"
        )
        process_base = f"business_process.steps[step_id={assessed.step_id}]"
        review_base = f"review.steps[candidate_step_id={assessed.step_id}]"
        criterion_by_name = {item.name: item.assertion for item in reviewed.criteria}
        criteria = [
            _value_trace(
                criterion_by_name[item.criterion if assessment is not None else item],
                validated_path=(
                    f"{process_base}.characteristics.{(item.criterion if assessment is not None else item).value}"
                ),
                review_path=f"{review_base}.criteria[name={(item.criterion if assessment is not None else item).value}]",
                assessment_path=(
                    f"{assessed_base}.criteria[criterion={(item.criterion if assessment is not None else item).value}]"
                ),
            )
            for item in (assessed.criteria if assessment is not None else list(CriterionName))
        ]
        signal_traces = [
            _value_trace(
                item.assertion,
                validated_path=(
                    f"{process_base}.characteristics.capability_signals.{item.name}"
                ),
                review_path=f"{review_base}.capability_signals[name={item.name}]",
                assessment_path=None,
            )
            for item in reviewed.capability_signals
        ]
        traces.append(
            StepAssessmentTrace(
                step_id=assessed.step_id,
                assessment_step_path=assessed_base,
                recommendation_path=f"{assessed_base}.recommendation_mode",
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
                        f"{process_base}.characteristics.human_accountability_required"
                    ),
                    review_path=(
                        f"{review_base}.human_accountability_required"
                    ),
                    assessment_path=f"{assessed_base}.human_accountability",
                ),
                capability_signals=signal_traces,
            )
        )
    return traces


def _apply_assessment_paths(
    template: list[StepAssessmentTrace], assessment: ProcessAssessment
) -> list[StepAssessmentTrace]:
    """The template already contains stable paths; check complete ordered coverage."""
    if [item.step_id for item in template] != [item.step_id for item in assessment.step_assessments]:
        raise ValueError("Traceability template does not match assessed step order")
    return template


def _m2_successor_traceability(successor, baseline: list[StepAssessmentTrace]) -> list[StepAssessmentTrace]:
    """Replace only the target data-readiness trace with supplemental M2 evidence."""
    evidence_id = f"m2-doc-evidence-{successor.supporting_document.content_sha256}"
    result: list[StepAssessmentTrace] = []
    for step in baseline:
        if step.step_id != successor.target_step_id:
            result.append(step)
            continue
        criteria: list[ReviewedValueTrace] = []
        for item in step.criteria:
            if not item.validated_process_field_path.endswith(".data_readiness"):
                criteria.append(item)
                continue
            criteria.append(
                ReviewedValueTrace(
                    validated_process_field_path=item.validated_process_field_path,
                    review_field_path=(
                        f"m2.successor_review[{successor.successor_review_id}]."
                        f"criteria[name=data_readiness]"
                    ),
                    assessment_field_path=item.assessment_field_path,
                    origin=InformationOrigin.DOCUMENT_SUPPORTED,
                    knowledge_state=KnowledgeState.KNOWN,
                    review_disposition=ReviewDisposition.CORRECTED,
                    evidence=[
                        EvidenceTraceReference(
                            evidence_id=evidence_id,
                            document_id=successor.supporting_document.document_id,
                            block_id=f"m2-doc-{successor.supporting_document.content_sha256[:12]}",
                            block_start_offset=successor.locator.start_offset,
                            block_end_offset=successor.locator.end_offset,
                            source_locator=(
                                f"lines {successor.locator.line_start}-{successor.locator.line_end}; "
                                f"chars {successor.locator.start_offset}-{successor.locator.end_offset}"
                            ),
                        )
                    ],
                )
            )
        result.append(step.model_copy(update={"criteria": criteria}))
    return result


def _valid_m2_successor_projection(successor) -> bool:
    """Validate M2's one-field patch even if a caller bypassed its projector."""
    baseline = successor.baseline_approved.business_process.model_dump(mode="json")
    projected = successor.successor_process.model_dump(mode="json")
    evidence_id = f"m2-doc-evidence-{successor.supporting_document.content_sha256}"
    if len(projected["evidence"]) != len(baseline["evidence"]) + 1:
        return False
    supplemental = projected["evidence"][-1]
    if (
        supplemental.get("evidence_id") != evidence_id
        or supplemental.get("source_id") != successor.supporting_document.document_id
        or "not original Phase 3 extraction evidence" not in supplemental.get("provenance", "")
    ):
        return False
    if projected["evidence"][:-1] != baseline["evidence"]:
        return False
    projected["evidence"].pop()
    try:
        base_step = next(item for item in baseline["steps"] if item["step_id"] == successor.target_step_id)
        new_step = next(item for item in projected["steps"] if item["step_id"] == successor.target_step_id)
    except StopIteration:
        return False
    new_data = new_step["characteristics"]["data_readiness"]
    if (
        new_data.get("knowledge_state") != KnowledgeState.KNOWN.value
        or new_data.get("value") not in {0, 1, 2, 3, 4}
        or new_data.get("evidence_ids") != [evidence_id]
    ):
        return False
    base_step["characteristics"].pop("data_readiness", None)
    new_step["characteristics"].pop("data_readiness", None)
    return baseline == projected


def _value_trace(
    assertion: ReviewedAssertion,
    *,
    validated_path: str,
    review_path: str,
    assessment_path: str | None,
) -> ReviewedValueTrace:
    evidence = []
    if assertion.retained and assertion.origin is not InformationOrigin.HUMAN_SUPPLIED:
        evidence = [
            EvidenceTraceReference(
                evidence_id=item.evidence_id,
                document_id=item.document_id,
                block_id=item.block_id,
                block_start_offset=item.block_start_offset,
                block_end_offset=item.block_end_offset,
                source_locator=item.source_locator,
            )
            for item in assertion.evidence
        ]
    return ReviewedValueTrace(
        validated_process_field_path=validated_path,
        review_field_path=review_path,
        assessment_field_path=assessment_path,
        origin=assertion.origin,
        knowledge_state=assertion.knowledge_state,
        review_disposition=assertion.disposition,
        evidence=evidence,
    )

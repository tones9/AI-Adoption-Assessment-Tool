"""Read-only package-centred view model for the Decision Continuation Workspace."""

from __future__ import annotations

from dataclasses import dataclass

from ai_adoption_engine.grw.m2.models import (
    M2ArtifactReference,
    M2ArtifactType,
    M2BaselineReference,
    M2BaselineSuccessorComparison,
    M2DataReadinessResolution,
    M2DocumentSubmission,
    M2EvidenceReview,
    M2ReassessmentApproval,
    M2ReassessmentRequest,
    M2RunStage,
    M2StepGapReference,
    M2SuccessorApprovedReview,
    M2SuccessorAssessment,
    M2SuccessorDecisionPackage,
)
from ai_adoption_engine.grw.m2.service import M2ReassessmentService
from ai_adoption_engine.grw.models import GrwM1Context, GrwM1Status
from ai_adoption_engine.models.decision_support import DecisionPackageSuccess
from ai_adoption_engine.models.enums import CriterionName
from ai_adoption_engine.models.integrated_assessment import IntegratedAssessmentSuccess
from ai_adoption_engine.persistence.base import PersistenceError
from ai_adoption_engine.persistence.reassessment import M2RunListing
from ai_adoption_engine.workspace.models import ArtifactType, StoredArtifact, WorkflowStage


_TERMINAL_M2_STAGES = frozenset(
    {
        M2RunStage.COMPARED,
        M2RunStage.EVIDENCE_REJECTED,
        M2RunStage.INSUFFICIENT,
        M2RunStage.BLOCKED_CONFLICT,
        M2RunStage.STALE,
        M2RunStage.WITHDRAWN,
        M2RunStage.FAILED,
    }
)


@dataclass(frozen=True)
class DecisionContinuationArtifactReference:
    artifact_id: str
    artifact_revision: int
    payload_sha256: str


@dataclass(frozen=True)
class DecisionContinuationRecommendation:
    step_id: str
    current_activity: str
    recommendation_mode: str
    rationale: str


@dataclass(frozen=True)
class DecisionContinuationBaseline:
    assessment_id: str
    package: DecisionContinuationArtifactReference
    approved_review: DecisionContinuationArtifactReference
    integrated_assessment: DecisionContinuationArtifactReference
    package_id: str
    package_completeness: str
    policy_id: str
    policy_version: str
    policy_fingerprint: str
    recommendations: tuple[DecisionContinuationRecommendation, ...]


@dataclass(frozen=True)
class DecisionContinuationSuccessor:
    package_artifact: M2ArtifactReference
    package_id: str
    target_recommendation: str


@dataclass(frozen=True)
class DecisionContinuationComparison:
    artifact: M2ArtifactReference
    categories: tuple[str, ...]
    neutral_explanation: str
    baseline_recommendation: str
    successor_recommendation: str


@dataclass(frozen=True)
class DecisionContinuationGateDifference:
    gate: str
    baseline_status: str | None
    successor_status: str | None
    baseline_rationale: str | None
    successor_rationale: str | None


@dataclass(frozen=True)
class DecisionContinuationApprovedChange:
    approval_reason: str
    exact_change: str
    mapping_rationale: str
    retained_uncertainty: str
    changed_field_path: str
    baseline_remains_active: bool


@dataclass(frozen=True)
class DecisionContinuationEvidenceBasis:
    document_id: str
    content_sha256: str
    filename: str
    source_label: str
    line_start: int
    line_end: int
    start_offset: int
    end_offset: int
    exact_excerpt: str
    source_authority: str
    scope_statement: str
    period_statement: str
    semantic_rationale: str
    limitations: str
    conflict_status: str
    conflict_rationale: str
    reconciliation_statement: str | None
    applicability_statement: str | None


@dataclass(frozen=True)
class DecisionContinuationLineageReference:
    label: str
    artifact_id: str
    artifact_revision: int
    payload_sha256: str


@dataclass(frozen=True)
class DecisionContinuationControlledReport:
    run_id: str
    current_activity: str
    field_name: str
    baseline_package_id: str
    baseline_value: int | None
    baseline_knowledge_state: str
    baseline_recommendation: str
    baseline_rationale: tuple[str, ...]
    approved_change: DecisionContinuationApprovedChange
    evidence: DecisionContinuationEvidenceBasis
    successor_package_id: str
    successor_value: int | None
    successor_knowledge_state: str
    successor_recommendation: str
    successor_rationale: tuple[str, ...]
    gate_differences: tuple[DecisionContinuationGateDifference, ...]
    comparison_categories: tuple[str, ...]
    neutral_explanation: str
    lineage: tuple[DecisionContinuationLineageReference, ...]


@dataclass(frozen=True)
class DecisionContinuationRun:
    run_id: str
    stage: M2RunStage
    created_at: str
    updated_at: str
    baseline: M2BaselineReference
    gap: M2StepGapReference
    successor: DecisionContinuationSuccessor | None
    comparison: DecisionContinuationComparison | None
    controlled_report: DecisionContinuationControlledReport | None = None

    @property
    def is_terminal(self) -> bool:
        return self.stage in _TERMINAL_M2_STAGES


@dataclass(frozen=True)
class DecisionContinuationView:
    baseline: DecisionContinuationBaseline
    m1_context: GrwM1Context | None
    m1_status: GrwM1Status
    m2_context: tuple[M2BaselineReference, M2StepGapReference] | None
    m2_runs: tuple[DecisionContinuationRun, ...]
    m2_discovery_error: str | None = None


class DecisionContinuationService:
    """Compose existing read contracts; DCW owns no evidence or decision write."""

    def __init__(self, workspace_service, m2_service: M2ReassessmentService) -> None:
        self.workspace_service = workspace_service
        self.m2_service = m2_service

    @staticmethod
    def _reference(artifact: StoredArtifact) -> DecisionContinuationArtifactReference:
        return DecisionContinuationArtifactReference(
            artifact_id=artifact.artifact_id,
            artifact_revision=artifact.artifact_revision,
            payload_sha256=artifact.payload_sha256,
        )

    def _baseline(self, assessment_id: str) -> DecisionContinuationBaseline:
        workspace = self.workspace_service.repository.load_workspace(assessment_id)
        approved = workspace.active_artifacts.get(ArtifactType.APPROVED_REVIEW)
        integrated = workspace.active_artifacts.get(ArtifactType.INTEGRATED_ASSESSMENT_RESULT)
        package = workspace.active_artifacts.get(ArtifactType.DECISION_PACKAGE_RESULT)
        if (
            workspace.assessment.current_stage is not WorkflowStage.PACKAGE_READY
            or approved is None
            or integrated is None
            or package is None
            or not isinstance(integrated.payload, IntegratedAssessmentSuccess)
            or not isinstance(package.payload, DecisionPackageSuccess)
        ):
            raise ValueError("Decision continuation requires a package-ready baseline")
        decision_package = package.payload.package
        return DecisionContinuationBaseline(
            assessment_id=assessment_id,
            package=self._reference(package),
            approved_review=self._reference(approved),
            integrated_assessment=self._reference(integrated),
            package_id=decision_package.package_id,
            package_completeness=decision_package.completeness.value,
            policy_id=decision_package.source.policy.policy_id,
            policy_version=decision_package.source.policy.policy_version,
            policy_fingerprint=decision_package.source.policy.decision_policy_fingerprint,
            recommendations=tuple(
                DecisionContinuationRecommendation(
                    step_id=item.step_id,
                    current_activity=item.current_activity,
                    recommendation_mode=item.recommendation_mode.value,
                    rationale=item.rationale,
                )
                for item in decision_package.portfolio.items
            ),
        )

    @staticmethod
    def _assert_baseline_matches(
        baseline: DecisionContinuationBaseline, m2_baseline: M2BaselineReference
    ) -> None:
        if (
            m2_baseline.assessment_id != baseline.assessment_id
            or m2_baseline.decision_package.artifact_id != baseline.package.artifact_id
            or m2_baseline.decision_package.artifact_revision
            != baseline.package.artifact_revision
            or m2_baseline.decision_package.payload_sha256 != baseline.package.payload_sha256
            or m2_baseline.package_id != baseline.package_id
            or m2_baseline.approved_review.artifact_id != baseline.approved_review.artifact_id
            or m2_baseline.approved_review.artifact_revision
            != baseline.approved_review.artifact_revision
            or m2_baseline.approved_review.payload_sha256 != baseline.approved_review.payload_sha256
            or m2_baseline.integrated_assessment.artifact_id
            != baseline.integrated_assessment.artifact_id
            or m2_baseline.integrated_assessment.artifact_revision
            != baseline.integrated_assessment.artifact_revision
            or m2_baseline.integrated_assessment.payload_sha256
            != baseline.integrated_assessment.payload_sha256
        ):
            raise PersistenceError("M2 run does not match the active package baseline")

    def _load_baseline_artifact(self, reference: M2ArtifactReference, expected_type):
        artifact = self.workspace_service.repository.load_artifact(reference.artifact_id)
        if (
            artifact.artifact_id != reference.artifact_id
            or artifact.artifact_revision != reference.artifact_revision
            or artifact.payload_sha256 != reference.payload_sha256
            or not isinstance(artifact.payload, expected_type)
        ):
            raise PersistenceError("Pinned baseline artifact is stale or invalid")
        return artifact.payload

    def _load_m2_artifact(
        self,
        run_id: str,
        artifact_type: M2ArtifactType,
        expected_type,
    ):
        reference = self.m2_service.repository.load_artifact_reference(
            run_id, artifact_type
        )
        if reference is None:
            raise PersistenceError(
                f"M2 run is missing {artifact_type.value.lower()}"
            )
        payload = self.m2_service.repository.load_artifact(reference.artifact_id)
        if not isinstance(payload, expected_type) or payload.run_id != run_id:
            raise PersistenceError("M2 artifact does not belong to its declared run")
        return reference, payload

    @staticmethod
    def _target_assessment(integrated: IntegratedAssessmentSuccess, step_id: str):
        step = next(
            (
                item
                for item in integrated.process_assessment.step_assessments
                if item.step_id == step_id
            ),
            None,
        )
        if step is None:
            raise PersistenceError("Integrated assessment does not cover the M2 target")
        criterion = next(
            (
                item
                for item in step.criteria
                if item.criterion is CriterionName.DATA_READINESS
            ),
            None,
        )
        if criterion is None:
            raise PersistenceError("Integrated assessment has no data-readiness value")
        return step, criterion

    @staticmethod
    def _target_package(package: DecisionPackageSuccess, step_id: str):
        item = next(
            (
                item
                for item in package.package.portfolio.items
                if item.step_id == step_id
            ),
            None,
        )
        if item is None:
            raise PersistenceError("Decision Package does not cover the M2 target")
        return item

    @staticmethod
    def _gate_differences(baseline_item, successor_item):
        baseline = {item.gate.value: item for item in baseline_item.gate_results}
        successor = {item.gate.value: item for item in successor_item.gate_results}
        order = list(baseline) + [gate for gate in successor if gate not in baseline]
        differences = []
        for gate in order:
            old = baseline.get(gate)
            new = successor.get(gate)
            if (
                old is not None
                and new is not None
                and old.model_dump(mode="json") == new.model_dump(mode="json")
            ):
                continue
            differences.append(
                DecisionContinuationGateDifference(
                    gate=gate,
                    baseline_status=old.status.value if old is not None else None,
                    successor_status=new.status.value if new is not None else None,
                    baseline_rationale=old.rationale if old is not None else None,
                    successor_rationale=new.rationale if new is not None else None,
                )
            )
        return tuple(differences)

    @staticmethod
    def _lineage_reference(label: str, reference) -> DecisionContinuationLineageReference:
        return DecisionContinuationLineageReference(
            label=label,
            artifact_id=reference.artifact_id,
            artifact_revision=reference.artifact_revision,
            payload_sha256=reference.payload_sha256,
        )

    def _controlled_report(
        self,
        listing: M2RunListing,
        successor_reference: M2ArtifactReference,
        successor_package: M2SuccessorDecisionPackage,
        comparison_reference: M2ArtifactReference,
        comparison: M2BaselineSuccessorComparison,
    ) -> DecisionContinuationControlledReport:
        run_id = listing.run_id
        submission_ref, submission = self._load_m2_artifact(
            run_id, M2ArtifactType.DOCUMENT_SUBMISSION, M2DocumentSubmission
        )
        evidence_ref, evidence = self._load_m2_artifact(
            run_id, M2ArtifactType.EVIDENCE_REVIEW, M2EvidenceReview
        )
        resolution_ref, resolution = self._load_m2_artifact(
            run_id,
            M2ArtifactType.DATA_READINESS_RESOLUTION,
            M2DataReadinessResolution,
        )
        request_ref, request = self._load_m2_artifact(
            run_id, M2ArtifactType.REASSESSMENT_REQUEST, M2ReassessmentRequest
        )
        approval_ref, approval = self._load_m2_artifact(
            run_id, M2ArtifactType.REASSESSMENT_APPROVAL, M2ReassessmentApproval
        )
        successor_review_ref, successor_review = self._load_m2_artifact(
            run_id,
            M2ArtifactType.SUCCESSOR_APPROVED_REVIEW,
            M2SuccessorApprovedReview,
        )
        successor_assessment_ref, successor_assessment = self._load_m2_artifact(
            run_id,
            M2ArtifactType.SUCCESSOR_INTEGRATED_ASSESSMENT,
            M2SuccessorAssessment,
        )

        if (
            successor_reference != listing.successor_package_artifact
            or comparison_reference != listing.comparison_artifact
            or submission.baseline != listing.baseline
            or submission.gap != listing.gap
            or evidence.submission_artifact != submission_ref
            or resolution.evidence_review_artifact != evidence_ref
            or request.baseline != listing.baseline
            or request.gap != listing.gap
            or request.evidence_review_artifact != evidence_ref
            or request.resolution_artifact != resolution_ref
            or approval.request_artifact != request_ref
            or successor_review.baseline_approved_review
            != listing.baseline.approved_review
            or successor_review.request_artifact != request_ref
            or successor_review.approval_artifact != approval_ref
            or successor_review.evidence_review_artifact != evidence_ref
            or successor_review.resolution_artifact != resolution_ref
            or successor_review.data_readiness_resolution != resolution
            or successor_review.target_step_id != listing.gap.step_id
            or successor_review.supporting_document != submission.document
            or successor_review.locator != evidence.locator
            or successor_assessment.successor_review_artifact != successor_review_ref
            or successor_assessment.request_artifact != request_ref
            or successor_assessment.approval_artifact != approval_ref
            or successor_assessment.evidence_review_artifact != evidence_ref
            or successor_assessment.resolution_artifact != resolution_ref
            or successor_assessment.baseline != listing.baseline
            or successor_package.successor_assessment_artifact
            != successor_assessment_ref
            or successor_package.request_artifact != request_ref
            or successor_package.approval_artifact != approval_ref
            or successor_package.evidence_review_artifact != evidence_ref
            or successor_package.resolution_artifact != resolution_ref
            or successor_package.baseline != listing.baseline
            or comparison.baseline != listing.baseline
            or comparison.successor_package_artifact != successor_reference
            or comparison.target_step_id != listing.gap.step_id
            or not approval.baseline_remains_active
        ):
            raise PersistenceError("M2 controlled-report lineage is inconsistent")

        baseline_package = self._load_baseline_artifact(
            listing.baseline.decision_package, DecisionPackageSuccess
        )
        baseline_integrated = self._load_baseline_artifact(
            listing.baseline.integrated_assessment, IntegratedAssessmentSuccess
        )
        if (
            baseline_package.package.package_id != listing.baseline.package_id
            or baseline_package.package.source.integrated_assessment_run_id
            != baseline_integrated.metadata.assessment_run_id
            or successor_package.decision_package.package.source.integrated_assessment_run_id
            != successor_assessment.integrated_assessment.metadata.assessment_run_id
        ):
            raise PersistenceError("Decision Package assessment lineage is inconsistent")

        baseline_step, baseline_criterion = self._target_assessment(
            baseline_integrated, listing.gap.step_id
        )
        successor_step, successor_criterion = self._target_assessment(
            successor_assessment.integrated_assessment, listing.gap.step_id
        )
        baseline_item = self._target_package(
            baseline_package, listing.gap.step_id
        )
        successor_item = self._target_package(
            successor_package.decision_package, listing.gap.step_id
        )
        gate_differences = self._gate_differences(baseline_item, successor_item)
        if (
            baseline_step.recommendation_mode != baseline_item.recommendation_mode
            or baseline_step.gate_results != baseline_item.gate_results
            or successor_step.recommendation_mode != successor_item.recommendation_mode
            or successor_step.gate_results != successor_item.gate_results
            or resolution.baseline_value != baseline_criterion.value
            or resolution.baseline_knowledge_state
            is not baseline_criterion.knowledge_state
            or resolution.proposed_value != successor_criterion.value
            or resolution.proposed_knowledge_state
            is not successor_criterion.knowledge_state
            or comparison.baseline_data_readiness != baseline_criterion.value
            or comparison.successor_data_readiness != successor_criterion.value
            or comparison.baseline_recommendation
            != baseline_item.recommendation_mode.value
            or comparison.successor_recommendation
            != successor_item.recommendation_mode.value
            or (
                "GATE_CHANGE" in comparison.categories
                and not gate_differences
            )
        ):
            raise PersistenceError("M2 comparison does not match its package lineage")

        return DecisionContinuationControlledReport(
            run_id=run_id,
            current_activity=listing.gap.current_activity,
            field_name=listing.gap.information_gap.field_name,
            baseline_package_id=baseline_package.package.package_id,
            baseline_value=baseline_criterion.value,
            baseline_knowledge_state=baseline_criterion.knowledge_state.value,
            baseline_recommendation=baseline_item.recommendation_mode.value,
            baseline_rationale=tuple(baseline_item.rationale),
            approved_change=DecisionContinuationApprovedChange(
                approval_reason=approval.rationale,
                exact_change=approval.exact_change,
                mapping_rationale=resolution.mapping_rationale,
                retained_uncertainty=approval.retained_uncertainty,
                changed_field_path=successor_review.changed_field_path,
                baseline_remains_active=approval.baseline_remains_active,
            ),
            evidence=DecisionContinuationEvidenceBasis(
                document_id=submission.document.document_id,
                content_sha256=submission.document.content_sha256,
                filename=submission.document.filename,
                source_label=submission.document.source_label,
                line_start=evidence.locator.line_start,
                line_end=evidence.locator.line_end,
                start_offset=evidence.locator.start_offset,
                end_offset=evidence.locator.end_offset,
                exact_excerpt=evidence.locator.exact_excerpt,
                source_authority=evidence.source_authority,
                scope_statement=evidence.scope_statement,
                period_statement=evidence.period_statement,
                semantic_rationale=evidence.semantic_rationale,
                limitations=evidence.limitations,
                conflict_status=evidence.conflict_status.value,
                conflict_rationale=evidence.conflict_rationale,
                reconciliation_statement=evidence.reconciliation_statement,
                applicability_statement=evidence.applicability_statement,
            ),
            successor_package_id=successor_package.decision_package.package.package_id,
            successor_value=successor_criterion.value,
            successor_knowledge_state=successor_criterion.knowledge_state.value,
            successor_recommendation=successor_item.recommendation_mode.value,
            successor_rationale=tuple(successor_item.rationale),
            gate_differences=gate_differences,
            comparison_categories=tuple(comparison.categories),
            neutral_explanation=comparison.neutral_explanation,
            lineage=(
                self._lineage_reference(
                    "Baseline approved review", listing.baseline.approved_review
                ),
                self._lineage_reference(
                    "Baseline integrated assessment",
                    listing.baseline.integrated_assessment,
                ),
                self._lineage_reference(
                    "Baseline Decision Package", listing.baseline.decision_package
                ),
                self._lineage_reference("Document submission", submission_ref),
                self._lineage_reference("Evidence review", evidence_ref),
                self._lineage_reference("Criterion resolution", resolution_ref),
                self._lineage_reference("Reassessment request", request_ref),
                self._lineage_reference("Reassessment approval", approval_ref),
                self._lineage_reference("Successor review", successor_review_ref),
                self._lineage_reference(
                    "Successor integrated assessment", successor_assessment_ref
                ),
                self._lineage_reference(
                    "Successor Decision Package", successor_reference
                ),
                self._lineage_reference("Formal comparison", comparison_reference),
            ),
        )

    def _run_view(self, listing: M2RunListing) -> DecisionContinuationRun:
        successor = None
        successor_payload = None
        if listing.successor_package_artifact is not None:
            payload = self.m2_service.repository.load_artifact(
                listing.successor_package_artifact.artifact_id
            )
            if not isinstance(payload, M2SuccessorDecisionPackage):
                raise PersistenceError("M2 successor package artifact is invalid")
            if payload.run_id != listing.run_id or payload.baseline != listing.baseline:
                raise PersistenceError("M2 successor package lineage is invalid")
            successor_payload = payload
            item = next(
                (
                    item
                    for item in payload.decision_package.package.portfolio.items
                    if item.step_id == listing.gap.step_id
                ),
                None,
            )
            if item is None:
                raise PersistenceError("M2 successor package does not cover its target step")
            successor = DecisionContinuationSuccessor(
                package_artifact=listing.successor_package_artifact,
                package_id=payload.decision_package.package.package_id,
                target_recommendation=item.recommendation_mode.value,
            )
        comparison = None
        comparison_payload = None
        if listing.comparison_artifact is not None:
            payload = self.m2_service.repository.load_artifact(
                listing.comparison_artifact.artifact_id
            )
            if not isinstance(payload, M2BaselineSuccessorComparison):
                raise PersistenceError("M2 comparison artifact is invalid")
            if (
                payload.run_id != listing.run_id
                or payload.target_step_id != listing.gap.step_id
                or payload.baseline != listing.baseline
            ):
                raise PersistenceError("M2 comparison does not match its target step")
            comparison_payload = payload
            comparison = DecisionContinuationComparison(
                artifact=listing.comparison_artifact,
                categories=tuple(payload.categories),
                neutral_explanation=payload.neutral_explanation,
                baseline_recommendation=payload.baseline_recommendation,
                successor_recommendation=payload.successor_recommendation,
            )
        controlled_report = None
        if comparison_payload is not None:
            if successor_payload is None or listing.successor_package_artifact is None:
                raise PersistenceError("M2 comparison has no successor Decision Package")
            controlled_report = self._controlled_report(
                listing,
                listing.successor_package_artifact,
                successor_payload,
                listing.comparison_artifact,
                comparison_payload,
            )
        return DecisionContinuationRun(
            run_id=listing.run_id,
            stage=listing.stage,
            created_at=listing.created_at.isoformat(),
            updated_at=listing.updated_at.isoformat(),
            baseline=listing.baseline,
            gap=listing.gap,
            successor=successor,
            comparison=comparison,
            controlled_report=controlled_report,
        )

    def open(self, assessment_id: str) -> DecisionContinuationView:
        """Load DCW view state without changing any workspace or M2 record."""

        baseline = self._baseline(assessment_id)
        m1_status = self.workspace_service.load_grw_m1_status(assessment_id)
        m2_baseline = self.m2_service.load_m2_baseline_reference(assessment_id)
        m2_context = self.m2_service.open_m2_m1_context(assessment_id)
        if m2_baseline is None:
            return DecisionContinuationView(
                baseline=baseline,
                m1_context=m1_status.context,
                m1_status=m1_status,
                m2_context=m2_context,
                m2_runs=(),
            )
        self._assert_baseline_matches(baseline, m2_baseline)
        if m2_context is not None and m2_context[0] != m2_baseline:
            raise PersistenceError("Current M2 eligibility does not match its package baseline")
        try:
            listings = self.m2_service.repository.list_runs_for_baseline(
                baseline.assessment_id,
                baseline.package.artifact_id,
                baseline.package.payload_sha256,
                expected_baseline=m2_baseline,
            )
            runs = tuple(self._run_view(listing) for listing in listings)
            for run in runs:
                self._assert_baseline_matches(baseline, run.baseline)
        except PersistenceError:
            return DecisionContinuationView(
                baseline=baseline,
                m1_context=m1_status.context,
                m1_status=m1_status,
                m2_context=None,
                m2_runs=(),
                m2_discovery_error=(
                    "Persisted reassessment records could not be validated. "
                    "No reassessment action is available."
                ),
            )
        return DecisionContinuationView(
            baseline=baseline,
            m1_context=m1_status.context,
            m1_status=m1_status,
            m2_context=m2_context,
            m2_runs=runs,
        )

    def resumable_run(
        self, assessment_id: str, run_id: str
    ) -> DecisionContinuationRun | None:
        """Return a valid non-terminal run, or fail closed without a write."""

        view = self.open(assessment_id)
        if view.m2_context is None or view.m2_discovery_error is not None:
            return None
        expected_baseline, expected_gap = view.m2_context
        for run in view.m2_runs:
            if run.run_id != run_id:
                continue
            if run.is_terminal or run.baseline != expected_baseline or run.gap != expected_gap:
                return None
            return run
        return None

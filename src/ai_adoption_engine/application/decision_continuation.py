"""Read-only package-centred view model for the Decision Continuation Workspace."""

from __future__ import annotations

from dataclasses import dataclass

from ai_adoption_engine.grw.m2.models import (
    M2ArtifactReference,
    M2BaselineReference,
    M2BaselineSuccessorComparison,
    M2RunStage,
    M2StepGapReference,
    M2SuccessorDecisionPackage,
)
from ai_adoption_engine.grw.m2.service import M2ReassessmentService
from ai_adoption_engine.grw.models import GrwM1Context, GrwM1Status
from ai_adoption_engine.models.decision_support import DecisionPackageSuccess
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
class DecisionContinuationRun:
    run_id: str
    stage: M2RunStage
    created_at: str
    updated_at: str
    baseline: M2BaselineReference
    gap: M2StepGapReference
    successor: DecisionContinuationSuccessor | None
    comparison: DecisionContinuationComparison | None

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

    def _run_view(self, listing: M2RunListing) -> DecisionContinuationRun:
        successor = None
        if listing.successor_package_artifact is not None:
            payload = self.m2_service.repository.load_artifact(
                listing.successor_package_artifact.artifact_id
            )
            if not isinstance(payload, M2SuccessorDecisionPackage):
                raise PersistenceError("M2 successor package artifact is invalid")
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
        if listing.comparison_artifact is not None:
            payload = self.m2_service.repository.load_artifact(
                listing.comparison_artifact.artifact_id
            )
            if not isinstance(payload, M2BaselineSuccessorComparison):
                raise PersistenceError("M2 comparison artifact is invalid")
            if payload.target_step_id != listing.gap.step_id:
                raise PersistenceError("M2 comparison does not match its target step")
            comparison = DecisionContinuationComparison(
                artifact=listing.comparison_artifact,
                categories=tuple(payload.categories),
                neutral_explanation=payload.neutral_explanation,
                baseline_recommendation=payload.baseline_recommendation,
                successor_recommendation=payload.successor_recommendation,
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

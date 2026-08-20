"""Guarded non-decision operations for the smallest GRW evidence lifecycle."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_adoption_engine.grw.models import (
    GrwAdmissibilityEffect,
    GrwArtifactReference,
    GrwBaselineReference,
    GrwCriterionSnapshot,
    GrwEvidenceClass,
    GrwEvidenceReview,
    GrwEvidenceSubmission,
    GrwGapReference,
    GrwM1Context,
    GrwM1Status,
    GrwNonChangeProof,
    GrwParseStatus,
    GrwParsedEstimateCandidate,
    GrwQuestion,
    GrwReviewDecision,
)
from ai_adoption_engine.models.decision_support import (
    DecisionPackageSuccess,
    InformationGap,
    InformationGapKind,
)
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.integrated_assessment import IntegratedAssessmentSuccess
from ai_adoption_engine.persistence.base import ArtifactNotFoundError
from ai_adoption_engine.workspace.models import (
    ArtifactType,
    OperationKind,
    OperationStatus,
    StoredArtifact,
    WorkflowStage,
)


class GrwM1Error(ValueError):
    """A GRW M1 action was outside the intentionally narrow lifecycle."""


_RANGE = re.compile(
    r"(?P<lower>\d[\d,]*)\s*(?:–|-|to)\s*(?P<upper>\d[\d,]*)\s+"
    r"(?P<unit>[A-Za-z][A-Za-z _-]{0,40}?)\s+(?:per|a)\s+"
    r"(?P<period>month|week|day|year)s?\b",
    re.IGNORECASE,
)
_QUALIFIER = re.compile(r"\b(usually|around|roughly|approximately|about)\b", re.IGNORECASE)


def parse_estimate_candidate(answer_text: str) -> GrwParsedEstimateCandidate:
    """Parse only an explicit range/unit/period without assigning decision meaning."""

    match = _RANGE.search(answer_text)
    if match is None:
        return GrwParsedEstimateCandidate(
            parse_status=(
                GrwParseStatus.AMBIGUOUS
                if re.search(r"\d", answer_text)
                else GrwParseStatus.NOT_PARSED
            ),
            ambiguity_note=(
                "No simple range with an explicit unit and period was recognised."
                if re.search(r"\d", answer_text)
                else "No numeric range was recognised."
            ),
        )
    qualifiers = [item.lower() for item in _QUALIFIER.findall(answer_text)]
    return GrwParsedEstimateCandidate(
        parse_status=GrwParseStatus.CANDIDATE_NEEDS_REVIEW,
        lower_bound=int(match.group("lower").replace(",", "")),
        upper_bound=int(match.group("upper").replace(",", "")),
        unit=match.group("unit").strip().lower(),
        period=match.group("period").lower(),
        qualifiers=qualifiers,
    )


class GrwM1Service:
    """M1 sidecar service. It does not import or execute Phases 4–6 services."""

    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def _assert_write_target_is_not_frozen_portfolio(self) -> None:
        """Refuse GRW writes to the repository's immutable evaluation corpus.

        This check intentionally uses only the configured database path.  It runs
        before a GRW mutation loads an assessment, starts an operation, or opens a
        transaction, so detecting a protected target cannot itself mutate it.
        """

        database_path = getattr(self.repository, "path", None)
        if database_path is None:
            return
        resolved_parts = Path(database_path).resolve(strict=False).parts
        if "evaluation" in resolved_parts and "portfolio" in resolved_parts:
            raise GrwM1Error(
                "GRW M1 writes are refused for frozen evaluation portfolio workspaces"
            )

    @staticmethod
    def _reference(artifact: StoredArtifact) -> GrwArtifactReference:
        return GrwArtifactReference(
            artifact_id=artifact.artifact_id,
            artifact_revision=artifact.artifact_revision,
            payload_sha256=artifact.payload_sha256,
        )

    def open_m1_context(self, assessment_id: str) -> GrwM1Context | None:
        workspace = self.repository.load_workspace(assessment_id)
        package_artifact = workspace.active_artifacts.get(ArtifactType.DECISION_PACKAGE_RESULT)
        integrated_artifact = workspace.active_artifacts.get(
            ArtifactType.INTEGRATED_ASSESSMENT_RESULT
        )
        approved_artifact = workspace.active_artifacts.get(ArtifactType.APPROVED_REVIEW)
        if (
            workspace.assessment.current_stage is not WorkflowStage.PACKAGE_READY
            or package_artifact is None
            or integrated_artifact is None
            or approved_artifact is None
            or not isinstance(package_artifact.payload, DecisionPackageSuccess)
            or not isinstance(integrated_artifact.payload, IntegratedAssessmentSuccess)
        ):
            return None
        package = package_artifact.payload.package
        selected = self._select_eligible_gap(package)
        if selected is None:
            return None
        item, gap = selected
        baseline = GrwBaselineReference(
            assessment_id=assessment_id,
            package_id=package.package_id,
            approved_review=self._reference(approved_artifact),
            integrated_assessment=self._reference(integrated_artifact),
            decision_package=self._reference(package_artifact),
        )
        gap_reference = GrwGapReference(
            package_id=package.package_id,
            step_id=item.step_id,
            current_activity=item.current_activity,
            information_gap=gap,
        )
        question = GrwQuestion(
            customer_question=(
                f"About how often is “{item.current_activity}” performed in a typical "
                "month? A rough range is okay."
            ),
            help_text="An estimate or range is welcome when exact figures are unavailable.",
            why_it_matters=(
                "This can provide preliminary context about the scale of this activity. "
                "It does not change the current assessment."
            ),
        )
        return GrwM1Context(baseline=baseline, gap=gap_reference, question=question)

    @staticmethod
    def _select_eligible_gap(package) -> tuple[Any, InformationGap] | None:
        for item in package.portfolio.items:
            for gap in item.missing_information:
                if (
                    gap.kind is InformationGapKind.UNKNOWN_INPUT
                    and gap.field_name == CriterionName.REPETITION.value
                    and gap.knowledge_state is KnowledgeState.UNKNOWN
                ):
                    return item, gap
        return None

    def load_m1_status(self, assessment_id: str) -> GrwM1Status:
        context = self.open_m1_context(assessment_id)
        workspace = self.repository.load_workspace(assessment_id)
        submission_artifact = workspace.active_artifacts.get(
            ArtifactType.GRW_EVIDENCE_SUBMISSION
        )
        review_artifact = workspace.active_artifacts.get(ArtifactType.GRW_EVIDENCE_REVIEW)
        return GrwM1Status(
            context=context,
            submission_artifact_id=(
                submission_artifact.artifact_id if submission_artifact else None
            ),
            submission=(submission_artifact.payload if submission_artifact else None),
            review_artifact_id=(review_artifact.artifact_id if review_artifact else None),
            review=(review_artifact.payload if review_artifact else None),
        )

    def submit_response(
        self,
        assessment_id: str,
        *,
        baseline: GrwBaselineReference,
        gap_id: str,
        answer_text: str,
        explicit_unknown: bool = False,
    ) -> GrwEvidenceSubmission:
        self._assert_write_target_is_not_frozen_portfolio()
        context = self.open_m1_context(assessment_id)
        if context is None:
            raise GrwM1Error("No optional M1 question is available for this package")
        if baseline != context.baseline or gap_id != context.gap.information_gap.gap_id:
            raise GrwM1Error("The question is no longer attached to the active decision package")
        if not isinstance(answer_text, str):
            raise GrwM1Error("An answer must be text")
        if len(answer_text) > 2000:
            raise GrwM1Error("An answer must be 2,000 characters or fewer")
        if explicit_unknown and not answer_text:
            answer_text = "I do not know."
        if not answer_text.strip():
            raise GrwM1Error("Provide an answer or select I do not know")

        workspace = self.repository.load_workspace(assessment_id)
        existing = workspace.active_artifacts.get(ArtifactType.GRW_EVIDENCE_SUBMISSION)
        evidence_class = (
            GrwEvidenceClass.UNKNOWN
            if explicit_unknown
            else GrwEvidenceClass.OPERATOR_PROVIDED_ESTIMATE
        )
        parsed = None if explicit_unknown else parse_estimate_candidate(answer_text)
        if existing is not None:
            existing_submission = existing.payload
            if (
                existing_submission.answer_text == answer_text
                and existing_submission.evidence_class is evidence_class
                and existing_submission.gap.information_gap.gap_id == gap_id
            ):
                return existing_submission
            raise GrwM1Error("This optional M1 question has already been submitted")

        key = self._operation_key(
            "submit",
            context.baseline.decision_package.artifact_id,
            gap_id,
            evidence_class.value,
            answer_text,
        )
        operation = self.repository.begin_operation(
            assessment_id, OperationKind.GRW_SUBMIT, key
        )
        if operation.status is OperationStatus.COMPLETED:
            assert operation.produced_artifact_id
            return self.repository.load_artifact(operation.produced_artifact_id).payload
        try:
            submission = GrwEvidenceSubmission(
                submission_id=self.repository.id_factory("grw-submission"),
                submitted_at=self.repository.clock(),
                baseline=context.baseline,
                gap=context.gap,
                question=context.question,
                answer_text=answer_text,
                evidence_class=evidence_class,
                parsed_candidate=parsed,
            )
            self.repository.save_artifact_and_advance(
                assessment_id,
                ArtifactType.GRW_EVIDENCE_SUBMISSION,
                submission,
                artifact_schema_version="grw-m1-v0.1",
                stage=WorkflowStage.PACKAGE_READY,
                parent_artifact_id=context.baseline.decision_package.artifact_id,
                operation_id=operation.operation_id,
            )
        except Exception:
            self.repository.fail_operation(operation.operation_id, "grw-submit-failed")
            raise
        return submission

    def review_submission(
        self,
        assessment_id: str,
        *,
        submission_artifact_id: str,
        decision: GrwReviewDecision,
        reviewer_label: str,
        rationale: str,
    ) -> GrwEvidenceReview:
        self._assert_write_target_is_not_frozen_portfolio()
        if not reviewer_label.strip() or len(reviewer_label) > 200:
            raise GrwM1Error("A reviewer label of 1–200 characters is required")
        if not rationale.strip() or len(rationale) > 2000:
            raise GrwM1Error("A review rationale of 1–2,000 characters is required")
        context = self.open_m1_context(assessment_id)
        if context is None:
            raise GrwM1Error("No optional M1 question is available for this package")
        try:
            submission_artifact = self.repository.load_artifact(submission_artifact_id)
        except ArtifactNotFoundError as exc:
            raise GrwM1Error("The submitted evidence was not found") from exc
        if (
            submission_artifact.assessment_id != assessment_id
            or submission_artifact.artifact_type is not ArtifactType.GRW_EVIDENCE_SUBMISSION
        ):
            raise GrwM1Error("The submitted evidence does not belong to this assessment")
        submission = submission_artifact.payload
        if (
            submission.baseline != context.baseline
            or submission.gap.information_gap.gap_id != context.gap.information_gap.gap_id
            or submission_artifact.parent_artifact_id
            != context.baseline.decision_package.artifact_id
        ):
            raise GrwM1Error("The submitted evidence is not attached to the active baseline")
        workspace = self.repository.load_workspace(assessment_id)
        active_submission = workspace.active_artifacts.get(ArtifactType.GRW_EVIDENCE_SUBMISSION)
        if active_submission is None or active_submission.artifact_id != submission_artifact_id:
            raise GrwM1Error("Only the active submitted evidence may be reviewed")
        existing_review = workspace.active_artifacts.get(ArtifactType.GRW_EVIDENCE_REVIEW)
        if existing_review is not None:
            raise GrwM1Error("This M1 submission has already been reviewed")
        try:
            decision = GrwReviewDecision(decision)
        except ValueError as exc:
            raise GrwM1Error("The review decision is not supported by M1") from exc
        effect = {
            GrwReviewDecision.ACCEPT_PRELIMINARY: GrwAdmissibilityEffect.PRELIMINARY_UNDERSTANDING,
            GrwReviewDecision.ACCEPT_RECORDED_ONLY: GrwAdmissibilityEffect.RECORDED_ONLY,
            GrwReviewDecision.REJECT: GrwAdmissibilityEffect.NONE,
        }[decision]
        key = self._operation_key(
            "review",
            submission_artifact_id,
            submission_artifact.payload_sha256,
            decision.value,
            reviewer_label,
            rationale,
        )
        operation = self.repository.begin_operation(
            assessment_id, OperationKind.GRW_REVIEW, key
        )
        if operation.status is OperationStatus.COMPLETED:
            assert operation.produced_artifact_id
            return self.repository.load_artifact(operation.produced_artifact_id).payload
        try:
            review = GrwEvidenceReview(
                review_id=self.repository.id_factory("grw-review"),
                reviewed_at=self.repository.clock(),
                submission_artifact_id=submission_artifact.artifact_id,
                submission_payload_sha256=submission_artifact.payload_sha256,
                reviewer_label=reviewer_label,
                rationale=rationale,
                decision=decision,
                admissibility_effect=effect,
                non_change_proof=self._non_change_proof(context),
            )
            self.repository.save_artifact_and_advance(
                assessment_id,
                ArtifactType.GRW_EVIDENCE_REVIEW,
                review,
                artifact_schema_version="grw-m1-v0.1",
                stage=WorkflowStage.PACKAGE_READY,
                parent_artifact_id=submission_artifact.artifact_id,
                operation_id=operation.operation_id,
            )
        except Exception:
            self.repository.fail_operation(operation.operation_id, "grw-review-failed")
            raise
        return review

    def _non_change_proof(self, context: GrwM1Context) -> GrwNonChangeProof:
        """Fail closed when any pinned baseline artefact no longer matches."""

        workspace = self.repository.load_workspace(context.baseline.assessment_id)
        approved = workspace.active_artifacts.get(ArtifactType.APPROVED_REVIEW)
        integrated = workspace.active_artifacts.get(ArtifactType.INTEGRATED_ASSESSMENT_RESULT)
        package = workspace.active_artifacts.get(ArtifactType.DECISION_PACKAGE_RESULT)
        if (
            approved is None
            or integrated is None
            or package is None
            or self._reference(approved) != context.baseline.approved_review
            or self._reference(integrated) != context.baseline.integrated_assessment
            or self._reference(package) != context.baseline.decision_package
            or not isinstance(integrated.payload, IntegratedAssessmentSuccess)
            or not isinstance(package.payload, DecisionPackageSuccess)
        ):
            raise GrwM1Error("The immutable baseline no longer matches the submitted evidence")
        assessment_step = next(
            (
                item
                for item in integrated.payload.process_assessment.step_assessments
                if item.step_id == context.gap.step_id
            ),
            None,
        )
        package_item = next(
            (item for item in package.payload.package.portfolio.items if item.step_id == context.gap.step_id),
            None,
        )
        if assessment_step is None or package_item is None:
            raise GrwM1Error("The selected M1 step is absent from the immutable baseline")
        criterion = next(
            (item for item in assessment_step.criteria if item.criterion is CriterionName.REPETITION),
            None,
        )
        if criterion is None:
            raise GrwM1Error("The selected M1 criterion is absent from the immutable baseline")
        gate_payload = [item.model_dump(mode="json") for item in assessment_step.gate_results]
        gate_digest = hashlib.sha256(
            json.dumps(gate_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return GrwNonChangeProof(
            baseline=context.baseline,
            criterion=GrwCriterionSnapshot(
                criterion_name=criterion.criterion.value,
                value=criterion.value,
                knowledge_state=criterion.knowledge_state,
                rationale=criterion.rationale,
                evidence_ids=list(criterion.evidence_ids),
                confidence=criterion.confidence,
            ),
            gate_results=[item.model_copy(deep=True) for item in assessment_step.gate_results],
            gate_results_sha256=gate_digest,
            recommendation_mode=package_item.recommendation_mode,
            priority_status=package_item.priority_status,
            priority=(package_item.priority.model_copy(deep=True) if package_item.priority else None),
            roi_statement=package.payload.package.roi_statement,
        )

    @staticmethod
    def _operation_key(*parts: str) -> str:
        return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()

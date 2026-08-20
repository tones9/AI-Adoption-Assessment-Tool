"""Guarded M2 M1 lifecycle orchestration; baseline workspace is read-only."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ai_adoption_engine.application.assessment import IntegratedAssessmentService
from ai_adoption_engine.application.fingerprints import fingerprint_decision_policy
from ai_adoption_engine.decision_support.service import DecisionSupportPackageService
from ai_adoption_engine.grw.m2.comparison import M2ComparisonService
from ai_adoption_engine.grw.m2.instrument import load_instrument_reference
from ai_adoption_engine.grw.m2.models import (
    M2ActorDeclaration,
    M2ArtifactReference,
    M2ArtifactType,
    M2BaselineReference,
    M2DataReadinessResolution,
    M2DocumentLocator,
    M2DocumentSubmission,
    M2EvidencePermission,
    M2EvidenceReview,
    M2EvidenceClass,
    M2ConflictStatus,
    M2ReassessmentApproval,
    M2ReassessmentRequest,
    M2RunStage,
    M2StepGapReference,
    M2SupportingDocument,
    M2SuccessorAssessment,
    M2SuccessorDecisionPackage,
)
from ai_adoption_engine.grw.m2.policy import load_policy_reference
from ai_adoption_engine.grw.m2.projection import SuccessorReviewProjector
from ai_adoption_engine.models.decision_support import DecisionPackageSuccess, InformationGapKind
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.integrated_assessment import IntegratedAssessmentSuccess
from ai_adoption_engine.persistence.reassessment import SQLiteReassessmentRepository, assert_m2_write_target_allowed
from ai_adoption_engine.workspace.models import ArtifactType, StoredArtifact, WorkflowStage


MAX_SUPPORTING_DOCUMENT_BYTES = 100_000


class M2ReassessmentError(ValueError):
    """An operation attempted to exceed the approved M2 M1 contract."""


def _now() -> datetime:
    return datetime.now(UTC)


class M2ReassessmentService:
    """Separate M2 state machine; it never invokes workspace mutation methods."""

    def __init__(
        self,
        baseline_repository: Any,
        reassessment_repository: SQLiteReassessmentRepository,
        *,
        assessment_service: IntegratedAssessmentService | None = None,
        package_service: DecisionSupportPackageService | None = None,
        clock=_now,
        id_factory=None,
    ) -> None:
        self.baseline_repository = baseline_repository
        self.repository = reassessment_repository
        self.assessment_service = assessment_service or IntegratedAssessmentService()
        self.package_service = package_service or DecisionSupportPackageService()
        self.clock = clock
        self.id_factory = id_factory or (lambda prefix: f"{prefix}-{uuid4().hex}")
        self.projector = SuccessorReviewProjector()
        self.comparator = M2ComparisonService()

    def _guard(self) -> None:
        assert_m2_write_target_allowed(self.repository.path)

    @staticmethod
    def _key(payload: Any) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _begin(self, run_id: str, kind: str, payload: Any):
        operation = self.repository.begin_operation(run_id, kind, self._key(payload))
        if operation["status"] == "COMPLETED":
            artifact_id = operation["produced_artifact_id"]
            if artifact_id is None:
                raise M2ReassessmentError("Completed M2 operation has no immutable result")
            return operation, self.repository.load_artifact(artifact_id)
        if operation["status"] == "FAILED":
            raise M2ReassessmentError("This immutable M2 operation previously failed")
        return operation, None

    def _fail(self, operation: dict[str, Any] | None, code: str, *, stale: bool = False) -> None:
        if operation is not None and operation["status"] == "PENDING":
            self.repository.fail_operation(
                operation["operation_id"],
                code,
                terminal_stage=M2RunStage.STALE if stale else M2RunStage.FAILED,
            )

    @staticmethod
    def _ref(artifact: StoredArtifact) -> M2ArtifactReference:
        return M2ArtifactReference(artifact_id=artifact.artifact_id, artifact_revision=artifact.artifact_revision, payload_sha256=artifact.payload_sha256)

    def load_m2_baseline_reference(
        self, assessment_id: str
    ) -> M2BaselineReference | None:
        """Load the hash-pinned package-ready baseline without selecting a gap.

        Discovery callers need this historical identity even when the narrowly
        eligible data-readiness route is no longer actionable.  It is a read
        helper only; it introduces no new evidence or reassessment semantics.
        """

        workspace = self.baseline_repository.load_workspace(assessment_id)
        approved = workspace.active_artifacts.get(ArtifactType.APPROVED_REVIEW)
        integrated = workspace.active_artifacts.get(ArtifactType.INTEGRATED_ASSESSMENT_RESULT)
        package = workspace.active_artifacts.get(ArtifactType.DECISION_PACKAGE_RESULT)
        if workspace.assessment.current_stage is not WorkflowStage.PACKAGE_READY or not approved or not integrated or not package:
            return None
        if not isinstance(integrated.payload, IntegratedAssessmentSuccess) or not isinstance(package.payload, DecisionPackageSuccess):
            return None
        return M2BaselineReference(
            assessment_id=assessment_id,
            execution_mode=workspace.assessment.execution_mode.value,
            source_document_id=integrated.payload.lineage.source_document_id,
            approved_review=self._ref(approved), integrated_assessment=self._ref(integrated), decision_package=self._ref(package),
            package_id=package.payload.package.package_id,
            validated_process_fingerprint=integrated.payload.lineage.validated_process_fingerprint,
            decision_policy_id=integrated.payload.policy.policy_id,
            decision_policy_version=integrated.payload.policy.policy_version,
            decision_policy_status=integrated.payload.policy.policy_status,
            decision_policy_fingerprint=integrated.payload.policy.decision_policy_fingerprint,
        )

    def open_m2_m1_context(self, assessment_id: str) -> tuple[M2BaselineReference, M2StepGapReference] | None:
        baseline = self.load_m2_baseline_reference(assessment_id)
        if baseline is None:
            return None
        workspace = self.baseline_repository.load_workspace(assessment_id)
        approved = workspace.active_artifacts[ArtifactType.APPROVED_REVIEW]
        integrated = workspace.active_artifacts[ArtifactType.INTEGRATED_ASSESSMENT_RESULT]
        package = workspace.active_artifacts[ArtifactType.DECISION_PACKAGE_RESULT]
        for item in package.payload.package.portfolio.items:
            for gap in item.missing_information:
                if gap.kind is InformationGapKind.UNKNOWN_INPUT and gap.field_name == CriterionName.DATA_READINESS.value and gap.knowledge_state is KnowledgeState.UNKNOWN:
                    criterion = next((c for c in next(s for s in integrated.payload.process_assessment.step_assessments if s.step_id == item.step_id).criteria if c.criterion is CriterionName.DATA_READINESS), None)
                    if criterion is None or criterion.knowledge_state is not KnowledgeState.UNKNOWN:
                        continue
                    approved_step = next(s for s in approved.payload.business_process.steps if s.step_id == item.step_id)
                    required_known = (
                        CriterionName.AI_CAPABILITY_FIT,
                        CriterionName.PREDICTABILITY,
                        CriterionName.CONVENTIONAL_SOLUTION_FIT,
                        CriterionName.BUSINESS_VALUE,
                        CriterionName.HUMAN_JUDGEMENT_REQUIREMENT,
                        CriterionName.RISK_CONSEQUENCE,
                        CriterionName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT,
                        CriterionName.REPETITION,
                        CriterionName.IMPLEMENTATION_COMPLEXITY,
                    )
                    if any(approved_step.characteristics.criterion(name).knowledge_state is not KnowledgeState.KNOWN for name in required_known):
                        continue
                    if approved_step.characteristics.ai_capability_fit.value is None or approved_step.characteristics.ai_capability_fit.value < 3:
                        continue
                    if approved_step.characteristics.capability_signals.categorises_items.knowledge_state is not KnowledgeState.KNOWN or not approved_step.characteristics.capability_signals.categorises_items.value:
                        continue
                    return baseline, M2StepGapReference(package_id=baseline.package_id, step_id=item.step_id, current_activity=item.current_activity, information_gap=gap, baseline_value=criterion.value, baseline_knowledge_state=criterion.knowledge_state)
        return None

    def _assert_fresh_baseline(
        self, baseline: M2BaselineReference, *, run_id: str | None = None
    ) -> None:
        current = self.open_m2_m1_context(baseline.assessment_id)
        if current is None or current[0] != baseline:
            if run_id is not None:
                operation = self.repository.begin_operation(
                    run_id,
                    "STALE_BASELINE",
                    self._key(
                        {
                            "assessment_id": baseline.assessment_id,
                            "baseline_package": baseline.decision_package.model_dump(
                                mode="json"
                            ),
                        }
                    ),
                )
                self._fail(operation, "stale-baseline", stale=True)
            raise M2ReassessmentError("The pinned baseline is stale; no successor can be created")
        self._assert_decision_policy_fresh(baseline, run_id=run_id)

    def _assert_decision_policy_fresh(
        self, baseline: M2BaselineReference, *, run_id: str | None = None
    ) -> None:
        """M2 never mixes a pinned baseline with a later decision policy."""

        try:
            current_fingerprint = fingerprint_decision_policy(
                self.assessment_service.policy_loader()
            )
        except Exception as exc:
            if run_id is not None:
                operation = self.repository.begin_operation(
                    run_id,
                    "STALE_DECISION_POLICY",
                    self._key({"assessment_id": baseline.assessment_id, "reason": "unavailable"}),
                )
                self._fail(operation, "decision-policy-unavailable", stale=True)
            raise M2ReassessmentError(
                "Current decision policy could not be verified; reassessment is stale"
            ) from exc
        if current_fingerprint != baseline.decision_policy_fingerprint:
            if run_id is not None:
                operation = self.repository.begin_operation(
                    run_id,
                    "STALE_DECISION_POLICY",
                    self._key(
                        {
                            "assessment_id": baseline.assessment_id,
                            "pinned": baseline.decision_policy_fingerprint,
                            "current": current_fingerprint,
                        }
                    ),
                )
                self._fail(operation, "stale-decision-policy", stale=True)
            raise M2ReassessmentError(
                "Decision policy changed; reassessment is stale"
            )

    def create_run(self, assessment_id: str) -> tuple[str, M2BaselineReference, M2StepGapReference]:
        self._guard()
        context = self.open_m2_m1_context(assessment_id)
        if context is None:
            raise M2ReassessmentError("M2 M1 requires a package-ready baseline with UNKNOWN data_readiness")
        baseline, gap = context
        self._assert_decision_policy_fresh(baseline)
        creation_key = self._key({"baseline": baseline.model_dump(mode="json"), "step_id": gap.step_id, "gap": gap.information_gap.model_dump(mode="json")})
        manifest = {"baseline": baseline.model_dump(mode="json"), "gap": gap.model_dump(mode="json"), "creation_key": creation_key, "created_at": self.clock().isoformat()}
        run_id, _, _ = self.repository.create_run_with_manifest(
            assessment_id,
            baseline.decision_package.artifact_id,
            baseline.decision_package.payload_sha256,
            creation_idempotency_key=creation_key,
            manifest_payload=manifest,
        )
        return run_id, baseline, gap

    def submit_supporting_document(self, run_id: str, *, content_bytes: bytes, filename: str, source_label: str, submitter: M2ActorDeclaration) -> M2DocumentSubmission:
        self._guard()
        run = self.repository.load_run(run_id)
        existing_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.DOCUMENT_SUBMISSION)
        if existing_ref is not None:
            existing = self.repository.load_artifact(existing_ref.artifact_id)
            if existing.document.content_sha256 == hashlib.sha256(content_bytes).hexdigest() and existing.document.filename == filename and existing.document.source_label == source_label and existing.submitter == submitter:
                return existing
            raise M2ReassessmentError("A different supporting document cannot replace an immutable M2 submission")
        if M2RunStage(run["stage"]) is not M2RunStage.OPEN:
            raise M2ReassessmentError("A supporting document can be submitted only once to an open M2 run")
        if not isinstance(content_bytes, bytes) or not content_bytes or len(content_bytes) > MAX_SUPPORTING_DOCUMENT_BYTES:
            raise M2ReassessmentError("Supporting document must be non-empty text within the M2 M1 size limit")
        if not filename.lower().endswith(".txt"):
            raise M2ReassessmentError("M2 M1 accepts one plain-text (.txt) supporting document only")
        try:
            decoded = content_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise M2ReassessmentError("Supporting document must be valid UTF-8 plain text") from exc
        if not decoded.strip() or not source_label.strip():
            raise M2ReassessmentError("Supporting document text and source label are required")
        baseline, gap = self._baseline_from_manifest(run_id)
        self._assert_fresh_baseline(baseline, run_id=run_id)
        digest = hashlib.sha256(content_bytes).hexdigest()
        document = M2SupportingDocument(document_id=f"doc-{digest}", content_sha256=digest, filename=filename, byte_length=len(content_bytes), received_at=self.clock(), source_label=source_label)
        submission = M2DocumentSubmission(submission_id=self.id_factory("m2-document-submission"), run_id=run_id, submitted_at=self.clock(), baseline=baseline, gap=gap, document=document, submitter=submitter)
        manifest = self.repository.load_artifact_reference(run_id, M2ArtifactType.RUN_MANIFEST)
        assert manifest is not None
        operation, replay = self._begin(run_id, "SUBMIT_DOCUMENT", {"run_id": run_id, "document_sha256": digest, "filename": filename, "source_label": source_label, "submitter": submitter.model_dump(mode="json")})
        if replay is not None:
            return replay
        try:
            self.repository.save_document_and_submission(run_id, document, content_bytes, submission, manifest, operation_id=operation["operation_id"])
        except Exception:
            self._fail(operation, "document-submit-failed")
            raise
        return submission

    def review_document_evidence(self, run_id: str, *, reviewer: M2ActorDeclaration, locator: M2DocumentLocator, scope_statement: str, period_statement: str, source_authority: str, semantic_rationale: str, limitations: str, conflict_status: M2ConflictStatus, conflict_rationale: str, permission: M2EvidencePermission, reconciliation_statement: str | None = None, applicability_statement: str | None = None) -> M2EvidenceReview:
        self._guard()
        run = self.repository.load_run(run_id)
        existing_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.EVIDENCE_REVIEW)
        if existing_ref is not None:
            existing = self.repository.load_artifact(existing_ref.artifact_id)
            if (existing.reviewer == reviewer and existing.locator == locator and existing.scope_statement == scope_statement and existing.period_statement == period_statement and existing.source_authority == source_authority and existing.semantic_rationale == semantic_rationale and existing.limitations == limitations and existing.conflict_status is conflict_status and existing.conflict_rationale == conflict_rationale and existing.permission is permission and existing.reconciliation_statement == reconciliation_statement and existing.applicability_statement == applicability_statement):
                return existing
            raise M2ReassessmentError("A document evidence review is immutable and cannot be replaced")
        if M2RunStage(run["stage"]) is not M2RunStage.DOCUMENT_SUBMITTED:
            raise M2ReassessmentError("Document evidence review requires a submitted M2 document")
        baseline, _ = self._baseline_from_manifest(run_id)
        self._assert_fresh_baseline(baseline, run_id=run_id)
        submission_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.DOCUMENT_SUBMISSION)
        assert submission_ref is not None
        submission = self.repository.load_artifact(submission_ref.artifact_id)
        self._validate_locator(submission.document, locator)
        _, policy = load_policy_reference()
        review = M2EvidenceReview(review_id=self.id_factory("m2-evidence-review"), run_id=run_id, submission_artifact=submission_ref, reviewed_at=self.clock(), reviewer=reviewer, locator=locator, scope_statement=scope_statement, period_statement=period_statement, source_authority=source_authority, semantic_rationale=semantic_rationale, limitations=limitations, conflict_status=conflict_status, conflict_rationale=conflict_rationale, reconciliation_statement=reconciliation_statement, applicability_statement=applicability_statement, permission=permission, evidence_class=M2EvidenceClass.DOCUMENT_SUPPORTED if permission is M2EvidencePermission.CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE else None, admissibility_policy=policy)
        if conflict_status is M2ConflictStatus.UNRESOLVED:
            stage = M2RunStage.BLOCKED_CONFLICT
        elif permission is M2EvidencePermission.REJECTED:
            stage = M2RunStage.EVIDENCE_REJECTED
        elif permission is M2EvidencePermission.INSUFFICIENT_FOR_THIS_USE:
            stage = M2RunStage.INSUFFICIENT
        else:
            stage = M2RunStage.EVIDENCE_REVIEWED
        operation, replay = self._begin(run_id, "REVIEW_EVIDENCE", review.model_dump(mode="json", exclude={"review_id", "reviewed_at"}))
        if replay is not None:
            return replay
        try:
            self.repository.save_artifact_and_advance(run_id, M2ArtifactType.EVIDENCE_REVIEW, review, submission_ref.artifact_id, stage, operation_id=operation["operation_id"])
        except Exception:
            self._fail(operation, "evidence-review-failed")
            raise
        return review

    def propose_data_readiness_resolution(self, run_id: str, *, proposed_value: int | None, proposed_knowledge_state: KnowledgeState, mapping_rationale: str, data_owner: M2ActorDeclaration, criterion_reviewer: M2ActorDeclaration, narrowed_scope_statement: str | None = None, data_owner_reconciliation: str | None = None) -> M2DataReadinessResolution:
        self._guard()
        run = self.repository.load_run(run_id)
        existing_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.DATA_READINESS_RESOLUTION)
        if existing_ref is not None:
            existing = self.repository.load_artifact(existing_ref.artifact_id)
            if (existing.proposed_value == proposed_value and existing.proposed_knowledge_state is proposed_knowledge_state and existing.mapping_rationale == mapping_rationale and existing.data_owner == data_owner and existing.criterion_reviewer == criterion_reviewer):
                return existing
            raise M2ReassessmentError("A criterion resolution is immutable and cannot be replaced")
        if M2RunStage(run["stage"]) is not M2RunStage.EVIDENCE_REVIEWED:
            raise M2ReassessmentError("Criterion resolution requires accepted document evidence")
        baseline, gap = self._baseline_from_manifest(run_id)
        self._assert_fresh_baseline(baseline, run_id=run_id)
        review_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.EVIDENCE_REVIEW)
        assert review_ref is not None
        review = self.repository.load_artifact(review_ref.artifact_id)
        self._assert_document_and_policy_fresh(run_id, review)
        if review.permission is not M2EvidencePermission.CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE or review.evidence_class is not M2EvidenceClass.DOCUMENT_SUPPORTED:
            raise M2ReassessmentError("Evidence is not admissible for M2 M1 criterion resolution")
        if review.conflict_status in {M2ConflictStatus.PARTIALLY_OVERLAPPING, M2ConflictStatus.DIFFERENT_SCOPE} and not narrowed_scope_statement:
            raise M2ReassessmentError("A scope conflict requires an explicit narrowed evidence scope")
        if review.conflict_status is M2ConflictStatus.CONTRADICTORY and (not review.reconciliation_statement or not data_owner_reconciliation):
            raise M2ReassessmentError("Contradictory evidence requires reviewer and data-owner reconciliation")
        if review.conflict_status is M2ConflictStatus.STALE_OR_SUPERSEDED and not review.applicability_statement:
            raise M2ReassessmentError("Stale or superseded evidence requires a target-scope applicability statement")
        if review.conflict_status is M2ConflictStatus.UNRESOLVED:
            raise M2ReassessmentError("Unresolved material conflict cannot resolve data readiness")
        if proposed_value == 5 or proposed_value not in {None, 0, 1, 2, 3, 4}:
            raise M2ReassessmentError("Document-only M2 M1 permits values 0–4 only; data_readiness = 5 requires future measured evidence")
        if proposed_knowledge_state is KnowledgeState.KNOWN and proposed_value is None:
            raise M2ReassessmentError("A known data-readiness resolution requires a reviewed instrument value")
        _, policy = load_policy_reference(); _, instrument = load_instrument_reference()
        resolution = M2DataReadinessResolution(resolution_id=self.id_factory("m2-data-readiness-resolution"), run_id=run_id, evidence_review_artifact=review_ref, baseline_value=gap.baseline_value, baseline_knowledge_state=gap.baseline_knowledge_state, proposed_value=proposed_value, proposed_knowledge_state=proposed_knowledge_state, mapping_rationale=mapping_rationale, document_locators=[review.locator], narrowed_scope_statement=narrowed_scope_statement, data_owner_reconciliation=data_owner_reconciliation, data_owner=data_owner, criterion_reviewer=criterion_reviewer, instrument=instrument, admissibility_policy=policy)
        operation, replay = self._begin(run_id, "RESOLVE_DATA_READINESS", resolution.model_dump(mode="json", exclude={"resolution_id"}))
        if replay is not None:
            return replay
        try:
            self.repository.save_artifact_and_advance(run_id, M2ArtifactType.DATA_READINESS_RESOLUTION, resolution, review_ref.artifact_id, M2RunStage.RESOLUTION_PROPOSED, operation_id=operation["operation_id"])
        except Exception:
            self._fail(operation, "resolution-failed")
            raise
        return resolution

    def request_reassessment(self, run_id: str) -> M2ReassessmentRequest:
        self._guard()
        run = self.repository.load_run(run_id)
        existing_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.REASSESSMENT_REQUEST)
        if existing_ref is not None:
            return self.repository.load_artifact(existing_ref.artifact_id)
        if M2RunStage(run["stage"]) is not M2RunStage.RESOLUTION_PROPOSED:
            raise M2ReassessmentError("Reassessment requires a reviewed criterion resolution")
        baseline, gap = self._baseline_from_manifest(run_id); self._assert_fresh_baseline(baseline, run_id=run_id)
        review_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.EVIDENCE_REVIEW); resolution_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.DATA_READINESS_RESOLUTION)
        assert review_ref and resolution_ref
        review = self.repository.load_artifact(review_ref.artifact_id); resolution = self.repository.load_artifact(resolution_ref.artifact_id)
        self._assert_document_and_policy_fresh(run_id, review, resolution)
        if resolution.proposed_knowledge_state is not KnowledgeState.KNOWN or resolution.proposed_value is None or review.conflict_status is M2ConflictStatus.UNRESOLVED:
            raise M2ReassessmentError("Retained unknown or unresolved conflict cannot request a formal reassessment")
        request_body = {"baseline": baseline.model_dump(mode="json"), "gap": gap.model_dump(mode="json"), "review": review_ref.model_dump(mode="json"), "resolution": resolution_ref.model_dump(mode="json"), "policy": resolution.admissibility_policy.model_dump(mode="json"), "instrument": resolution.instrument.model_dump(mode="json")}
        request = M2ReassessmentRequest(request_id=self.id_factory("m2-reassessment-request"), run_id=run_id, requested_at=self.clock(), baseline=baseline, gap=gap, evidence_review_artifact=review_ref, resolution_artifact=resolution_ref, conflict_status=review.conflict_status, data_owner=resolution.data_owner, criterion_reviewer=resolution.criterion_reviewer, baseline_decision_policy_fingerprint=baseline.decision_policy_fingerprint, request_sha256=self._key(request_body), admissibility_policy=resolution.admissibility_policy, instrument=resolution.instrument)
        operation, replay = self._begin(run_id, "REQUEST_REASSESSMENT", request_body)
        if replay is not None:
            return replay
        try:
            self.repository.save_artifact_and_advance(run_id, M2ArtifactType.REASSESSMENT_REQUEST, request, resolution_ref.artifact_id, M2RunStage.REQUESTED, operation_id=operation["operation_id"])
        except Exception:
            self._fail(operation, "request-failed")
            raise
        return request

    def approve_reassessment(self, run_id: str, *, approver: M2ActorDeclaration, rationale: str, exact_change: str = "Resolve only the selected data_readiness criterion in a separate successor.", retained_uncertainty: str = "Document limitations remain explicit; no deployment, outcome, or ROI claim is made.") -> M2ReassessmentApproval:
        self._guard()
        run = self.repository.load_run(run_id)
        existing_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.REASSESSMENT_APPROVAL)
        if existing_ref is not None:
            existing = self.repository.load_artifact(existing_ref.artifact_id)
            if existing.approver == approver and existing.rationale == rationale:
                return existing
            raise M2ReassessmentError("A reassessment approval is immutable and cannot be replaced")
        if M2RunStage(run["stage"]) is not M2RunStage.REQUESTED:
            raise M2ReassessmentError("Explicit approval is required before successor creation")
        baseline, _ = self._baseline_from_manifest(run_id); self._assert_fresh_baseline(baseline, run_id=run_id)
        request_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.REASSESSMENT_REQUEST); assert request_ref
        request = self.repository.load_artifact(request_ref.artifact_id)
        review = self.repository.load_artifact(request.evidence_review_artifact.artifact_id)
        resolution = self.repository.load_artifact(request.resolution_artifact.artifact_id)
        self._assert_document_and_policy_fresh(run_id, review, resolution)
        approval = M2ReassessmentApproval(approval_id=self.id_factory("m2-reassessment-approval"), run_id=run_id, request_artifact=request_ref, approved_at=self.clock(), approver=approver, rationale=rationale, exact_change=exact_change, retained_uncertainty=retained_uncertainty, conflict_status=request.conflict_status, acknowledged_no_verified_role_separation=approver.acknowledged_local_role_limitation)
        operation, replay = self._begin(run_id, "APPROVE_REASSESSMENT", approval.model_dump(mode="json", exclude={"approval_id", "approved_at"}))
        if replay is not None:
            return replay
        try:
            self.repository.save_artifact_and_advance(run_id, M2ArtifactType.REASSESSMENT_APPROVAL, approval, request_ref.artifact_id, M2RunStage.APPROVED, operation_id=operation["operation_id"])
        except Exception:
            self._fail(operation, "approval-failed")
            raise
        return approval

    def build_successor_review(self, run_id: str):
        self._guard()
        run = self.repository.load_run(run_id)
        existing_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.SUCCESSOR_APPROVED_REVIEW)
        if existing_ref is not None:
            return self.repository.load_artifact(existing_ref.artifact_id)
        if M2RunStage(run["stage"]) is not M2RunStage.APPROVED:
            raise M2ReassessmentError("Successor review requires explicit reassessment approval")
        baseline, gap = self._baseline_from_manifest(run_id); self._assert_fresh_baseline(baseline, run_id=run_id)
        baseline_approved = self._load_baseline_artifact(baseline.approved_review).payload
        approval_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.REASSESSMENT_APPROVAL); resolution_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.DATA_READINESS_RESOLUTION); submission_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.DOCUMENT_SUBMISSION); review_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.EVIDENCE_REVIEW)
        assert approval_ref and resolution_ref and submission_ref and review_ref
        request_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.REASSESSMENT_REQUEST); assert request_ref
        approval = self.repository.load_artifact(approval_ref.artifact_id); resolution = self.repository.load_artifact(resolution_ref.artifact_id); submission = self.repository.load_artifact(submission_ref.artifact_id); evidence_review = self.repository.load_artifact(review_ref.artifact_id)
        self._assert_document_and_policy_fresh(run_id, evidence_review, resolution)
        successor = self.projector.build(run_id=run_id, baseline_artifact=baseline.approved_review, baseline_approved=baseline_approved, request_artifact=request_ref, approval_artifact=approval_ref, approval=approval, evidence_review_artifact=review_ref, resolution_artifact=resolution_ref, resolution=resolution, document=submission.document, locator=evidence_review.locator, target_step_id=gap.step_id, successor_review_id=self.id_factory("m2-successor-review"), successor_approval_event_id=self.id_factory("m2-successor-approval"))
        operation, replay = self._begin(run_id, "BUILD_SUCCESSOR_REVIEW", {"approval": approval_ref.model_dump(mode="json")})
        if replay is not None:
            return replay
        try:
            self.repository.save_artifact_and_advance(run_id, M2ArtifactType.SUCCESSOR_APPROVED_REVIEW, successor, approval_ref.artifact_id, M2RunStage.SUCCESSOR_REVIEW_READY, operation_id=operation["operation_id"])
        except Exception:
            self._fail(operation, "successor-projection-failed")
            raise
        return successor

    def assess_successor(self, run_id: str) -> M2SuccessorAssessment:
        self._guard()
        run = self.repository.load_run(run_id)
        existing_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.SUCCESSOR_INTEGRATED_ASSESSMENT)
        if existing_ref is not None:
            return self.repository.load_artifact(existing_ref.artifact_id)
        if M2RunStage(run["stage"]) is not M2RunStage.SUCCESSOR_REVIEW_READY:
            raise M2ReassessmentError("A successor review is required before Phase 5 reassessment")
        baseline, _ = self._baseline_from_manifest(run_id); self._assert_fresh_baseline(baseline, run_id=run_id)
        successor_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.SUCCESSOR_APPROVED_REVIEW); assert successor_ref
        successor = self.repository.load_artifact(successor_ref.artifact_id)
        review = self.repository.load_artifact(
            successor.evidence_review_artifact.artifact_id
        )
        resolution = self.repository.load_artifact(
            successor.resolution_artifact.artifact_id
        )
        self._assert_document_and_policy_fresh(run_id, review, resolution)
        operation, replay = self._begin(run_id, "ASSESS_SUCCESSOR", {"successor": successor_ref.model_dump(mode="json"), "decision_policy": baseline.decision_policy_fingerprint})
        if replay is not None:
            return replay
        try:
            result = self.assessment_service.assess_successor(successor, reassessment_repository=self.repository)
        except Exception:
            self._fail(operation, "phase5-execution-failed")
            raise
        if not isinstance(result, IntegratedAssessmentSuccess):
            self._fail(operation, "phase5-validation-failed")
            raise M2ReassessmentError("Phase 5 successor assessment failed without producing a successor package")
        if result.policy.decision_policy_fingerprint != baseline.decision_policy_fingerprint:
            self._fail(operation, "stale-decision-policy", stale=True)
            raise M2ReassessmentError("Decision policy changed; successor reassessment is stale")
        _, policy = load_policy_reference(); _, instrument = load_instrument_reference()
        payload = M2SuccessorAssessment(run_id=run_id, successor_review_artifact=successor_ref, request_artifact=successor.request_artifact, approval_artifact=successor.approval_artifact, evidence_review_artifact=successor.evidence_review_artifact, resolution_artifact=successor.resolution_artifact, integrated_assessment=result, baseline=baseline, admissibility_policy=policy, instrument=instrument)
        try:
            self.repository.save_artifact_and_advance(run_id, M2ArtifactType.SUCCESSOR_INTEGRATED_ASSESSMENT, payload, successor_ref.artifact_id, M2RunStage.ASSESSED, operation_id=operation["operation_id"])
        except Exception:
            self._fail(operation, "phase5-persist-failed")
            raise
        return payload

    def generate_successor_package(self, run_id: str) -> M2SuccessorDecisionPackage:
        self._guard()
        run = self.repository.load_run(run_id)
        existing_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.SUCCESSOR_DECISION_PACKAGE)
        if existing_ref is not None:
            return self.repository.load_artifact(existing_ref.artifact_id)
        if M2RunStage(run["stage"]) is not M2RunStage.ASSESSED:
            raise M2ReassessmentError("A successful successor assessment is required before Phase 6 packaging")
        baseline, _ = self._baseline_from_manifest(run_id); self._assert_fresh_baseline(baseline, run_id=run_id)
        assessment_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.SUCCESSOR_INTEGRATED_ASSESSMENT); assert assessment_ref
        successor_assessment = self.repository.load_artifact(assessment_ref.artifact_id)
        review = self.repository.load_artifact(successor_assessment.evidence_review_artifact.artifact_id)
        resolution = self.repository.load_artifact(successor_assessment.resolution_artifact.artifact_id)
        self._assert_document_and_policy_fresh(run_id, review, resolution)
        operation, replay = self._begin(run_id, "GENERATE_SUCCESSOR_PACKAGE", {"assessment": assessment_ref.model_dump(mode="json")})
        if replay is not None:
            return replay
        try:
            package = self.package_service.generate(successor_assessment.integrated_assessment)
        except Exception:
            self._fail(operation, "phase6-execution-failed")
            raise
        if not isinstance(package, DecisionPackageSuccess):
            self._fail(operation, "phase6-validation-failed")
            raise M2ReassessmentError("Phase 6 successor package generation failed")
        payload = M2SuccessorDecisionPackage(run_id=run_id, successor_assessment_artifact=assessment_ref, request_artifact=successor_assessment.request_artifact, approval_artifact=successor_assessment.approval_artifact, evidence_review_artifact=successor_assessment.evidence_review_artifact, resolution_artifact=successor_assessment.resolution_artifact, decision_package=package, baseline=baseline)
        try:
            self.repository.save_artifact_and_advance(run_id, M2ArtifactType.SUCCESSOR_DECISION_PACKAGE, payload, assessment_ref.artifact_id, M2RunStage.PACKAGE_READY, operation_id=operation["operation_id"])
        except Exception:
            self._fail(operation, "phase6-persist-failed")
            raise
        return payload

    def compare(self, run_id: str):
        self._guard()
        run = self.repository.load_run(run_id)
        existing_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.BASELINE_SUCCESSOR_COMPARISON)
        if existing_ref is not None:
            return self.repository.load_artifact(existing_ref.artifact_id)
        if M2RunStage(run["stage"]) is not M2RunStage.PACKAGE_READY:
            raise M2ReassessmentError("A successor Decision Package is required before comparison")
        baseline, gap = self._baseline_from_manifest(run_id); self._assert_fresh_baseline(baseline, run_id=run_id)
        baseline_package = self._load_baseline_artifact(baseline.decision_package).payload
        successor_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.SUCCESSOR_DECISION_PACKAGE); assert successor_ref
        successor_package = self.repository.load_artifact(successor_ref.artifact_id)
        resolution_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.DATA_READINESS_RESOLUTION); assert resolution_ref
        resolution = self.repository.load_artifact(resolution_ref.artifact_id)
        review = self.repository.load_artifact(resolution.evidence_review_artifact.artifact_id)
        self._assert_document_and_policy_fresh(run_id, review, resolution)
        operation, replay = self._begin(run_id, "COMPARE", {"baseline_package": baseline.decision_package.model_dump(mode="json"), "successor_package": successor_ref.model_dump(mode="json")})
        if replay is not None:
            return replay
        try:
            comparison = self.comparator.compare(comparison_id=self.id_factory("m2-comparison"), run_id=run_id, created_at=self.clock(), baseline=baseline, baseline_package=baseline_package, successor_package_artifact=successor_ref, successor_package=successor_package.decision_package, target_step_id=gap.step_id, baseline_data_readiness=gap.baseline_value, successor_data_readiness=resolution.proposed_value)
            self.repository.save_artifact_and_advance(run_id, M2ArtifactType.BASELINE_SUCCESSOR_COMPARISON, comparison, successor_ref.artifact_id, M2RunStage.COMPARED, operation_id=operation["operation_id"])
        except Exception:
            self._fail(operation, "comparison-failed")
            raise
        return comparison

    def _baseline_from_manifest(self, run_id: str) -> tuple[M2BaselineReference, M2StepGapReference]:
        manifest_ref = self.repository.load_artifact_reference(run_id, M2ArtifactType.RUN_MANIFEST)
        if manifest_ref is None:
            raise M2ReassessmentError("M2 run manifest is missing")
        manifest = self.repository.load_artifact(manifest_ref.artifact_id)
        return M2BaselineReference.model_validate(manifest["baseline"]), M2StepGapReference.model_validate(manifest["gap"])

    def _load_baseline_artifact(self, reference: M2ArtifactReference) -> StoredArtifact:
        artifact = self.baseline_repository.load_artifact(reference.artifact_id)
        if self._ref(artifact) != reference:
            raise M2ReassessmentError("Pinned baseline artifact is stale or corrupted")
        return artifact

    def _validate_locator(self, document: M2SupportingDocument, locator: M2DocumentLocator) -> None:
        raw = self.repository.load_document_bytes(document.document_id)
        if hashlib.sha256(raw).hexdigest() != document.content_sha256:
            raise M2ReassessmentError("Supporting document content hash changed")
        text = raw.decode("utf-8")
        if text[locator.start_offset:locator.end_offset] != locator.exact_excerpt:
            raise M2ReassessmentError("Document locator does not reproduce its exact excerpt")
        line_start = text.count("\n", 0, locator.start_offset) + 1
        line_end = text.count("\n", 0, locator.end_offset) + 1
        if (line_start, line_end) != (locator.line_start, locator.line_end):
            raise M2ReassessmentError("Document locator line range is inconsistent with stored text")

    def _assert_document_and_policy_fresh(self, run_id: str, review: M2EvidenceReview, resolution: M2DataReadinessResolution | None = None) -> None:
        submission = self.repository.load_artifact(review.submission_artifact.artifact_id)
        try:
            self._validate_locator(submission.document, review.locator)
        except M2ReassessmentError:
            operation = self.repository.begin_operation(run_id, "STALE_EVIDENCE", self._key({"review": review.review_id, "reason": "document-hash"}))
            self._fail(operation, "stale-document-hash", stale=True)
            raise
        _, policy = load_policy_reference()
        if review.admissibility_policy != policy or (resolution is not None and resolution.admissibility_policy != policy):
            operation = self.repository.begin_operation(run_id, "STALE_POLICY", self._key({"review": review.review_id, "reason": "admissibility-policy"}))
            self._fail(operation, "stale-admissibility-policy", stale=True)
            raise M2ReassessmentError("M2 admissibility policy changed; reassessment is stale")
        if resolution is not None:
            _, instrument = load_instrument_reference()
            if resolution.instrument != instrument:
                operation = self.repository.begin_operation(run_id, "STALE_INSTRUMENT", self._key({"resolution": resolution.resolution_id, "reason": "instrument"}))
                self._fail(operation, "stale-data-readiness-instrument", stale=True)
                raise M2ReassessmentError("M2 data-readiness instrument changed; reassessment is stale")

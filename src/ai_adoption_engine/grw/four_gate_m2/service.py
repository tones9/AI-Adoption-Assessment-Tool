"""Explicit core lifecycle for same-contract four-gate reassessment."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from ai_adoption_engine.application.fingerprints import fingerprint_four_gate_policy
from ai_adoption_engine.application.four_gate_assessment import (
    FourGateIntegratedAssessmentService,
)
from ai_adoption_engine.application.four_gate_decision_continuation import (
    DecisionContinuationContractFamily,
    discriminate_decision_continuation,
)
from ai_adoption_engine.decision.four_gate_policy import FourGateDecisionPolicy
from ai_adoption_engine.decision_support.four_gate_service import (
    FourGateDecisionSupportPackageService,
)
from ai_adoption_engine.grw.four_gate_m2.comparison import (
    FourGateM2ComparisonService,
)
from ai_adoption_engine.grw.four_gate_m2.models import (
    FourGateM2ActorDeclaration,
    FourGateM2ArtifactReference,
    FourGateM2ArtifactType,
    FourGateM2BaselineReference,
    FourGateM2ConflictStatus,
    FourGateM2DataReadinessResolution,
    FourGateM2DocumentLocator,
    FourGateM2DocumentSubmission,
    FourGateM2EvidencePermission,
    FourGateM2EvidenceReview,
    FourGateM2GapReference,
    FourGateM2ReassessmentApproval,
    FourGateM2ReassessmentRequest,
    FourGateM2RunManifest,
    FourGateM2RunStage,
    FourGateM2SuccessorApprovedReview,
    FourGateM2SuccessorAssessment,
    FourGateM2SuccessorDecisionPackage,
    FourGateM2SupportingDocument,
)
from ai_adoption_engine.grw.four_gate_m2.projection import (
    FourGateM2SuccessorProjector,
    assert_one_field_projection,
)
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.four_gate_assessment import (
    DecisionStatus,
    FourGateName,
    FourGateStatus,
    OutcomeCode,
)
from ai_adoption_engine.models.four_gate_decision_support import (
    FourGateDecisionPackageSuccess,
    FourGateInformationGapKind,
)
from ai_adoption_engine.models.four_gate_integrated_assessment import (
    FourGateIntegratedAssessmentSuccess,
)
from ai_adoption_engine.persistence.four_gate_reassessment import (
    FourGateM2PersistenceError,
    SQLiteFourGateReassessmentRepository,
)
from ai_adoption_engine.workspace.models import ArtifactType, StoredArtifact


MAX_DOCUMENT_BYTES = 2_000_000


class FourGateM2Error(ValueError):
    pass


class FourGateM2Service:
    """Successor-only service; policy selection is always explicit."""

    def __init__(
        self,
        baseline_repository,
        repository: SQLiteFourGateReassessmentRepository,
        *,
        policy_loader,
        phase5_service_factory=None,
        phase6_service=None,
        projector=None,
        comparator=None,
        clock=None,
        id_factory=None,
    ) -> None:
        if Path(baseline_repository.path).resolve() != repository.path.resolve():
            raise FourGateM2Error(
                "Successor reassessment must use the pinned baseline workspace"
            )
        self.baseline_repository = baseline_repository
        self.repository = repository
        self.policy_loader = policy_loader
        self.clock = clock or (lambda: datetime.now(UTC))
        self.id_factory = id_factory or repository.id_factory
        self.phase5_service_factory = phase5_service_factory or (
            lambda loader: FourGateIntegratedAssessmentService(
                policy_loader=loader,
                clock=self.clock,
                run_id_factory=lambda: self.id_factory("four-gate-assessment"),
            )
        )
        self.phase6_service = phase6_service or FourGateDecisionSupportPackageService()
        self.projector = projector or FourGateM2SuccessorProjector()
        self.comparator = comparator or FourGateM2ComparisonService()

    def open_context(
        self, assessment_id: str, target_step_id: str
    ) -> tuple[FourGateM2BaselineReference, FourGateM2GapReference] | None:
        snapshot = self.baseline_repository.load_workspace(assessment_id)
        contract = discriminate_decision_continuation(snapshot)
        if contract.contract_family is not DecisionContinuationContractFamily.FOUR_GATE:
            return None
        baseline_view = contract.successor_baseline
        if baseline_view is None:
            return None
        integrated_artifact = snapshot.active_artifacts[
            ArtifactType.INTEGRATED_ASSESSMENT_RESULT
        ]
        package_artifact = snapshot.active_artifacts[
            ArtifactType.DECISION_PACKAGE_RESULT
        ]
        approved_artifact = snapshot.active_artifacts[ArtifactType.APPROVED_REVIEW]
        integrated = integrated_artifact.payload
        package_result = package_artifact.payload
        if not isinstance(integrated, FourGateIntegratedAssessmentSuccess) or not isinstance(
            package_result, FourGateDecisionPackageSuccess
        ):
            return None
        item = next(
            (
                value
                for value in package_result.package.portfolio.items
                if value.step_id == target_step_id
            ),
            None,
        )
        assessed = next(
            (
                value
                for value in integrated.process_assessment.step_assessments
                if value.step_id == target_step_id
            ),
            None,
        )
        if item is None or assessed is None:
            return None
        active_gaps = [
            gap
            for gap in item.information_gaps
            if gap.kind is FourGateInformationGapKind.ACTIVE_DECISION_BLOCKER
        ]
        criterion = next(
            (
                value
                for value in assessed.criteria
                if value.criterion is CriterionName.DATA_READINESS
            ),
            None,
        )
        gate_two = assessed.gate_results[1]
        if (
            item.decision_status is not DecisionStatus.DISCOVERY_REQUIRED
            or item.outcome_code is not OutcomeCode.DISCOVERY_REQUIRED
            or len(active_gaps) != 1
            or len(assessed.blocking_gaps) != 1
            or active_gaps[0].gate is not FourGateName.IS_IT_READY
            or active_gaps[0].field_name != CriterionName.DATA_READINESS.value
            or assessed.blocking_gaps[0].gate is not FourGateName.IS_IT_READY
            or assessed.blocking_gaps[0].field_name
            != CriterionName.DATA_READINESS.value
            or gate_two.gate is not FourGateName.IS_IT_READY
            or gate_two.status is not FourGateStatus.BLOCKED_BY_EVIDENCE
            or criterion is None
            or criterion.knowledge_state is not KnowledgeState.UNKNOWN
            or criterion.value is not None
        ):
            return None
        baseline = FourGateM2BaselineReference(
            assessment_id=assessment_id,
            execution_mode=snapshot.assessment.execution_mode.value,
            source_document_id=integrated.lineage.source_document_id,
            approved_review=_reference(approved_artifact),
            integrated_assessment=_reference(integrated_artifact),
            decision_package=_reference(package_artifact),
            package_id=package_result.package.package_id,
            validated_process_fingerprint=integrated.lineage.validated_process_fingerprint,
            framework_id=integrated.process_assessment.framework_id,
            framework_version=integrated.process_assessment.framework_version,
            phase1_contract_version=integrated.metadata.phase1_contract_version,
            phase5_schema_version=integrated.metadata.integration_schema_version,
            phase6_schema_version=package_result.package.package_schema_version,
            decision_policy_id=integrated.policy.policy_id,
            decision_policy_version=integrated.policy.policy_version,
            decision_policy_status=integrated.policy.policy_status,
            decision_policy_fingerprint=(
                integrated.policy.decision_policy_fingerprint
            ),
        )
        target = FourGateM2GapReference(
            package_id=baseline.package_id,
            step_id=item.step_id,
            activity=item.activity,
            information_gap=active_gaps[0],
            gate_result=gate_two,
            baseline_value=None,
            baseline_knowledge_state=KnowledgeState.UNKNOWN,
        )
        return baseline, target

    def create_run(
        self, assessment_id: str, target_step_id: str
    ) -> FourGateM2RunManifest:
        context = self.open_context(assessment_id, target_step_id)
        if context is None:
            raise FourGateM2Error(
                "Successor reassessment requires active Gate 2 data_readiness discovery"
            )
        baseline, target = context
        self._load_pinned_policy(baseline)
        key = _hash(
            {
                "baseline": baseline.model_dump(mode="json"),
                "target": target.model_dump(mode="json"),
            }
        )
        manifest = FourGateM2RunManifest(
            run_id=self.id_factory("four-gate-reassessment-run"),
            created_at=self.clock(),
            baseline=baseline,
            target=target,
            creation_idempotency_key=key,
        )
        run_id, reference, reused = self.repository.create_run_with_manifest(manifest)
        if reused:
            stored = self.repository.load_artifact(reference.artifact_id)
            if stored.baseline != baseline or stored.target != target:
                raise FourGateM2Error("Idempotent run does not match the baseline")
            return stored
        if run_id != manifest.run_id:
            raise FourGateM2Error("Persisted run identity is inconsistent")
        return manifest

    def submit_supporting_document(
        self,
        run_id: str,
        *,
        content_bytes: bytes,
        filename: str,
        source_label: str,
        submitter: FourGateM2ActorDeclaration,
    ) -> FourGateM2DocumentSubmission:
        existing = self._existing(run_id, FourGateM2ArtifactType.DOCUMENT_SUBMISSION)
        if not isinstance(content_bytes, bytes):
            raise FourGateM2Error("Supporting evidence must be supplied as bytes")
        digest = hashlib.sha256(content_bytes).hexdigest()
        if existing is not None:
            if (
                existing.document.content_sha256 == digest
                and existing.document.filename == filename
                and existing.document.source_label == source_label
                and existing.submitter == submitter
            ):
                return existing
            raise FourGateM2Error("A different document cannot replace the candidate")
        manifest = self._assert_fresh(run_id)
        if (
            not isinstance(content_bytes, bytes)
            or not content_bytes
            or len(content_bytes) > MAX_DOCUMENT_BYTES
            or not filename.lower().endswith(".txt")
        ):
            raise FourGateM2Error("Supporting evidence must be non-empty UTF-8 text")
        try:
            content_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FourGateM2Error("Supporting evidence must be valid UTF-8") from exc
        document = FourGateM2SupportingDocument(
            document_id=f"doc-{digest}",
            content_sha256=digest,
            filename=filename,
            byte_length=len(content_bytes),
            received_at=self.clock(),
            source_label=source_label,
        )
        submission = FourGateM2DocumentSubmission(
            submission_id=self.id_factory("four-gate-document-submission"),
            run_id=run_id,
            submitted_at=self.clock(),
            baseline=manifest.baseline,
            target=manifest.target,
            document=document,
            submitter=submitter,
        )
        parent = self._required_ref(run_id, FourGateM2ArtifactType.RUN_MANIFEST)
        self.repository.save_document_and_submission(
            run_id,
            document,
            content_bytes,
            submission,
            parent=parent,
            idempotency_key=_hash(submission.model_dump(mode="json")),
        )
        return submission

    def review_document_evidence(
        self,
        run_id: str,
        *,
        reviewer: FourGateM2ActorDeclaration,
        locator: FourGateM2DocumentLocator,
        scope_statement: str,
        period_statement: str,
        source_authority: str,
        applicability_statement: str,
        semantic_rationale: str,
        limitations: str,
        conflict_status: FourGateM2ConflictStatus,
        conflict_rationale: str,
        permission: FourGateM2EvidencePermission,
    ) -> FourGateM2EvidenceReview:
        existing = self._existing(run_id, FourGateM2ArtifactType.EVIDENCE_REVIEW)
        if existing is not None:
            candidate = existing.model_dump(
                mode="json", exclude={"review_id", "reviewed_at"}
            )
            supplied = {
                **candidate,
                "reviewer": reviewer.model_dump(mode="json"),
                "locator": locator.model_dump(mode="json"),
                "scope_statement": scope_statement,
                "period_statement": period_statement,
                "source_authority": source_authority,
                "applicability_statement": applicability_statement,
                "semantic_rationale": semantic_rationale,
                "limitations": limitations,
                "conflict_status": conflict_status.value,
                "conflict_rationale": conflict_rationale,
                "permission": permission.value,
            }
            if candidate == supplied:
                return existing
            raise FourGateM2Error("Evidence review is immutable")
        self._assert_fresh(run_id)
        submission = self._required_artifact(
            run_id, FourGateM2ArtifactType.DOCUMENT_SUBMISSION
        )
        self._validate_locator(submission.document, locator)
        if (
            permission
            is FourGateM2EvidencePermission.CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE
            and conflict_status is not FourGateM2ConflictStatus.CONSISTENT
        ):
            raise FourGateM2Error(
                "Conflicted or inapplicable evidence cannot resolve data_readiness"
            )
        review = FourGateM2EvidenceReview(
            review_id=self.id_factory("four-gate-evidence-review"),
            run_id=run_id,
            baseline=submission.baseline,
            target=submission.target,
            submission_artifact=self._required_ref(
                run_id, FourGateM2ArtifactType.DOCUMENT_SUBMISSION
            ),
            reviewed_at=self.clock(),
            reviewer=reviewer,
            locator=locator,
            scope_statement=scope_statement,
            period_statement=period_statement,
            source_authority=source_authority,
            applicability_statement=applicability_statement,
            semantic_rationale=semantic_rationale,
            limitations=limitations,
            conflict_status=conflict_status,
            conflict_rationale=conflict_rationale,
            permission=permission,
        )
        if conflict_status is not FourGateM2ConflictStatus.CONSISTENT:
            stage = FourGateM2RunStage.BLOCKED_CONFLICT
        elif permission is FourGateM2EvidencePermission.REJECTED:
            stage = FourGateM2RunStage.EVIDENCE_REJECTED
        elif permission is FourGateM2EvidencePermission.INSUFFICIENT_FOR_THIS_USE:
            stage = FourGateM2RunStage.INSUFFICIENT
        else:
            stage = FourGateM2RunStage.EVIDENCE_REVIEWED
        self._save(
            run_id,
            FourGateM2ArtifactType.EVIDENCE_REVIEW,
            review,
            FourGateM2ArtifactType.DOCUMENT_SUBMISSION,
            FourGateM2RunStage.DOCUMENT_SUBMITTED,
            stage,
        )
        return review

    def propose_data_readiness_resolution(
        self,
        run_id: str,
        *,
        proposed_value: int | None,
        proposed_knowledge_state: KnowledgeState,
        mapping_rationale: str,
        data_owner: FourGateM2ActorDeclaration,
        criterion_reviewer: FourGateM2ActorDeclaration,
    ) -> FourGateM2DataReadinessResolution:
        existing = self._existing(
            run_id, FourGateM2ArtifactType.DATA_READINESS_RESOLUTION
        )
        if existing is not None:
            if (
                existing.proposed_value == proposed_value
                and existing.proposed_knowledge_state is proposed_knowledge_state
                and existing.mapping_rationale == mapping_rationale
                and existing.data_owner == data_owner
                and existing.criterion_reviewer == criterion_reviewer
            ):
                return existing
            raise FourGateM2Error("Data-readiness resolution is immutable")
        manifest = self._assert_fresh(run_id)
        review = self._required_artifact(run_id, FourGateM2ArtifactType.EVIDENCE_REVIEW)
        self._assert_evidence_fresh(run_id, review)
        if (
            review.permission
            is not FourGateM2EvidencePermission.CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE
            or review.conflict_status is not FourGateM2ConflictStatus.CONSISTENT
        ):
            raise FourGateM2Error("Only admissible reviewed evidence may resolve the criterion")
        resolution = FourGateM2DataReadinessResolution(
            resolution_id=self.id_factory("four-gate-data-readiness-resolution"),
            run_id=run_id,
            baseline=manifest.baseline,
            target=manifest.target,
            evidence_review_artifact=self._required_ref(
                run_id, FourGateM2ArtifactType.EVIDENCE_REVIEW
            ),
            proposed_value=proposed_value,
            proposed_knowledge_state=proposed_knowledge_state,
            mapping_rationale=mapping_rationale,
            data_owner=data_owner,
            criterion_reviewer=criterion_reviewer,
        )
        self._save(
            run_id,
            FourGateM2ArtifactType.DATA_READINESS_RESOLUTION,
            resolution,
            FourGateM2ArtifactType.EVIDENCE_REVIEW,
            FourGateM2RunStage.EVIDENCE_REVIEWED,
            FourGateM2RunStage.RESOLUTION_PROPOSED,
        )
        return resolution

    def request_reassessment(self, run_id: str) -> FourGateM2ReassessmentRequest:
        existing = self._existing(run_id, FourGateM2ArtifactType.REASSESSMENT_REQUEST)
        if existing is not None:
            return existing
        manifest = self._assert_fresh(run_id)
        resolution = self._required_artifact(
            run_id, FourGateM2ArtifactType.DATA_READINESS_RESOLUTION
        )
        review = self._required_artifact(run_id, FourGateM2ArtifactType.EVIDENCE_REVIEW)
        self._assert_evidence_fresh(run_id, review)
        if (
            resolution.proposed_knowledge_state is not KnowledgeState.KNOWN
            or resolution.proposed_value is None
        ):
            raise FourGateM2Error("A known reviewed value is required to request reassessment")
        body = {
            "baseline": manifest.baseline.model_dump(mode="json"),
            "target": manifest.target.model_dump(mode="json"),
            "review": resolution.evidence_review_artifact.model_dump(mode="json"),
            "resolution": self._required_ref(
                run_id, FourGateM2ArtifactType.DATA_READINESS_RESOLUTION
            ).model_dump(mode="json"),
        }
        request = FourGateM2ReassessmentRequest(
            request_id=self.id_factory("four-gate-reassessment-request"),
            run_id=run_id,
            requested_at=self.clock(),
            baseline=manifest.baseline,
            target=manifest.target,
            evidence_review_artifact=resolution.evidence_review_artifact,
            resolution_artifact=self._required_ref(
                run_id, FourGateM2ArtifactType.DATA_READINESS_RESOLUTION
            ),
            changed_field_path=(
                f"steps.{manifest.target.step_id}.characteristics.data_readiness"
            ),
            request_sha256=_hash(body),
        )
        self._save(
            run_id,
            FourGateM2ArtifactType.REASSESSMENT_REQUEST,
            request,
            FourGateM2ArtifactType.DATA_READINESS_RESOLUTION,
            FourGateM2RunStage.RESOLUTION_PROPOSED,
            FourGateM2RunStage.REQUESTED,
        )
        return request

    def approve_reassessment(
        self,
        run_id: str,
        *,
        approver: FourGateM2ActorDeclaration,
        rationale: str,
        exact_change: str = "Resolve only target data_readiness in a separate successor.",
        retained_uncertainty: str = (
            "Evidence limitations remain; no deployment, outcome, or ROI claim is made."
        ),
    ) -> FourGateM2ReassessmentApproval:
        existing = self._existing(run_id, FourGateM2ArtifactType.REASSESSMENT_APPROVAL)
        if existing is not None:
            if (
                existing.approver == approver
                and existing.rationale == rationale
                and existing.exact_change == exact_change
                and existing.retained_uncertainty == retained_uncertainty
            ):
                return existing
            raise FourGateM2Error("Reassessment approval is immutable")
        manifest = self._assert_fresh(run_id)
        request_ref = self._required_ref(
            run_id, FourGateM2ArtifactType.REASSESSMENT_REQUEST
        )
        approval = FourGateM2ReassessmentApproval(
            approval_id=self.id_factory("four-gate-reassessment-approval"),
            run_id=run_id,
            baseline=manifest.baseline,
            target=manifest.target,
            request_artifact=request_ref,
            approved_at=self.clock(),
            approver=approver,
            rationale=rationale,
            exact_change=exact_change,
            retained_uncertainty=retained_uncertainty,
        )
        self._save(
            run_id,
            FourGateM2ArtifactType.REASSESSMENT_APPROVAL,
            approval,
            FourGateM2ArtifactType.REASSESSMENT_REQUEST,
            FourGateM2RunStage.REQUESTED,
            FourGateM2RunStage.APPROVED,
        )
        return approval

    def build_successor_review(
        self, run_id: str
    ) -> FourGateM2SuccessorApprovedReview:
        existing = self._existing(
            run_id, FourGateM2ArtifactType.SUCCESSOR_APPROVED_REVIEW
        )
        if existing is not None:
            return existing
        manifest = self._assert_fresh(run_id)
        self._load_pinned_policy(manifest.baseline)
        baseline_approved = self._load_baseline_artifact(
            manifest.baseline.approved_review,
            "phase4-v0.1",
        ).payload
        approval = self._required_artifact(
            run_id, FourGateM2ArtifactType.REASSESSMENT_APPROVAL
        )
        resolution = self._required_artifact(
            run_id, FourGateM2ArtifactType.DATA_READINESS_RESOLUTION
        )
        evidence_review = self._required_artifact(
            run_id, FourGateM2ArtifactType.EVIDENCE_REVIEW
        )
        self._assert_evidence_fresh(run_id, evidence_review)
        submission = self._required_artifact(
            run_id, FourGateM2ArtifactType.DOCUMENT_SUBMISSION
        )
        successor = self.projector.build(
            run_id=run_id,
            baseline=manifest.baseline,
            baseline_approved=baseline_approved,
            request_artifact=self._required_ref(
                run_id, FourGateM2ArtifactType.REASSESSMENT_REQUEST
            ),
            approval_artifact=self._required_ref(
                run_id, FourGateM2ArtifactType.REASSESSMENT_APPROVAL
            ),
            approval=approval,
            evidence_review_artifact=self._required_ref(
                run_id, FourGateM2ArtifactType.EVIDENCE_REVIEW
            ),
            evidence_review=evidence_review,
            resolution_artifact=self._required_ref(
                run_id, FourGateM2ArtifactType.DATA_READINESS_RESOLUTION
            ),
            resolution=resolution,
            document=submission.document,
            locator=evidence_review.locator,
            target_step_id=manifest.target.step_id,
            successor_review_id=self.id_factory("four-gate-successor-review"),
            successor_process_id=self.id_factory("four-gate-successor-process"),
        )
        self._save(
            run_id,
            FourGateM2ArtifactType.SUCCESSOR_APPROVED_REVIEW,
            successor,
            FourGateM2ArtifactType.REASSESSMENT_APPROVAL,
            FourGateM2RunStage.APPROVED,
            FourGateM2RunStage.SUCCESSOR_REVIEW_READY,
        )
        return successor

    def assess_successor(self, run_id: str) -> FourGateM2SuccessorAssessment:
        existing = self._existing(
            run_id, FourGateM2ArtifactType.SUCCESSOR_INTEGRATED_ASSESSMENT
        )
        if existing is not None:
            return existing
        manifest = self._assert_fresh(run_id)
        policy = self._load_pinned_policy(manifest.baseline)
        successor = self._required_artifact(
            run_id, FourGateM2ArtifactType.SUCCESSOR_APPROVED_REVIEW
        )
        resolution = self._required_artifact(
            run_id, FourGateM2ArtifactType.DATA_READINESS_RESOLUTION
        )
        baseline_approved = self._load_baseline_artifact(
            manifest.baseline.approved_review, "phase4-v0.1"
        ).payload
        if successor.approval_artifact != self._required_ref(
            run_id, FourGateM2ArtifactType.REASSESSMENT_APPROVAL
        ):
            raise FourGateM2Error("Successor projection references the wrong approval")
        assert_one_field_projection(
            baseline_approved,
            successor.approved_review,
            target_step_id=successor.target_step_id,
            evidence_id=successor.evidence_id,
            resolution=resolution,
        )
        phase5 = self.phase5_service_factory(lambda: policy)
        result = phase5.assess(successor.approved_review)
        if (
            not isinstance(result, FourGateIntegratedAssessmentSuccess)
            or result.metadata.integration_schema_version != "phase5-v0.2"
            or result.metadata.phase1_contract_version != "phase1-v0.4"
            or result.process_assessment.framework_id != "four-gate-framework.v0.1"
            or result.process_assessment.process_id
            != successor.approved_review.business_process.process_id
            or result.lineage.validated_process_fingerprint
            != successor.successor_process_fingerprint
            or result.policy.policy_id != manifest.baseline.decision_policy_id
            or result.policy.policy_version
            != manifest.baseline.decision_policy_version
            or result.policy.policy_status != manifest.baseline.decision_policy_status
            or result.policy.decision_policy_fingerprint
            != manifest.baseline.decision_policy_fingerprint
        ):
            raise FourGateM2Error("Explicit successor Phase 5 reassessment failed closed")
        payload = FourGateM2SuccessorAssessment(
            run_id=run_id,
            baseline=manifest.baseline,
            successor_review_artifact=self._required_ref(
                run_id, FourGateM2ArtifactType.SUCCESSOR_APPROVED_REVIEW
            ),
            integrated_assessment=result,
        )
        self._save(
            run_id,
            FourGateM2ArtifactType.SUCCESSOR_INTEGRATED_ASSESSMENT,
            payload,
            FourGateM2ArtifactType.SUCCESSOR_APPROVED_REVIEW,
            FourGateM2RunStage.SUCCESSOR_REVIEW_READY,
            FourGateM2RunStage.ASSESSED,
        )
        return payload

    def generate_successor_package(
        self, run_id: str
    ) -> FourGateM2SuccessorDecisionPackage:
        existing = self._existing(
            run_id, FourGateM2ArtifactType.SUCCESSOR_DECISION_PACKAGE
        )
        if existing is not None:
            return existing
        manifest = self._assert_fresh(run_id)
        self._load_pinned_policy(manifest.baseline)
        assessment = self._required_artifact(
            run_id, FourGateM2ArtifactType.SUCCESSOR_INTEGRATED_ASSESSMENT
        )
        generated = self.phase6_service.generate(assessment.integrated_assessment)
        if (
            not isinstance(generated, FourGateDecisionPackageSuccess)
            or generated.package_schema_version != "phase6-v0.2"
            or generated.package.source.phase1_contract_version != "phase1-v0.4"
            or generated.package.current_state.framework_id
            != manifest.baseline.framework_id
            or generated.package.source.policy.policy_id
            != manifest.baseline.decision_policy_id
            or generated.package.source.policy.policy_version
            != manifest.baseline.decision_policy_version
            or generated.package.source.policy.decision_policy_fingerprint
            != manifest.baseline.decision_policy_fingerprint
        ):
            raise FourGateM2Error("Explicit successor Phase 6 packaging failed closed")
        payload = FourGateM2SuccessorDecisionPackage(
            run_id=run_id,
            baseline=manifest.baseline,
            successor_assessment_artifact=self._required_ref(
                run_id, FourGateM2ArtifactType.SUCCESSOR_INTEGRATED_ASSESSMENT
            ),
            decision_package=generated,
        )
        self._save(
            run_id,
            FourGateM2ArtifactType.SUCCESSOR_DECISION_PACKAGE,
            payload,
            FourGateM2ArtifactType.SUCCESSOR_INTEGRATED_ASSESSMENT,
            FourGateM2RunStage.ASSESSED,
            FourGateM2RunStage.PACKAGE_READY,
        )
        return payload

    def compare(self, run_id: str):
        existing = self._existing(
            run_id, FourGateM2ArtifactType.BASELINE_SUCCESSOR_COMPARISON
        )
        if existing is not None:
            return existing
        manifest = self._assert_fresh(run_id)
        self._load_pinned_policy(manifest.baseline)
        baseline_package = self._load_baseline_artifact(
            manifest.baseline.decision_package, "phase6-v0.2"
        ).payload
        successor = self._required_artifact(
            run_id, FourGateM2ArtifactType.SUCCESSOR_DECISION_PACKAGE
        )
        resolution = self._required_artifact(
            run_id, FourGateM2ArtifactType.DATA_READINESS_RESOLUTION
        )
        projection = self._required_artifact(
            run_id, FourGateM2ArtifactType.SUCCESSOR_APPROVED_REVIEW
        )
        comparison = self.comparator.compare(
            comparison_id=self.id_factory("four-gate-comparison"),
            run_id=run_id,
            created_at=self.clock(),
            baseline=manifest.baseline,
            baseline_package=baseline_package,
            successor_package_artifact=self._required_ref(
                run_id, FourGateM2ArtifactType.SUCCESSOR_DECISION_PACKAGE
            ),
            successor_package=successor.decision_package,
            target_step_id=manifest.target.step_id,
            successor_data_readiness=resolution.proposed_value,
            successor_evidence_ids=[projection.evidence_id],
        )
        self._save(
            run_id,
            FourGateM2ArtifactType.BASELINE_SUCCESSOR_COMPARISON,
            comparison,
            FourGateM2ArtifactType.SUCCESSOR_DECISION_PACKAGE,
            FourGateM2RunStage.PACKAGE_READY,
            FourGateM2RunStage.COMPARED,
        )
        return comparison

    def _assert_fresh(self, run_id: str) -> FourGateM2RunManifest:
        manifest = self._required_artifact(run_id, FourGateM2ArtifactType.RUN_MANIFEST)
        context = self.open_context(
            manifest.baseline.assessment_id, manifest.target.step_id
        )
        if context is None or context != (manifest.baseline, manifest.target):
            raise FourGateM2Error("Pinned baseline, contract, or target gap is stale")
        self._load_pinned_policy(manifest.baseline)
        return manifest

    def _load_pinned_policy(
        self, baseline: FourGateM2BaselineReference
    ) -> FourGateDecisionPolicy:
        try:
            raw = self.policy_loader()
            policy = FourGateDecisionPolicy.model_validate(
                raw.model_dump(mode="json") if hasattr(raw, "model_dump") else raw
            )
        except Exception as exc:
            raise FourGateM2Error("Explicit successor policy could not be validated") from exc
        if (
            policy.policy_id != baseline.decision_policy_id
            or policy.version != baseline.decision_policy_version
            or fingerprint_four_gate_policy(policy)
            != baseline.decision_policy_fingerprint
        ):
            raise FourGateM2Error("Pinned decision policy fingerprint changed")
        return policy

    def _assert_evidence_fresh(
        self, run_id: str, review: FourGateM2EvidenceReview
    ) -> None:
        submission = self._required_artifact(
            run_id, FourGateM2ArtifactType.DOCUMENT_SUBMISSION
        )
        if review.submission_artifact != self._required_ref(
            run_id, FourGateM2ArtifactType.DOCUMENT_SUBMISSION
        ):
            raise FourGateM2Error("Evidence review references the wrong document")
        self._validate_locator(submission.document, review.locator)

    def _validate_locator(
        self,
        document: FourGateM2SupportingDocument,
        locator: FourGateM2DocumentLocator,
    ) -> None:
        raw = self.repository.load_document_bytes(document.document_id)
        if hashlib.sha256(raw).hexdigest() != document.content_sha256:
            raise FourGateM2Error("Supporting document hash changed")
        text = raw.decode("utf-8")
        if text[locator.start_offset : locator.end_offset] != locator.exact_excerpt:
            raise FourGateM2Error("Evidence locator does not reproduce its excerpt")
        if (
            text.count("\n", 0, locator.start_offset) + 1,
            text.count("\n", 0, locator.end_offset) + 1,
        ) != (locator.line_start, locator.line_end):
            raise FourGateM2Error("Evidence locator line range is invalid")

    def _load_baseline_artifact(
        self, reference: FourGateM2ArtifactReference, schema_version: str
    ) -> StoredArtifact:
        artifact = self.baseline_repository.load_artifact(reference.artifact_id)
        if (
            _reference(artifact) != reference
            or artifact.artifact_schema_version != schema_version
        ):
            raise FourGateM2Error("Pinned baseline artifact changed")
        return artifact

    def _existing(self, run_id: str, artifact_type: FourGateM2ArtifactType):
        reference = self.repository.load_artifact_reference(run_id, artifact_type)
        return self.repository.load_artifact(reference.artifact_id) if reference else None

    def _required_ref(
        self, run_id: str, artifact_type: FourGateM2ArtifactType
    ) -> FourGateM2ArtifactReference:
        reference = self.repository.load_artifact_reference(run_id, artifact_type)
        if reference is None:
            raise FourGateM2Error(f"Run is missing {artifact_type.value}")
        return reference

    def _required_artifact(self, run_id: str, artifact_type: FourGateM2ArtifactType):
        return self.repository.load_artifact(
            self._required_ref(run_id, artifact_type).artifact_id
        )

    def _save(
        self,
        run_id: str,
        artifact_type: FourGateM2ArtifactType,
        payload,
        parent_type: FourGateM2ArtifactType,
        expected_stage: FourGateM2RunStage,
        stage: FourGateM2RunStage,
    ) -> None:
        try:
            self.repository.save_artifact_and_advance(
                run_id,
                artifact_type,
                payload,
                parent=self._required_ref(run_id, parent_type),
                expected_stage=expected_stage,
                stage=stage,
                idempotency_key=_hash(payload.model_dump(mode="json")),
            )
        except FourGateM2PersistenceError as exc:
            raise FourGateM2Error(str(exc)) from exc


def _reference(artifact: StoredArtifact) -> FourGateM2ArtifactReference:
    return FourGateM2ArtifactReference(
        artifact_id=artifact.artifact_id,
        artifact_revision=artifact.artifact_revision,
        payload_sha256=artifact.payload_sha256,
    )


def _hash(payload) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()

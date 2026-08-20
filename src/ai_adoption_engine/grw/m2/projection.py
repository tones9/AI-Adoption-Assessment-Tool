"""Construct one M2 successor projection without reopening the Phase 4 review."""

from __future__ import annotations

from copy import deepcopy

from ai_adoption_engine.application.fingerprints import fingerprint_business_process
from ai_adoption_engine.grw.m2.models import (
    M2ArtifactReference,
    M2DataReadinessResolution,
    M2DocumentLocator,
    M2ReassessmentApproval,
    M2SupportingDocument,
    M2SuccessorApprovedReview,
)
from ai_adoption_engine.models.enums import KnowledgeState, UncertaintyStatus
from ai_adoption_engine.models.evidence import CriterionInput, EvidenceReference
from ai_adoption_engine.models.review import ApprovedProcessReview


class SuccessorProjectionError(ValueError):
    pass


class SuccessorReviewProjector:
    """A narrowly scoped deep-copy + one-field patch projector."""

    def build(
        self,
        *,
        run_id: str,
        baseline_artifact: M2ArtifactReference,
        baseline_approved: ApprovedProcessReview,
        request_artifact: M2ArtifactReference,
        approval_artifact: M2ArtifactReference,
        approval: M2ReassessmentApproval,
        evidence_review_artifact: M2ArtifactReference,
        resolution_artifact: M2ArtifactReference,
        resolution: M2DataReadinessResolution,
        document: M2SupportingDocument,
        locator: M2DocumentLocator,
        target_step_id: str,
        successor_review_id: str,
        successor_approval_event_id: str,
    ) -> M2SuccessorApprovedReview:
        if resolution.proposed_knowledge_state is not KnowledgeState.KNOWN or resolution.proposed_value is None:
            raise SuccessorProjectionError("Only an approved known M2 data-readiness resolution can create a successor")
        process = deepcopy(baseline_approved.business_process)
        baseline_payload = baseline_approved.business_process.model_dump(mode="json")
        step = next((item for item in process.steps if item.step_id == target_step_id), None)
        if step is None:
            raise SuccessorProjectionError("Pinned target step no longer exists in the baseline projection")
        evidence_id = f"m2-doc-evidence-{document.content_sha256}"
        if any(item.evidence_id == evidence_id for item in process.evidence):
            raise SuccessorProjectionError("Supporting document evidence ID collides with baseline evidence")
        process.evidence.append(EvidenceReference(
            evidence_id=evidence_id,
            source_id=document.document_id,
            source_locator=f"lines {locator.line_start}-{locator.line_end}; chars {locator.start_offset}-{locator.end_offset}",
            supporting_snippet=locator.exact_excerpt,
            provenance="M2 reviewed supporting document; not original Phase 3 extraction evidence.",
            knowledge_state=KnowledgeState.KNOWN,
            uncertainty_status=UncertaintyStatus.UNCERTAIN,
        ))
        step.characteristics.data_readiness = CriterionInput(
            value=resolution.proposed_value,
            knowledge_state=KnowledgeState.KNOWN,
            rationale=resolution.mapping_rationale,
            evidence_ids=[evidence_id],
        )
        successor_payload = process.model_dump(mode="json")
        baseline_step = next(item for item in baseline_payload["steps"] if item["step_id"] == target_step_id)
        successor_step = next(item for item in successor_payload["steps"] if item["step_id"] == target_step_id)
        baseline_step["characteristics"].pop("data_readiness")
        successor_step["characteristics"].pop("data_readiness")
        if baseline_step != successor_step:
            raise SuccessorProjectionError("Successor projector attempted to change a field other than data_readiness")
        baseline_non_m2_evidence = baseline_payload["evidence"]
        if successor_payload["evidence"][:-1] != baseline_non_m2_evidence:
            raise SuccessorProjectionError("Successor projector attempted to replace baseline evidence")
        return M2SuccessorApprovedReview(
            successor_review_id=successor_review_id,
            successor_approval_event_id=successor_approval_event_id,
            run_id=run_id,
            baseline_approved_review=baseline_artifact,
            request_artifact=request_artifact,
            approval_artifact=approval_artifact,
            evidence_review_artifact=evidence_review_artifact,
            resolution_artifact=resolution_artifact,
            data_readiness_resolution=resolution,
            baseline_approved=baseline_approved,
            successor_process=process,
            target_step_id=target_step_id,
            changed_field_path=f"steps.{target_step_id}.characteristics.data_readiness",
            supporting_document=document,
            locator=locator,
            successor_process_fingerprint=fingerprint_business_process(process),
        )

"""One-field approved-review projection for successor GRW/M2."""

from __future__ import annotations

from copy import deepcopy

from ai_adoption_engine.application.fingerprints import fingerprint_business_process
from ai_adoption_engine.grw.four_gate_m2.models import (
    FourGateM2ArtifactReference,
    FourGateM2BaselineReference,
    FourGateM2DataReadinessResolution,
    FourGateM2DocumentLocator,
    FourGateM2EvidenceReview,
    FourGateM2ReassessmentApproval,
    FourGateM2SuccessorApprovedReview,
    FourGateM2SupportingDocument,
)
from ai_adoption_engine.models.candidate_process import ResolvedEvidenceReference
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.evidence import CriterionInput, EvidenceReference
from ai_adoption_engine.models.review import (
    ApprovedProcessReview,
    InformationOrigin,
    ReviewDisposition,
)


class FourGateM2ProjectionError(ValueError):
    pass


class FourGateM2SuccessorProjector:
    def build(
        self,
        *,
        run_id: str,
        baseline: FourGateM2BaselineReference,
        baseline_approved: ApprovedProcessReview,
        request_artifact: FourGateM2ArtifactReference,
        approval_artifact: FourGateM2ArtifactReference,
        approval: FourGateM2ReassessmentApproval,
        evidence_review_artifact: FourGateM2ArtifactReference,
        evidence_review: FourGateM2EvidenceReview,
        resolution_artifact: FourGateM2ArtifactReference,
        resolution: FourGateM2DataReadinessResolution,
        document: FourGateM2SupportingDocument,
        locator: FourGateM2DocumentLocator,
        target_step_id: str,
        successor_review_id: str,
        successor_process_id: str,
    ) -> FourGateM2SuccessorApprovedReview:
        if (
            resolution.proposed_knowledge_state is not KnowledgeState.KNOWN
            or resolution.proposed_value is None
            or not approval.baseline_remains_active
        ):
            raise FourGateM2ProjectionError(
                "Only an approved known data-readiness resolution may be projected"
            )

        projected = baseline_approved.model_copy(deep=True)
        process = projected.business_process
        review = projected.review
        process_step = next(
            (item for item in process.steps if item.step_id == target_step_id), None
        )
        review_step = next(
            (item for item in review.steps if item.candidate_step_id == target_step_id),
            None,
        )
        if process_step is None or review_step is None:
            raise FourGateM2ProjectionError("The pinned target step no longer exists")

        evidence_id = f"cev-{document.content_sha256}"
        if any(item.evidence_id == evidence_id for item in process.evidence):
            raise FourGateM2ProjectionError(
                "The reviewed document evidence collides with baseline evidence"
            )
        resolved = ResolvedEvidenceReference(
            evidence_id=evidence_id,
            document_id=document.document_id,
            block_id=f"four-gate-m2-{document.content_sha256[:12]}",
            block_start_offset=0,
            block_end_offset=len(locator.exact_excerpt),
            document_start_offset=locator.start_offset,
            document_end_offset=locator.end_offset,
            source_locator=(
                f"lines {locator.line_start}-{locator.line_end}; "
                f"chars {locator.start_offset}-{locator.end_offset}"
            ),
            exact_snippet=locator.exact_excerpt,
        )
        process.evidence.append(
            EvidenceReference(
                evidence_id=evidence_id,
                source_id=document.document_id,
                source_locator=resolved.source_locator,
                supporting_snippet=locator.exact_excerpt,
                provenance="Phase 2 document-supported source evidence",
                knowledge_state=KnowledgeState.KNOWN,
                uncertainty_status="certain",
            )
        )
        process_step.characteristics.data_readiness = CriterionInput(
            value=resolution.proposed_value,
            knowledge_state=KnowledgeState.KNOWN,
            rationale=resolution.mapping_rationale,
            evidence_ids=[evidence_id],
        )
        reviewed = next(
            item.assertion
            for item in review_step.criteria
            if item.name is CriterionName.DATA_READINESS
        )
        reviewed.value = resolution.proposed_value
        reviewed.knowledge_state = KnowledgeState.KNOWN
        reviewed.origin = InformationOrigin.DOCUMENT_SUPPORTED
        reviewed.rationale = resolution.mapping_rationale
        reviewed.evidence = [resolved]
        reviewed.confidence = None
        reviewed.disposition = ReviewDisposition.CORRECTED

        process.process_id = successor_process_id
        review.review_id = successor_review_id
        projected = ApprovedProcessReview.model_validate(
            projected.model_dump(mode="json")
        )
        assert_one_field_projection(
            baseline_approved,
            projected,
            target_step_id=target_step_id,
            evidence_id=evidence_id,
            resolution=resolution,
        )
        return FourGateM2SuccessorApprovedReview(
            run_id=run_id,
            baseline=baseline,
            baseline_approved_review=baseline.approved_review,
            request_artifact=request_artifact,
            approval_artifact=approval_artifact,
            evidence_review_artifact=evidence_review_artifact,
            resolution_artifact=resolution_artifact,
            target_step_id=target_step_id,
            changed_field_path=(
                f"steps.{target_step_id}.characteristics.data_readiness"
            ),
            evidence_id=evidence_id,
            successor_process_fingerprint=fingerprint_business_process(
                projected.business_process
            ),
            approved_review=projected,
        )


def assert_one_field_projection(
    baseline: ApprovedProcessReview,
    successor: ApprovedProcessReview,
    *,
    target_step_id: str,
    evidence_id: str,
    resolution: FourGateM2DataReadinessResolution,
) -> None:
    """Prove only data readiness, its evidence, and derived IDs changed."""

    old = baseline.model_dump(mode="json")
    new = successor.model_dump(mode="json")
    old_process = old["business_process"]
    new_process = new["business_process"]
    if len(new_process["evidence"]) != len(old_process["evidence"]) + 1:
        raise FourGateM2ProjectionError("Projection evidence cardinality changed")
    added = new_process["evidence"][-1]
    if added["evidence_id"] != evidence_id:
        raise FourGateM2ProjectionError("Projection added unexpected evidence")
    if new_process["evidence"][:-1] != old_process["evidence"]:
        raise FourGateM2ProjectionError("Projection replaced baseline evidence")
    new_process["evidence"].pop()
    new_process["process_id"] = old_process["process_id"]

    old_step = next(
        item for item in old_process["steps"] if item["step_id"] == target_step_id
    )
    new_step = next(
        item for item in new_process["steps"] if item["step_id"] == target_step_id
    )
    expected = {
        "value": resolution.proposed_value,
        "knowledge_state": KnowledgeState.KNOWN.value,
        "rationale": resolution.mapping_rationale,
        "evidence_ids": [evidence_id],
        "confidence": None,
    }
    if new_step["characteristics"]["data_readiness"] != expected:
        raise FourGateM2ProjectionError("Projection data_readiness is not approved")
    if new_step["evidence_ids"] != old_step["evidence_ids"]:
        raise FourGateM2ProjectionError("Projection changed step-level evidence")
    new_step["characteristics"]["data_readiness"] = deepcopy(
        old_step["characteristics"]["data_readiness"]
    )
    if new_process != old_process:
        raise FourGateM2ProjectionError("Projection changed a non-target process field")

    old_review = old["review"]
    new_review = new["review"]
    new_review["review_id"] = old_review["review_id"]
    old_assertion = next(
        item["assertion"]
        for step in old_review["steps"]
        if step["candidate_step_id"] == target_step_id
        for item in step["criteria"]
        if item["name"] == CriterionName.DATA_READINESS.value
    )
    new_assertion = next(
        item["assertion"]
        for step in new_review["steps"]
        if step["candidate_step_id"] == target_step_id
        for item in step["criteria"]
        if item["name"] == CriterionName.DATA_READINESS.value
    )
    new_assertion.clear()
    new_assertion.update(deepcopy(old_assertion))
    if new_review != old_review:
        raise FourGateM2ProjectionError("Projection changed a non-target review field")

    if new["approval"] != old["approval"]:
        raise FourGateM2ProjectionError("Projection changed baseline approval metadata")

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter

from ai_adoption_engine.application.fingerprints import fingerprint_business_process
from ai_adoption_engine.formal.input_adapter import (
    FormalFourGateInputAdapter,
    _canonical_json_bytes,
)
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.formal_assessment import (
    FORMAL_ASSESSMENT_AUTHORIZATION_SCHEMA,
    FORMAL_ASSESSMENT_INPUT_CHOICE_SCHEMA,
    FORMAL_ASSESSMENT_RUN_STORE_ID,
    ApprovedProcessAuthorizationPin,
    FormalAssessmentAuthorization,
    FormalAssessmentInputChoice,
    FormalAssessmentInputMode,
    FormalInputConflictResolution,
    FormalRunLineage,
    FormalValueOrigin,
    ProjectedValueOrigin,
    SupportingDocumentRevisionPin,
    SupportingEvidenceCandidatePin,
    SupportingEvidenceDisposition,
    SupportingHistoryExclusion,
)
from ai_adoption_engine.models.formal_assessment_adapter import (
    FORMAL_FOUR_GATE_INPUT_ADAPTER_RULES,
    FormalFourGateInputAdapterRules,
    FormalInputAdapterFailure,
    FormalInputAdapterFailureCode,
    FormalInputAdapterSuccess,
)
from ai_adoption_engine.models.formal_evidence import (
    FORMAL_EVIDENCE_FAMILY,
    FORMAL_EVIDENCE_READINESS_SCHEMA,
    FORMAL_INPUT_CANDIDATE_SET_SCHEMA,
    FORMAL_INPUT_MAPPING_SCHEMA,
    REVIEWER_DECLARATION_SCHEMA,
    SUPPORTING_EVIDENCE_PROPOSAL_SCHEMA,
    SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
    ActivityEvidenceFormalTarget,
    AttemptStatus,
    CandidateDocumentIdentity,
    CandidateExtractionIdentity,
    CapabilitySignalFormalTarget,
    CriterionFormalTarget,
    DocumentCategory,
    EvidenceClassification,
    ExcludedProposalReference,
    ExtractorIdentity,
    FormalEvidenceLineage,
    FormalEvidenceReadiness,
    FormalInputCandidateSet,
    FormalInputMapping,
    FormalTargetKind,
    HumanAccountabilityFormalTarget,
    MappingDisposition,
    ReadinessStatus,
    RequestIdentity,
    ReviewAction as SupportingReviewAction,
    ReviewedEvidenceReference,
    ReviewerDeclaration,
    SupportingEvidenceProposal,
    SupportingEvidenceReviewRevision,
    SupportingSourceSpan,
)
from ai_adoption_engine.models.four_gate_assessment import CapabilitySignalName
from ai_adoption_engine.models.review import (
    ApprovedProcessReview,
    InformationOrigin,
    ReviewDisposition,
)
from tests.fakes.review import FIXED_TIME, approved_review


NOW = datetime(2026, 10, 5, 14, 0, tzinfo=UTC)
HASH_A = "a" * 64


def canonical_hash(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def request(token: str) -> RequestIdentity:
    return RequestIdentity(
        request_token=token,
        canonical_request_sha256=canonical_hash({"token": token}),
    )


def reviewer() -> ReviewerDeclaration:
    return ReviewerDeclaration(
        schema_version=REVIEWER_DECLARATION_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        reviewer_display_name="Alex Reviewer",
        declared_organisational_role="Process owner",
        identity_and_authority_locally_declared_not_authenticated=True,
        declared_at=NOW,
    )


def formal_lineage(approved: ApprovedProcessReview) -> FormalEvidenceLineage:
    process = approved.business_process
    source_id = process.evidence[0].source_id
    return FormalEvidenceLineage(
        formal_lifecycle_schema="preliminary-formal-lifecycle.v0.1",
        formal_lifecycle_id="formal-1",
        journey_id="journey-1",
        source_assessment_id="assessment-1",
        approved_review_artifact_id="approved-review-1",
        approved_review_schema_version="phase4-v0.1",
        approved_review_revision=1,
        approved_review_payload_sha256=hashlib.sha256(
            TypeAdapter(ApprovedProcessReview).dump_json(
                approved,
                by_alias=True,
                exclude_none=False,
            )
        ).hexdigest(),
        source_document_id=source_id,
        source_document_sha256=source_id.removeprefix("doc-"),
        validated_process_id=process.process_id,
        validated_process_fingerprint=fingerprint_business_process(process),
    )


def run_lineage() -> FormalRunLineage:
    return FormalRunLineage(
        formal_lifecycle_id="formal-1",
        authorization_id="authorization-1",
        projection_id="projection-1",
        run_id="run-1",
    )


def compatibility():
    from tests.unit.test_formal_assessment_models import compatibility as make

    return make()


def make_authorization(
    approved: ApprovedProcessReview,
    *,
    candidate: FormalInputCandidateSet | None = None,
    readiness: FormalEvidenceReadiness | None = None,
    resolutions: tuple[FormalInputConflictResolution, ...] = (),
    excluded: bool = False,
) -> FormalAssessmentAuthorization:
    lineage = formal_lineage(approved)
    rl = run_lineage()
    if candidate is None:
        disposition = (
            SupportingEvidenceDisposition.CURRENT_SUPPORTING_EVIDENCE_EXPLICITLY_EXCLUDED
            if excluded
            else SupportingEvidenceDisposition.NO_SUPPORTING_HISTORY
        )
        exclusion = None
        if excluded:
            exclusion = SupportingHistoryExclusion(
                lineage=lineage,
                supporting_history_head_id="supporting-head-1",
                supporting_history_head_sha256=HASH_A,
                current_documents=(
                    SupportingDocumentRevisionPin(
                        document_id="supporting-doc-1",
                        document_content_sha256=HASH_A,
                        metadata_revision_id="metadata-1",
                    ),
                ),
                confirmation="EXCLUDE CURRENT SUPPORTING EVIDENCE FROM THIS RUN",
                declarant=reviewer(),
                rationale="This attempt deliberately excludes current supporting evidence.",
                excluded_at=NOW,
                request=request("exclude"),
            )
        choice = FormalAssessmentInputChoice(
            schema_version=FORMAL_ASSESSMENT_INPUT_CHOICE_SCHEMA,
            store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
            lineage=lineage,
            mode=FormalAssessmentInputMode.APPROVED_PROCESS_ONLY,
            supporting_evidence_disposition=disposition,
            exclusion=exclusion,
            explicit_user_confirmation=True,
            selected_at=NOW,
            request=request("choice"),
        )
    else:
        assert readiness is not None
        candidate_hash = canonical_hash(candidate)
        pin = SupportingEvidenceCandidatePin(
            lineage=lineage,
            supporting_history_head_id="supporting-head-1",
            supporting_history_head_sha256=HASH_A,
            candidate_set_id=candidate.candidate_set_id,
            candidate_set_payload_sha256=candidate_hash,
            readiness_id=readiness.readiness_id,
            readiness_payload_sha256=canonical_hash(readiness),
            readiness_candidate_set_id=candidate.candidate_set_id,
            readiness_candidate_set_payload_sha256=candidate_hash,
            readiness_status="READY_TO_ATTEMPT",
        )
        choice = FormalAssessmentInputChoice(
            schema_version=FORMAL_ASSESSMENT_INPUT_CHOICE_SCHEMA,
            store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
            lineage=lineage,
            mode=FormalAssessmentInputMode.APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE,
            supporting_evidence_disposition=SupportingEvidenceDisposition.CURRENT_SUPPORTING_EVIDENCE_INCLUDED,
            supporting_candidate=pin,
            explicit_user_confirmation=True,
            selected_at=NOW,
            request=request("choice"),
        )
    approval_event = next(
        item for item in approved.review.events if item.action.value == "approve"
    )
    return FormalAssessmentAuthorization(
        schema_version=FORMAL_ASSESSMENT_AUTHORIZATION_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        authorization_id=rl.authorization_id,
        run_lineage=rl,
        approved_process=ApprovedProcessAuthorizationPin(
            lineage=lineage,
            source_extraction_run_id=approved.review.original_candidate.extraction_run_id,
            approval_event_id=approval_event.event_id,
            approved_at=approved.approval.approved_at,
        ),
        input_choice=choice,
        conflict_resolutions=resolutions,
        compatibility=compatibility(),
        explicit_run_confirmation="ATTEMPT ORGANISATIONAL ASSESSMENT",
        authorization_scope="ASSESSMENT_RUN_ATTEMPT_ONLY_NOT_APPROVAL_OR_IMPLEMENTATION_AUTHORITY",
        request=request("authorize"),
        authorized_at=NOW,
    )


def extractor() -> ExtractorIdentity:
    return ExtractorIdentity(
        extractor_id="supporting-extractor",
        extractor_version="0.1.0",
        provider_id="provider",
        provider_version="2026-10",
        output_schema_id="supporting-proposal",
        output_schema_version="0.1.0",
        prompt_id="supporting-evidence",
        prompt_version="0.1.0",
    )


def make_span(
    lineage: FormalEvidenceLineage,
    index: int,
    excerpt: str,
) -> SupportingSourceSpan:
    return SupportingSourceSpan(
        lineage=lineage,
        document_id="supporting-doc-1",
        document_content_sha256=HASH_A,
        parsed_document_id="parsed-1",
        block_id=f"block-{index}",
        page_number=1,
        line_start=index,
        line_end_exclusive=index + 1,
        document_character_start=index * 100,
        document_character_end_exclusive=index * 100 + len(excerpt),
        block_character_start=0,
        block_character_end_exclusive=len(excerpt),
        exact_excerpt=excerpt,
        excerpt_sha256=hashlib.sha256(excerpt.encode()).hexdigest(),
        locator=f"page 1, line {index}",
    )


def make_fact_entry(
    approved: ApprovedProcessReview,
    *,
    index: int,
    target,
    value: int | bool | None,
    mapping_id: str | None = None,
    classification: EvidenceClassification = EvidenceClassification.DOCUMENTED_FACT,
    state: KnowledgeState = KnowledgeState.KNOWN,
    confidence: float | None = None,
):
    lineage = formal_lineage(approved)
    activity_id = approved.business_process.steps[0].step_id
    excerpt = f"Reviewed supporting statement {index}."
    span = make_span(lineage, index, excerpt)
    proposal = SupportingEvidenceProposal(
        schema_version=SUPPORTING_EVIDENCE_PROPOSAL_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=lineage,
        extraction_attempt_id="extraction-1",
        document_id="supporting-doc-1",
        document_content_sha256=HASH_A,
        proposed_claim=excerpt,
        proposed_classification=classification,
        primary_source_span=span,
        proposed_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
        suggested_activity_ids=(activity_id,),
        suggested_formal_targets=(target,),
        ambiguity_indicated=False,
        conflict_indicated=False,
        relevance_explanation="The statement is relevant after human review.",
        extraction_confidence=0.8,
        extractor=extractor(),
    )
    review = SupportingEvidenceReviewRevision(
        schema_version=SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=lineage,
        proposal_id=proposal.proposal_id,
        revision_id=f"review-{index}",
        revision_number=1,
        action=SupportingReviewAction.ACCEPT,
        original_proposal=proposal,
        approved_claim=proposal.proposed_claim,
        source_spans=(span,),
        selected_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
        approved_classification=classification,
        claim_directly_supported_by_excerpt=(
            True if classification is EvidenceClassification.DOCUMENTED_FACT else False
        ),
        inference_confidence=confidence,
        candidate_eligible=True,
        reviewer=reviewer(),
        rationale="Human reviewed this evidence.",
        reviewed_at=NOW,
        request=request(f"review-{index}"),
    )
    reference = ReviewedEvidenceReference(
        lineage=lineage,
        review_revision_id=review.revision_id,
        proposal_id=proposal.proposal_id,
        action=review.action,
        classification=review.approved_classification,
    )
    mapping = FormalInputMapping(
        schema_version=FORMAL_INPUT_MAPPING_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        mapping_id=mapping_id or f"mapping-{index}",
        lineage=lineage,
        activity_id=activity_id,
        target=target,
        disposition=MappingDisposition.MAPPED_FORMAL_INPUT,
        value=value,
        knowledge_state=state,
        approved_evidence_classification=classification,
        supporting_reviews=(reference,),
        mapping_rationale=f"Approved mapping rationale {index}.",
        reviewer=reviewer(),
        mapped_at=NOW,
        inference_confidence=confidence,
        request=request(f"mapping-{index}"),
    )
    return proposal, review, reference, mapping


def make_bundle(
    approved: ApprovedProcessReview,
    entries: tuple[tuple, ...],
) -> tuple[FormalInputCandidateSet, FormalEvidenceReadiness, tuple[SupportingEvidenceReviewRevision, ...]]:
    proposals = tuple(item[0] for item in entries)
    reviews = tuple(item[1] for item in entries)
    references = tuple(item[2] for item in entries)
    mappings = tuple(item[3] for item in entries if item[3] is not None)
    context_ids = tuple(
        reference.review_revision_id
        for mapping in mappings
        if mapping.disposition is MappingDisposition.CONTEXT_ONLY
        for reference in mapping.supporting_reviews
    )
    unknown_ids = tuple(
        item.revision_id
        for item in reviews
        if item.approved_classification is EvidenceClassification.UNKNOWN
    )
    conflict_ids = tuple(
        item.revision_id
        for item in reviews
        if item.approved_classification is EvidenceClassification.CONFLICT
    )
    candidate = FormalInputCandidateSet(
        schema_version=FORMAL_INPUT_CANDIDATE_SET_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        candidate_set_id="candidate-1",
        lineage=formal_lineage(approved),
        current_documents=(
            CandidateDocumentIdentity(
                document_id="supporting-doc-1",
                content_sha256=HASH_A,
                byte_size=500,
                metadata_revision_id="metadata-1",
            ),
        ),
        current_extractions=(
            CandidateExtractionIdentity(
                extraction_attempt_id="extraction-1",
                document_id="supporting-doc-1",
                status=AttemptStatus.SUCCEEDED,
                proposal_ids=tuple(item.proposal_id for item in proposals),
            ),
        ),
        current_reviews=references,
        ordered_formal_mappings=mappings,
        context_only_review_revision_ids=context_ids,
        retained_unknown_review_revision_ids=unknown_ids,
        retained_conflict_review_revision_ids=conflict_ids,
        rejected_or_excluded_proposals=tuple(
            ExcludedProposalReference(
                proposal_id=reference.proposal_id,
                reason="Human reviewer rejected this proposal.",
            )
            for reference in references
            if reference.action is SupportingReviewAction.REJECT
        ),
        created_at=NOW,
        conversion_request=request("convert"),
    )
    readiness = FormalEvidenceReadiness(
        schema_version=FORMAL_EVIDENCE_READINESS_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        readiness_id="readiness-1",
        lineage=formal_lineage(approved),
        candidate_set=candidate,
        current_review_revision_ids=tuple(item.revision_id for item in reviews),
        processing_complete_or_explicitly_excluded=True,
        every_current_proposal_terminally_reviewed=True,
        every_accepted_or_corrected_item_mapped_or_context_only=True,
        candidate_set_includes_every_current_review_revision=True,
        lineage_and_integrity_valid=True,
        retained_unknown_count=len(unknown_ids),
        retained_conflict_count=len(conflict_ids),
        status=ReadinessStatus.READY_TO_ATTEMPT,
        evaluated_at=NOW,
    )
    return candidate, readiness, reviews


def make_inference_entries(approved: ApprovedProcessReview, target):
    fact = make_fact_entry(
        approved,
        index=1,
        target=target,
        value=4,
    )
    fact_proposal, fact_review, fact_reference, _ = fact
    context_mapping = FormalInputMapping(
        schema_version=FORMAL_INPUT_MAPPING_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        mapping_id="mapping-fact-context",
        lineage=formal_lineage(approved),
        activity_id=approved.business_process.steps[0].step_id,
        target=None,
        disposition=MappingDisposition.CONTEXT_ONLY,
        value=None,
        knowledge_state=KnowledgeState.UNKNOWN,
        approved_evidence_classification=None,
        supporting_reviews=(fact_reference,),
        mapping_rationale="The fact is retained as inference support.",
        reviewer=reviewer(),
        mapped_at=NOW,
        request=request("mapping-fact-context"),
    )
    lineage = formal_lineage(approved)
    activity_id = approved.business_process.steps[0].step_id
    excerpt = "Reviewed inference statement."
    span = make_span(lineage, 2, excerpt)
    proposal = SupportingEvidenceProposal(
        schema_version=SUPPORTING_EVIDENCE_PROPOSAL_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=lineage,
        extraction_attempt_id="extraction-1",
        document_id="supporting-doc-1",
        document_content_sha256=HASH_A,
        proposed_claim=excerpt,
        proposed_classification=EvidenceClassification.REVIEWED_INFERENCE,
        primary_source_span=span,
        proposed_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
        suggested_activity_ids=(activity_id,),
        suggested_formal_targets=(target,),
        ambiguity_indicated=False,
        conflict_indicated=False,
        relevance_explanation="The inference is relevant after review.",
        extraction_confidence=0.7,
        extractor=extractor(),
    )
    inference = SupportingEvidenceReviewRevision(
        schema_version=SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=lineage,
        proposal_id=proposal.proposal_id,
        revision_id="review-2",
        revision_number=1,
        action=SupportingReviewAction.ACCEPT,
        original_proposal=proposal,
        approved_claim=proposal.proposed_claim,
        source_spans=(span,),
        selected_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
        approved_classification=EvidenceClassification.REVIEWED_INFERENCE,
        claim_directly_supported_by_excerpt=False,
        inference_confidence=0.7,
        inference_documented_facts=(fact_reference,),
        candidate_eligible=True,
        reviewer=reviewer(),
        rationale="The inference is grounded in the linked fact.",
        reviewed_at=NOW,
        request=request("review-2"),
    )
    inference_reference = ReviewedEvidenceReference(
        lineage=lineage,
        review_revision_id=inference.revision_id,
        proposal_id=proposal.proposal_id,
        action=inference.action,
        classification=inference.approved_classification,
    )
    mapping = FormalInputMapping(
        schema_version=FORMAL_INPUT_MAPPING_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        mapping_id="mapping-inference",
        lineage=lineage,
        activity_id=activity_id,
        target=target,
        disposition=MappingDisposition.MAPPED_FORMAL_INPUT,
        value=4,
        knowledge_state=KnowledgeState.INFERRED,
        approved_evidence_classification=EvidenceClassification.REVIEWED_INFERENCE,
        supporting_reviews=(inference_reference,),
        supporting_documented_fact_review_ids=(fact_review.revision_id,),
        mapping_rationale="The reviewed inference supports the score.",
        reviewer=reviewer(),
        mapped_at=NOW,
        inference_confidence=0.7,
        request=request("mapping-inference"),
    )
    return (
        (fact_proposal, fact_review, fact_reference, context_mapping),
        (proposal, inference, inference_reference, mapping),
    )


def make_unknown_entry(approved: ApprovedProcessReview, target, index: int):
    proposal, _, _, _ = make_fact_entry(
        approved, index=index, target=target, value=None
    )
    review = SupportingEvidenceReviewRevision(
        schema_version=SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=formal_lineage(approved),
        proposal_id=proposal.proposal_id,
        revision_id=f"review-{index}",
        revision_number=1,
        action=SupportingReviewAction.ACCEPT,
        original_proposal=proposal,
        approved_claim=proposal.proposed_claim,
        source_spans=(proposal.primary_source_span,),
        selected_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
        approved_classification=EvidenceClassification.UNKNOWN,
        candidate_eligible=False,
        reviewer=reviewer(),
        rationale="The reviewed evidence retains an unknown formal value.",
        reviewed_at=NOW,
        request=request(f"review-{index}"),
    )
    reference = ReviewedEvidenceReference(
        lineage=formal_lineage(approved),
        review_revision_id=review.revision_id,
        proposal_id=proposal.proposal_id,
        action=review.action,
        classification=review.approved_classification,
    )
    mapping = FormalInputMapping(
        schema_version=FORMAL_INPUT_MAPPING_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        mapping_id=f"mapping-{index}",
        lineage=formal_lineage(approved),
        activity_id=approved.business_process.steps[0].step_id,
        target=target,
        disposition=MappingDisposition.MAPPED_FORMAL_INPUT,
        value=None,
        knowledge_state=KnowledgeState.UNKNOWN,
        approved_evidence_classification=EvidenceClassification.UNKNOWN,
        supporting_reviews=(reference,),
        mapping_rationale="Unknown remains non-positive.",
        reviewer=reviewer(),
        mapped_at=NOW,
        request=request(f"mapping-{index}"),
    )
    return proposal, review, reference, mapping


def make_rejected_entry(approved: ApprovedProcessReview, target, index: int):
    proposal, _, _, _ = make_fact_entry(
        approved, index=index, target=target, value=3
    )
    review = SupportingEvidenceReviewRevision(
        schema_version=SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=formal_lineage(approved),
        proposal_id=proposal.proposal_id,
        revision_id=f"review-{index}",
        revision_number=1,
        action=SupportingReviewAction.REJECT,
        original_proposal=proposal,
        candidate_eligible=False,
        reviewer=reviewer(),
        rationale="Human reviewer rejected this proposal.",
        reviewed_at=NOW,
        request=request(f"review-{index}"),
    )
    reference = ReviewedEvidenceReference(
        lineage=formal_lineage(approved),
        review_revision_id=review.revision_id,
        proposal_id=proposal.proposal_id,
        action=review.action,
        classification=None,
    )
    return proposal, review, reference, None


def make_conflict_entry(
    approved: ApprovedProcessReview,
    target,
    index: int,
    competing: tuple[ReviewedEvidenceReference, ReviewedEvidenceReference],
):
    lineage = formal_lineage(approved)
    activity_id = approved.business_process.steps[0].step_id
    excerpt = f"Reviewed conflicting statement {index}."
    span = make_span(lineage, index, excerpt)
    proposal = SupportingEvidenceProposal(
        schema_version=SUPPORTING_EVIDENCE_PROPOSAL_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=lineage,
        extraction_attempt_id="extraction-1",
        document_id="supporting-doc-1",
        document_content_sha256=HASH_A,
        proposed_claim=excerpt,
        proposed_classification=EvidenceClassification.CONFLICT,
        primary_source_span=span,
        proposed_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
        suggested_activity_ids=(activity_id,),
        suggested_formal_targets=(target,),
        ambiguity_indicated=False,
        conflict_indicated=True,
        relevance_explanation="The conflicting statement is retained after review.",
        extraction_confidence=0.8,
        extractor=extractor(),
    )
    review = SupportingEvidenceReviewRevision(
        schema_version=SUPPORTING_EVIDENCE_REVIEW_REVISION_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=lineage,
        proposal_id=proposal.proposal_id,
        revision_id=f"review-{index}",
        revision_number=1,
        action=SupportingReviewAction.ACCEPT,
        original_proposal=proposal,
        approved_claim=proposal.proposed_claim,
        source_spans=(span,),
        selected_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
        approved_classification=EvidenceClassification.CONFLICT,
        competing_evidence=competing,
        candidate_eligible=False,
        reviewer=reviewer(),
        rationale="The conflict cannot provide a scalar value.",
        reviewed_at=NOW,
        request=request(f"review-{index}"),
    )
    reference = ReviewedEvidenceReference(
        lineage=lineage,
        review_revision_id=review.revision_id,
        proposal_id=proposal.proposal_id,
        action=review.action,
        classification=review.approved_classification,
    )
    mapping = FormalInputMapping(
        schema_version=FORMAL_INPUT_MAPPING_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        mapping_id=f"mapping-{index}",
        lineage=lineage,
        activity_id=activity_id,
        target=target,
        disposition=MappingDisposition.MAPPED_FORMAL_INPUT,
        value=None,
        knowledge_state=KnowledgeState.UNKNOWN,
        approved_evidence_classification=EvidenceClassification.CONFLICT,
        supporting_reviews=(reference,),
        mapping_rationale="Conflict remains non-positive.",
        reviewer=reviewer(),
        mapped_at=NOW,
        request=request(f"mapping-{index}"),
    )
    return proposal, review, reference, mapping


def project_supporting(approved, candidate, readiness, reviews, resolutions=()):
    return FormalFourGateInputAdapter().project(
        authorization=make_authorization(
            approved,
            candidate=candidate,
            readiness=readiness,
            resolutions=resolutions,
        ),
        approved_review=approved,
        candidate_set=candidate,
        readiness=readiness,
        supporting_reviews=reviews,
    )


def approved_with_known(
    criterion: CriterionName,
    value: int,
) -> ApprovedProcessReview:
    approved = approved_review().model_copy(deep=True)
    step = approved.business_process.steps[0]
    evidence_id = step.evidence_ids[0]
    current = step.characteristics.criterion(criterion)
    setattr(
        step.characteristics,
        criterion.value,
        current.model_copy(
            update={
                "value": value,
                "knowledge_state": KnowledgeState.KNOWN,
                "rationale": "Approved source value.",
                "evidence_ids": [evidence_id],
                "confidence": None,
            }
        ),
    )
    reviewed_step = approved.review.steps[0]
    assertion = next(
        item.assertion for item in reviewed_step.criteria if item.name is criterion
    )
    assertion.value = value
    assertion.knowledge_state = KnowledgeState.KNOWN
    assertion.origin = InformationOrigin.DOCUMENT_SUPPORTED
    assertion.rationale = "Approved source value."
    assertion.evidence = [reviewed_step.activity.evidence[0]]
    assertion.confidence = None
    assertion.disposition = ReviewDisposition.CORRECTED
    return ApprovedProcessReview.model_validate(approved.model_dump(mode="json"))


def make_resolution(adapter, approved, candidate, readiness, reviews, *, selected_value):
    authorization = make_authorization(approved, candidate=candidate, readiness=readiness)
    mapping_list = list(candidate.ordered_formal_mappings)
    evidence_by_mapping = {
        item.mapping_id: adapter._evidence_for_mapping(
            item, {review.revision_id: review for review in reviews}
        )
        for item in mapping_list
        if adapter._is_positive_mapping(item)
    }
    groups = adapter._groups(mapping_list, evidence_by_mapping)
    target = mapping_list[0].target
    step = approved.business_process.steps[0]
    approved_input = step.characteristics.criterion(target.criterion)
    alternatives = adapter._conflict_alternatives(
        authorization,
        step,
        target,
        approved_input,
        groups,
        {item.evidence_id: item for item in approved.business_process.evidence},
    )
    selected = next(item for item in alternatives if item.value == selected_value)
    return FormalInputConflictResolution(
        schema_version="formal-input-conflict-resolution.v0.1",
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        resolution_id="resolution-1",
        lineage=formal_lineage(approved),
        run_lineage=run_lineage(),
        activity_id=step.step_id,
        target=target,
        alternatives=alternatives,
        selected_value=selected.value,
        selected_knowledge_state=selected.knowledge_state,
        selected_confidence=selected.confidence,
        reviewer=reviewer(),
        explicit_human_selection=True,
        rationale="Human selected the effective value for this exact run.",
        resolved_at=NOW,
        request=request("resolve"),
    )


def test_process_only_projects_without_migration_seven_objects() -> None:
    approved = approved_review()
    result = FormalFourGateInputAdapter().project(
        authorization=make_authorization(approved),
        approved_review=approved,
    )
    assert isinstance(result, FormalInputAdapterSuccess)
    assert result.projection.approved_process == approved.business_process
    assert result.projection.engine_input == approved.business_process
    assert all(
        trace.origin is ProjectedValueOrigin.SOURCE_ONLY
        for activity in result.projection.activities
        for trace in activity.field_resolutions
    )
    assert all(len(activity.field_resolutions) == 21 for activity in result.projection.activities)


def test_process_only_explicit_exclusion_is_preserved() -> None:
    approved = approved_review()
    result = FormalFourGateInputAdapter().project(
        authorization=make_authorization(approved, excluded=True),
        approved_review=approved,
    )
    assert isinstance(result, FormalInputAdapterSuccess)
    assert result.projection.authorization.input_choice.exclusion is not None


def test_process_only_rejects_mixed_supporting_inputs_without_partial_projection() -> None:
    approved = approved_review()
    target = CriterionFormalTarget(
        kind=FormalTargetKind.CRITERION,
        criterion=CriterionName.BUSINESS_VALUE,
    )
    bundle = make_bundle(approved, (make_fact_entry(approved, index=1, target=target, value=4),))
    result = FormalFourGateInputAdapter().project(
        authorization=make_authorization(approved),
        approved_review=approved,
        candidate_set=bundle[0],
        readiness=bundle[1],
        supporting_reviews=bundle[2],
    )
    assert isinstance(result, FormalInputAdapterFailure)
    assert result.errors[0].code is FormalInputAdapterFailureCode.MODE_INPUT_MISMATCH
    assert result.projection is None


def test_invalid_approval_lineage_is_typed_failure() -> None:
    approved = approved_review()
    authorization = make_authorization(approved)
    changed_lineage = authorization.approved_process.lineage.model_copy(
        update={"validated_process_fingerprint": "f" * 64}
    )
    authorization = authorization.model_copy(
        update={
            "approved_process": authorization.approved_process.model_copy(
                update={"lineage": changed_lineage}
            )
        }
    )
    result = FormalFourGateInputAdapter().project(
        authorization=authorization,
        approved_review=approved,
    )
    assert isinstance(result, FormalInputAdapterFailure)
    assert result.errors[0].code in {
        FormalInputAdapterFailureCode.INVALID_AUTHORIZATION,
        FormalInputAdapterFailureCode.INVALID_APPROVED_LINEAGE,
    }
    assert result.projection is None


def test_fill_unknown_from_documented_fact_preserves_structure_and_order() -> None:
    approved = approved_review()
    target = CriterionFormalTarget(
        kind=FormalTargetKind.CRITERION,
        criterion=CriterionName.BUSINESS_VALUE,
    )
    candidate, readiness, reviews = make_bundle(
        approved,
        (make_fact_entry(approved, index=1, target=target, value=4),),
    )
    result = project_supporting(approved, candidate, readiness, reviews)
    assert isinstance(result, FormalInputAdapterSuccess)
    projected = result.projection.engine_input
    value = projected.steps[0].characteristics.business_value
    assert value.value == 4
    assert value.knowledge_state is KnowledgeState.KNOWN
    trace = next(
        item
        for item in result.projection.activities[0].field_resolutions
        if item.target == target
    )
    assert trace.origin is ProjectedValueOrigin.FILLED_UNKNOWN
    assert projected.steps[0].activity == approved.business_process.steps[0].activity
    assert [item.step_id for item in projected.steps] == [
        item.step_id for item in approved.business_process.steps
    ]
    assert projected.steps[1].dependencies == approved.business_process.steps[1].dependencies


def test_criterion_accountability_and_capability_use_canonical_order() -> None:
    approved = approved_review()
    entries = (
        make_fact_entry(
            approved,
            index=1,
            target=CriterionFormalTarget(
                kind=FormalTargetKind.CRITERION,
                criterion=CriterionName.DATA_READINESS,
            ),
            value=3,
        ),
        make_fact_entry(
            approved,
            index=2,
            target=HumanAccountabilityFormalTarget(
                kind=FormalTargetKind.HUMAN_ACCOUNTABILITY_REQUIRED
            ),
            value=True,
        ),
        make_fact_entry(
            approved,
            index=3,
            target=CapabilitySignalFormalTarget(
                kind=FormalTargetKind.CAPABILITY_SIGNAL,
                capability_signal=CapabilitySignalName.CATEGORISES_ITEMS,
            ),
            value=True,
        ),
    )
    candidate, readiness, reviews = make_bundle(approved, entries)
    result = project_supporting(approved, candidate, readiness, reviews)
    assert isinstance(result, FormalInputAdapterSuccess)
    step = result.projection.engine_input.steps[0]
    assert step.characteristics.data_readiness.value == 3
    assert step.characteristics.human_accountability_required.value is True
    assert step.characteristics.capability_signals.categorises_items.value is True
    traces = result.projection.activities[0].field_resolutions
    assert [item.target.criterion for item in traces[:10]] == list(CriterionName)
    assert traces[10].target.kind is FormalTargetKind.HUMAN_ACCOUNTABILITY_REQUIRED
    assert [item.target.capability_signal for item in traces[11:]] == list(CapabilitySignalName)


def test_identical_value_combines_source_and_supporting_provenance() -> None:
    approved = approved_with_known(CriterionName.BUSINESS_VALUE, 4)
    target = CriterionFormalTarget(
        kind=FormalTargetKind.CRITERION,
        criterion=CriterionName.BUSINESS_VALUE,
    )
    candidate, readiness, reviews = make_bundle(
        approved,
        (make_fact_entry(approved, index=1, target=target, value=4),),
    )
    result = project_supporting(approved, candidate, readiness, reviews)
    assert isinstance(result, FormalInputAdapterSuccess)
    trace = next(
        item for item in result.projection.activities[0].field_resolutions if item.target == target
    )
    assert trace.origin is ProjectedValueOrigin.CORROBORATED
    assert len(trace.evidence_ids) == 2
    assert len(trace.supporting_mappings) == 1


def test_reviewed_inference_preserves_confidence_and_exact_fact_links() -> None:
    approved = approved_review()
    target = CriterionFormalTarget(
        kind=FormalTargetKind.CRITERION,
        criterion=CriterionName.BUSINESS_VALUE,
    )
    candidate, readiness, reviews = make_bundle(
        approved,
        make_inference_entries(approved, target),
    )
    result = project_supporting(approved, candidate, readiness, reviews)
    assert isinstance(result, FormalInputAdapterSuccess)
    projected = result.projection.engine_input.steps[0].characteristics.business_value
    assert projected.value == 4
    assert projected.knowledge_state is KnowledgeState.INFERRED
    assert projected.confidence == 0.7
    assert len(projected.evidence_ids) == 2


def test_context_only_and_unknown_mappings_never_become_scalar_inputs() -> None:
    approved = approved_review()
    target = CriterionFormalTarget(
        kind=FormalTargetKind.CRITERION,
        criterion=CriterionName.RISK_CONSEQUENCE,
    )
    positive_target = CriterionFormalTarget(
        kind=FormalTargetKind.CRITERION,
        criterion=CriterionName.BUSINESS_VALUE,
    )
    context = make_fact_entry(
        approved, index=1, target=target, value=5
    )
    context_mapping = context[3].model_copy(
        update={
            "target": None,
            "disposition": MappingDisposition.CONTEXT_ONLY,
            "value": None,
            "knowledge_state": KnowledgeState.UNKNOWN,
            "approved_evidence_classification": None,
            "inference_confidence": None,
        }
    )
    entries = (
        (context[0], context[1], context[2], context_mapping),
        make_unknown_entry(approved, target, 2),
        make_fact_entry(
            approved, index=3, target=positive_target, value=4
        ),
    )
    candidate, readiness, reviews = make_bundle(approved, entries)
    result = project_supporting(approved, candidate, readiness, reviews)
    assert isinstance(result, FormalInputAdapterSuccess)
    projected = result.projection.engine_input.steps[0].characteristics.risk_consequence
    assert projected.value is None
    assert projected.knowledge_state is KnowledgeState.UNKNOWN
    trace = next(
        item
        for item in result.projection.activities[0].field_resolutions
        if item.target == target
    )
    assert trace.origin is ProjectedValueOrigin.SOURCE_ONLY


def test_rejected_and_conflict_evidence_never_become_scalar_inputs() -> None:
    approved = approved_review()
    target = CriterionFormalTarget(
        kind=FormalTargetKind.CRITERION,
        criterion=CriterionName.RISK_CONSEQUENCE,
    )
    positive_target = CriterionFormalTarget(
        kind=FormalTargetKind.CRITERION,
        criterion=CriterionName.BUSINESS_VALUE,
    )
    first = make_fact_entry(approved, index=1, target=target, value=2)
    second = make_fact_entry(approved, index=2, target=target, value=4)
    context_entries = tuple(
        (
            item[0],
            item[1],
            item[2],
            item[3].model_copy(
                update={
                    "target": None,
                    "disposition": MappingDisposition.CONTEXT_ONLY,
                    "value": None,
                    "knowledge_state": KnowledgeState.UNKNOWN,
                    "approved_evidence_classification": None,
                }
            ),
        )
        for item in (first, second)
    )
    conflict = make_conflict_entry(
        approved,
        target,
        3,
        (first[2], second[2]),
    )
    entries = (
        *context_entries,
        conflict,
        make_rejected_entry(approved, target, 4),
        make_fact_entry(approved, index=5, target=positive_target, value=4),
    )
    candidate, readiness, reviews = make_bundle(approved, entries)
    result = project_supporting(approved, candidate, readiness, reviews)
    assert isinstance(result, FormalInputAdapterSuccess)
    projected = result.projection.engine_input.steps[0].characteristics.risk_consequence
    assert projected.value is None
    assert projected.knowledge_state is KnowledgeState.UNKNOWN
    supporting_provenance = "\n".join(
        item.provenance or "" for item in result.projection.complete_evidence
    )
    assert conflict[1].revision_id not in supporting_provenance
    assert entries[3][1].revision_id not in supporting_provenance


def test_known_source_vs_supporting_conflict_requires_exact_resolution() -> None:
    approved = approved_with_known(CriterionName.BUSINESS_VALUE, 3)
    target = CriterionFormalTarget(
        kind=FormalTargetKind.CRITERION,
        criterion=CriterionName.BUSINESS_VALUE,
    )
    candidate, readiness, reviews = make_bundle(
        approved,
        (make_fact_entry(approved, index=1, target=target, value=5),),
    )
    unresolved = project_supporting(approved, candidate, readiness, reviews)
    assert isinstance(unresolved, FormalInputAdapterFailure)
    assert unresolved.errors[0].code is FormalInputAdapterFailureCode.UNRESOLVED_CONFLICT
    adapter = FormalFourGateInputAdapter()
    resolution = make_resolution(
        adapter, approved, candidate, readiness, reviews, selected_value=5
    )
    resolved = project_supporting(
        approved, candidate, readiness, reviews, (resolution,)
    )
    assert isinstance(resolved, FormalInputAdapterSuccess)
    assert resolved.projection.engine_input.steps[0].characteristics.business_value.value == 5


def test_supporting_vs_supporting_conflict_over_unknown_never_invents_source_value() -> None:
    approved = approved_review()
    target = CriterionFormalTarget(
        kind=FormalTargetKind.CRITERION,
        criterion=CriterionName.BUSINESS_VALUE,
    )
    entries = (
        make_fact_entry(approved, index=1, target=target, value=3),
        make_fact_entry(approved, index=2, target=target, value=5),
    )
    candidate, readiness, reviews = make_bundle(approved, entries)
    adapter = FormalFourGateInputAdapter()
    resolution = make_resolution(
        adapter, approved, candidate, readiness, reviews, selected_value=3
    )
    assert all(
        item.origin is FormalValueOrigin.SUPPORTING_MAPPING
        for item in resolution.alternatives
    )
    result = project_supporting(
        approved, candidate, readiness, reviews, (resolution,)
    )
    assert isinstance(result, FormalInputAdapterSuccess)
    assert result.projection.engine_input.steps[0].characteristics.business_value.value == 3


def test_conflict_combines_identical_source_and_supporting_provenance() -> None:
    approved = approved_with_known(CriterionName.BUSINESS_VALUE, 3)
    target = CriterionFormalTarget(
        kind=FormalTargetKind.CRITERION,
        criterion=CriterionName.BUSINESS_VALUE,
    )
    entries = (
        make_fact_entry(approved, index=1, target=target, value=3),
        make_fact_entry(approved, index=2, target=target, value=5),
    )
    candidate, readiness, reviews = make_bundle(approved, entries)
    resolution = make_resolution(
        FormalFourGateInputAdapter(),
        approved,
        candidate,
        readiness,
        reviews,
        selected_value=3,
    )
    assert resolution.alternatives[0].origin is FormalValueOrigin.CORROBORATED
    assert resolution.alternatives[0].supporting_mappings
    result = project_supporting(
        approved, candidate, readiness, reviews, (resolution,)
    )
    assert isinstance(result, FormalInputAdapterSuccess)
    projected = result.projection.engine_input.steps[0].characteristics.business_value
    assert len(projected.evidence_ids) == 2


def test_invalid_and_extra_conflict_resolutions_fail_closed() -> None:
    approved = approved_review()
    target = CriterionFormalTarget(
        kind=FormalTargetKind.CRITERION,
        criterion=CriterionName.BUSINESS_VALUE,
    )
    entries = (
        make_fact_entry(approved, index=1, target=target, value=3),
        make_fact_entry(approved, index=2, target=target, value=5),
    )
    candidate, readiness, reviews = make_bundle(approved, entries)
    resolution = make_resolution(
        FormalFourGateInputAdapter(),
        approved,
        candidate,
        readiness,
        reviews,
        selected_value=3,
    )
    bad = resolution.model_copy(
        update={"alternatives": tuple(reversed(resolution.alternatives))}
    )
    result = project_supporting(approved, candidate, readiness, reviews, (bad,))
    assert isinstance(result, FormalInputAdapterFailure)
    assert result.errors[0].code is FormalInputAdapterFailureCode.INVALID_CONFLICT_RESOLUTION

    single_candidate, single_readiness, single_reviews = make_bundle(
        approved, (entries[0],)
    )
    extra = project_supporting(
        approved,
        single_candidate,
        single_readiness,
        single_reviews,
        (resolution,),
    )
    assert isinstance(extra, FormalInputAdapterFailure)
    assert extra.errors[0].code is FormalInputAdapterFailureCode.INVALID_CONFLICT_RESOLUTION


def test_invalid_selected_value_and_cross_lineage_resolution_fail_closed() -> None:
    approved = approved_review()
    target = CriterionFormalTarget(
        kind=FormalTargetKind.CRITERION,
        criterion=CriterionName.BUSINESS_VALUE,
    )
    entries = (
        make_fact_entry(approved, index=1, target=target, value=3),
        make_fact_entry(approved, index=2, target=target, value=5),
    )
    candidate, readiness, reviews = make_bundle(approved, entries)
    resolution = make_resolution(
        FormalFourGateInputAdapter(),
        approved,
        candidate,
        readiness,
        reviews,
        selected_value=3,
    )
    authorization = make_authorization(
        approved, candidate=candidate, readiness=readiness
    )

    invalid_selection = resolution.model_copy(update={"selected_value": 4})
    invalid_authorization = authorization.model_copy(
        update={"conflict_resolutions": (invalid_selection,)}
    )
    invalid = FormalFourGateInputAdapter().project(
        authorization=invalid_authorization,
        approved_review=approved,
        candidate_set=candidate,
        readiness=readiness,
        supporting_reviews=reviews,
    )
    assert isinstance(invalid, FormalInputAdapterFailure)
    assert invalid.errors[0].code is FormalInputAdapterFailureCode.INVALID_CONFLICT_RESOLUTION
    assert invalid.projection is None

    cross_lineage = resolution.model_copy(
        update={
            "lineage": resolution.lineage.model_copy(
                update={"formal_lifecycle_id": "formal-other"}
            )
        }
    )
    cross_lineage_authorization = authorization.model_copy(
        update={"conflict_resolutions": (cross_lineage,)}
    )
    cross = FormalFourGateInputAdapter().project(
        authorization=cross_lineage_authorization,
        approved_review=approved,
        candidate_set=candidate,
        readiness=readiness,
        supporting_reviews=reviews,
    )
    assert isinstance(cross, FormalInputAdapterFailure)
    assert cross.errors[0].code is FormalInputAdapterFailureCode.INVALID_CONFLICT_RESOLUTION
    assert cross.projection is None


def test_candidate_readiness_hash_drift_and_missing_reviews_fail_closed() -> None:
    approved = approved_review()
    target = CriterionFormalTarget(
        kind=FormalTargetKind.CRITERION,
        criterion=CriterionName.BUSINESS_VALUE,
    )
    candidate, readiness, reviews = make_bundle(
        approved,
        (make_fact_entry(approved, index=1, target=target, value=4),),
    )
    authorization = make_authorization(
        approved, candidate=candidate, readiness=readiness
    )
    changed = candidate.model_copy(update={"candidate_set_id": "candidate-changed"})
    drift = FormalFourGateInputAdapter().project(
        authorization=authorization,
        approved_review=approved,
        candidate_set=changed,
        readiness=readiness,
        supporting_reviews=reviews,
    )
    assert isinstance(drift, FormalInputAdapterFailure)
    assert drift.errors[0].code is FormalInputAdapterFailureCode.INVALID_CANDIDATE_OR_READINESS_PIN
    missing = FormalFourGateInputAdapter().project(
        authorization=authorization,
        approved_review=approved,
        candidate_set=candidate,
        readiness=readiness,
        supporting_reviews=(),
    )
    assert isinstance(missing, FormalInputAdapterFailure)
    assert missing.errors[0].code is FormalInputAdapterFailureCode.INVALID_SUPPORTING_PROVENANCE


def test_activity_evidence_adds_provenance_without_scalar() -> None:
    approved = approved_review()
    target = ActivityEvidenceFormalTarget(kind=FormalTargetKind.ACTIVITY_EVIDENCE)
    positive_target = CriterionFormalTarget(
        kind=FormalTargetKind.CRITERION,
        criterion=CriterionName.BUSINESS_VALUE,
    )
    candidate, readiness, reviews = make_bundle(
        approved,
        (
            make_fact_entry(approved, index=1, target=target, value=None),
            make_fact_entry(
                approved, index=2, target=positive_target, value=4
            ),
        ),
    )
    result = project_supporting(approved, candidate, readiness, reviews)
    assert isinstance(result, FormalInputAdapterSuccess)
    projected = result.projection.activities[0]
    assert len(projected.activity_evidence) == 2
    assert all(len(item.field_resolutions) == 21 for item in result.projection.activities)
    activity_mapping = candidate.ordered_formal_mappings[0]
    assert activity_mapping.target.kind is FormalTargetKind.ACTIVITY_EVIDENCE
    assert activity_mapping.value is None


def test_projection_and_evidence_are_deterministic() -> None:
    approved = approved_review()
    target = CriterionFormalTarget(
        kind=FormalTargetKind.CRITERION,
        criterion=CriterionName.BUSINESS_VALUE,
    )
    candidate, readiness, reviews = make_bundle(
        approved,
        (make_fact_entry(approved, index=1, target=target, value=4),),
    )
    immutable_inputs = tuple(
        _canonical_json_bytes(item)
        for item in (approved, candidate, readiness, *reviews)
    )
    first = project_supporting(approved, candidate, readiness, reviews)
    second = project_supporting(approved, candidate, readiness, reviews)
    assert isinstance(first, FormalInputAdapterSuccess)
    assert isinstance(second, FormalInputAdapterSuccess)
    assert first.projection.canonical_json_bytes() == second.projection.canonical_json_bytes()
    assert first.projection.projection_fingerprint == second.projection.projection_fingerprint
    supporting_ids = [
        item.evidence_id
        for item in first.projection.complete_evidence
        if item.evidence_id.startswith("fev-")
    ]
    assert supporting_ids == [
        item.evidence_id
        for item in second.projection.complete_evidence
        if item.evidence_id.startswith("fev-")
    ]
    assert immutable_inputs == tuple(
        _canonical_json_bytes(item)
        for item in (approved, candidate, readiness, *reviews)
    )


def test_rules_and_compatibility_drift_return_typed_failure() -> None:
    approved = approved_review()
    drifted_rules = FORMAL_FOUR_GATE_INPUT_ADAPTER_RULES.model_copy(
        update={"criterion_order": tuple(reversed(tuple(CriterionName)))}
    )
    rules_result = FormalFourGateInputAdapter(drifted_rules).project(
        authorization=make_authorization(approved), approved_review=approved
    )
    assert isinstance(rules_result, FormalInputAdapterFailure)
    assert rules_result.errors[0].code is FormalInputAdapterFailureCode.INCOMPATIBLE_IDENTITY_OR_RULES
    authorization = make_authorization(approved)
    authorization = authorization.model_copy(
        update={
            "compatibility": authorization.compatibility.model_copy(
                update={"policy_fingerprint": "f" * 64}
            )
        }
    )
    identity_result = FormalFourGateInputAdapter().project(
        authorization=authorization, approved_review=approved
    )
    assert isinstance(identity_result, FormalInputAdapterFailure)
    assert identity_result.errors[0].code is FormalInputAdapterFailureCode.INCOMPATIBLE_IDENTITY_OR_RULES


def test_new_adapter_models_are_frozen_extra_forbidden() -> None:
    assert FormalFourGateInputAdapterRules.model_config["frozen"] is True
    assert FormalFourGateInputAdapterRules.model_config["extra"] == "forbid"
    with pytest.raises(Exception):
        FormalFourGateInputAdapterRules(unexpected=True)

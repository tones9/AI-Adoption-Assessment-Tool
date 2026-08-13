"""Synthetic integrated assessment fixtures for deterministic Phase 6 tests."""

import json
from pathlib import Path

from ai_adoption_engine.application.assessment import (
    INTEGRATION_SCHEMA_VERSION,
    PHASE1_CONTRACT_VERSION,
)
from ai_adoption_engine.application.fingerprints import (
    fingerprint_business_process,
    fingerprint_decision_policy,
)
from ai_adoption_engine.decision.engine import AssessmentEngine
from ai_adoption_engine.decision.policy import load_policy
from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.models.integrated_assessment import (
    AssessmentLineage,
    AssessmentRunMetadata,
    AssessedPolicyReference,
    EvidenceTraceReference,
    IntegratedAssessmentSuccess,
    ReviewedValueTrace,
    StepAssessmentTrace,
)
from ai_adoption_engine.models.process import BusinessProcess
from ai_adoption_engine.models.review import (
    InformationOrigin,
    ReviewDisposition,
)
from tests.fakes.review import FIXED_TIME, approved_review


ROOT = Path(__file__).resolve().parents[2]


def _origin(state: KnowledgeState) -> InformationOrigin:
    if state is KnowledgeState.KNOWN:
        return InformationOrigin.DOCUMENT_SUPPORTED
    if state is KnowledgeState.INFERRED:
        return InformationOrigin.MODEL_INFERRED
    return InformationOrigin.UNKNOWN


def _evidence(reference, document_id: str) -> EvidenceTraceReference:
    length = max(1, len(reference.supporting_snippet))
    return EvidenceTraceReference(
        evidence_id=reference.evidence_id,
        document_id=document_id,
        block_id=f"synthetic-{reference.evidence_id.lower()}",
        block_start_offset=0,
        block_end_offset=length,
        source_locator=reference.source_locator,
    )


def sample_integrated_assessment() -> IntegratedAssessmentSuccess:
    policy = load_policy(ROOT / "config" / "decision_policy.v0.2.json")
    with (ROOT / "data/sample_processes/synthetic_customer_complaint_process.json").open(
        encoding="utf-8"
    ) as handle:
        process = BusinessProcess.model_validate(json.load(handle))
    assessment = AssessmentEngine(policy).assess(process)
    base = approved_review()
    document_id = base.review.original_candidate.source_document_id
    traces = []
    for assessed in assessment.step_assessments:
        evidence_by_id = {item.evidence_id: item for item in assessed.evidence}
        base_assessment = (
            f"process_assessment.step_assessments[step_id={assessed.step_id}]"
        )
        base_review = f"review.steps[candidate_step_id={assessed.step_id}]"
        base_process = f"business_process.steps[step_id={assessed.step_id}]"

        def value_trace(name, state, evidence_ids, assessment_path):
            evidence = [
                _evidence(evidence_by_id[item], document_id)
                for item in evidence_ids
                if item in evidence_by_id
            ]
            return ReviewedValueTrace(
                validated_process_field_path=f"{base_process}.{name}",
                review_field_path=f"{base_review}.{name}",
                assessment_field_path=assessment_path,
                origin=_origin(state),
                knowledge_state=state,
                review_disposition=(
                    ReviewDisposition.UNKNOWN_RETAINED
                    if state is KnowledgeState.UNKNOWN
                    else ReviewDisposition.ACCEPTED
                ),
                evidence=evidence,
            )

        criteria = [
            value_trace(
                f"criteria[name={item.criterion.value}]",
                item.knowledge_state,
                item.evidence_ids,
                f"{base_assessment}.criteria[criterion={item.criterion.value}]",
            )
            for item in assessed.criteria
        ]
        accountability = value_trace(
            "human_accountability_required",
            assessed.human_accountability.knowledge_state,
            assessed.human_accountability.evidence_ids,
            f"{base_assessment}.human_accountability",
        )
        capability_signals = [
            ReviewedValueTrace(
                validated_process_field_path=(
                    f"{base_process}.capability_signals.synthetic_{index}"
                ),
                review_field_path=(
                    f"{base_review}.capability_signals[name=synthetic_{index}]"
                ),
                assessment_field_path=None,
                origin=InformationOrigin.UNKNOWN,
                knowledge_state=KnowledgeState.UNKNOWN,
                review_disposition=ReviewDisposition.UNKNOWN_RETAINED,
                evidence=[],
            )
            for index in range(10)
        ]
        activity_evidence = assessed.evidence[:1]
        traces.append(
            StepAssessmentTrace(
                step_id=assessed.step_id,
                assessment_step_path=base_assessment,
                recommendation_path=f"{base_assessment}.recommendation_mode",
                gate_results_path=f"{base_assessment}.gate_results",
                validated_step_path=base_process,
                review_step_path=base_review,
                activity=ReviewedValueTrace(
                    validated_process_field_path=f"{base_process}.activity",
                    review_field_path=f"{base_review}.activity",
                    assessment_field_path=f"{base_assessment}.activity",
                    origin=InformationOrigin.DOCUMENT_SUPPORTED,
                    knowledge_state=KnowledgeState.KNOWN,
                    review_disposition=ReviewDisposition.ACCEPTED,
                    evidence=[
                        _evidence(item, document_id) for item in activity_evidence
                    ],
                ),
                criteria=criteria,
                human_accountability=accountability,
                capability_signals=capability_signals,
            )
        )
    return IntegratedAssessmentSuccess(
        metadata=AssessmentRunMetadata(
            assessment_run_id="phase6-synthetic-assessment",
            assessed_at=FIXED_TIME,
            integration_schema_version=INTEGRATION_SCHEMA_VERSION,
            phase1_contract_version=PHASE1_CONTRACT_VERSION,
        ),
        lineage=AssessmentLineage(
            source_document_id=document_id,
            extraction_run_id="phase6-synthetic-extraction",
            review_id="phase6-synthetic-review",
            approval_event_id="phase6-synthetic-approval",
            approved_at=FIXED_TIME,
            validated_process_id=process.process_id,
            validated_process_fingerprint=fingerprint_business_process(process),
        ),
        policy=AssessedPolicyReference(
            policy_id=policy.policy_id,
            policy_version=policy.version,
            policy_status=policy.status,
            decision_policy_fingerprint=fingerprint_decision_policy(policy),
        ),
        process_assessment=assessment,
        step_traceability=traces,
    )

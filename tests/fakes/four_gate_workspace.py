from __future__ import annotations

from pathlib import Path

from ai_adoption_engine.application.four_gate_assessment import (
    FourGateIntegratedAssessmentService,
)
from ai_adoption_engine.decision.four_gate_policy import load_four_gate_policy
from ai_adoption_engine.decision_support.four_gate_service import (
    FourGateDecisionSupportPackageService,
)
from ai_adoption_engine.models.four_gate_decision_support import (
    FourGateDecisionPackageSuccess,
)
from ai_adoption_engine.models.four_gate_integrated_assessment import (
    FourGateIntegratedAssessmentSuccess,
)
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.evidence import CriterionInput
from ai_adoption_engine.models.review import (
    ApprovedProcessReview,
    InformationOrigin,
    ReviewDisposition,
)
from ai_adoption_engine.persistence.four_gate import FourGatePersistenceAdapter
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.workspace.models import (
    ArtifactType,
    ExecutionMode,
    WorkflowStage,
)
from tests.fakes.review import FIXED_TIME, approved_review


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "decision_policy.v0.3.json"


def persisted_four_gate_baseline(tmp_path):
    """Create one explicit, package-ready phase5/6 successor baseline."""

    return _persisted_four_gate_baseline(tmp_path, approved_review())


def persisted_four_gate_data_readiness_baseline(tmp_path):
    """Create an eligible successor baseline with one Gate 2 blocker."""

    approved = approved_review().model_copy(deep=True)
    process_step = approved.business_process.steps[0]
    review_step = approved.review.steps[0]
    evidence_id = process_step.evidence_ids[0]
    resolved_evidence = review_step.activity.evidence[0]
    known_values = {
        CriterionName.BUSINESS_VALUE: 4,
        CriterionName.IMPLEMENTATION_COMPLEXITY: 2,
    }
    for criterion, value in known_values.items():
        rationale = f"Human-reviewed fixture value for {criterion.value}."
        setattr(
            process_step.characteristics,
            criterion.value,
            CriterionInput(
                value=value,
                knowledge_state=KnowledgeState.KNOWN,
                rationale=rationale,
                evidence_ids=[evidence_id],
            ),
        )
        reviewed = next(
            item.assertion for item in review_step.criteria if item.name is criterion
        )
        reviewed.value = value
        reviewed.knowledge_state = KnowledgeState.KNOWN
        reviewed.origin = InformationOrigin.DOCUMENT_SUPPORTED
        reviewed.rationale = rationale
        reviewed.evidence = [resolved_evidence]
        reviewed.confidence = None
        reviewed.disposition = ReviewDisposition.CORRECTED
    approved = ApprovedProcessReview.model_validate(approved.model_dump(mode="json"))
    return _persisted_four_gate_baseline(tmp_path, approved)


def _persisted_four_gate_baseline(tmp_path, approved):
    tmp_path.mkdir(parents=True, exist_ok=True)
    policy = load_four_gate_policy(POLICY_PATH)
    integrated = FourGateIntegratedAssessmentService(
        policy_loader=lambda: policy,
        clock=lambda: FIXED_TIME,
        run_id_factory=lambda: "dcw-four-gate-phase5",
    ).assess(approved)
    assert isinstance(integrated, FourGateIntegratedAssessmentSuccess)
    package = FourGateDecisionSupportPackageService().generate(integrated)
    assert isinstance(package, FourGateDecisionPackageSuccess)

    repository = SQLiteAssessmentRepository(tmp_path / "four-gate-dcw.db")
    adapter = FourGatePersistenceAdapter(repository)
    assessment = adapter.create_assessment(
        "Four-gate DCW baseline",
        ExecutionMode.OFFLINE_DEMO,
        policy_fingerprint=integrated.policy.decision_policy_fingerprint,
    )
    review_reference = repository.save_artifact_and_advance(
        assessment.assessment_id,
        ArtifactType.REVIEW_SESSION,
        approved.review,
        artifact_schema_version="phase4-v0.1",
        stage=WorkflowStage.IN_REVIEW,
    )
    approved_reference = repository.save_artifact_and_advance(
        assessment.assessment_id,
        ArtifactType.APPROVED_REVIEW,
        approved,
        artifact_schema_version="phase4-v0.1",
        stage=WorkflowStage.APPROVED,
        parent_artifact_id=review_reference.artifact_id,
    )
    integrated_reference = adapter.persist_integrated_assessment(
        assessment.assessment_id,
        integrated,
        approved_artifact_id=approved_reference.artifact_id,
    )
    package_reference = adapter.persist_decision_package(
        assessment.assessment_id,
        package,
        integrated_artifact_id=integrated_reference.artifact_id,
    )
    return repository, assessment.assessment_id, integrated, package, package_reference

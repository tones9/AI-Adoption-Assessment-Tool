"""Deterministic helpers for successor four-gate reassessment tests."""

from __future__ import annotations

from itertools import count

from ai_adoption_engine.decision.four_gate_policy import load_four_gate_policy
from ai_adoption_engine.grw.four_gate_m2.models import (
    FourGateM2ActorDeclaration,
    FourGateM2ConflictStatus,
    FourGateM2DocumentLocator,
    FourGateM2EvidencePermission,
)
from ai_adoption_engine.grw.four_gate_m2.service import FourGateM2Service
from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.persistence.four_gate_reassessment import (
    SQLiteFourGateReassessmentRepository,
)
from tests.fakes.four_gate_workspace import (
    POLICY_PATH,
    persisted_four_gate_data_readiness_baseline,
)
from tests.fakes.review import FIXED_TIME


DOCUMENT_BYTES = b"Data systems are complete and validated for this activity."


def successor_m2_service(tmp_path, *, policy_loader=None, phase5_factory=None, phase6=None):
    baseline_repository, assessment_id, integrated, package, package_ref = (
        persisted_four_gate_data_readiness_baseline(tmp_path)
    )
    sequence = count(1)
    id_factory = lambda prefix: f"{prefix}-{next(sequence)}"
    repository = SQLiteFourGateReassessmentRepository(
        baseline_repository.path,
        clock=lambda: FIXED_TIME,
        id_factory=id_factory,
    )
    service = FourGateM2Service(
        baseline_repository,
        repository,
        policy_loader=policy_loader or (lambda: load_four_gate_policy(POLICY_PATH)),
        phase5_service_factory=phase5_factory,
        phase6_service=phase6,
        clock=lambda: FIXED_TIME,
        id_factory=id_factory,
    )
    target_step_id = package.package.portfolio.items[0].step_id
    return {
        "baseline_repository": baseline_repository,
        "repository": repository,
        "assessment_id": assessment_id,
        "integrated": integrated,
        "package": package,
        "package_ref": package_ref,
        "service": service,
        "target_step_id": target_step_id,
    }


def actor(label: str = "Declared data owner") -> FourGateM2ActorDeclaration:
    return FourGateM2ActorDeclaration(
        label=label,
        declared_role="Data owner and criterion reviewer",
        acknowledged_local_role_limitation=True,
        declared_at=FIXED_TIME,
    )


def advance_to_reviewed(state):
    service = state["service"]
    manifest = service.create_run(state["assessment_id"], state["target_step_id"])
    declared = actor()
    submission = service.submit_supporting_document(
        manifest.run_id,
        content_bytes=DOCUMENT_BYTES,
        filename="data-readiness-evidence.txt",
        source_label="Declared data-owner report",
        submitter=declared,
    )
    text = DOCUMENT_BYTES.decode("utf-8")
    locator = FourGateM2DocumentLocator(
        start_offset=0,
        end_offset=len(text),
        line_start=1,
        line_end=1,
        exact_excerpt=text,
    )
    review = service.review_document_evidence(
        manifest.run_id,
        reviewer=declared,
        locator=locator,
        scope_statement="The target activity only.",
        period_statement="Current-state evidence at review time.",
        source_authority="Locally declared data owner.",
        applicability_statement="The statement applies to the target activity's data.",
        semantic_rationale="The reviewed statement maps to data readiness only.",
        limitations="Authority is locally declared and has not been externally verified.",
        conflict_status=FourGateM2ConflictStatus.CONSISTENT,
        conflict_rationale="No conflicting evidence was identified in the baseline.",
        permission=(
            FourGateM2EvidencePermission.CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE
        ),
    )
    return manifest, submission, review, declared


def advance_to_approved(state, *, value: int = 4):
    service = state["service"]
    manifest, submission, review, declared = advance_to_reviewed(state)
    resolution = service.propose_data_readiness_resolution(
        manifest.run_id,
        proposed_value=value,
        proposed_knowledge_state=KnowledgeState.KNOWN,
        mapping_rationale=f"Reviewed evidence supports data readiness score {value}.",
        data_owner=declared,
        criterion_reviewer=declared,
    )
    request = service.request_reassessment(manifest.run_id)
    approval = service.approve_reassessment(
        manifest.run_id,
        approver=declared,
        rationale="Approve only the documented data-readiness resolution.",
    )
    return manifest, submission, review, resolution, request, approval


def complete_lifecycle(state, *, value: int = 4):
    service = state["service"]
    prior = advance_to_approved(state, value=value)
    run_id = prior[0].run_id
    projection = service.build_successor_review(run_id)
    assessment = service.assess_successor(run_id)
    package = service.generate_successor_package(run_id)
    comparison = service.compare(run_id)
    return (*prior, projection, assessment, package, comparison)

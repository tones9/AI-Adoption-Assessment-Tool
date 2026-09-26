"""Closed, read-only contract discrimination for Decision Continuation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai_adoption_engine.models.decision_support import DecisionPackageSuccess
from ai_adoption_engine.models.four_gate_decision_support import (
    FourGateDecisionPackageSuccess,
    FourGateDecisionSupportPackage,
    FourGateInformationGapKind,
)
from ai_adoption_engine.models.four_gate_assessment import (
    DecisionStatus,
    FourGateName,
    FourGateStatus,
    OutcomeCode,
)
from ai_adoption_engine.models.four_gate_integrated_assessment import (
    FourGateIntegratedAssessmentSuccess,
)
from ai_adoption_engine.models.integrated_assessment import IntegratedAssessmentSuccess
from ai_adoption_engine.models.review import ApprovedProcessReview
from ai_adoption_engine.workspace.models import (
    ArtifactType,
    StoredArtifact,
    WorkflowStage,
    WorkspaceSnapshot,
)


class DecisionContinuationContractFamily(StrEnum):
    LEGACY = "LEGACY"
    FOUR_GATE = "FOUR_GATE"
    UNSUPPORTED = "UNSUPPORTED"


class SuccessorContinuationState(StrEnum):
    AVAILABLE = "AVAILABLE"
    DEFERRED_UNAVAILABLE = "DEFERRED_UNAVAILABLE"


@dataclass(frozen=True)
class DecisionContinuationArtifactIdentity:
    artifact_id: str
    artifact_revision: int
    artifact_schema_version: str
    payload_sha256: str
    parent_artifact_id: str | None


@dataclass(frozen=True)
class FourGateContinuationGate:
    gate: str
    status: str


@dataclass(frozen=True)
class FourGateContinuationDecision:
    sequence: int
    step_id: str
    activity: str
    decision_status: str
    change_disposition: str
    readiness_disposition: str
    selected_intervention_family: str
    autonomy_ceiling: str
    outcome_code: str
    gates: tuple[FourGateContinuationGate, ...]


@dataclass(frozen=True)
class FourGateContinuationBaseline:
    assessment_id: str
    package_id: str
    package_completeness: str
    framework_id: str
    framework_version: str
    phase1_contract_version: str
    phase5_schema_version: str
    phase6_schema_version: str
    policy_id: str
    policy_version: str
    policy_status: str
    policy_fingerprint: str
    approved_review: DecisionContinuationArtifactIdentity
    integrated_assessment: DecisionContinuationArtifactIdentity
    decision_package: DecisionContinuationArtifactIdentity
    decisions: tuple[FourGateContinuationDecision, ...]
    immutable: bool
    package: FourGateDecisionSupportPackage


@dataclass(frozen=True)
class DecisionContinuationContractView:
    contract_family: DecisionContinuationContractFamily
    successor_baseline: FourGateContinuationBaseline | None = None
    continuation_state: SuccessorContinuationState | None = None
    eligible_step_ids: tuple[str, ...] = ()
    failure_message: str | None = None

    @property
    def legacy_continuation_available(self) -> bool:
        return self.contract_family is DecisionContinuationContractFamily.LEGACY

    @property
    def successor_continuation_available(self) -> bool:
        return self.continuation_state is SuccessorContinuationState.AVAILABLE


def discriminate_decision_continuation(
    snapshot: WorkspaceSnapshot,
) -> DecisionContinuationContractView:
    """Identify one complete baseline family without version inference.

    This function reads only the already-hydrated snapshot. It never composes a
    GRW/M2 service, creates a run, or writes an artifact.
    """

    try:
        if _is_exact_legacy_baseline(snapshot):
            return DecisionContinuationContractView(
                contract_family=DecisionContinuationContractFamily.LEGACY
            )
        successor = _successor_baseline(snapshot)
        if successor is not None:
            eligible_step_ids = _eligible_successor_step_ids(successor.package)
            return DecisionContinuationContractView(
                contract_family=DecisionContinuationContractFamily.FOUR_GATE,
                successor_baseline=successor,
                continuation_state=(
                    SuccessorContinuationState.AVAILABLE
                    if eligible_step_ids
                    else SuccessorContinuationState.DEFERRED_UNAVAILABLE
                ),
                eligible_step_ids=eligible_step_ids,
            )
    except (AttributeError, KeyError, TypeError, ValueError):
        pass
    return DecisionContinuationContractView(
        contract_family=DecisionContinuationContractFamily.UNSUPPORTED,
        failure_message=(
            "The saved baseline contract could not be verified. "
            "No continuation action is available."
        ),
    )


def _active_baseline_artifacts(
    snapshot: WorkspaceSnapshot,
) -> tuple[StoredArtifact, StoredArtifact, StoredArtifact] | None:
    if snapshot.assessment.current_stage is not WorkflowStage.PACKAGE_READY:
        return None
    approved = snapshot.active_artifacts.get(ArtifactType.APPROVED_REVIEW)
    integrated = snapshot.active_artifacts.get(
        ArtifactType.INTEGRATED_ASSESSMENT_RESULT
    )
    package = snapshot.active_artifacts.get(ArtifactType.DECISION_PACKAGE_RESULT)
    if approved is None or integrated is None or package is None:
        return None
    if (
        integrated.parent_artifact_id != approved.artifact_id
        or package.parent_artifact_id != integrated.artifact_id
        or approved.artifact_schema_version != "phase4-v0.1"
        or not isinstance(approved.payload, ApprovedProcessReview)
    ):
        return None
    return approved, integrated, package


def _is_exact_legacy_baseline(snapshot: WorkspaceSnapshot) -> bool:
    artifacts = _active_baseline_artifacts(snapshot)
    if artifacts is None:
        return False
    _, integrated_artifact, package_artifact = artifacts
    pin = snapshot.assessment.contract_pin
    if (
        pin.decision_contract_version != "phase1-v0.3"
        or pin.policy_id != "decision_policy.v0.2"
        or pin.policy_version != "0.2.0"
        or integrated_artifact.artifact_schema_version != "phase5-v0.1"
        or package_artifact.artifact_schema_version != "phase6-v0.1"
        or not isinstance(integrated_artifact.payload, IntegratedAssessmentSuccess)
        or not isinstance(package_artifact.payload, DecisionPackageSuccess)
    ):
        return False
    integrated = integrated_artifact.payload
    package = package_artifact.payload.package
    return (
        integrated.metadata.integration_schema_version == "phase5-v0.1"
        and integrated.metadata.phase1_contract_version == "phase1-v0.3"
        and package.package_schema_version == "phase6-v0.1"
        and _policy_matches_pin(integrated.policy, pin)
        and _policy_matches_pin(package.source.policy, pin)
        and package.source.policy == integrated.policy
        and package.source.integrated_assessment_run_id
        == integrated.metadata.assessment_run_id
        and package.source.lineage == integrated.lineage
        and package.current_state.process_id
        == integrated.process_assessment.process_id
        and package.current_state.ordered_step_ids
        == [step.step_id for step in integrated.process_assessment.step_assessments]
    )


def _successor_baseline(
    snapshot: WorkspaceSnapshot,
) -> FourGateContinuationBaseline | None:
    artifacts = _active_baseline_artifacts(snapshot)
    if artifacts is None:
        return None
    approved_artifact, integrated_artifact, package_artifact = artifacts
    pin = snapshot.assessment.contract_pin
    if (
        pin.decision_contract_version != "phase1-v0.4"
        or pin.policy_id != "decision_policy.v0.3"
        or pin.policy_version != "0.3.0"
        or pin.virtual
        or integrated_artifact.artifact_schema_version != "phase5-v0.2"
        or package_artifact.artifact_schema_version != "phase6-v0.2"
        or not isinstance(
            integrated_artifact.payload, FourGateIntegratedAssessmentSuccess
        )
        or not isinstance(package_artifact.payload, FourGateDecisionPackageSuccess)
        or ArtifactType.GRW_EVIDENCE_SUBMISSION in snapshot.active_artifacts
        or ArtifactType.GRW_EVIDENCE_REVIEW in snapshot.active_artifacts
    ):
        return None

    integrated = integrated_artifact.payload
    package = package_artifact.payload.package
    assessment = integrated.process_assessment
    if (
        integrated.metadata.integration_schema_version != "phase5-v0.2"
        or integrated.metadata.phase1_contract_version != "phase1-v0.4"
        or assessment.decision_contract_version != "phase1-v0.4"
        or assessment.framework_id != "four-gate-framework.v0.1"
        or assessment.framework_version != "0.1"
        or package_artifact.payload.package_schema_version != "phase6-v0.2"
        or package.package_schema_version != "phase6-v0.2"
        or package.source.integration_schema_version != "phase5-v0.2"
        or package.source.phase1_contract_version != "phase1-v0.4"
        or package.current_state.framework_id != "four-gate-framework.v0.1"
        or package.current_state.framework_version != "0.1"
        or not _policy_matches_pin(integrated.policy, pin)
        or not _policy_matches_pin(package.source.policy, pin)
        or package.source.policy != integrated.policy
        or package.source.integrated_assessment_run_id
        != integrated.metadata.assessment_run_id
        or package.source.lineage != integrated.lineage
        or package.current_state.process_id != assessment.process_id
        or package.current_state.ordered_step_ids
        != [step.step_id for step in assessment.step_assessments]
        or not _successor_steps_agree(integrated, package)
    ):
        return None

    return FourGateContinuationBaseline(
        assessment_id=snapshot.assessment.assessment_id,
        package_id=package.package_id,
        package_completeness=package.completeness.value,
        framework_id=assessment.framework_id,
        framework_version=assessment.framework_version,
        phase1_contract_version=integrated.metadata.phase1_contract_version,
        phase5_schema_version=integrated.metadata.integration_schema_version,
        phase6_schema_version=package.package_schema_version,
        policy_id=integrated.policy.policy_id,
        policy_version=integrated.policy.policy_version,
        policy_status=integrated.policy.policy_status,
        policy_fingerprint=integrated.policy.decision_policy_fingerprint,
        approved_review=_artifact_identity(approved_artifact),
        integrated_assessment=_artifact_identity(integrated_artifact),
        decision_package=_artifact_identity(package_artifact),
        decisions=tuple(
            FourGateContinuationDecision(
                sequence=item.sequence,
                step_id=item.step_id,
                activity=item.activity,
                decision_status=item.decision_status.value,
                change_disposition=item.change_disposition.value,
                readiness_disposition=item.readiness_disposition.value,
                selected_intervention_family=(
                    item.selected_intervention_family.value
                ),
                autonomy_ceiling=item.autonomy_ceiling.value,
                outcome_code=item.outcome_code.value,
                gates=tuple(
                    FourGateContinuationGate(
                        gate=gate.gate.value,
                        status=gate.status.value,
                    )
                    for gate in item.gate_results
                ),
            )
            for item in package.portfolio.items
        ),
        immutable=True,
        package=package,
    )


def _successor_steps_agree(
    integrated: FourGateIntegratedAssessmentSuccess,
    package: FourGateDecisionSupportPackage,
) -> bool:
    assessed = integrated.process_assessment.step_assessments
    packaged = package.portfolio.items
    if len(assessed) != len(packaged):
        return False
    traces = {trace.step_id: trace for trace in integrated.step_traceability}
    if len(traces) != len(integrated.step_traceability):
        return False
    for source, item in zip(assessed, packaged, strict=True):
        if (
            item.step_id != source.step_id
            or item.activity != source.activity
            or item.decision_status is not source.decision_status
            or item.change_disposition is not source.change_disposition
            or item.readiness_disposition is not source.readiness_disposition
            or item.selected_intervention_family
            is not source.selected_intervention_family
            or item.autonomy_ceiling is not source.autonomy_ceiling
            or item.outcome_code is not source.outcome_code
            or item.gate_results != source.gate_results
            or item.source_traceability != traces.get(source.step_id)
        ):
            return False
    return True


def _policy_matches_pin(policy, pin) -> bool:
    return (
        policy.policy_id == pin.policy_id
        and policy.policy_version == pin.policy_version
        and policy.decision_policy_fingerprint == pin.decision_policy_fingerprint
    )


def _eligible_successor_step_ids(
    package: FourGateDecisionSupportPackage,
) -> tuple[str, ...]:
    eligible: list[str] = []
    for item in package.portfolio.items:
        active = [
            gap
            for gap in item.information_gaps
            if gap.kind is FourGateInformationGapKind.ACTIVE_DECISION_BLOCKER
        ]
        gate_two = item.gate_results[1]
        if (
            item.decision_status is DecisionStatus.DISCOVERY_REQUIRED
            and item.outcome_code is OutcomeCode.DISCOVERY_REQUIRED
            and len(active) == 1
            and active[0].gate is FourGateName.IS_IT_READY
            and active[0].field_name == "data_readiness"
            and gate_two.gate is FourGateName.IS_IT_READY
            and gate_two.status is FourGateStatus.BLOCKED_BY_EVIDENCE
            and len(gate_two.blocking_gaps) == 1
            and gate_two.blocking_gaps[0].field_name == "data_readiness"
        ):
            eligible.append(item.step_id)
    return tuple(eligible)


def _artifact_identity(
    artifact: StoredArtifact,
) -> DecisionContinuationArtifactIdentity:
    return DecisionContinuationArtifactIdentity(
        artifact_id=artifact.artifact_id,
        artifact_revision=artifact.artifact_revision,
        artifact_schema_version=artifact.artifact_schema_version,
        payload_sha256=artifact.payload_sha256,
        parent_artifact_id=artifact.parent_artifact_id,
    )

"""Pure same-contract typed comparison for four-gate reassessment."""

from __future__ import annotations

from datetime import datetime

from ai_adoption_engine.grw.four_gate_m2.models import (
    FourGateM2ArtifactReference,
    FourGateM2BaselineReference,
    FourGateM2BaselineSuccessorComparison,
    FourGateM2DecisionSnapshot,
)
from ai_adoption_engine.models.four_gate_decision_support import (
    FourGateDecisionPackageSuccess,
)


class FourGateM2ComparisonError(ValueError):
    pass


class FourGateM2ComparisonService:
    def compare(
        self,
        *,
        comparison_id: str,
        run_id: str,
        created_at: datetime,
        baseline: FourGateM2BaselineReference,
        baseline_package: FourGateDecisionPackageSuccess,
        successor_package_artifact: FourGateM2ArtifactReference,
        successor_package: FourGateDecisionPackageSuccess,
        target_step_id: str,
        successor_data_readiness: int,
        successor_evidence_ids: list[str],
    ) -> FourGateM2BaselineSuccessorComparison:
        old = baseline_package.package
        new = successor_package.package
        if (
            old.package_id != baseline.package_id
            or old.package_schema_version != "phase6-v0.2"
            or new.package_schema_version != "phase6-v0.2"
            or old.current_state.framework_id != "four-gate-framework.v0.1"
            or new.current_state.framework_id != "four-gate-framework.v0.1"
            or old.source.phase1_contract_version != "phase1-v0.4"
            or new.source.phase1_contract_version != "phase1-v0.4"
            or old.source.policy.policy_id != "decision_policy.v0.3"
            or new.source.policy.policy_id != "decision_policy.v0.3"
            or old.source.policy.policy_version != "0.3.0"
            or new.source.policy.policy_version != "0.3.0"
            or old.source.policy.decision_policy_fingerprint
            != baseline.decision_policy_fingerprint
            or new.source.policy.decision_policy_fingerprint
            != baseline.decision_policy_fingerprint
        ):
            raise FourGateM2ComparisonError(
                "Comparison requires two snapshots of the pinned four-gate contract"
            )
        try:
            old_item = next(
                item for item in old.portfolio.items if item.step_id == target_step_id
            )
            new_item = next(
                item for item in new.portfolio.items if item.step_id == target_step_id
            )
        except StopIteration as exc:
            raise FourGateM2ComparisonError(
                "Comparison target must exist in both same-contract packages"
            ) from exc

        baseline_snapshot = _snapshot(old_item)
        successor_snapshot = _snapshot(new_item)
        categories = ["DATA_READINESS_CHANGE"]
        if baseline_snapshot.decision_status is not successor_snapshot.decision_status:
            categories.append("DECISION_STATUS_CHANGE")
        if (
            baseline_snapshot.change_disposition,
            baseline_snapshot.readiness_disposition,
            baseline_snapshot.selected_intervention_family,
            baseline_snapshot.autonomy_ceiling,
            baseline_snapshot.outcome_code,
        ) != (
            successor_snapshot.change_disposition,
            successor_snapshot.readiness_disposition,
            successor_snapshot.selected_intervention_family,
            successor_snapshot.autonomy_ceiling,
            successor_snapshot.outcome_code,
        ):
            categories.append("TYPED_DECISION_CHANGE")
        if baseline_snapshot.gate_results != successor_snapshot.gate_results:
            categories.append("GATE_CHANGE")
        if (
            baseline_snapshot.priority_status,
            baseline_snapshot.priority_score,
        ) != (
            successor_snapshot.priority_status,
            successor_snapshot.priority_score,
        ):
            categories.append("PRIORITY_CHANGE")
        if len(categories) == 1:
            categories.append("NO_FORMAL_DECISION_CHANGE")
        return FourGateM2BaselineSuccessorComparison(
            comparison_id=comparison_id,
            run_id=run_id,
            created_at=created_at,
            baseline=baseline,
            successor_package_artifact=successor_package_artifact,
            target_step_id=target_step_id,
            baseline_data_readiness=None,
            successor_data_readiness=successor_data_readiness,
            baseline_evidence_ids=[],
            successor_evidence_ids=successor_evidence_ids,
            baseline_decision=baseline_snapshot,
            successor_decision=successor_snapshot,
            categories=categories,
            neutral_explanation=(
                "This records a same-contract decision difference after one "
                "approved data-readiness evidence change. It does not establish "
                "improvement, regression, deployment readiness, implementation "
                "success, or Return on Investment (ROI)."
            ),
        )


def _snapshot(item) -> FourGateM2DecisionSnapshot:
    return FourGateM2DecisionSnapshot(
        decision_status=item.decision_status,
        change_disposition=item.change_disposition,
        readiness_disposition=item.readiness_disposition,
        selected_intervention_family=item.selected_intervention_family,
        autonomy_ceiling=item.autonomy_ceiling,
        outcome_code=item.outcome_code,
        gate_results=item.gate_results,
        priority_status=item.priority_status,
        priority_score=item.priority.score if item.priority is not None else None,
    )

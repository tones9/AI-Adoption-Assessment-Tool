"""Pure deterministic M2 baseline/successor package comparison."""

from __future__ import annotations

from datetime import datetime

from ai_adoption_engine.grw.m2.models import (
    M2ArtifactReference,
    M2BaselineReference,
    M2BaselineSuccessorComparison,
)
from ai_adoption_engine.models.decision_support import DecisionPackageSuccess


class M2ComparisonService:
    def compare(
        self,
        *,
        comparison_id: str,
        run_id: str,
        created_at: datetime,
        baseline: M2BaselineReference,
        baseline_package: DecisionPackageSuccess,
        successor_package_artifact: M2ArtifactReference,
        successor_package: DecisionPackageSuccess,
        target_step_id: str,
        baseline_data_readiness: int | None,
        successor_data_readiness: int | None,
    ) -> M2BaselineSuccessorComparison:
        old_item = next(item for item in baseline_package.package.portfolio.items if item.step_id == target_step_id)
        new_item = next(item for item in successor_package.package.portfolio.items if item.step_id == target_step_id)
        categories: list[str] = []
        if baseline_data_readiness != successor_data_readiness:
            categories.append("CRITERION_CHANGE")
        if [x.model_dump(mode="json") for x in old_item.gate_results] != [x.model_dump(mode="json") for x in new_item.gate_results]:
            categories.append("GATE_CHANGE")
        if old_item.recommendation_mode != new_item.recommendation_mode:
            categories.append("RECOMMENDATION_CHANGE")
        if not categories:
            categories.append("NO_FORMAL_CHANGE")
        return M2BaselineSuccessorComparison(
            comparison_id=comparison_id,
            run_id=run_id,
            created_at=created_at,
            baseline=baseline,
            successor_package_artifact=successor_package_artifact,
            target_step_id=target_step_id,
            baseline_data_readiness=baseline_data_readiness,
            successor_data_readiness=successor_data_readiness,
            baseline_recommendation=old_item.recommendation_mode.value,
            successor_recommendation=new_item.recommendation_mode.value,
            categories=categories,
            neutral_explanation="The comparison records a formal difference after approved additional evidence. It does not describe recommendation movement as success, an outcome, or ROI proof.",
        )

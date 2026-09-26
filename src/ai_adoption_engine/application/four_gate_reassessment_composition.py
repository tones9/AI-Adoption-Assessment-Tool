"""Explicit composition root for the activated successor DCW path."""

from __future__ import annotations

from pathlib import Path

from ai_adoption_engine.decision.four_gate_policy import load_four_gate_policy
from ai_adoption_engine.grw.four_gate_m2.service import FourGateM2Service
from ai_adoption_engine.persistence.four_gate_reassessment import (
    SQLiteFourGateReassessmentRepository,
    assert_four_gate_m2_write_target_allowed,
)
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository


ROOT = Path(__file__).resolve().parents[3]
SUCCESSOR_POLICY_PATH = ROOT / "config" / "decision_policy.v0.3.json"


def build_four_gate_m2_service(database_path: str | Path) -> FourGateM2Service:
    """Compose only the explicit v0.3 successor lifecycle."""

    assert_four_gate_m2_write_target_allowed(database_path)
    baseline = SQLiteAssessmentRepository(database_path)
    reassessment = SQLiteFourGateReassessmentRepository(database_path)
    return FourGateM2Service(
        baseline,
        reassessment,
        policy_loader=lambda: load_four_gate_policy(SUCCESSOR_POLICY_PATH),
    )

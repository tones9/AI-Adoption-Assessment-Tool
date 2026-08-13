import json
from pathlib import Path

import pytest

from ai_adoption_engine.decision.engine import AssessmentEngine
from ai_adoption_engine.decision.policy import DecisionPolicy, load_policy
from ai_adoption_engine.models.process import BusinessProcess

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = PROJECT_ROOT / "config" / "decision_policy.v0.2.json"
SAMPLE_PATH = (
    PROJECT_ROOT
    / "data"
    / "sample_processes"
    / "synthetic_customer_complaint_process.json"
)


@pytest.fixture
def policy() -> DecisionPolicy:
    return load_policy(POLICY_PATH)


@pytest.fixture
def process() -> BusinessProcess:
    with SAMPLE_PATH.open(encoding="utf-8") as handle:
        return BusinessProcess.model_validate(json.load(handle))


@pytest.fixture
def engine(policy: DecisionPolicy) -> AssessmentEngine:
    return AssessmentEngine(policy)

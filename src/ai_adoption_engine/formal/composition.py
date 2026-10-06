"""Default-off composition for the formal-assessment product boundary.

This module is intentionally inert until the presentation activation layer calls
it.  In particular it does not load a policy, construct a provider, project an
input, or invoke the strict engine during composition.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_adoption_engine.formal.input_adapter import FormalFourGateInputAdapter
from ai_adoption_engine.formal.run_service import FormalAssessmentRunService
from ai_adoption_engine.persistence.formal_assessment import (
    SQLiteFormalAssessmentRepository,
)
from ai_adoption_engine.persistence.formal_evidence import SQLiteFormalEvidenceRepository


DEFAULT_FOUR_GATE_POLICY = (
    Path(__file__).resolve().parents[3] / "config" / "decision_policy.v0.3.json"
)


@dataclass(frozen=True)
class FormalAssessmentServiceBundle:
    """The explicit service dependencies for one writable application database."""

    repository: SQLiteFormalAssessmentRepository
    evidence_repository: SQLiteFormalEvidenceRepository
    adapter: FormalFourGateInputAdapter
    runs: FormalAssessmentRunService
    policy_path: Path


RepositoryFactory = Callable[[str | Path], SQLiteFormalAssessmentRepository]
EvidenceRepositoryFactory = Callable[[str | Path], SQLiteFormalEvidenceRepository]
AdapterFactory = Callable[[], FormalFourGateInputAdapter]
RunServiceFactory = Callable[..., FormalAssessmentRunService]


def build_formal_assessment_service_bundle(
    database_path: str | Path,
    *,
    policy_path: str | Path = DEFAULT_FOUR_GATE_POLICY,
    repository_factory: RepositoryFactory = SQLiteFormalAssessmentRepository,
    evidence_repository_factory: EvidenceRepositoryFactory = SQLiteFormalEvidenceRepository,
    adapter_factory: AdapterFactory = FormalFourGateInputAdapter,
    run_service_factory: RunServiceFactory = FormalAssessmentRunService,
) -> FormalAssessmentServiceBundle:
    """Construct migrations 7/8 only after the UI activation guard has passed."""

    repository = repository_factory(database_path)
    # This second repository is read-only in use here.  It has no provider or
    # extraction service and gives the controller exact supporting history.
    evidence_repository = evidence_repository_factory(database_path)
    adapter = adapter_factory()
    exact_policy = Path(policy_path)
    return FormalAssessmentServiceBundle(
        repository=repository,
        evidence_repository=evidence_repository,
        adapter=adapter,
        runs=run_service_factory(repository, policy_path=exact_policy, adapter=adapter),
        policy_path=exact_policy,
    )

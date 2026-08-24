"""Small provider-independent composition root for the Phase 7 application."""

from __future__ import annotations

import os
from pathlib import Path

from ai_adoption_engine.workspace.demo_fixtures import fixture_for_document_id
from ai_adoption_engine.workspace.service import AssessmentWorkspaceService
from ai_adoption_engine.workspace.models import ExecutionMode
from ai_adoption_engine.extraction.errors import ExtractionProviderConfigurationError
from ai_adoption_engine.extraction.service import ProcessExtractionService
from ai_adoption_engine.models.document import IngestedDocument
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.persistence.reassessment import (
    SQLiteReassessmentRepository,
    assert_m2_write_target_allowed,
)
from ai_adoption_engine.grw.m2.service import M2ReassessmentService
from ai_adoption_engine.application.decision_continuation import DecisionContinuationService


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_PATH = ROOT / "var" / "ai_adoption_engine.db"
DEFAULT_EXTRACTION_CONFIG = ROOT / "config" / "extraction.v0.1.json"


def extraction_service_for(
    mode: ExecutionMode, document: IngestedDocument
) -> ProcessExtractionService:
    if mode is ExecutionMode.OFFLINE_DEMO:
        # Scripted extraction stays bound to the exact document it was written
        # for; the registry only allows more than one bundled fixture.
        fixture = fixture_for_document_id(document.document_id)
        if fixture is None:
            raise ExtractionProviderConfigurationError(
                "Offline scripted extraction is available only for a bundled synthetic demo document."
            )
        return ProcessExtractionService(fixture.provider(), repair_attempts=0)
    if not os.environ.get("OPENAI_API_KEY"):
        raise ExtractionProviderConfigurationError(
            "Live extraction requires OPENAI_API_KEY in the local environment."
        )
    # The optional provider and SDK path are imported only for explicit live mode.
    from ai_adoption_engine.extraction.providers.openai import (
        build_openai_extraction_service,
    )

    return build_openai_extraction_service(DEFAULT_EXTRACTION_CONFIG)


def build_workspace_service(
    database_path: str | Path | None = None,
) -> AssessmentWorkspaceService:
    repository = SQLiteAssessmentRepository(database_path or DEFAULT_DATABASE_PATH)
    return AssessmentWorkspaceService(
        repository,
        extraction_service_factory=extraction_service_for,
    )


def build_m2_reassessment_service(
    database_path: str | Path | None = None,
) -> M2ReassessmentService:
    """Compose M2 separately; protect frozen targets before any database open."""
    path = database_path or DEFAULT_DATABASE_PATH
    assert_m2_write_target_allowed(path)
    baseline = SQLiteAssessmentRepository(path)
    reassessment = SQLiteReassessmentRepository(path)
    return M2ReassessmentService(baseline, reassessment)


def build_decision_continuation_service(
    database_path: str | Path | None = None,
) -> DecisionContinuationService:
    """Compose the read-only DCW view for an ordinary local workspace.

    The same frozen-workspace guard applies before either M2 collaborator is
    constructed.  DCW intentionally receives existing services rather than
    creating a new persistence model or lifecycle write path.
    """

    path = database_path or DEFAULT_DATABASE_PATH
    assert_m2_write_target_allowed(path)
    workspace = build_workspace_service(path)
    reassessment = SQLiteReassessmentRepository(path)
    m2 = M2ReassessmentService(workspace.repository, reassessment)
    return DecisionContinuationService(workspace, m2)

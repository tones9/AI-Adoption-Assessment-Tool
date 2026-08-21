from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ai_adoption_engine.persistence.workspace_protection import Phase4FrozenWorkspaceError
from ai_adoption_engine.workspace.composition import build_workspace_service
from ai_adoption_engine.workspace.demo_extraction import demo_text
from ai_adoption_engine.workspace.models import ExecutionMode
from ai_adoption_engine.workspace.service import (
    AssessmentWorkspaceService,
    WorkflowGuardError,
)


ROOT = Path(__file__).resolve().parents[2]
PORT004_PRE_M2_WORKSPACE = (
    ROOT
    / "evaluation"
    / "portfolio"
    / "runs"
    / "port-004"
    / "production-run-v0.2-review"
    / "workspace.db"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _migration_versions(path: Path, *, read_only: bool) -> list[int]:
    connection = sqlite3.connect(
        f"file:{path}?mode=ro" if read_only else path,
        uri=read_only,
    )
    try:
        return [
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
    finally:
        connection.close()


class _ProtectedRepositoryDouble:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load_workspace(self, *_args, **_kwargs):
        raise AssertionError("The Phase 4 guard must refuse before repository access")


def test_all_phase4_write_entry_points_refuse_before_repository_access(tmp_path: Path) -> None:
    protected = tmp_path / "evaluation" / "portfolio" / "PORT-004" / "workspace.db"
    protected.parent.mkdir(parents=True)
    protected.write_bytes(b"frozen evaluation bytes")
    before = _sha256(protected)
    service = AssessmentWorkspaceService(
        _ProtectedRepositoryDouble(protected), extraction_service_factory=lambda *_args: None
    )

    attempts = (
        lambda: service.start_review("assessment"),
        lambda: service.save_review("assessment", None),
        lambda: service.approve("assessment"),
        lambda: service.reset_to_review("assessment"),
    )
    for attempt in attempts:
        with pytest.raises(Phase4FrozenWorkspaceError, match="refused for frozen evaluation portfolio"):
            attempt()
        assert _sha256(protected) == before


def test_protected_p2_access_never_composes_or_migrates_a_pre_m2_port004_copy(
    tmp_path: Path, monkeypatch
) -> None:
    """P2 must stop before ordinary workspace composition can migrate a freeze."""

    assert PORT004_PRE_M2_WORKSPACE.is_file()
    source_before = _sha256(PORT004_PRE_M2_WORKSPACE)
    source_versions = _migration_versions(PORT004_PRE_M2_WORKSPACE, read_only=True)
    assert source_versions == [1]

    protected = (
        tmp_path / "evaluation" / "portfolio" / "PORT-004-copy" / "workspace.db"
    )
    protected.parent.mkdir(parents=True)
    shutil.copy2(PORT004_PRE_M2_WORKSPACE, protected)
    before = _sha256(protected)
    before_versions = _migration_versions(protected, read_only=True)
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(protected))

    from ai_adoption_engine.presentation.pages import review as review_page

    def _unexpected_hydration(*_args, **_kwargs):
        raise AssertionError("Protected P2 review attempted ordinary workspace hydration")

    monkeypatch.setattr(review_page, "hydrate_workspace", _unexpected_hydration)

    app = AppTest.from_string(
        "import streamlit as st\n"
        "st.session_state.selected_assessment_id = 'frozen-port-004'\n"
        "from ai_adoption_engine.presentation.pages.review import render\n"
        "render()",
        default_timeout=30,
    ).run()

    assert not app.exception
    rendered = "\n".join(
        str(item.value)
        for kind in ("info", "error", "write")
        for item in app.get(kind)
    )
    assert "frozen evaluation record" in rendered
    assert _migration_versions(protected, read_only=True) == before_versions
    assert _sha256(protected) == before
    assert _migration_versions(PORT004_PRE_M2_WORKSPACE, read_only=True) == source_versions
    assert _sha256(PORT004_PRE_M2_WORKSPACE) == source_before


def test_ordinary_workspace_keeps_existing_phase4_lifecycle(tmp_path: Path) -> None:
    service = build_workspace_service(tmp_path / "ordinary.db")
    assessment = service.repository.create_assessment("Ordinary P2 control", ExecutionMode.OFFLINE_DEMO)
    service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    service.extract(assessment.assessment_id)
    review = service.start_review(assessment.assessment_id)
    service.review_service.accept_assertion(review, review.process_name, "process.name")
    for step in review.steps:
        service.review_service.accept_assertion(
            review, step.activity, f"steps.{step.candidate_step_id}.activity"
        )
    service.review_service.accept_step_order(review)
    service.save_review(assessment.assessment_id, review)
    assert service.approve(assessment.assessment_id).approved is not None


def test_stale_review_identity_is_refused_by_the_existing_phase4_save_boundary(
    tmp_path: Path,
) -> None:
    service = build_workspace_service(tmp_path / "stale.db")
    assessment = service.repository.create_assessment("Stale P2 control", ExecutionMode.OFFLINE_DEMO)
    service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    service.extract(assessment.assessment_id)
    current = service.start_review(assessment.assessment_id)
    stale = current.model_copy(update={"review_id": "stale-review-id"})

    with pytest.raises(WorkflowGuardError, match="Only the current review session"):
        service.save_review(assessment.assessment_id, stale)

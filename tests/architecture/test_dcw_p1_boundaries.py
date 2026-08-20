from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ai_adoption_engine.persistence.reassessment import M2FrozenWorkspaceError
from ai_adoption_engine.workspace.composition import build_decision_continuation_service


ROOT = Path(__file__).resolve().parents[2]


def test_dcw_application_and_page_do_not_own_lifecycle_writes() -> None:
    application = (
        ROOT / "src" / "ai_adoption_engine" / "application" / "decision_continuation.py"
    ).read_text(encoding="utf-8")
    page = (
        ROOT
        / "src"
        / "ai_adoption_engine"
        / "presentation"
        / "pages"
        / "decision_continuation.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "create_run(",
        "submit_supporting_document(",
        "review_document_evidence(",
        "propose_data_readiness_resolution(",
        "request_reassessment(",
        "approve_reassessment(",
        "build_successor_review(",
        "assess_successor(",
        "generate_successor_package(",
        "reset_to_review(",
        "AssessmentEngine(",
        "DecisionSupportPackageService(",
    ):
        assert forbidden not in application
        assert forbidden not in page
    assert "file_uploader" not in page
    assert "data_editor" not in page


def test_dcw_composition_refuses_protected_workspace_before_opening_it(tmp_path) -> None:
    protected = tmp_path / "evaluation" / "portfolio" / "PORT-004" / "workspace.db"
    protected.parent.mkdir(parents=True)
    protected.write_bytes(b"frozen evaluation workspace")
    before = hashlib.sha256(protected.read_bytes()).hexdigest()

    with pytest.raises(M2FrozenWorkspaceError):
        build_decision_continuation_service(protected)

    assert hashlib.sha256(protected.read_bytes()).hexdigest() == before


def test_grw_pages_return_to_dcw_only_through_registered_navigation() -> None:
    for filename in ("gap_resolution.py", "reassessment.py"):
        source = (
            ROOT / "src" / "ai_adoption_engine" / "presentation" / "pages" / filename
        ).read_text(encoding="utf-8")
        assert "Return to decision continuation" in source
        assert 'switch_to_registered_page("decision-continuation")' in source

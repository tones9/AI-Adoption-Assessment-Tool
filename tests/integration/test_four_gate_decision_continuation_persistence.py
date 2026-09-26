from __future__ import annotations

import hashlib
import sqlite3

import pytest

from ai_adoption_engine.application.decision_continuation import (
    DecisionContinuationService,
)
from ai_adoption_engine.application.four_gate_decision_continuation import (
    DecisionContinuationContractFamily,
    discriminate_decision_continuation,
)
from ai_adoption_engine.grw.m2.service import M2ReassessmentService
from ai_adoption_engine.grw.m2.service import M2ReassessmentError
from ai_adoption_engine.persistence.reassessment import SQLiteReassessmentRepository
from ai_adoption_engine.workspace.service import AssessmentWorkspaceService
from tests.fakes.four_gate_workspace import persisted_four_gate_baseline


def _counts(path) -> tuple[int, int, int]:
    connection = sqlite3.connect(path)
    try:
        return (
            connection.execute("SELECT COUNT(*) FROM assessment_artifacts").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM assessment_operations").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM reassessment_runs").fetchone()[0],
        )
    finally:
        connection.close()


def test_persisted_successor_dcw_is_read_only_and_creates_no_m1_or_m2_state(
    tmp_path,
) -> None:
    repository, assessment_id, *_ = persisted_four_gate_baseline(tmp_path)
    before_hash = hashlib.sha256(repository.path.read_bytes()).hexdigest()
    before_counts = _counts(repository.path)
    snapshot = repository.load_workspace(assessment_id)

    view = discriminate_decision_continuation(snapshot)

    assert view.contract_family is DecisionContinuationContractFamily.FOUR_GATE
    assert view.successor_baseline is not None
    assert view.successor_baseline.immutable is True
    assert view.legacy_continuation_available is False
    assert view.successor_continuation_available is False
    assert _counts(repository.path) == before_counts
    assert hashlib.sha256(repository.path.read_bytes()).hexdigest() == before_hash


def test_legacy_dcw_service_refuses_successor_before_loading_grw_or_m2(
    tmp_path,
    monkeypatch,
) -> None:
    repository, assessment_id, *_ = persisted_four_gate_baseline(tmp_path)
    workspace = AssessmentWorkspaceService(
        repository, extraction_service_factory=lambda *_args: None
    )
    m2 = M2ReassessmentService(
        repository, SQLiteReassessmentRepository(repository.path)
    )
    monkeypatch.setattr(
        workspace,
        "load_grw_m1_status",
        lambda *_args: pytest.fail("legacy GRW M1 must not be loaded"),
    )
    monkeypatch.setattr(
        m2,
        "load_m2_baseline_reference",
        lambda *_args: pytest.fail("legacy M2 must not be loaded"),
    )

    with pytest.raises(ValueError, match="package-ready baseline"):
        DecisionContinuationService(workspace, m2).open(assessment_id)


def test_successor_baseline_is_ineligible_for_legacy_m1_and_m2_creation(
    tmp_path,
) -> None:
    repository, assessment_id, *_ = persisted_four_gate_baseline(tmp_path)
    workspace = AssessmentWorkspaceService(
        repository, extraction_service_factory=lambda *_args: None
    )
    m2 = M2ReassessmentService(
        repository, SQLiteReassessmentRepository(repository.path)
    )
    before = _counts(repository.path)

    assert workspace.open_grw_m1_context(assessment_id) is None
    assert m2.load_m2_baseline_reference(assessment_id) is None
    assert m2.open_m2_m1_context(assessment_id) is None
    with pytest.raises(M2ReassessmentError, match="package-ready baseline"):
        m2.create_run(assessment_id)

    assert _counts(repository.path) == before

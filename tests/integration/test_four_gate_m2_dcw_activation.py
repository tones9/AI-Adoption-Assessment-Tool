from __future__ import annotations

import hashlib
import shutil
import sqlite3

import pytest

from ai_adoption_engine.application.four_gate_decision_continuation import (
    DecisionContinuationContractFamily,
    SuccessorContinuationState,
    discriminate_decision_continuation,
)
from ai_adoption_engine.application.four_gate_reassessment_composition import (
    build_four_gate_m2_service,
)
from ai_adoption_engine.grw.four_gate_m2.models import FourGateM2RunStage
from ai_adoption_engine.grw.four_gate_m2.service import FourGateM2Error
from ai_adoption_engine.presentation.context import (
    four_gate_m2_continuation_available,
)
from ai_adoption_engine.workspace.models import ArtifactType
from tests.fakes.four_gate_m2 import actor
from tests.fakes.four_gate_workspace import (
    persisted_four_gate_baseline,
    persisted_four_gate_data_readiness_baseline,
)


def _baseline_rows(path) -> tuple[list[tuple], list[tuple]]:
    with sqlite3.connect(path) as connection:
        artifacts = connection.execute(
            "SELECT artifact_id, artifact_type, artifact_schema_version, payload_json, "
            "payload_sha256, parent_artifact_id FROM assessment_artifacts "
            "ORDER BY artifact_id"
        ).fetchall()
        active = connection.execute(
            "SELECT assessment_id, artifact_type, artifact_id FROM active_artifacts "
            "ORDER BY assessment_id, artifact_type"
        ).fetchall()
    return artifacts, active


def _successor_counts(path) -> tuple[int, int, int]:
    with sqlite3.connect(path) as connection:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        return tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if table in names
            else 0
            for table in (
                "four_gate_reassessment_runs",
                "four_gate_reassessment_artifacts",
                "four_gate_reassessment_documents",
            )
        )


def test_dcw_activation_is_explicit_resumable_idempotent_and_baseline_preserving(
    tmp_path,
) -> None:
    repository, assessment_id, _, package_result, _ = (
        persisted_four_gate_data_readiness_baseline(tmp_path)
    )
    target_step_id = package_result.package.portfolio.items[0].step_id
    before = _baseline_rows(repository.path)
    view = discriminate_decision_continuation(repository.load_workspace(assessment_id))

    assert view.continuation_state is SuccessorContinuationState.AVAILABLE
    assert _successor_counts(repository.path) == (0, 0, 0)

    first_service = build_four_gate_m2_service(repository.path)
    first = first_service.create_run(assessment_id, target_step_id)
    repeated = first_service.create_run(assessment_id, target_step_id)
    resumed_service = build_four_gate_m2_service(repository.path)
    resumed = resumed_service.repository.list_runs(assessment_id)

    assert first == repeated
    assert [row["run_id"] for row in resumed] == [first.run_id]
    assert resumed[0]["stage"] == FourGateM2RunStage.OPEN.value
    assert resumed_service.open_context(assessment_id, target_step_id) is not None
    assert _successor_counts(repository.path) == (1, 1, 0)
    assert _baseline_rows(repository.path) == before


@pytest.mark.parametrize(
    ("filename", "content", "match"),
    [
        ("support.pdf", b"valid UTF-8", "UTF-8"),
        ("support.txt", b"\xff\xfe", "UTF-8"),
    ],
)
def test_dcw_document_intake_accepts_only_utf8_txt_without_partial_write(
    tmp_path, filename, content, match
) -> None:
    repository, assessment_id, _, package_result, _ = (
        persisted_four_gate_data_readiness_baseline(tmp_path)
    )
    target_step_id = package_result.package.portfolio.items[0].step_id
    service = build_four_gate_m2_service(repository.path)
    run = service.create_run(assessment_id, target_step_id)
    before = _successor_counts(repository.path)

    with pytest.raises(FourGateM2Error, match=match):
        service.submit_supporting_document(
            run.run_id,
            content_bytes=content,
            filename=filename,
            source_label="Declared source",
            submitter=actor(),
        )

    assert _successor_counts(repository.path) == before
    assert service.repository.load_run(run.run_id)["stage"] == (
        FourGateM2RunStage.OPEN.value
    )


def test_ineligible_successor_dcw_does_not_compose_or_write(tmp_path) -> None:
    repository, assessment_id, *_ = persisted_four_gate_baseline(tmp_path)
    before_bytes = repository.path.read_bytes()
    before_counts = _successor_counts(repository.path)

    view = discriminate_decision_continuation(repository.load_workspace(assessment_id))

    assert view.continuation_state is SuccessorContinuationState.DEFERRED_UNAVAILABLE
    assert view.successor_continuation_available is False
    assert _successor_counts(repository.path) == before_counts
    assert repository.path.read_bytes() == before_bytes


@pytest.mark.parametrize("damage", ["mixed", "unknown", "malformed"])
def test_invalid_successor_contracts_fail_before_composition_or_write(
    tmp_path, damage
) -> None:
    repository, assessment_id, *_ = persisted_four_gate_data_readiness_baseline(
        tmp_path
    )
    snapshot = repository.load_workspace(assessment_id)
    package = snapshot.active_artifacts[ArtifactType.DECISION_PACKAGE_RESULT]
    if damage == "mixed":
        replacement = package.model_copy(
            update={"artifact_schema_version": "phase6-v0.1"}
        )
    elif damage == "unknown":
        replacement = package.model_copy(
            update={"artifact_schema_version": "phase6-v99"}
        )
    else:
        replacement = package.model_copy(update={"parent_artifact_id": "wrong-parent"})
    invalid = snapshot.model_copy(
        update={
            "active_artifacts": {
                **snapshot.active_artifacts,
                ArtifactType.DECISION_PACKAGE_RESULT: replacement,
            }
        }
    )
    before_bytes = repository.path.read_bytes()
    before_counts = _successor_counts(repository.path)

    view = discriminate_decision_continuation(invalid)

    assert view.contract_family is DecisionContinuationContractFamily.UNSUPPORTED
    assert view.successor_continuation_available is False
    assert _successor_counts(repository.path) == before_counts
    assert repository.path.read_bytes() == before_bytes


def test_frozen_successor_dcw_guard_is_read_only_and_creates_no_sidecars(
    tmp_path, monkeypatch
) -> None:
    source, *_ = persisted_four_gate_data_readiness_baseline(tmp_path / "source")
    frozen = tmp_path / "evaluation" / "portfolio" / "frozen" / "workspace.db"
    frozen.parent.mkdir(parents=True)
    shutil.copy2(source.path, frozen)
    before_bytes = frozen.read_bytes()
    before_hash = hashlib.sha256(before_bytes).hexdigest()
    before_entries = tuple(sorted(path.name for path in frozen.parent.iterdir()))
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(frozen))

    assert four_gate_m2_continuation_available() is False

    assert frozen.read_bytes() == before_bytes
    assert hashlib.sha256(frozen.read_bytes()).hexdigest() == before_hash
    assert tuple(sorted(path.name for path in frozen.parent.iterdir())) == before_entries
    assert not any(
        path.name.endswith(("-journal", "-wal", "-shm"))
        for path in frozen.parent.iterdir()
    )

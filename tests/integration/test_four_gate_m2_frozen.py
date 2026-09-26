from __future__ import annotations

import hashlib
import shutil

import pytest

from ai_adoption_engine.persistence.four_gate_reassessment import (
    FourGateM2FrozenWorkspaceError,
    SQLiteFourGateReassessmentRepository,
)
from tests.fakes.four_gate_workspace import (
    persisted_four_gate_data_readiness_baseline,
)


def _snapshot(path):
    return {
        "bytes": path.read_bytes(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "entries": tuple(sorted(item.name for item in path.parent.iterdir())),
    }


def test_successor_reassessment_refuses_frozen_workspace_without_file_changes(
    tmp_path,
) -> None:
    repository, *_ = persisted_four_gate_data_readiness_baseline(tmp_path / "source")
    protected = tmp_path / "evaluation" / "portfolio" / "frozen" / "workspace.db"
    protected.parent.mkdir(parents=True)
    shutil.copy2(repository.path, protected)
    before = _snapshot(protected)

    with pytest.raises(FourGateM2FrozenWorkspaceError, match="frozen portfolio"):
        SQLiteFourGateReassessmentRepository(protected)

    assert _snapshot(protected) == before
    assert not any(
        item.name.endswith(("-journal", "-wal", "-shm"))
        for item in protected.parent.iterdir()
    )

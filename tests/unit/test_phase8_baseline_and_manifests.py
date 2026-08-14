from __future__ import annotations

import pytest

from evaluation.harness.baseline import assert_baseline_isolation, select_confirmatory_run
from evaluation.harness.run_manifest import validate_run_manifest


def test_baseline_rejects_policy_or_after_leakage() -> None:
    assert_baseline_isolation({"process": {"steps": []}})
    with pytest.raises(ValueError):
        assert_baseline_isolation({"process": {}, "policy_thresholds": {}})
    with pytest.raises(ValueError):
        assert_baseline_isolation({"process": {}, "after_packet": {}})


def test_run_selection_uses_lowest_valid_index_not_list_order() -> None:
    runs = [
        {"run_index":3,"status":"success","structurally_valid":True,"quality":.99},
        {"run_index":1,"status":"success","structurally_valid":False,"quality":1},
        {"run_index":2,"status":"success","structurally_valid":True,"quality":.1},
    ]
    assert select_confirmatory_run(runs)["run_index"] == 2


def test_manifest_blocks_unauthorized_confirmatory_run() -> None:
    manifest = {
        "schema_id":"phase8-run-manifest.v0.1","run_id":"r","case_id":"c","study_id":"A",
        "cohort":"confirmatory","run_index":1,"status":"success","git_commit":"g",
        "case_manifest_sha256":"h","input_sha256":"h","started_at":"t","completed_at":"t",
        "output_path":"","output_sha256":"h","recommendations_frozen":False,
        "confirmatory_authorized":False,
    }
    with pytest.raises(PermissionError):
        validate_run_manifest(manifest)

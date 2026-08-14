from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import load_json, sha256_file


REQUIRED = {
    "schema_id", "run_id", "case_id", "study_id", "cohort", "run_index", "status",
    "git_commit", "case_manifest_sha256", "input_sha256", "started_at", "completed_at",
    "output_path", "output_sha256", "recommendations_frozen",
}


def validate_run_manifest(manifest: dict[str, Any], *, root: str | Path | None = None) -> None:
    missing = REQUIRED - set(manifest)
    if missing:
        raise ValueError(f"Run manifest missing fields: {sorted(missing)}")
    if manifest["schema_id"] != "phase8-run-manifest.v0.1":
        raise ValueError("Unexpected run-manifest schema")
    if manifest["cohort"] == "confirmatory" and manifest.get("confirmatory_authorized") is not True:
        raise PermissionError("Confirmatory execution is not authorized")
    if root is not None and manifest["output_path"]:
        output = Path(root) / manifest["output_path"]
        if sha256_file(output) != manifest["output_sha256"]:
            raise ValueError("Run output hash mismatch")


def load_and_validate(path: str | Path, *, root: str | Path | None = None) -> dict[str, Any]:
    manifest = load_json(path)
    validate_run_manifest(manifest, root=root)
    return manifest

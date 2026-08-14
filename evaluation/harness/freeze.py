from __future__ import annotations

from pathlib import Path

from .common import load_json, sha256_file


def verify_protocol_freeze(project_root: str | Path) -> None:
    root = Path(project_root)
    manifest = load_json(root / "evaluation" / "protocol" / "freeze_manifest.v0.1.json")
    for item in manifest["files"]:
        if sha256_file(root / item["path"]) != item["sha256"]:
            raise ValueError(f"Frozen Phase 8 protocol file changed: {item['path']}")

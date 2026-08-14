from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .common import load_json, sha256_file


class CaseIntegrityError(ValueError):
    pass


class SealedAfterPacketError(PermissionError):
    pass


@dataclass(frozen=True)
class LoadedBeforePacket:
    manifest: dict[str, Any]
    files: dict[str, bytes]


def _verify_files(case_dir: Path, entries: list[dict[str, str]]) -> dict[str, bytes]:
    loaded: dict[str, bytes] = {}
    for entry in entries:
        relative = entry["path"]
        path = case_dir / relative
        if not path.is_file() or sha256_file(path) != entry["sha256"]:
            raise CaseIntegrityError(f"Hash verification failed: {relative}")
        loaded[relative] = path.read_bytes()
    return loaded


def load_before_packet(case_dir: str | Path) -> LoadedBeforePacket:
    root = Path(case_dir)
    manifest = load_json(root / "manifest.json")
    return LoadedBeforePacket(manifest, _verify_files(root, manifest["before_files"]))


def load_after_packet(
    case_dir: str | Path,
    *,
    recommendations_frozen: bool,
    freeze_record: str | Path | None,
) -> dict[str, bytes]:
    if not recommendations_frozen or freeze_record is None:
        raise SealedAfterPacketError("After packet remains sealed until recommendations are frozen")
    record_path = Path(freeze_record)
    if not record_path.is_file():
        raise SealedAfterPacketError("A persisted recommendation-freeze record is required")
    root = Path(case_dir)
    manifest = load_json(root / "manifest.json")
    record = load_json(record_path)
    if record.get("case_id") != manifest.get("case_id") or not record.get("recommendations_frozen"):
        raise SealedAfterPacketError("Freeze record does not authorize this case")
    return _verify_files(root, manifest["after_files"])


def verify_case_packet(case_dir: str | Path) -> dict[str, Any]:
    root = Path(case_dir)
    manifest = load_json(root / "manifest.json")
    _verify_files(root, manifest["before_files"])
    _verify_files(root, manifest["after_files"])
    return manifest

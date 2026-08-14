from __future__ import annotations

from pathlib import Path

from evaluation.harness.common import sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CASE_ID = "CON-001"
CASE_TITLE = "Assembly conveyor maintenance"
BEFORE_RELATIVE_PATH = Path(
    "evaluation/cases/confirmatory/con-001-bmw-maintenance/before/process_document.txt"
)
BEFORE_PATH = (PROJECT_ROOT / BEFORE_RELATIVE_PATH).resolve()
BEFORE_SHA256 = "0767e1e5dd672cb4a4faae490f97d0b56d7a3156572a446bc5c7487ee2e0fe9d"

EVIDENCE_CATALOG = (
    {
        "evidence_id": "E1",
        "locator": "before/process_document.txt:3-4",
        "text": "Vehicle assembly relies on conveyor systems that move parts and vehicles through production.",
    },
    {
        "evidence_id": "E2",
        "locator": "before/process_document.txt:5-6",
        "text": "Wear or faults in conveyor components can interrupt the line.",
    },
    {
        "evidence_id": "E3",
        "locator": "before/process_document.txt:6-9",
        "text": (
            "Maintenance personnel inspect system condition, identify abnormal behaviour, "
            "diagnose the affected component, and arrange maintenance action so production can continue."
        ),
    },
    {
        "evidence_id": "E4",
        "locator": "before/process_document.txt:9-10",
        "text": (
            "The current-state packet does not disclose volumes, false-alarm rates, "
            "intervention costs, or acceptable operational risk."
        ),
    },
)

ACTION_CUES = (
    {"cue_id": "C1", "text": "move parts and vehicles through production", "evidence_locators": ["E1"]},
    {"cue_id": "C2", "text": "inspect system condition", "evidence_locators": ["E3"]},
    {"cue_id": "C3", "text": "identify abnormal behaviour", "evidence_locators": ["E3"]},
    {"cue_id": "C4", "text": "diagnose the affected component", "evidence_locators": ["E3"]},
    {"cue_id": "C5", "text": "arrange maintenance action", "evidence_locators": ["E3"]},
)


class BeforePacketIntegrityError(ValueError):
    pass


def load_frozen_before() -> str:
    """Load the one allowlisted source after verifying its frozen digest."""
    expected = (PROJECT_ROOT / BEFORE_RELATIVE_PATH).resolve()
    if BEFORE_PATH != expected or not BEFORE_PATH.is_relative_to(PROJECT_ROOT):
        raise BeforePacketIntegrityError("CON-001 before path is outside the allowlist")
    actual = sha256_file(BEFORE_PATH)
    if actual != BEFORE_SHA256:
        raise BeforePacketIntegrityError(
            f"CON-001 before packet hash mismatch: expected {BEFORE_SHA256}, got {actual}"
        )
    return BEFORE_PATH.read_text(encoding="utf-8")

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SUCCESSOR_MODULE = (
    ROOT
    / "src"
    / "ai_adoption_engine"
    / "application"
    / "four_gate_decision_continuation.py"
)
LEGACY_MODULE = (
    ROOT
    / "src"
    / "ai_adoption_engine"
    / "application"
    / "decision_continuation.py"
)
SUCCESSOR_PRESENTATION = (
    ROOT
    / "src"
    / "ai_adoption_engine"
    / "presentation"
    / "four_gate_decision_continuation.py"
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_successor_discriminator_has_no_grw_m2_write_or_engine_dependencies() -> None:
    imports = _imports(SUCCESSOR_MODULE)
    forbidden = (
        "ai_adoption_engine.grw",
        "ai_adoption_engine.decision",
        "ai_adoption_engine.persistence.reassessment",
        "ai_adoption_engine.persistence.sqlite",
        "ai_adoption_engine.extraction.providers",
        "ai_adoption_engine.presentation",
    )
    assert not any(
        name == root or name.startswith(root + ".")
        for name in imports
        for root in forbidden
    )


def test_legacy_dcw_application_does_not_import_the_successor_discriminator() -> None:
    assert (
        "ai_adoption_engine.application.four_gate_decision_continuation"
        not in _imports(LEGACY_MODULE)
    )


def test_successor_dcw_projection_uses_no_legacy_workflow_or_persistence() -> None:
    imports = _imports(SUCCESSOR_PRESENTATION)
    forbidden = (
        "ai_adoption_engine.decision",
        "ai_adoption_engine.persistence",
        "ai_adoption_engine.grw.m2",
        "ai_adoption_engine.workspace.service",
        "ai_adoption_engine.extraction.providers",
    )
    assert not any(
        name == root or name.startswith(root + ".")
        for name in imports
        for root in forbidden
    )

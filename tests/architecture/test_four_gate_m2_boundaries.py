from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "ai_adoption_engine"
SUCCESSOR = SOURCE / "grw" / "four_gate_m2"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_successor_service_uses_only_successor_phase5_and_phase6_routes() -> None:
    imports = _imports(SUCCESSOR / "service.py")
    assert "ai_adoption_engine.application.four_gate_assessment" in imports
    assert "ai_adoption_engine.decision_support.four_gate_service" in imports
    forbidden = (
        "ai_adoption_engine.application.assessment",
        "ai_adoption_engine.decision_support.service",
        "ai_adoption_engine.grw.m2",
        "ai_adoption_engine.persistence.reassessment",
        "ai_adoption_engine.presentation",
        "streamlit",
        "openai",
    )
    assert not any(
        name == root or name.startswith(root + ".")
        for name in imports
        for root in forbidden
    )


def test_successor_repository_has_no_engine_provider_ui_or_legacy_m2_imports() -> None:
    imports = _imports(SOURCE / "persistence" / "four_gate_reassessment.py")
    forbidden = (
        "ai_adoption_engine.application",
        "ai_adoption_engine.decision",
        "ai_adoption_engine.decision_support",
        "ai_adoption_engine.grw.m2",
        "ai_adoption_engine.presentation",
        "ai_adoption_engine.extraction",
        "streamlit",
        "openai",
    )
    assert not any(
        name == root or name.startswith(root + ".")
        for name in imports
        for root in forbidden
    )


def test_legacy_and_default_routes_do_not_import_successor_m2() -> None:
    paths = (
        SOURCE / "grw" / "m2" / "service.py",
        SOURCE / "persistence" / "reassessment.py",
        SOURCE / "application" / "decision_continuation.py",
        SOURCE / "workspace" / "service.py",
        SOURCE / "cli.py",
        ROOT / "streamlit_app.py",
    )
    for path in paths:
        assert not any(
            name == "ai_adoption_engine.grw.four_gate_m2"
            or name.startswith("ai_adoption_engine.grw.four_gate_m2.")
            for name in _imports(path)
        )


def test_dcw_discriminator_remains_read_only_and_service_free() -> None:
    path = SOURCE / "application" / "four_gate_decision_continuation.py"
    imports = _imports(path)
    forbidden = (
        "ai_adoption_engine.grw",
        "ai_adoption_engine.persistence",
        "ai_adoption_engine.presentation",
        "streamlit",
    )
    assert not any(
        name == root or name.startswith(root + ".")
        for name in imports
        for root in forbidden
    )
    assert SCHEMA_FAMILY not in path.read_text(encoding="utf-8")


def test_successor_dcw_activation_never_composes_legacy_m1_or_m2() -> None:
    paths = (
        SOURCE / "application" / "four_gate_reassessment_composition.py",
        SOURCE / "presentation" / "four_gate_decision_continuation.py",
    )
    forbidden = (
        "ai_adoption_engine.grw.m1",
        "ai_adoption_engine.grw.m2",
        "ai_adoption_engine.persistence.reassessment",
        "ai_adoption_engine.application.decision_continuation",
        "ai_adoption_engine.application.assessment",
        "ai_adoption_engine.decision_support.service",
    )
    for path in paths:
        imports = _imports(path)
        assert not any(
            name == root or name.startswith(root + ".")
            for name in imports
            for root in forbidden
        )


def test_successor_composition_pins_exact_policy_and_has_no_default_switch() -> None:
    path = SOURCE / "application" / "four_gate_reassessment_composition.py"
    source = path.read_text(encoding="utf-8")
    imports = _imports(path)

    assert "decision_policy.v0.3.json" in source
    assert "FourGateM2Service" in source
    assert "ai_adoption_engine.grw.four_gate_m2.service" in imports
    assert "decision_policy.v0.2" not in source
    assert "DEFAULT_DATABASE_PATH" not in source


SCHEMA_FAMILY = "grw-m2-four-gate-v0.1"

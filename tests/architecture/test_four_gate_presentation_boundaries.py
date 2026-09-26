import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PRESENTATION = ROOT / "src" / "ai_adoption_engine" / "presentation"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_successor_projection_has_no_engine_policy_gate_or_persistence_imports() -> None:
    paths = (
        PRESENTATION / "contracts.py",
        PRESENTATION / "four_gate_narrative.py",
        PRESENTATION / "four_gate_report_view.py",
        PRESENTATION / "four_gate_ui.py",
    )
    forbidden = (
        "ai_adoption_engine.decision",
        "ai_adoption_engine.persistence",
        "ai_adoption_engine.workspace",
        "ai_adoption_engine.application",
        "ai_adoption_engine.extraction",
        "openai",
    )
    for path in paths:
        imports = _imports(path)
        assert not any(
            imported == prefix or imported.startswith(f"{prefix}.")
            for imported in imports
            for prefix in forbidden
        )


def test_successor_ui_contains_no_generation_or_write_calls() -> None:
    source = (PRESENTATION / "four_gate_ui.py").read_text(encoding="utf-8")
    for forbidden in (
        "workspace_service",
        "save_artifact",
        "generate_package",
        ".assess(",
        "begin_operation",
    ):
        assert forbidden not in source


def test_default_composition_and_cli_do_not_import_successor_projection() -> None:
    for path in (
        ROOT / "src" / "ai_adoption_engine" / "workspace" / "composition.py",
        ROOT / "src" / "ai_adoption_engine" / "cli.py",
    ):
        imports = _imports(path)
        assert "ai_adoption_engine.presentation.four_gate_ui" not in imports
        assert "ai_adoption_engine.presentation.four_gate_narrative" not in imports

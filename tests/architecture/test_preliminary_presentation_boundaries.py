from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "ai_adoption_engine"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_preliminary_result_projection_is_pure_and_streamlit_disconnected() -> None:
    module = SOURCE / "presentation" / "preliminary_result.py"
    imports = _imports(module)

    assert "streamlit" not in imports
    assert not any(name.startswith("ai_adoption_engine.persistence") for name in imports)
    assert not any(name.startswith("ai_adoption_engine.workspace") for name in imports)
    assert not any(name.startswith("ai_adoption_engine.application") for name in imports)


def test_selector_and_defaults_do_not_import_the_result_projector() -> None:
    for path in (
        ROOT / "streamlit_app.py",
        SOURCE / "presentation" / "preliminary_ui.py",
    ):
        imports = _imports(path)
        assert "ai_adoption_engine.presentation.preliminary_result" not in imports


def test_process_journey_imports_projector_without_importing_an_evaluator() -> None:
    path = SOURCE / "presentation" / "pages" / "process_journey.py"
    imports = _imports(path)
    assert "ai_adoption_engine.presentation.preliminary_result" in imports
    assert "ai_adoption_engine.preliminary.evaluator" not in imports
    assert "ai_adoption_engine.preliminary.evaluator_v0_2" not in imports


def test_execution_persistence_and_strict_routes_do_not_depend_on_presentation() -> None:
    paths = (
        SOURCE / "preliminary" / "run.py",
        SOURCE / "preliminary" / "journey.py",
        SOURCE / "persistence" / "preliminary.py",
        SOURCE / "engine.py",
        SOURCE / "application" / "assessment.py",
        SOURCE / "cli.py",
    )
    for path in paths:
        if not path.exists():
            continue
        assert "ai_adoption_engine.presentation.preliminary_result" not in _imports(path)

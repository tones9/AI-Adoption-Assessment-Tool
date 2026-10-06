from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "ai_adoption_engine"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_slice_five_derivation_and_presentation_are_pure_and_default_off() -> None:
    modules = (
        SOURCE / "formal" / "guidance.py",
        SOURCE / "presentation" / "formal_assessment_result.py",
    )
    forbidden_prefixes = (
        "streamlit",
        "ai_adoption_engine.persistence",
        "ai_adoption_engine.decision.four_gate_engine",
        "ai_adoption_engine.formal.input_adapter",
        "ai_adoption_engine.formal.run_service",
    )
    for module in modules:
        imports = _imports(module)
        assert not any(
            name == prefix or name.startswith(f"{prefix}.")
            for name in imports
            for prefix in forbidden_prefixes
        )

    for path in (
        ROOT / "streamlit_app.py",
        SOURCE / "presentation" / "preliminary_ui.py",
        SOURCE / "cli.py",
        SOURCE / "application" / "assessment.py",
    ):
        if path.exists():
            assert "ai_adoption_engine.presentation.formal_assessment_result" not in _imports(path)
            assert "ai_adoption_engine.formal.guidance" not in _imports(path)

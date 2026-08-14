from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_production_does_not_import_evaluation() -> None:
    violations = []
    for path in (ROOT / "src" / "ai_adoption_engine").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(alias.name.startswith("evaluation") for alias in node.names):
                violations.append(path)
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("evaluation"):
                violations.append(path)
    assert not violations


def test_confirmatory_execution_is_disabled() -> None:
    import json

    config = json.loads((ROOT / "evaluation" / "config" / "evaluation.v0.1.json").read_text())
    assert config["confirmatory_runs_authorized"] is False
    assert config["external_human_evaluation_authorized"] is False

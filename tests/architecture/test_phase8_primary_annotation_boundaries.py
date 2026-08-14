from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "evaluation" / "primary_annotation"
FORBIDDEN_IMPORT_PREFIXES = (
    "openai",
    "ai_adoption_engine.extraction",
    "ai_adoption_engine.decision",
    "ai_adoption_engine.application",
    "ai_adoption_engine.decision_support",
    "evaluation.harness.baseline",
)


def test_primary_annotation_package_has_no_provider_engine_or_baseline_imports() -> None:
    violations: list[tuple[Path, str]] = []
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.append(node.module or "")
            for name in names:
                if name.startswith(FORBIDDEN_IMPORT_PREFIXES):
                    violations.append((path, name))
    assert not violations


def test_primary_annotation_source_contains_no_after_packet_path() -> None:
    for path in PACKAGE.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "con-001-bmw-maintenance/after" not in source
        assert "after/reference_evidence.md" not in source

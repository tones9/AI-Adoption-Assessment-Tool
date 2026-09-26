from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "ai_adoption_engine"
COHORT = ROOT / "evaluation" / "four_gate_cohorts"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_production_code_never_imports_successor_cohort() -> None:
    prohibited = (
        "evaluation.four_gate_cohorts",
        "evaluation/four_gate_cohorts",
        "four_gate_evaluation_cohort",
    )
    for path in SOURCE.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not any(token in text for token in prohibited), path


def test_cohort_harness_uses_explicit_successor_routes_only() -> None:
    imports = _imports(COHORT / "harness.py")
    assert "ai_adoption_engine.application.four_gate_assessment" in imports
    assert "ai_adoption_engine.decision_support.four_gate_service" in imports
    forbidden = (
        "ai_adoption_engine.application.assessment",
        "ai_adoption_engine.decision.engine",
        "ai_adoption_engine.decision.policy",
        "ai_adoption_engine.decision_support.service",
        "ai_adoption_engine.persistence",
        "ai_adoption_engine.presentation",
        "ai_adoption_engine.extraction.providers.openai",
        "streamlit",
        "openai",
    )
    assert not any(
        name == root or name.startswith(root + ".")
        for name in imports
        for root in forbidden
    )


def test_cohort_files_are_separate_from_phase8_and_visibly_development_only() -> None:
    assert COHORT.is_dir()
    assert not str(COHORT.relative_to(ROOT)).startswith("evaluation/portfolio/")
    protocol = (COHORT / "protocol.md").read_text(encoding="utf-8")
    assert "four-gate-evaluation-cohort.v0.1" in protocol
    assert "excluded from real-world" in protocol
    assert "No governed real-world cases" in protocol
    for path in (COHORT / "development_fixtures").glob("*.txt"):
        assert path.is_file()


def test_legacy_evaluation_harness_does_not_import_successor_cohort() -> None:
    for path in (ROOT / "evaluation" / "harness").glob("*.py"):
        assert not any(
            name == "evaluation.four_gate_cohorts"
            or name.startswith("evaluation.four_gate_cohorts.")
            for name in _imports(path)
        )

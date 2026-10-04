from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "ai_adoption_engine"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_slice6_activation_remains_out_of_application_and_cli_defaults() -> None:
    for path in (
        ROOT / "streamlit_app.py",
        SOURCE / "cli.py",
        SOURCE / "workspace/composition.py",
        SOURCE / "workspace/service.py",
        SOURCE / "preliminary/composition.py",
    ):
        source = path.read_text(encoding="utf-8")
        assert "AI_ADOPTION_ENGINE_SUPPORTING_EVIDENCE_UI" not in source
        assert "build_supporting_evidence_service_bundle" not in source


def test_slice6_ui_composition_does_not_invoke_strict_or_preliminary_evaluators() -> None:
    imports = set()
    for path in (
        SOURCE / "supporting_evidence/composition.py",
        SOURCE / "presentation/supporting_evidence_ui.py",
        SOURCE / "presentation/supporting_evidence_workflow.py",
    ):
        imports.update(_imports(path))
    forbidden = (
        "ai_adoption_engine.engine",
        "ai_adoption_engine.application.assessment",
        "ai_adoption_engine.preliminary.evaluator",
        "ai_adoption_engine.preliminary.evaluator_v0_2",
        "ai_adoption_engine.decision_support",
    )
    assert not any(
        imported == item or imported.startswith(f"{item}.")
        for imported in imports
        for item in forbidden
    )


def test_slice6_reuses_migration_seven_and_frozen_contracts() -> None:
    migrations = (SOURCE / "persistence/preliminary_migrations.py").read_text(
        encoding="utf-8"
    )
    models = (SOURCE / "models/formal_evidence.py").read_text(encoding="utf-8")
    assert "SUPPORTING_EVIDENCE_MIGRATION_8" not in migrations
    assert "preliminary-formal-evidence.v0.2" not in models
    assert "supporting-evidence-extraction.v0.2" not in models


def test_process_journey_activates_only_the_presentation_workflow() -> None:
    imports = _imports(SOURCE / "presentation/pages/process_journey.py")
    assert "ai_adoption_engine.presentation.supporting_evidence_ui" in imports
    assert "ai_adoption_engine.presentation.supporting_evidence_workflow" in imports
    assert "ai_adoption_engine.persistence.formal_evidence" not in imports
    assert "ai_adoption_engine.supporting_evidence.conversion" not in imports

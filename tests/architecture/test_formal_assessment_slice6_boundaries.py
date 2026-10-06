from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "ai_adoption_engine"
SLICE6 = (
    SOURCE / "formal/composition.py",
    SOURCE / "presentation/formal_assessment_ui.py",
    SOURCE / "presentation/formal_assessment_workflow.py",
)


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
        SOURCE / "__main__.py",
        SOURCE / "workspace/composition.py",
        SOURCE / "workspace/service.py",
        SOURCE / "preliminary/composition.py",
        SOURCE / "supporting_evidence/composition.py",
    ):
        source = path.read_text(encoding="utf-8")
        assert "AI_ADOPTION_ENGINE_FORMAL_ASSESSMENT_UI" not in source
        assert "build_formal_assessment_service_bundle" not in source
        assert "formal_assessment_workflow" not in source


def test_only_the_process_journey_page_activates_the_formal_workflow() -> None:
    importers = {
        path.relative_to(SOURCE).as_posix()
        for path in SOURCE.rglob("*.py")
        if "ai_adoption_engine.presentation.formal_assessment_workflow" in _imports(path)
    }
    assert importers == {"presentation/pages/process_journey.py"}
    composition_importers = {
        path.relative_to(SOURCE).as_posix()
        for path in SOURCE.rglob("*.py")
        if "ai_adoption_engine.formal.composition" in _imports(path)
    }
    assert composition_importers == {"presentation/formal_assessment_ui.py"}


def test_slice6_never_reaches_legacy_engines_approval_or_decision_packages() -> None:
    imports: set[str] = set()
    for path in SLICE6:
        imports.update(_imports(path))
    forbidden = (
        "ai_adoption_engine.engine",
        "ai_adoption_engine.application.assessment",
        "ai_adoption_engine.decision_support",
        "ai_adoption_engine.decision.engine",
        "ai_adoption_engine.decision.gates",
        "ai_adoption_engine.preliminary.evaluator",
        "ai_adoption_engine.preliminary.evaluator_v0_2",
        "ai_adoption_engine.supporting_evidence.openai",
        "ai_adoption_engine.supporting_evidence.extraction",
        "openai",
        "anthropic",
        "requests",
        "httpx",
    )
    assert not any(
        imported == item or imported.startswith(f"{item}.")
        for imported in imports
        for item in forbidden
    )
    workflow = (SOURCE / "presentation/formal_assessment_workflow.py").read_text(encoding="utf-8")
    for token in (
        "FourGateAssessmentEngine",
        "load_four_gate_policy",
        ".project(",
        "_build_projection",
        "DecisionPackage",
    ):
        assert token not in workflow


def test_slice6_preserves_migrations_policy_and_adapter_identities() -> None:
    migration = (SOURCE / "persistence/formal_assessment_migration.py").read_text(encoding="utf-8")
    assert "MIGRATION_9" not in migration and "migration 9" not in migration.lower()
    from ai_adoption_engine.formal.input_adapter import formal_assessment_compatibility_identity
    from ai_adoption_engine.models.formal_assessment_adapter import (
        FORMAL_FOUR_GATE_INPUT_ADAPTER_RULES,
    )

    assert FORMAL_FOUR_GATE_INPUT_ADAPTER_RULES.rules_fingerprint == (
        "0472d8517f0a6176ac56ed5599b11c7b22d94092a8a85083551837fd54ec8b5d"
    )
    identity = formal_assessment_compatibility_identity()
    assert identity.policy_id == "decision_policy.v0.3"
    assert identity.engine_id == "four-gate-assessment-engine.v0.1"
    assert identity.output_contract == "phase1-v0.4"
    assert identity.readiness_contract == "formal-evidence-readiness.v0.1"

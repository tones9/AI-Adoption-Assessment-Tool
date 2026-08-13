import ast
from pathlib import Path

from ai_adoption_engine.decision.engine import AssessmentEngine
from ai_adoption_engine.decision_support import DecisionSupportPackageService
from ai_adoption_engine.extraction.providers.openai import OpenAIExtractionProvider
from ai_adoption_engine.models.decision_support import DecisionPackageSuccess
from tests.fakes.decision_support import sample_integrated_assessment


def _imports_under(root: Path) -> set[str]:
    imports = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
    return imports


def test_phase6_has_no_engine_rules_provider_ui_or_persistence_imports() -> None:
    root = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "ai_adoption_engine"
        / "decision_support"
    )
    imports = _imports_under(root)
    forbidden = (
        "ai_adoption_engine.decision.engine",
        "ai_adoption_engine.decision.capabilities",
        "ai_adoption_engine.decision.gates",
        "ai_adoption_engine.decision.scoring",
        "ai_adoption_engine.extraction.providers",
        "openai",
        "sqlite3",
        "streamlit",
    )
    assert not any(
        imported == item or imported.startswith(f"{item}.")
        for imported in imports
        for item in forbidden
    )


def test_earlier_phases_do_not_depend_on_phase6() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "ai_adoption_engine"
    for package in ("decision", "ingestion", "extraction", "review", "application"):
        imports = _imports_under(root / package)
        assert not any(
            item == "ai_adoption_engine.decision_support"
            or item.startswith("ai_adoption_engine.decision_support.")
            for item in imports
        )


def test_generation_never_invokes_engine_or_openai(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Phase 6 invoked a forbidden runtime dependency")

    integrated = sample_integrated_assessment()
    monkeypatch.setattr(AssessmentEngine, "assess", fail_if_called)
    monkeypatch.setattr(OpenAIExtractionProvider, "extract_chunk", fail_if_called)
    result = DecisionSupportPackageService().generate(integrated)
    assert isinstance(result, DecisionPackageSuccess)


def test_phase6_source_contains_no_threshold_or_weight_configuration() -> None:
    root = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "ai_adoption_engine"
        / "decision_support"
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
    assert "minimum_ai_capability_fit" not in source
    assert "minimum_business_value" not in source
    assert "ScoringCriterion" not in source

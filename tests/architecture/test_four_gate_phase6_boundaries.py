import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "src" / "ai_adoption_engine"
SUCCESSOR_FILES = [
    SOURCE_ROOT / "models" / "four_gate_decision_support.py",
    SOURCE_ROOT / "decision_support" / "four_gate_service.py",
]


def _imports_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_successor_phase6_has_no_engine_provider_persistence_or_view_imports() -> None:
    imports = set().union(*(_imports_in(path) for path in SUCCESSOR_FILES))
    forbidden = (
        "ai_adoption_engine.decision.four_gate_engine",
        "ai_adoption_engine.decision.four_gate_gates",
        "ai_adoption_engine.decision.four_gate_policy",
        "ai_adoption_engine.decision.engine",
        "ai_adoption_engine.decision.gates",
        "ai_adoption_engine.decision.scoring",
        "ai_adoption_engine.extraction",
        "ai_adoption_engine.persistence",
        "ai_adoption_engine.decision_support.report",
        "ai_adoption_engine.presentation",
        "ai_adoption_engine.reporting",
        "ai_adoption_engine.ui",
        "openai",
        "sqlite3",
        "streamlit",
    )
    assert not any(
        imported == item or imported.startswith(f"{item}.")
        for imported in imports
        for item in forbidden
    )


def test_successor_phase6_contains_no_threshold_weight_or_provider_logic() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in SUCCESSOR_FILES)
    forbidden_fragments = (
        "minimum_ai_capability_fit",
        "minimum_business_value",
        "maximum_implementation_complexity_for_readiness",
        "ScoringCriterion",
        "provider.",
        ".assess(",
    )
    assert not any(fragment in source for fragment in forbidden_fragments)


def test_legacy_phase6_and_default_routes_do_not_import_successor_phase6() -> None:
    legacy_files = [
        *(
            path
            for path in (SOURCE_ROOT / "decision_support").glob("*.py")
            if path.name != "four_gate_service.py"
        ),
        SOURCE_ROOT / "models" / "decision_support.py",
        SOURCE_ROOT / "cli.py",
        ROOT / "streamlit_app.py",
    ]
    successor_modules = {
        "ai_adoption_engine.decision_support.four_gate_service",
        "ai_adoption_engine.models.four_gate_decision_support",
    }
    for path in legacy_files:
        assert _imports_in(path).isdisjoint(successor_modules), path


def test_successor_phase6_is_not_imported_by_earlier_phase_packages() -> None:
    for package_name in ("decision", "ingestion", "extraction", "review", "application"):
        package = SOURCE_ROOT / package_name
        for path in package.rglob("*.py"):
            if path.name == "four_gate_decision_continuation.py":
                # DCW is a downstream read-only package consumer, not an
                # earlier assessment phase or a default generation route.
                continue
            imports = _imports_in(path)
            assert (
                "ai_adoption_engine.decision_support.four_gate_service"
                not in imports
            ), path
            assert (
                "ai_adoption_engine.models.four_gate_decision_support"
                not in imports
            ), path

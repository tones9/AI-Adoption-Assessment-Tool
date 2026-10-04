import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "src/ai_adoption_engine/models/formal_evidence.py"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_formal_evidence_contracts_are_provider_and_execution_independent() -> None:
    imported = _imports(MODEL_PATH)
    forbidden_fragments = {
        ".providers",
        ".persistence",
        "streamlit",
        "four_gate_engine",
        "preliminary_evaluator",
        "preliminary_assessment_v0_2",
    }
    assert not {
        module
        for module in imported
        if any(fragment in module for fragment in forbidden_fragments)
    }


def test_formal_evidence_contracts_are_not_activated_by_runtime_boundaries() -> None:
    runtime_paths = [
        ROOT / "streamlit_app.py",
        ROOT / "src/ai_adoption_engine/presentation/preliminary_ui.py",
        ROOT / "src/ai_adoption_engine/persistence/preliminary_serialization.py",
        ROOT / "src/ai_adoption_engine/preliminary/__init__.py",
        ROOT / "src/ai_adoption_engine/preliminary/formal.py",
        ROOT / "src/ai_adoption_engine/preliminary/journey.py",
        ROOT / "src/ai_adoption_engine/preliminary/run.py",
    ]
    for path in runtime_paths:
        if path.exists():
            assert "models.formal_evidence" not in path.read_text(encoding="utf-8")


def test_slice_one_adds_no_persistence_or_service_module() -> None:
    source = MODEL_PATH.read_text(encoding="utf-8")
    forbidden_symbols = {
        "sqlite3",
        "CREATE TABLE",
        "ALTER TABLE",
        "requests.",
        "httpx.",
        "streamlit.",
    }
    assert not {symbol for symbol in forbidden_symbols if symbol in source}

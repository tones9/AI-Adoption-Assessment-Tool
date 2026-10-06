import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "src/ai_adoption_engine/models/formal_assessment.py"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_formal_assessment_contracts_are_execution_and_persistence_independent() -> None:
    imported = _imports(MODEL_PATH)
    forbidden_fragments = {
        ".application",
        ".decision.four_gate_engine",
        ".persistence",
        ".presentation",
        ".providers",
        "streamlit",
    }
    assert not {
        module
        for module in imported
        if any(fragment in module for fragment in forbidden_fragments)
    }


def test_slice_one_adds_no_runtime_activation_or_storage_artifacts() -> None:
    source = MODEL_PATH.read_text(encoding="utf-8")
    forbidden_symbols = {
        "sqlite3",
        "CREATE TABLE",
        "ALTER TABLE",
        "requests.",
        "httpx.",
        "streamlit.",
        "DecisionPackage",
        "FormalApproval",
    }
    assert not {symbol for symbol in forbidden_symbols if symbol in source}


def test_runtime_boundaries_do_not_import_formal_assessment_slice_one() -> None:
    runtime_paths = [
        ROOT / "streamlit_app.py",
        ROOT / "src/ai_adoption_engine/persistence/preliminary_serialization.py",
        ROOT / "src/ai_adoption_engine/preliminary/formal.py",
        ROOT / "src/ai_adoption_engine/application/four_gate_assessment.py",
    ]
    for path in runtime_paths:
        assert "models.formal_assessment" not in path.read_text(encoding="utf-8")


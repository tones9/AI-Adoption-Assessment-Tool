import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = ROOT / "src/ai_adoption_engine/formal/input_adapter.py"
MODEL_PATH = ROOT / "src/ai_adoption_engine/models/formal_assessment_adapter.py"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_adapter_has_no_persistence_ui_provider_or_engine_dependency() -> None:
    imports = _imports(ADAPTER_PATH) | _imports(MODEL_PATH)
    forbidden = {
        ".persistence",
        ".presentation",
        ".providers",
        "streamlit",
        "four_gate_engine",
        "decision_support",
    }
    assert not {
        module for module in imports if any(fragment in module for fragment in forbidden)
    }


def test_adapter_contains_no_runtime_activation_or_storage_logic() -> None:
    source = ADAPTER_PATH.read_text(encoding="utf-8")
    forbidden = {
        "sqlite3",
        "CREATE TABLE",
        "ALTER TABLE",
        "requests.",
        "httpx.",
        "streamlit.",
        "DecisionPackage",
        "FormalApproval",
    }
    assert not {item for item in forbidden if item in source}


def test_adapter_is_not_imported_by_runtime_routes() -> None:
    paths = [
        ROOT / "streamlit_app.py",
        ROOT / "src/ai_adoption_engine/application/four_gate_assessment.py",
        ROOT / "src/ai_adoption_engine/preliminary/formal.py",
        ROOT / "src/ai_adoption_engine/persistence/preliminary_serialization.py",
    ]
    for path in paths:
        assert "formal.input_adapter" not in path.read_text(encoding="utf-8")


import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src/ai_adoption_engine"
SERVICE = SOURCE / "formal/run_service.py"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_run_service_has_only_explicit_formal_orchestration_dependencies() -> None:
    imports = _imports(SERVICE)
    forbidden = (
        "ai_adoption_engine.application",
        "ai_adoption_engine.presentation",
        "ai_adoption_engine.providers",
        "ai_adoption_engine.preliminary",
        "ai_adoption_engine.decision_support",
        "ai_adoption_engine.review.approval",
        "streamlit",
        "requests",
        "httpx",
    )
    assert not any(
        imported == item or imported.startswith(f"{item}.")
        for imported in imports
        for item in forbidden
    )


def test_run_service_has_no_ui_network_approval_or_decision_package_behavior() -> None:
    source = SERVICE.read_text(encoding="utf-8")
    forbidden = (
        "streamlit",
        "requests.",
        "httpx.",
        "DecisionPackage",
        "FormalApproval",
        "APPROVE IMPLEMENTATION",
        "openai",
    )
    assert not {item for item in forbidden if item in source}


def test_run_service_is_not_activated_by_existing_runtime_or_legacy_routes() -> None:
    paths = (
        ROOT / "streamlit_app.py",
        SOURCE / "cli.py",
        SOURCE / "workspace/composition.py",
        SOURCE / "workspace/service.py",
        SOURCE / "preliminary/composition.py",
        SOURCE / "preliminary/formal.py",
        SOURCE / "preliminary/journey.py",
        SOURCE / "preliminary/run.py",
        SOURCE / "application/four_gate_assessment.py",
    )
    for path in paths:
        if path.exists():
            source = path.read_text(encoding="utf-8")
            assert "formal.run_service" not in source
            assert "FormalAssessmentRunService" not in source

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_p2_journey_projection_has_no_decision_persistence_or_lifecycle_imports() -> None:
    path = ROOT / "src" / "ai_adoption_engine" / "presentation" / "review_journey.py"
    imports = _imports(path)
    forbidden = (
        "ai_adoption_engine.application",
        "ai_adoption_engine.decision",
        "ai_adoption_engine.decision_support",
        "ai_adoption_engine.grw",
        "ai_adoption_engine.persistence",
        "ai_adoption_engine.workspace",
        "ai_adoption_engine.review.service",
        "sqlite3",
        "streamlit",
    )
    assert not any(
        item == forbidden_item or item.startswith(f"{forbidden_item}.")
        for item in imports
        for forbidden_item in forbidden
    )


def test_phase4_guard_is_first_statement_of_each_existing_write_boundary() -> None:
    path = ROOT / "src" / "ai_adoption_engine" / "workspace" / "service.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    workspace = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "AssessmentWorkspaceService"
    )
    for name in ("start_review", "save_review", "approve", "reset_to_review"):
        method = next(
            node for node in workspace.body if isinstance(node, ast.FunctionDef) and node.name == name
        )
        first = method.body[0]
        assert isinstance(first, ast.Expr)
        assert isinstance(first.value, ast.Call)
        assert isinstance(first.value.func, ast.Attribute)
        assert first.value.func.attr == "_assert_phase4_write_target_allowed"


def test_p2_does_not_add_review_persistence_or_direct_downstream_actions() -> None:
    review_page = (
        ROOT / "src" / "ai_adoption_engine" / "presentation" / "pages" / "review.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        ".assess(",
        ".generate_package(",
        ".submit_grw_",
        ".review_grw_",
        "m2_reassessment_service",
        "SQLite",
        "reset_to_review(",
    ):
        assert forbidden not in review_page
    assert "build_review_journey" in review_page
    assert "workspace_service().save_review" in review_page
    assert "workspace_service().approve" in review_page


def test_protected_p2_routes_stop_before_workspace_hydration_or_composition() -> None:
    for page_name in ("review.py", "source.py"):
        source = (
            ROOT / "src" / "ai_adoption_engine" / "presentation" / "pages" / page_name
        ).read_text(encoding="utf-8")
        assert source.index("frozen_evaluation_workspace_selected()") < source.index(
            "snapshot = hydrate_workspace()"
        )

    entrypoint = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    assert entrypoint.index("protected_p2_page =") < entrypoint.index(
        "snapshot = None if protected_p2_page else hydrate_workspace()"
    )

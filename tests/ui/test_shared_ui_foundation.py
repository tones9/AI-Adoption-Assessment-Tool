"""Regression coverage for the shared Portfolio V1 presentation foundation."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ai_adoption_engine.presentation.theme import PRODUCT_BYLINE, PRODUCT_NAME


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("module", "title"),
    [
        ("decision_continuation", "Decision continuation"),
        ("gap_resolution", "Add preliminary context"),
    ],
)
def test_guarded_continuation_pages_render_h1_before_guard(
    module: str, title: str
) -> None:
    app = AppTest.from_string(
        f"from ai_adoption_engine.presentation.pages.{module} import render\nrender()",
        default_timeout=10,
    ).run()

    assert not app.exception
    assert [element.type for element in app.main.children.values()] == [
        "title",
        "flex_container",
    ]
    assert app.title[0].value == title
    assert "Create or open an assessment first." in app.info[0].value


def test_new_workspace_has_source_current_and_no_completed_stage() -> None:
    app = AppTest.from_string(
        "from ai_adoption_engine.presentation.components.status import render_progress\n"
        "from ai_adoption_engine.workspace.models import WorkflowStage\n"
        "render_progress(WorkflowStage.NEW)"
    ).run()

    assert not app.exception
    progress = app.markdown[0].value
    assert progress.count("aae-stage-current") == 1
    assert "aae-stage-done" not in progress
    assert 'aae-stage-current"><span class="aae-stage-mark">→</span>' in progress
    assert '<span class="aae-stage-label">Source</span>' in progress


def test_product_branding_is_rendered_from_the_shared_identity() -> None:
    app = AppTest.from_string(
        "from ai_adoption_engine.presentation.components.shell import render_brand\n"
        "render_brand()"
    ).run()

    assert not app.exception
    rendered = "\n".join(element.value for element in app.markdown)
    assert PRODUCT_NAME == "AI Adoption Assessment Tool"
    assert PRODUCT_BYLINE == "Conceptualised and shipped by Antony Vishal."
    assert PRODUCT_NAME in rendered
    assert PRODUCT_BYLINE in rendered
    assert "AI Project Memory" not in rendered


def test_entrypoint_uses_shared_product_identity_for_browser_title() -> None:
    tree = ast.parse((ROOT / "streamlit_app.py").read_text(encoding="utf-8"))
    page_config = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "set_page_config"
    )
    page_title = next(
        keyword.value
        for keyword in page_config.keywords
        if keyword.arg == "page_title"
    )

    assert isinstance(page_title, ast.Name)
    assert page_title.id == "PRODUCT_NAME"


def test_registered_navigation_keeps_five_primary_and_three_optional_routes() -> None:
    tree = ast.parse((ROOT / "streamlit_app.py").read_text(encoding="utf-8"))
    groups: dict[str, list[tuple[str, str, str]]] = {}

    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id not in {
            "main_journey",
            "continuation",
        }:
            continue
        assert isinstance(node.value, ast.List)
        routes = []
        for item in node.value.elts:
            assert isinstance(item, ast.Call)
            assert isinstance(item.func, ast.Attribute)
            assert item.func.attr == "Page"
            destination = ast.unparse(item.args[0])
            keywords = {
                keyword.arg: ast.literal_eval(keyword.value)
                for keyword in item.keywords
            }
            routes.append((destination, keywords["title"], keywords["url_path"]))
        groups[target.id] = routes

    assert groups == {
        "main_journey": [
            ("assessments.render", "Assessments", "assessments"),
            ("source.render", "Source & Extraction", "source"),
            ("review.render", "Validate process", "review"),
            ("results.render", "Assessment Results", "results"),
            ("decision_package.render", "Decision Package", "decision-package"),
        ],
        "continuation": [
            (
                "decision_continuation.render",
                "Decision continuation",
                "decision-continuation",
            ),
            ("gap_resolution.render", "Gap resolution", "gap-resolution"),
            ("reassessment.render", "Reassessment", "reassessment"),
        ],
    }


def test_entrypoint_uses_streamlits_responsive_sidebar_default() -> None:
    entrypoint = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    assert 'initial_sidebar_state="auto"' in entrypoint

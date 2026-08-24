"""Choosing between the two bundled demo fixtures on the Source screen.

The selection is deliberately small: one radio of bundled documents inside the
existing offline-demo input, and the same synthetic label on both. These tests
pin the choice a demo user actually has, and the refusal that still applies to
any other document.
"""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.workspace.demo_fixtures import (
    DECISION_VARIETY,
    DEMO_FIXTURES,
    EVIDENCE_GAP,
    SYNTHETIC_LABEL,
)
from ai_adoption_engine.workspace.models import ExecutionMode


def _source_page(tmp_path, monkeypatch) -> AppTest:
    database = tmp_path / "source.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(database))
    repository = SQLiteAssessmentRepository(database)
    assessment = repository.create_assessment("Demo", ExecutionMode.OFFLINE_DEMO)
    return AppTest.from_string(
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment.assessment_id!r}\n"
        "from ai_adoption_engine.presentation.pages.source import render\n"
        "render()\n",
        default_timeout=60,
    ).run()


def _rendered(app) -> str:
    return "\n".join(
        str(item.value)
        for kind in ("title", "subheader", "markdown", "caption", "info", "warning", "text")
        for item in app.get(kind)
    )


def test_both_bundled_fixtures_are_offered_by_name(tmp_path, monkeypatch) -> None:
    app = _source_page(tmp_path, monkeypatch)
    assert not app.exception
    choice = app.radio(key="demo-fixture-choice")
    # The radio renders each fixture by its title, in registry order.
    assert list(choice.options) == [fixture.title for fixture in DEMO_FIXTURES]
    assert EVIDENCE_GAP.title in choice.options
    assert DECISION_VARIETY.title in choice.options
    rendered = _rendered(app)
    # The default selection is the original conservative fixture, so the
    # existing demo path is unchanged for anyone who does not choose.
    assert choice.value.key == EVIDENCE_GAP.key
    assert SYNTHETIC_LABEL in rendered
    assert EVIDENCE_GAP.summary in rendered


def test_choosing_the_variety_fixture_previews_that_document(
    tmp_path, monkeypatch
) -> None:
    app = _source_page(tmp_path, monkeypatch)
    app = app.radio(key="demo-fixture-choice").set_value(DECISION_VARIETY).run()
    assert not app.exception
    rendered = _rendered(app)
    assert DECISION_VARIETY.summary in rendered
    assert SYNTHETIC_LABEL in rendered
    preview = app.text_area[0].value
    assert preview == DECISION_VARIETY.text()
    assert "Synthetic Field Service Request Handling" in preview


def test_ingesting_the_variety_fixture_enables_scripted_extraction(
    tmp_path, monkeypatch
) -> None:
    app = _source_page(tmp_path, monkeypatch)
    app = app.radio(key="demo-fixture-choice").set_value(DECISION_VARIETY).run()
    app = next(
        item for item in app.button if item.label == "Ingest document"
    ).click().run()
    assert not app.exception
    rendered = _rendered(app)
    assert DECISION_VARIETY.title in rendered
    assert SYNTHETIC_LABEL in rendered
    assert "Scripted extraction is disabled" not in rendered
    extract = next(
        item for item in app.button if item.label == "Extract candidate process"
    )
    assert not extract.disabled


def test_scripted_extraction_stays_refused_for_any_other_document(
    tmp_path, monkeypatch
) -> None:
    app = _source_page(tmp_path, monkeypatch)
    # The first radio on the page is the input-source chooser.
    input_source = app.radio[0]
    assert input_source.label == "Input source"
    app = input_source.set_value("Paste text").run()
    app.text_area[0].set_value(
        "An unrelated process description that is not a bundled fixture."
    )
    app = next(
        item for item in app.button if item.label == "Ingest document"
    ).click().run()
    assert not app.exception
    assert (
        "Scripted extraction is disabled: this is not an approved bundled demo document."
        in _rendered(app)
    )
    extract = next(
        item for item in app.button if item.label == "Extract candidate process"
    )
    assert extract.disabled


def test_bundled_documents_exist_where_the_registry_says(tmp_path) -> None:
    root = Path(__file__).resolve().parents[2]
    for fixture in DEMO_FIXTURES:
        assert (root / "data" / "demo" / fixture.source_label).is_file(), fixture.key

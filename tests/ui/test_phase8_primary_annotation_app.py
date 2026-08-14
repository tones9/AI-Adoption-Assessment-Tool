from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "evaluation" / "primary_annotation" / "streamlit_app.py"


def test_primary_annotation_app_starts_before_only_and_unpopulated() -> None:
    app = AppTest.from_file(APP, default_timeout=20).run()
    assert not app.exception
    assert app.title[0].value == "CON-001 primary annotation"
    rendered = "\n".join(
        str(item.value)
        for kind in ("caption", "warning", "markdown", "info", "code")
        for item in app.get(kind)
    )
    assert "unconfirmed cues" in rendered.lower()
    assert "0767e1e5dd672cb4a4faae490f97d0b56d7a3156572a446bc5c7487ee2e0fe9d" in rendered
    assert "later intervention" not in rendered.lower()
    assert not (ROOT / "evaluation" / "artifacts" / "primary_annotations" / "con-001").exists()

from __future__ import annotations

import hashlib

from ai_adoption_engine.presentation.pages import decision_continuation
from tests.fakes.four_gate_workspace import persisted_four_gate_baseline
from tests.ui.test_decision_continuation_decision_first import _split_layers
from tests.ui.test_decision_continuation_ui import _dcw_app


def test_successor_dcw_shows_decision_first_unavailable_state_without_actions(
    tmp_path,
    monkeypatch,
) -> None:
    repository, assessment_id, _, package_result, _ = persisted_four_gate_baseline(
        tmp_path
    )
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(repository.path))
    monkeypatch.setattr(
        decision_continuation,
        "decision_continuation_service",
        lambda: (_ for _ in ()).throw(
            AssertionError("legacy DCW service must not be composed")
        ),
    )
    before = hashlib.sha256(repository.path.read_bytes()).hexdigest()

    app = _dcw_app(assessment_id)

    assert not app.exception
    layer_one, layer_two = _split_layers(app)
    visible = "\n".join(layer_one)
    technical = "\n".join(layer_two)
    assert [item.value for item in app.subheader][:5] == [
        "Your current official decision",
        "What your decision covers",
        "What is available now",
        "Do you need to do anything?",
        "Continuation unavailable",
    ]
    assert "immutable official baseline" in visible
    assert "Continuation unavailable" in visible
    assert "workflow limitation, not an assessment error" in visible
    assert "M1 and M2 reassessment and comparison workflows are legacy-only" in visible
    assert "No legacy continuation can be started, resumed, created, persisted" in visible
    for item in package_result.package.portfolio.items:
        assert item.activity in visible
        assert item.outcome_code.value in technical
        assert item.decision_status.value in technical
    assert not app.button
    assert not app.file_uploader
    assert not app.selectbox
    assert hashlib.sha256(repository.path.read_bytes()).hexdigest() == before


def test_successor_contract_ids_and_hashes_stay_behind_technical_details(
    tmp_path,
    monkeypatch,
) -> None:
    repository, assessment_id, integrated, package_result, package_ref = (
        persisted_four_gate_baseline(tmp_path)
    )
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(repository.path))

    app = _dcw_app(assessment_id)

    assert not app.exception
    layer_one, layer_two = _split_layers(app)
    visible = "\n".join(layer_one)
    technical = "\n".join(layer_two)
    tokens = (
        "four-gate-framework.v0.1",
        "phase1-v0.4",
        "phase5-v0.2",
        "phase6-v0.2",
        "decision_policy.v0.3",
        "0.3.0",
        integrated.policy.decision_policy_fingerprint,
        package_result.package.package_id,
        package_ref.artifact_id,
    )
    for token in tokens:
        assert token in technical
        assert token not in visible

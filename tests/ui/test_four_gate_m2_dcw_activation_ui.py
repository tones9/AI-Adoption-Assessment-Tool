from __future__ import annotations

import hashlib
import shutil

from ai_adoption_engine.grw.four_gate_m2.models import (
    FourGateM2ConflictStatus,
    FourGateM2DocumentLocator,
    FourGateM2EvidencePermission,
    FourGateM2RunStage,
)
from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.presentation.pages import decision_continuation
from tests.fakes.four_gate_m2 import DOCUMENT_BYTES, actor, successor_m2_service
from tests.fakes.four_gate_workspace import (
    persisted_four_gate_data_readiness_baseline,
)
from tests.ui.test_decision_continuation_decision_first import _split_layers
from tests.ui.test_decision_continuation_ui import _dcw_app


def _button_labels(app) -> list[str]:
    return [button.label for button in app.button]


def _assert_only_stage_action(app, expected: str) -> None:
    labels = _button_labels(app)
    assert expected in labels
    lifecycle_actions = {
        "Start controlled reassessment",
        "Submit document for human review",
        "Record human evidence review",
        "Record proposed data-readiness resolution",
        "Request reassessment",
        "Approve successor reassessment",
        "Create separate successor review",
        "Run successor assessment",
        "Create successor Decision Package",
        "Create same-contract comparison",
    }
    assert [label for label in labels if label in lifecycle_actions] == [expected]


def test_eligible_successor_dcw_offers_only_explicit_successor_start(
    tmp_path, monkeypatch
) -> None:
    repository, assessment_id, *_ = persisted_four_gate_data_readiness_baseline(
        tmp_path
    )
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(repository.path))
    monkeypatch.setattr(
        decision_continuation,
        "decision_continuation_service",
        lambda: (_ for _ in ()).throw(
            AssertionError("legacy DCW/M1/M2 must not be composed")
        ),
    )

    app = _dcw_app(assessment_id)

    assert not app.exception
    layer_one, _ = _split_layers(app)
    visible = "\n".join(layer_one)
    assert "Your current official decision" in visible
    assert "immutable official baseline" in visible
    assert "Optional controlled reassessment" in visible
    assert "same-contract decision" in visible
    _assert_only_stage_action(app, "Start controlled reassessment")
    assert not app.file_uploader

    app = next(
        button
        for button in app.button
        if button.label == "Start controlled reassessment"
    ).click().run()

    assert not app.exception
    _assert_only_stage_action(app, "Submit document for human review")
    assert len(app.file_uploader) == 1
    assert "Record human evidence review" not in _button_labels(app)
    assert "Approve successor reassessment" not in _button_labels(app)


def test_successor_dcw_resumes_every_human_controlled_stage_and_compares_typed(
    tmp_path, monkeypatch
) -> None:
    state = successor_m2_service(tmp_path)
    service = state["service"]
    assessment_id = state["assessment_id"]
    monkeypatch.setenv(
        "AI_ADOPTION_ENGINE_DB_PATH", str(state["baseline_repository"].path)
    )
    manifest = service.create_run(assessment_id, state["target_step_id"])

    app = _dcw_app(assessment_id)
    assert not app.exception
    _assert_only_stage_action(app, "Submit document for human review")
    assert len(app.file_uploader) == 1

    declared = actor()
    service.submit_supporting_document(
        manifest.run_id,
        content_bytes=DOCUMENT_BYTES,
        filename="support.txt",
        source_label="Declared data-owner report",
        submitter=declared,
    )
    app = _dcw_app(assessment_id)
    assert not app.exception
    _assert_only_stage_action(app, "Record human evidence review")
    assert "Approve successor reassessment" not in _button_labels(app)

    text = DOCUMENT_BYTES.decode("utf-8")
    service.review_document_evidence(
        manifest.run_id,
        reviewer=declared,
        locator=FourGateM2DocumentLocator(
            start_offset=0,
            end_offset=len(text),
            line_start=1,
            line_end=1,
            exact_excerpt=text,
        ),
        scope_statement="The target activity only.",
        period_statement="Current-state evidence at review time.",
        source_authority="Locally declared data owner.",
        applicability_statement="The evidence applies to the target activity.",
        semantic_rationale="The reviewed statement maps to data readiness only.",
        limitations="Authority is locally declared.",
        conflict_status=FourGateM2ConflictStatus.CONSISTENT,
        conflict_rationale="No conflicting baseline evidence was identified.",
        permission=(
            FourGateM2EvidencePermission.CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE
        ),
    )
    app = _dcw_app(assessment_id)
    assert not app.exception
    _assert_only_stage_action(app, "Record proposed data-readiness resolution")

    service.propose_data_readiness_resolution(
        manifest.run_id,
        proposed_value=4,
        proposed_knowledge_state=KnowledgeState.KNOWN,
        mapping_rationale="Reviewed evidence supports data-readiness value 4.",
        data_owner=declared,
        criterion_reviewer=declared,
    )
    app = _dcw_app(assessment_id)
    assert not app.exception
    _assert_only_stage_action(app, "Request reassessment")

    service.request_reassessment(manifest.run_id)
    app = _dcw_app(assessment_id)
    assert not app.exception
    _assert_only_stage_action(app, "Approve successor reassessment")
    assert "Create separate successor review" not in _button_labels(app)

    app = next(
        button
        for button in app.button
        if button.label == "Approve successor reassessment"
    ).click().run()
    assert not app.exception
    _assert_only_stage_action(app, "Approve successor reassessment")
    assert service.repository.load_run(manifest.run_id)["stage"] == (
        FourGateM2RunStage.REQUESTED.value
    )

    service.approve_reassessment(
        manifest.run_id,
        approver=declared,
        rationale="Explicitly approve the one-field successor reassessment.",
    )
    app = _dcw_app(assessment_id)
    assert not app.exception
    _assert_only_stage_action(app, "Create separate successor review")

    service.build_successor_review(manifest.run_id)
    app = _dcw_app(assessment_id)
    assert not app.exception
    _assert_only_stage_action(app, "Run successor assessment")

    service.assess_successor(manifest.run_id)
    app = _dcw_app(assessment_id)
    assert not app.exception
    _assert_only_stage_action(app, "Create successor Decision Package")

    service.generate_successor_package(manifest.run_id)
    app = _dcw_app(assessment_id)
    assert not app.exception
    _assert_only_stage_action(app, "Create same-contract comparison")

    service.compare(manifest.run_id)
    app = _dcw_app(assessment_id)
    assert not app.exception
    layer_one, layer_two = _split_layers(app)
    visible = "\n".join(layer_one)
    technical = "\n".join(layer_two)
    assert "Official baseline decision" in visible
    assert "Separate successor decision" in visible
    assert "does not establish improvement" in visible
    assert "deployment readiness" in visible
    assert not [
        label
        for label in _button_labels(app)
        if label != "Technical details"
    ]
    assert "Typed same-contract comparison" in technical
    assert "change_disposition:" in technical
    assert "readiness_disposition:" in technical
    assert "selected_intervention_family:" in technical
    assert "autonomy_ceiling:" in technical
    assert "gate_results:" in technical


def test_frozen_successor_dcw_is_read_only_and_offers_no_action(
    tmp_path, monkeypatch
) -> None:
    source, assessment_id, *_ = persisted_four_gate_data_readiness_baseline(
        tmp_path / "source"
    )
    frozen = tmp_path / "evaluation" / "portfolio" / "frozen" / "workspace.db"
    frozen.parent.mkdir(parents=True)
    shutil.copy2(source.path, frozen)
    before = frozen.read_bytes()
    before_hash = hashlib.sha256(before).hexdigest()
    before_entries = tuple(sorted(path.name for path in frozen.parent.iterdir()))
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(frozen))
    monkeypatch.setattr(
        decision_continuation,
        "four_gate_m2_service",
        lambda: (_ for _ in ()).throw(
            AssertionError("successor write service must not be composed")
        ),
    )

    app = _dcw_app(assessment_id)

    assert not app.exception
    visible = "\n".join(_split_layers(app)[0])
    assert "protected read-only workspace" in visible
    assert "no reassessment record or artifact can be created" in visible
    assert not app.button
    assert not app.file_uploader
    assert frozen.read_bytes() == before
    assert hashlib.sha256(frozen.read_bytes()).hexdigest() == before_hash
    assert tuple(sorted(path.name for path in frozen.parent.iterdir())) == before_entries

"""The two bundled demo fixtures, proved against the unchanged engine.

The point of the second fixture is that its outcomes are *produced*, not
asserted: the synthetic source records operational facts, the scripted
extraction cites the sentence stating each one, a human review accepts them, and
the existing policy decides what each activity gets.  These tests therefore run
the real pipeline and check the result, rather than pinning strings.

They also protect the first fixture: its deliberate all-unknown behaviour is the
honest conservative case and must not drift.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

import pytest

from ai_adoption_engine.grw.m2.service import M2ReassessmentService
from ai_adoption_engine.models.enums import (
    CriterionName,
    KnowledgeState,
    RecommendationMode,
)
from ai_adoption_engine.persistence.reassessment import SQLiteReassessmentRepository
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.workspace.composition import extraction_service_for
from ai_adoption_engine.workspace import demo_field_service
from ai_adoption_engine.workspace.demo_fixtures import (
    DECISION_VARIETY,
    DEMO_FIXTURES,
    EVIDENCE_GAP,
    SYNTHETIC_LABEL,
    fixture_for_document_id,
    fixture_for_key,
)
from ai_adoption_engine.workspace.models import ArtifactType, ExecutionMode
from ai_adoption_engine.workspace.service import AssessmentWorkspaceService


ROOT = Path(__file__).resolve().parents[2]

#: The first fixture's document is frozen behaviour: its content decides the
#: conservative demo, and this digest fails loudly if it is edited.
EVIDENCE_GAP_SHA256 = hashlib.sha256(
    (ROOT / "data" / "demo" / "synthetic_complaint_process.txt").read_bytes()
).hexdigest()


def _run_fixture(tmp_path: Path, key: str, monkeypatch):
    """Run one bundled fixture through ingest → review → approve → assess → package."""

    fixture = fixture_for_key(key)
    database = tmp_path / f"{key}.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(database))
    repository = SQLiteAssessmentRepository(database)
    service = AssessmentWorkspaceService(
        repository, extraction_service_factory=extraction_service_for
    )
    assessment = repository.create_assessment(fixture.title, ExecutionMode.OFFLINE_DEMO)
    service.ingest_upload(
        assessment.assessment_id,
        raw_text=fixture.text(),
        source_label=fixture.source_label,
    )
    assert service.extract(assessment.assessment_id).status == "success"

    review = service.start_review(assessment.assessment_id)
    reviews = service.review_service
    reviews.accept_assertion(review, review.process_name, "process.name")
    for step in review.steps:
        reviews.accept_assertion(
            review, step.activity, f"steps.{step.candidate_step_id}.activity"
        )
        for characteristic in step.criteria:
            path = (
                f"steps.{step.candidate_step_id}.criteria.{characteristic.name.value}"
            )
            if characteristic.assertion.knowledge_state is KnowledgeState.UNKNOWN:
                reviews.retain_unknown(review, characteristic.assertion, path)
            else:
                reviews.accept_assertion(review, characteristic.assertion, path)
        accountability = f"steps.{step.candidate_step_id}.human_accountability_required"
        if step.human_accountability_required.knowledge_state is KnowledgeState.UNKNOWN:
            reviews.retain_unknown(
                review, step.human_accountability_required, accountability
            )
        else:
            reviews.accept_assertion(
                review, step.human_accountability_required, accountability
            )
        for signal in step.capability_signals:
            if signal.assertion.knowledge_state is KnowledgeState.KNOWN:
                reviews.accept_assertion(
                    review,
                    signal.assertion,
                    f"steps.{step.candidate_step_id}.capability_signals.{signal.name}",
                )
    reviews.accept_step_order(review)
    service.save_review(assessment.assessment_id, review)

    assert service.approve(assessment.assessment_id).approved is not None
    assert service.assess(assessment.assessment_id).status == "success"
    package = service.generate_package(assessment.assessment_id)
    assert package.status == "success"
    return repository, assessment.assessment_id, package.package


def _modes(package) -> Counter:
    return Counter(item.recommendation_mode for item in package.portfolio.items)


# ---------------------------------------------------------------------------
# 1. Both fixtures are explicitly synthetic
# ---------------------------------------------------------------------------


def test_every_bundled_fixture_is_labelled_synthetic() -> None:
    assert SYNTHETIC_LABEL == "SYNTHETIC DEMONSTRATION DATA"
    for fixture in DEMO_FIXTURES:
        assert "synthetic" in fixture.source_label.lower(), fixture.key
        assert fixture.source_label.endswith(".txt")
        assert fixture.document_id().startswith("doc-")
    # The new document states the label in its own text.  The original document
    # is frozen and is labelled instead by its filename and by the permanent
    # offline-demo banner, so this difference is asserted rather than papered
    # over.
    assert SYNTHETIC_LABEL in DECISION_VARIETY.text()
    assert SYNTHETIC_LABEL not in EVIDENCE_GAP.text()


def test_decision_variety_source_states_that_it_is_demonstration_only() -> None:
    text = DECISION_VARIETY.text()
    assert SYNTHETIC_LABEL in text
    assert "not a real customer process" in text
    assert "not research evidence" in text
    assert "not a record of any measured outcome" in text
    supporting = (
        ROOT / "data" / "demo" / "synthetic_field_service_contract_records.txt"
    ).read_text(encoding="utf-8")
    assert SYNTHETIC_LABEL in supporting
    assert "not a real customer record" in supporting


def test_fixtures_are_distinct_and_resolvable_by_document_identity() -> None:
    assert {fixture.key for fixture in DEMO_FIXTURES} == {
        "evidence-gap",
        "decision-variety",
    }
    assert EVIDENCE_GAP.document_id() != DECISION_VARIETY.document_id()
    for fixture in DEMO_FIXTURES:
        assert fixture_for_document_id(fixture.document_id()) is fixture
    assert fixture_for_document_id("doc-" + "0" * 64) is None


# ---------------------------------------------------------------------------
# 2. The existing fixture is unchanged
# ---------------------------------------------------------------------------


def test_evidence_gap_fixture_document_is_byte_identical() -> None:
    digest = hashlib.sha256(
        (ROOT / "data" / "demo" / "synthetic_complaint_process.txt").read_bytes()
    ).hexdigest()
    assert digest == EVIDENCE_GAP_SHA256


def test_evidence_gap_fixture_still_records_every_criterion_as_unknown(
    tmp_path, monkeypatch
) -> None:
    _, _, package = _run_fixture(tmp_path, "evidence-gap", monkeypatch)
    modes = _modes(package)
    assert set(modes) == {RecommendationMode.INVESTIGATE_FURTHER}
    assert sum(modes.values()) == 7


# ---------------------------------------------------------------------------
# 3. The new fixture produces a mix of outcomes, from the unchanged engine
# ---------------------------------------------------------------------------


def test_decision_variety_fixture_produces_four_distinct_outcomes(
    tmp_path, monkeypatch
) -> None:
    _, _, package = _run_fixture(tmp_path, "decision-variety", monkeypatch)
    assert package.current_state.process_name == "Synthetic Field Service Request Handling"
    outcomes = {
        item.current_activity: item.recommendation_mode
        for item in package.portfolio.items
    }
    assert outcomes == {
        "Sort incoming maintenance requests": RecommendationMode.AUTOMATE,
        "Check the request against the service contract": (
            RecommendationMode.INVESTIGATE_FURTHER
        ),
        "Draft the scheduling note for the field engineer": RecommendationMode.AUGMENT,
        "Approve or refuse a goodwill repair": RecommendationMode.DO_NOT_RECOMMEND,
    }
    # All four locked modes, each exactly once: this is the fixture's purpose.
    assert set(_modes(package).values()) == {1}
    assert len(_modes(package)) == 4


def test_score_eligible_activities_receive_a_complete_priority(
    tmp_path, monkeypatch
) -> None:
    _, _, package = _run_fixture(tmp_path, "decision-variety", monkeypatch)
    scored = {
        item.current_activity: item.priority
        for item in package.portfolio.items
        if item.recommendation_mode
        in {RecommendationMode.AUTOMATE, RecommendationMode.AUGMENT}
    }
    assert set(scored) == {
        "Sort incoming maintenance requests",
        "Draft the scheduling note for the field engineer",
    }
    for activity, priority in scored.items():
        assert priority is not None, activity
        assert priority.score is not None, activity
        assert priority.band is not None, activity
    # The automation candidate scores above the augmentation candidate; both are
    # engine output, not fixture text.
    assert (
        scored["Sort incoming maintenance requests"].score
        > scored["Draft the scheduling note for the field engineer"].score
    )


def test_the_open_question_is_the_only_decision_material_gap(
    tmp_path, monkeypatch
) -> None:
    _, _, package = _run_fixture(tmp_path, "decision-variety", monkeypatch)
    material = {
        (item.current_activity, gap.field_name)
        for item in package.portfolio.items
        for gap in item.missing_information
        if gap.material_to_recommendation and gap.field_name in set(CriterionName)
    }
    assert material == {
        (
            "Check the request against the service contract",
            CriterionName.DATA_READINESS.value,
        )
    }


# ---------------------------------------------------------------------------
# 4. Determinism
# ---------------------------------------------------------------------------


def test_repeated_runs_of_the_new_fixture_are_identical(tmp_path, monkeypatch) -> None:
    _, _, first = _run_fixture(tmp_path / "one", "decision-variety", monkeypatch)
    _, _, second = _run_fixture(tmp_path / "two", "decision-variety", monkeypatch)
    # ``package_id`` is derived from the package's content, so equality across
    # two independent workspaces is the determinism assertion.  Run identifiers
    # and timestamps legitimately differ and are excluded by that derivation.
    assert first.package_id == second.package_id
    assert first.completeness == second.completeness

    def outcomes(package):
        return [
            (
                item.current_activity,
                item.recommendation_mode,
                getattr(item.priority, "score", None),
                tuple(sorted(gap.field_name for gap in item.missing_information)),
            )
            for item in package.portfolio.items
        ]

    assert outcomes(first) == outcomes(second)


# ---------------------------------------------------------------------------
# 5. Evidence and provenance
# ---------------------------------------------------------------------------


def test_every_cited_snippet_resolves_in_the_bundled_document() -> None:
    text = DECISION_VARIETY.text()
    for block_id, snippet in demo_field_service.cited_snippets():
        assert snippet in text, (block_id, snippet[:60])


def test_every_known_criterion_carries_resolved_source_evidence(
    tmp_path, monkeypatch
) -> None:
    repository, assessment_id, _ = _run_fixture(
        tmp_path, "decision-variety", monkeypatch
    )
    workspace = repository.load_workspace(assessment_id)
    integrated = workspace.active_artifacts[ArtifactType.INTEGRATED_ASSESSMENT_RESULT]
    canonical = DECISION_VARIETY.text()
    checked = 0
    for step in integrated.payload.process_assessment.step_assessments:
        index = {reference.evidence_id: reference for reference in step.evidence}
        for criterion in step.criteria:
            if criterion.knowledge_state is KnowledgeState.UNKNOWN:
                assert criterion.value is None, (step.step_id, criterion.criterion)
                assert not criterion.evidence_ids, (step.step_id, criterion.criterion)
                continue
            assert criterion.evidence_ids, (step.step_id, criterion.criterion)
            for evidence_id in criterion.evidence_ids:
                reference = index.get(evidence_id)
                assert reference is not None, (step.step_id, criterion.criterion)
                # The snippet is resolved from the ingested document, not
                # supplied by the provider, so it must appear in the source.
                assert reference.supporting_snippet in canonical
                assert reference.source_locator
                checked += 1
    # Nine activities' worth of documented criteria: 10 + 9 + 10 + 10.
    assert checked == 39


def test_the_unknown_criterion_stays_unknown_with_no_evidence(
    tmp_path, monkeypatch
) -> None:
    repository, assessment_id, _ = _run_fixture(
        tmp_path, "decision-variety", monkeypatch
    )
    workspace = repository.load_workspace(assessment_id)
    integrated = workspace.active_artifacts[ArtifactType.INTEGRATED_ASSESSMENT_RESULT]
    unknowns = {
        (step.step_id, criterion.criterion)
        for step in integrated.payload.process_assessment.step_assessments
        for criterion in step.criteria
        if criterion.knowledge_state is KnowledgeState.UNKNOWN
    }
    assert any(
        criterion is CriterionName.DATA_READINESS for _, criterion in unknowns
    )
    assert sum(
        1 for _, criterion in unknowns if criterion is CriterionName.DATA_READINESS
    ) == 1


# ---------------------------------------------------------------------------
# 6. No methodology change
# ---------------------------------------------------------------------------


def test_both_fixtures_run_on_the_same_unchanged_policy(
    tmp_path, monkeypatch
) -> None:
    repository_a, assessment_a, _ = _run_fixture(
        tmp_path / "gap", "evidence-gap", monkeypatch
    )
    repository_b, assessment_b, _ = _run_fixture(
        tmp_path / "variety", "decision-variety", monkeypatch
    )

    def policy_identity(repository, assessment_id):
        payload = repository.load_workspace(assessment_id).active_artifacts[
            ArtifactType.INTEGRATED_ASSESSMENT_RESULT
        ].payload
        return (
            payload.policy.policy_id,
            payload.policy.policy_version,
            payload.policy.policy_status,
            payload.policy.decision_policy_fingerprint,
            payload.metadata.phase1_contract_version,
        )

    assert policy_identity(repository_a, assessment_a) == policy_identity(
        repository_b, assessment_b
    )


def test_the_new_fixture_module_contains_no_engine_import() -> None:
    source = (
        ROOT
        / "src"
        / "ai_adoption_engine"
        / "workspace"
        / "demo_field_service.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "ai_adoption_engine.decision",
        "ai_adoption_engine.decision_support",
        "ai_adoption_engine.grw",
        "decision_policy",
    ):
        assert forbidden not in source, forbidden


# ---------------------------------------------------------------------------
# 7. The controlled reassessment route becomes demonstrable
# ---------------------------------------------------------------------------


def test_controlled_reassessment_is_available_only_on_the_new_fixture(
    tmp_path, monkeypatch
) -> None:
    for key, expected in (("evidence-gap", False), ("decision-variety", True)):
        repository, assessment_id, _ = _run_fixture(tmp_path / key, key, monkeypatch)
        service = M2ReassessmentService(
            repository, SQLiteReassessmentRepository(repository.path)
        )
        context = service.open_m2_m1_context(assessment_id)
        assert (context is not None) is expected, key
        if context is not None:
            _, gap = context
            assert gap.current_activity == "Check the request against the service contract"
            assert gap.information_gap.field_name == CriterionName.DATA_READINESS.value
            assert gap.baseline_knowledge_state is KnowledgeState.UNKNOWN
            assert gap.baseline_value is None


@pytest.fixture()
def reassessed(tmp_path, monkeypatch):
    """Drive the bundled supporting document through the whole M2 lifecycle."""

    from datetime import UTC, datetime

    from ai_adoption_engine.grw.m2.models import (
        M2ActorDeclaration,
        M2ArtifactType,
        M2ConflictStatus,
        M2DocumentLocator,
        M2EvidencePermission,
    )

    def actor(label: str, role: str) -> M2ActorDeclaration:
        return M2ActorDeclaration(
            label=label,
            declared_role=role,
            acknowledged_local_role_limitation=True,
            declared_at=datetime.now(UTC),
        )

    repository, assessment_id, package = _run_fixture(
        tmp_path, "decision-variety", monkeypatch
    )
    baseline_artifact = repository.load_workspace(assessment_id).active_artifacts[
        ArtifactType.DECISION_PACKAGE_RESULT
    ]
    service = M2ReassessmentService(
        repository, SQLiteReassessmentRepository(repository.path)
    )
    run_id, _, _ = service.create_run(assessment_id)
    document = ROOT / "data" / "demo" / "synthetic_field_service_contract_records.txt"
    payload = document.read_bytes()
    text = payload.decode("utf-8")
    service.submit_supporting_document(
        run_id,
        content_bytes=payload,
        filename=document.name,
        source_label="Synthetic contracts team",
        submitter=actor("Demo submitter", "document submitter"),
    )
    start = text.index("Fields retained.")
    end = text.index("Limitations.") + len("Limitations.")
    service.review_document_evidence(
        run_id,
        reviewer=actor("Demo evidence reviewer", "evidence reviewer"),
        locator=M2DocumentLocator(
            start_offset=start,
            end_offset=end,
            line_start=text.count("\n", 0, start) + 1,
            line_end=text.count("\n", 0, end) + 1,
            exact_excerpt=text[start:end],
        ),
        scope_statement="The note covers the contract records used by the entitlement check only.",
        period_statement="January 2023 onward; earlier records lack clause references.",
        source_authority="Synthetic contracts team",
        semantic_rationale=(
            "The retained fields, the coverage history and the access arrangement "
            "address the recorded data-readiness question."
        ),
        limitations=(
            "Exclusions wording is unstandardised and pre-2023 records lack clause references."
        ),
        conflict_status=M2ConflictStatus.CONSISTENT,
        conflict_rationale="No material conflict with the reviewed process document.",
        permission=M2EvidencePermission.CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE,
    )
    service.propose_data_readiness_resolution(
        run_id,
        proposed_value=3,
        proposed_knowledge_state=KnowledgeState.KNOWN,
        mapping_rationale=(
            "Fields, coverage and access are documented; free-text and migration "
            "limits keep it below the top anchor."
        ),
        data_owner=actor("Demo data owner", "data owner"),
        criterion_reviewer=actor("Demo criterion reviewer", "criterion reviewer"),
    )
    service.request_reassessment(run_id)
    service.approve_reassessment(
        run_id,
        approver=actor("Demo approver", "reassessment approver"),
        rationale="The reviewed data-readiness resolution is approved for a separate successor.",
    )
    service.build_successor_review(run_id)
    service.assess_successor(run_id)
    service.generate_successor_package(run_id)
    comparison = service.compare(run_id)
    return {
        "repository": repository,
        "assessment_id": assessment_id,
        "service": service,
        "run_id": run_id,
        "baseline_artifact": baseline_artifact,
        "baseline_package": package,
        "comparison": comparison,
        "artifact_type": M2ArtifactType,
    }


def test_reassessment_leaves_the_baseline_package_untouched(reassessed) -> None:
    before = reassessed["baseline_artifact"]
    after = reassessed["repository"].load_workspace(
        reassessed["assessment_id"]
    ).active_artifacts[ArtifactType.DECISION_PACKAGE_RESULT]
    assert after.artifact_id == before.artifact_id
    assert after.artifact_revision == before.artifact_revision
    assert after.payload_sha256 == before.payload_sha256
    assert (
        after.payload.package.model_dump(mode="json")
        == reassessed["baseline_package"].model_dump(mode="json")
    )


def test_reassessment_produces_a_separate_successor_package(reassessed) -> None:
    reference = SQLiteReassessmentRepository(
        reassessed["repository"].path
    ).load_artifact_reference(
        reassessed["run_id"], reassessed["artifact_type"].SUCCESSOR_DECISION_PACKAGE
    )
    stored = SQLiteReassessmentRepository(
        reassessed["repository"].path
    ).load_artifact(reference.artifact_id)
    successor = getattr(stored.decision_package, "package", stored.decision_package)
    baseline = reassessed["baseline_package"]
    assert successor.package_id != baseline.package_id

    baseline_modes = {
        item.current_activity: item.recommendation_mode
        for item in baseline.portfolio.items
    }
    successor_modes = {
        item.current_activity: item.recommendation_mode
        for item in successor.portfolio.items
    }
    changed = {
        activity
        for activity in baseline_modes
        if baseline_modes[activity] != successor_modes[activity]
    }
    # Only the reassessed activity may differ; the narrow route touches one.
    assert changed == {"Check the request against the service contract"}
    assert (
        baseline_modes["Check the request against the service contract"]
        is RecommendationMode.INVESTIGATE_FURTHER
    )


def test_comparison_stays_deterministic_and_neutral(reassessed) -> None:
    repeated = reassessed["service"].compare(reassessed["run_id"])
    assert repeated.model_dump(mode="json") == reassessed["comparison"].model_dump(
        mode="json"
    )
    explanation = reassessed["comparison"].neutral_explanation.lower()
    for word in ("success", "improve", "better", "roi proof"):
        if word in explanation:
            assert "not" in explanation
    assert "does not describe recommendation movement as success" in explanation

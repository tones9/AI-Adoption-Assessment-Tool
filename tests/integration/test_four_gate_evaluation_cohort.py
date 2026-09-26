from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ai_adoption_engine.models.four_gate_assessment import (
    AutonomyCeiling,
    FourGateName,
    FourGateStatus,
    OutcomeCode,
    SelectedInterventionFamily,
)
from evaluation.four_gate_cohorts.contracts import (
    DEVELOPMENT_FIXTURE_EXCLUSION,
    CohortContractError,
    FourGateCohortManifest,
    MeasureState,
)
from evaluation.four_gate_cohorts.harness import (
    FourGateDevelopmentCohortHarness,
    freeze_development_cohort,
)
from evaluation.four_gate_cohorts.development_run import (
    build_initial_development_cohort,
)
from evaluation.four_gate_cohorts.synthetic_fixtures import (
    FIXTURE_TIME,
    load_synthetic_development_fixtures,
)


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "decision_policy.v0.3.json"
PORTFOLIO = ROOT / "evaluation" / "portfolio"


def _portfolio_hashes() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(PORTFOLIO.rglob("*"))
        if path.is_file()
    }


def _run_fixture_cohort():
    harness = FourGateDevelopmentCohortHarness(POLICY_PATH)
    fixtures = load_synthetic_development_fixtures()
    triples = []
    results = []
    for fixture in fixtures:
        manifest = harness.build_case_manifest(
            case_id=fixture.spec.case_id,
            title=fixture.spec.title,
            source_filename=fixture.spec.filename,
            source_bytes=fixture.source_bytes,
            approved_review=fixture.approved_review,
            frozen_before_at=FIXTURE_TIME,
        )
        result = harness.run_case(
            manifest,
            source_bytes=fixture.source_bytes,
            approved_review=fixture.approved_review,
        )
        triples.append((fixture.source_bytes, fixture.approved_review, result))
        results.append(result)
    cohort = FourGateCohortManifest(
        cohort_id="four-gate-development-initial-v0-1",
        contract=harness.contract,
        case_ids=[fixture.spec.case_id for fixture in fixtures],
    )
    summary = harness.summarize(cohort, results)
    return harness, fixtures, cohort, triples, results, summary


def test_synthetic_fixture_coverage_uses_only_successor_contracts() -> None:
    _, fixtures, _, _, results, _ = _run_fixture_cohort()
    observed = {
        result.manifest.case_id: result.outcomes[0] for result in results
    }
    assert observed == {
        fixture.spec.case_id: fixture.spec.expected_outcome for fixture in fixtures
    }
    assert set(observed.values()) == {
        OutcomeCode.NO_CHANGE_JUSTIFIED,
        OutcomeCode.DISCOVERY_REQUIRED,
        OutcomeCode.CONVENTIONAL_AUTOMATION,
        OutcomeCode.KEEP_HUMAN_LED,
        OutcomeCode.PROCESS_IMPROVEMENT_FIRST,
    }
    for result in results:
        integrated = result.run.integrated_assessment
        package = result.run.decision_package.package
        assert integrated.metadata.phase1_contract_version == "phase1-v0.4"
        assert integrated.metadata.integration_schema_version == "phase5-v0.2"
        assert package.package_schema_version == "phase6-v0.2"
        assert integrated.process_assessment.framework_id == (
            "four-gate-framework.v0.1"
        )
        assert [
            gate.gate
            for gate in integrated.process_assessment.step_assessments[0].gate_results
        ] == list(FourGateName)
        assert result.run.traceability.passed_count == (
            result.run.traceability.check_count
        )

    no_change = results[0].run.integrated_assessment.process_assessment.step_assessments[0]
    discovery = results[1].run.integrated_assessment.process_assessment.step_assessments[0]
    conventional = results[2].run.integrated_assessment.process_assessment.step_assessments[0]
    veto = results[3].run.integrated_assessment.process_assessment.step_assessments[0]
    process_first = results[4].run.integrated_assessment.process_assessment.step_assessments[0]
    assert [gate.status for gate in no_change.gate_results[1:]] == [
        FourGateStatus.NOT_EVALUATED,
        FourGateStatus.NOT_EVALUATED,
        FourGateStatus.NOT_EVALUATED,
    ]
    assert [gate.status for gate in discovery.gate_results[2:]] == [
        FourGateStatus.NOT_EVALUATED,
        FourGateStatus.NOT_EVALUATED,
    ]
    assert conventional.gate_results[3].status is FourGateStatus.NOT_EVALUATED
    assert process_first.gate_results[2].status is FourGateStatus.NOT_EVALUATED
    assert veto.selected_intervention_family is SelectedInterventionFamily.AI
    assert veto.autonomy_ceiling is AutonomyCeiling.AI_NOT_PERMITTED
    assert veto.outcome_code is OutcomeCode.KEEP_HUMAN_LED


def test_identical_case_and_policy_have_byte_stable_semantic_output() -> None:
    harness = FourGateDevelopmentCohortHarness(POLICY_PATH)
    fixture = load_synthetic_development_fixtures()[1]
    manifest = harness.build_case_manifest(
        case_id=fixture.spec.case_id,
        title=fixture.spec.title,
        source_filename=fixture.spec.filename,
        source_bytes=fixture.source_bytes,
        approved_review=fixture.approved_review,
        frozen_before_at=FIXTURE_TIME,
    )

    first = harness.run_case(
        manifest,
        source_bytes=fixture.source_bytes,
        approved_review=fixture.approved_review,
    )
    second = harness.run_case(
        manifest,
        source_bytes=fixture.source_bytes,
        approved_review=fixture.approved_review,
    )

    assert first.canonical_json_bytes() == second.canonical_json_bytes()
    assert first.run.repeatability.byte_equal is True
    assert first.run.repeatability.first_semantic_sha256 == (
        first.run.repeatability.repeated_semantic_sha256
    )


def test_summary_and_freeze_preserve_denominators_disclosures_and_phase8(
    tmp_path,
) -> None:
    before = _portfolio_hashes()
    _, _, cohort, triples, results, summary = _run_fixture_cohort()

    assert summary.case_count == 5
    assert summary.excluded_from_real_world_claim_count == 5
    assert summary.not_evaluated_gate_count == 8
    assert summary.total_gate_count == 20
    assert sum(summary.outcome_counts.values()) == 5
    by_measure = {item.measure_id: item for item in summary.measures}
    assert by_measure["contract-and-traceability-checks"].numerator == 55
    assert by_measure["contract-and-traceability-checks"].denominator == 55
    for measure_id in (
        "independent-reference-agreement",
        "real-world-outcome-claims",
    ):
        assert by_measure[measure_id].state is MeasureState.NOT_APPLICABLE
        assert by_measure[measure_id].numerator is None
        assert by_measure[measure_id].denominator is None
    assert DEVELOPMENT_FIXTURE_EXCLUSION in summary.disclosures

    first = freeze_development_cohort(tmp_path / "one", cohort, triples, summary)
    second = freeze_development_cohort(tmp_path / "two", cohort, triples, summary)
    first_files = {
        str(path.relative_to(first)): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    }
    second_files = {
        str(path.relative_to(second)): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }
    assert first_files == second_files
    assert DEVELOPMENT_FIXTURE_EXCLUSION in (
        first / "cohort_summary.v0.1.md"
    ).read_text(encoding="utf-8")
    assert "not applicable" in (
        first / "cohort_summary.v0.1.md"
    ).read_text(encoding="utf-8")
    assert _portfolio_hashes() == before

    changed = first / "cohort_summary.v0.1.json"
    changed.write_text("changed", encoding="utf-8")
    with pytest.raises(CohortContractError, match="artifact changed"):
        freeze_development_cohort(tmp_path / "one", cohort, triples, summary)


def test_freeze_refuses_phase8_target_before_any_write(tmp_path) -> None:
    _, _, cohort, triples, _, summary = _run_fixture_cohort()
    target = tmp_path / "evaluation" / "portfolio" / "successor"
    before = tuple(target.parent.iterdir()) if target.parent.exists() else ()

    with pytest.raises(CohortContractError, match="cannot target Phase 8"):
        freeze_development_cohort(target, cohort, triples, summary)

    after = tuple(target.parent.iterdir()) if target.parent.exists() else ()
    assert after == before
    assert not target.exists()


def test_initial_development_cohort_builder_is_explicit_and_repeatable(
    tmp_path,
) -> None:
    first_path, first_summary = build_initial_development_cohort(
        policy_path=POLICY_PATH,
        output_root=tmp_path,
    )
    second_path, second_summary = build_initial_development_cohort(
        policy_path=POLICY_PATH,
        output_root=tmp_path,
    )

    assert first_path == second_path
    assert first_summary.canonical_json_bytes() == (
        second_summary.canonical_json_bytes()
    )
    assert (first_path / "cohort_manifest.v0.1.json").is_file()
    assert (first_path / "cohort_summary.v0.1.json").is_file()
    assert (first_path / "cohort_summary.v0.1.md").is_file()
    assert len(list((first_path / "cases").glob("*/freeze_manifest.v0.1.json"))) == 5

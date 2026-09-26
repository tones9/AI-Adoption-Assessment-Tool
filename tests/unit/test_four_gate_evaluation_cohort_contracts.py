from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from evaluation.four_gate_cohorts.contracts import (
    COHORT_PROTOCOL_VERSION,
    DEVELOPMENT_FIXTURE_EXCLUSION,
    CohortContractError,
    FourGateDevelopmentCaseManifest,
    FourGateMeasure,
    MeasureState,
)
from evaluation.four_gate_cohorts.harness import (
    FourGateDevelopmentCohortHarness,
)
from evaluation.four_gate_cohorts.synthetic_fixtures import (
    FIXTURE_TIME,
    load_synthetic_development_fixtures,
)


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "decision_policy.v0.3.json"


def _first_case():
    harness = FourGateDevelopmentCohortHarness(POLICY_PATH)
    fixture = load_synthetic_development_fixtures()[0]
    manifest = harness.build_case_manifest(
        case_id=fixture.spec.case_id,
        title=fixture.spec.title,
        source_filename=fixture.spec.filename,
        source_bytes=fixture.source_bytes,
        approved_review=fixture.approved_review,
        frozen_before_at=FIXTURE_TIME,
    )
    return harness, fixture, manifest


def test_case_manifest_accepts_only_exact_successor_pins_and_lineage() -> None:
    harness, fixture, manifest = _first_case()

    result = harness.run_case(
        manifest,
        source_bytes=fixture.source_bytes,
        approved_review=fixture.approved_review,
    )

    assert manifest.contract.cohort_protocol == COHORT_PROTOCOL_VERSION
    assert manifest.contract.framework_id == "four-gate-framework.v0.1"
    assert manifest.contract.decision_policy_id == "decision_policy.v0.3"
    assert manifest.contract.decision_policy_version == "0.3.0"
    assert manifest.contract.phase1_contract_version == "phase1-v0.4"
    assert manifest.contract.phase5_schema_version == "phase5-v0.2"
    assert manifest.contract.phase6_schema_version == "phase6-v0.2"
    assert result.run.integrated_assessment.lineage.review_id == (
        manifest.approved_review.review_id
    )
    assert result.run.integrated_assessment.lineage.source_document_id == (
        manifest.source.source_identifier
    )
    assert result.development_fixture_exclusion == DEVELOPMENT_FIXTURE_EXCLUSION


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.pop("source"), "development-fixture contract"),
        (
            lambda payload: payload["contract"].update(
                {"phase5_schema_version": "phase5-v0.1"}
            ),
            "development-fixture contract",
        ),
        (
            lambda payload: payload["contract"].update(
                {"decision_policy_fingerprint": "f" * 64}
            ),
            "development-fixture contract",
        ),
        (
            lambda payload: payload.update({"schema_version": "phase8-case-manifest.v0.1"}),
            "development-fixture contract",
        ),
    ],
)
def test_missing_mixed_malformed_or_changed_pins_fail_closed(mutation, message) -> None:
    harness, fixture, manifest = _first_case()
    payload = manifest.model_dump(mode="json")
    mutation(payload)

    with pytest.raises(CohortContractError, match=message):
        harness.run_case(
            payload,
            source_bytes=fixture.source_bytes,
            approved_review=fixture.approved_review,
        )


def test_changed_source_or_review_hash_fails_before_successor_execution() -> None:
    harness, fixture, manifest = _first_case()
    with pytest.raises(CohortContractError, match="Source bytes"):
        harness.run_case(
            manifest,
            source_bytes=fixture.source_bytes + b"changed",
            approved_review=fixture.approved_review,
        )

    payload = manifest.model_dump(mode="json")
    payload["approved_review"]["approved_review_sha256"] = "0" * 64
    changed_review_pin = FourGateDevelopmentCaseManifest.model_validate(payload)
    with pytest.raises(CohortContractError, match="Approved review"):
        harness.run_case(
            changed_review_pin,
            source_bytes=fixture.source_bytes,
            approved_review=fixture.approved_review,
        )


def test_changed_policy_payload_cannot_claim_the_pinned_cohort_protocol(
    tmp_path,
) -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["description"] = "Changed policy payload with unchanged identifiers."
    changed_policy = tmp_path / "decision_policy.v0.3.changed.json"
    changed_policy.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CohortContractError, match="exact successor contract"):
        FourGateDevelopmentCohortHarness(changed_policy)


def test_legacy_phase8_artifact_is_not_a_successor_case() -> None:
    harness, fixture, _ = _first_case()
    legacy = json.loads(
        (ROOT / "evaluation" / "portfolio" / "register.v0.1.json").read_text(
            encoding="utf-8"
        )
    )

    with pytest.raises(CohortContractError, match="development-fixture contract"):
        harness.run_case(
            legacy,
            source_bytes=fixture.source_bytes,
            approved_review=fixture.approved_review,
        )


def test_not_applicable_measure_cannot_be_reported_as_zero() -> None:
    measure = FourGateMeasure(
        measure_id="independent-reference-agreement",
        state=MeasureState.NOT_APPLICABLE,
        not_applicable_reason="No independent reference annotation exists.",
    )
    assert measure.numerator is None
    assert measure.denominator is None

    with pytest.raises(ValidationError, match="cannot use zero denominators"):
        FourGateMeasure(
            measure_id="independent-reference-agreement",
            state=MeasureState.NOT_APPLICABLE,
            numerator=0,
            denominator=1,
            not_applicable_reason="No independent reference annotation exists.",
        )

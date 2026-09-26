"""Build the initial frozen synthetic cohort in an explicitly supplied location."""

from __future__ import annotations

from pathlib import Path

from .contracts import FourGateCohortManifest, FourGateCohortSummary
from .harness import FourGateDevelopmentCohortHarness, freeze_development_cohort
from .synthetic_fixtures import FIXTURE_TIME, load_synthetic_development_fixtures


INITIAL_COHORT_ID = "four-gate-development-initial-v0-1"


def build_initial_development_cohort(
    *,
    policy_path: str | Path,
    output_root: str | Path,
) -> tuple[Path, FourGateCohortSummary]:
    """Run and freeze only the five controlled development fixtures."""

    harness = FourGateDevelopmentCohortHarness(policy_path)
    fixtures = load_synthetic_development_fixtures()
    frozen_inputs = []
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
        frozen_inputs.append(
            (fixture.source_bytes, fixture.approved_review, result)
        )
        results.append(result)
    cohort = FourGateCohortManifest(
        cohort_id=INITIAL_COHORT_ID,
        contract=harness.contract,
        case_ids=[fixture.spec.case_id for fixture in fixtures],
    )
    summary = harness.summarize(cohort, results)
    location = freeze_development_cohort(
        output_root,
        cohort,
        frozen_inputs,
        summary,
    )
    return location, summary


__all__ = ["INITIAL_COHORT_ID", "build_initial_development_cohort"]

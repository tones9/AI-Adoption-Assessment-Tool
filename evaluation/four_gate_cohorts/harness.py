"""Offline harness for the successor cohort's synthetic development fixtures."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Iterable

from pydantic import ValidationError

from ai_adoption_engine.application.fingerprints import (
    fingerprint_business_process,
    fingerprint_four_gate_policy,
)
from ai_adoption_engine.application.four_gate_assessment import (
    FourGateIntegratedAssessmentService,
)
from ai_adoption_engine.decision.four_gate_policy import load_four_gate_policy
from ai_adoption_engine.decision_support.four_gate_service import (
    FourGateDecisionSupportPackageService,
)
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.four_gate_assessment import (
    FourGateName,
    FourGateStatus,
    OutcomeCode,
)
from ai_adoption_engine.models.four_gate_decision_support import (
    FourGateDecisionPackageSuccess,
    FourGateInformationGapKind,
    FourGateReportSectionId,
)
from ai_adoption_engine.models.four_gate_integrated_assessment import (
    FourGateIntegratedAssessmentSuccess,
)
from ai_adoption_engine.models.review import ApprovedProcessReview

from .contracts import (
    COHORT_PROTOCOL_VERSION,
    DEVELOPMENT_FIXTURE_EXCLUSION,
    CohortContractError,
    FourGateApprovedReviewPin,
    FourGateCaseFreezeManifest,
    FourGateCohortManifest,
    FourGateCohortPin,
    FourGateCohortRun,
    FourGateCohortSummary,
    FourGateDeterministicRepeatability,
    FourGateDevelopmentCaseManifest,
    FourGateDevelopmentCaseResult,
    FourGateFreezeFile,
    FourGateMeasure,
    FourGateSourcePin,
    FourGateTraceabilityChecks,
    MeasureState,
)


_NOT_APPLICABLE_REFERENCE_REASON = (
    "Synthetic development fixtures have no independent human reference annotations."
)
_NOT_APPLICABLE_CLAIM_REASON = (
    "Development fixtures are excluded from real-world performance, effectiveness, "
    "ROI, deployment-safety, threshold-quality, and generalisation claims."
)


def _canonical_bytes(value: object) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _validated_case_manifest(value: object) -> FourGateDevelopmentCaseManifest:
    try:
        payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
        return FourGateDevelopmentCaseManifest.model_validate(payload)
    except (AttributeError, TypeError, ValueError, ValidationError) as exc:
        raise CohortContractError(
            "Case is not an exact four-gate development-fixture contract"
        ) from exc


def _validated_review(value: object) -> ApprovedProcessReview:
    try:
        payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
        return ApprovedProcessReview.model_validate(payload)
    except (AttributeError, TypeError, ValueError, ValidationError) as exc:
        raise CohortContractError("Approved-review artifact is malformed") from exc


class FourGateDevelopmentCohortHarness:
    """Run only the explicit Phase 5/6 successor route with an exact policy pin."""

    def __init__(self, policy_path: str | Path) -> None:
        self.policy_path = Path(policy_path)
        try:
            self.policy = load_four_gate_policy(self.policy_path)
        except Exception as exc:
            raise CohortContractError(
                "The explicit successor policy could not be loaded"
            ) from exc
        fingerprint = fingerprint_four_gate_policy(self.policy)
        try:
            self.contract = FourGateCohortPin(
                decision_policy_fingerprint=fingerprint
            )
        except ValidationError as exc:
            raise CohortContractError(
                "The loaded policy is not the exact successor contract"
            ) from exc
        if (
            self.policy.policy_id != self.contract.decision_policy_id
            or self.policy.version != self.contract.decision_policy_version
            or self.policy.framework_id != self.contract.framework_id
            or self.policy.framework_version != self.contract.framework_version
            or self.policy.decision_contract_version
            != self.contract.phase1_contract_version
        ):
            raise CohortContractError(
                "The loaded policy is not the exact successor contract"
            )

    def build_case_manifest(
        self,
        *,
        case_id: str,
        title: str,
        source_filename: str,
        source_bytes: bytes,
        approved_review: ApprovedProcessReview,
        frozen_before_at,
    ) -> FourGateDevelopmentCaseManifest:
        review = _validated_review(approved_review)
        lineage = _review_pin(review)
        return FourGateDevelopmentCaseManifest(
            case_id=case_id,
            title=title,
            frozen_before_at=frozen_before_at,
            contract=self.contract,
            source=FourGateSourcePin(
                source_identifier=lineage.source_document_id,
                source_filename=source_filename,
                byte_length=len(source_bytes),
                sha256=_sha256(source_bytes),
            ),
            approved_review=lineage,
        )

    def run_case(
        self,
        manifest: object,
        *,
        source_bytes: bytes,
        approved_review: object,
    ) -> FourGateDevelopmentCaseResult:
        case = _validated_case_manifest(manifest)
        review = _validated_review(approved_review)
        self._validate_inputs(case, source_bytes, review)

        run_id = "four-gate-cohort-run-" + _sha256(
            _canonical_bytes(
                {
                    "case": case.model_dump(mode="json"),
                    "approved_review": review.model_dump(mode="json"),
                }
            )
        )
        assessment_run_id = f"{run_id}:phase5-v0.2"

        def assess_once() -> FourGateIntegratedAssessmentSuccess:
            result = FourGateIntegratedAssessmentService(
                policy_loader=lambda: self.policy,
                clock=lambda: case.frozen_before_at,
                run_id_factory=lambda: assessment_run_id,
            ).assess(review)
            if not isinstance(result, FourGateIntegratedAssessmentSuccess):
                raise CohortContractError(
                    "Explicit successor Phase 5 failed closed for this case"
                )
            return result

        first_integrated = assess_once()
        first_package = FourGateDecisionSupportPackageService().generate(
            first_integrated
        )
        repeated_integrated = assess_once()
        repeated_package = FourGateDecisionSupportPackageService().generate(
            repeated_integrated
        )
        if not isinstance(first_package, FourGateDecisionPackageSuccess) or not isinstance(
            repeated_package, FourGateDecisionPackageSuccess
        ):
            raise CohortContractError(
                "Explicit successor Phase 6 failed closed for this case"
            )

        first_bytes = _canonical_bytes(
            {
                "integrated_assessment": first_integrated.model_dump(mode="json"),
                "decision_package": first_package.model_dump(mode="json"),
            }
        )
        repeated_bytes = _canonical_bytes(
            {
                "integrated_assessment": repeated_integrated.model_dump(mode="json"),
                "decision_package": repeated_package.model_dump(mode="json"),
            }
        )
        if first_bytes != repeated_bytes:
            raise CohortContractError(
                "Identical approved input and policy were not byte-stable"
            )

        checks = _traceability_checks(review, first_integrated, first_package)
        steps = first_integrated.process_assessment.step_assessments
        not_evaluated = sum(
            gate.status is FourGateStatus.NOT_EVALUATED
            for step in steps
            for gate in step.gate_results
        )
        run = FourGateCohortRun(
            run_id=run_id,
            case_id=case.case_id,
            contract=case.contract,
            source=case.source,
            approved_review=case.approved_review,
            integrated_assessment=first_integrated,
            decision_package=first_package,
            traceability=checks,
            repeatability=FourGateDeterministicRepeatability(
                first_semantic_sha256=_sha256(first_bytes),
                repeated_semantic_sha256=_sha256(repeated_bytes),
            ),
        )
        return FourGateDevelopmentCaseResult(
            manifest=case,
            run=run,
            outcomes=[step.outcome_code for step in steps],
            not_evaluated_gate_count=not_evaluated,
            total_gate_count=4 * len(steps),
            measures=[
                FourGateMeasure(
                    measure_id="contract-and-traceability-checks",
                    state=MeasureState.OBSERVED,
                    numerator=checks.passed_count,
                    denominator=checks.check_count,
                ),
                FourGateMeasure(
                    measure_id="deterministic-semantic-repeatability",
                    state=MeasureState.OBSERVED,
                    numerator=1,
                    denominator=1,
                ),
                FourGateMeasure(
                    measure_id="independent-reference-agreement",
                    state=MeasureState.NOT_APPLICABLE,
                    not_applicable_reason=_NOT_APPLICABLE_REFERENCE_REASON,
                ),
                FourGateMeasure(
                    measure_id="real-world-outcome-claims",
                    state=MeasureState.NOT_APPLICABLE,
                    not_applicable_reason=_NOT_APPLICABLE_CLAIM_REASON,
                ),
            ],
        )

    def summarize(
        self,
        cohort: object,
        results: Iterable[FourGateDevelopmentCaseResult],
    ) -> FourGateCohortSummary:
        try:
            payload = (
                cohort.model_dump(mode="json")
                if hasattr(cohort, "model_dump")
                else cohort
            )
            manifest = FourGateCohortManifest.model_validate(payload)
        except (AttributeError, TypeError, ValueError, ValidationError) as exc:
            raise CohortContractError("Cohort manifest is malformed") from exc
        if manifest.contract != self.contract:
            raise CohortContractError("Cohort contract pin does not match the policy")
        ordered = list(results)
        if [item.manifest.case_id for item in ordered] != manifest.case_ids:
            raise CohortContractError(
                "Cohort results must exactly match manifest case order"
            )
        if any(item.manifest.contract != self.contract for item in ordered):
            raise CohortContractError("Mixed case contract detected")
        outcomes = Counter(
            outcome for item in ordered for outcome in item.outcomes
        )
        checks_passed = sum(
            item.run.traceability.passed_count for item in ordered
        )
        checks_total = sum(item.run.traceability.check_count for item in ordered)
        return FourGateCohortSummary(
            cohort=manifest,
            case_count=len(ordered),
            valid_development_fixture_count=len(ordered),
            excluded_from_real_world_claim_count=len(ordered),
            outcome_counts={outcome: outcomes.get(outcome, 0) for outcome in OutcomeCode},
            not_evaluated_gate_count=sum(
                item.not_evaluated_gate_count for item in ordered
            ),
            total_gate_count=sum(item.total_gate_count for item in ordered),
            measures=[
                FourGateMeasure(
                    measure_id="contract-and-traceability-checks",
                    state=MeasureState.OBSERVED,
                    numerator=checks_passed,
                    denominator=checks_total,
                ),
                FourGateMeasure(
                    measure_id="deterministic-semantic-repeatability",
                    state=MeasureState.OBSERVED,
                    numerator=len(ordered),
                    denominator=len(ordered),
                ),
                FourGateMeasure(
                    measure_id="independent-reference-agreement",
                    state=MeasureState.NOT_APPLICABLE,
                    not_applicable_reason=_NOT_APPLICABLE_REFERENCE_REASON,
                ),
                FourGateMeasure(
                    measure_id="real-world-outcome-claims",
                    state=MeasureState.NOT_APPLICABLE,
                    not_applicable_reason=_NOT_APPLICABLE_CLAIM_REASON,
                ),
            ],
            disclosures=[
                DEVELOPMENT_FIXTURE_EXCLUSION,
                "This cohort validates contract execution and auditability only.",
                "No governed real-world cases or independent references are included.",
                "Inherited thresholds and weights remain provisional and are not "
                "academically validated.",
            ],
        )

    def _validate_inputs(
        self,
        case: FourGateDevelopmentCaseManifest,
        source_bytes: bytes,
        review: ApprovedProcessReview,
    ) -> None:
        if case.contract != self.contract:
            raise CohortContractError("Case contract pin does not match the policy")
        if (
            not isinstance(source_bytes, bytes)
            or not source_bytes
            or len(source_bytes) != case.source.byte_length
            or _sha256(source_bytes) != case.source.sha256
        ):
            raise CohortContractError("Source bytes do not match the immutable source pin")
        actual_review = _review_pin(review)
        if actual_review != case.approved_review:
            raise CohortContractError(
                "Approved review or its lineage does not match the case pin"
            )
        if case.source.source_identifier != actual_review.source_document_id:
            raise CohortContractError(
                "Source identifier does not match approved-review lineage"
            )


def _review_pin(review: ApprovedProcessReview) -> FourGateApprovedReviewPin:
    approval_events = [
        item for item in review.review.events if item.action.value == "approve"
    ]
    if len(approval_events) != 1:
        raise CohortContractError("Approved review must contain one approval event")
    return FourGateApprovedReviewPin(
        review_id=review.review.review_id,
        approval_event_id=approval_events[0].event_id,
        source_document_id=review.review.original_candidate.source_document_id,
        validated_process_id=review.business_process.process_id,
        validated_process_fingerprint=fingerprint_business_process(
            review.business_process
        ),
        approved_review_sha256=_sha256(_canonical_bytes(review)),
    )


def _traceability_checks(review, integrated, package_result):
    package = package_result.package
    assessed = integrated.process_assessment.step_assessments
    process_steps = review.business_process.steps
    ordered_step_coverage = [item.step_id for item in assessed] == [
        item.step_id for item in process_steps
    ] == [item.step_id for item in package.portfolio.items]
    four_ordered_gates = all(
        [gate.gate for gate in item.gate_results] == list(FourGateName)
        for item in assessed
    )
    not_evaluated_valid = all(_not_evaluated_suffix_is_valid(item) for item in assessed)
    typed_combinations_valid = all(
        source.outcome_code is packaged.outcome_code
        and source.change_disposition is packaged.change_disposition
        and source.readiness_disposition is packaged.readiness_disposition
        and source.selected_intervention_family
        is packaged.selected_intervention_family
        and source.autonomy_ceiling is packaged.autonomy_ceiling
        for source, packaged in zip(assessed, package.portfolio.items, strict=True)
    )
    appendix_ids = {item.evidence_id for item in package.evidence_appendix}
    evidence_lineage_resolved = all(
        evidence.evidence_id in appendix_ids
        for item in package.portfolio.items
        for evidence in item.material_evidence
    )
    retained_unknowns_preserved = all(
        _unknowns_preserved(source, assessed_step)
        for source, assessed_step in zip(process_steps, assessed, strict=True)
    )
    gaps_valid = all(
        bool(
            [
                gap
                for gap in item.information_gaps
                if gap.kind is FourGateInformationGapKind.ACTIVE_DECISION_BLOCKER
            ]
        )
        == (item.outcome_code is OutcomeCode.DISCOVERY_REQUIRED)
        for item in package.portfolio.items
    )
    report_complete = [
        section.section_id for section in package.report_content.sections
    ] == list(FourGateReportSectionId)
    lineage_valid = (
        integrated.lineage.review_id == review.review.review_id
        and integrated.lineage.source_document_id
        == review.review.original_candidate.source_document_id
        and integrated.lineage.validated_process_fingerprint
        == fingerprint_business_process(review.business_process)
        and package.source.lineage == integrated.lineage
    )
    if not all(
        (
            ordered_step_coverage,
            four_ordered_gates,
            not_evaluated_valid,
            typed_combinations_valid,
            evidence_lineage_resolved,
            retained_unknowns_preserved,
            gaps_valid,
            report_complete,
            lineage_valid,
        )
    ):
        raise CohortContractError("Successor output failed cohort traceability checks")
    return FourGateTraceabilityChecks()


def _not_evaluated_suffix_is_valid(step) -> bool:
    stopped = False
    for gate in step.gate_results:
        if gate.status is FourGateStatus.NOT_EVALUATED:
            stopped = True
        elif stopped:
            return False
    return True


def _unknowns_preserved(source, assessed) -> bool:
    assessed_criteria = {item.criterion: item for item in assessed.criteria}
    for criterion in CriterionName:
        source_value = source.characteristics.criterion(criterion)
        assessed_value = assessed_criteria[criterion]
        if source_value.knowledge_state is KnowledgeState.UNKNOWN and (
            assessed_value.knowledge_state is not KnowledgeState.UNKNOWN
            or assessed_value.value is not None
        ):
            return False
    accountability = source.characteristics.human_accountability_required
    if accountability.knowledge_state is KnowledgeState.UNKNOWN and (
        assessed.human_accountability.knowledge_state is not KnowledgeState.UNKNOWN
        or assessed.human_accountability.value is not None
    ):
        return False
    for source_signal, assessed_signal in zip(
        source.characteristics.capability_signals.model_dump().values(),
        assessed.capability_signals,
        strict=True,
    ):
        if source_signal["knowledge_state"] == KnowledgeState.UNKNOWN.value and (
            assessed_signal.knowledge_state is not KnowledgeState.UNKNOWN
            or assessed_signal.value is not None
        ):
            return False
    return True


def freeze_development_cohort(
    output_root: str | Path,
    cohort: FourGateCohortManifest,
    cases: Iterable[tuple[bytes, ApprovedProcessReview, FourGateDevelopmentCaseResult]],
    summary: FourGateCohortSummary,
) -> Path:
    """Write immutable, deterministic development artifacts outside Phase 8."""

    root = Path(output_root).resolve(strict=False)
    parts = root.parts
    if "evaluation" in parts and "portfolio" in parts:
        raise CohortContractError("Successor cohort output cannot target Phase 8")
    cohort_root = root / cohort.cohort_id
    _write_immutable(
        cohort_root / "cohort_manifest.v0.1.json", _canonical_bytes(cohort) + b"\n"
    )
    for source_bytes, review, result in cases:
        case_root = cohort_root / "cases" / result.manifest.case_id
        files = {
            "case_manifest.v0.1.json": _canonical_bytes(result.manifest) + b"\n",
            "source/source.txt": source_bytes,
            "review/approved_review.v0.1.json": _canonical_bytes(review) + b"\n",
            "successor_run/result.v0.1.json": result.canonical_json_bytes() + b"\n",
        }
        entries: list[FourGateFreezeFile] = []
        for relative, payload in files.items():
            _write_immutable(case_root / relative, payload)
            entries.append(
                FourGateFreezeFile(
                    relative_path=relative,
                    sha256=_sha256(payload),
                    byte_length=len(payload),
                )
            )
        freeze = FourGateCaseFreezeManifest(
            case_id=result.manifest.case_id,
            contract=result.manifest.contract,
            source=result.manifest.source,
            approved_review=result.manifest.approved_review,
            files=entries,
        )
        _write_immutable(
            case_root / "freeze_manifest.v0.1.json",
            _canonical_bytes(freeze) + b"\n",
        )
    _write_immutable(
        cohort_root / "cohort_summary.v0.1.json",
        summary.canonical_json_bytes() + b"\n",
    )
    _write_immutable(
        cohort_root / "cohort_summary.v0.1.md",
        _summary_markdown(summary).encode("utf-8"),
    )
    return cohort_root


def _write_immutable(path: Path, payload: bytes) -> None:
    if path.exists():
        if not path.is_file() or path.read_bytes() != payload:
            raise CohortContractError(f"Frozen cohort artifact changed: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _summary_markdown(summary: FourGateCohortSummary) -> str:
    lines = [
        "# Four-gate synthetic development cohort",
        "",
        DEVELOPMENT_FIXTURE_EXCLUSION,
        "",
        f"Protocol: {summary.cohort.contract.cohort_protocol}",
        (
            "Framework: "
            f"{summary.cohort.contract.framework_id} "
            f"/ {summary.cohort.contract.framework_version}"
        ),
        (
            "Decision policy: "
            f"{summary.cohort.contract.decision_policy_id} "
            f"/ {summary.cohort.contract.decision_policy_version}"
        ),
        (
            "Policy fingerprint: "
            f"{summary.cohort.contract.decision_policy_fingerprint}"
        ),
        (
            "Contracts: "
            f"{summary.cohort.contract.phase1_contract_version}, "
            f"{summary.cohort.contract.phase5_schema_version}, "
            f"{summary.cohort.contract.phase6_schema_version}"
        ),
        "",
        f"Cases: {summary.case_count}",
        (
            "Not-evaluated gates: "
            f"{summary.not_evaluated_gate_count}/{summary.total_gate_count}"
        ),
        "",
        "## Outcome counts",
        "",
    ]
    lines.extend(
        f"- {outcome.value}: {summary.outcome_counts[outcome]}"
        for outcome in OutcomeCode
    )
    lines.extend(("", "## Measures", ""))
    for measure in summary.measures:
        if measure.state is MeasureState.NOT_APPLICABLE:
            lines.append(
                f"- {measure.measure_id}: not applicable — "
                f"{measure.not_applicable_reason}"
            )
        else:
            lines.append(
                f"- {measure.measure_id}: {measure.numerator}/{measure.denominator}"
            )
    lines.extend(("", "## Disclosures", ""))
    lines.extend(f"- {item}" for item in summary.disclosures)
    return "\n".join(lines) + "\n"


__all__ = [
    "COHORT_PROTOCOL_VERSION",
    "FourGateDevelopmentCohortHarness",
    "freeze_development_cohort",
]

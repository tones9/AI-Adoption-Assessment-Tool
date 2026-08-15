"""Stage 2 operator script for the PORT-003 retrospective portfolio validation run.

Scope
-----
Source-bounded Phase 4 human review and explicit approval, then the deterministic
Phase 5 integrated assessment and Phase 6 decision-support package, followed by
export of the remaining product artefacts. This script adds no product logic and
changes no policy, prompt, schema, model configuration, threshold or taxonomy.

Review discipline
-----------------
Every decision below is justified only by wording visible in the frozen PORT-003
BEFORE document, which is already embedded in the persisted Phase 2 artefact. This
script therefore reads no case files at all: it operates on the workspace database
produced by stage 1.

The review may accept supported assertions, accept transparently inferred ones,
correct signals the frozen evidence clearly supports, and retain everything else as
unknown. It must not import AFTER evidence, organisation knowledge, industry norms,
invented risk, volume or ROI values.

Recorded review decisions
-------------------------
1. Accept every assertion the extraction supported with resolved evidence.
2. Make no capability corrections. The live extraction already identified
   ``creates_new_content`` as true on both step 2 ("records notes and action items")
   and step 4 ("prepares a meeting summary"), each with resolved source evidence, so
   there is no supported signal left for review to recover. Introducing any further
   positive signal would exceed the frozen BEFORE evidence.
3. Accept the step 4 -> step 3 "uses output of" dependency. The source states the
   summary is prepared "from the cleaned notes", and cleaned notes are the documented
   output of step 3, so the inference is transparent and order-consistent.
4. Accept the explicit numbered step order.
5. Retain every remaining unknown as unknown, including all ten decision criteria on
   every step, action-item routing or orchestration, document reading, decision
   support, and human accountability on steps 2 to 4.

Unlike PORT-002, where Phase 4 recovered three capability signals the extraction had
missed, this review contributes no capability recovery. Its contribution is
verification, explicit disposition of every assertion, and retention of unknowns.

Usage
-----
Preview every review decision without writing anything::

    .venv/bin/python evaluation/portfolio/_run_port003_stage2.py --dry-run

Apply the review, approve, assess, generate the package and export::

    .venv/bin/python evaluation/portfolio/_run_port003_stage2.py --apply

No ``PYTHONPATH`` is required; this script prepends ``src/`` to ``sys.path``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
PORTFOLIO = SCRIPT_PATH.parent
ROOT = PORTFOLIO.parents[1]

sys.path.insert(0, str(ROOT / "src"))

CASE_ID = "PORT-003"
RUN_DIR = PORTFOLIO / "runs" / "port-003" / "production-run-v0.1"
DATABASE_PATH = RUN_DIR / "workspace.db"

# Capability signals the live extraction is expected to have identified unaided.
# Verified, never mutated: if this precondition fails the candidate has changed and
# the recorded review reasoning would no longer describe the artefact.
EXPECTED_EXTRACTION_SIGNALS = {
    (2, "creates_new_content"): True,
    (4, "creates_new_content"): True,
}
ACCEPT_RATIONALE = (
    "The assertion is supported by, or transparently inferred from, the frozen BEFORE document."
)
UNKNOWN_RATIONALE = (
    "The frozen BEFORE document does not supply this value; retain it as unknown."
)
ORDER_RATIONALE = (
    "The four retained activities follow the explicit numbered order in the frozen BEFORE document."
)
DEPENDENCY_RATIONALE = (
    "The source states the summary is prepared from the cleaned notes, which are the "
    "documented output of the preceding review-and-cleanup activity."
)
APPROVAL_RATIONALE = (
    "Approved solely against the frozen PORT-003 BEFORE document. Every source-supported "
    "assertion was accepted, the order-consistent dependency was accepted, no capability "
    "signal required correction, and all genuinely missing assessment information was "
    "retained as unknown."
)


class CaseDataBoundaryError(RuntimeError):
    """A forbidden portfolio case file was opened during the production run."""


def install_case_data_guard() -> None:
    """Abort if any portfolio file outside this run's own directory is opened."""

    portfolio_root = os.path.realpath(PORTFOLIO)
    allowed_files = {os.path.realpath(SCRIPT_PATH)}
    allowed_tree = os.path.realpath(RUN_DIR)

    def hook(event: str, args: tuple[Any, ...]) -> None:
        if event not in {"open", "os.open", "sqlite3.connect"}:
            return
        target = args[0]
        if not isinstance(target, (str, bytes, os.PathLike)):
            return
        try:
            resolved = os.path.realpath(os.fsdecode(target))
        except Exception:  # pragma: no cover - defensive only
            return
        if not resolved.startswith(portfolio_root + os.sep):
            return
        if resolved in allowed_files:
            return
        if resolved == allowed_tree or resolved.startswith(allowed_tree + os.sep):
            return
        raise CaseDataBoundaryError(
            f"{CASE_ID} case-data guard refused to open {resolved}. "
            "Stage 2 may touch only this run's own output directory."
        )

    sys.addaudithook(hook)


def write_json(path: Path, payload: Any) -> None:
    document = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def locate_assessment_id() -> str:
    connection = sqlite3.connect(DATABASE_PATH)
    try:
        row = connection.execute(
            "SELECT assessment_id FROM assessments ORDER BY created_at"
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise SystemExit(f"{CASE_ID} workspace contains no assessment")
    return row[0]


def review_assertion(service: Any, session: Any, assertion: Any, field_path: str) -> None:
    """Explicitly dispose of one assertion: accept if supported, else retain unknown."""

    from ai_adoption_engine.models.enums import KnowledgeState

    if assertion.knowledge_state is KnowledgeState.UNKNOWN:
        service.retain_unknown(session, assertion, field_path, rationale=UNKNOWN_RATIONALE)
    else:
        service.accept_assertion(session, assertion, field_path, rationale=ACCEPT_RATIONALE)


def review_collection(service: Any, session: Any, collection: Any, field_path: str) -> None:
    for index, item in enumerate(collection.items):
        review_assertion(service, session, item, f"{field_path}[{index}]")


def verify_extraction_signals(session: Any) -> None:
    """Assert which positive capability signals the live extraction produced unaided.

    This is a read-only precondition. The review does not add, correct or remove any
    capability signal; it records that the extraction found these without human help.
    """

    from ai_adoption_engine.models.enums import KnowledgeState

    observed: dict[tuple[int, str], Any] = {}
    for step in session.steps:
        for signal in step.capability_signals:
            assertion = signal.assertion
            if assertion.knowledge_state is not KnowledgeState.UNKNOWN:
                observed[(step.sequence, str(signal.name))] = assertion.value

    if observed != EXPECTED_EXTRACTION_SIGNALS:
        raise SystemExit(
            "The candidate's positive capability signals are not what the recorded "
            f"review reasoning describes.\n  expected {EXPECTED_EXTRACTION_SIGNALS}\n"
            f"  observed {observed}"
        )

    print("\n--- CAPABILITY SIGNALS IDENTIFIED BY PHASE 3 (unaided) ---")
    for (sequence, name), value in sorted(observed.items()):
        print(f"  step {sequence}  {name} = {value}")
    print("  Phase 4 adds no capability signal; no supported signal was missed.")


def perform_review(service: Any, session: Any) -> None:
    verify_extraction_signals(session)

    review_assertion(service, session, session.process_name, "process.process_name")
    review_assertion(
        service, session, session.process_description, "process.process_description"
    )
    review_assertion(
        service, session, session.process_objective, "process.process_objective"
    )

    for step in session.steps:
        prefix = f"steps.{step.candidate_step_id}"
        review_assertion(service, session, step.document_order, f"{prefix}.document_order")
        review_assertion(service, session, step.activity, f"{prefix}.activity")
        review_assertion(service, session, step.description, f"{prefix}.description")
        for name in (
            "actors",
            "responsible_roles",
            "systems",
            "inputs",
            "outputs",
            "exceptions",
            "operational_characteristics",
        ):
            review_collection(service, session, getattr(step, name), f"{prefix}.{name}")
        for index, decision in enumerate(step.decisions):
            review_assertion(
                service, session, decision.condition, f"{prefix}.decisions[{index}].condition"
            )
            review_collection(
                service, session, decision.branches, f"{prefix}.decisions[{index}].branches"
            )
        for index, dependency in enumerate(step.dependencies):
            review_assertion(
                service,
                session,
                dependency.target_label,
                f"{prefix}.dependencies[{index}].target_label",
            )
            review_assertion(
                service,
                session,
                dependency.relationship,
                f"{prefix}.dependencies[{index}].relationship",
            )
        for criterion in step.criteria:
            review_assertion(
                service,
                session,
                criterion.assertion,
                f"{prefix}.criteria.{criterion.name.value}",
            )
        review_assertion(
            service,
            session,
            step.human_accountability_required,
            f"{prefix}.human_accountability_required",
        )
        for signal in step.capability_signals:
            review_assertion(
                service,
                session,
                signal.assertion,
                f"{prefix}.capability_signals.{signal.name}",
            )

    service.accept_step_order(session, rationale=ORDER_RATIONALE)


def report_review(session: Any) -> None:
    counts = Counter(event.action.value for event in session.events)
    print("\n--- PHASE 4 REVIEW EVENTS ---")
    for action, count in sorted(counts.items()):
        print(f"  {action:<20} {count}")
    print(f"  {'TOTAL':<20} {sum(counts.values())}")

    mutations = [
        event
        for event in session.events
        if event.action.value in {"correct", "correct-dependency", "reject", "resolve-unknown"}
    ]
    print("\n--- CORRECTIONS / REJECTIONS ---")
    if not mutations:
        print("  none - the review accepted or retained every assertion as extracted")
    for event in mutations:
        print(f"  {event.action.value}  {event.field_path}")
        print(f"    {event.rationale}")

    print("\n--- RETAINED UNKNOWN SAMPLE (first 6) ---")
    unknown = [e for e in session.events if e.action.value == "retain-unknown"]
    for event in unknown[:6]:
        print(f"  {event.field_path}")
    print(f"  ... {len(unknown)} retained unknown in total")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the review in memory and print the decisions without persisting.",
    )
    group.add_argument(
        "--apply",
        action="store_true",
        help="Persist the review, approve, assess, generate the package and export.",
    )
    args = parser.parse_args(argv)

    install_case_data_guard()

    if not DATABASE_PATH.exists():
        raise SystemExit(f"{DATABASE_PATH.relative_to(ROOT)} is missing; run stage 1 first.")

    from ai_adoption_engine.models.decision_support import DecisionPackageSuccess
    from ai_adoption_engine.models.integrated_assessment import IntegratedAssessmentSuccess
    from ai_adoption_engine.workspace.composition import build_workspace_service

    assessment_id = locate_assessment_id()
    service = build_workspace_service(DATABASE_PATH)
    workspace = service.repository.load_workspace(assessment_id)
    stage = workspace.assessment.current_stage.value
    print(f"assessment_id      {assessment_id}")
    print(f"current_stage      {stage}")
    # "in-review" is valid re-entry: start_review is idempotent and returns the
    # persisted session, which a previous --dry-run may already have created.
    if stage not in {"candidate-ready", "in-review"}:
        raise SystemExit(
            f"{CASE_ID} must be at candidate-ready or in-review; found {stage}."
        )

    session = service.start_review(assessment_id)
    perform_review(service.review_service, session)
    report_review(session)

    if args.dry_run:
        print("\nDRY RUN - nothing was persisted beyond the review session start.")
        print("Re-run with --apply to approve, assess and export.")
        return 0

    service.save_review(assessment_id, session)
    write_json(RUN_DIR / "review_session.json", session)

    approval = service.approve(assessment_id, rationale=APPROVAL_RATIONALE)
    if approval.approved is None:
        for error in approval.errors:
            print(f"  approval error: {error.code} {error.field_path or ''} {error.message}")
        raise SystemExit("Approval failed.")
    approved = approval.approved
    write_json(RUN_DIR / "approval_result.json", approval)
    write_json(RUN_DIR / "approved_review.json", approved)
    write_json(RUN_DIR / "validated_business_process.json", approved.business_process)
    print(f"\napproval_event_id  {approved.review.events[-1].event_id}")
    print(f"validated_steps    {len(approved.business_process.steps)}")

    integrated = service.assess(assessment_id)
    if not isinstance(integrated, IntegratedAssessmentSuccess):
        raise SystemExit(f"Integrated assessment failed: {integrated}")
    write_json(RUN_DIR / "integrated_assessment.json", integrated)

    print("\n--- PHASE 5 DETERMINISTIC ASSESSMENT ---")
    distribution: Counter[str] = Counter()
    for item in integrated.process_assessment.step_assessments:
        mode = item.recommendation_mode.value
        distribution[mode] += 1
        capabilities = [capability.value for capability in item.capabilities] or ["none"]
        failed = [
            gate.gate.value for gate in item.gate_results if gate.status.value == "failed"
        ]
        print(f"  step {item.step_id[-8:]}  {item.activity[:38]:<38} {mode}")
        print(f"      capabilities={capabilities} failed_gates={failed}")
    print(f"  distribution: {dict(distribution)}")

    package = service.generate_package(assessment_id)
    if not isinstance(package, DecisionPackageSuccess):
        raise SystemExit(f"Decision package failed: {package}")
    write_json(RUN_DIR / "decision_package_result.json", package)
    print("\n--- PHASE 6 DECISION PACKAGE ---")
    print(f"  package_id          {package.package.package_id}")
    print(f"  portfolio_items     {len(package.package.portfolio.items)}")
    print(f"  future_state_status {package.package.future_state.status.value}")
    print(f"  completeness        {package.package.completeness.value}")

    final = service.repository.load_workspace(assessment_id)
    active = {
        artifact_type.value: {
            "artifact_id": stored.artifact_id,
            "artifact_revision": stored.artifact_revision,
            "parent_artifact_id": stored.parent_artifact_id,
            "payload_sha256": stored.payload_sha256,
        }
        for artifact_type, stored in final.active_artifacts.items()
    }
    run_state = {
        "active_artifacts": active,
        "approval_event_id": approved.review.events[-1].event_id,
        "approval_timestamp": approved.approval.approved_at.isoformat(),
        "assessed_at": integrated.metadata.assessed_at.isoformat(),
        "assessment_id": assessment_id,
        "assessment_run_id": integrated.metadata.assessment_run_id,
        "decision_policy_fingerprint": integrated.policy.decision_policy_fingerprint,
        "document_id": final.assessment.document_id,
        "extraction_run_id": session.original_candidate.extraction_run_id,
        "future_state_status": package.package.future_state.status.value,
        "integration_schema_version": integrated.metadata.integration_schema_version,
        "package_completeness": package.package.completeness.value,
        "package_id": package.package.package_id,
        "phase1_contract_version": integrated.metadata.phase1_contract_version,
        "policy_id": integrated.policy.policy_id,
        "policy_status": integrated.policy.policy_status,
        "policy_version": integrated.policy.policy_version,
        "recommendations": {
            item.step_id: item.recommendation_mode.value
            for item in integrated.process_assessment.step_assessments
        },
        "review_event_counts": dict(
            Counter(event.action.value for event in approved.review.events)
        ),
        "review_id": session.review_id,
        "roi_statement": package.package.roi_statement,
        "source_document_id": integrated.lineage.source_document_id,
        "source_sha256": final.assessment.document_id.removeprefix("doc-"),
        "validated_process_fingerprint": integrated.lineage.validated_process_fingerprint,
        "validated_process_id": integrated.lineage.validated_process_id,
        "workflow_stage": final.assessment.current_stage.value,
    }
    write_json(RUN_DIR / "final_run_state.json", run_state)

    print("\n--- STAGE 2 ARTEFACTS WRITTEN ---")
    for name in sorted(path.name for path in RUN_DIR.iterdir() if path.is_file()):
        digest = hashlib.sha256((RUN_DIR / name).read_bytes()).hexdigest()
        print(f"  {digest}  {name}")
    print("\nStage 2 complete. Workflow stage:", final.assessment.current_stage.value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

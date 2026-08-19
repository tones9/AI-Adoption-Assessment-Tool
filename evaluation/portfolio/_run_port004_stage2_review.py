"""Stage 2 (Phase 4 human review) preparation script for PORT-004.

Scope
-----
This script prepares Phase 4 human review for PORT-004 (USPTO patent examiner
prior-art search workflow). It does not perform review. Its only implemented
mode, ``--dry-run``, is strictly in-memory: it loads the frozen Stage 1
candidate, starts a review session, and enumerates the resulting state so a
human can decide what review actions to take. It never accepts, corrects,
rejects, resolves a conflict, resolves a dependency, removes or reorders a
step, approves, or runs assessment.

A second mode, ``--confirm-init-stage2-workspace``, exists in this file only as
a documented, hard-refusing stub -- mirroring the pattern used in
``_run_port004_stage1.py``, where ``--confirm-live-call`` existed before it was
authorised to do anything. It is not implemented yet. When it is, it will copy
``evaluation/portfolio/runs/port-004/production-run-v0.1/workspace.db`` into a
new Stage 2 working directory and never open the frozen copy for writing.
Until then it refuses unconditionally, and no persistent Stage 2 workspace is
created by this file.

Why dry-run loads the JSON, not the frozen database
-----------------------------------------------------
The frozen ``workspace.db`` is hash-verified below for provenance, exactly as
instructed, but it is never opened with ``sqlite3.connect`` in this script.
Opening a SQLite file, even nominally read-only, is a filesystem operation
this script should not need in a mode whose entire contract is "writes
nothing." The Stage 1 record already confirmed the database's stored
``CANDIDATE_EXTRACTION_RESULT`` payload is byte-identical to
``candidate_extraction.json`` (same recorded ``payload_sha256``), so loading
the JSON file directly, verified by its own pinned hash, is equivalent and
strictly safer.

Case-data boundary
-------------------
The only files this script may read are the frozen BEFORE corpus (hash check
only), the frozen candidate JSON, and the frozen Stage 1 workspace.db (hash
check only, opened as raw bytes, never via sqlite3). It must never read
PORT-001/002/003 material, any sealed AFTER packet (none exists for PORT-004),
the case register, provenance manifests, leakage audits, source captures, or
OCR-derived material. Enforced by an explicit allowlist and a
``sys.addaudithook`` guard, as in the Stage 1 script.

Evidence-choice fidelity
--------------------------
"Enumerate available evidence choices per step exactly as the current UI would
expose them" is implemented by importing the UI's own, pure (no Streamlit
calls), private helper --
``ai_adoption_engine.presentation.pages.review._step_evidence_choices`` -- and
its label formatter, rather than re-implementing similar logic that could
silently drift from what a reviewer actually sees. This is a private API and
may break if that module changes; that risk is accepted here in exchange for
exact parity.

Provenance discipline
------------------------
Per the explicit correction to this task: no material criterion is
pre-classified as incapable of a DOCUMENT_SUPPORTED path. For every one of the
10 criteria and human_accountability_required, on every retained step, this
script reports the same three facts a human needs to decide for themselves:
whether the product wires an evidence_choices pathway for that field type at
all, how many already-resolved evidence references exist on that step (the
reusable pool, computed identically to the UI), and the field's current
knowledge_state/origin/evidence count. It does not decide, suggest, or apply
a value for any of them. Capability signals are reported the same way; the UI
does not wire evidence_choices for them, which is reported as an observed
fact about the current product, not a judgement that they cannot be
document-supported in principle.

The two ambiguous dependencies are handled the same way: a literal ordinal
match against ``target_label`` is computed and printed as a labelled human
review option, never applied. No Phase 3 evidence is minted; only existing
resolved evidence already present in candidate_extraction.json is surfaced.

Usage
-----
Inspect the full Phase 4 starting state, with no write and no persistence::

    .venv/bin/python evaluation/portfolio/_run_port004_stage2_review.py --dry-run

The other flag exists and refuses; see above::

    .venv/bin/python evaluation/portfolio/_run_port004_stage2_review.py --confirm-init-stage2-workspace

No ``PYTHONPATH`` is required; this script prepends ``src/`` to ``sys.path``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
PORTFOLIO = SCRIPT_PATH.parent
ROOT = PORTFOLIO.parents[1]

sys.path.insert(0, str(ROOT / "src"))

CASE_ID = "PORT-004"

STAGE1_RUN_DIR = PORTFOLIO / "runs" / "port-004" / "production-run-v0.1"
CANDIDATE_PATH = STAGE1_RUN_DIR / "candidate_extraction.json"
STAGE1_DATABASE_PATH = STAGE1_RUN_DIR / "workspace.db"
BEFORE_PATH = PORTFOLIO / "product_inputs" / "port-004.before.txt"

EXPECTED_CANDIDATE_SHA256 = (
    "ffbefc0eef7ad68b90859576d60aa0c09606c1eb6fd267d4fe2dca13b2c8ad65"
)
EXPECTED_STAGE1_DATABASE_SHA256 = (
    "f4a5c97503ec9a7f3c989fec8a2d5048f0678f2994e9b93e52802af55d2ac49f"
)
EXPECTED_BEFORE_SHA256 = (
    "98fd4ecece92f0bec27664241013677af1bd67e15816d3f8ba2291b23e017c01"
)
EXPECTED_FINGERPRINT = (
    "3c5c86bd132d25745ee7fcba2e40c3e3d796a9ff404a36a93aecce60cbaf1a85"
)

# Not created by this script. Documented here so the eventual persistent mode's
# location is fixed and reviewable before it is implemented.
STAGE2_RUN_DIR = PORTFOLIO / "runs" / "port-004" / "production-run-v0.2-review"

# Documentary only; enforced by the allowlist guard below, not by this tuple.
FORBIDDEN_CASE_MATERIAL = (
    "evaluation/portfolio/register.v0.1.json",
    "evaluation/portfolio/register.v0.2.json",
    "evaluation/portfolio/hashes.sha256",
    "evaluation/portfolio/freeze_manifest.v0.1.json",
    "evaluation/portfolio/cross_case_summary.v0.1.json",
    "evaluation/portfolio/cross_case_summary.v0.1.md",
    "evaluation/portfolio/provenance/",
    "evaluation/portfolio/leakage_audits/",
    "evaluation/portfolio/source_captures/",
    "evaluation/portfolio/sealed_after/",
    "evaluation/portfolio/product_inputs/port-001.before.txt",
    "evaluation/portfolio/product_inputs/port-002.before.txt",
    "evaluation/portfolio/product_inputs/port-003.before.txt",
    "evaluation/portfolio/runs/port-001/",
    "evaluation/portfolio/runs/port-002/",
    "evaluation/portfolio/runs/port-003/",
    "evaluation/portfolio/port-003-supersession-note.v0.1.md",
    "evaluation/portfolio/port-004.correction-note.v0.1.md",
    "evaluation/portfolio/port-004.freeze-record.v0.1.md",
    "evaluation/portfolio/runs/port-004/stage1-observation-record.v0.1.md",
    "evaluation/portfolio/runs/port-004/port-004.run-hashes.sha256",
    "evaluation/portfolio/runs/port-004/production-run-v0.1/ingestion_result.json",
    "evaluation/portfolio/runs/port-004/production-run-v0.1/run_state_after_extraction.json",
)


class CaseDataBoundaryError(RuntimeError):
    """A forbidden portfolio case file was opened during Stage 2 preparation."""


def install_case_data_guard() -> None:
    """Abort the process if any portfolio file outside the allowlist is opened."""

    portfolio_root = os.path.realpath(PORTFOLIO)
    allowed_files = {
        os.path.realpath(BEFORE_PATH),
        os.path.realpath(CANDIDATE_PATH),
        os.path.realpath(STAGE1_DATABASE_PATH),
        os.path.realpath(SCRIPT_PATH),
    }

    def hook(event: str, args: tuple[Any, ...]) -> None:
        if event not in {"open", "os.open", "sqlite3.connect"}:
            return
        if event == "sqlite3.connect":
            # No sqlite connection is permitted anywhere in --dry-run. The
            # frozen database is hash-verified as raw bytes only.
            raise CaseDataBoundaryError(
                f"{CASE_ID} Stage 2 dry-run refused a sqlite3.connect call. "
                "The frozen Stage 1 database is verified by hash only and is "
                "never opened as a database in this mode."
            )
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
        raise CaseDataBoundaryError(
            f"{CASE_ID} Stage 2 case-data guard refused to open {resolved}. "
            "Only the frozen BEFORE document, the frozen candidate JSON, the "
            "frozen Stage 1 database (hash check only) and this script are "
            "permitted in --dry-run."
        )

    sys.addaudithook(hook)


def production_fingerprint() -> str:
    listing = subprocess.run(
        ["git", "ls-files", "config", "src", "streamlit_app.py", "pyproject.toml"],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    ).stdout.split()
    lines = [
        f"{hashlib.sha256((ROOT / name).read_bytes()).hexdigest()}  {name}"
        for name in sorted(listing)
    ]
    return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()


def run_safety_checks() -> bytes:
    """Verify every hard-checked hash. Returns the candidate JSON bytes.

    Aborts on any mismatch, before anything else runs.
    """

    print("--- SAFETY CHECKS ---")

    if not CANDIDATE_PATH.is_file():
        raise SystemExit(f"ABORT: frozen candidate is missing: {CANDIDATE_PATH}")
    candidate_bytes = CANDIDATE_PATH.read_bytes()
    candidate_digest = hashlib.sha256(candidate_bytes).hexdigest()
    print(f"  candidate_extraction.json  {CANDIDATE_PATH.relative_to(ROOT)}")
    print(f"    sha256                   {candidate_digest}")
    if candidate_digest != EXPECTED_CANDIDATE_SHA256:
        raise SystemExit(
            "ABORT: frozen candidate hash mismatch.\n"
            f"  expected {EXPECTED_CANDIDATE_SHA256}\n"
            f"  actual   {candidate_digest}\n"
            "Refusing to prepare review against an unfrozen candidate."
        )
    print("    hash                     MATCH")

    if not STAGE1_DATABASE_PATH.is_file():
        raise SystemExit(f"ABORT: frozen Stage 1 database is missing: {STAGE1_DATABASE_PATH}")
    db_digest = hashlib.sha256(STAGE1_DATABASE_PATH.read_bytes()).hexdigest()
    print(f"  workspace.db (Stage 1)     {STAGE1_DATABASE_PATH.relative_to(ROOT)}")
    print(f"    sha256                   {db_digest}")
    if db_digest != EXPECTED_STAGE1_DATABASE_SHA256:
        raise SystemExit(
            "ABORT: frozen Stage 1 database hash mismatch.\n"
            f"  expected {EXPECTED_STAGE1_DATABASE_SHA256}\n"
            f"  actual   {db_digest}\n"
            "The frozen Stage 1 artefact is no longer in its frozen state. "
            "Nothing was read from it as a database."
        )
    print("    hash                     MATCH (verified as raw bytes; never opened as a database)")

    if not BEFORE_PATH.is_file():
        raise SystemExit(f"ABORT: frozen BEFORE corpus is missing: {BEFORE_PATH}")
    before_digest = hashlib.sha256(BEFORE_PATH.read_bytes()).hexdigest()
    print(f"  BEFORE corpus              {BEFORE_PATH.relative_to(ROOT)}")
    print(f"    sha256                   {before_digest}")
    if before_digest != EXPECTED_BEFORE_SHA256:
        raise SystemExit(
            "ABORT: frozen BEFORE corpus hash mismatch.\n"
            f"  expected {EXPECTED_BEFORE_SHA256}\n"
            f"  actual   {before_digest}"
        )
    print("    hash                     MATCH")

    fingerprint = production_fingerprint()
    print(f"  production fingerprint     {fingerprint}")
    if fingerprint != EXPECTED_FINGERPRINT:
        raise SystemExit(
            "ABORT: production subtree fingerprint mismatch.\n"
            f"  expected {EXPECTED_FINGERPRINT}\n"
            f"  actual   {fingerprint}\n"
            "Production code has changed since this script was approved."
        )
    print("    fingerprint              MATCH")
    print("  all safety checks          PASSED")
    return candidate_bytes


# --------------------------------------------------------------------------
# Dry-run reporting. Every function below is read-only: it builds Python
# objects in memory and prints them. Nothing here calls .save(), .write(),
# sqlite3.connect, or any ProcessReviewService method that mutates a session
# in a way that would be mistaken for an applied review decision (accept,
# correct, reject, resolve_unknown, retain_unknown, reorder_steps,
# accept_step_order, correct_dependency, reject_dependency, resolve_conflict
# are never called).
# --------------------------------------------------------------------------


def _print_header(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def _dependency_target_guess(target_label_value: str | None, steps: list) -> tuple[str, str] | None:
    """A literal 'step-N' ordinal match against global sequence, nothing more.

    This is a suggestion for a human to evaluate, not a resolution. It is
    deliberately naive: it does not consult chunk boundaries, rationale text,
    or relationship semantics. Returns (candidate_step_id, activity_value) or
    None if the label does not match the simple pattern.
    """

    if not target_label_value:
        return None
    match = re.fullmatch(r"step-(\d+)", target_label_value.strip(), flags=re.IGNORECASE)
    if not match:
        return None
    ordinal = int(match.group(1))
    for step in steps:
        if step.sequence == ordinal:
            return step.candidate_step_id, str(step.activity.value or "")
    return None


def describe_review_preparation(candidate_bytes: bytes) -> None:
    """Load the frozen candidate, start a review session, report everything.

    No file is written. No sqlite connection is opened. No review action is
    applied.
    """

    from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
    from ai_adoption_engine.models.extraction import CandidateExtractionResult
    from ai_adoption_engine.models.review import InformationOrigin
    from ai_adoption_engine.presentation.review_progress import (
        approval_errors,
        build_review_progress,
    )
    from ai_adoption_engine.review.service import ProcessReviewService

    # Imported for exact UI parity, not re-implemented. See module docstring.
    from ai_adoption_engine.presentation.pages.review import (
        _evidence_option_label as ui_evidence_option_label,
        _step_evidence_choices as ui_step_evidence_choices,
    )

    result = CandidateExtractionResult.model_validate(json.loads(candidate_bytes))

    _print_header("SYSTEM STATE — frozen extraction result")
    print(f"  status              {result.status.value}")
    print(f"  candidate present   {result.candidate is not None}")
    if result.candidate is not None:
        print(f"  extraction_run_id   {result.candidate.extraction_run_id}")
        print(f"  candidate_status    {result.candidate.candidate_status.value}")
        print(f"  step count          {len(result.candidate.steps)}")
    print(f"  issue count         {len(result.issues)}")

    service = ProcessReviewService()
    session = service.start_review(result)  # pure; no disk, no network

    _print_header("SYSTEM STATE — ProcessReviewSession (in memory only)")
    print(f"  review_id           {session.review_id}")
    print(f"  status              {session.status.value}")
    print(f"  order_accepted      {session.order_accepted}")
    print(f"  step count          {len(session.steps)}")
    print(f"  conflict count      {len(session.conflicts)}")
    print(f"  event count         {len(session.events)}  (0 expected — nothing applied yet)")

    _print_header("SYSTEM STATE — ReviewConflict objects (session.conflicts)")
    print("  Every entry here has blocking=True by construction: start_review() only")
    print("  creates a ReviewConflict for issues _issue_is_blocking() classifies as")
    print("  blocking. Non-blocking issues never become ReviewConflict objects; they")
    print("  remain visible only in session.extraction_issues (listed below).")
    for conflict in session.conflicts:
        print(
            f"  conflict_id={conflict.conflict_id}  code={conflict.code}  "
            f"blocking={conflict.blocking}  status={conflict.status.value}  "
            f"field_path={conflict.field_path}"
        )
        print(f"    message: {conflict.message}")

    # session.extraction_issues holds every Phase 3 issue (blocking and
    # non-blocking); session.conflicts holds only the blocking subset, each
    # built from an issue with identical (code, field_path, message). Match on
    # that exact triple, not on field_path alone, since two distinct issues
    # (e.g. the two ambiguous-dependency issues) can share a field_path.
    conflict_keys = {(c.code, c.field_path, c.message) for c in session.conflicts}
    _print_header("SYSTEM STATE — extraction_issues not represented as a conflict")
    for issue in session.extraction_issues:
        if (issue.code, issue.field_path, issue.message) in conflict_keys:
            continue
        print(
            f"  code={issue.code}  severity={issue.severity.value}  "
            f"field_path={issue.field_path}  chunk_id={issue.chunk_id}"
        )
        print(f"    message: {issue.message}")
        print("    NOTE: non-blocking — no ReviewConflict object exists for this issue.")

    _print_header("SYSTEM STATE — approval_errors(session) (every approval requirement, live)")
    errors = approval_errors(session)  # side-effect-free per its own docstring
    if not errors:
        print("  none (unexpected at this stage — nothing has been reviewed yet)")
    for error in errors:
        print(f"  code={error.code}  field_path={error.field_path}")
        print(f"    {error.message}")

    _print_header("SYSTEM STATE — build_review_progress(session)")
    progress = build_review_progress(session)
    print(f"  total_required      {progress.total_required}")
    print(f"  completed_required  {progress.completed_required}")
    print(f"  remaining_required  {progress.remaining_required}")
    print(f"  is_ready            {progress.is_ready}")
    for item in progress.outstanding:
        print(
            f"  outstanding: {item.item_id}  location={item.location_label}  "
            f"field={item.field_label}"
        )
        print(f"    reason: {item.reason}")

    _print_header("SYSTEM STATE — retained steps")
    for step in sorted(session.steps, key=lambda item: item.sequence):
        print(
            f"  sequence={step.sequence}  candidate_step_id={step.candidate_step_id}  "
            f"retained={step.retained}  order_basis={step.order_basis.value}"
        )
        print(f"    activity: {step.activity.value}")

    _print_header("HUMAN REVIEW OPTION — unresolved dependencies (proposal only, not applied)")
    print("  correct_dependency() and resolve_conflict() were NOT called. The proposed")
    print("  target below is a literal 'step-N' -> global-sequence-N match, offered for")
    print("  human judgement only.")
    for step in sorted(session.steps, key=lambda item: item.sequence):
        for index, dependency in enumerate(step.dependencies):
            if dependency.target_candidate_step_id is not None:
                continue
            print(
                f"  step {step.sequence} ({step.candidate_step_id}) "
                f"dependencies[{index}]:"
            )
            print(f"    target_label.value (raw)   : {dependency.target_label.value!r}")
            print(f"    relationship.value         : {dependency.relationship.value!r}")
            print("    EXISTING EVIDENCE (relationship.evidence):")
            for reference in dependency.relationship.evidence:
                print(f"      - {ui_evidence_option_label(reference)}")
            guess = _dependency_target_guess(dependency.target_label.value, session.steps)
            if guess is not None:
                guessed_id, guessed_activity = guess
                print(
                    f"    HUMAN REVIEW OPTION: propose target_candidate_step_id="
                    f"{guessed_id} (\"{guessed_activity}\") — NOT APPLIED."
                )
            else:
                print("    HUMAN REVIEW OPTION: no literal 'step-N' match found; no proposal.")

    _print_header(
        "SYSTEM STATE + EXISTING EVIDENCE — material criteria and accountability, per step"
    )
    print("  document_supported_path_wired reflects only whether the current UI passes an")
    print("  evidence_choices pool for that field TYPE (criteria and accountability: yes;")
    print("  capability_signals: no). It does not mean any specific value is supported —")
    print("  that is left to human judgement per the correction to this task: retain")
    print("  UNKNOWN unless existing evidence actually supports a value.")
    for step in sorted(session.steps, key=lambda item: item.sequence):
        pool = ui_step_evidence_choices(step)
        print(
            f"\n  step {step.sequence} ({step.candidate_step_id}) — "
            f"reusable evidence pool size: {len(pool)}"
        )
        for characteristic in step.criteria:
            assertion = characteristic.assertion
            print(
                f"    criterion={characteristic.name.value:<35} "
                f"knowledge_state={assertion.knowledge_state.value:<9} "
                f"origin={assertion.origin.value:<18} "
                f"own_evidence_count={len(assertion.evidence)} "
                f"document_supported_path_wired=True"
            )
        accountability = step.human_accountability_required
        print(
            f"    field=human_accountability_required           "
            f"knowledge_state={accountability.knowledge_state.value:<9} "
            f"origin={accountability.origin.value:<18} "
            f"own_evidence_count={len(accountability.evidence)} "
            f"document_supported_path_wired=True"
        )
        for signal in step.capability_signals:
            assertion = signal.assertion
            print(
                f"    capability_signal={signal.name:<26} "
                f"knowledge_state={assertion.knowledge_state.value:<9} "
                f"origin={assertion.origin.value:<18} "
                f"own_evidence_count={len(assertion.evidence)} "
                f"document_supported_path_wired=False (UI does not pass evidence_choices "
                f"for capability signals; service.correct_assertion would still accept "
                f"origin=DOCUMENT_SUPPORTED with evidence if called directly)"
            )

    _print_header("EXISTING EVIDENCE — full re-citable evidence pool per step (as the UI shows it)")
    for step in sorted(session.steps, key=lambda item: item.sequence):
        pool = ui_step_evidence_choices(step)
        print(f"\n  step {step.sequence} ({step.candidate_step_id}) — {len(pool)} evidence reference(s):")
        for reference in pool:
            print(f"    - evidence_id={reference.evidence_id}")
            print(f"      {ui_evidence_option_label(reference)}")

    _print_header("HUMAN INTERPRETATION — carried from the Stage 1 observation record")
    print("  Steps 1-3 state the document's abstract three-step planning framework")
    print("  verbatim. Later steps, drawn from the more granular subsections that")
    print("  follow, largely appear to elaborate or refine that same framework rather")
    print("  than represent wholly independent sequential activities. This is a")
    print("  reading offered for Phase 4's benefit, not a system finding, and it is")
    print("  not applied to the step order, dependencies, or any field here. See")
    print("  runs/port-004/stage1-observation-record.v0.1.md section 6 for the full text.")

    _print_header("CONFIRMATIONS")
    print(f"  Stage 2 working directory NOT created: {not STAGE2_RUN_DIR.exists()}")
    print(f"  Frozen Stage 1 run directory unchanged: {STAGE1_RUN_DIR}")
    print("  No accept/correct/reject/resolve-unknown/retain-unknown/reorder/")
    print("  accept-step-order/correct-dependency/reject-dependency/resolve-conflict/")
    print("  select-primary-actor/approve action was called.")
    print("  No sqlite3 connection was opened at any point in this run.")
    print("\n--- DRY RUN COMPLETE — NOTHING WAS WRITTEN, NOTHING WAS APPLIED ---")


def init_stage2_workspace() -> None:
    raise SystemExit(
        "ABORT: persistent Stage 2 workspace creation is not yet approved.\n"
        "This mode is a documented stub only. When approved, it will:\n"
        f"  1. copy {STAGE1_DATABASE_PATH.relative_to(ROOT)}\n"
        f"     to a new file under {STAGE2_RUN_DIR.relative_to(ROOT)}\n"
        "  2. never open the frozen Stage 1 copy for writing\n"
        "  3. call AssessmentWorkspaceService.start_review() against the new copy only\n"
        "Nothing was copied, written, or connected to."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Load the frozen candidate, start a review session, report everything. Writes nothing.",
    )
    group.add_argument(
        "--confirm-init-stage2-workspace",
        action="store_true",
        help="Not yet approved. Documented stub that refuses; see module docstring.",
    )
    args = parser.parse_args(argv)

    install_case_data_guard()
    print("=" * 78)
    print(
        f"{CASE_ID} STAGE 2 / PHASE 4 PREPARATION "
        f"({'DRY RUN' if args.dry_run else 'INIT STAGE 2 WORKSPACE'})"
    )
    print("=" * 78)
    candidate_bytes = run_safety_checks()

    if args.dry_run:
        describe_review_preparation(candidate_bytes)
    else:
        init_stage2_workspace()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

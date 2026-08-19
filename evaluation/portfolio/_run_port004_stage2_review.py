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

Two further modes, ``--confirm-init-stage2-workspace`` and
``--execute-authorised-review``, implement the persistent Stage 2 path
authorised on the basis of Phase 4 action plan v1.1. The first copies
``evaluation/portfolio/runs/port-004/production-run-v0.1/workspace.db`` into
``evaluation/portfolio/runs/port-004/production-run-v0.2-review/workspace.db``
and never opens the frozen copy for writing; it fails closed if the Stage 2
directory already exists. The second executes exactly the sixteen authorised
review actions plus the eighty-eight explicit UNKNOWN retentions against the
Stage 2 copy, through ``AssessmentWorkspaceService``, and stops at
ready-for-approval. Neither mode approves, persists a validated
``BusinessProcess``, runs assessment, generates recommendations or a decision
package, or touches AFTER material; ``--execute-authorised-review`` installs a
hard runtime guard that makes the approve/assess/package entry points raise.
See "Why the readiness check transiently builds a projection" below for the one
place an approval projection is constructed in memory and immediately discarded.

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
The only portfolio files this script may read are the frozen BEFORE corpus
(hash check only), the four frozen Stage 1 artefacts -- ``candidate_extraction.json``,
``ingestion_result.json``, ``run_state_after_extraction.json`` and
``workspace.db``, all hashed as raw bytes, with only the candidate ever parsed
and the database never opened via sqlite3 -- and, in the persistent modes, the
Stage 2 working directory. ``ingestion_result.json`` and
``run_state_after_extraction.json`` are readable solely so their frozen hashes
can be enforced; they are never parsed or interpreted. This script must never
read PORT-001/002/003 material, any sealed AFTER packet (none exists for
PORT-004), the case register, provenance manifests, leakage audits, source
captures, or OCR-derived material. Enforced by an explicit allowlist and a
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

Execution identity and the committed-before-run rule
------------------------------------------------------
The production fingerprint covers ``config``, ``src``, ``streamlit_app.py`` and
``pyproject.toml`` only, so it says nothing about this operator. Both persistent
modes therefore report an execution identity -- current git HEAD, the SHA-256 of
the exact operator bytes being run, whether the file is tracked, and whether it
is byte-identical to the version stored in HEAD -- and refuse to run unless the
operator matches HEAD exactly. Stage 2 artefacts are then attributable to a
specific commit. ``--dry-run`` reports the same identity without gating, so the
working copy can be inspected before it is committed. Only this file is gated:
an unrelated dirty working tree does not block execution and is not inspected.

Partial-execution recovery rule (fail closed, no automatic resume)
--------------------------------------------------------------------
``--execute-authorised-review`` saves one review action at a time, exactly as
the Streamlit UI does, because that is the persistence granularity the product
provides; there is no cross-action transaction in the repository contract. A
runtime or persistence failure part-way through can therefore leave a Stage 2
database holding some but not all of the authorised actions.

There is deliberately no resume mode. If a run aborts after the first mutation:

1. Do not re-run this operator against that database. ``--execute-authorised-review``
   requires a pristine session (zero events, order not accepted, all 88 fields
   still pristine UNKNOWN, nothing already accepted or corrected) and will abort
   rather than double-apply, but the correct response is human inspection, not
   another attempt.
2. Do not hand-repair the partial review.
3. Inspect the partial Stage 2 database, record what was and was not applied,
   then decide explicitly: discard the Stage 2 directory and re-run from the
   frozen Stage 1 copy, or re-plan. Either way the decision is recorded before
   anything is re-executed.

``--confirm-init-stage2-workspace`` refuses to touch an existing Stage 2
directory for the same reason.

Why the readiness check transiently builds a projection
---------------------------------------------------------
``presentation.review_progress.approval_errors`` -- which this operator reports,
and which ``build_review_progress`` calls internally -- evaluates readiness by
calling the real ``approve_review`` and reading its ``.errors``. It returns
``list[ApprovalError]``, and ``ApprovalError`` is a pydantic ``BaseModel``, so
``model_dump(mode="json")`` is correct.

One consequence must be stated plainly: ``ApprovalResult`` validates that
exactly one of ``approved`` / ``errors`` is populated, so when a session *is*
ready, ``approve_review`` necessarily constructs an in-memory
``ApprovedProcessReview`` including the projected ``BusinessProcess`` before
returning it. That object is discarded immediately. It is never persisted, no
``APPROVED_REVIEW`` artefact is created, and the session itself is untouched
(``approve_review`` deep-copies before mutating its snapshot). This is the
product's own readiness path -- the UI does it on every render -- and it cannot
be avoided while reporting readiness through the public API. This operator
asserts afterwards that the session status is still ``in-review`` and that no
``APPROVED_REVIEW`` artefact exists.

Usage
-----
Inspect the full Phase 4 starting state, with no write and no persistence::

    .venv/bin/python evaluation/portfolio/_run_port004_stage2_review.py --dry-run

Both persistent modes require this file to be committed and identical to HEAD.

Create the persistent Stage 2 working copy (fails closed if it already exists)::

    .venv/bin/python evaluation/portfolio/_run_port004_stage2_review.py --confirm-init-stage2-workspace

Execute the authorised Phase 4 actions against that copy and stop at
ready-for-approval::

    .venv/bin/python evaluation/portfolio/_run_port004_stage2_review.py --execute-authorised-review

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
import textwrap
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
PORTFOLIO = SCRIPT_PATH.parent
ROOT = PORTFOLIO.parents[1]

sys.path.insert(0, str(ROOT / "src"))

CASE_ID = "PORT-004"

STAGE1_RUN_DIR = PORTFOLIO / "runs" / "port-004" / "production-run-v0.1"
CANDIDATE_PATH = STAGE1_RUN_DIR / "candidate_extraction.json"
STAGE1_INGESTION_PATH = STAGE1_RUN_DIR / "ingestion_result.json"
STAGE1_RUN_STATE_PATH = STAGE1_RUN_DIR / "run_state_after_extraction.json"
STAGE1_DATABASE_PATH = STAGE1_RUN_DIR / "workspace.db"
BEFORE_PATH = PORTFOLIO / "product_inputs" / "port-004.before.txt"

EXPECTED_CANDIDATE_SHA256 = (
    "ffbefc0eef7ad68b90859576d60aa0c09606c1eb6fd267d4fe2dca13b2c8ad65"
)
EXPECTED_INGESTION_SHA256 = (
    "caaeb9534c827202fac910ba715e88ff93086dccfd9f637fb0919f364438eb58"
)
EXPECTED_RUN_STATE_SHA256 = (
    "1f346ee7bf5911ad4e1e3e23fc57cf08962ed0dd54934a5246eb0b9d564f9a19"
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
)

# The four frozen Stage 1 artefacts. ingestion_result.json and
# run_state_after_extraction.json were previously listed as forbidden reads;
# they are now hash-gated instead, which requires reading their raw bytes. They
# are still never parsed, never interpreted and never opened for writing.
FROZEN_STAGE1_ARTEFACTS = (
    ("candidate_extraction.json", CANDIDATE_PATH, EXPECTED_CANDIDATE_SHA256),
    ("ingestion_result.json", STAGE1_INGESTION_PATH, EXPECTED_INGESTION_SHA256),
    (
        "run_state_after_extraction.json",
        STAGE1_RUN_STATE_PATH,
        EXPECTED_RUN_STATE_SHA256,
    ),
    ("workspace.db", STAGE1_DATABASE_PATH, EXPECTED_STAGE1_DATABASE_SHA256),
)


class CaseDataBoundaryError(RuntimeError):
    """A forbidden portfolio case file was opened during Stage 2 preparation."""


def install_case_data_guard(mode: str = "dry-run") -> None:
    """Abort the process if any portfolio file outside the allowlist is opened.

    ``mode`` selects the permitted surface:

    ``dry-run``
        Unchanged from the committed behaviour: the frozen BEFORE corpus, the
        frozen candidate JSON, the frozen Stage 1 database (raw bytes only) and
        this script. Every ``sqlite3.connect`` call is refused outright.

    ``stage2``
        The same read allowlist, plus the Stage 2 working directory
        (``production-run-v0.2-review/``) for reading and writing. A
        ``sqlite3.connect`` call is permitted **only** for a path inside that
        Stage 2 directory, so the frozen Stage 1 database can never be opened
        as a database, in any access mode, by any code path in this process.

    The forbidden set is unchanged in both modes: PORT-001/002/003 material,
    sealed AFTER packets, the case register, provenance manifests, leakage
    audits, source captures and OCR-derived material all remain unreachable.
    """

    if mode not in {"dry-run", "stage2"}:  # pragma: no cover - programmer error
        raise ValueError(f"unknown case-data guard mode: {mode!r}")

    portfolio_root = os.path.realpath(PORTFOLIO)
    stage2_root = os.path.realpath(STAGE2_RUN_DIR)
    allowed_files = {
        os.path.realpath(BEFORE_PATH),
        os.path.realpath(SCRIPT_PATH),
    } | {os.path.realpath(path) for _name, path, _digest in FROZEN_STAGE1_ARTEFACTS}

    def _inside_stage2(resolved: str) -> bool:
        return resolved == stage2_root or resolved.startswith(stage2_root + os.sep)

    def hook(event: str, args: tuple[Any, ...]) -> None:
        if event not in {"open", "os.open", "sqlite3.connect"}:
            return
        if event == "sqlite3.connect":
            if mode == "dry-run":
                # No sqlite connection is permitted anywhere in --dry-run. The
                # frozen database is hash-verified as raw bytes only.
                raise CaseDataBoundaryError(
                    f"{CASE_ID} Stage 2 dry-run refused a sqlite3.connect call. "
                    "The frozen Stage 1 database is verified by hash only and is "
                    "never opened as a database in this mode."
                )
            target = args[0] if args else None
            if not isinstance(target, (str, bytes, os.PathLike)):
                raise CaseDataBoundaryError(
                    f"{CASE_ID} Stage 2 guard refused a sqlite3.connect call with a "
                    "non-path target."
                )
            resolved = os.path.realpath(os.fsdecode(target))
            if _inside_stage2(resolved):
                return
            raise CaseDataBoundaryError(
                f"{CASE_ID} Stage 2 guard refused sqlite3.connect({resolved}). "
                "Only the Stage 2 working database may be opened as a database. "
                "The frozen Stage 1 database is verified by hash only."
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
        if mode == "stage2" and _inside_stage2(resolved):
            return
        raise CaseDataBoundaryError(
            f"{CASE_ID} Stage 2 case-data guard refused to open {resolved}. "
            "Only the frozen BEFORE document, the frozen candidate JSON, the "
            "frozen Stage 1 database (hash check only), this script and — in "
            "stage2 mode — the Stage 2 working directory are permitted."
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


OPERATOR_RELATIVE_PATH = "evaluation/portfolio/_run_port004_stage2_review.py"


def _git(*args: str) -> tuple[int, str]:
    """Run a read-only git command in the repository root. Never mutates."""

    completed = subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=ROOT, check=False
    )
    return completed.returncode, completed.stdout.strip()


def execution_identity() -> dict[str, Any]:
    """Identify exactly which operator file is executing, and from what state.

    The production fingerprint deliberately covers ``config``, ``src``,
    ``streamlit_app.py`` and ``pyproject.toml`` only, so it says nothing about
    this evaluation operator. These fields close that gap: they record the
    commit the repository is on, the SHA-256 of the exact bytes being run, and
    whether those bytes are identical to the version stored in HEAD.

    Read-only: ``git rev-parse``, ``git ls-files`` and ``git hash-object``
    neither write objects nor touch the index. ``git hash-object`` without
    ``-w`` computes a digest and stores nothing.
    """

    script_bytes = SCRIPT_PATH.read_bytes()
    script_sha256 = hashlib.sha256(script_bytes).hexdigest()

    head_rc, head_commit = _git("rev-parse", "HEAD")
    tracked_rc, _ = _git("ls-files", "--error-unmatch", OPERATOR_RELATIVE_PATH)
    head_blob_rc, head_blob = _git("rev-parse", f"HEAD:{OPERATOR_RELATIVE_PATH}")
    working_blob_rc, working_blob = _git("hash-object", str(SCRIPT_PATH))

    tracked = tracked_rc == 0
    matches_head = (
        tracked
        and head_blob_rc == 0
        and working_blob_rc == 0
        and head_blob == working_blob
    )

    return {
        "operator_path": OPERATOR_RELATIVE_PATH,
        "operator_sha256": script_sha256,
        "git_head": head_commit if head_rc == 0 else None,
        "operator_tracked": tracked,
        "operator_blob_in_head": head_blob if head_blob_rc == 0 else None,
        "operator_blob_working": working_blob if working_blob_rc == 0 else None,
        "operator_matches_head": matches_head,
    }


def report_execution_identity(*, require_committed: bool) -> dict[str, Any]:
    """Print the execution identity and, for persistent modes, gate on it.

    Portfolio discipline for this case is: commit the reviewed operator first,
    then execute exactly that committed version, so the Stage 2 artefacts are
    attributable to a specific commit. ``--dry-run`` reports the identity but
    does not gate, so the working copy can be inspected before it is committed.

    Only this operator file is gated. An unrelated dirty working tree (for
    example the master-bible document, or the untracked ``.claude/`` directory)
    does not block execution and is deliberately not inspected.
    """

    identity = execution_identity()
    print("--- EXECUTION IDENTITY ---")
    print(f"  git HEAD                   {identity['git_head']}")
    print(f"  operator path              {identity['operator_path']}")
    print(f"  operator sha256            {identity['operator_sha256']}")
    print(f"  operator tracked by git    {identity['operator_tracked']}")
    print(f"  blob in HEAD               {identity['operator_blob_in_head']}")
    print(f"  blob of file being run     {identity['operator_blob_working']}")
    print(f"  matches HEAD exactly       {identity['operator_matches_head']}")

    if not require_committed:
        print("  gate                       NOT ENFORCED (dry-run reports identity only)")
        return identity

    if identity["git_head"] is None:
        raise SystemExit(
            "ABORT: git HEAD could not be resolved, so this run cannot be attributed "
            "to a commit. No compensating mutation was attempted."
        )
    if not identity["operator_matches_head"]:
        raise SystemExit(
            "ABORT: the operator file being executed is not identical to the version "
            "stored in HEAD.\n"
            f"  HEAD                {identity['git_head']}\n"
            f"  blob in HEAD        {identity['operator_blob_in_head']}\n"
            f"  blob being executed {identity['operator_blob_working']}\n"
            f"  tracked             {identity['operator_tracked']}\n"
            "Persistent Stage 2 modes require the reviewed operator to be committed "
            "first, so every Stage 2 artefact is attributable to an exact commit. "
            "Commit this file, then re-run. No compensating mutation was attempted."
        )
    print("  gate                       PASSED (executing the committed operator)")
    return identity


def verify_frozen_stage1(label: str) -> dict[str, str]:
    """Hash all four frozen Stage 1 artefacts as raw bytes and enforce equality.

    None of the four is parsed here, and none is ever opened for writing. Any
    mismatch aborts; no compensating mutation is attempted.
    """

    digests: dict[str, str] = {}
    for name, path, expected in FROZEN_STAGE1_ARTEFACTS:
        if not path.is_file():
            raise SystemExit(f"ABORT: frozen Stage 1 artefact is missing: {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        digests[name] = digest
        print(f"  {name:<34} {digest}")
        if digest != expected:
            raise SystemExit(
                f"ABORT: frozen Stage 1 artefact hash mismatch ({label}): {name}\n"
                f"  expected {expected}\n"
                f"  actual   {digest}\n"
                "The frozen Stage 1 artefact is no longer in its frozen state. "
                "No compensating mutation was attempted."
            )
        print(f"  {'':<34} MATCH")
    return digests


def run_safety_checks() -> bytes:
    """Verify every hard-checked hash. Returns the candidate JSON bytes.

    Aborts on any mismatch, before anything else runs.
    """

    print("--- SAFETY CHECKS ---")
    print("  frozen Stage 1 artefacts (raw bytes; never parsed, never opened for writing):")
    verify_frozen_stage1("pre-execution")
    print(
        "  workspace.db was verified as raw bytes only and is never opened as a database."
    )

    candidate_bytes = CANDIDATE_PATH.read_bytes()

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


# ==========================================================================
# AUTHORISED PHASE 4 EXECUTION (action plan v1.1)
#
# Everything from here to the end of the file runs only under
# --confirm-init-stage2-workspace or --execute-authorised-review. Both modes
# stop at ready-for-approval. Neither approves, persists a validated
# BusinessProcess, runs assessment, generates recommendations or a decision
# package, or reads AFTER material. The product's own readiness check may
# transiently construct an in-memory approval projection; see the module
# docstring.
# ==========================================================================

STAGE2_DATABASE_PATH = STAGE2_RUN_DIR / "workspace.db"
STAGE2_RECORD_PATH = STAGE2_RUN_DIR / "stage2-execution-record.v0.1.json"

# --- Frozen identifiers the plan is pinned to. Every one is asserted before use.

STEP1_ID = "candidate-step-8761540c3fb724d5"
STEP2_ID = "candidate-step-df4f0ee1970efb51"
STEP3_ID = "candidate-step-55d273f0f007cf1f"

# (candidate_step_id, activity value, pinned activity evidence_id)
EXPECTED_STEPS: tuple[tuple[str, str, str], ...] = (
    (
        STEP1_ID,
        "identifying the field of search",
        "cev-67271175d3d1719a9554d6f0db88f0b91c6658fd28bb2b8d74563d37c1a6d03c",
    ),
    (
        STEP2_ID,
        "selecting the proper tool(s) to perform the search",
        "cev-892048315c0fe7255c55040a41ddb90dfc19243c7e0c50369a36139702529dc0",
    ),
    (
        STEP3_ID,
        "determining the appropriate search strategy for each search tool selected",
        "cev-494f3cbd5958e00942cb71d374e0ffc77a614cffed8582ea4900cc5539f41cf4",
    ),
    (
        "candidate-step-56dffd383d81b62b",
        "Prioritize areas to be searched",
        "cev-be2fb97725e7c1a4bf0bc164a7fadcd15652fa5de5c83a1320eefadb2c1533d7",
    ),
    (
        "candidate-step-77a07b30101d76fe",
        "Select search tools",
        "cev-b4b3aeb73ed4985a452f01a2527d9f41088fb9b8d9b4f85a402446298c01953e",
    ),
    (
        "candidate-step-2d9417a14cf0f937",
        "Conduct Internet searching",
        "cev-05f346901e323bc326381c0d3c2d78223b1287495b91457299d0e87ce4203696",
    ),
    (
        "candidate-step-69b86f080884cb5a",
        "Document Internet search strategies",
        "cev-d4d7b0aed220ac894e9358a3d0ad062cf24c2bcca8a78e58b6b89227e2d167c2",
    ),
    (
        "candidate-step-a154c8ee145a50f9",
        "Conduct a careful and comprehensive search",
        "cev-0718a77997f7e55d32d78e381e270945c04274bbd15f57492f2fab087b79e3f6",
    ),
)

EXPECTED_CONFLICT_CODES: tuple[str, ...] = (
    "snippet-not-found",
    "ambiguous-dependency",
    "ambiguous-dependency",
    "process-field-conflict",
)

PROCESS_NAME_VALUE = "How to Search"

EV_PROCESS_NAME = (
    "cev-6915c0b9d0439cd7bce10948efcf7471e95ab05d6b8f4adf025cc1abe7f65b42"
)
EV_STEP2_RELATIONSHIP = (
    "cev-08b516894d50a1d4d2b10386f2759f9d489b8d41eb72e34eaab6378ad802f8fb"
)
EV_STEP2_TARGET_LABEL = (
    "cev-9f8a9e0432a9273d8b73d7853594521e6ce3112e704d8ea18d0d4d50c79b5b53"
)
EV_STEP3_RELATIONSHIP = (
    "cev-92f08c226d88c620589d2bf13f1f6f5abef6196dee65054db4a205fd9fdc4002"
)
EV_STEP3_TARGET_LABEL = (
    "cev-6dfb5b66fcf5e24500eb1febf2ecfb16dbc12c0bb7291d1bdcbaaf8ddb48f78a"
)

# Every evidence reference the sixteen authorised actions rely upon. All must
# already exist in the frozen candidate; none is ever created.
ALL_PINNED_EVIDENCE: tuple[str, ...] = (
    EV_PROCESS_NAME,
    EV_STEP2_RELATIONSHIP,
    EV_STEP2_TARGET_LABEL,
    EV_STEP3_RELATIONSHIP,
    EV_STEP3_TARGET_LABEL,
) + tuple(evidence_id for _sid, _activity, evidence_id in EXPECTED_STEPS)

EXPECTED_PINNED_EVIDENCE_COUNT = 13

EXPECTED_TOTAL_REQUIRED = 16
EXPECTED_STEP_COUNT = 8
EXPECTED_CONFLICT_COUNT = 4
EXPECTED_CRITERIA_PER_STEP = 10
EXPECTED_RETENTIONS = 88

# The complete expected ReviewEvent ledger. Keys are filled in from the
# production ReviewAction enum at run time, never from hardcoded display
# strings, so a rename in production surfaces as an abort rather than a
# silently wrong count.
EXPECTED_EVENT_LEDGER = {
    "CORRECT_DEPENDENCY": 2,
    "RESOLVE_CONFLICT": 4,
    "ACCEPT": 9,
    "RETAIN_UNKNOWN": 88,
    "ACCEPT_STEP_ORDER": 1,
}
EXPECTED_EVENT_TOTAL = 104


APPROVAL_BOUNDARY_NOTE = (
    'No APPROVED_REVIEW artefact was persisted, no validated BusinessProcess was persisted or passed into integrated assessment, and no AssessmentEngine execution occurred. The product readiness check may transiently construct an in-memory approval projection as part of its side-effect-free validation path.'
)


class ApprovalBoundaryError(RuntimeError):
    """A forbidden post-review operation was attempted."""


def install_approval_boundary_guard(service_class: Any) -> None:
    """Make approve / assess / generate_package raise, in this process only.

    This patches the in-memory class object for the lifetime of this script. It
    does not modify any production file, and it deliberately does not touch
    ``ai_adoption_engine.review.approval.approve_review`` itself, because
    ``review_progress.approval_errors`` calls that function as a side-effect-free
    preflight and must keep working.
    """

    def _blocked(name: str):
        def _raise(*_args: Any, **_kwargs: Any):
            raise ApprovalBoundaryError(
                f"{CASE_ID} Stage 2 execution refused AssessmentWorkspaceService.{name}(). "
                "This operator is authorised only up to ready-for-approval."
            )

        return _raise

    for name in ("approve", "assess", "generate_package"):
        setattr(service_class, name, _blocked(name))


# --- Per-field rationales for the 88 UNKNOWN retentions -------------------
#
# Composed, not copy-pasted: each rationale states why this criterion type
# cannot be read off a procedural manual, and what this specific step's own
# evidence pool actually contains. The 80 combinations are therefore distinct
# and step-specific. No rationale asserts a value, cites AFTER knowledge, or
# introduces a researcher-supplied figure.

CRITERION_BASIS: dict[str, str] = {
    "repetition": (
        "The frozen corpus prescribes procedure and states no frequency, volume, "
        "caseload or docket figure from which a 0-5 repetition rating could be read."
    ),
    "predictability": (
        "The frozen corpus states no rule-structure or variability measure; where it "
        "speaks to variability at all it does so qualitatively, not as a 0-5 rating."
    ),
    "data_readiness": (
        "The frozen corpus names reference sources to be consulted but never assesses "
        "their accessibility, representativeness, governance or readiness."
    ),
    "ai_capability_fit": (
        "The frozen corpus predates and never addresses machine capability, so no 0-5 "
        "capability-fit rating can be grounded in it."
    ),
    "human_judgement_requirement": (
        "The frozen corpus evidences that expert human judgement is involved but never "
        "grades it; selecting one of 0-5 would be a researcher inference, and this "
        "criterion is gate-material."
    ),
    "business_value": (
        "The frozen corpus states procedural obligations and never assesses operational "
        "or strategic value."
    ),
    "risk_consequence": (
        "The frozen corpus identifies harms to be avoided but never grades the severity "
        "of an error on a 0-5 scale; this criterion is gate-material."
    ),
    "residual_risk_with_human_oversight": (
        "This criterion is counterfactual to a changed operating model; the frozen "
        "corpus describes an all-human process and cannot speak to it."
    ),
    "implementation_complexity": (
        "The frozen corpus describes tool availability and procedure, never integration "
        "effort, cost or feasibility."
    ),
    "conventional_solution_fit": (
        "The frozen corpus never compares conventional software, rules or redesign "
        "against any alternative approach."
    ),
}

STEP_POOL_NOTE: dict[int, str] = {
    1: (
        "Step 1's pool (11 references) is field-of-search instruction and "
        "reference-source naming only."
    ),
    2: (
        "Step 2's pool (10 references) is tool-selection instruction and a statement "
        "that the choice rests on examiner knowledge."
    ),
    3: (
        "Step 3's pool (11 references) is strategy-determination instruction plus "
        "consultation roles and a case-by-case qualifier."
    ),
    4: (
        "Step 4's pool holds only 2 references, both the prioritisation sentence "
        "itself."
    ),
    5: (
        "Step 5's pool holds only 3 references: a section heading, a guidance pointer "
        "and a Technology Center qualifier."
    ),
    6: (
        "Step 6's pool (11 references) is Internet-search permission and "
        "confidentiality restriction text."
    ),
    7: (
        "Step 7's pool (6 references) is the documentation obligation and its "
        "procedural cross-reference."
    ),
    8: (
        "Step 8's pool (13 references) is search-conduct instruction and "
        "reference-selection guidance."
    ),
}

ACCOUNTABILITY_RATIONALE: dict[int, str] = {
    1: (
        "RETAIN UNKNOWN. The corpus assigns the three planning steps to the examiner "
        "and requires justification before eliminating a reference source, but states "
        "no accountability classification for the activity. A present human duty is not "
        "the future-model accountability Boolean this field carries."
    ),
    2: (
        "RETAIN UNKNOWN. The corpus grounds tool choice in the examiner's knowledge but "
        "makes no statement about required accountability for the activity."
    ),
    3: (
        "RETAIN UNKNOWN. The corpus assigns strategy determination to the examiner, with "
        "optional consultation, but states no accountability classification."
    ),
    4: (
        "RETAIN UNKNOWN. The prioritisation sentence names no actor at all and carries no "
        "accountability statement."
    ),
    5: (
        "RETAIN UNKNOWN. The tool-selection subsection is methodological guidance and "
        "states nothing about who is accountable."
    ),
    6: (
        "RETAIN UNKNOWN. The corpus imposes confidentiality obligations on examiners using "
        "the Internet, which evidences a present duty of care, not the accountability "
        "classification this Boolean records."
    ),
    7: (
        "RETAIN UNKNOWN. The corpus states an unconditional documentation obligation on "
        "Patent Organization users (cev-e0c26d1568f9443a1413 and the activity evidence). "
        "That evidences a present human duty, not the future-model accountability Boolean. "
        "Explicitly retained as UNKNOWN per action plan v1.1."
    ),
    8: (
        "RETAIN UNKNOWN. The corpus requires the examiner to fully consider cited prior "
        "art, which is a present procedural duty and not a stated accountability "
        "classification."
    ),
}


def _criterion_rationale(criterion_name: str, sequence: int) -> str:
    return (
        "RETAIN UNKNOWN. "
        + CRITERION_BASIS[criterion_name]
        + " "
        + STEP_POOL_NOTE[sequence]
        + " No existing Phase 3 evidence reference supports a specific value, and none is supplied."
    )


# --- Exact conflict resolution texts, verbatim from action plan v1.1 -------

RESOLUTION_R13 = (
    "Reviewer confirms that no value was admitted for multiple_processes_detected. The "
    "provider's snippet could not be resolved against block t-b0032 of chunk-0002, so the "
    "assertion failed closed to UNKNOWN - not FALSE - and no such value is stored on the "
    "frozen candidate. The reviewer does not supply a value and makes no finding as to "
    "whether the wider source contains additional processes. The frozen BEFORE scope (MPEP "
    "Ninth Edition Rev. 10.2019, sections 904-904.03, pages 900-40 to 900-46, corrected at "
    "841d066) was deliberately narrowed to the single documented process \"How to Search\"; "
    "anything outside that scope is out of scope for PORT-004 and remains unknown. This "
    "conflict is closed as reviewed-and-acknowledged, not as adjudicated."
)

RESOLUTION_R14 = (
    "Closes the first of the two ambiguous-dependency conflicts, which corresponds to step 2 "
    f"({STEP2_ID}, dependencies[0], raw schematic target label \"step-1\"). "
    "Attribution basis: this conflict is session.conflicts[1], built by start_review() from "
    "issues[1] of the frozen candidate via an order-preserving comprehension. "
    "extraction/merge.py emits one ambiguous-dependency issue per unresolvable dependency "
    "while iterating retained steps in ascending final sequence (the sort by "
    "_earliest_position precedes that loop), and the frozen candidate contains exactly two "
    "unresolvable dependencies, on steps 2 and 3 in that order. The attribution is therefore "
    "determined by construction order, verified against the frozen artefact at review time, "
    "not assumed by convention. The ReviewConflict object itself stores no field_path, "
    "chunk_id or block_id. Both ambiguous dependencies have been corrected in this session. "
    f"This one's target was set to {STEP1_ID} (\"identifying the field of search\") on "
    f"existing Phase 3 evidence {EV_STEP2_TARGET_LABEL} - \"Having determined the field of "
    "search, the examiner should then determine what search tools should be employed\" - "
    "which names the antecedent activity in words, independently of the schematic ordinal. "
    "No evidence was created or minted."
)

RESOLUTION_R15 = (
    "Closes the second of the two ambiguous-dependency conflicts, which corresponds to step 3 "
    f"({STEP3_ID}, dependencies[0], raw schematic target label \"step-2\"). "
    "Attribution basis: this conflict is session.conflicts[2], built from issues[2] of the "
    "frozen candidate by the same order-preserving construction described in the companion "
    "closure, and verified against the frozen artefact at review time rather than assumed. "
    "Both ambiguous dependencies have been corrected in this session. This one's target was "
    f"set to {STEP2_ID} (\"selecting the proper tool(s) to perform the search\") on existing "
    f"Phase 3 evidence {EV_STEP3_TARGET_LABEL} - \"selecting the proper tool(s) to perform "
    "the search; and (C) determining the appropriate search strategy for each search tool "
    f"selected.\" - read with relationship evidence {EV_STEP3_RELATIONSHIP}, \"determining "
    "the appropriate search strategy for each search tool selected.\", in which the participle "
    "\"selected\" refers to the immediately preceding clause. No evidence was created or minted."
)

RESOLUTION_R16 = (
    "Reviewer accepts the retained, first-supported process name \"How to Search\", cited "
    f"verbatim to the MPEP section 904 heading (existing evidence {EV_PROCESS_NAME}, lines "
    "15-47). The retained value is independently document-supported on that evidence. The "
    "competing chunk-0002 value was not persisted by the Phase 3 process-field merge and was "
    "therefore unavailable for comparison at review time; the reviewer is not claiming to have "
    "adjudicated two visible alternatives. No process-name rewrite occurred. The "
    "non-observability of superseded process-field values is recorded as a limitation of the "
    "current first-supported-wins merge."
)

RATIONALE_R11 = (
    f"Sets the step 2 dependency target to {STEP1_ID} (\"identifying the field of search\"). "
    f"Supported by existing Phase 3 evidence {EV_STEP2_TARGET_LABEL} - \"Having determined the "
    "field of search, the examiner should then determine what search tools should be employed\" "
    f"- and relationship evidence {EV_STEP2_RELATIONSHIP}, \"Having determined the field of "
    "search\". The cited sentence names its own antecedent in words, so the resolution does not "
    "rest on the schematic \"step-1\" ordinal alone. The relationship value is unchanged and no "
    "evidence was created or minted."
)

RATIONALE_R12 = (
    f"Sets the step 3 dependency target to {STEP2_ID} (\"selecting the proper tool(s) to perform "
    f"the search\"). Supported by existing Phase 3 evidence {EV_STEP3_TARGET_LABEL} and "
    f"relationship evidence {EV_STEP3_RELATIONSHIP}, \"determining the appropriate search "
    "strategy for each search tool selected.\", in which the participle \"selected\" refers to "
    "the immediately preceding clause (B). The relationship value is unchanged and no evidence "
    "was created or minted."
)

RATIONALE_PROCESS_NAME = (
    f"Accepted as extracted. \"{PROCESS_NAME_VALUE}\" is the MPEP section 904 heading quoted "
    f"verbatim, carried by existing Phase 3 evidence {EV_PROCESS_NAME}. No correction is made: "
    "a rewritten name would be HUMAN_SUPPLIED and could carry no document evidence."
)

RATIONALE_STEP_ORDER = (
    "Reviewer confirmed the displayed current-state order. All eight retained steps carry "
    "order_basis=source_position and their activity evidence locators ascend monotonically with "
    "sequence. This acceptance records document/display order only; it is not a claim that the "
    "eight activities execute in this sequence in practice."
)


def _activity_rationale(sequence: int, activity: str) -> str:
    return (
        f"Accepted as extracted. Step {sequence} activity \"{activity}\" is carried verbatim or "
        "as a faithful nominalisation of its own frozen Phase 3 evidence snippet. No correction "
        "is made; a rewrite would substitute researcher phrasing for the product's output."
    )


# --- Small helpers used only by the execution mode ------------------------


def _fail(message: str) -> "SystemExit":
    """Return a SystemExit carrying a STOP message. No compensating mutation."""

    return SystemExit(f"ABORT: {message}\nNo compensating mutation was attempted.")


def _iter_evidence_ids(node: Any) -> "Any":
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "evidence_id" and isinstance(value, str):
                yield value
            else:
                yield from _iter_evidence_ids(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_evidence_ids(item)


def _count_human_supplied(node: Any) -> int:
    total = 0
    if isinstance(node, dict):
        if node.get("origin") == "HUMAN_SUPPLIED":
            total += 1
        for value in node.values():
            total += _count_human_supplied(value)
    elif isinstance(node, list):
        for item in node:
            total += _count_human_supplied(item)
    return total


def _load_session(service: Any, assessment_id: str, artifact_type: Any) -> Any:
    workspace = service.repository.load_workspace(assessment_id)
    stored = workspace.active_artifacts.get(artifact_type)
    if stored is None:
        raise _fail("the Stage 2 workspace holds no active REVIEW_SESSION artefact.")
    return stored.payload


def _sorted_steps(session: Any) -> list:
    return sorted(session.steps, key=lambda item: item.sequence)


def init_stage2_workspace() -> None:
    """Create the persistent Stage 2 working copy. Fails closed if it exists."""

    import shutil

    _print_header("STAGE 2 WORKSPACE CREATION")

    if STAGE2_RUN_DIR.exists():
        raise _fail(
            f"the Stage 2 directory already exists: {STAGE2_RUN_DIR.relative_to(ROOT)}\n"
            "This operator does not overwrite it and does not implement resume semantics. "
            "Inspect the existing directory and decide explicitly what to do with it."
        )

    print(f"  source (frozen, read-only) {STAGE1_DATABASE_PATH.relative_to(ROOT)}")
    print(f"  destination                {STAGE2_DATABASE_PATH.relative_to(ROOT)}")

    STAGE2_RUN_DIR.mkdir(parents=True, exist_ok=False)
    # copyfile opens the source read-only ('rb'); the frozen database is never
    # opened for writing, and never opened as a database at all.
    shutil.copyfile(STAGE1_DATABASE_PATH, STAGE2_DATABASE_PATH)

    post_copy = hashlib.sha256(STAGE1_DATABASE_PATH.read_bytes()).hexdigest()
    print(f"  frozen Stage 1 db re-hash  {post_copy}")
    if post_copy != EXPECTED_STAGE1_DATABASE_SHA256:
        raise _fail(
            "the frozen Stage 1 database changed during the copy.\n"
            f"  expected {EXPECTED_STAGE1_DATABASE_SHA256}\n"
            f"  actual   {post_copy}"
        )
    print("    frozen Stage 1 unchanged MATCH")

    stage2_digest = hashlib.sha256(STAGE2_DATABASE_PATH.read_bytes()).hexdigest()
    print(f"  Stage 2 copy sha256        {stage2_digest}")
    if stage2_digest != EXPECTED_STAGE1_DATABASE_SHA256:
        raise _fail("the Stage 2 copy does not match the frozen source byte for byte.")
    print("    byte-identical to source MATCH")

    print("\n--- STAGE 2 WORKSPACE CREATED. NO REVIEW WAS STARTED OR MUTATED. ---")
    print("Next: --execute-authorised-review")


def _verify_initial_state(session: Any, progress: Any, review_status_cls: Any) -> None:
    _print_header("PRE-EXECUTION VERIFICATION — initial review state")

    checks: list[tuple[str, Any, Any]] = [
        ("status", session.status, review_status_cls.IN_REVIEW),
        ("step count", len(session.steps), EXPECTED_STEP_COUNT),
        ("conflict count", len(session.conflicts), EXPECTED_CONFLICT_COUNT),
        ("event count", len(session.events), 0),
        ("order_accepted", session.order_accepted, False),
        ("total_required", progress.total_required, EXPECTED_TOTAL_REQUIRED),
        ("completed_required", progress.completed_required, 0),
        ("remaining_required", progress.remaining_required, EXPECTED_TOTAL_REQUIRED),
        ("is_ready", progress.is_ready, False),
    ]
    for label, actual, expected in checks:
        verdict = "OK" if actual == expected else "MISMATCH"
        print(f"  {label:<20} actual={actual!s:<12} expected={expected!s:<12} {verdict}")
        if actual != expected:
            raise _fail(
                f"initial review state differs materially: {label} is {actual!r}, "
                f"expected {expected!r}."
            )

    if session.process_name.disposition.value != "unreviewed":
        raise _fail(
            "process.name has already been reviewed "
            f"(disposition={session.process_name.disposition.value}); refusing to accept it."
        )
    if EV_PROCESS_NAME not in [item.evidence_id for item in session.process_name.evidence]:
        raise _fail("the pinned process-name evidence is not attached to process.name.")

    criteria_unknown = 0
    accountability_unknown = 0
    for index, (step, expected) in enumerate(
        zip(_sorted_steps(session), EXPECTED_STEPS, strict=True), start=1
    ):
        expected_id, expected_activity, expected_evidence = expected
        if step.candidate_step_id != expected_id or step.sequence != index:
            raise _fail(
                f"step {index} identity differs: {step.candidate_step_id} at sequence "
                f"{step.sequence}, expected {expected_id} at sequence {index}."
            )
        if str(step.activity.value) != expected_activity:
            raise _fail(
                f"step {index} activity differs: {step.activity.value!r}, expected "
                f"{expected_activity!r}."
            )
        if not step.retained:
            raise _fail(f"step {index} is not retained.")
        if step.activity.disposition.value != "unreviewed":
            raise _fail(
                f"step {index} activity has already been reviewed "
                f"(disposition={step.activity.disposition.value}); refusing to accept it."
            )
        if expected_evidence not in [item.evidence_id for item in step.activity.evidence]:
            raise _fail(
                f"step {index} activity is missing its pinned evidence {expected_evidence}."
            )
        if len(step.criteria) != EXPECTED_CRITERIA_PER_STEP:
            raise _fail(
                f"step {index} carries {len(step.criteria)} criteria, expected "
                f"{EXPECTED_CRITERIA_PER_STEP}."
            )
        for characteristic in step.criteria:
            assertion = characteristic.assertion
            if (
                assertion.knowledge_state.value != "unknown"
                or assertion.value is not None
                or assertion.disposition.value != "unreviewed"
            ):
                raise _fail(
                    f"step {index} criterion {characteristic.name.value} is not a pristine "
                    f"UNKNOWN (knowledge_state={assertion.knowledge_state.value}, "
                    f"value={assertion.value!r}, disposition={assertion.disposition.value})."
                )
            criteria_unknown += 1
        accountability = step.human_accountability_required
        if (
            accountability.knowledge_state.value != "unknown"
            or accountability.value is not None
            or accountability.disposition.value != "unreviewed"
        ):
            raise _fail(
                f"step {index} human_accountability_required is not a pristine UNKNOWN "
                f"(knowledge_state={accountability.knowledge_state.value}, "
                f"value={accountability.value!r}, "
                f"disposition={accountability.disposition.value})."
            )
        accountability_unknown += 1
        for signal in step.capability_signals:
            if signal.assertion.disposition.value != "unreviewed":
                raise _fail(
                    f"step {index} capability signal {signal.name} has already been "
                    "reviewed through Phase 4; this operator never edits capability signals."
                )

    if criteria_unknown != 80:
        raise _fail(f"expected 80 UNKNOWN criteria, found {criteria_unknown}.")
    if accountability_unknown != EXPECTED_STEP_COUNT:
        raise _fail(
            f"expected {EXPECTED_STEP_COUNT} UNKNOWN accountability fields, found "
            f"{accountability_unknown}."
        )

    print(f"  all {EXPECTED_STEP_COUNT} step identities, sequences and activities  OK")
    print("  process.name unreviewed with pinned evidence                OK")
    print(f"  criteria pristine UNKNOWN                                   {criteria_unknown}/80 OK")
    print(f"  accountability pristine UNKNOWN                             {accountability_unknown}/8 OK")
    print("  capability signals not pre-reviewed                         OK")


class PersistedReviewMismatch(RuntimeError):
    """The persisted REVIEW_SESSION does not match the verified pure preflight."""


def _session_shape(session: Any) -> dict[str, Any]:
    """A comparable structural fingerprint of a review session.

    Deliberately excludes ``review_id`` and timestamps: ``start_review()`` mints
    a fresh review_id, so those differ between the pure preflight session and
    the persisted one by design. Everything structural must be identical.
    """

    return {
        "status": session.status.value,
        "order_accepted": session.order_accepted,
        "event_count": len(session.events),
        "steps": [
            (step.sequence, step.candidate_step_id, str(step.activity.value), step.retained)
            for step in _sorted_steps(session)
        ],
        "conflict_codes": [conflict.code for conflict in session.conflicts],
        "conflict_statuses": [conflict.status.value for conflict in session.conflicts],
        "conflict_field_paths": [conflict.field_path for conflict in session.conflicts],
        "unresolved_dependencies": [
            (
                step.sequence,
                step.candidate_step_id,
                index,
                str(dependency.target_label.value),
            )
            for step in _sorted_steps(session)
            for index, dependency in enumerate(step.dependencies)
            if dependency.retained and dependency.target_candidate_step_id is None
        ],
        "process_name": str(session.process_name.value),
        "criteria_unknown": sum(
            1
            for step in session.steps
            for item in step.criteria
            if item.assertion.knowledge_state.value == "unknown"
            and item.assertion.value is None
            and item.assertion.disposition.value == "unreviewed"
        ),
        "accountability_unknown": sum(
            1
            for step in session.steps
            if step.human_accountability_required.knowledge_state.value == "unknown"
            and step.human_accountability_required.value is None
            and step.human_accountability_required.disposition.value == "unreviewed"
        ),
        "capability_signals_reviewed": sum(
            1
            for step in session.steps
            for signal in step.capability_signals
            if signal.assertion.disposition.value != "unreviewed"
        ),
    }


def pure_phase4_preflight(candidate_bytes: bytes, review_status_cls: Any) -> dict[str, Any]:
    """Validate the whole Phase 4 review shape in memory, before any persistence.

    Builds a ``ProcessReviewSession`` through the pure
    ``ProcessReviewService.start_review()`` path -- the same path the committed
    ``--dry-run`` mode uses -- so every candidate-derived precondition is proved
    before the workspace-integrated ``start_review()`` writes anything. Nothing
    here opens a database, writes a file, or mutates a session.

    Returns the structural fingerprint the persisted session must reproduce.
    """

    from ai_adoption_engine.models.extraction import CandidateExtractionResult
    from ai_adoption_engine.presentation.review_progress import build_review_progress
    from ai_adoption_engine.review.service import ProcessReviewService

    _print_header("PURE PHASE 4 PREFLIGHT — in memory, before any persistence")
    print("  No workspace, no database and no artefact is touched in this section.")

    _verify_pinned_evidence(candidate_bytes)

    result = CandidateExtractionResult.model_validate(json.loads(candidate_bytes))
    if result.candidate is None:
        raise _fail("the frozen candidate holds no CandidateBusinessProcess.")
    print(f"  frozen extraction status   {result.status.value}")
    print(f"  candidate steps            {len(result.candidate.steps)}")
    print(f"  frozen issues              {len(result.issues)}")

    pure_session = ProcessReviewService().start_review(result)
    pure_progress = build_review_progress(pure_session)
    print(f"  in-memory review_id        {pure_session.review_id}  (discarded; not persisted)")

    _verify_initial_state(pure_session, pure_progress, review_status_cls)
    _verify_conflict_mapping(pure_session)

    shape = _session_shape(pure_session)
    print("\n  PURE PHASE 4 PREFLIGHT PASSED — persistent review creation is now authorised.")
    return shape


def verify_persisted_review(
    session: Any, progress: Any, review_status_cls: Any, expected_shape: dict[str, Any]
) -> None:
    """Re-verify the persisted REVIEW_SESSION before any review action is applied.

    Raises :class:`PersistedReviewMismatch` on any difference, so the caller can
    report precisely that persistent creation happened while no human-review
    action was applied.
    """

    _print_header("POST-PERSISTENCE VERIFICATION — before any review action")

    checks: list[tuple[str, Any, Any]] = [
        ("status", session.status, review_status_cls.IN_REVIEW),
        ("step count", len(session.steps), EXPECTED_STEP_COUNT),
        ("conflict count", len(session.conflicts), EXPECTED_CONFLICT_COUNT),
        ("event count", len(session.events), 0),
        ("order_accepted", session.order_accepted, False),
        ("total_required", progress.total_required, EXPECTED_TOTAL_REQUIRED),
        ("completed_required", progress.completed_required, 0),
        ("remaining_required", progress.remaining_required, EXPECTED_TOTAL_REQUIRED),
        ("is_ready", progress.is_ready, False),
    ]
    for label, actual, expected in checks:
        verdict = "OK" if actual == expected else "MISMATCH"
        print(f"  {label:<20} actual={actual!s:<12} expected={expected!s:<12} {verdict}")
        if actual != expected:
            raise PersistedReviewMismatch(
                f"persisted review {label} is {actual!r}, expected {expected!r}"
            )

    actual_shape = _session_shape(session)
    for key in sorted(expected_shape):
        if actual_shape.get(key) != expected_shape[key]:
            raise PersistedReviewMismatch(
                f"persisted review differs from the verified pure preflight on {key!r}:\n"
                f"  preflight {expected_shape[key]!r}\n"
                f"  persisted {actual_shape.get(key)!r}"
            )
    print("  structural equivalence to the pure preflight            OK")
    print("    (review_id and timestamps are expected to differ and are not compared)")


def _verify_pinned_evidence(candidate_bytes: bytes) -> None:
    """Every evidence id the 16 authorised actions cite must already exist."""

    frozen_ids = set(_iter_evidence_ids(json.loads(candidate_bytes)))
    missing = [item for item in ALL_PINNED_EVIDENCE if item not in frozen_ids]
    unique = sorted(set(ALL_PINNED_EVIDENCE))
    print(
        f"  pinned evidence ids referenced by the plan  {len(unique)} "
        f"(expected {EXPECTED_PINNED_EVIDENCE_COUNT})"
    )
    if len(unique) != EXPECTED_PINNED_EVIDENCE_COUNT:
        raise _fail(
            f"the plan pins {len(unique)} distinct evidence ids, expected "
            f"{EXPECTED_PINNED_EVIDENCE_COUNT}."
        )
    if missing:
        raise _fail(
            "these pinned evidence ids do not exist in the frozen candidate: "
            f"{missing}"
        )
    print("  all pinned evidence present in frozen candidate  OK")


def _verify_conflict_mapping(session: Any) -> dict[str, Any]:
    """Ordered positional verification. No dict is keyed by a ReviewConflict."""

    _print_header("PRE-EXECUTION VERIFICATION — dependency / conflict mapping")

    codes = [conflict.code for conflict in session.conflicts]
    print(f"  conflict code order        {codes}")
    if tuple(codes) != EXPECTED_CONFLICT_CODES:
        raise _fail(
            f"conflict code order differs: {codes}, expected {list(EXPECTED_CONFLICT_CODES)}."
        )
    print("    matches expected order   OK")

    unresolved = [
        (step.sequence, step.candidate_step_id, index, dependency)
        for step in _sorted_steps(session)
        for index, dependency in enumerate(step.dependencies)
        if dependency.retained and dependency.target_candidate_step_id is None
    ]
    print(f"  unresolved retained deps   {len(unresolved)}")
    for sequence, step_id, index, dependency in unresolved:
        print(
            f"    step {sequence} {step_id} dependencies[{index}] "
            f"raw_label={dependency.target_label.value!r} target=None"
        )

    expected_unresolved = ((2, STEP2_ID, 0, "step-1"), (3, STEP3_ID, 0, "step-2"))
    if len(unresolved) != len(expected_unresolved):
        raise _fail(
            f"expected exactly {len(expected_unresolved)} unresolved retained dependencies, "
            f"found {len(unresolved)}."
        )
    for (sequence, step_id, index, dependency), expected in zip(
        unresolved, expected_unresolved, strict=True
    ):
        if (sequence, step_id, index) != expected[:3]:
            raise _fail(
                f"unresolved dependency differs: got ({sequence}, {step_id}, {index}), "
                f"expected {expected[:3]}."
            )
        if str(dependency.target_label.value) != expected[3]:
            raise _fail(
                f"step {sequence} raw target label is {dependency.target_label.value!r}, "
                f"expected {expected[3]!r}."
            )

    evidence_checks = (
        (2, unresolved[0][3].relationship, EV_STEP2_RELATIONSHIP),
        (2, unresolved[0][3].target_label, EV_STEP2_TARGET_LABEL),
        (3, unresolved[1][3].relationship, EV_STEP3_RELATIONSHIP),
        (3, unresolved[1][3].target_label, EV_STEP3_TARGET_LABEL),
    )
    for sequence, assertion, expected_evidence in evidence_checks:
        present = [item.evidence_id for item in assertion.evidence]
        if expected_evidence not in present:
            raise _fail(
                f"step {sequence} dependency evidence {expected_evidence} is not present; "
                f"found {present}."
            )
    print("    pinned dependency evidence present on both dependencies  OK")

    # Ordered positional attribution, established in action plan v1.1 section 1.
    ambiguous_positions = [
        index
        for index, conflict in enumerate(session.conflicts)
        if conflict.code == "ambiguous-dependency"
    ]
    if ambiguous_positions != [1, 2]:
        raise _fail(
            f"ambiguous-dependency conflicts are at positions {ambiguous_positions}, "
            "expected [1, 2]."
        )

    mapping = {
        "conflicts[1]": {
            "conflict_id": session.conflicts[1].conflict_id,
            "step_sequence": 2,
            "candidate_step_id": STEP2_ID,
            "dependency_index": 0,
            "raw_target_label": "step-1",
        },
        "conflicts[2]": {
            "conflict_id": session.conflicts[2].conflict_id,
            "step_sequence": 3,
            "candidate_step_id": STEP3_ID,
            "dependency_index": 0,
            "raw_target_label": "step-2",
        },
    }
    print("  deterministic positional mapping established:")
    for position, detail in mapping.items():
        print(
            f"    {position} conflict_id={detail['conflict_id']} -> step "
            f"{detail['step_sequence']} ({detail['candidate_step_id']}) "
            f"dependencies[{detail['dependency_index']}] raw={detail['raw_target_label']!r}"
        )
    return mapping


def execute_authorised_review(candidate_bytes: bytes, identity: dict[str, Any]) -> None:
    """Execute exactly the authorised Phase 4 actions, then stop at ready.

    Every deterministic precondition is checked before the first mutation. If
    any of them fails the run aborts with no compensating mutation, and — if a
    Stage 2 database already exists — the fail-closed recovery rule in the
    module docstring applies.
    """

    from ai_adoption_engine.models.review import ReviewAction, ReviewStatus
    from ai_adoption_engine.presentation.review_progress import (
        approval_errors,
        build_review_progress,
    )
    from ai_adoption_engine.workspace.composition import build_workspace_service
    from ai_adoption_engine.workspace.models import ArtifactType
    from ai_adoption_engine.workspace.service import AssessmentWorkspaceService

    if not STAGE2_DATABASE_PATH.is_file():
        raise _fail(
            f"the Stage 2 database is missing: {STAGE2_DATABASE_PATH.relative_to(ROOT)}\n"
            "Run --confirm-init-stage2-workspace first."
        )

    install_approval_boundary_guard(AssessmentWorkspaceService)
    print("  approval boundary guard    INSTALLED "
          "(approve / assess / generate_package now raise)")

    service = build_workspace_service(STAGE2_DATABASE_PATH)
    assessments = service.repository.list_assessments()
    if len(assessments) != 1:
        raise _fail(
            f"expected exactly one assessment in the Stage 2 workspace, found "
            f"{len(assessments)}."
        )
    assessment_id = assessments[0].assessment_id
    print(f"  assessment_id              {assessment_id}")
    print(f"  title                      {assessments[0].title}")
    print(f"  workflow stage             {assessments[0].current_stage.value}")

    pre_workspace = service.repository.load_workspace(assessment_id)
    if ArtifactType.APPROVED_REVIEW in pre_workspace.active_artifacts:
        raise _fail(
            "the Stage 2 workspace already holds an APPROVED_REVIEW artefact. "
            "This operator is authorised only up to ready-for-approval."
        )
    print("  APPROVED_REVIEW absent     OK")

    # ---- Everything above is read-only. Everything candidate-derived is now
    # ---- proved in memory, before the workspace-integrated start_review()
    # ---- persists a REVIEW_SESSION artefact.
    expected_shape = pure_phase4_preflight(candidate_bytes, ReviewStatus)

    _print_header("PERSISTENT REVIEW CREATION — the first persistent Phase 4 write")
    print("  AssessmentWorkspaceService.start_review() persists a REVIEW_SESSION")
    print("  artefact and advances the workflow stage. The product provides no")
    print("  cross-action transaction, so this call is not made transactional here.")
    session = service.start_review(assessment_id)
    # Inspect what was actually persisted, not merely what was returned.
    session = _load_session(service, assessment_id, ArtifactType.REVIEW_SESSION)
    progress = build_review_progress(session)

    _print_header("SYSTEM STATE — persisted review session on the Stage 2 copy")
    print(f"  review_id                  {session.review_id}")
    print(f"  status                     {session.status.value}")
    print(f"  steps                      {len(session.steps)}")
    print(f"  conflicts                  {len(session.conflicts)}")
    for index, conflict in enumerate(session.conflicts):
        print(
            f"    conflicts[{index}] conflict_id={conflict.conflict_id} "
            f"code={conflict.code} status={conflict.status.value} "
            f"blocking={conflict.blocking} field_path={conflict.field_path}"
        )
    print(f"  total_required             {progress.total_required}")
    print(f"  completed_required         {progress.completed_required}")
    print(f"  remaining_required         {progress.remaining_required}")
    print(f"  is_ready                   {progress.is_ready}")

    try:
        verify_persisted_review(session, progress, ReviewStatus, expected_shape)
        # Recomputed on the persisted session so the closures below use the live
        # conflict_ids, and so the positional attribution is proved again against
        # what was actually written.
        mapping = _verify_conflict_mapping(session)
    except PersistedReviewMismatch as mismatch:
        raise SystemExit(
            f"ABORT: {mismatch}\n\n"
            "A persistent REVIEW_SESSION artefact WAS created by "
            "AssessmentWorkspaceService.start_review(), but NO human-review action "
            "was applied: no dependency correction, no conflict resolution, no "
            "acceptance, no retention, no step-order acceptance. The Stage 2 "
            "database therefore holds an unmodified review session and nothing "
            "else.\n"
            "The fail-closed recovery rule applies: do not re-run this operator "
            "against that database and do not hand-repair it. Inspect the Stage 2 "
            "directory, record what exists, then decide explicitly whether to "
            "discard it and re-run from the frozen Stage 1 copy, or to re-plan.\n"
            "No compensating mutation was attempted."
        ) from mismatch

    print("\n  ALL PREFLIGHT AND POST-PERSISTENCE CHECKS PASSED — the first review action follows.")

    conflict_ids = [conflict.conflict_id for conflict in session.conflicts]
    review_id = session.review_id
    applied: list[str] = []

    def apply(label: str, mutate) -> None:
        nonlocal session
        working = session.model_copy(deep=True)
        mutate(working)
        service.save_review(assessment_id, working)
        session = _load_session(service, assessment_id, ArtifactType.REVIEW_SESSION)
        if session.review_id != review_id:
            raise _fail("the review_id changed mid-execution.")
        applied.append(label)
        print(f"    applied: {label}")

    review = service.review_service

    def _step_of(working: Any, step_id: str) -> Any:
        return next(
            item for item in working.steps if item.candidate_step_id == step_id
        )

    # ---- R11 / R12: the only two content-changing actions ----------------
    _print_header("EXECUTING — R11, R12 (dependency target corrections)")
    apply(
        "R11 correct_dependency step 2 dep[0]",
        lambda working: review.correct_dependency(
            working, STEP2_ID, 0, STEP1_ID, rationale=RATIONALE_R11
        ),
    )
    apply(
        "R12 correct_dependency step 3 dep[0]",
        lambda working: review.correct_dependency(
            working, STEP3_ID, 0, STEP2_ID, rationale=RATIONALE_R12
        ),
    )

    # ---- R14 / R15 / R13 / R16: conflict closures ------------------------
    _print_header("EXECUTING — R14, R15, R13, R16 (conflict closures)")
    apply(
        f"R14 resolve_conflict conflicts[1] {conflict_ids[1]}",
        lambda working: review.resolve_conflict(
            working, conflict_ids[1], resolution=RESOLUTION_R14
        ),
    )
    apply(
        f"R15 resolve_conflict conflicts[2] {conflict_ids[2]}",
        lambda working: review.resolve_conflict(
            working, conflict_ids[2], resolution=RESOLUTION_R15
        ),
    )
    apply(
        f"R13 resolve_conflict conflicts[0] {conflict_ids[0]}",
        lambda working: review.resolve_conflict(
            working, conflict_ids[0], resolution=RESOLUTION_R13
        ),
    )
    apply(
        f"R16 resolve_conflict conflicts[3] {conflict_ids[3]}",
        lambda working: review.resolve_conflict(
            working, conflict_ids[3], resolution=RESOLUTION_R16
        ),
    )

    # ---- R1: process identity -------------------------------------------
    _print_header("EXECUTING — R1 (accept process name)")
    if str(session.process_name.value) != PROCESS_NAME_VALUE:
        raise _fail(
            f"process name is {session.process_name.value!r}, expected "
            f"{PROCESS_NAME_VALUE!r}."
        )
    if EV_PROCESS_NAME not in [item.evidence_id for item in session.process_name.evidence]:
        raise _fail("the pinned process-name evidence is not attached to process.name.")
    apply(
        "R1 accept process.name",
        lambda working: review.accept_assertion(
            working, working.process_name, "process.name", rationale=RATIONALE_PROCESS_NAME
        ),
    )

    # ---- R3..R10: the eight activities, accepted exactly as frozen -------
    _print_header("EXECUTING — R3..R10 (accept 8 activities, no corrections)")
    for sequence, (step_id, activity, _evidence_id) in enumerate(EXPECTED_STEPS, start=1):
        requirement = sequence + 2
        apply(
            f"R{requirement} accept steps.{step_id}.activity",
            lambda working, sid=step_id, seq=sequence, act=activity: review.accept_assertion(
                working,
                _step_of(working, sid).activity,
                f"steps.{sid}.activity",
                rationale=_activity_rationale(seq, act),
            ),
        )

    # ---- The 88 explicit UNKNOWN retentions ------------------------------
    _print_header("EXECUTING — 88 explicit UNKNOWN retentions (80 criteria + 8 accountability)")
    retention_count = 0
    for step in _sorted_steps(session):
        sequence = step.sequence
        step_id = step.candidate_step_id
        for index, characteristic in enumerate(step.criteria):
            name = characteristic.name.value
            if characteristic.assertion.knowledge_state.value != "unknown":
                raise _fail(
                    f"step {sequence} criterion {name} is not UNKNOWN; refusing to retain."
                )
            apply(
                f"RETAIN_UNKNOWN steps.{step_id}.criteria[{index}] ({name})",
                lambda working, sid=step_id, i=index, nm=name, seq=sequence: review.retain_unknown(
                    working,
                    _step_of(working, sid).criteria[i].assertion,
                    f"steps.{sid}.criteria[{i}]",
                    rationale=_criterion_rationale(nm, seq),
                ),
            )
            retention_count += 1
        if step.human_accountability_required.knowledge_state.value != "unknown":
            raise _fail(
                f"step {sequence} human_accountability_required is not UNKNOWN; refusing."
            )
        apply(
            f"RETAIN_UNKNOWN steps.{step_id}.human_accountability_required",
            lambda working, sid=step_id, seq=sequence: review.retain_unknown(
                working,
                _step_of(working, sid).human_accountability_required,
                f"steps.{sid}.human_accountability_required",
                rationale=ACCOUNTABILITY_RATIONALE[seq],
            ),
        )
        retention_count += 1
    if retention_count != EXPECTED_RETENTIONS:
        raise _fail(
            f"recorded {retention_count} retentions, expected {EXPECTED_RETENTIONS}."
        )

    # ---- R2: step order, last -------------------------------------------
    _print_header("EXECUTING — R2 (accept step order, last action)")
    apply(
        "R2 accept_step_order",
        lambda working: review.accept_step_order(working, rationale=RATIONALE_STEP_ORDER),
    )

    _final_report(
        service=service,
        assessment_id=assessment_id,
        session=session,
        candidate_bytes=candidate_bytes,
        mapping=mapping,
        applied=applied,
        identity=identity,
        approval_errors=approval_errors,
        build_review_progress=build_review_progress,
        artifact_type_cls=ArtifactType,
        review_action_cls=ReviewAction,
        review_status_cls=ReviewStatus,
        json_module=json,
    )


def _final_report(
    *,
    service: Any,
    assessment_id: str,
    session: Any,
    candidate_bytes: bytes,
    mapping: dict[str, Any],
    applied: list[str],
    identity: dict[str, Any],
    approval_errors: Any,
    build_review_progress: Any,
    artifact_type_cls: Any,
    review_action_cls: Any,
    review_status_cls: Any,
    json_module: Any,
) -> None:
    frozen = json_module.loads(candidate_bytes)
    frozen_evidence = set(_iter_evidence_ids(frozen))
    dumped = session.model_dump(mode="json")
    session_evidence = set(_iter_evidence_ids(dumped))
    minted = sorted(session_evidence - frozen_evidence)
    human_supplied = _count_human_supplied(dumped)

    action_counts: dict[str, int] = {}
    for event in session.events:
        action_counts[event.action.value] = action_counts.get(event.action.value, 0) + 1

    # Build the expected ledger from the production ReviewAction enum members,
    # never from hardcoded display strings, so a production rename aborts here
    # instead of silently satisfying a wrong count.
    expected_ledger: dict[str, int] = {}
    for member_name, count in EXPECTED_EVENT_LEDGER.items():
        member = getattr(review_action_cls, member_name, None)
        if member is None:
            raise _fail(
                f"production ReviewAction has no member {member_name}; the expected "
                "event ledger no longer matches production and must be re-derived."
            )
        expected_ledger[member.value] = count
    if sum(expected_ledger.values()) != EXPECTED_EVENT_TOTAL:
        raise _fail("the expected event ledger does not sum to EXPECTED_EVENT_TOTAL.")

    criteria_unknown = sum(
        1
        for step in session.steps
        for item in step.criteria
        if item.assertion.knowledge_state.value == "unknown" and item.assertion.value is None
    )
    accountability_unknown = sum(
        1
        for step in session.steps
        if step.human_accountability_required.knowledge_state.value == "unknown"
        and step.human_accountability_required.value is None
    )
    signals_touched = sum(
        1
        for step in session.steps
        for signal in step.capability_signals
        if signal.assertion.disposition.value != "unreviewed"
    )

    errors = approval_errors(session)
    progress = build_review_progress(session)

    _print_header("FINAL REPORT")
    print(f"  review_id                  {session.review_id}")
    print(f"  status                     {session.status.value}")
    print(f"  total ReviewEvent count    {len(session.events)}")
    print("  events by action (actual vs expected):")
    for action in sorted(set(action_counts) | set(expected_ledger)):
        actual = action_counts.get(action, 0)
        expected = expected_ledger.get(action, 0)
        verdict = "OK" if actual == expected else "MISMATCH"
        print(f"    {action:<20} {actual:>4}   expected {expected:>4}   {verdict}")
    if action_counts != expected_ledger:
        raise _fail(
            f"the ReviewEvent ledger differs from the authorised plan.\n"
            f"  actual   {action_counts}\n"
            f"  expected {expected_ledger}"
        )
    if len(session.events) != EXPECTED_EVENT_TOTAL:
        raise _fail(
            f"expected {EXPECTED_EVENT_TOTAL} ReviewEvents, found {len(session.events)}."
        )
    print(f"  event ledger               MATCHES the authorised plan ({EXPECTED_EVENT_TOTAL})")

    print("\n  retained steps and final sequence:")
    for step in _sorted_steps(session):
        print(
            f"    {step.sequence}. {step.candidate_step_id}  retained={step.retained}  "
            f"disposition={step.activity.disposition.value}  activity={step.activity.value}"
        )

    print("\n  final dependency targets:")
    for step in _sorted_steps(session):
        for index, dependency in enumerate(step.dependencies):
            print(
                f"    step {step.sequence} dependencies[{index}] "
                f"raw_label={dependency.target_label.value!r} "
                f"relationship={dependency.relationship.value!r} "
                f"target={dependency.target_candidate_step_id} "
                f"retained={dependency.retained}"
            )

    print("\n  conflicts:")
    for index, conflict in enumerate(session.conflicts):
        summary = (conflict.resolution or "")[:110].replace("\n", " ")
        print(
            f"    conflicts[{index}] {conflict.conflict_id} code={conflict.code} "
            f"status={conflict.status.value}"
        )
        print(f"      resolution: {summary}...")

    print(f"\n  material criteria still UNKNOWN      {criteria_unknown} (expected 80)")
    print(f"  accountability still UNKNOWN         {accountability_unknown} (expected 8)")
    print(f"  capability signals modified          {signals_touched} (expected 0)")
    print(f"  HUMAN_SUPPLIED assertions            {human_supplied} (expected 0)")
    print(f"  newly minted evidence references     {len(minted)} (expected 0)")
    if minted:
        print(f"    minted: {minted}")

    print(f"\n  approval_errors(session)             {errors}")
    print("  build_review_progress:")
    print(f"    total_required                     {progress.total_required}")
    print(f"    completed_required                 {progress.completed_required}")
    print(f"    remaining_required                 {progress.remaining_required}")
    print(f"    is_ready                           {progress.is_ready}")
    for item in progress.outstanding:
        print(f"    outstanding: {item.item_id} {item.field_label} — {item.reason}")

    workspace = service.repository.load_workspace(assessment_id)
    approved_present = artifact_type_cls.APPROVED_REVIEW in workspace.active_artifacts
    print(f"\n  workflow stage                       {workspace.assessment.current_stage.value}")
    print(f"  APPROVED_REVIEW artefact present     {approved_present} (expected False)")

    _print_header("FROZEN STAGE 1 ARTEFACTS — post-execution re-hash (all four enforced)")
    frozen_hashes = verify_frozen_stage1("post-execution")
    before_digest = hashlib.sha256(BEFORE_PATH.read_bytes()).hexdigest()
    print(f"  {BEFORE_PATH.name:<34} {before_digest}"
          f"{'  MATCH' if before_digest == EXPECTED_BEFORE_SHA256 else '  MISMATCH'}")

    stage2_digest = hashlib.sha256(STAGE2_DATABASE_PATH.read_bytes()).hexdigest()
    print(f"\n  Stage 2 workspace.db sha256          {stage2_digest}")

    record = {
        "case_id": CASE_ID,
        "stage": "stage-2-phase-4-human-review",
        "action_plan_version": "v1.1",
        "execution_identity": identity,
        "assessment_id": assessment_id,
        "review_id": session.review_id,
        "review_status": session.status.value,
        # The project's run-state records carry no wall-clock field (see
        # _run_port004_stage1.py), so none is injected here. The product's own
        # timestamps, already persisted inside the review session, are recorded
        # instead, which keeps this file reproducible from the workspace.
        "review_created_at": session.created_at.isoformat(),
        "review_updated_at": session.updated_at.isoformat(),
        "first_event_at": (
            session.events[0].occurred_at.isoformat() if session.events else None
        ),
        "last_event_at": (
            session.events[-1].occurred_at.isoformat() if session.events else None
        ),
        "expected_events_by_action": expected_ledger,
        "expected_event_total": EXPECTED_EVENT_TOTAL,
        "pinned_evidence_ids": sorted(set(ALL_PINNED_EVIDENCE)),
        "ambiguous_dependency_mapping": mapping,
        "applied_actions": applied,
        "event_count": len(session.events),
        "events_by_action": action_counts,
        "criteria_unknown": criteria_unknown,
        "accountability_unknown": accountability_unknown,
        "capability_signals_modified": signals_touched,
        "human_supplied_assertions": human_supplied,
        "newly_minted_evidence": minted,
        # approval_errors() returns list[ApprovalError]; ApprovalError is a
        # pydantic BaseModel (models/review.py), so model_dump is correct here.
        "approval_errors": [error.model_dump(mode="json") for error in errors],
        "progress": {
            "total_required": progress.total_required,
            "completed_required": progress.completed_required,
            "remaining_required": progress.remaining_required,
            "is_ready": progress.is_ready,
        },
        "approved_review_present": approved_present,
        "approval_boundary_note": APPROVAL_BOUNDARY_NOTE,
        "workflow_stage": workspace.assessment.current_stage.value,
        "frozen_stage1_hashes": frozen_hashes,
        "before_corpus_sha256": before_digest,
        "stage2_database_sha256": stage2_digest,
        "production_fingerprint": EXPECTED_FINGERPRINT,
    }
    STAGE2_RECORD_PATH.write_text(
        json_module.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"  execution record written             {STAGE2_RECORD_PATH.relative_to(ROOT)}")

    if session.status is not review_status_cls.IN_REVIEW:
        raise _fail(
            f"the review status is {session.status.value}; it must remain in-review."
        )
    if approved_present:
        raise _fail("an APPROVED_REVIEW artefact exists; this operator never approves.")

    ready = progress.is_ready and not errors
    print("\n" + "=" * 78)
    if ready:
        print("REVIEW IS READY FOR APPROVAL — AND IS DELIBERATELY LEFT UNAPPROVED.")
        print("This operator never called approve_review() itself.")
        for line in textwrap.wrap(APPROVAL_BOUNDARY_NOTE, 78):
            print(line)
    else:
        print("REVIEW IS NOT READY. See approval_errors and outstanding items above.")
    print("=" * 78)
    if not ready:
        raise _fail("the review did not reach ready-for-approval.")


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
        help="Create the persistent Stage 2 working copy. Fails closed if it already exists.",
    )
    group.add_argument(
        "--execute-authorised-review",
        action="store_true",
        help=(
            "Execute the sixteen authorised review actions and the 88 UNKNOWN retentions "
            "against the Stage 2 copy, then stop at ready-for-approval. Never approves."
        ),
    )
    args = parser.parse_args(argv)

    if args.dry_run:
        mode_label, guard_mode = "DRY RUN", "dry-run"
    elif args.confirm_init_stage2_workspace:
        mode_label, guard_mode = "INIT STAGE 2 WORKSPACE", "stage2"
    else:
        mode_label, guard_mode = "EXECUTE AUTHORISED REVIEW", "stage2"

    install_case_data_guard(guard_mode)
    print("=" * 78)
    print(f"{CASE_ID} STAGE 2 / PHASE 4 ({mode_label})")
    print("=" * 78)
    identity = report_execution_identity(require_committed=not args.dry_run)
    candidate_bytes = run_safety_checks()

    if args.dry_run:
        describe_review_preparation(candidate_bytes)
    elif args.confirm_init_stage2_workspace:
        init_stage2_workspace()
    else:
        execute_authorised_review(candidate_bytes, identity)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

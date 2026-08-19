"""Stage 3 (Phase 4 explicit approval) operator for PORT-004.

Scope
-----
This operator crosses exactly one boundary: it turns the frozen, verified,
ready-but-unapproved PORT-004 Phase 4 review into a persisted
``APPROVED_REVIEW`` artefact, and then stops. It never runs deterministic
assessment, never generates a recommendation or a decision package, never
reopens or mutates a review, and never touches AFTER material.

It deliberately does **not** modify ``_run_port004_stage2_review.py``. That
operator's SHA-256 is cited inside the frozen Stage 2 execution record and the
frozen Stage 2 observation record; editing it would retroactively break the
provenance link recorded at the ready-but-unapproved freeze.

Three mutually exclusive modes, mirroring the Stage 2 discipline
------------------------------------------------------------------
``--dry-run``
    Writes nothing, creates nothing, opens no read-write database connection.
    Verifies every frozen hash, the whole PORT-004 run manifest, the production
    fingerprint and the complete approval-ready state of the frozen Stage 2
    review, which it reads through a strictly read-only SQLite URI. It never
    calls ``AssessmentWorkspaceService.approve``.

``--confirm-init-stage3-workspace``
    Creates ``runs/port-004/production-run-v0.3-approved/`` and copies the
    frozen Stage 2 ``workspace.db`` into it byte-for-byte. Approval is **not**
    performed in this mode, and no approval record is written. Fails closed if
    the Stage 3 directory already exists.

``--confirm-approve-review``
    Requires the Stage 3 copy to exist and to still be byte-identical to the
    frozen Stage 2 source. Re-verifies every gate, re-verifies the whole review
    through product code, then makes exactly one call to
    ``AssessmentWorkspaceService.approve(...)`` and stops.

Separating workspace creation from the approval mutation is deliberate: the
copy is a reversible filesystem operation, the approval is not.

Why approve a copy rather than the frozen Stage 2 database
-------------------------------------------------------------
``production-run-v0.2-review/workspace.db`` is frozen in git at the
ready-but-unapproved checkpoint, and its SHA-256 is quoted in two committed
records. Approving it in place would leave those records describing a file that
no longer has the stated hash. Nothing in the product prevents approving a
copy: ``build_workspace_service`` accepts any database path, the assessment and
artefact identifiers travel with a byte copy, and ``approve()`` requires only an
active ``REVIEW_SESSION`` with no ``APPROVED_REVIEW``.

What ``approve()`` actually does, and one nuance that matters
----------------------------------------------------------------
``AssessmentWorkspaceService.approve`` calls the pure ``approve_review`` and, on
success, persists a **new** ``APPROVED_REVIEW`` artefact whose parent is the
``REVIEW_SESSION`` artefact, advancing ``assessments.current_stage`` to
``approved``. It does not replace the ``REVIEW_SESSION``: the persistence layer
raises ``PersistenceError`` for any attempt to replace a non-review artefact,
and ``deactivate_types`` is empty.

The nuance: ``approve_review`` deep-copies the session before setting
``status=APPROVED``, so after approval the **standalone ``REVIEW_SESSION``
artefact still reads ``in-review``**. The approved snapshot lives inside
``APPROVED_REVIEW.review``. Post-approval verification here therefore asserts on
the ``APPROVED_REVIEW`` artefact and on ``assessments.current_stage``, and
explicitly expects the standalone review payload to remain ``in-review``.

``approve()`` does not call ``assess()``. Assessment is a separate method that
*requires* an existing ``APPROVED_REVIEW``, and packaging requires a successful
assessment, so the dependency runs one way only and approval cannot cascade.

Failure semantics — no automatic resume, ever
------------------------------------------------
Read this before re-running anything.

*If Stage 3 copy creation fails midway*: inspect
``production-run-v0.3-approved/`` by hand. Do not re-run this operator against
it -- ``--confirm-init-stage3-workspace`` refuses an existing directory, and
that refusal is the intended behaviour. Decide explicitly whether to discard the
directory and re-create it from the frozen Stage 2 copy, or to re-plan.

*If ``--confirm-approve-review`` fails before the ``approve()`` call*: no
approval occurred and nothing was persisted by this operator. Inspect, then
re-plan. The pristine-copy gate will refuse to proceed against a Stage 3
database whose hash has drifted from the frozen source.

*If ``approve()`` succeeds but post-approval verification or record writing
fails*: **the approval may already be persisted.** Never re-run approval
automatically. ``approve()`` is not operation-tracked -- unlike ``assess`` and
``generate_package`` it takes no idempotency key -- and its only replay guard is
the "already approved" check inside the service. Inspect the Stage 3 database
**read-only**, establish exactly what exists, and recover the documentation
separately as a deliberate, recorded decision. Do not hand-repair the database
and do not call ``reset_to_review``.

Case-data boundary
-------------------
Readable: the frozen BEFORE corpus, the four frozen Stage 1 artefacts, the three
frozen Stage 2 freeze artefacts, the PORT-004 run manifest, this script, and --
in the persistent modes -- the Stage 3 working directory. Every one of those is
hash-verified. ``sqlite3.connect`` is permitted only for the frozen Stage 2
database in ``--dry-run`` (read-only URI) and only for the Stage 3 directory in
the persistent modes; the frozen Stage 1 and Stage 2 databases are otherwise
verified as raw bytes and never opened as databases. PORT-001/002/003 material,
sealed AFTER packets, the case register, provenance manifests, leakage audits,
source captures and OCR-derived material are all unreachable. Enforced by an
explicit allowlist and a ``sys.addaudithook`` guard.

Usage
-----
All three commands, in order. Both persistent modes require this file to be
committed and byte-identical to HEAD::

    .venv/bin/python evaluation/portfolio/_run_port004_stage3_approval.py --dry-run
    .venv/bin/python evaluation/portfolio/_run_port004_stage3_approval.py --confirm-init-stage3-workspace
    .venv/bin/python evaluation/portfolio/_run_port004_stage3_approval.py --confirm-approve-review

No ``PYTHONPATH`` is required; this script prepends ``src/`` to ``sys.path``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, Iterator


SCRIPT_PATH = Path(__file__).resolve()
PORTFOLIO = SCRIPT_PATH.parent
ROOT = PORTFOLIO.parents[1]

sys.path.insert(0, str(ROOT / "src"))

CASE_ID = "PORT-004"
OPERATOR_RELATIVE_PATH = "evaluation/portfolio/_run_port004_stage3_approval.py"

CASE_RUN_DIR = PORTFOLIO / "runs" / "port-004"
STAGE1_RUN_DIR = CASE_RUN_DIR / "production-run-v0.1"
STAGE2_RUN_DIR = CASE_RUN_DIR / "production-run-v0.2-review"
STAGE3_RUN_DIR = CASE_RUN_DIR / "production-run-v0.3-approved"

CANDIDATE_PATH = STAGE1_RUN_DIR / "candidate_extraction.json"
STAGE1_INGESTION_PATH = STAGE1_RUN_DIR / "ingestion_result.json"
STAGE1_RUN_STATE_PATH = STAGE1_RUN_DIR / "run_state_after_extraction.json"
STAGE1_DATABASE_PATH = STAGE1_RUN_DIR / "workspace.db"

STAGE2_DATABASE_PATH = STAGE2_RUN_DIR / "workspace.db"
STAGE2_EXECUTION_RECORD_PATH = STAGE2_RUN_DIR / "stage2-execution-record.v0.1.json"
STAGE2_OBSERVATION_RECORD_PATH = CASE_RUN_DIR / "stage2-observation-record.v0.1.md"
STAGE1_OBSERVATION_RECORD_PATH = CASE_RUN_DIR / "stage1-observation-record.v0.1.md"
RUN_MANIFEST_PATH = CASE_RUN_DIR / "port-004.run-hashes.sha256"

STAGE3_DATABASE_PATH = STAGE3_RUN_DIR / "workspace.db"
STAGE3_APPROVAL_RECORD_PATH = STAGE3_RUN_DIR / "stage3-approval-record.v0.1.json"
BEFORE_PATH = PORTFOLIO / "product_inputs" / "port-004.before.txt"

# ---- Pinned hashes. Every one is a hard gate. ----------------------------

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
EXPECTED_STAGE2_DATABASE_SHA256 = (
    "0fc81b4a14f2336dc672148fcd91a77db86fb92ac518144cf4ace1718ef82612"
)
EXPECTED_STAGE2_EXECUTION_RECORD_SHA256 = (
    "1c33e51a56ea4482d77ab930cccb5319dccaea92e1d1e4541301ba52505ef51b"
)
EXPECTED_STAGE2_OBSERVATION_RECORD_SHA256 = (
    "19f3457d135c53609acf3e1ecf173633516794c299396df79395ba7afd611d58"
)
EXPECTED_RUN_MANIFEST_SHA256 = (
    "f550977f43556e89d1a3f1588e5b77579157b4887430b8c18187f19631c74e8b"
)
EXPECTED_BEFORE_SHA256 = (
    "98fd4ecece92f0bec27664241013677af1bd67e15816d3f8ba2291b23e017c01"
)
EXPECTED_FINGERPRINT = (
    "3c5c86bd132d25745ee7fcba2e40c3e3d796a9ff404a36a93aecce60cbaf1a85"
)

FROZEN_STAGE1_ARTEFACTS: tuple[tuple[str, Path, str], ...] = (
    ("candidate_extraction.json", CANDIDATE_PATH, EXPECTED_CANDIDATE_SHA256),
    ("ingestion_result.json", STAGE1_INGESTION_PATH, EXPECTED_INGESTION_SHA256),
    (
        "run_state_after_extraction.json",
        STAGE1_RUN_STATE_PATH,
        EXPECTED_RUN_STATE_SHA256,
    ),
    ("workspace.db", STAGE1_DATABASE_PATH, EXPECTED_STAGE1_DATABASE_SHA256),
)

FROZEN_STAGE2_ARTEFACTS: tuple[tuple[str, Path, str], ...] = (
    ("workspace.db (Stage 2)", STAGE2_DATABASE_PATH, EXPECTED_STAGE2_DATABASE_SHA256),
    (
        "stage2-execution-record.v0.1.json",
        STAGE2_EXECUTION_RECORD_PATH,
        EXPECTED_STAGE2_EXECUTION_RECORD_SHA256,
    ),
    (
        "stage2-observation-record.v0.1.md",
        STAGE2_OBSERVATION_RECORD_PATH,
        EXPECTED_STAGE2_OBSERVATION_RECORD_SHA256,
    ),
)

# ---- Pinned review identity, from the frozen ready-but-unapproved freeze --

EXPECTED_ASSESSMENT_ID = "assessment-088291801b5e4e208b0a1d6078aed1bc"
EXPECTED_REVIEW_ID = "review-8f199803fc07467e95dba9950d5ed399"
EXPECTED_REVIEW_ARTIFACT_ID = "artifact-ffc7fe4a9f6540eabd5683fcf50c550b"
EXPECTED_REVIEW_PAYLOAD_SHA256 = (
    "0bd62671726c9a3f6cebfc3359b09a5bfcc0c2016bac6c7d158c80e4eb7af522"
)

STEP1_ID = "candidate-step-8761540c3fb724d5"
STEP2_ID = "candidate-step-df4f0ee1970efb51"
STEP3_ID = "candidate-step-55d273f0f007cf1f"
STEP6_ID = "candidate-step-2d9417a14cf0f937"
STEP7_ID = "candidate-step-69b86f080884cb5a"

EXPECTED_STEPS: tuple[tuple[str, str], ...] = (
    (STEP1_ID, "identifying the field of search"),
    (STEP2_ID, "selecting the proper tool(s) to perform the search"),
    (STEP3_ID, "determining the appropriate search strategy for each search tool selected"),
    ("candidate-step-56dffd383d81b62b", "Prioritize areas to be searched"),
    ("candidate-step-77a07b30101d76fe", "Select search tools"),
    (STEP6_ID, "Conduct Internet searching"),
    (STEP7_ID, "Document Internet search strategies"),
    ("candidate-step-a154c8ee145a50f9", "Conduct a careful and comprehensive search"),
)

# (step_id, dependency index, expected resolved target)
EXPECTED_DEPENDENCIES: tuple[tuple[str, int, str], ...] = (
    (STEP2_ID, 0, STEP1_ID),
    (STEP3_ID, 0, STEP2_ID),
    (STEP7_ID, 0, STEP6_ID),
)

EXPECTED_EVENT_LEDGER = {
    "CORRECT_DEPENDENCY": 2,
    "RESOLVE_CONFLICT": 4,
    "ACCEPT": 9,
    "RETAIN_UNKNOWN": 88,
    "ACCEPT_STEP_ORDER": 1,
}
EXPECTED_EVENT_TOTAL = 104
EXPECTED_STEP_COUNT = 8
EXPECTED_CONFLICT_COUNT = 4
EXPECTED_CRITERIA_UNKNOWN = 80
EXPECTED_ACCOUNTABILITY_UNKNOWN = 8

APPROVAL_RATIONALE = (
    "PORT-004 explicit Phase 4 approval after frozen ready-but-unapproved "
    "checkpoint; action plan v1.1 and Stage 2 checkpoint verified."
)

STOP_BOUNDARY_NOTE = (
    "The frozen Stage 2 ready-but-unapproved database remains immutable. The "
    "standalone REVIEW_SESSION artefact still reads in-review; the approved "
    "snapshot lives inside the separate APPROVED_REVIEW artefact. The workflow "
    "stage is approved. No deterministic assessment, recommendation or decision "
    "package was produced, and no AFTER evidence was accessed."
)


class CaseDataBoundaryError(RuntimeError):
    """A forbidden portfolio file was opened during Stage 3."""


class ApprovalBoundaryError(RuntimeError):
    """A forbidden post-approval operation was attempted."""


class Stage3GateError(RuntimeError):
    """A Stage 3 precondition failed."""


def _fail(message: str) -> SystemExit:
    """Return a SystemExit carrying a STOP message. No compensating mutation."""

    return SystemExit(f"ABORT: {message}\nNo compensating mutation was attempted.")


# --------------------------------------------------------------------------
# Case-data guard
# --------------------------------------------------------------------------


def _sqlite_target_path(target: Any) -> str | None:
    """Resolve the filesystem path a sqlite3.connect target refers to.

    Handles the ``file:/abs/path?mode=ro`` URI form used for read-only opens.
    """

    if not isinstance(target, (str, bytes, os.PathLike)):
        return None
    text = os.fsdecode(target)
    if text.startswith("file:"):
        text = text[len("file:") :]
        text = text.split("?", 1)[0]
    if not text:
        return None
    return os.path.realpath(text)


def install_case_data_guard(mode: str) -> None:
    """Abort if any portfolio file outside the allowlist is opened.

    ``mode`` is ``"dry-run"`` or ``"stage3"``. In ``dry-run`` the only permitted
    sqlite connection is the frozen Stage 2 database, which this operator always
    opens through a read-only URI. In ``stage3`` the only permitted sqlite
    connections are inside the Stage 3 working directory, so neither frozen
    database can be opened as a database at all.
    """

    if mode not in {"dry-run", "stage3"}:  # pragma: no cover - programmer error
        raise ValueError(f"unknown case-data guard mode: {mode!r}")

    portfolio_root = os.path.realpath(PORTFOLIO)
    stage3_root = os.path.realpath(STAGE3_RUN_DIR)
    stage2_database = os.path.realpath(STAGE2_DATABASE_PATH)

    allowed_files = {
        os.path.realpath(BEFORE_PATH),
        os.path.realpath(SCRIPT_PATH),
        os.path.realpath(RUN_MANIFEST_PATH),
        os.path.realpath(STAGE1_OBSERVATION_RECORD_PATH),
    }
    allowed_files |= {os.path.realpath(p) for _n, p, _d in FROZEN_STAGE1_ARTEFACTS}
    allowed_files |= {os.path.realpath(p) for _n, p, _d in FROZEN_STAGE2_ARTEFACTS}

    def _inside_stage3(resolved: str) -> bool:
        return resolved == stage3_root or resolved.startswith(stage3_root + os.sep)

    def hook(event: str, args: tuple[Any, ...]) -> None:
        if event not in {"open", "os.open", "sqlite3.connect"}:
            return
        if event == "sqlite3.connect":
            resolved = _sqlite_target_path(args[0] if args else None)
            if resolved is None:
                raise CaseDataBoundaryError(
                    f"{CASE_ID} Stage 3 guard refused a sqlite3.connect call with an "
                    "unresolvable target."
                )
            if mode == "dry-run":
                if resolved == stage2_database:
                    return
                raise CaseDataBoundaryError(
                    f"{CASE_ID} Stage 3 dry-run refused sqlite3.connect({resolved}). "
                    "Only the frozen Stage 2 database may be opened, and only through "
                    "a read-only URI."
                )
            if _inside_stage3(resolved):
                return
            raise CaseDataBoundaryError(
                f"{CASE_ID} Stage 3 guard refused sqlite3.connect({resolved}). "
                "Only the Stage 3 working database may be opened as a database. The "
                "frozen Stage 1 and Stage 2 databases are verified by hash only."
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
        if mode == "stage3" and _inside_stage3(resolved):
            return
        raise CaseDataBoundaryError(
            f"{CASE_ID} Stage 3 case-data guard refused to open {resolved}. "
            "Only the frozen BEFORE corpus, the frozen Stage 1 and Stage 2 artefacts, "
            "the run manifest, this script and -- in the persistent modes -- the "
            "Stage 3 working directory are permitted."
        )

    sys.addaudithook(hook)


# --------------------------------------------------------------------------
# Approval boundary guard
# --------------------------------------------------------------------------


def install_approval_boundary_guard(service_class: Any) -> None:
    """Make assess / generate_package / reset_to_review raise, in this process.

    ``approve`` is deliberately left intact: it is this operator's one authorised
    mutation. ``review.approval.approve_review`` is deliberately NOT patched,
    because ``review_progress.approval_errors`` calls it as the product's
    side-effect-free readiness check and must keep working.
    """

    def _blocked(name: str):
        def _raise(*_args: Any, **_kwargs: Any):
            raise ApprovalBoundaryError(
                f"{CASE_ID} Stage 3 refused AssessmentWorkspaceService.{name}(). "
                "This operator stops at persisted approval."
            )

        return _raise

    for name in ("assess", "generate_package", "reset_to_review"):
        setattr(service_class, name, _blocked(name))


# --------------------------------------------------------------------------
# Hash / manifest / fingerprint gates
# --------------------------------------------------------------------------


def _print_header(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def verify_pinned_artefacts(label: str) -> dict[str, str]:
    """Hash every frozen artefact as raw bytes and enforce equality."""

    digests: dict[str, str] = {}
    for name, path, expected in FROZEN_STAGE1_ARTEFACTS + FROZEN_STAGE2_ARTEFACTS:
        if not path.is_file():
            raise _fail(f"frozen artefact is missing: {path}")
        digest = _sha256_file(path)
        digests[str(path.relative_to(ROOT))] = digest
        print(f"  {name:<36} {digest}")
        if digest != expected:
            raise _fail(
                f"frozen artefact hash mismatch ({label}): {name}\n"
                f"  expected {expected}\n"
                f"  actual   {digest}"
            )
        print(f"  {'':<36} MATCH")
    return digests


def verify_run_manifest() -> str:
    """Verify the manifest's own hash, then every entry it lists.

    The manifest is never modified by this operator.
    """

    if not RUN_MANIFEST_PATH.is_file():
        raise _fail(f"run manifest is missing: {RUN_MANIFEST_PATH}")
    manifest_digest = _sha256_file(RUN_MANIFEST_PATH)
    print(f"  run manifest sha256                  {manifest_digest}")
    if manifest_digest != EXPECTED_RUN_MANIFEST_SHA256:
        raise _fail(
            "run manifest hash mismatch.\n"
            f"  expected {EXPECTED_RUN_MANIFEST_SHA256}\n"
            f"  actual   {manifest_digest}\n"
            "The PORT-004 freeze manifest has changed since this operator was pinned."
        )
    print("  run manifest hash                    MATCH")

    entries = 0
    for line in RUN_MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, relative = line.partition("  ")
        if not digest or not relative:
            raise _fail(f"unparseable run-manifest line: {line!r}")
        target = CASE_RUN_DIR / relative
        if not target.is_file():
            raise _fail(f"run manifest references a missing file: {relative}")
        actual = _sha256_file(target)
        status = "OK" if actual == digest else "FAILED"
        print(f"    {relative:<52} {status}")
        if actual != digest:
            raise _fail(
                f"run manifest entry failed verification: {relative}\n"
                f"  expected {digest}\n"
                f"  actual   {actual}"
            )
        entries += 1
    print(f"  run manifest entries verified        {entries}")
    return manifest_digest


def run_safety_checks() -> bytes:
    """Every hard gate except execution identity. Returns candidate JSON bytes."""

    print("--- SAFETY CHECKS ---")
    print("  frozen artefacts (raw bytes; the databases are never opened as databases here):")
    verify_pinned_artefacts("pre-execution")

    if not BEFORE_PATH.is_file():
        raise _fail(f"frozen BEFORE corpus is missing: {BEFORE_PATH}")
    before_digest = _sha256_file(BEFORE_PATH)
    print(f"  BEFORE corpus                        {before_digest}")
    if before_digest != EXPECTED_BEFORE_SHA256:
        raise _fail(
            "frozen BEFORE corpus hash mismatch.\n"
            f"  expected {EXPECTED_BEFORE_SHA256}\n"
            f"  actual   {before_digest}"
        )
    print("  BEFORE corpus hash                   MATCH")

    verify_run_manifest()

    fingerprint = production_fingerprint()
    print(f"  production fingerprint               {fingerprint}")
    if fingerprint != EXPECTED_FINGERPRINT:
        raise _fail(
            "production subtree fingerprint mismatch.\n"
            f"  expected {EXPECTED_FINGERPRINT}\n"
            f"  actual   {fingerprint}\n"
            "Production code has changed since this operator was approved."
        )
    print("  production fingerprint               MATCH")
    print("  all safety checks                    PASSED")
    return CANDIDATE_PATH.read_bytes()


# --------------------------------------------------------------------------
# Execution identity
# --------------------------------------------------------------------------


def _git(*args: str) -> tuple[int, str]:
    completed = subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=ROOT, check=False
    )
    return completed.returncode, completed.stdout.strip()


def execution_identity() -> dict[str, Any]:
    """Identify which operator bytes are running, and from what commit.

    Read-only: ``git hash-object`` is called without ``-w``, so no object is
    written and the index is untouched. HEAD is recorded, never pinned -- this
    operator's own commit will advance HEAD by design.
    """

    script_sha256 = hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest()
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
    identity = execution_identity()
    print("--- EXECUTION IDENTITY ---")
    print(f"  git HEAD                             {identity['git_head']}")
    print(f"  operator path                        {identity['operator_path']}")
    print(f"  operator sha256                      {identity['operator_sha256']}")
    print(f"  operator tracked by git              {identity['operator_tracked']}")
    print(f"  blob in HEAD                         {identity['operator_blob_in_head']}")
    print(f"  blob of file being run               {identity['operator_blob_working']}")
    print(f"  matches HEAD exactly                 {identity['operator_matches_head']}")

    if not require_committed:
        print("  gate                                 NOT ENFORCED (dry-run reports only)")
        return identity
    if identity["git_head"] is None:
        raise _fail("git HEAD could not be resolved; this run cannot be attributed.")
    if not identity["operator_matches_head"]:
        raise _fail(
            "the operator being executed is not identical to the version in HEAD.\n"
            f"  HEAD                {identity['git_head']}\n"
            f"  blob in HEAD        {identity['operator_blob_in_head']}\n"
            f"  blob being executed {identity['operator_blob_working']}\n"
            f"  tracked             {identity['operator_tracked']}\n"
            "Persistent Stage 3 modes require the reviewed operator to be committed "
            "first, so every Stage 3 artefact is attributable to an exact commit."
        )
    print("  gate                                 PASSED (executing the committed operator)")
    return identity


# --------------------------------------------------------------------------
# Shared read-only inspection helpers
# --------------------------------------------------------------------------


def _iter_evidence_ids(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "evidence_id" and isinstance(value, str):
                yield value
            else:
                yield from _iter_evidence_ids(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_evidence_ids(item)


def _iter_evidence_id_lists(node: Any) -> Iterator[str]:
    """Evidence identifiers as they appear in the projected Phase 1 model."""

    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"evidence_ids"} and isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        yield item
            elif key == "evidence_id" and isinstance(value, str):
                yield value
            else:
                yield from _iter_evidence_id_lists(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_evidence_id_lists(item)


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


def _sorted_steps(session: Any) -> list:
    return sorted(session.steps, key=lambda item: item.sequence)


def _capability_signal_state(session: Any) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for step in _sorted_steps(session):
        for signal in step.capability_signals:
            assertion = signal.assertion
            state[f"{step.candidate_step_id}:{signal.name}"] = {
                "value": assertion.value,
                "knowledge_state": assertion.knowledge_state.value,
                "disposition": assertion.disposition.value,
                "evidence_ids": sorted(
                    item.evidence_id for item in assertion.evidence
                ),
            }
    return state


def verify_review_session(session: Any, candidate_bytes: bytes, review_status_cls: Any) -> None:
    """Every review-state precondition. Raises Stage3GateError on any difference."""

    def check(label: str, actual: Any, expected: Any) -> None:
        verdict = "OK" if actual == expected else "MISMATCH"
        print(f"  {label:<34} actual={actual!s:<52.52} {verdict}")
        if actual != expected:
            raise Stage3GateError(f"{label} is {actual!r}, expected {expected!r}")

    check("review_id", session.review_id, EXPECTED_REVIEW_ID)
    check("review status", session.status, review_status_cls.IN_REVIEW)
    check("order_accepted", session.order_accepted, True)
    check("event count", len(session.events), EXPECTED_EVENT_TOTAL)
    check("conflict count", len(session.conflicts), EXPECTED_CONFLICT_COUNT)
    check("retained step count", sum(1 for s in session.steps if s.retained), EXPECTED_STEP_COUNT)

    ledger: dict[str, int] = {}
    for event in session.events:
        ledger[event.action.value] = ledger.get(event.action.value, 0) + 1
    print(f"  event ledger                       {ledger}")

    unresolved = [c.code for c in session.conflicts if c.status.value != "resolved"]
    check("unresolved conflicts", unresolved, [])

    for index, (step, (expected_id, expected_activity)) in enumerate(
        zip(_sorted_steps(session), EXPECTED_STEPS, strict=True), start=1
    ):
        if step.candidate_step_id != expected_id or step.sequence != index:
            raise Stage3GateError(
                f"step {index} identity differs: {step.candidate_step_id} at "
                f"sequence {step.sequence}"
            )
        if str(step.activity.value) != expected_activity:
            raise Stage3GateError(
                f"step {index} activity differs: {step.activity.value!r}"
            )
        if not step.retained:
            raise Stage3GateError(f"step {index} is not retained")
    print(f"  step identities and activities     all {EXPECTED_STEP_COUNT} OK")

    by_id = {step.candidate_step_id: step for step in session.steps}
    for step_id, index, expected_target in EXPECTED_DEPENDENCIES:
        dependency = by_id[step_id].dependencies[index]
        if dependency.target_candidate_step_id != expected_target:
            raise Stage3GateError(
                f"dependency {step_id}[{index}] targets "
                f"{dependency.target_candidate_step_id!r}, expected {expected_target!r}"
            )
        if not dependency.retained:
            raise Stage3GateError(f"dependency {step_id}[{index}] is not retained")
    print("  dependency targets                 all 3 exact OK")

    criteria_unknown = sum(
        1
        for step in session.steps
        for item in step.criteria
        if item.assertion.knowledge_state.value == "unknown"
        and item.assertion.value is None
    )
    accountability_unknown = sum(
        1
        for step in session.steps
        if step.human_accountability_required.knowledge_state.value == "unknown"
        and step.human_accountability_required.value is None
    )
    check("criteria UNKNOWN", criteria_unknown, EXPECTED_CRITERIA_UNKNOWN)
    check("accountability UNKNOWN", accountability_unknown, EXPECTED_ACCOUNTABILITY_UNKNOWN)

    dumped = session.model_dump(mode="json")
    check("HUMAN_SUPPLIED assertions", _count_human_supplied(dumped), 0)

    frozen_ids = set(_iter_evidence_ids(json.loads(candidate_bytes)))
    minted = sorted(set(_iter_evidence_ids(dumped)) - frozen_ids)
    check("newly minted evidence", minted, [])

    signals_touched = sum(
        1
        for step in session.steps
        for signal in step.capability_signals
        if signal.assertion.disposition.value != "unreviewed"
    )
    check("capability signals modified", signals_touched, 0)


def verify_readiness(session: Any, approval_errors: Any, build_review_progress: Any) -> Any:
    """Run the product's own readiness path. Never calls the workspace approve()."""

    errors = approval_errors(session)
    progress = build_review_progress(session)
    print(f"  approval_errors                    {errors}")
    print(f"  total/completed/remaining/ready    {progress.total_required}/"
          f"{progress.completed_required}/{progress.remaining_required}/{progress.is_ready}")
    if errors:
        raise Stage3GateError(f"approval_errors is not empty: {errors}")
    if not progress.is_ready:
        raise Stage3GateError("build_review_progress reports the review is not ready")
    return progress


def verify_no_downstream_artefacts(workspace: Any, artifact_type_cls: Any, *, expect_approved: bool) -> None:
    active = workspace.active_artifacts
    approved_present = artifact_type_cls.APPROVED_REVIEW in active
    assessment_present = artifact_type_cls.INTEGRATED_ASSESSMENT_RESULT in active
    package_present = artifact_type_cls.DECISION_PACKAGE_RESULT in active
    print(f"  APPROVED_REVIEW present            {approved_present} (expected {expect_approved})")
    print(f"  INTEGRATED_ASSESSMENT_RESULT       {assessment_present} (expected False)")
    print(f"  DECISION_PACKAGE_RESULT            {package_present} (expected False)")
    if approved_present is not expect_approved:
        raise Stage3GateError(
            f"APPROVED_REVIEW present={approved_present}, expected {expect_approved}"
        )
    if assessment_present or package_present:
        raise Stage3GateError(
            "an integrated assessment or decision package artefact exists; this "
            "operator never runs assessment or packaging"
        )


# --------------------------------------------------------------------------
# Mode: --dry-run
# --------------------------------------------------------------------------


def dry_run(candidate_bytes: bytes) -> None:
    """Read-only. Reads the frozen Stage 2 review through a read-only URI."""

    import sqlite3

    from ai_adoption_engine.models.review import ProcessReviewSession, ReviewStatus
    from ai_adoption_engine.presentation.review_progress import (
        approval_errors,
        build_review_progress,
    )
    from ai_adoption_engine.workspace.models import ArtifactType

    _print_header("DRY RUN — frozen Stage 2 review, read-only")
    print(f"  Stage 3 directory exists           {STAGE3_RUN_DIR.exists()} (expected False here)")

    uri = f"file:{STAGE2_DATABASE_PATH}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        assessments = connection.execute(
            "SELECT assessment_id, current_stage FROM assessments"
        ).fetchall()
        if len(assessments) != 1:
            raise _fail(f"expected exactly one assessment, found {len(assessments)}")
        assessment_id = assessments[0]["assessment_id"]
        stage = assessments[0]["current_stage"]
        print(f"  assessment_id                      {assessment_id}")
        print(f"  workflow stage                     {stage}")
        if assessment_id != EXPECTED_ASSESSMENT_ID:
            raise _fail(f"unexpected assessment_id {assessment_id}")
        if stage != "in-review":
            raise _fail(f"workflow stage is {stage!r}, expected 'in-review'")

        present = sorted(
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT artifact_type FROM assessment_artifacts"
            )
        )
        print(f"  artefact types present             {present}")
        for forbidden in (
            ArtifactType.APPROVED_REVIEW.value,
            ArtifactType.INTEGRATED_ASSESSMENT_RESULT.value,
            ArtifactType.DECISION_PACKAGE_RESULT.value,
        ):
            if forbidden in present:
                raise _fail(f"{forbidden} already exists in the frozen Stage 2 database")

        row = connection.execute(
            """SELECT a.artifact_id, a.payload_json, a.payload_sha256
               FROM assessment_artifacts a
               JOIN active_artifacts v ON v.artifact_id = a.artifact_id
               WHERE v.artifact_type = 'REVIEW_SESSION'"""
        ).fetchone()
        if row is None:
            raise _fail("the frozen Stage 2 database holds no active REVIEW_SESSION")
        print(f"  REVIEW_SESSION artefact id         {row['artifact_id']}")
        print(f"  REVIEW_SESSION payload sha256      {row['payload_sha256']}")
        if row["artifact_id"] != EXPECTED_REVIEW_ARTIFACT_ID:
            raise _fail(f"unexpected REVIEW_SESSION artefact id {row['artifact_id']}")
        if row["payload_sha256"] != EXPECTED_REVIEW_PAYLOAD_SHA256:
            raise _fail(
                "REVIEW_SESSION payload hash mismatch.\n"
                f"  expected {EXPECTED_REVIEW_PAYLOAD_SHA256}\n"
                f"  actual   {row['payload_sha256']}"
            )
        payload = row["payload_json"]
    finally:
        connection.close()

    session = ProcessReviewSession.model_validate(json.loads(payload))
    _print_header("DRY RUN — approval-ready state")
    try:
        verify_review_session(session, candidate_bytes, ReviewStatus)
        verify_readiness(session, approval_errors, build_review_progress)
    except Stage3GateError as failure:
        raise _fail(str(failure)) from failure

    _print_header("CONFIRMATIONS")
    print(f"  Stage 3 directory NOT created      {not STAGE3_RUN_DIR.exists()}")
    print("  AssessmentWorkspaceService.approve() was NOT called.")
    print("  No write connection was opened; the Stage 2 database was read via mode=ro.")
    print("\n--- DRY RUN COMPLETE — NOTHING WAS WRITTEN, NOTHING WAS APPROVED ---")


# --------------------------------------------------------------------------
# Mode: --confirm-init-stage3-workspace
# --------------------------------------------------------------------------


def init_stage3_workspace() -> None:
    """Create the Stage 3 working copy. Approval is NOT performed here."""

    _print_header("STAGE 3 WORKSPACE CREATION")

    if STAGE3_RUN_DIR.exists():
        raise _fail(
            f"the Stage 3 directory already exists: {STAGE3_RUN_DIR.relative_to(ROOT)}\n"
            "This operator does not overwrite it and implements no resume semantics. "
            "Inspect the existing directory and decide explicitly what to do with it."
        )

    print(f"  source (frozen, read-only)         {STAGE2_DATABASE_PATH.relative_to(ROOT)}")
    print(f"  destination                        {STAGE3_DATABASE_PATH.relative_to(ROOT)}")

    STAGE3_RUN_DIR.mkdir(parents=True, exist_ok=False)
    # copyfile opens the source 'rb'. The frozen Stage 2 database is never opened
    # for writing, and never opened as a database.
    shutil.copyfile(STAGE2_DATABASE_PATH, STAGE3_DATABASE_PATH)

    post_copy = _sha256_file(STAGE2_DATABASE_PATH)
    print(f"  frozen Stage 2 db re-hash          {post_copy}")
    if post_copy != EXPECTED_STAGE2_DATABASE_SHA256:
        raise _fail(
            "the frozen Stage 2 database changed during the copy.\n"
            f"  expected {EXPECTED_STAGE2_DATABASE_SHA256}\n"
            f"  actual   {post_copy}"
        )
    print("  frozen Stage 2 unchanged           MATCH")

    stage3_digest = _sha256_file(STAGE3_DATABASE_PATH)
    print(f"  Stage 3 copy sha256                {stage3_digest}")
    if stage3_digest != EXPECTED_STAGE2_DATABASE_SHA256:
        raise _fail("the Stage 3 copy does not match the frozen source byte for byte.")
    print("  byte-identical to source           MATCH")
    print(f"  approval record written            {STAGE3_APPROVAL_RECORD_PATH.exists()} (expected False)")

    print("\n" + "=" * 78)
    print("STAGE 3 WORKSPACE CREATED — REVIEW REMAINS UNAPPROVED.")
    print("=" * 78)
    print("Next, only when authorised: --confirm-approve-review")


# --------------------------------------------------------------------------
# Mode: --confirm-approve-review
# --------------------------------------------------------------------------


def approve_stage3_review(candidate_bytes: bytes, identity: dict[str, Any]) -> None:
    """Verify everything, then make exactly one approval call, then stop."""

    from ai_adoption_engine.models.review import ReviewStatus
    from ai_adoption_engine.presentation.review_progress import (
        approval_errors,
        build_review_progress,
    )
    from ai_adoption_engine.workspace.composition import build_workspace_service
    from ai_adoption_engine.workspace.models import ArtifactType
    from ai_adoption_engine.workspace.service import AssessmentWorkspaceService

    _print_header("STAGE 3 PRISTINE-COPY GATE")
    if not STAGE3_DATABASE_PATH.is_file():
        raise _fail(
            f"the Stage 3 database is missing: {STAGE3_DATABASE_PATH.relative_to(ROOT)}\n"
            "Run --confirm-init-stage3-workspace first."
        )
    stage3_digest = _sha256_file(STAGE3_DATABASE_PATH)
    print(f"  Stage 3 workspace.db sha256        {stage3_digest}")
    if stage3_digest != EXPECTED_STAGE2_DATABASE_SHA256:
        raise _fail(
            "the Stage 3 copy is not pristine.\n"
            f"  expected {EXPECTED_STAGE2_DATABASE_SHA256}\n"
            f"  actual   {stage3_digest}\n"
            "This operator implements no resume semantics. Inspect the Stage 3 "
            "directory read-only and decide explicitly what to do with it."
        )
    print("  pristine copy                      MATCH")
    if STAGE3_APPROVAL_RECORD_PATH.exists():
        raise _fail(
            "a Stage 3 approval record already exists; refusing to approve again."
        )

    install_approval_boundary_guard(AssessmentWorkspaceService)
    print("  approval boundary guard            INSTALLED "
          "(assess / generate_package / reset_to_review now raise)")

    service = build_workspace_service(STAGE3_DATABASE_PATH)
    assessments = service.repository.list_assessments()
    if len(assessments) != 1:
        raise _fail(f"expected exactly one assessment, found {len(assessments)}")
    assessment_id = assessments[0].assessment_id
    print(f"  assessment_id                      {assessment_id}")
    if assessment_id != EXPECTED_ASSESSMENT_ID:
        raise _fail(f"unexpected assessment_id {assessment_id}")

    workspace = service.repository.load_workspace(assessment_id)
    print(f"  workflow stage                     {workspace.assessment.current_stage.value}")
    if workspace.assessment.current_stage.value != "in-review":
        raise _fail(
            f"workflow stage is {workspace.assessment.current_stage.value!r}, "
            "expected 'in-review'"
        )

    _print_header("PRE-APPROVAL VERIFICATION — on the Stage 3 copy, before any mutation")
    try:
        verify_no_downstream_artefacts(workspace, ArtifactType, expect_approved=False)
        stored_review = workspace.active_artifacts.get(ArtifactType.REVIEW_SESSION)
        if stored_review is None:
            raise Stage3GateError("no active REVIEW_SESSION artefact")
        print(f"  REVIEW_SESSION artefact id         {stored_review.artifact_id}")
        print(f"  REVIEW_SESSION payload sha256      {stored_review.payload_sha256}")
        if stored_review.artifact_id != EXPECTED_REVIEW_ARTIFACT_ID:
            raise Stage3GateError(
                f"REVIEW_SESSION artefact id is {stored_review.artifact_id!r}"
            )
        if stored_review.payload_sha256 != EXPECTED_REVIEW_PAYLOAD_SHA256:
            raise Stage3GateError(
                f"REVIEW_SESSION payload sha256 is {stored_review.payload_sha256!r}"
            )
        session = stored_review.payload
        verify_review_session(session, candidate_bytes, ReviewStatus)
        verify_readiness(session, approval_errors, build_review_progress)
    except Stage3GateError as failure:
        raise _fail(
            f"{failure}\n"
            "STOP before approval. AssessmentWorkspaceService.approve() was NOT called "
            "and nothing was persisted by this operator."
        ) from failure

    signals_before = _capability_signal_state(session)
    review_artifact_id = stored_review.artifact_id

    print("\n  ALL PRE-APPROVAL CHECKS PASSED — the single approval call follows.")

    # ---- The one authorised persistent mutation --------------------------
    _print_header("APPROVAL — one call to AssessmentWorkspaceService.approve()")
    print(f"  rationale: {APPROVAL_RATIONALE}")
    result = service.approve(
        assessment_id, rationale=APPROVAL_RATIONALE, approved_at=None
    )
    print(f"  approved is not None               {result.approved is not None}")
    print(f"  errors                             {result.errors}")
    if result.approved is None or result.errors:
        raise _fail(
            "approval did not succeed.\n"
            f"  errors: {result.errors}\n"
            "No retry is attempted and no resume semantics exist. Inspect the Stage 3 "
            "database read-only and re-plan."
        )

    _post_approval(
        service=service,
        assessment_id=assessment_id,
        result=result,
        identity=identity,
        candidate_bytes=candidate_bytes,
        signals_before=signals_before,
        review_artifact_id=review_artifact_id,
        artifact_type_cls=ArtifactType,
    )


def _post_approval(
    *,
    service: Any,
    assessment_id: str,
    result: Any,
    identity: dict[str, Any],
    candidate_bytes: bytes,
    signals_before: dict[str, dict[str, Any]],
    review_artifact_id: str,
    artifact_type_cls: Any,
) -> None:
    """Verify the persisted approval, then write the approval record and stop.

    If anything here fails, the approval is ALREADY PERSISTED. Do not re-run
    approval. See the failure-semantics section of the module docstring.
    """

    _print_header("POST-APPROVAL VERIFICATION")
    workspace = service.repository.load_workspace(assessment_id)
    approved_stored = workspace.active_artifacts.get(artifact_type_cls.APPROVED_REVIEW)
    if approved_stored is None:
        raise _fail(
            "no active APPROVED_REVIEW artefact after a successful approval call. "
            "The approval may be partially persisted; inspect read-only and re-plan."
        )
    print(f"  APPROVED_REVIEW artefact id        {approved_stored.artifact_id}")
    print(f"  APPROVED_REVIEW payload sha256     {approved_stored.payload_sha256}")
    print(f"  revision                           {approved_stored.artifact_revision}")
    print(f"  parent artefact id                 {approved_stored.parent_artifact_id}")
    if approved_stored.artifact_revision != 1:
        raise _fail(f"APPROVED_REVIEW revision is {approved_stored.artifact_revision}")
    if approved_stored.parent_artifact_id != review_artifact_id:
        raise _fail(
            f"APPROVED_REVIEW parent is {approved_stored.parent_artifact_id!r}, "
            f"expected {review_artifact_id!r}"
        )

    approved = approved_stored.payload
    print(f"  embedded review status             {approved.review.status.value}")
    if approved.review.status.value != "approved":
        raise _fail("the embedded review snapshot is not approved")

    stored_review = workspace.active_artifacts.get(artifact_type_cls.REVIEW_SESSION)
    if stored_review is None:
        raise _fail("the standalone REVIEW_SESSION artefact is no longer active")
    print(f"  standalone REVIEW_SESSION status   {stored_review.payload.status.value} "
          "(expected in-review — approve_review snapshots rather than mutating)")
    if stored_review.payload.status.value != "in-review":
        raise _fail(
            "the standalone REVIEW_SESSION status changed; approval must not mutate it"
        )
    if stored_review.payload_sha256 != EXPECTED_REVIEW_PAYLOAD_SHA256:
        raise _fail("the standalone REVIEW_SESSION payload changed during approval")

    stage = workspace.assessment.current_stage.value
    print(f"  workflow stage                     {stage}")
    if stage != "approved":
        raise _fail(f"workflow stage is {stage!r}, expected 'approved'")

    verify_no_downstream_artefacts(workspace, artifact_type_cls, expect_approved=True)

    # WorkspaceSnapshot exposes artefacts, not operations, and the repository has
    # no list-operations accessor. Read the operations table directly through a
    # read-only URI on the Stage 3 database, which the case-data guard permits.
    import sqlite3

    connection = sqlite3.connect(f"file:{STAGE3_DATABASE_PATH}?mode=ro", uri=True)
    try:
        operations = sorted(
            {row[0] for row in connection.execute(
                "SELECT DISTINCT operation_kind FROM assessment_operations"
            )}
        )
    finally:
        connection.close()
    print(f"  recorded operations                {operations}")
    forbidden_operations = {"assess", "generate-package"}
    if set(operations) & forbidden_operations:
        raise _fail(f"an assess or package operation exists: {operations}")

    # ---- Projected BusinessProcess -------------------------------------
    process = approved.business_process
    print(f"\n  projected steps                    {len(process.steps)}")
    if len(process.steps) != EXPECTED_STEP_COUNT:
        raise _fail(f"projected process has {len(process.steps)} steps")
    for index, (step, (expected_id, expected_activity)) in enumerate(
        zip(sorted(process.steps, key=lambda s: s.sequence), EXPECTED_STEPS, strict=True),
        start=1,
    ):
        if step.step_id != expected_id or step.sequence != index:
            raise _fail(f"projected step {index} identity differs: {step.step_id}")
        if step.activity != expected_activity:
            raise _fail(f"projected step {index} activity differs: {step.activity!r}")
    print("  projected step ids and activities  all exact OK")

    projected = {step.step_id: step for step in process.steps}
    for step_id, _index, expected_target in EXPECTED_DEPENDENCIES:
        actual = projected[step_id].dependencies
        if actual != [expected_target]:
            raise _fail(
                f"projected dependencies for {step_id} are {actual}, "
                f"expected [{expected_target!r}]"
            )
    for step_id, step in projected.items():
        if step_id not in {item[0] for item in EXPECTED_DEPENDENCIES} and step.dependencies:
            raise _fail(f"projected step {step_id} has unexpected dependencies")
    print("  projected dependencies             all 3 exact, no others OK")

    criteria_unknown = 0
    accountability_unknown = 0
    for step in process.steps:
        characteristics = step.characteristics
        for name in (
            "repetition",
            "predictability",
            "data_readiness",
            "ai_capability_fit",
            "human_judgement_requirement",
            "business_value",
            "risk_consequence",
            "residual_risk_with_human_oversight",
            "implementation_complexity",
            "conventional_solution_fit",
        ):
            criterion = getattr(characteristics, name)
            if criterion.value is not None or criterion.knowledge_state.value != "unknown":
                raise _fail(
                    f"projected criterion {name} on {step.step_id} is not UNKNOWN"
                )
            criteria_unknown += 1
        accountability = characteristics.human_accountability_required
        if (
            accountability.value is not None
            or accountability.knowledge_state.value != "unknown"
        ):
            raise _fail(
                f"projected human_accountability_required on {step.step_id} is not UNKNOWN"
            )
        accountability_unknown += 1
    print(f"  projected criteria UNKNOWN         {criteria_unknown} (expected 80)")
    print(f"  projected accountability UNKNOWN   {accountability_unknown} (expected 8)")
    if criteria_unknown != EXPECTED_CRITERIA_UNKNOWN:
        raise _fail(f"projected criteria UNKNOWN = {criteria_unknown}")
    if accountability_unknown != EXPECTED_ACCOUNTABILITY_UNKNOWN:
        raise _fail(f"projected accountability UNKNOWN = {accountability_unknown}")

    signals_after = _capability_signal_state(approved.review)
    signals_unchanged = signals_after == signals_before
    print(f"  capability signals unchanged       {signals_unchanged}")
    if not signals_unchanged:
        raise _fail("capability signals changed across approval")

    approved_dump = approved.model_dump(mode="json")
    human_supplied = _count_human_supplied(approved_dump)
    frozen_ids = set(_iter_evidence_ids(json.loads(candidate_bytes)))
    minted = sorted(set(_iter_evidence_id_lists(approved_dump)) - frozen_ids)
    print(f"  HUMAN_SUPPLIED assertions          {human_supplied} (expected 0)")
    print(f"  newly minted evidence              {len(minted)} (expected 0)")
    if human_supplied != 0:
        raise _fail(f"HUMAN_SUPPLIED assertions = {human_supplied}")
    if minted:
        raise _fail(f"approval minted evidence: {minted}")

    _print_header("FROZEN SOURCES — post-approval re-hash")
    frozen_digests = verify_pinned_artefacts("post-approval")
    before_digest = _sha256_file(BEFORE_PATH)
    print(f"  BEFORE corpus                        {before_digest}")
    if before_digest != EXPECTED_BEFORE_SHA256:
        raise _fail("the BEFORE corpus changed during approval")
    manifest_digest = _sha256_file(RUN_MANIFEST_PATH)
    print(f"  run manifest                         {manifest_digest}")
    if manifest_digest != EXPECTED_RUN_MANIFEST_SHA256:
        raise _fail("the run manifest changed during approval")

    stage3_digest = _sha256_file(STAGE3_DATABASE_PATH)
    print(f"  Stage 3 workspace.db (final)         {stage3_digest}")

    record = {
        "case_id": CASE_ID,
        "stage": "stage-3-phase-4-explicit-approval",
        "action_plan_version": "v1.1",
        "execution_identity": identity,
        "production_fingerprint": EXPECTED_FINGERPRINT,
        "source_stage2_database_sha256": EXPECTED_STAGE2_DATABASE_SHA256,
        "source_stage2_execution_record_sha256": EXPECTED_STAGE2_EXECUTION_RECORD_SHA256,
        "source_stage2_observation_record_sha256": (
            EXPECTED_STAGE2_OBSERVATION_RECORD_SHA256
        ),
        "run_manifest_sha256_at_approval": manifest_digest,
        "assessment_id": assessment_id,
        "review_id": approved.review.review_id,
        "review_session_artifact_id": review_artifact_id,
        "review_session_payload_sha256": EXPECTED_REVIEW_PAYLOAD_SHA256,
        "review_session_status_after_approval": stored_review.payload.status.value,
        "approved_review_artifact_id": approved_stored.artifact_id,
        "approved_review_payload_sha256": approved_stored.payload_sha256,
        "approved_review_revision": approved_stored.artifact_revision,
        "approved_review_parent_artifact_id": approved_stored.parent_artifact_id,
        "approval_statement": approved.approval.approval_statement,
        "approved_at": approved.approval.approved_at.isoformat(),
        "approval_rationale": approved.approval.rationale,
        "workflow_stage": stage,
        "projected_process": {
            "process_id": process.process_id,
            "name": process.name,
            "step_count": len(process.steps),
            "steps": [
                {
                    "sequence": step.sequence,
                    "step_id": step.step_id,
                    "activity": step.activity,
                    "dependencies": list(step.dependencies),
                }
                for step in sorted(process.steps, key=lambda s: s.sequence)
            ],
            "evidence_reference_count": len(process.evidence),
        },
        "dependency_targets": {
            step_id: expected for step_id, _index, expected in EXPECTED_DEPENDENCIES
        },
        "criteria_unknown": criteria_unknown,
        "accountability_unknown": accountability_unknown,
        "human_supplied_assertions": human_supplied,
        "newly_minted_evidence_count": len(minted),
        "capability_signals_finding": (
            "Capability signals were copied field-for-field by the Phase 1 projection "
            "and were neither modified nor recomputed during approval; the "
            "pre-approval and post-approval signal states are identical."
        ),
        "integrated_assessment_result_present": False,
        "decision_package_result_present": False,
        "assess_operation_present": False,
        "package_operation_present": False,
        "frozen_source_hashes_after_approval": frozen_digests,
        "before_corpus_sha256": before_digest,
        "stage3_database_sha256": stage3_digest,
        "stop_boundary_note": STOP_BOUNDARY_NOTE,
    }
    STAGE3_APPROVAL_RECORD_PATH.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"  approval record written              {STAGE3_APPROVAL_RECORD_PATH.relative_to(ROOT)}")
    print("  (the record cannot contain its own hash; record it in the run manifest)")

    print("\n" + "=" * 78)
    print("PORT-004 PHASE 4 APPROVAL PERSISTED — ASSESSMENT NOT RUN.")
    print("=" * 78)
    for line in textwrap.wrap(STOP_BOUNDARY_NOTE, 78):
        print(line)
    print("\nSTOP. No deterministic assessment, no recommendation, no decision package.")


# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify every gate and the approval-ready state. Writes nothing, approves nothing.",
    )
    group.add_argument(
        "--confirm-init-stage3-workspace",
        action="store_true",
        help="Create the Stage 3 working copy of the frozen Stage 2 database. Does not approve.",
    )
    group.add_argument(
        "--confirm-approve-review",
        action="store_true",
        help="Make exactly one AssessmentWorkspaceService.approve() call, then stop.",
    )
    args = parser.parse_args(argv)

    if args.dry_run:
        mode_label, guard_mode = "DRY RUN", "dry-run"
    elif args.confirm_init_stage3_workspace:
        mode_label, guard_mode = "INIT STAGE 3 WORKSPACE", "stage3"
    else:
        mode_label, guard_mode = "APPROVE REVIEW", "stage3"

    install_case_data_guard(guard_mode)
    print("=" * 78)
    print(f"{CASE_ID} STAGE 3 / PHASE 4 EXPLICIT APPROVAL ({mode_label})")
    print("=" * 78)
    identity = report_execution_identity(require_committed=not args.dry_run)
    candidate_bytes = run_safety_checks()

    if args.dry_run:
        dry_run(candidate_bytes)
    elif args.confirm_init_stage3_workspace:
        init_stage3_workspace()
    else:
        approve_stage3_review(candidate_bytes, identity)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

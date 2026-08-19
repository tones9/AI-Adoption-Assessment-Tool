"""Stage 4 (Phase 5 deterministic assessment) operator for PORT-004.

Scope
-----
This operator crosses exactly one boundary: it runs the deterministic
integrated assessment against the frozen, approved PORT-004 review and persists
the resulting ``INTEGRATED_ASSESSMENT_RESULT``. It then stops. It never
generates a decision package, a recommendation document, a roadmap, a
governance output or any implementation artefact, it never approves or reopens
a review, and it never touches AFTER material.

It deliberately does **not** modify ``_run_port004_stage3_approval.py``. That
operator's SHA-256 is cited inside the frozen Stage 3 approval record and the
frozen Stage 3 observation record; editing it would retroactively break the
provenance link recorded at the approval freeze. One operator per boundary is
the established pattern for this case.

Three mutually exclusive modes
---------------------------------
``--dry-run``
    Writes nothing, creates nothing, opens no read-write database connection.
    Verifies every frozen hash, the whole PORT-004 run manifest, the production
    fingerprint, and the complete assessment-readiness of the frozen Stage 3
    approved workspace, which it reads through a strictly read-only SQLite URI.

    It **never** calls ``AssessmentWorkspaceService.assess``,
    ``IntegratedAssessmentService.assess`` or ``AssessmentEngine.assess``. It
    reports readiness only, and it deliberately reports **no** expected
    assessment outcome: no recommendation mode, no gate result, no priority.
    Engine output is observed only after the authorised execution.

``--confirm-init-stage4-workspace``
    Creates ``runs/port-004/production-run-v0.4-assessed/`` and copies the frozen
    Stage 3 approved ``workspace.db`` into it byte-for-byte. Assessment is
    **not** run in this mode, and no assessment record is written. Fails closed
    if the Stage 4 directory already exists.

``--confirm-run-assessment``
    Requires the Stage 4 copy to exist and to still be byte-identical to the
    frozen Stage 3 source. Re-verifies every gate, then makes exactly one call
    to ``AssessmentWorkspaceService.assess(...)``, records what the engine
    actually produced, and stops.

Separating workspace creation from the assessment mutation is deliberate: the
copy is a reversible filesystem operation, the assessment is not.

No expected-outcome gating
----------------------------
This operator never asserts a recommendation mode, a gate status, a priority
score or a priority status. Gating on an expected outcome would convert a
finding into a requirement, and the whole point of the PORT-004 retrospective is
that the finding is whatever the frozen evidence produces. Every gate in this
file is an *integrity* gate: identity, hashes, provenance, immutability, absence
of downstream artefacts, and the invariants that must hold whatever the engine
decides -- UNKNOWN stays UNKNOWN, no HUMAN_SUPPLIED value appears, no evidence
is minted. Engine output is recorded verbatim, after the fact, without
comparison to any expectation.

Why assess a copy rather than the frozen Stage 3 database
------------------------------------------------------------
``production-run-v0.3-approved/workspace.db`` is frozen in git at the approval
checkpoint and its SHA-256 is quoted in two committed records. Assessing it in
place would leave those records describing a file that no longer has the stated
hash, and would destroy "approved, never assessed" as an inspectable historical
state. Nothing in the product prevents assessing a copy: ``build_workspace_service``
accepts any database path, all identifiers travel with a byte copy, and
``assess()`` requires only an active ``APPROVED_REVIEW``.

What ``assess()`` actually does
----------------------------------
``AssessmentWorkspaceService.assess`` reads the active ``APPROVED_REVIEW`` and
nothing else -- not the ``REVIEW_SESSION``, not the candidate, not the ingestion
result. It is **operation-tracked**: it opens an ``ASSESS`` operation keyed by
``sha256(approved.artifact_id)``, and if that operation is already ``COMPLETED``
it returns the previously produced artefact without running the engine again. On
success it persists one new ``INTEGRATED_ASSESSMENT_RESULT`` whose parent is the
``APPROVED_REVIEW`` artefact, advancing ``assessments.current_stage`` to
``assessed``. A failure result is still persisted, but the stage stays
``approved``.

``assess()`` does not call ``generate_package()``. Packaging is a separate method
requiring an active *successful* assessment artefact, so nothing cascades.

Note that ``IntegratedAssessmentSuccess`` means the *integration* succeeded, not
that any step was recommended for adoption. This operator records the outcome
either way and never treats a particular recommendation mode as success.

Failure semantics -- no automatic resume, ever
-------------------------------------------------
Read this before re-running anything.

*If Stage 4 copy creation fails midway*: inspect
``production-run-v0.4-assessed/`` by hand. Do not re-run this operator against
it -- ``--confirm-init-stage4-workspace`` refuses an existing directory, and that
refusal is intended. Decide explicitly whether to discard the directory and
re-create it from the frozen Stage 3 copy, or to re-plan.

*If ``--confirm-run-assessment`` fails before the ``assess()`` call*: no
assessment ran and nothing was persisted by this operator. The pristine-copy gate
refuses to proceed against a Stage 4 database whose hash has drifted.

*If ``assess()`` succeeds but post-assessment verification or record writing
fails*: **the assessment is already persisted.** Do not re-run blindly. There is
one asymmetry with Stage 3 worth knowing: because ``assess()`` *is*
operation-tracked, a re-run against the same ``APPROVED_REVIEW`` returns the
stored artefact rather than reassessing -- but that must still be a deliberate,
recorded decision, never an automatic retry. Inspect the Stage 4 database
**read-only**, establish exactly what exists, and recover the documentation
separately. Do not hand-repair the database and do not call ``reset_to_review``.

Case-data boundary
-------------------
Readable: the frozen BEFORE corpus, the four frozen Stage 1 artefacts, the three
frozen Stage 2 freeze artefacts, the three frozen Stage 3 freeze artefacts, the
PORT-004 run manifest, this script, and -- in the persistent modes -- the Stage 4
working directory. Every one of those is hash-verified. ``sqlite3.connect`` is
permitted only for the frozen Stage 3 database in ``--dry-run`` (read-only URI)
and only inside the Stage 4 directory in the persistent modes; the frozen Stage
1, Stage 2 and Stage 3 databases are otherwise verified as raw bytes and never
opened as databases. PORT-001/002/003 material, sealed AFTER packets, the case
register, provenance manifests, leakage audits, source captures and OCR-derived
material are all unreachable. Enforced by an explicit allowlist and a
``sys.addaudithook`` guard.

Usage
-----
All three commands, in order. Both persistent modes require this file to be
committed and byte-identical to HEAD::

    .venv/bin/python evaluation/portfolio/_run_port004_stage4_assessment.py --dry-run
    .venv/bin/python evaluation/portfolio/_run_port004_stage4_assessment.py --confirm-init-stage4-workspace
    .venv/bin/python evaluation/portfolio/_run_port004_stage4_assessment.py --confirm-run-assessment

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
OPERATOR_RELATIVE_PATH = "evaluation/portfolio/_run_port004_stage4_assessment.py"

CASE_RUN_DIR = PORTFOLIO / "runs" / "port-004"
STAGE1_RUN_DIR = CASE_RUN_DIR / "production-run-v0.1"
STAGE2_RUN_DIR = CASE_RUN_DIR / "production-run-v0.2-review"
STAGE3_RUN_DIR = CASE_RUN_DIR / "production-run-v0.3-approved"
STAGE4_RUN_DIR = CASE_RUN_DIR / "production-run-v0.4-assessed"

CANDIDATE_PATH = STAGE1_RUN_DIR / "candidate_extraction.json"
STAGE1_INGESTION_PATH = STAGE1_RUN_DIR / "ingestion_result.json"
STAGE1_RUN_STATE_PATH = STAGE1_RUN_DIR / "run_state_after_extraction.json"
STAGE1_DATABASE_PATH = STAGE1_RUN_DIR / "workspace.db"
STAGE1_OBSERVATION_RECORD_PATH = CASE_RUN_DIR / "stage1-observation-record.v0.1.md"

STAGE2_DATABASE_PATH = STAGE2_RUN_DIR / "workspace.db"
STAGE2_EXECUTION_RECORD_PATH = STAGE2_RUN_DIR / "stage2-execution-record.v0.1.json"
STAGE2_OBSERVATION_RECORD_PATH = CASE_RUN_DIR / "stage2-observation-record.v0.1.md"

STAGE3_DATABASE_PATH = STAGE3_RUN_DIR / "workspace.db"
STAGE3_APPROVAL_RECORD_PATH = STAGE3_RUN_DIR / "stage3-approval-record.v0.1.json"
STAGE3_OBSERVATION_RECORD_PATH = CASE_RUN_DIR / "stage3-observation-record.v0.1.md"

STAGE4_DATABASE_PATH = STAGE4_RUN_DIR / "workspace.db"
STAGE4_ASSESSMENT_RECORD_PATH = STAGE4_RUN_DIR / "stage4-assessment-record.v0.1.json"

RUN_MANIFEST_PATH = CASE_RUN_DIR / "port-004.run-hashes.sha256"
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
EXPECTED_STAGE1_OBSERVATION_RECORD_SHA256 = (
    "db6ecae125e415efe35a11656e73a17e1be752768dffe1e2ead38404b8b32cc1"
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
EXPECTED_STAGE3_DATABASE_SHA256 = (
    "09b4399987814a32b9bc48b01bcd246daee319180ae4d6a2d208932d0ca33e46"
)
EXPECTED_STAGE3_APPROVAL_RECORD_SHA256 = (
    "3cab058cbdf590ab73e45031a9921fd081ea85bfee44fc0dd71c51c97cb4fe7e"
)
EXPECTED_STAGE3_OBSERVATION_RECORD_SHA256 = (
    "341bf6c083e64e9264d96e0256b08b4bcb6c97f0bcd76ff24f1c1588dff44a1b"
)
EXPECTED_RUN_MANIFEST_SHA256 = (
    "4462b37f2832123db34b075cfefba96ac22766130bdcc4790506e3c923653597"
)
EXPECTED_BEFORE_SHA256 = (
    "98fd4ecece92f0bec27664241013677af1bd67e15816d3f8ba2291b23e017c01"
)
EXPECTED_FINGERPRINT = (
    "3c5c86bd132d25745ee7fcba2e40c3e3d796a9ff404a36a93aecce60cbaf1a85"
)

FROZEN_ARTEFACTS: tuple[tuple[str, Path, str], ...] = (
    ("stage1 candidate_extraction.json", CANDIDATE_PATH, EXPECTED_CANDIDATE_SHA256),
    ("stage1 ingestion_result.json", STAGE1_INGESTION_PATH, EXPECTED_INGESTION_SHA256),
    (
        "stage1 run_state_after_extraction.json",
        STAGE1_RUN_STATE_PATH,
        EXPECTED_RUN_STATE_SHA256,
    ),
    ("stage1 workspace.db", STAGE1_DATABASE_PATH, EXPECTED_STAGE1_DATABASE_SHA256),
    (
        "stage1-observation-record.v0.1.md",
        STAGE1_OBSERVATION_RECORD_PATH,
        EXPECTED_STAGE1_OBSERVATION_RECORD_SHA256,
    ),
    ("stage2 workspace.db", STAGE2_DATABASE_PATH, EXPECTED_STAGE2_DATABASE_SHA256),
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
    ("stage3 workspace.db", STAGE3_DATABASE_PATH, EXPECTED_STAGE3_DATABASE_SHA256),
    (
        "stage3-approval-record.v0.1.json",
        STAGE3_APPROVAL_RECORD_PATH,
        EXPECTED_STAGE3_APPROVAL_RECORD_SHA256,
    ),
    (
        "stage3-observation-record.v0.1.md",
        STAGE3_OBSERVATION_RECORD_PATH,
        EXPECTED_STAGE3_OBSERVATION_RECORD_SHA256,
    ),
)

# ---- Pinned identity, from the frozen Stage 3 approval freeze -------------

EXPECTED_ASSESSMENT_ID = "assessment-088291801b5e4e208b0a1d6078aed1bc"
EXPECTED_REVIEW_ID = "review-8f199803fc07467e95dba9950d5ed399"
EXPECTED_REVIEW_ARTIFACT_ID = "artifact-ffc7fe4a9f6540eabd5683fcf50c550b"
EXPECTED_REVIEW_PAYLOAD_SHA256 = (
    "0bd62671726c9a3f6cebfc3359b09a5bfcc0c2016bac6c7d158c80e4eb7af522"
)
EXPECTED_APPROVED_ARTIFACT_ID = "artifact-5d7e6631ce3042e1871e19a9d8d39010"
EXPECTED_APPROVED_PAYLOAD_SHA256 = (
    "c886848bba58ab762410e950083a497977b579157eeba6ac08728aee5368f960"
)
EXPECTED_APPROVED_AT = "2026-08-19T14:04:02.249428+00:00"
EXPECTED_APPROVAL_STATEMENT = "APPROVE CURRENT-STATE PROCESS"

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

EXPECTED_DEPENDENCIES: tuple[tuple[str, str], ...] = (
    (STEP2_ID, STEP1_ID),
    (STEP3_ID, STEP2_ID),
    (STEP7_ID, STEP6_ID),
)

EXPECTED_STEP_COUNT = 8
EXPECTED_CRITERIA_UNKNOWN = 80
EXPECTED_ACCOUNTABILITY_UNKNOWN = 8

CRITERION_FIELD_NAMES = (
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
)

STOP_BOUNDARY_NOTE = (
    "The deterministic assessment result is persisted. No decision package, "
    "recommendation document, executive report, roadmap, governance output or "
    "implementation artefact was generated. The frozen Stage 1, Stage 2 and "
    "Stage 3 artefacts remain immutable, the APPROVED_REVIEW artefact is "
    "unchanged, and no AFTER evidence was accessed."
)


class CaseDataBoundaryError(RuntimeError):
    """A forbidden portfolio file was opened during Stage 4."""


class AssessmentBoundaryError(RuntimeError):
    """A forbidden operation beyond the assessment boundary was attempted."""


class Stage4GateError(RuntimeError):
    """A Stage 4 precondition failed."""


def _fail(message: str) -> SystemExit:
    """Return a SystemExit carrying a STOP message. No compensating mutation."""

    return SystemExit(f"ABORT: {message}\nNo compensating mutation was attempted.")


def _print_header(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    """Abort if any portfolio file outside the allowlist is opened."""

    if mode not in {"dry-run", "stage4"}:  # pragma: no cover - programmer error
        raise ValueError(f"unknown case-data guard mode: {mode!r}")

    portfolio_root = os.path.realpath(PORTFOLIO)
    stage4_root = os.path.realpath(STAGE4_RUN_DIR)
    stage3_database = os.path.realpath(STAGE3_DATABASE_PATH)

    allowed_files = {
        os.path.realpath(BEFORE_PATH),
        os.path.realpath(SCRIPT_PATH),
        os.path.realpath(RUN_MANIFEST_PATH),
    }
    allowed_files |= {os.path.realpath(p) for _n, p, _d in FROZEN_ARTEFACTS}

    def _inside_stage4(resolved: str) -> bool:
        return resolved == stage4_root or resolved.startswith(stage4_root + os.sep)

    def hook(event: str, args: tuple[Any, ...]) -> None:
        if event not in {"open", "os.open", "sqlite3.connect"}:
            return
        if event == "sqlite3.connect":
            resolved = _sqlite_target_path(args[0] if args else None)
            if resolved is None:
                raise CaseDataBoundaryError(
                    f"{CASE_ID} Stage 4 guard refused a sqlite3.connect call with an "
                    "unresolvable target."
                )
            if mode == "dry-run":
                if resolved == stage3_database:
                    return
                raise CaseDataBoundaryError(
                    f"{CASE_ID} Stage 4 dry-run refused sqlite3.connect({resolved}). "
                    "Only the frozen Stage 3 database may be opened, and only through "
                    "a read-only URI."
                )
            if _inside_stage4(resolved):
                return
            raise CaseDataBoundaryError(
                f"{CASE_ID} Stage 4 guard refused sqlite3.connect({resolved}). "
                "Only the Stage 4 working database may be opened as a database. The "
                "frozen Stage 1, Stage 2 and Stage 3 databases are verified by hash only."
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
        if mode == "stage4" and _inside_stage4(resolved):
            return
        raise CaseDataBoundaryError(
            f"{CASE_ID} Stage 4 case-data guard refused to open {resolved}. "
            "Only the frozen BEFORE corpus, the frozen Stage 1/2/3 artefacts, the run "
            "manifest, this script and -- in the persistent modes -- the Stage 4 "
            "working directory are permitted."
        )

    sys.addaudithook(hook)


# --------------------------------------------------------------------------
# Assessment boundary guard
# --------------------------------------------------------------------------


def install_assessment_boundary_guard(service_class: Any) -> None:
    """Make approve / generate_package / reset_to_review raise, in this process.

    ``assess`` is deliberately left intact: it is this operator's one authorised
    mutation. Nothing inside ``IntegratedAssessmentService`` or the deterministic
    engine is patched -- the engine must run exactly as production runs it.
    """

    def _blocked(name: str):
        def _raise(*_args: Any, **_kwargs: Any):
            raise AssessmentBoundaryError(
                f"{CASE_ID} Stage 4 refused AssessmentWorkspaceService.{name}(). "
                "This operator stops at persisted assessment."
            )

        return _raise

    for name in ("approve", "generate_package", "reset_to_review"):
        setattr(service_class, name, _blocked(name))


# --------------------------------------------------------------------------
# Hash / manifest / fingerprint gates
# --------------------------------------------------------------------------


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


def verify_frozen_artefacts(label: str) -> dict[str, str]:
    """Hash every frozen artefact as raw bytes and enforce equality."""

    digests: dict[str, str] = {}
    for name, path, expected in FROZEN_ARTEFACTS:
        if not path.is_file():
            raise _fail(f"frozen artefact is missing: {path}")
        digest = _sha256_file(path)
        digests[str(path.relative_to(ROOT))] = digest
        print(f"  {name:<40} {digest}")
        if digest != expected:
            raise _fail(
                f"frozen artefact hash mismatch ({label}): {name}\n"
                f"  expected {expected}\n"
                f"  actual   {digest}"
            )
        print(f"  {'':<40} MATCH")
    return digests


def verify_run_manifest() -> str:
    """Verify the manifest's own hash, then every entry it lists.

    The manifest is never modified by this operator.
    """

    if not RUN_MANIFEST_PATH.is_file():
        raise _fail(f"run manifest is missing: {RUN_MANIFEST_PATH}")
    manifest_digest = _sha256_file(RUN_MANIFEST_PATH)
    print(f"  run manifest sha256                      {manifest_digest}")
    if manifest_digest != EXPECTED_RUN_MANIFEST_SHA256:
        raise _fail(
            "run manifest hash mismatch.\n"
            f"  expected {EXPECTED_RUN_MANIFEST_SHA256}\n"
            f"  actual   {manifest_digest}\n"
            "The PORT-004 freeze manifest has changed since this operator was pinned."
        )
    print("  run manifest hash                        MATCH")

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
        print(f"    {relative:<56} {status}")
        if actual != digest:
            raise _fail(
                f"run manifest entry failed verification: {relative}\n"
                f"  expected {digest}\n"
                f"  actual   {actual}"
            )
        entries += 1
    print(f"  run manifest entries verified            {entries}")
    return manifest_digest


def run_safety_checks() -> bytes:
    """Every hard gate except execution identity. Returns candidate JSON bytes."""

    print("--- SAFETY CHECKS ---")
    print("  frozen artefacts (raw bytes; the databases are never opened as databases here):")
    verify_frozen_artefacts("pre-execution")

    if not BEFORE_PATH.is_file():
        raise _fail(f"frozen BEFORE corpus is missing: {BEFORE_PATH}")
    before_digest = _sha256_file(BEFORE_PATH)
    print(f"  BEFORE corpus                            {before_digest}")
    if before_digest != EXPECTED_BEFORE_SHA256:
        raise _fail(
            "frozen BEFORE corpus hash mismatch.\n"
            f"  expected {EXPECTED_BEFORE_SHA256}\n"
            f"  actual   {before_digest}"
        )
    print("  BEFORE corpus hash                       MATCH")

    verify_run_manifest()

    fingerprint = production_fingerprint()
    print(f"  production fingerprint                   {fingerprint}")
    if fingerprint != EXPECTED_FINGERPRINT:
        raise _fail(
            "production subtree fingerprint mismatch.\n"
            f"  expected {EXPECTED_FINGERPRINT}\n"
            f"  actual   {fingerprint}\n"
            "Production code has changed since this operator was approved."
        )
    print("  production fingerprint                   MATCH")
    print("  all safety checks                        PASSED")
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
    written and the index is untouched. HEAD is recorded, never pinned.
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
    print(f"  git HEAD                                 {identity['git_head']}")
    print(f"  operator path                            {identity['operator_path']}")
    print(f"  operator sha256                          {identity['operator_sha256']}")
    print(f"  operator tracked by git                  {identity['operator_tracked']}")
    print(f"  blob in HEAD                             {identity['operator_blob_in_head']}")
    print(f"  blob of file being run                   {identity['operator_blob_working']}")
    print(f"  matches HEAD exactly                     {identity['operator_matches_head']}")

    if not require_committed:
        print("  gate                                     NOT ENFORCED (dry-run reports only)")
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
            "Persistent Stage 4 modes require the reviewed operator to be committed "
            "first, so every Stage 4 artefact is attributable to an exact commit."
        )
    print("  gate                                     PASSED (executing the committed operator)")
    return identity


# --------------------------------------------------------------------------
# Shared inspection helpers
# --------------------------------------------------------------------------


def _iter_evidence_ids(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "evidence_id" and isinstance(value, str):
                yield value
            elif key == "evidence_ids" and isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        yield item
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


# ---- Operator-owned projection helpers -----------------------------------
#
# These mirror the semantics the production integration layer applies, but they
# are this operator's own code: no private production symbol is imported. The
# authoritative consistency validation still runs inside
# AssessmentWorkspaceService.assess() and fails closed on any divergence; these
# checks exist so that a divergence is caught and reported *before* the
# mutation rather than as a persisted failure artefact afterwards.


def _reviewed_text(assertion: Any) -> str | None:
    """Projected optional text for a reviewed assertion."""

    if not assertion.retained or assertion.value is None:
        return None
    value = str(assertion.value)
    return value if value.strip() else None


def _collection_values(collection: Any) -> list[str]:
    return [
        str(item.value)
        for item in collection.items
        if item.retained and item.value is not None
    ]


def _first_collection_value(collection: Any) -> str | None:
    values = _collection_values(collection)
    return values[0] if values else None


def _assertion_evidence_ids(assertion: Any) -> list[str]:
    """Evidence a reviewed assertion contributes to the projection."""

    if (
        not assertion.retained
        or assertion.value is None
        or assertion.origin.value == "HUMAN_SUPPLIED"
    ):
        return []
    return [item.evidence_id for item in assertion.evidence]


def _expected_step_evidence(step: Any) -> list[str]:
    """Evidence identifiers a reviewed step should project."""

    evidence_ids: set[str] = set()

    def add_assertion(item: Any) -> None:
        evidence_ids.update(_assertion_evidence_ids(item))

    def add_collection(item: Any) -> None:
        evidence_ids.update(reference.evidence_id for reference in item.evidence)
        for value in item.items:
            add_assertion(value)

    for value in (
        step.activity,
        step.description,
        step.document_order,
        step.human_accountability_required,
    ):
        add_assertion(value)
    for item in (
        step.actors,
        step.responsible_roles,
        step.systems,
        step.inputs,
        step.outputs,
        step.exceptions,
        step.operational_characteristics,
    ):
        add_collection(item)
    for decision in step.decisions:
        if decision.retained:
            add_assertion(decision.condition)
            add_collection(decision.branches)
    for dependency in step.dependencies:
        if dependency.retained:
            add_assertion(dependency.target_label)
            add_assertion(dependency.relationship)
    return sorted(evidence_ids)


def _assertion_projects_as(reviewed: Any, projected: Any, caster: Any) -> bool:
    """Whether a reviewed assertion projects onto its Phase 1 input faithfully."""

    if not reviewed.retained or reviewed.value is None:
        return (
            projected.value is None
            and projected.knowledge_state.value == "unknown"
            and projected.evidence_ids == []
            and projected.confidence is None
        )
    return (
        projected.value == caster(reviewed.value)
        and projected.knowledge_state.value == reviewed.knowledge_state.value
        and projected.confidence == reviewed.confidence
        and projected.evidence_ids == _assertion_evidence_ids(reviewed)
    )


def verify_projection_consistency(approved: Any, process: Any) -> None:
    """Operator-owned check that the projection matches its approved review.

    Field-by-field, against the embedded reviewed record. Raises
    :class:`Stage4GateError` on any divergence.

    Scope note, stated honestly: the process-level evidence map is checked for
    integrity and containment rather than reconstructed as an exact set. The
    production pipeline performs the exact set comparison itself during
    ``assess()``; duplicating that derivation here would mean maintaining a
    second copy of a rule that already exists in production.
    """

    review = approved.review

    if str(process.name) != str(review.process_name.value):
        raise Stage4GateError("projected process name differs from the reviewed value")
    if process.description != _reviewed_text(review.process_description):
        raise Stage4GateError("projected description differs from the reviewed value")
    if process.business_objective != _reviewed_text(review.process_objective):
        raise Stage4GateError("projected objective differs from the reviewed value")
    if process.organisation is not None:
        raise Stage4GateError("projected organisation is not None")

    retained = sorted(
        (step for step in review.steps if step.retained), key=lambda item: item.sequence
    )
    if len(retained) != len(process.steps):
        raise Stage4GateError(
            f"{len(retained)} retained reviewed steps vs {len(process.steps)} projected"
        )

    for reviewed, projected in zip(
        retained, sorted(process.steps, key=lambda s: s.sequence), strict=True
    ):
        where = f"step {projected.step_id}"
        if reviewed.candidate_step_id != projected.step_id:
            raise Stage4GateError(f"{where}: identity differs")
        if reviewed.sequence != projected.sequence:
            raise Stage4GateError(f"{where}: sequence differs")
        if str(reviewed.activity.value) != projected.activity:
            raise Stage4GateError(f"{where}: activity differs")
        if projected.description != _reviewed_text(reviewed.description):
            raise Stage4GateError(f"{where}: description differs")
        if projected.actor != reviewed.primary_actor:
            raise Stage4GateError(f"{where}: actor differs")
        if projected.responsible_role != _first_collection_value(
            reviewed.responsible_roles
        ):
            raise Stage4GateError(f"{where}: responsible_role differs")
        for name in ("systems", "inputs", "outputs", "exceptions"):
            if getattr(projected, name) != _collection_values(getattr(reviewed, name)):
                raise Stage4GateError(f"{where}: {name} differ")
        expected_dependencies = [
            item.target_candidate_step_id
            for item in reviewed.dependencies
            if item.retained and item.target_candidate_step_id is not None
        ]
        if projected.dependencies != expected_dependencies:
            raise Stage4GateError(f"{where}: dependencies differ")
        if sorted(projected.evidence_ids) != _expected_step_evidence(reviewed):
            raise Stage4GateError(f"{where}: evidence_ids differ")

        reviewed_criteria = {item.name.value: item.assertion for item in reviewed.criteria}
        for name in CRITERION_FIELD_NAMES:
            if not _assertion_projects_as(
                reviewed_criteria[name], getattr(projected.characteristics, name), int
            ):
                raise Stage4GateError(f"{where}: criterion {name} differs")
        if not _assertion_projects_as(
            reviewed.human_accountability_required,
            projected.characteristics.human_accountability_required,
            bool,
        ):
            raise Stage4GateError(f"{where}: human_accountability_required differs")
        reviewed_signals = {
            item.name: item.assertion for item in reviewed.capability_signals
        }
        for name, field in projected.characteristics.capability_signals:
            if not _assertion_projects_as(reviewed_signals[name], field, bool):
                raise Stage4GateError(f"{where}: capability signal {name} differs")

    evidence_ids = [item.evidence_id for item in process.evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise Stage4GateError("projected evidence identifiers are not unique")
    known = set(evidence_ids)
    for step in process.steps:
        missing = sorted(set(step.evidence_ids) - known)
        if missing:
            raise Stage4GateError(
                f"step {step.step_id} references evidence absent from the process: {missing}"
            )
    for reference in process.evidence:
        if reference.provenance != "Phase 2 document-supported source evidence":
            raise Stage4GateError(
                f"evidence {reference.evidence_id} has unexpected provenance "
                f"{reference.provenance!r}"
            )
        if reference.knowledge_state.value != "known":
            raise Stage4GateError(
                f"evidence {reference.evidence_id} is not KNOWN"
            )


def verify_approved_artifact(approved: Any, candidate_bytes: bytes) -> None:
    """Every readiness precondition on the approval artefact.

    Deliberately excludes anything about the eventual assessment outcome. These
    are integrity checks only: identity, immutable review content, the invariants
    that must hold whatever the engine decides.

    No private production symbol is imported. Every check below is either an
    explicit assertion in this file or delegates to ``verify_projection_consistency``,
    which is operator-owned. The production pipeline still applies its own
    approval-artefact and projection-consistency validation inside ``assess()``;
    these checks exist to catch a divergence before the mutation rather than as a
    persisted failure artefact afterwards.
    """

    from ai_adoption_engine.models.process import BusinessProcess

    review = approved.review
    if review.review_id != EXPECTED_REVIEW_ID:
        raise Stage4GateError(f"embedded review_id is {review.review_id!r}")
    if review.status.value != "approved":
        raise Stage4GateError(f"embedded review status is {review.status.value!r}")
    if approved.approval.approval_statement != EXPECTED_APPROVAL_STATEMENT:
        raise Stage4GateError("unexpected approval statement")
    if approved.approval.approved_at.isoformat() != EXPECTED_APPROVED_AT:
        raise Stage4GateError(
            f"approved_at is {approved.approval.approved_at.isoformat()!r}"
        )
    print(f"  embedded review_id                       {review.review_id}")
    print(f"  embedded review status                   {review.status.value}")
    print(f"  approved_at                              {approved.approval.approved_at.isoformat()}")

    open_blocking = [
        item.code for item in review.conflicts if item.blocking and item.status.value == "open"
    ]
    if open_blocking:
        raise Stage4GateError(f"open blocking conflicts: {open_blocking}")
    print("  open blocking conflicts                  none OK")

    approval_events = [e for e in review.events if e.action.value == "approve"]
    if len(approval_events) != 1:
        raise Stage4GateError(f"{len(approval_events)} approval events, expected 1")
    if approval_events[0].occurred_at != approved.approval.approved_at:
        raise Stage4GateError("approval event timestamp does not match approval metadata")
    print("  exactly one APPROVE event, timestamps     match OK")

    process = BusinessProcess.model_validate(
        approved.business_process.model_dump(mode="json")
    )
    verify_projection_consistency(approved, process)
    print("  operator projection-consistency check    PASSED")

    if len(process.steps) != EXPECTED_STEP_COUNT:
        raise Stage4GateError(f"projected process has {len(process.steps)} steps")
    for index, (step, (expected_id, expected_activity)) in enumerate(
        zip(sorted(process.steps, key=lambda s: s.sequence), EXPECTED_STEPS, strict=True),
        start=1,
    ):
        if step.step_id != expected_id or step.sequence != index:
            raise Stage4GateError(f"projected step {index} identity differs: {step.step_id}")
        if step.activity != expected_activity:
            raise Stage4GateError(f"projected step {index} activity differs")
    print(f"  projected step ids and activities        all {EXPECTED_STEP_COUNT} exact OK")

    projected = {step.step_id: step for step in process.steps}
    expected_dependency_owners = {item[0] for item in EXPECTED_DEPENDENCIES}
    for step_id, expected_target in EXPECTED_DEPENDENCIES:
        if projected[step_id].dependencies != [expected_target]:
            raise Stage4GateError(
                f"projected dependencies for {step_id} are "
                f"{projected[step_id].dependencies}"
            )
    for step_id, step in projected.items():
        if step_id not in expected_dependency_owners and step.dependencies:
            raise Stage4GateError(f"projected step {step_id} has unexpected dependencies")
    print("  projected dependency targets             all 3 exact, no others OK")

    criteria_unknown = 0
    accountability_unknown = 0
    for step in process.steps:
        for name in CRITERION_FIELD_NAMES:
            criterion = getattr(step.characteristics, name)
            if criterion.value is not None or criterion.knowledge_state.value != "unknown":
                raise Stage4GateError(
                    f"projected criterion {name} on {step.step_id} is not UNKNOWN"
                )
            criteria_unknown += 1
        accountability = step.characteristics.human_accountability_required
        if (
            accountability.value is not None
            or accountability.knowledge_state.value != "unknown"
        ):
            raise Stage4GateError(
                f"projected human_accountability_required on {step.step_id} is not UNKNOWN"
            )
        accountability_unknown += 1
    if criteria_unknown != EXPECTED_CRITERIA_UNKNOWN:
        raise Stage4GateError(f"projected criteria UNKNOWN = {criteria_unknown}")
    if accountability_unknown != EXPECTED_ACCOUNTABILITY_UNKNOWN:
        raise Stage4GateError(
            f"projected accountability UNKNOWN = {accountability_unknown}"
        )
    print(f"  projected criteria UNKNOWN               {criteria_unknown}")
    print(f"  projected accountability UNKNOWN         {accountability_unknown}")

    dumped = approved.model_dump(mode="json")
    human_supplied = _count_human_supplied(dumped)
    if human_supplied != 0:
        raise Stage4GateError(f"HUMAN_SUPPLIED assertions = {human_supplied}")
    frozen_ids = set(_iter_evidence_ids(json.loads(candidate_bytes)))
    minted = sorted(set(_iter_evidence_ids(dumped)) - frozen_ids)
    if minted:
        raise Stage4GateError(f"evidence not present in the frozen candidate: {minted}")
    print("  HUMAN_SUPPLIED assertions                0")
    print("  evidence outside the frozen candidate    none")


# --------------------------------------------------------------------------
# Mode: --dry-run
# --------------------------------------------------------------------------


def dry_run(candidate_bytes: bytes) -> None:
    """Read-only readiness verification. Runs no assessment of any kind."""

    import sqlite3

    from ai_adoption_engine.models.review import ApprovedProcessReview, ProcessReviewSession

    _print_header("DRY RUN — frozen Stage 3 approved workspace, read-only")
    print(f"  Stage 4 directory exists                 {STAGE4_RUN_DIR.exists()} (expected False here)")
    print("  This mode never calls AssessmentWorkspaceService.assess,")
    print("  IntegratedAssessmentService.assess or AssessmentEngine.assess,")
    print("  and reports no expected assessment outcome.")

    uri = f"file:{STAGE3_DATABASE_PATH}?mode=ro"
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
        print(f"\n  assessment_id                            {assessment_id}")
        print(f"  workflow stage                           {stage}")
        if assessment_id != EXPECTED_ASSESSMENT_ID:
            raise _fail(f"unexpected assessment_id {assessment_id}")
        if stage != "approved":
            raise _fail(f"workflow stage is {stage!r}, expected 'approved'")

        present = sorted(
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT artifact_type FROM assessment_artifacts"
            )
        )
        print(f"  artefact types present                   {present}")
        for forbidden in ("INTEGRATED_ASSESSMENT_RESULT", "DECISION_PACKAGE_RESULT"):
            if forbidden in present:
                raise _fail(f"{forbidden} already exists in the frozen Stage 3 database")
        if "APPROVED_REVIEW" not in present:
            raise _fail("the frozen Stage 3 database holds no APPROVED_REVIEW")

        operations = sorted(
            {
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT operation_kind FROM assessment_operations"
                )
            }
        )
        print(f"  recorded operations                      {operations}")
        if set(operations) & {"assess", "generate-package"}:
            raise _fail(f"an assess or package operation already exists: {operations}")

        approved_row = connection.execute(
            """SELECT a.artifact_id, a.artifact_revision, a.parent_artifact_id,
                      a.payload_json, a.payload_sha256
               FROM assessment_artifacts a
               JOIN active_artifacts v ON v.artifact_id = a.artifact_id
               WHERE v.artifact_type = 'APPROVED_REVIEW'"""
        ).fetchone()
        review_row = connection.execute(
            """SELECT a.artifact_id, a.payload_json, a.payload_sha256
               FROM assessment_artifacts a
               JOIN active_artifacts v ON v.artifact_id = a.artifact_id
               WHERE v.artifact_type = 'REVIEW_SESSION'"""
        ).fetchone()
    finally:
        connection.close()

    if approved_row is None or review_row is None:
        raise _fail("the frozen Stage 3 database is missing an expected active artefact")

    print(f"\n  APPROVED_REVIEW artefact id              {approved_row['artifact_id']}")
    print(f"  APPROVED_REVIEW payload sha256           {approved_row['payload_sha256']}")
    print(f"  APPROVED_REVIEW revision                 {approved_row['artifact_revision']}")
    print(f"  APPROVED_REVIEW parent                   {approved_row['parent_artifact_id']}")
    if approved_row["artifact_id"] != EXPECTED_APPROVED_ARTIFACT_ID:
        raise _fail(f"unexpected APPROVED_REVIEW artefact id {approved_row['artifact_id']}")
    if approved_row["payload_sha256"] != EXPECTED_APPROVED_PAYLOAD_SHA256:
        raise _fail("APPROVED_REVIEW payload hash mismatch")
    if approved_row["artifact_revision"] != 1:
        raise _fail("APPROVED_REVIEW revision is not 1")
    if approved_row["parent_artifact_id"] != EXPECTED_REVIEW_ARTIFACT_ID:
        raise _fail("APPROVED_REVIEW parent artefact is not the frozen REVIEW_SESSION")

    print(f"  REVIEW_SESSION artefact id               {review_row['artifact_id']}")
    print(f"  REVIEW_SESSION payload sha256            {review_row['payload_sha256']}")
    if review_row["artifact_id"] != EXPECTED_REVIEW_ARTIFACT_ID:
        raise _fail("unexpected REVIEW_SESSION artefact id")
    if review_row["payload_sha256"] != EXPECTED_REVIEW_PAYLOAD_SHA256:
        raise _fail("REVIEW_SESSION payload hash mismatch")
    standalone = ProcessReviewSession.model_validate(json.loads(review_row["payload_json"]))
    print(f"  standalone REVIEW_SESSION status         {standalone.status.value} "
          "(expected in-review)")
    if standalone.status.value != "in-review":
        raise _fail("the standalone REVIEW_SESSION is not in-review")

    approved = ApprovedProcessReview.model_validate(json.loads(approved_row["payload_json"]))
    _print_header("DRY RUN — assessment readiness (integrity only, no outcome)")
    try:
        verify_approved_artifact(approved, candidate_bytes)
    except Stage4GateError as failure:
        raise _fail(str(failure)) from failure

    _print_header("CONFIRMATIONS")
    print(f"  Stage 4 directory NOT created            {not STAGE4_RUN_DIR.exists()}")
    print("  No assessment of any kind was executed.")
    print("  No recommendation mode, gate result or priority was computed or reported.")
    print("  No write connection was opened; Stage 3 was read via mode=ro.")
    print("\n--- DRY RUN COMPLETE — NOTHING WAS WRITTEN, NOTHING WAS ASSESSED ---")


# --------------------------------------------------------------------------
# Mode: --confirm-init-stage4-workspace
# --------------------------------------------------------------------------


def init_stage4_workspace() -> None:
    """Create the Stage 4 working copy. Assessment is NOT run here."""

    _print_header("STAGE 4 WORKSPACE CREATION")

    if STAGE4_RUN_DIR.exists():
        raise _fail(
            f"the Stage 4 directory already exists: {STAGE4_RUN_DIR.relative_to(ROOT)}\n"
            "This operator does not overwrite it and implements no resume semantics. "
            "Inspect the existing directory and decide explicitly what to do with it."
        )

    print(f"  source (frozen, read-only)               {STAGE3_DATABASE_PATH.relative_to(ROOT)}")
    print(f"  destination                              {STAGE4_DATABASE_PATH.relative_to(ROOT)}")

    STAGE4_RUN_DIR.mkdir(parents=True, exist_ok=False)
    # copyfile opens the source 'rb'. The frozen Stage 3 database is never opened
    # for writing, and never opened as a database.
    shutil.copyfile(STAGE3_DATABASE_PATH, STAGE4_DATABASE_PATH)

    post_copy = _sha256_file(STAGE3_DATABASE_PATH)
    print(f"  frozen Stage 3 db re-hash                {post_copy}")
    if post_copy != EXPECTED_STAGE3_DATABASE_SHA256:
        raise _fail(
            "the frozen Stage 3 database changed during the copy.\n"
            f"  expected {EXPECTED_STAGE3_DATABASE_SHA256}\n"
            f"  actual   {post_copy}"
        )
    print("  frozen Stage 3 unchanged                 MATCH")

    stage4_digest = _sha256_file(STAGE4_DATABASE_PATH)
    print(f"  Stage 4 copy sha256                      {stage4_digest}")
    if stage4_digest != EXPECTED_STAGE3_DATABASE_SHA256:
        raise _fail("the Stage 4 copy does not match the frozen source byte for byte.")
    print("  byte-identical to source                 MATCH")
    print(f"  assessment record written                {STAGE4_ASSESSMENT_RECORD_PATH.exists()} (expected False)")

    print("\n" + "=" * 78)
    print("STAGE 4 WORKSPACE CREATED — ASSESSMENT NOT RUN.")
    print("=" * 78)
    print("Next, only when authorised: --confirm-run-assessment")


# --------------------------------------------------------------------------
# Mode: --confirm-run-assessment
# --------------------------------------------------------------------------


def run_stage4_assessment(candidate_bytes: bytes, identity: dict[str, Any]) -> None:
    """Verify everything, then make exactly one assess call, then stop."""

    from ai_adoption_engine.models.integrated_assessment import (
        IntegratedAssessmentFailure,
        IntegratedAssessmentSuccess,
    )
    from ai_adoption_engine.workspace.composition import build_workspace_service
    from ai_adoption_engine.workspace.models import ArtifactType
    from ai_adoption_engine.workspace.service import AssessmentWorkspaceService

    _print_header("STAGE 4 PRISTINE-COPY GATE")
    if not STAGE4_DATABASE_PATH.is_file():
        raise _fail(
            f"the Stage 4 database is missing: {STAGE4_DATABASE_PATH.relative_to(ROOT)}\n"
            "Run --confirm-init-stage4-workspace first."
        )
    stage4_digest = _sha256_file(STAGE4_DATABASE_PATH)
    print(f"  Stage 4 workspace.db sha256              {stage4_digest}")
    if stage4_digest != EXPECTED_STAGE3_DATABASE_SHA256:
        raise _fail(
            "the Stage 4 copy is not pristine.\n"
            f"  expected {EXPECTED_STAGE3_DATABASE_SHA256}\n"
            f"  actual   {stage4_digest}\n"
            "This operator implements no resume semantics. Inspect the Stage 4 "
            "directory read-only and decide explicitly what to do with it."
        )
    print("  pristine copy                            MATCH")
    if STAGE4_ASSESSMENT_RECORD_PATH.exists():
        raise _fail(
            "a Stage 4 assessment record already exists; refusing to assess again."
        )

    install_assessment_boundary_guard(AssessmentWorkspaceService)
    print("  assessment boundary guard                INSTALLED "
          "(approve / generate_package / reset_to_review now raise)")

    service = build_workspace_service(STAGE4_DATABASE_PATH)
    assessments = service.repository.list_assessments()
    if len(assessments) != 1:
        raise _fail(f"expected exactly one assessment, found {len(assessments)}")
    assessment_id = assessments[0].assessment_id
    print(f"  assessment_id                            {assessment_id}")
    if assessment_id != EXPECTED_ASSESSMENT_ID:
        raise _fail(f"unexpected assessment_id {assessment_id}")

    workspace = service.repository.load_workspace(assessment_id)
    stage = workspace.assessment.current_stage.value
    print(f"  workflow stage                           {stage}")
    if stage != "approved":
        raise _fail(f"workflow stage is {stage!r}, expected 'approved'")

    _print_header("PRE-ASSESSMENT VERIFICATION — on the Stage 4 copy, before any mutation")
    active = workspace.active_artifacts
    if ArtifactType.INTEGRATED_ASSESSMENT_RESULT in active:
        raise _fail("an INTEGRATED_ASSESSMENT_RESULT already exists")
    if ArtifactType.DECISION_PACKAGE_RESULT in active:
        raise _fail("a DECISION_PACKAGE_RESULT already exists")
    approved_stored = active.get(ArtifactType.APPROVED_REVIEW)
    review_stored = active.get(ArtifactType.REVIEW_SESSION)
    if approved_stored is None or review_stored is None:
        raise _fail("the Stage 4 copy is missing an expected active artefact")
    print(f"  APPROVED_REVIEW artefact id              {approved_stored.artifact_id}")
    print(f"  APPROVED_REVIEW payload sha256           {approved_stored.payload_sha256}")
    if approved_stored.artifact_id != EXPECTED_APPROVED_ARTIFACT_ID:
        raise _fail("unexpected APPROVED_REVIEW artefact id")
    if approved_stored.payload_sha256 != EXPECTED_APPROVED_PAYLOAD_SHA256:
        raise _fail("APPROVED_REVIEW payload hash mismatch")
    if approved_stored.artifact_revision != 1:
        raise _fail("APPROVED_REVIEW revision is not 1")
    if approved_stored.parent_artifact_id != EXPECTED_REVIEW_ARTIFACT_ID:
        raise _fail("APPROVED_REVIEW parent artefact is not the frozen REVIEW_SESSION")
    if review_stored.payload_sha256 != EXPECTED_REVIEW_PAYLOAD_SHA256:
        raise _fail("REVIEW_SESSION payload hash mismatch")
    if review_stored.payload.status.value != "in-review":
        raise _fail("the standalone REVIEW_SESSION is not in-review")
    print("  REVIEW_SESSION unchanged and in-review   OK")

    try:
        verify_approved_artifact(approved_stored.payload, candidate_bytes)
    except Stage4GateError as failure:
        raise _fail(
            f"{failure}\n"
            "STOP before assessment. AssessmentWorkspaceService.assess() was NOT called "
            "and nothing was persisted by this operator."
        ) from failure

    print("\n  ALL PRE-ASSESSMENT CHECKS PASSED — the single assessment call follows.")

    # ---- The one authorised persistent mutation --------------------------
    _print_header("ASSESSMENT — one call to AssessmentWorkspaceService.assess()")
    result = service.assess(assessment_id)
    is_success = isinstance(result, IntegratedAssessmentSuccess)
    is_failure = isinstance(result, IntegratedAssessmentFailure)
    print(f"  result type                              {type(result).__name__}")
    print(f"  IntegratedAssessmentSuccess              {is_success}")
    if is_failure:
        for error in result.errors:
            print(f"    error code={error.code.value} field_path={error.field_path} "
                  f"step_id={error.step_id}")
            print(f"      {error.message}")
        raise _fail(
            "the integrated assessment returned a failure result. It has been persisted "
            "by the product as the assessment outcome; the workflow stage remains "
            "'approved'. Do not re-run this operator: assess() is operation-tracked and "
            "a re-run would return the stored artefact rather than reassessing. Inspect "
            "the Stage 4 database read-only and re-plan."
        )
    if not is_success:
        raise _fail(f"unexpected assessment result type {type(result).__name__}")

    _post_assessment(
        service=service,
        assessment_id=assessment_id,
        result=result,
        identity=identity,
        candidate_bytes=candidate_bytes,
        approved_stored=approved_stored,
        review_stored=review_stored,
        artifact_type_cls=ArtifactType,
    )


def _post_assessment(
    *,
    service: Any,
    assessment_id: str,
    result: Any,
    identity: dict[str, Any],
    candidate_bytes: bytes,
    approved_stored: Any,
    review_stored: Any,
    artifact_type_cls: Any,
) -> None:
    """Verify integrity, record what the engine produced, then stop.

    If anything here fails, the assessment is ALREADY PERSISTED. Do not re-run.
    See the failure-semantics section of the module docstring.
    """

    import sqlite3

    _print_header("POST-ASSESSMENT VERIFICATION — integrity only")
    workspace = service.repository.load_workspace(assessment_id)
    stored = workspace.active_artifacts.get(artifact_type_cls.INTEGRATED_ASSESSMENT_RESULT)
    if stored is None:
        raise _fail(
            "no active INTEGRATED_ASSESSMENT_RESULT after a successful assessment call. "
            "The assessment may be partially persisted; inspect read-only and re-plan."
        )
    print(f"  assessment artefact id                   {stored.artifact_id}")
    print(f"  assessment payload sha256                {stored.payload_sha256}")
    print(f"  revision                                 {stored.artifact_revision}")
    print(f"  parent artefact id                       {stored.parent_artifact_id}")
    if stored.artifact_revision != 1:
        raise _fail(f"assessment artefact revision is {stored.artifact_revision}")
    if stored.parent_artifact_id != approved_stored.artifact_id:
        raise _fail(
            f"assessment parent is {stored.parent_artifact_id!r}, expected "
            f"{approved_stored.artifact_id!r}"
        )
    if artifact_type_cls.DECISION_PACKAGE_RESULT in workspace.active_artifacts:
        raise _fail("a DECISION_PACKAGE_RESULT exists; this operator never packages")
    print("  DECISION_PACKAGE_RESULT present          False")

    stage = workspace.assessment.current_stage.value
    print(f"  workflow stage                           {stage}")
    if stage != "assessed":
        raise _fail(f"workflow stage is {stage!r}, expected 'assessed'")

    approved_after = workspace.active_artifacts.get(artifact_type_cls.APPROVED_REVIEW)
    review_after = workspace.active_artifacts.get(artifact_type_cls.REVIEW_SESSION)
    if approved_after is None or review_after is None:
        raise _fail("an upstream artefact is no longer active after assessment")
    if approved_after.payload_sha256 != approved_stored.payload_sha256:
        raise _fail("the APPROVED_REVIEW payload changed during assessment")
    if review_after.payload_sha256 != review_stored.payload_sha256:
        raise _fail("the REVIEW_SESSION payload changed during assessment")
    if review_after.payload.status.value != "in-review":
        raise _fail("the standalone REVIEW_SESSION status changed during assessment")
    print("  APPROVED_REVIEW unchanged                OK")
    print("  REVIEW_SESSION unchanged and in-review   OK")

    connection = sqlite3.connect(f"file:{STAGE4_DATABASE_PATH}?mode=ro", uri=True)
    try:
        operations = sorted(
            {
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT operation_kind FROM assessment_operations"
                )
            }
        )
        assess_status = sorted(
            {
                row[0]
                for row in connection.execute(
                    "SELECT status FROM assessment_operations WHERE operation_kind = 'assess'"
                )
            }
        )
    finally:
        connection.close()
    print(f"  recorded operations                      {operations}")
    print(f"  assess operation status                  {assess_status}")
    if "generate-package" in operations:
        raise _fail("a generate-package operation exists")
    if assess_status != ["completed"]:
        raise _fail(f"assess operation status is {assess_status}, expected ['completed']")

    assessment = result.process_assessment
    step_ids = [item.step_id for item in assessment.step_assessments]
    expected_ids = [item[0] for item in EXPECTED_STEPS]
    print(f"  step assessments                         {len(step_ids)}")
    if step_ids != expected_ids:
        raise _fail("the assessment does not carry exactly one result per process step, in order")
    print("  one result per step, in order            OK")

    criteria_unknown = 0
    accountability_unknown = 0
    for step_assessment in assessment.step_assessments:
        for criterion in step_assessment.criteria:
            if criterion.value is None and criterion.knowledge_state.value == "unknown":
                criteria_unknown += 1
        accountability = step_assessment.human_accountability
        if accountability.value is None and accountability.knowledge_state.value == "unknown":
            accountability_unknown += 1
    print(f"  criteria still UNKNOWN                   {criteria_unknown}")
    print(f"  accountability still UNKNOWN             {accountability_unknown}")
    if criteria_unknown != EXPECTED_CRITERIA_UNKNOWN:
        raise _fail(f"criteria UNKNOWN in the assessment = {criteria_unknown}")
    if accountability_unknown != EXPECTED_ACCOUNTABILITY_UNKNOWN:
        raise _fail(f"accountability UNKNOWN in the assessment = {accountability_unknown}")

    result_dump = result.model_dump(mode="json")
    human_supplied = _count_human_supplied(result_dump)
    frozen_ids = set(_iter_evidence_ids(json.loads(candidate_bytes)))
    minted = sorted(set(_iter_evidence_ids(result_dump)) - frozen_ids)
    print(f"  HUMAN_SUPPLIED assertions                {human_supplied}")
    print(f"  evidence outside the frozen candidate    {len(minted)}")
    if human_supplied != 0:
        raise _fail(f"HUMAN_SUPPLIED assertions = {human_supplied}")
    if minted:
        raise _fail(f"assessment referenced evidence outside the frozen candidate: {minted}")

    # ---- Engine output, recorded and never gated on ----------------------
    _print_header("ENGINE OUTPUT — recorded as observed, not compared to any expectation")
    print(f"  policy_id                                {result.policy.policy_id}")
    print(f"  policy_version                           {result.policy.policy_version}")
    print(f"  policy_status                            {result.policy.policy_status}")
    print(f"  decision_policy_fingerprint              {result.policy.decision_policy_fingerprint}")
    print(f"  assessment_run_id                        {result.metadata.assessment_run_id}")
    print(f"  assessed_at                              {result.metadata.assessed_at.isoformat()}")
    observed_steps = []
    for step_assessment in assessment.step_assessments:
        entry = {
            "step_id": step_assessment.step_id,
            "activity": step_assessment.activity,
            "recommendation_mode": step_assessment.recommendation_mode.value,
            "capabilities": [item.value for item in step_assessment.capabilities],
            "priority": step_assessment.priority,
            "priority_status": step_assessment.priority_status.value,
            "priority_missing_criteria": [
                item.value for item in step_assessment.priority_missing_criteria
            ],
            "gate_results": [
                {
                    "gate": gate.gate.value,
                    "status": gate.status.value,
                    "rationale": gate.rationale,
                }
                for gate in step_assessment.gate_results
            ],
        }
        observed_steps.append(entry)
        print(
            f"    {entry['step_id']}  mode={entry['recommendation_mode']}  "
            f"priority_status={entry['priority_status']}  "
            f"capabilities={entry['capabilities']}"
        )

    _print_header("FROZEN SOURCES — post-assessment re-hash")
    frozen_digests = verify_frozen_artefacts("post-assessment")
    before_digest = _sha256_file(BEFORE_PATH)
    print(f"  BEFORE corpus                            {before_digest}")
    if before_digest != EXPECTED_BEFORE_SHA256:
        raise _fail("the BEFORE corpus changed during assessment")
    manifest_digest = _sha256_file(RUN_MANIFEST_PATH)
    print(f"  run manifest                             {manifest_digest}")
    if manifest_digest != EXPECTED_RUN_MANIFEST_SHA256:
        raise _fail("the run manifest changed during assessment")
    stage4_digest = _sha256_file(STAGE4_DATABASE_PATH)
    print(f"  Stage 4 workspace.db (final)             {stage4_digest}")

    record = {
        "case_id": CASE_ID,
        "stage": "stage-4-phase-5-deterministic-assessment",
        "execution_identity": identity,
        "production_fingerprint": EXPECTED_FINGERPRINT,
        "source_stage3_database_sha256": EXPECTED_STAGE3_DATABASE_SHA256,
        "source_stage3_approval_record_sha256": EXPECTED_STAGE3_APPROVAL_RECORD_SHA256,
        "source_stage3_observation_record_sha256": (
            EXPECTED_STAGE3_OBSERVATION_RECORD_SHA256
        ),
        "run_manifest_sha256_at_assessment": manifest_digest,
        "assessment_id": assessment_id,
        "review_id": EXPECTED_REVIEW_ID,
        "review_session_artifact_id": EXPECTED_REVIEW_ARTIFACT_ID,
        "review_session_payload_sha256": EXPECTED_REVIEW_PAYLOAD_SHA256,
        "review_session_status_after_assessment": review_after.payload.status.value,
        "approved_review_artifact_id": approved_stored.artifact_id,
        "approved_review_payload_sha256": approved_stored.payload_sha256,
        "integrated_assessment_artifact_id": stored.artifact_id,
        "integrated_assessment_payload_sha256": stored.payload_sha256,
        "integrated_assessment_revision": stored.artifact_revision,
        "integrated_assessment_parent_artifact_id": stored.parent_artifact_id,
        "assessment_run_id": result.metadata.assessment_run_id,
        "assessed_at": result.metadata.assessed_at.isoformat(),
        "integration_schema_version": result.metadata.integration_schema_version,
        "phase1_contract_version": result.metadata.phase1_contract_version,
        "policy_id": result.policy.policy_id,
        "policy_version": result.policy.policy_version,
        "policy_status": result.policy.policy_status,
        "decision_policy_fingerprint": result.policy.decision_policy_fingerprint,
        "workflow_stage": stage,
        "observed_step_assessments": observed_steps,
        "criteria_unknown": criteria_unknown,
        "accountability_unknown": accountability_unknown,
        "human_supplied_assertions": human_supplied,
        "newly_minted_evidence_count": len(minted),
        "decision_package_result_present": False,
        "package_operation_present": False,
        "recorded_operations": operations,
        "frozen_source_hashes_after_assessment": frozen_digests,
        "before_corpus_sha256": before_digest,
        "stage4_database_sha256": stage4_digest,
        "stop_boundary_note": STOP_BOUNDARY_NOTE,
        "outcome_gating_note": (
            "This operator asserts no expected recommendation mode, gate status or "
            "priority. Engine output above is recorded exactly as produced."
        ),
    }
    STAGE4_ASSESSMENT_RECORD_PATH.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"  assessment record written                {STAGE4_ASSESSMENT_RECORD_PATH.relative_to(ROOT)}")
    print("  (the record cannot contain its own hash; record it in the run manifest)")

    print("\n" + "=" * 78)
    print("PORT-004 DETERMINISTIC ASSESSMENT PERSISTED — NO DECISION PACKAGE GENERATED.")
    print("=" * 78)
    for line in textwrap.wrap(STOP_BOUNDARY_NOTE, 78):
        print(line)
    print("\nSTOP. No decision package, no recommendation document, no implementation output.")


# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify every gate and assessment readiness. Writes nothing, assesses nothing.",
    )
    group.add_argument(
        "--confirm-init-stage4-workspace",
        action="store_true",
        help="Create the Stage 4 working copy of the frozen Stage 3 database. Does not assess.",
    )
    group.add_argument(
        "--confirm-run-assessment",
        action="store_true",
        help="Make exactly one AssessmentWorkspaceService.assess() call, then stop.",
    )
    args = parser.parse_args(argv)

    if args.dry_run:
        mode_label, guard_mode = "DRY RUN", "dry-run"
    elif args.confirm_init_stage4_workspace:
        mode_label, guard_mode = "INIT STAGE 4 WORKSPACE", "stage4"
    else:
        mode_label, guard_mode = "RUN ASSESSMENT", "stage4"

    install_case_data_guard(guard_mode)
    print("=" * 78)
    print(f"{CASE_ID} STAGE 4 / PHASE 5 DETERMINISTIC ASSESSMENT ({mode_label})")
    print("=" * 78)
    identity = report_execution_identity(require_committed=not args.dry_run)
    candidate_bytes = run_safety_checks()

    if args.dry_run:
        dry_run(candidate_bytes)
    elif args.confirm_init_stage4_workspace:
        init_stage4_workspace()
    else:
        run_stage4_assessment(candidate_bytes, identity)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

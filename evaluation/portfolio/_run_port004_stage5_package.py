"""Stage 5 (Phase 6 decision package generation) operator for PORT-004.

Scope
-----
This operator crosses exactly one boundary: it generates the deterministic
decision-support package from the frozen, assessed PORT-004 workspace and
persists the resulting ``DECISION_PACKAGE_RESULT``. It then stops. This is the
terminal stage of the product workflow -- nothing downstream of
``DECISION_PACKAGE_RESULT`` exists in ``ArtifactType`` -- so the operator
produces no implementation, deployment or rollout artefact of any kind, and it
never touches AFTER material.

It deliberately does **not** modify ``_run_port004_stage4_assessment.py``. That
operator's SHA-256 is cited inside the frozen Stage 4 assessment record and the
frozen Stage 4 observation record; editing it would retroactively break the
provenance link recorded at the assessment freeze. One operator per boundary is
the established pattern for this case: Stage 3 did not extend Stage 2, Stage 4
did not extend Stage 3, and Stage 5 does not extend Stage 4.

Three mutually exclusive modes
---------------------------------
``--dry-run``
    Writes nothing, creates nothing, opens no read-write database connection.
    Verifies every frozen hash, the whole PORT-004 run manifest, the production
    fingerprint, and the packaging readiness of the frozen Stage 4 assessed
    workspace, which it reads through a strictly read-only SQLite URI.

    It **never** calls ``AssessmentWorkspaceService.generate_package``, never
    touches ``DecisionSupportPackageService``, and never calculates or displays
    any predicted package outcome -- no completeness classification, no
    future-state content, no roadmap, no governance text, no package id.
    Readiness is a structural property; package content is observed only after
    the authorised generation.

``--confirm-init-stage5-workspace``
    Creates ``runs/port-004/production-run-v0.5-packaged/`` and copies the
    frozen Stage 4 ``workspace.db`` into it byte-for-byte. Package generation is
    **not** performed in this mode, and no package record is written. Fails
    closed if the Stage 5 directory already exists.

``--confirm-generate-package``
    Requires the Stage 5 copy to exist and to still be byte-identical to the
    frozen Stage 4 source. Re-verifies every gate, then makes exactly one call
    to ``AssessmentWorkspaceService.generate_package(...)``, records what was
    produced, and stops.

Separating workspace creation from the generation mutation is deliberate: the
copy is a reversible filesystem operation, the generation is not.

No expected-outcome gating
----------------------------
This operator never asserts a completeness classification, an intervention
type, a roadmap shape or any package narrative. Gating on an expected outcome
would convert a finding into a requirement. Every gate here is an *integrity*
gate: identity, hashes, provenance, immutability, absence of unexpected
artefacts, and the invariants that must hold whatever the package layer
produces -- UNKNOWN stays UNKNOWN, no HUMAN_SUPPLIED value appears, no evidence
is minted. Package content is recorded verbatim, after the fact.

Why package a copy rather than the frozen Stage 4 database
-------------------------------------------------------------
``production-run-v0.4-assessed/workspace.db`` is frozen in git at the
assessment checkpoint and its SHA-256 is quoted in two committed records.
Packaging it in place would leave those records describing a file that no
longer has the stated hash, and would destroy "assessed, never packaged" as an
inspectable historical state. Nothing in the product prevents packaging a copy:
``build_workspace_service`` accepts any database path, all identifiers travel
with a byte copy, and ``generate_package()`` requires only an active successful
assessment artefact.

What ``generate_package()`` actually does
--------------------------------------------
``AssessmentWorkspaceService.generate_package`` reads the active
``INTEGRATED_ASSESSMENT_RESULT`` and nothing else -- not the
``APPROVED_REVIEW``, not the ``REVIEW_SESSION``, not the candidate, not the
policy file. It requires that artefact's payload to be an
``IntegratedAssessmentSuccess``; a persisted assessment *failure* fails the same
guard.

It is **operation-tracked**: it opens a ``GENERATE_PACKAGE`` operation keyed by
``sha256(integrated.artifact_id)``, and if that operation is already
``COMPLETED`` it returns the previously produced artefact without regenerating
anything. On success it persists one new ``DECISION_PACKAGE_RESULT`` whose
parent is the assessment artefact, advancing ``assessments.current_stage`` to
``package-ready``. A failure result is still persisted, but the stage stays
``assessed``.

Nothing cascades: ``DECISION_PACKAGE_RESULT`` is the terminal artefact type.

Failure semantics -- no automatic resume, ever
-------------------------------------------------
Read this before re-running anything.

*If Stage 5 copy creation fails midway*: inspect
``production-run-v0.5-packaged/`` by hand. Do not re-run this operator against
it -- ``--confirm-init-stage5-workspace`` refuses an existing directory, and
that refusal is intended. Decide explicitly whether to discard the directory and
re-create it from the frozen Stage 4 copy, or to re-plan.

*If ``--confirm-generate-package`` fails before the ``generate_package()``
call*: nothing was generated and nothing was persisted by this operator. The
pristine-copy gate refuses to proceed against a Stage 5 database whose hash has
drifted.

*If ``generate_package()`` succeeds but post-generation verification or record
writing fails*: **the package is already persisted.** Do not re-run blindly.
Because the call is operation-tracked, a re-run against the same assessment
artefact returns the stored package rather than regenerating -- but that must
still be a deliberate, recorded decision, never an automatic retry. Inspect the
Stage 5 database **read-only**, establish exactly what exists, and recover the
documentation separately. Do not hand-repair the database and do not call
``reset_to_review``.

Case-data boundary
-------------------
Readable: the frozen BEFORE corpus, the fourteen frozen Stage 1 to Stage 4
artefacts, the PORT-004 run manifest, this script, and -- in the persistent
modes -- the Stage 5 working directory. Every one of those is hash-verified.
``sqlite3.connect`` is permitted only for the frozen Stage 4 database in
``--dry-run`` (read-only URI) and only inside the Stage 5 directory in the
persistent modes; the frozen Stage 1 to Stage 4 databases are otherwise verified
as raw bytes and never opened as databases. PORT-001/002/003 material, sealed
AFTER packets, the case register, provenance manifests, leakage audits, source
captures and OCR-derived material are all unreachable. Enforced by an explicit
allowlist and a ``sys.addaudithook`` guard.

Usage
-----
All three commands, in order. Both persistent modes require this file to be
committed and byte-identical to HEAD::

    .venv/bin/python evaluation/portfolio/_run_port004_stage5_package.py --dry-run
    .venv/bin/python evaluation/portfolio/_run_port004_stage5_package.py --confirm-init-stage5-workspace
    .venv/bin/python evaluation/portfolio/_run_port004_stage5_package.py --confirm-generate-package

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
OPERATOR_RELATIVE_PATH = "evaluation/portfolio/_run_port004_stage5_package.py"

CASE_RUN_DIR = PORTFOLIO / "runs" / "port-004"
STAGE1_RUN_DIR = CASE_RUN_DIR / "production-run-v0.1"
STAGE2_RUN_DIR = CASE_RUN_DIR / "production-run-v0.2-review"
STAGE3_RUN_DIR = CASE_RUN_DIR / "production-run-v0.3-approved"
STAGE4_RUN_DIR = CASE_RUN_DIR / "production-run-v0.4-assessed"
STAGE5_RUN_DIR = CASE_RUN_DIR / "production-run-v0.5-packaged"

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
STAGE4_OBSERVATION_RECORD_PATH = CASE_RUN_DIR / "stage4-observation-record.v0.1.md"

STAGE5_DATABASE_PATH = STAGE5_RUN_DIR / "workspace.db"
STAGE5_PACKAGE_RECORD_PATH = STAGE5_RUN_DIR / "stage5-package-record.v0.1.json"

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
EXPECTED_STAGE4_DATABASE_SHA256 = (
    "9c144be8b2ca2d8fa3f0cf88a6d4ea4e344371afc13fc856a4a52bc94148cce3"
)
EXPECTED_STAGE4_ASSESSMENT_RECORD_SHA256 = (
    "42f399ac5bc0c8f86ff9dcda58b9c5c2cd5af2240a284606eedd94e6cd4df32e"
)
EXPECTED_STAGE4_OBSERVATION_RECORD_SHA256 = (
    "996889149324d0ecd45659706142785815cb0c0cd77e014102211e1b5330d375"
)
EXPECTED_RUN_MANIFEST_SHA256 = (
    "fb9aa99f2b5c8f1a12729b839b4f2ad1a5fc6e1aba5c158127e6907e1945fd37"
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
    ("stage4 workspace.db", STAGE4_DATABASE_PATH, EXPECTED_STAGE4_DATABASE_SHA256),
    (
        "stage4-assessment-record.v0.1.json",
        STAGE4_ASSESSMENT_RECORD_PATH,
        EXPECTED_STAGE4_ASSESSMENT_RECORD_SHA256,
    ),
    (
        "stage4-observation-record.v0.1.md",
        STAGE4_OBSERVATION_RECORD_PATH,
        EXPECTED_STAGE4_OBSERVATION_RECORD_SHA256,
    ),
)

# ---- Pinned identity, from the frozen Stage 4 assessment freeze -----------

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
EXPECTED_ASSESSMENT_ARTIFACT_ID = "artifact-61ee88e2be40437598864e7f634b2243"
EXPECTED_ASSESSMENT_PAYLOAD_SHA256 = (
    "eedf5c3a70b0144987d1d7af5fc4ccbdafd5895f0baddd6555b398724700820b"
)
EXPECTED_ASSESSMENT_RUN_ID = "assessment-485eee54ece54f46aba333b6e72e4307"
EXPECTED_DECISION_POLICY_FINGERPRINT = (
    "b72e528b102bf893b45e6de9ec311e0888341d12b8aa3f99b8047e324d6a6d66"
)
EXPECTED_POLICY_ID = "decision_policy.v0.2"
EXPECTED_POLICY_VERSION = "0.2.0"

EXPECTED_STEP_IDS: tuple[str, ...] = (
    "candidate-step-8761540c3fb724d5",
    "candidate-step-df4f0ee1970efb51",
    "candidate-step-55d273f0f007cf1f",
    "candidate-step-56dffd383d81b62b",
    "candidate-step-77a07b30101d76fe",
    "candidate-step-2d9417a14cf0f937",
    "candidate-step-69b86f080884cb5a",
    "candidate-step-a154c8ee145a50f9",
)

EXPECTED_STEP_COUNT = 8
EXPECTED_CRITERIA_UNKNOWN = 80
EXPECTED_ACCOUNTABILITY_UNKNOWN = 8

STOP_BOUNDARY_NOTE = (
    "The deterministic decision package is persisted. This is the terminal "
    "product stage: no implementation, deployment or rollout artefact was "
    "produced, and no AFTER evidence was generated or accessed. The frozen "
    "Stage 1 to Stage 4 artefacts remain immutable, and the "
    "INTEGRATED_ASSESSMENT_RESULT, APPROVED_REVIEW and REVIEW_SESSION artefacts "
    "are unchanged."
)


class CaseDataBoundaryError(RuntimeError):
    """A forbidden portfolio file was opened during Stage 5."""


class PackageBoundaryError(RuntimeError):
    """A forbidden operation outside the packaging boundary was attempted."""


class Stage5GateError(RuntimeError):
    """A Stage 5 precondition failed."""


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

    if mode not in {"dry-run", "stage5"}:  # pragma: no cover - programmer error
        raise ValueError(f"unknown case-data guard mode: {mode!r}")

    portfolio_root = os.path.realpath(PORTFOLIO)
    stage5_root = os.path.realpath(STAGE5_RUN_DIR)
    stage4_database = os.path.realpath(STAGE4_DATABASE_PATH)

    allowed_files = {
        os.path.realpath(BEFORE_PATH),
        os.path.realpath(SCRIPT_PATH),
        os.path.realpath(RUN_MANIFEST_PATH),
    }
    allowed_files |= {os.path.realpath(p) for _n, p, _d in FROZEN_ARTEFACTS}

    def _inside_stage5(resolved: str) -> bool:
        return resolved == stage5_root or resolved.startswith(stage5_root + os.sep)

    def hook(event: str, args: tuple[Any, ...]) -> None:
        if event not in {"open", "os.open", "sqlite3.connect"}:
            return
        if event == "sqlite3.connect":
            resolved = _sqlite_target_path(args[0] if args else None)
            if resolved is None:
                raise CaseDataBoundaryError(
                    f"{CASE_ID} Stage 5 guard refused a sqlite3.connect call with an "
                    "unresolvable target."
                )
            if mode == "dry-run":
                if resolved == stage4_database:
                    return
                raise CaseDataBoundaryError(
                    f"{CASE_ID} Stage 5 dry-run refused sqlite3.connect({resolved}). "
                    "Only the frozen Stage 4 database may be opened, and only through "
                    "a read-only URI."
                )
            if _inside_stage5(resolved):
                return
            raise CaseDataBoundaryError(
                f"{CASE_ID} Stage 5 guard refused sqlite3.connect({resolved}). "
                "Only the Stage 5 working database may be opened as a database. The "
                "frozen Stage 1 to Stage 4 databases are verified by hash only."
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
        if mode == "stage5" and _inside_stage5(resolved):
            return
        raise CaseDataBoundaryError(
            f"{CASE_ID} Stage 5 case-data guard refused to open {resolved}. "
            "Only the frozen BEFORE corpus, the frozen Stage 1 to Stage 4 artefacts, "
            "the run manifest, this script and -- in the persistent modes -- the "
            "Stage 5 working directory are permitted."
        )

    sys.addaudithook(hook)


# --------------------------------------------------------------------------
# Package boundary guard
# --------------------------------------------------------------------------


def install_package_boundary_guard(service_class: Any) -> None:
    """Make approve / assess / reset_to_review raise, in this process only.

    ``generate_package`` is deliberately left intact: it is this operator's one
    authorised mutation. Nothing inside ``DecisionSupportPackageService`` or its
    builders is patched -- the package layer must run exactly as production runs
    it.
    """

    def _blocked(name: str):
        def _raise(*_args: Any, **_kwargs: Any):
            raise PackageBoundaryError(
                f"{CASE_ID} Stage 5 refused AssessmentWorkspaceService.{name}(). "
                "This operator stops at the persisted decision package."
            )

        return _raise

    for name in ("approve", "assess", "reset_to_review"):
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
            "Persistent Stage 5 modes require the reviewed operator to be committed "
            "first, so every Stage 5 artefact is attributable to an exact commit."
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


# --------------------------------------------------------------------------
# Operator-owned readiness checks
#
# These mirror the semantics the production package layer applies, but they are
# this operator's own code: no private production symbol is imported. The
# authoritative input-contract validation still runs inside
# DecisionSupportPackageService during generate_package(); these checks exist so
# that a divergence is caught and reported *before* the mutation rather than as
# a persisted failure artefact afterwards.
#
# Nothing here computes, classifies or displays package content.
# --------------------------------------------------------------------------


def verify_assessment_artifact(integrated: Any, candidate_bytes: bytes) -> None:
    """Every packaging precondition on the assessment artefact.

    Integrity only: identity, lineage, structural completeness, and the
    invariants that must hold whatever the package layer produces. Raises
    :class:`Stage5GateError` on any divergence.
    """

    from ai_adoption_engine.models.enums import GateName

    metadata = integrated.metadata
    print(f"  assessment_run_id                        {metadata.assessment_run_id}")
    if metadata.assessment_run_id != EXPECTED_ASSESSMENT_RUN_ID:
        raise Stage5GateError(
            f"assessment_run_id is {metadata.assessment_run_id!r}"
        )

    policy = integrated.policy
    print(f"  policy_id                                {policy.policy_id}")
    print(f"  policy_version                           {policy.policy_version}")
    print(f"  decision_policy_fingerprint              {policy.decision_policy_fingerprint}")
    if policy.policy_id != EXPECTED_POLICY_ID:
        raise Stage5GateError(f"policy_id is {policy.policy_id!r}")
    if policy.policy_version != EXPECTED_POLICY_VERSION:
        raise Stage5GateError(f"policy_version is {policy.policy_version!r}")
    if policy.decision_policy_fingerprint != EXPECTED_DECISION_POLICY_FINGERPRINT:
        raise Stage5GateError("decision_policy_fingerprint differs from the frozen value")

    assessment = integrated.process_assessment
    lineage = integrated.lineage
    print(f"  review_id (lineage)                      {lineage.review_id}")
    if lineage.review_id != EXPECTED_REVIEW_ID:
        raise Stage5GateError(f"lineage review_id is {lineage.review_id!r}")
    if assessment.process_id != lineage.validated_process_id:
        raise Stage5GateError(
            "assessed process_id does not match the Phase 5 lineage process id"
        )

    step_assessments = assessment.step_assessments
    traces = integrated.step_traceability
    step_ids = [item.step_id for item in step_assessments]
    print(f"  step assessments                         {len(step_assessments)}")
    print(f"  traceability records                     {len(traces)}")
    if len(step_assessments) != EXPECTED_STEP_COUNT:
        raise Stage5GateError(f"{len(step_assessments)} step assessments")
    if tuple(step_ids) != EXPECTED_STEP_IDS:
        raise Stage5GateError("step ids or their order differ from the frozen set")
    if len(traces) != len(step_assessments):
        raise Stage5GateError(
            "every assessed step requires exactly one traceability record"
        )
    print("  step ids and order                       exact OK")

    gate_names = set(GateName)
    criteria_unknown = 0
    accountability_unknown = 0
    for step_assessment, trace in zip(step_assessments, traces, strict=True):
        where = step_assessment.step_id
        if trace.step_id != where:
            raise Stage5GateError(f"{where}: traceability step id does not match")

        gates = [item.gate for item in step_assessment.gate_results]
        if len(gates) != len(set(gates)) or set(gates) != gate_names:
            raise Stage5GateError(
                f"{where}: each assessed step must retain every gate exactly once"
            )

        if len(step_assessment.criteria) != len(trace.criteria):
            raise Stage5GateError(
                f"{where}: every assessed criterion requires a reviewed-value trace"
            )
        for criterion, value_trace in zip(
            step_assessment.criteria, trace.criteria, strict=True
        ):
            if criterion.knowledge_state is not value_trace.knowledge_state:
                raise Stage5GateError(
                    f"{where}: criterion knowledge state does not match its trace"
                )
            if set(criterion.evidence_ids) != {
                item.evidence_id for item in value_trace.evidence
            }:
                raise Stage5GateError(
                    f"{where}: criterion evidence does not match its trace"
                )
            if criterion.value is None and criterion.knowledge_state.value == "unknown":
                criteria_unknown += 1

        accountability = step_assessment.human_accountability
        if (
            accountability.knowledge_state
            is not trace.human_accountability.knowledge_state
            or set(accountability.evidence_ids)
            != {item.evidence_id for item in trace.human_accountability.evidence}
        ):
            raise Stage5GateError(
                f"{where}: accountability evidence or knowledge state does not match "
                "its trace"
            )
        if (
            accountability.value is None
            and accountability.knowledge_state.value == "unknown"
        ):
            accountability_unknown += 1

    print("  gate completeness per step               every gate exactly once OK")
    print("  criterion/trace consistency              OK")
    print(f"  criteria UNKNOWN                         {criteria_unknown}")
    print(f"  accountability UNKNOWN                   {accountability_unknown}")
    if criteria_unknown != EXPECTED_CRITERIA_UNKNOWN:
        raise Stage5GateError(f"criteria UNKNOWN = {criteria_unknown}")
    if accountability_unknown != EXPECTED_ACCOUNTABILITY_UNKNOWN:
        raise Stage5GateError(f"accountability UNKNOWN = {accountability_unknown}")

    dumped = integrated.model_dump(mode="json")
    human_supplied = _count_human_supplied(dumped)
    frozen_ids = set(_iter_evidence_ids(json.loads(candidate_bytes)))
    minted = sorted(set(_iter_evidence_ids(dumped)) - frozen_ids)
    print(f"  HUMAN_SUPPLIED assertions                {human_supplied}")
    print(f"  evidence outside the frozen candidate    {len(minted)}")
    if human_supplied != 0:
        raise Stage5GateError(f"HUMAN_SUPPLIED assertions = {human_supplied}")
    if minted:
        raise Stage5GateError(f"evidence not present in the frozen candidate: {minted}")


# --------------------------------------------------------------------------
# Mode: --dry-run
# --------------------------------------------------------------------------


def dry_run(candidate_bytes: bytes) -> None:
    """Read-only readiness verification. Generates nothing, predicts nothing."""

    import sqlite3

    from ai_adoption_engine.models.integrated_assessment import (
        IntegratedAssessmentSuccess,
    )

    _print_header("DRY RUN — frozen Stage 4 assessed workspace, read-only")
    print(f"  Stage 5 directory exists                 {STAGE5_RUN_DIR.exists()} (expected False here)")
    print("  This mode never calls AssessmentWorkspaceService.generate_package,")
    print("  never touches DecisionSupportPackageService, and never calculates or")
    print("  displays any predicted package outcome.")

    uri = f"file:{STAGE4_DATABASE_PATH}?mode=ro"
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
        if stage != "assessed":
            raise _fail(f"workflow stage is {stage!r}, expected 'assessed'")

        present = sorted(
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT artifact_type FROM assessment_artifacts"
            )
        )
        print(f"  artefact types present                   {present}")
        if "DECISION_PACKAGE_RESULT" in present:
            raise _fail("a DECISION_PACKAGE_RESULT already exists in the frozen Stage 4 database")
        for required in ("INTEGRATED_ASSESSMENT_RESULT", "APPROVED_REVIEW", "REVIEW_SESSION"):
            if required not in present:
                raise _fail(f"the frozen Stage 4 database holds no {required}")

        operations = sorted(
            {
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT operation_kind FROM assessment_operations"
                )
            }
        )
        print(f"  recorded operations                      {operations}")
        if "generate-package" in operations:
            raise _fail(f"a generate-package operation already exists: {operations}")

        rows = {}
        for artifact_type in (
            "INTEGRATED_ASSESSMENT_RESULT",
            "APPROVED_REVIEW",
            "REVIEW_SESSION",
        ):
            rows[artifact_type] = connection.execute(
                """SELECT a.artifact_id, a.artifact_revision, a.parent_artifact_id,
                          a.payload_json, a.payload_sha256
                   FROM assessment_artifacts a
                   JOIN active_artifacts v ON v.artifact_id = a.artifact_id
                   WHERE v.artifact_type = ?""",
                (artifact_type,),
            ).fetchone()
    finally:
        connection.close()

    integrated_row = rows["INTEGRATED_ASSESSMENT_RESULT"]
    approved_row = rows["APPROVED_REVIEW"]
    review_row = rows["REVIEW_SESSION"]
    if integrated_row is None or approved_row is None or review_row is None:
        raise _fail("the frozen Stage 4 database is missing an expected active artefact")

    print(f"\n  assessment artefact id                   {integrated_row['artifact_id']}")
    print(f"  assessment payload sha256                {integrated_row['payload_sha256']}")
    print(f"  assessment revision                      {integrated_row['artifact_revision']}")
    print(f"  assessment parent                        {integrated_row['parent_artifact_id']}")
    if integrated_row["artifact_id"] != EXPECTED_ASSESSMENT_ARTIFACT_ID:
        raise _fail("unexpected INTEGRATED_ASSESSMENT_RESULT artefact id")
    if integrated_row["payload_sha256"] != EXPECTED_ASSESSMENT_PAYLOAD_SHA256:
        raise _fail("INTEGRATED_ASSESSMENT_RESULT payload hash mismatch")
    if integrated_row["artifact_revision"] != 1:
        raise _fail("INTEGRATED_ASSESSMENT_RESULT revision is not 1")
    if integrated_row["parent_artifact_id"] != EXPECTED_APPROVED_ARTIFACT_ID:
        raise _fail("the assessment artefact's parent is not the frozen APPROVED_REVIEW")

    print(f"  APPROVED_REVIEW artefact id              {approved_row['artifact_id']}")
    print(f"  APPROVED_REVIEW payload sha256           {approved_row['payload_sha256']}")
    if approved_row["artifact_id"] != EXPECTED_APPROVED_ARTIFACT_ID:
        raise _fail("unexpected APPROVED_REVIEW artefact id")
    if approved_row["payload_sha256"] != EXPECTED_APPROVED_PAYLOAD_SHA256:
        raise _fail("APPROVED_REVIEW payload hash mismatch")

    print(f"  REVIEW_SESSION artefact id               {review_row['artifact_id']}")
    print(f"  REVIEW_SESSION payload sha256            {review_row['payload_sha256']}")
    if review_row["artifact_id"] != EXPECTED_REVIEW_ARTIFACT_ID:
        raise _fail("unexpected REVIEW_SESSION artefact id")
    if review_row["payload_sha256"] != EXPECTED_REVIEW_PAYLOAD_SHA256:
        raise _fail("REVIEW_SESSION payload hash mismatch")

    integrated = IntegratedAssessmentSuccess.model_validate(
        json.loads(integrated_row["payload_json"])
    )

    _print_header("DRY RUN — packaging readiness (integrity only, no package content)")
    try:
        verify_assessment_artifact(integrated, candidate_bytes)
    except Stage5GateError as failure:
        raise _fail(str(failure)) from failure

    _print_header("CONFIRMATIONS")
    print(f"  Stage 5 directory NOT created            {not STAGE5_RUN_DIR.exists()}")
    print("  No package of any kind was generated.")
    print("  No completeness, future state, roadmap, governance text or package id")
    print("  was computed or reported.")
    print("  No write connection was opened; Stage 4 was read via mode=ro.")
    print("\n--- DRY RUN COMPLETE — NOTHING WAS WRITTEN, NOTHING WAS GENERATED ---")


# --------------------------------------------------------------------------
# Mode: --confirm-init-stage5-workspace
# --------------------------------------------------------------------------


def init_stage5_workspace() -> None:
    """Create the Stage 5 working copy. Package generation is NOT run here."""

    _print_header("STAGE 5 WORKSPACE CREATION")

    if STAGE5_RUN_DIR.exists():
        raise _fail(
            f"the Stage 5 directory already exists: {STAGE5_RUN_DIR.relative_to(ROOT)}\n"
            "This operator does not overwrite it and implements no resume semantics. "
            "Inspect the existing directory and decide explicitly what to do with it."
        )

    print(f"  source (frozen, read-only)               {STAGE4_DATABASE_PATH.relative_to(ROOT)}")
    print(f"  destination                              {STAGE5_DATABASE_PATH.relative_to(ROOT)}")

    STAGE5_RUN_DIR.mkdir(parents=True, exist_ok=False)
    # copyfile opens the source 'rb'. The frozen Stage 4 database is never opened
    # for writing, and never opened as a database.
    shutil.copyfile(STAGE4_DATABASE_PATH, STAGE5_DATABASE_PATH)

    post_copy = _sha256_file(STAGE4_DATABASE_PATH)
    print(f"  frozen Stage 4 db re-hash                {post_copy}")
    if post_copy != EXPECTED_STAGE4_DATABASE_SHA256:
        raise _fail(
            "the frozen Stage 4 database changed during the copy.\n"
            f"  expected {EXPECTED_STAGE4_DATABASE_SHA256}\n"
            f"  actual   {post_copy}"
        )
    print("  frozen Stage 4 unchanged                 MATCH")

    stage5_digest = _sha256_file(STAGE5_DATABASE_PATH)
    print(f"  Stage 5 copy sha256                      {stage5_digest}")
    if stage5_digest != EXPECTED_STAGE4_DATABASE_SHA256:
        raise _fail("the Stage 5 copy does not match the frozen source byte for byte.")
    print("  byte-identical to source                 MATCH")
    print(f"  package record written                   {STAGE5_PACKAGE_RECORD_PATH.exists()} (expected False)")

    print("\n" + "=" * 78)
    print("STAGE 5 WORKSPACE CREATED — PACKAGE NOT GENERATED.")
    print("=" * 78)
    print("Next, only when authorised: --confirm-generate-package")


# --------------------------------------------------------------------------
# Mode: --confirm-generate-package
# --------------------------------------------------------------------------


def generate_stage5_package(candidate_bytes: bytes, identity: dict[str, Any]) -> None:
    """Verify everything, then make exactly one generate_package call, then stop."""

    from ai_adoption_engine.models.decision_support import (
        DecisionPackageFailure,
        DecisionPackageSuccess,
    )
    from ai_adoption_engine.models.integrated_assessment import (
        IntegratedAssessmentSuccess,
    )
    from ai_adoption_engine.workspace.composition import build_workspace_service
    from ai_adoption_engine.workspace.models import ArtifactType
    from ai_adoption_engine.workspace.service import AssessmentWorkspaceService

    _print_header("STAGE 5 PRISTINE-COPY GATE")
    if not STAGE5_DATABASE_PATH.is_file():
        raise _fail(
            f"the Stage 5 database is missing: {STAGE5_DATABASE_PATH.relative_to(ROOT)}\n"
            "Run --confirm-init-stage5-workspace first."
        )
    stage5_digest = _sha256_file(STAGE5_DATABASE_PATH)
    print(f"  Stage 5 workspace.db sha256              {stage5_digest}")
    if stage5_digest != EXPECTED_STAGE4_DATABASE_SHA256:
        raise _fail(
            "the Stage 5 copy is not pristine.\n"
            f"  expected {EXPECTED_STAGE4_DATABASE_SHA256}\n"
            f"  actual   {stage5_digest}\n"
            "This operator implements no resume semantics. Inspect the Stage 5 "
            "directory read-only and decide explicitly what to do with it."
        )
    print("  pristine copy                            MATCH")
    if STAGE5_PACKAGE_RECORD_PATH.exists():
        raise _fail(
            "a Stage 5 package record already exists; refusing to generate again."
        )

    install_package_boundary_guard(AssessmentWorkspaceService)
    print("  package boundary guard                   INSTALLED "
          "(approve / assess / reset_to_review now raise)")

    service = build_workspace_service(STAGE5_DATABASE_PATH)
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
    if stage != "assessed":
        raise _fail(f"workflow stage is {stage!r}, expected 'assessed'")

    _print_header("PRE-GENERATION VERIFICATION — on the Stage 5 copy, before any mutation")
    active = workspace.active_artifacts
    if ArtifactType.DECISION_PACKAGE_RESULT in active:
        raise _fail("a DECISION_PACKAGE_RESULT already exists")
    integrated_stored = active.get(ArtifactType.INTEGRATED_ASSESSMENT_RESULT)
    approved_stored = active.get(ArtifactType.APPROVED_REVIEW)
    review_stored = active.get(ArtifactType.REVIEW_SESSION)
    if integrated_stored is None or approved_stored is None or review_stored is None:
        raise _fail("the Stage 5 copy is missing an expected active artefact")

    print(f"  assessment artefact id                   {integrated_stored.artifact_id}")
    print(f"  assessment payload sha256                {integrated_stored.payload_sha256}")
    if integrated_stored.artifact_id != EXPECTED_ASSESSMENT_ARTIFACT_ID:
        raise _fail("unexpected INTEGRATED_ASSESSMENT_RESULT artefact id")
    if integrated_stored.payload_sha256 != EXPECTED_ASSESSMENT_PAYLOAD_SHA256:
        raise _fail("INTEGRATED_ASSESSMENT_RESULT payload hash mismatch")
    if integrated_stored.artifact_revision != 1:
        raise _fail("INTEGRATED_ASSESSMENT_RESULT revision is not 1")
    if integrated_stored.parent_artifact_id != EXPECTED_APPROVED_ARTIFACT_ID:
        raise _fail("the assessment artefact's parent is not the frozen APPROVED_REVIEW")
    if approved_stored.payload_sha256 != EXPECTED_APPROVED_PAYLOAD_SHA256:
        raise _fail("APPROVED_REVIEW payload hash mismatch")
    if review_stored.payload_sha256 != EXPECTED_REVIEW_PAYLOAD_SHA256:
        raise _fail("REVIEW_SESSION payload hash mismatch")
    if review_stored.payload.status.value != "in-review":
        raise _fail("the standalone REVIEW_SESSION is not in-review")
    print("  upstream artefacts unchanged             OK")

    integrated_payload = integrated_stored.payload
    if not isinstance(integrated_payload, IntegratedAssessmentSuccess):
        raise _fail(
            "the active INTEGRATED_ASSESSMENT_RESULT is not an "
            f"IntegratedAssessmentSuccess (got {type(integrated_payload).__name__}). "
            "The product would refuse packaging; nothing was attempted."
        )
    try:
        verify_assessment_artifact(integrated_payload, candidate_bytes)
    except Stage5GateError as failure:
        raise _fail(
            f"{failure}\n"
            "STOP before generation. AssessmentWorkspaceService.generate_package() was "
            "NOT called and nothing was persisted by this operator."
        ) from failure

    print("\n  ALL PRE-GENERATION CHECKS PASSED — the single generation call follows.")

    # ---- The one authorised persistent mutation --------------------------
    _print_header("GENERATION — one call to AssessmentWorkspaceService.generate_package()")
    result = service.generate_package(assessment_id)
    is_success = isinstance(result, DecisionPackageSuccess)
    is_failure = isinstance(result, DecisionPackageFailure)
    print(f"  result type                              {type(result).__name__}")
    print(f"  DecisionPackageSuccess                   {is_success}")
    if is_failure:
        for error in result.errors:
            print(f"    error code={error.code.value} field_path={error.field_path} "
                  f"step_id={error.step_id}")
            print(f"      {error.message}")
        raise _fail(
            "the decision package returned a failure result. It has been persisted by "
            "the product as the packaging outcome; the workflow stage remains "
            "'assessed'. Do not re-run this operator: generate_package() is "
            "operation-tracked and a re-run would return the stored artefact rather "
            "than regenerating. Inspect the Stage 5 database read-only and re-plan."
        )
    if not is_success:
        raise _fail(f"unexpected package result type {type(result).__name__}")

    _post_generation(
        service=service,
        assessment_id=assessment_id,
        result=result,
        identity=identity,
        candidate_bytes=candidate_bytes,
        integrated_stored=integrated_stored,
        approved_stored=approved_stored,
        review_stored=review_stored,
        artifact_type_cls=ArtifactType,
    )


def _post_generation(
    *,
    service: Any,
    assessment_id: str,
    result: Any,
    identity: dict[str, Any],
    candidate_bytes: bytes,
    integrated_stored: Any,
    approved_stored: Any,
    review_stored: Any,
    artifact_type_cls: Any,
) -> None:
    """Verify integrity, record what was produced, then stop.

    If anything here fails, the package is ALREADY PERSISTED. Do not re-run.
    See the failure-semantics section of the module docstring.
    """

    import sqlite3

    _print_header("POST-GENERATION VERIFICATION — integrity only")
    workspace = service.repository.load_workspace(assessment_id)
    stored = workspace.active_artifacts.get(artifact_type_cls.DECISION_PACKAGE_RESULT)
    if stored is None:
        raise _fail(
            "no active DECISION_PACKAGE_RESULT after a successful generation call. "
            "The package may be partially persisted; inspect read-only and re-plan."
        )
    print(f"  package artefact id                      {stored.artifact_id}")
    print(f"  package payload sha256                   {stored.payload_sha256}")
    print(f"  revision                                 {stored.artifact_revision}")
    print(f"  parent artefact id                       {stored.parent_artifact_id}")
    if stored.artifact_revision != 1:
        raise _fail(f"package artefact revision is {stored.artifact_revision}")
    if stored.parent_artifact_id != integrated_stored.artifact_id:
        raise _fail(
            f"package parent is {stored.parent_artifact_id!r}, expected "
            f"{integrated_stored.artifact_id!r}"
        )

    stage = workspace.assessment.current_stage.value
    print(f"  workflow stage                           {stage}")
    if stage != "package-ready":
        raise _fail(f"workflow stage is {stage!r}, expected 'package-ready'")

    integrated_after = workspace.active_artifacts.get(
        artifact_type_cls.INTEGRATED_ASSESSMENT_RESULT
    )
    approved_after = workspace.active_artifacts.get(artifact_type_cls.APPROVED_REVIEW)
    review_after = workspace.active_artifacts.get(artifact_type_cls.REVIEW_SESSION)
    if integrated_after is None or approved_after is None or review_after is None:
        raise _fail("an upstream artefact is no longer active after generation")
    if integrated_after.payload_sha256 != integrated_stored.payload_sha256:
        raise _fail("the INTEGRATED_ASSESSMENT_RESULT payload changed during generation")
    if approved_after.payload_sha256 != approved_stored.payload_sha256:
        raise _fail("the APPROVED_REVIEW payload changed during generation")
    if review_after.payload_sha256 != review_stored.payload_sha256:
        raise _fail("the REVIEW_SESSION payload changed during generation")
    if review_after.payload.status.value != "in-review":
        raise _fail("the standalone REVIEW_SESSION status changed during generation")
    print("  INTEGRATED_ASSESSMENT_RESULT unchanged   OK")
    print("  APPROVED_REVIEW unchanged                OK")
    print("  REVIEW_SESSION unchanged and in-review   OK")

    connection = sqlite3.connect(f"file:{STAGE5_DATABASE_PATH}?mode=ro", uri=True)
    try:
        operations = sorted(
            {
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT operation_kind FROM assessment_operations"
                )
            }
        )
        package_status = sorted(
            {
                row[0]
                for row in connection.execute(
                    "SELECT status FROM assessment_operations "
                    "WHERE operation_kind = 'generate-package'"
                )
            }
        )
    finally:
        connection.close()
    print(f"  recorded operations                      {operations}")
    print(f"  generate-package operation status        {package_status}")
    if package_status != ["completed"]:
        raise _fail(
            f"generate-package operation status is {package_status}, expected ['completed']"
        )

    package = result.package
    ordered_ids = list(package.current_state.ordered_step_ids)
    portfolio_ids = [item.step_id for item in package.portfolio.items]
    print(f"  ordered step ids                         {len(ordered_ids)}")
    if tuple(ordered_ids) != EXPECTED_STEP_IDS:
        raise _fail("the package's ordered step ids differ from the frozen set")
    if tuple(portfolio_ids) != EXPECTED_STEP_IDS:
        raise _fail("the package portfolio's step ids differ from the frozen set")
    print("  step ids and order                       exact OK")
    if package.current_state.review_id != EXPECTED_REVIEW_ID:
        raise _fail("the package's current-state review id differs")
    if package.source.integrated_assessment_run_id != EXPECTED_ASSESSMENT_RUN_ID:
        raise _fail("the package's source assessment run id differs")
    if package.source.policy.decision_policy_fingerprint != (
        EXPECTED_DECISION_POLICY_FINGERPRINT
    ):
        raise _fail("the package's policy fingerprint differs")

    package_dump = result.model_dump(mode="json")
    human_supplied = _count_human_supplied(package_dump)
    frozen_ids = set(_iter_evidence_ids(json.loads(candidate_bytes)))
    minted = sorted(set(_iter_evidence_ids(package_dump)) - frozen_ids)
    print(f"  HUMAN_SUPPLIED assertions                {human_supplied}")
    print(f"  evidence outside the frozen candidate    {len(minted)}")
    if human_supplied != 0:
        raise _fail(f"HUMAN_SUPPLIED assertions = {human_supplied}")
    if minted:
        raise _fail(f"package referenced evidence outside the frozen candidate: {minted}")

    # ---- Package content, recorded as observed and never gated on --------
    _print_header("PACKAGE OUTPUT — recorded as observed, not compared to any expectation")
    print(f"  package_id                               {package.package_id}")
    print(f"  package_schema_version                   {package.package_schema_version}")
    print(f"  completeness                             {package.completeness.value}")
    print(f"  portfolio items                          {len(package.portfolio.items)}")
    print(f"  future-state steps                       {len(package.future_state.steps)}")
    print(f"  missing-information entries              {len(package.missing_information)}")
    print(f"  evidence appendix references             {len(package.evidence_appendix)}")
    print(f"  roi_statement                            {package.roi_statement}")
    observed_items = []
    for item in package.portfolio.items:
        entry = {
            "sequence": item.sequence,
            "step_id": item.step_id,
            "recommendation_mode": item.recommendation_mode.value,
            "priority": item.priority,
            "priority_status": item.priority_status.value,
            "capabilities": [value.value for value in item.capabilities],
            "missing_information_count": len(item.missing_information),
        }
        observed_items.append(entry)
        print(
            f"    {entry['step_id']}  mode={entry['recommendation_mode']}  "
            f"priority_status={entry['priority_status']}  "
            f"gaps={entry['missing_information_count']}"
        )

    _print_header("FROZEN SOURCES — post-generation re-hash")
    frozen_digests = verify_frozen_artefacts("post-generation")
    before_digest = _sha256_file(BEFORE_PATH)
    print(f"  BEFORE corpus                            {before_digest}")
    if before_digest != EXPECTED_BEFORE_SHA256:
        raise _fail("the BEFORE corpus changed during generation")
    manifest_digest = _sha256_file(RUN_MANIFEST_PATH)
    print(f"  run manifest                             {manifest_digest}")
    if manifest_digest != EXPECTED_RUN_MANIFEST_SHA256:
        raise _fail("the run manifest changed during generation")
    stage5_digest = _sha256_file(STAGE5_DATABASE_PATH)
    print(f"  Stage 5 workspace.db (final)             {stage5_digest}")

    record = {
        "case_id": CASE_ID,
        "stage": "stage-5-phase-6-decision-package",
        "execution_identity": identity,
        "production_fingerprint": EXPECTED_FINGERPRINT,
        "source_stage4_database_sha256": EXPECTED_STAGE4_DATABASE_SHA256,
        "source_stage4_assessment_record_sha256": (
            EXPECTED_STAGE4_ASSESSMENT_RECORD_SHA256
        ),
        "source_stage4_observation_record_sha256": (
            EXPECTED_STAGE4_OBSERVATION_RECORD_SHA256
        ),
        "run_manifest_sha256_at_generation": manifest_digest,
        "assessment_id": assessment_id,
        "review_id": EXPECTED_REVIEW_ID,
        "review_session_artifact_id": EXPECTED_REVIEW_ARTIFACT_ID,
        "review_session_payload_sha256": EXPECTED_REVIEW_PAYLOAD_SHA256,
        "review_session_status_after_generation": review_after.payload.status.value,
        "approved_review_artifact_id": EXPECTED_APPROVED_ARTIFACT_ID,
        "approved_review_payload_sha256": EXPECTED_APPROVED_PAYLOAD_SHA256,
        "integrated_assessment_artifact_id": integrated_stored.artifact_id,
        "integrated_assessment_payload_sha256": integrated_stored.payload_sha256,
        "assessment_run_id": EXPECTED_ASSESSMENT_RUN_ID,
        "decision_package_artifact_id": stored.artifact_id,
        "decision_package_payload_sha256": stored.payload_sha256,
        "decision_package_revision": stored.artifact_revision,
        "decision_package_parent_artifact_id": stored.parent_artifact_id,
        "package_id": package.package_id,
        "package_schema_version": package.package_schema_version,
        "completeness": package.completeness.value,
        "policy_id": package.source.policy.policy_id,
        "policy_version": package.source.policy.policy_version,
        "policy_status": package.source.policy.policy_status,
        "decision_policy_fingerprint": (
            package.source.policy.decision_policy_fingerprint
        ),
        "workflow_stage": stage,
        "ordered_step_ids": ordered_ids,
        "observed_portfolio_items": observed_items,
        "future_state_step_count": len(package.future_state.steps),
        "missing_information_count": len(package.missing_information),
        "evidence_appendix_count": len(package.evidence_appendix),
        "roi_statement": package.roi_statement,
        "human_supplied_assertions": human_supplied,
        "newly_minted_evidence_count": len(minted),
        "recorded_operations": operations,
        "generate_package_operation_status": package_status,
        "frozen_source_hashes_after_generation": frozen_digests,
        "before_corpus_sha256": before_digest,
        "stage5_database_sha256": stage5_digest,
        "stop_boundary_note": STOP_BOUNDARY_NOTE,
        "outcome_gating_note": (
            "This operator asserts no expected completeness, intervention type, "
            "roadmap shape or package narrative. Package content above is recorded "
            "exactly as produced."
        ),
    }
    STAGE5_PACKAGE_RECORD_PATH.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"  package record written                   {STAGE5_PACKAGE_RECORD_PATH.relative_to(ROOT)}")
    print("  (the record cannot contain its own hash; record it in the run manifest)")

    print("\n" + "=" * 78)
    print("PORT-004 DECISION PACKAGE PERSISTED — TERMINAL PRODUCT STAGE.")
    print("=" * 78)
    for line in textwrap.wrap(STOP_BOUNDARY_NOTE, 78):
        print(line)
    print("\nSTOP. No implementation, deployment or rollout output. No AFTER access.")


# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify every gate and packaging readiness. Writes nothing, generates nothing.",
    )
    group.add_argument(
        "--confirm-init-stage5-workspace",
        action="store_true",
        help="Create the Stage 5 working copy of the frozen Stage 4 database. Does not generate.",
    )
    group.add_argument(
        "--confirm-generate-package",
        action="store_true",
        help="Make exactly one AssessmentWorkspaceService.generate_package() call, then stop.",
    )
    args = parser.parse_args(argv)

    if args.dry_run:
        mode_label, guard_mode = "DRY RUN", "dry-run"
    elif args.confirm_init_stage5_workspace:
        mode_label, guard_mode = "INIT STAGE 5 WORKSPACE", "stage5"
    else:
        mode_label, guard_mode = "GENERATE PACKAGE", "stage5"

    install_case_data_guard(guard_mode)
    print("=" * 78)
    print(f"{CASE_ID} STAGE 5 / PHASE 6 DECISION PACKAGE ({mode_label})")
    print("=" * 78)
    identity = report_execution_identity(require_committed=not args.dry_run)
    candidate_bytes = run_safety_checks()

    if args.dry_run:
        dry_run(candidate_bytes)
    elif args.confirm_init_stage5_workspace:
        init_stage5_workspace()
    else:
        generate_stage5_package(candidate_bytes, identity)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

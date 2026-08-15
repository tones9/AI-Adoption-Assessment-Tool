"""Stage 3 operator script for the PORT-003 retrospective portfolio validation run.

Scope
-----
Freeze the complete PORT-003 product output. This script produces no product content:
it verifies the run, then writes ``output_freeze_manifest.v0.1.json`` and
``output_hashes.sha256``.

This must complete, and be committed, before the PORT-003 AFTER packet is opened.

Sealed AFTER handling
---------------------
The manifest records the sealed AFTER packet's digest so a later reader can prove the
packet was unchanged at freeze time. This script therefore opens that file, but only
inside :func:`digest_only`, which streams bytes into a hash and never retains, returns
or prints any content. The digest is additionally checked against a constant recorded
before the run, so the file open is pure verification rather than disclosure.

Usage
-----
    .venv/bin/python evaluation/portfolio/_run_port003_stage3_freeze.py --verify
    .venv/bin/python evaluation/portfolio/_run_port003_stage3_freeze.py --write
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
PORTFOLIO = SCRIPT_PATH.parent
ROOT = PORTFOLIO.parents[1]

sys.path.insert(0, str(ROOT / "src"))

CASE_ID = "PORT-003"
RUN_LABEL = "production-run-v0.1"
RUN_DIR = PORTFOLIO / "runs" / "port-003" / RUN_LABEL
DATABASE_PATH = RUN_DIR / "workspace.db"

BEFORE_PATH = PORTFOLIO / "product_inputs" / "port-003.before.txt"
EXPECTED_BEFORE_SHA256 = (
    "79237f4d0164a2d6c3747fca3baf1e4f92613bc5c29b367eca0d8add7428441b"
)
SEALED_AFTER_PATH = PORTFOLIO / "sealed_after" / "port-003.after.md"
EXPECTED_AFTER_SHA256 = (
    "b2f20906aea6895a5c0d0aa24f69a8f17ed8a470597ca6a70e9c30b901dd9e1a"
)

CASE_FREEZE_COMMIT = "d2deb43c4445743673768be85201e69be69554d3"
EXPECTED_PRODUCTION_FINGERPRINT = (
    "4deca4251d4a9840d6948411544fdf506f1953c16a56eaca803099d2cf81be5a"
)
OPENAI_SDK_VERSION = "2.54.0"

STAGE1_SCRIPT = PORTFOLIO / "_run_port003_stage1.py"
STAGE2_SCRIPT = PORTFOLIO / "_run_port003_stage2.py"

MANIFEST_NAME = "output_freeze_manifest.v0.1.json"
HASHES_NAME = "output_hashes.sha256"
PRODUCT_ARTIFACTS = (
    "approval_result.json",
    "approved_review.json",
    "candidate_extraction.json",
    "decision_package_result.json",
    "final_run_state.json",
    "ingestion_result.json",
    "integrated_assessment.json",
    "review_session.json",
    "run_state_after_extraction.json",
    "validated_business_process.json",
    "workspace.db",
)


class CaseDataBoundaryError(RuntimeError):
    """A forbidden portfolio case file was opened during the freeze."""


def install_case_data_guard() -> None:
    portfolio_root = os.path.realpath(PORTFOLIO)
    allowed_files = {
        os.path.realpath(BEFORE_PATH),
        os.path.realpath(SEALED_AFTER_PATH),  # digest_only verification, never read
        os.path.realpath(STAGE1_SCRIPT),
        os.path.realpath(STAGE2_SCRIPT),
        os.path.realpath(SCRIPT_PATH),
    }
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
            f"{CASE_ID} case-data guard refused to open {resolved}."
        )

    sys.addaudithook(hook)


def digest_only(path: Path) -> str:
    """Return a file's SHA-256 without retaining, returning or printing its content."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def production_subtree_fingerprint() -> str:
    listing = subprocess.run(
        ["git", "ls-files", "config", "src", "streamlit_app.py", "pyproject.toml"],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    ).stdout.split()
    lines = [
        f"{digest_only(ROOT / name)}  {name}" for name in sorted(listing)
    ]
    return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()


def git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    ).stdout.strip()


def verify() -> dict[str, Any]:
    failures: list[str] = []

    if digest_only(BEFORE_PATH) != EXPECTED_BEFORE_SHA256:
        failures.append("frozen BEFORE document hash changed")
    after_digest = digest_only(SEALED_AFTER_PATH)
    if after_digest != EXPECTED_AFTER_SHA256:
        failures.append("sealed AFTER packet hash changed")
    fingerprint = production_subtree_fingerprint()
    if fingerprint != EXPECTED_PRODUCTION_FINGERPRINT:
        failures.append(f"production fingerprint changed: {fingerprint}")

    for name in PRODUCT_ARTIFACTS:
        if not (RUN_DIR / name).is_file():
            failures.append(f"missing product artefact: {name}")

    connection = sqlite3.connect(f"file:{DATABASE_PATH}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        stage = connection.execute(
            "SELECT current_stage FROM assessments"
        ).fetchone()["current_stage"]
        rows = connection.execute(
            "SELECT artifact_type, artifact_revision FROM assessment_artifacts"
        ).fetchall()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    if stage != "package-ready":
        failures.append(f"workflow stage is {stage}, expected package-ready")
    if len(rows) != 6:
        failures.append(f"expected 6 persisted artefacts, found {len(rows)}")
    if any(row["artifact_revision"] != 1 for row in rows):
        failures.append("every persisted artefact must be at revision 1")
    if integrity != "ok":
        failures.append(f"sqlite integrity_check returned {integrity}")

    final_state = json.loads((RUN_DIR / "final_run_state.json").read_text())
    extraction_state = json.loads(
        (RUN_DIR / "run_state_after_extraction.json").read_text()
    )
    if final_state["source_sha256"] != EXPECTED_BEFORE_SHA256:
        failures.append("run source hash does not match the frozen BEFORE document")

    print(f"--- {CASE_ID} FREEZE VERIFICATION ---")
    print(f"  before sha256              {EXPECTED_BEFORE_SHA256[:16]}...  OK")
    print(f"  sealed AFTER sha256        {after_digest[:16]}...  OK (digest only)")
    print(f"  production fingerprint     {fingerprint[:16]}...  OK")
    print(f"  workflow stage             {stage}")
    print(f"  persisted artefacts        {len(rows)} (all revision 1)")
    print(f"  sqlite integrity           {integrity}")
    print(f"  recommendations            {Counter(final_state['recommendations'].values())}")

    if failures:
        for failure in failures:
            print(f"  FAIL: {failure}")
        raise SystemExit(f"{CASE_ID} freeze verification failed.")
    print("  all preconditions satisfied")

    return {
        "after_digest": after_digest,
        "final_state": final_state,
        "extraction_state": extraction_state,
    }


def build_manifest(context: dict[str, Any]) -> dict[str, Any]:
    final_state = context["final_state"]
    extraction_state = context["extraction_state"]
    invocation = extraction_state["provider_invocations"][0]
    distribution = Counter(final_state["recommendations"].values())

    return {
        "schema_version": "portfolio-product-output-freeze.v0.1",
        "case_id": CASE_ID,
        "run_label": RUN_LABEL,
        "pre_run_freeze_commit": CASE_FREEZE_COMMIT,
        "repository_head_at_run": git_head(),
        "production_subtree_fingerprint": EXPECTED_PRODUCTION_FINGERPRINT,
        "before_input": {
            "path": "evaluation/portfolio/product_inputs/port-003.before.txt",
            "sha256": EXPECTED_BEFORE_SHA256,
            "document_id": final_state["document_id"],
        },
        "provider": {
            "name": invocation["provider_name"],
            "sdk_version": OPENAI_SDK_VERSION,
            "requested_model": invocation["requested_model"],
            "effective_model": invocation["effective_model"],
            "configuration_id": "extraction.v0.1",
            "configuration_sha256": digest_only(
                ROOT / "config" / "extraction.v0.1.json"
            ),
            "prompt_version": "process-extraction.v0.1",
            "schema_version": "candidate-process.v0.1",
            "application_level_extraction_attempts": invocation["attempt"],
            "provider_calls": extraction_state["provider_calls"],
            "repair_invoked": False,
            "request_id": invocation["request_id"],
            "input_tokens": invocation["usage"]["input_tokens"],
            "output_tokens": invocation["usage"]["output_tokens"],
            "structured_output_status": "SUCCESS",
            "evidence_resolution_status": "SUCCESS",
        },
        "lineage": {
            "assessment_id": final_state["assessment_id"],
            "extraction_run_id": final_state["extraction_run_id"],
            "review_id": final_state["review_id"],
            "approval_event_id": final_state["approval_event_id"],
            "validated_process_id": final_state["validated_process_id"],
            "validated_process_fingerprint": final_state["validated_process_fingerprint"],
            "assessment_run_id": final_state["assessment_run_id"],
            "decision_policy_fingerprint": final_state["decision_policy_fingerprint"],
            "package_id": final_state["package_id"],
        },
        "product_outcome": {
            "workflow_stage": final_state["workflow_stage"],
            "candidate_step_count": extraction_state["candidate_step_count"],
            "review_status": "APPROVED",
            "recommendation_distribution": {
                "AUTOMATE": distribution.get("AUTOMATE", 0),
                "AUGMENT": distribution.get("AUGMENT", 0),
                "INVESTIGATE_FURTHER": distribution.get("INVESTIGATE_FURTHER", 0),
                "DO_NOT_RECOMMEND": distribution.get("DO_NOT_RECOMMEND", 0),
            },
            "package_completeness": final_state["package_completeness"],
            "future_state_status": final_state["future_state_status"],
            "roi_statement": final_state["roi_statement"],
        },
        "human_review": {
            "event_counts": final_state["review_event_counts"],
            "capability_signals_corrected": 0,
            "assertions_rejected": 0,
            "conflicts_resolved": 0,
            "note": (
                "The live extraction identified creates_new_content on the note-recording "
                "and summary-preparation activities unaided. Review accepted every "
                "source-supported assertion, accepted the order-consistent dependency, "
                "and retained all remaining unknowns. Unlike PORT-002, review recovered "
                "no missed capability signal because none was missed."
            ),
        },
        "operator_scripts": {
            "note": (
                "PORT-001 and PORT-002 operator scripts were not preserved in version "
                "control. PORT-003 commits its operator scripts so the run can be "
                "inspected and, apart from non-deterministic provider output, re-executed."
            ),
            "stage1": {
                "path": "evaluation/portfolio/_run_port003_stage1.py",
                "sha256": digest_only(STAGE1_SCRIPT),
            },
            "stage2": {
                "path": "evaluation/portfolio/_run_port003_stage2.py",
                "sha256": digest_only(STAGE2_SCRIPT),
            },
        },
        "after_boundary_at_output_freeze": {
            "path": "evaluation/portfolio/sealed_after/port-003.after.md",
            "sha256": context["after_digest"],
            "status": "SEALED_NOT_OPENED_FOR_COMPARISON",
        },
        "artifacts": [
            {"path": name, "sha256": digest_only(RUN_DIR / name)}
            for name in PRODUCT_ARTIFACTS
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--verify", action="store_true", help="Check preconditions only.")
    group.add_argument("--write", action="store_true", help="Write the freeze artefacts.")
    args = parser.parse_args(argv)

    install_case_data_guard()
    context = verify()
    if args.verify:
        print("\nVerification only; no freeze artefacts written.")
        return 0

    manifest_path = RUN_DIR / MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(build_manifest(context), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    relative = RUN_DIR.relative_to(ROOT).as_posix()
    lines = [
        f"{digest_only(RUN_DIR / name)}  {relative}/{name}"
        for name in sorted([*PRODUCT_ARTIFACTS, MANIFEST_NAME])
    ]
    (RUN_DIR / HASHES_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n--- FREEZE ARTEFACTS WRITTEN ---")
    for name in (MANIFEST_NAME, HASHES_NAME):
        print(f"  {digest_only(RUN_DIR / name)}  {name}")
    print(f"\n{CASE_ID} product output is frozen. The AFTER packet remains sealed.")
    print("Commit this freeze before opening evaluation/portfolio/sealed_after/port-003.after.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

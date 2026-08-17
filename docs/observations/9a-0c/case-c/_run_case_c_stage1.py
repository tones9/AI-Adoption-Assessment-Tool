"""Stage 1 operator script for the Phase 9A-0c Case C observation.

Scope
-----
Phase 2 ingestion and Phase 3 live extraction for Case C, followed by export of the
stage-1 artefacts. Operator harness only: no product logic, no change to policy,
prompt, schema, taxonomy, thresholds or configuration. It calls only the unchanged
Phase 1-7 production entry points.

This script stops at candidate extraction. It does not run Phase 4 review, approval,
the assessment engine, the decision-support package or any recommendation.

Case-data boundary
------------------
The only case file this script may read is the frozen Case C document::

    docs/observations/9a-0c/case-c/newriver-recruitment-selection-sop.pdf

It must never read the pre-registered prediction, the selection/freeze record, the
sourcing memos, the Plymouth scratch artefacts, or any PORT-001/002/003 artefact. That
boundary is enforced twice: by an explicit allowlist, and by a ``sys.addaudithook``
file-open guard that aborts the process if any other case file is opened.

The pre-registered prediction is deliberately unreadable by this script. Transmitting
or consulting it would contaminate the observation it exists to test.

Safety
------
Both hashes are hard-checked before anything is transmitted:

* document  ``2a8fba60b7264fb38dd6cd3e0308f6673245beffd47e82d855c423bb333a5f3f``
* fingerprint ``3c5c86bd132d25745ee7fcba2e40c3e3d796a9ff404a36a93aecce60cbaf1a85``

Usage
-----
Inspect what would be transmitted, with no network call::

    .venv/bin/python docs/observations/9a-0c/case-c/_run_case_c_stage1.py --dry-run

Perform the approved live provider call::

    .venv/bin/python docs/observations/9a-0c/case-c/_run_case_c_stage1.py --confirm-live-call

No ``PYTHONPATH`` is required; this script prepends ``src/`` to ``sys.path``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
CASE_DIR = SCRIPT_PATH.parent
ROOT = SCRIPT_PATH.parents[4]

sys.path.insert(0, str(ROOT / "src"))

CASE_ID = "C"
RUN_LABEL = "production-run-v0.1"
ASSESSMENT_TITLE = "Phase 9A-0c Case C observation"
SOURCE_FILENAME = "newriver-recruitment-selection-sop.pdf"

DOCUMENT_PATH = CASE_DIR / SOURCE_FILENAME
EXPECTED_DOCUMENT_SHA256 = (
    "2a8fba60b7264fb38dd6cd3e0308f6673245beffd47e82d855c423bb333a5f3f"
)
EXPECTED_FINGERPRINT = (
    "3c5c86bd132d25745ee7fcba2e40c3e3d796a9ff404a36a93aecce60cbaf1a85"
)

RUN_DIR = CASE_DIR / RUN_LABEL
DATABASE_PATH = RUN_DIR / "workspace.db"
EXTRACTION_CONFIG = ROOT / "config" / "extraction.v0.1.json"

# Measured during pre-run characterisation and recorded in the Case C freeze record.
# The frozen document under the frozen configuration must produce exactly this many
# chunks; any other number means the document or the configuration has changed.
EXPECTED_CHUNK_COUNT = 2

# Recorded so an operator error is loud rather than silent. This script never reads
# these; the audit hook below aborts the process if anything tries to.
FORBIDDEN_CASE_MATERIAL = (
    "docs/observations/9a-0c/case-c/case-c-prediction.v0.1.json",
    "docs/observations/9a-0c/case-c/case-c-selection-freeze-record.v0.1.md",
    "docs/observations/9a-0c/case-c-sourcing-candidates.v0.1.md",
    "docs/observations/9a-0c/case-c-sourcing-candidates.v0.2.md",
    "docs/observations/9a-0c/scratch/",
    "evaluation/portfolio/",
)


class CaseDataBoundaryError(RuntimeError):
    """A forbidden case file was opened during the Case C observation run."""


def install_case_data_guard() -> None:
    """Abort if any case file outside the allowlist is opened."""

    observations_root = os.path.realpath(CASE_DIR.parents[1])   # docs/observations
    portfolio_root = os.path.realpath(ROOT / "evaluation" / "portfolio")
    allowed_files = {
        os.path.realpath(DOCUMENT_PATH),
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
        guarded = resolved.startswith(observations_root + os.sep) or resolved.startswith(
            portfolio_root + os.sep
        )
        if not guarded:
            return
        if resolved in allowed_files:
            return
        if resolved == allowed_tree or resolved.startswith(allowed_tree + os.sep):
            return
        raise CaseDataBoundaryError(
            f"Case {CASE_ID} data guard refused to open {resolved}. Only the frozen "
            "Case C document and this run's own output directory are permitted."
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
    """Verify both hashes. Returns the document bytes. Aborts on any mismatch."""

    print("--- SAFETY CHECKS ---")
    if not DOCUMENT_PATH.is_file():
        raise SystemExit(f"Frozen Case C document is missing: {DOCUMENT_PATH}")
    payload = DOCUMENT_PATH.read_bytes()

    digest = hashlib.sha256(payload).hexdigest()
    print(f"  document           {DOCUMENT_PATH.relative_to(ROOT)}")
    print(f"  document sha256    {digest}")
    if digest != EXPECTED_DOCUMENT_SHA256:
        raise SystemExit(
            "ABORT: frozen document hash mismatch.\n"
            f"  expected {EXPECTED_DOCUMENT_SHA256}\n"
            f"  actual   {digest}\n"
            "Nothing was transmitted."
        )
    print("  document hash      MATCH")

    fingerprint = production_fingerprint()
    print(f"  fingerprint        {fingerprint}")
    if fingerprint != EXPECTED_FINGERPRINT:
        raise SystemExit(
            "ABORT: production subtree fingerprint mismatch.\n"
            f"  expected {EXPECTED_FINGERPRINT}\n"
            f"  actual   {fingerprint}\n"
            "Production code changed since Case C was frozen. Nothing was transmitted."
        )
    print("  fingerprint        MATCH")
    print("  all safety checks  PASSED")
    return payload


def write_json(path: Path, payload: Any) -> None:
    document = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class TransmissionPlan:
    """The exact provider payload, computed locally. Pure: no network, no state.

    Both modes derive their payload from this one function, so the hashes printed by
    --dry-run and by the live pre-transmission summary are necessarily identical for
    an unchanged document and configuration.
    """

    def __init__(self, configuration, result, document, chunks, system, prompts) -> None:
        self.configuration = configuration
        self.result = result
        self.document = document
        self.chunks = chunks
        self.system = system      # (characters, sha256)
        self.prompts = prompts    # [(chunk, characters, sha256)]

    @property
    def maximum_calls(self) -> int:
        return len(self.chunks) * (1 + self.configuration.repair_attempts)


def compute_transmission_plan(payload: bytes) -> TransmissionPlan:
    """Ingest and plan chunks locally. Makes no network call and creates no state."""

    from ai_adoption_engine.extraction.chunking import plan_chunks
    from ai_adoption_engine.extraction.configuration import load_extraction_configuration
    from ai_adoption_engine.extraction.prompting import SYSTEM_PROMPT, build_extraction_prompt
    from ai_adoption_engine.extraction.providers.base import ExtractionRequest
    from ai_adoption_engine.ingestion.pdf import ingest_pdf_bytes

    configuration = load_extraction_configuration(EXTRACTION_CONFIG)
    result = ingest_pdf_bytes(payload, SOURCE_FILENAME)
    if result.document is None:
        raise SystemExit(
            f"ABORT: ingestion failed: {[issue.code for issue in result.issues]}. "
            "Nothing was transmitted."
        )
    document = result.document
    chunks = plan_chunks(document, configuration.chunking_config())

    prompts = []
    for chunk in chunks:
        request = ExtractionRequest(
            document_id=document.document_id,
            chunk=chunk,
            schema_version=configuration.schema_version,
            prompt_version=configuration.prompt_version,
        )
        prompt = build_extraction_prompt(request)
        prompts.append((chunk, len(prompt), hashlib.sha256(prompt.encode()).hexdigest()))

    system = (len(SYSTEM_PROMPT), hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest())
    return TransmissionPlan(configuration, result, document, chunks, system, prompts)


def print_payload_hashes(plan: TransmissionPlan) -> None:
    """Print payload identity without printing any payload content."""

    characters, digest = plan.system
    print(f"  system prompt            {characters} chars  sha256={digest}")
    for chunk, characters, digest in plan.prompts:
        print(f"  user prompt              chunk={chunk.chunk_id}")
        print(f"                           {characters} chars  sha256={digest}")


def assert_expected_chunk_count(plan: TransmissionPlan) -> None:
    if len(plan.chunks) != EXPECTED_CHUNK_COUNT:
        raise SystemExit(
            f"ABORT: chunk plan is {len(plan.chunks)}, expected {EXPECTED_CHUNK_COUNT}.\n"
            "The frozen document or the extraction configuration has changed since "
            "Case C was characterised. Nothing was transmitted."
        )


def describe_transmission(payload: bytes) -> None:
    """Summarise the provider payload without printing it. No network call is made."""

    from ai_adoption_engine.models.extraction import RawChunkExtraction

    plan = compute_transmission_plan(payload)
    configuration, result, document = plan.configuration, plan.result, plan.document

    print("\n--- PHASE 2 INGESTION (local, deterministic) ---")
    print(f"  status             {result.status.value}")
    print(f"  document_id        {document.document_id}")
    print(f"  input_type         {document.source.input_type.value}")
    print(f"  blocks             {len(document.blocks)}")
    print(f"  canonical_text     {len(document.canonical_text)} characters")
    print(f"  issues             {[i.code for i in result.issues] or 'none'}")

    print("\n--- PHASE 3 CHUNK PLAN ---")
    print(f"  chunks planned     {len(plan.chunks)}")
    for chunk in plan.chunks:
        print(
            f"    {chunk.chunk_id}  sequence={chunk.sequence} "
            f"characters={chunk.character_count} blocks={len(chunk.block_ids)}"
        )
    assert_expected_chunk_count(plan)
    print(f"  chunk count check  MATCH ({EXPECTED_CHUNK_COUNT})")

    print("\n--- PROVIDER CONFIGURATION (unchanged, frozen) ---")
    for key, value in (
        ("provider", configuration.provider),
        ("model", configuration.model),
        ("reasoning_effort", configuration.reasoning_effort),
        ("prompt_version", configuration.prompt_version),
        ("schema_version", configuration.schema_version),
        ("tools_enabled", configuration.tools_enabled),
        ("streaming_enabled", configuration.streaming_enabled),
        ("store_responses", configuration.store_responses),
        ("max_output_tokens", configuration.max_output_tokens),
        ("timeout_seconds", configuration.timeout_seconds),
        ("sdk_max_retries", configuration.sdk_max_retries),
        ("repair_attempts", configuration.repair_attempts),
    ):
        print(f"  {key:<20} {value}")
    print(f"  {'response_format':<20} {RawChunkExtraction.__name__} (strict structured output)")

    print("\n--- WHAT WOULD BE TRANSMITTED (hashed, not printed) ---")
    print_payload_hashes(plan)
    print(f"\n  provider calls expected: {len(plan.chunks)}")
    print(f"  maximum with repair:     {plan.maximum_calls}")

    print("\n--- NOT TRANSMITTED ---")
    for item in FORBIDDEN_CASE_MATERIAL:
        print(f"  excluded  {item}")
    print("  The pre-registered prediction is never read by this script.")

    if "openai" in sys.modules:  # pragma: no cover - defensive assertion
        raise SystemExit("ABORT: the provider module was imported during a dry run.")
    print("\n--- DRY RUN COMPLETE — NO NETWORK CALL WAS MADE ---")
    print("  provider module not loaded; verified via sys.modules")
    print("  Re-run with --confirm-live-call to perform the live extraction.")


def run_live(payload: bytes) -> None:
    from ai_adoption_engine.workspace.composition import build_workspace_service
    from ai_adoption_engine.workspace.models import ExecutionMode

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("ABORT: OPENAI_API_KEY is not set. Nothing was transmitted.")

    # The run directory is immutable once created. A partial or previous run must never
    # be silently reused, and its artefacts must never be overwritten. A deliberate
    # rerun requires a separately named run directory, not deletion of this one.
    if RUN_DIR.exists():
        existing = sorted(item.name for item in RUN_DIR.iterdir())
        if existing:
            raise SystemExit(
                f"ABORT: {RUN_DIR.relative_to(ROOT)} already exists and is not empty.\n"
                f"  contains: {existing}\n"
                "Refusing to reuse or overwrite an existing run. Nothing was "
                "transmitted. A deliberate rerun must use a separately named run "
                "directory; do not delete this one during 9A-0c."
            )

    # ---- Pre-flight. Pure and local: no network, no workspace, no file created. ----
    # The same computation --dry-run uses, so the hashes below are necessarily the
    # hashes reviewed there. Every gate must pass before any state is created.
    plan = compute_transmission_plan(payload)
    configuration = plan.configuration
    assert_expected_chunk_count(plan)

    print("\n--- PRE-TRANSMISSION SUMMARY ---")
    print(f"  document sha256          {EXPECTED_DOCUMENT_SHA256}  VERIFIED")
    print(f"  production fingerprint   {EXPECTED_FINGERPRINT}  VERIFIED")
    print(f"  model                    {configuration.model}")
    print(f"  configuration            {configuration.configuration_id} v{configuration.version}")
    print(f"  prompt_version           {configuration.prompt_version}")
    print(f"  schema_version           {configuration.schema_version}")
    print(f"  reasoning_effort         {configuration.reasoning_effort}")
    print(f"  planned chunks           {len(plan.chunks)}")
    for chunk in plan.chunks:
        print(
            f"    {chunk.chunk_id}  sequence={chunk.sequence} "
            f"characters={chunk.character_count} blocks={len(chunk.block_ids)}"
        )
    print(f"  chunk count check        MATCH ({EXPECTED_CHUNK_COUNT})")
    print_payload_hashes(plan)
    print(f"  expected provider calls  {len(plan.chunks)} (one per chunk)")
    print(f"  maximum with repair      {plan.maximum_calls} "
          f"(repair_attempts={configuration.repair_attempts})")
    print("  all pre-flight gates     PASSED — creating workspace")

    # ---- Everything below this line creates state or transmits. ----
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    service = build_workspace_service(DATABASE_PATH)

    record = service.repository.create_assessment(ASSESSMENT_TITLE, ExecutionMode.LIVE_PROVIDER)
    print(f"\nassessment_id      {record.assessment_id}")

    ingestion = service.ingest_upload(
        record.assessment_id, payload=payload, filename=SOURCE_FILENAME
    )
    if ingestion.document is None:
        raise SystemExit(f"Ingestion failed: {[i.code for i in ingestion.issues]}")
    print(f"ingestion_status   {ingestion.status.value}")
    print(f"document_id        {ingestion.document.document_id}")
    print(f"blocks             {len(ingestion.document.blocks)}")

    print("\nCalling the live provider...")
    extraction = service.extract(record.assessment_id)
    candidate = extraction.candidate
    extraction_run_id = candidate.extraction_run_id if candidate is not None else None

    print(f"extraction_status  {extraction.status.value}")
    print(f"extraction_run_id  {extraction_run_id}")
    print(f"provider_calls     {len(extraction.provider_invocations)}")
    for invocation in extraction.provider_invocations:
        print(
            f"  chunk={invocation.chunk_id} attempt={invocation.attempt} "
            f"model={invocation.effective_model} request_id={invocation.request_id} "
            f"in={invocation.usage.input_tokens} out={invocation.usage.output_tokens}"
        )
    print(f"issues             {[i.code for i in extraction.issues] or 'none'}")
    if candidate is not None:
        print(f"candidate_steps    {len(candidate.steps)}")
        for step in candidate.steps:
            print(f"  {step.document_order.value}. {step.activity.value}")

    write_json(RUN_DIR / "ingestion_result.json", ingestion)
    write_json(RUN_DIR / "candidate_extraction.json", extraction)

    workspace = service.repository.load_workspace(record.assessment_id)
    active = {
        artifact_type.value: {
            "artifact_id": stored.artifact_id,
            "artifact_revision": stored.artifact_revision,
            "parent_artifact_id": stored.parent_artifact_id,
            "payload_sha256": stored.payload_sha256,
        }
        for artifact_type, stored in workspace.active_artifacts.items()
    }
    run_state = {
        "active_artifacts": active,
        "assessment_id": record.assessment_id,
        "candidate_present": candidate is not None,
        "candidate_step_count": len(candidate.steps) if candidate is not None else 0,
        "case_id": CASE_ID,
        "document_id": ingestion.document.document_id,
        "document_sha256": EXPECTED_DOCUMENT_SHA256,
        "execution_mode": workspace.assessment.execution_mode.value,
        "extraction_run_id": extraction_run_id,
        "extraction_status": extraction.status.value,
        "ingestion_status": ingestion.status.value,
        "issues": [issue.model_dump(mode="json") for issue in extraction.issues],
        "production_fingerprint": EXPECTED_FINGERPRINT,
        "provider_calls": len(extraction.provider_invocations),
        "provider_invocations": [
            invocation.model_dump(mode="json")
            for invocation in extraction.provider_invocations
        ],
        "workflow_stage": workspace.assessment.current_stage.value,
    }
    write_json(RUN_DIR / "run_state_after_extraction.json", run_state)

    print("\n--- STAGE 1 ARTEFACTS WRITTEN ---")
    for name in sorted(path.name for path in RUN_DIR.iterdir() if path.is_file()):
        digest = hashlib.sha256((RUN_DIR / name).read_bytes()).hexdigest()
        print(f"  {digest}  {name}")
    print("\nStage 1 complete. Workflow stage:", workspace.assessment.current_stage.value)
    print("Phase 4 review, assessment and decision package have NOT been run.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Summarise the provider payload without any network call.",
    )
    group.add_argument(
        "--confirm-live-call",
        action="store_true",
        help="Perform the approved live provider extraction.",
    )
    args = parser.parse_args(argv)

    install_case_data_guard()
    print("=" * 74)
    print(f"PHASE 9A-0c CASE {CASE_ID} — STAGE 1"
          f" ({'DRY RUN' if args.dry_run else 'LIVE PROVIDER CALL'})")
    print("=" * 74)
    payload = run_safety_checks()

    if args.dry_run:
        describe_transmission(payload)
    else:
        run_live(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

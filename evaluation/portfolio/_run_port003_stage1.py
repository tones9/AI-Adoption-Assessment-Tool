"""Stage 1 operator script for the PORT-003 retrospective portfolio validation run.

Scope
-----
Phase 2 ingestion and Phase 3 live extraction for PORT-003, followed by export of
the stage-1 product artefacts. This script is an operator harness only. It adds no
product logic, changes no policy, prompt, schema, model configuration or taxonomy,
and calls only the unchanged Phase 1-7 production entry points.

Case-data boundary
------------------
The only case file this script may read is::

    evaluation/portfolio/product_inputs/port-003.before.txt

It must never read the case register, provenance manifests, leakage audits, source
captures, or any sealed AFTER packet. That boundary is enforced twice: by an explicit
allowlist, and by a ``sys.addaudithook`` file-open guard that aborts the process if any
other file under ``evaluation/portfolio/`` is opened.

Reproducibility note
--------------------
The equivalent PORT-001 and PORT-002 operator scripts were not preserved in version
control. PORT-003 commits its operator scripts so the run can be inspected and, apart
from non-deterministic provider output, re-executed.

Usage
-----
Inspect exactly what would be transmitted, with no network call::

    .venv/bin/python evaluation/portfolio/_run_port003_stage1.py --dry-run

Perform the single approved live provider call::

    .venv/bin/python evaluation/portfolio/_run_port003_stage1.py --confirm-live-call

The package is not installed into the virtual environment, so this script prepends
``src/`` to ``sys.path`` in the same way ``streamlit_app.py`` does. No ``PYTHONPATH``
is required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
PORTFOLIO = SCRIPT_PATH.parent
ROOT = PORTFOLIO.parents[1]

# This script is executed directly; keep the repository runnable before install,
# matching the existing streamlit_app.py entrypoint convention.
sys.path.insert(0, str(ROOT / "src"))

CASE_ID = "PORT-003"
RUN_LABEL = "production-run-v0.1"
ASSESSMENT_TITLE = "PORT-003 production validation"
SOURCE_FILENAME = "port-003.before.txt"

BEFORE_PATH = PORTFOLIO / "product_inputs" / SOURCE_FILENAME
EXPECTED_BEFORE_SHA256 = (
    "79237f4d0164a2d6c3747fca3baf1e4f92613bc5c29b367eca0d8add7428441b"
)
RUN_DIR = PORTFOLIO / "runs" / "port-003" / RUN_LABEL
DATABASE_PATH = RUN_DIR / "workspace.db"
EXTRACTION_CONFIG = ROOT / "config" / "extraction.v0.1.json"

# Recorded so an operator error is loud rather than silent. This script never reads
# these files; the audit hook below aborts the process if anything tries to.
FORBIDDEN_CASE_MATERIAL = (
    "evaluation/portfolio/register.v0.1.json",
    "evaluation/portfolio/freeze_manifest.v0.1.json",
    "evaluation/portfolio/provenance/",
    "evaluation/portfolio/leakage_audits/",
    "evaluation/portfolio/source_captures/",
    "evaluation/portfolio/sealed_after/",
    "evaluation/portfolio/runs/port-001/",
    "evaluation/portfolio/runs/port-002/",
)


class CaseDataBoundaryError(RuntimeError):
    """A forbidden portfolio case file was opened during the production run."""


def install_case_data_guard() -> None:
    """Abort the process if any portfolio file outside the allowlist is opened."""

    portfolio_root = os.path.realpath(PORTFOLIO)
    allowed_files = {
        os.path.realpath(BEFORE_PATH),
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
            f"{CASE_ID} case-data guard refused to open {resolved}. "
            "Only the frozen BEFORE document and this run's output directory are permitted."
        )

    sys.addaudithook(hook)


def read_before_document() -> bytes:
    payload = BEFORE_PATH.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_BEFORE_SHA256:
        raise SystemExit(
            f"Frozen BEFORE document hash mismatch.\n"
            f"  expected {EXPECTED_BEFORE_SHA256}\n"
            f"  actual   {digest}\n"
            "Refusing to run against an unfrozen input."
        )
    return payload


def write_json(path: Path, payload: Any) -> str:
    document = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def describe_transmission(payload: bytes) -> None:
    """Print the exact provider payload without contacting any provider."""

    from ai_adoption_engine.extraction.chunking import plan_chunks
    from ai_adoption_engine.extraction.configuration import load_extraction_configuration
    from ai_adoption_engine.extraction.prompting import SYSTEM_PROMPT, build_extraction_prompt
    from ai_adoption_engine.extraction.providers.base import ExtractionRequest
    from ai_adoption_engine.ingestion.text import ingest_text_bytes
    from ai_adoption_engine.models.extraction import RawChunkExtraction

    configuration = load_extraction_configuration(EXTRACTION_CONFIG)
    result = ingest_text_bytes(payload, SOURCE_FILENAME)
    if result.document is None:
        raise SystemExit(f"Ingestion failed: {[issue.code for issue in result.issues]}")
    document = result.document

    print("=" * 78)
    print(f"{CASE_ID} STAGE 1 DRY RUN - NO NETWORK CALL WAS MADE")
    print("=" * 78)

    print("\n--- FILES READ ---")
    print(f"  {BEFORE_PATH.relative_to(ROOT)}")
    print(f"    sha256    {EXPECTED_BEFORE_SHA256}")
    print(f"    bytes     {len(payload)}")
    print(f"  {EXTRACTION_CONFIG.relative_to(ROOT)}  (frozen provider configuration)")
    print("  No other file under evaluation/portfolio/ was read.")

    print("\n--- PHASE 2 INGESTION (local, deterministic) ---")
    print(f"  status         {result.status.value}")
    print(f"  document_id    {document.document_id}")
    print(f"  input_type     {document.source.input_type.value}")
    print(f"  blocks         {len(document.blocks)}")
    print(f"  canonical_text {len(document.canonical_text)} characters")
    print(f"  issues         {[issue.code for issue in result.issues] or 'none'}")

    chunks = plan_chunks(document, configuration.chunking_config())
    print("\n--- PHASE 3 CHUNK PLAN ---")
    print(f"  chunks planned {len(chunks)}")
    for chunk in chunks:
        print(
            f"    {chunk.chunk_id}  sequence={chunk.sequence}  "
            f"characters={chunk.character_count}  blocks={len(chunk.block_ids)}"
        )

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

    for chunk in chunks:
        request = ExtractionRequest(
            document_id=document.document_id,
            chunk=chunk,
            schema_version=configuration.schema_version,
            prompt_version=configuration.prompt_version,
        )
        print("\n" + "=" * 78)
        print(f"EXACT TRANSMITTED PAYLOAD - chunk {chunk.chunk_id}")
        print("=" * 78)
        print("\n----- role: system -----")
        print(SYSTEM_PROMPT)
        print("\n----- role: user -----")
        print(build_extraction_prompt(request))

    print("\n" + "=" * 78)
    print("Nothing else is transmitted. No provenance manifest, leakage audit, source")
    print("capture, case register or sealed AFTER material is read or sent.")
    print("Re-run with --confirm-live-call to perform the live extraction.")
    print("=" * 78)


def run_live(payload: bytes) -> None:
    from ai_adoption_engine.workspace.composition import build_workspace_service
    from ai_adoption_engine.workspace.models import ArtifactType, ExecutionMode

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set; refusing to attempt a live run.")
    if DATABASE_PATH.exists():
        raise SystemExit(
            f"{DATABASE_PATH.relative_to(ROOT)} already exists. "
            "Refusing to re-run and risk a duplicate paid provider call."
        )

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    service = build_workspace_service(DATABASE_PATH)

    record = service.repository.create_assessment(
        ASSESSMENT_TITLE, ExecutionMode.LIVE_PROVIDER
    )
    print(f"assessment_id      {record.assessment_id}")

    ingestion = service.ingest_upload(
        record.assessment_id, payload=payload, filename=SOURCE_FILENAME
    )
    if ingestion.document is None:
        raise SystemExit(f"Ingestion failed: {[issue.code for issue in ingestion.issues]}")
    print(f"ingestion_status   {ingestion.status.value}")
    print(f"document_id        {ingestion.document.document_id}")
    print(f"blocks             {len(ingestion.document.blocks)}")

    print("\nCalling the live provider once...")
    extraction = service.extract(record.assessment_id)
    candidate = extraction.candidate
    extraction_run_id = candidate.extraction_run_id if candidate is not None else None
    print(f"extraction_status  {extraction.status.value}")
    print(f"extraction_run_id  {extraction_run_id}")
    print(f"provider_calls     {len(extraction.provider_invocations)}")
    for invocation in extraction.provider_invocations:
        print(
            f"  attempt={invocation.attempt} model={invocation.effective_model} "
            f"request_id={invocation.request_id} "
            f"in={invocation.usage.input_tokens} out={invocation.usage.output_tokens}"
        )
    print(f"issues             {[issue.code for issue in extraction.issues] or 'none'}")
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
        "document_id": ingestion.document.document_id,
        "execution_mode": workspace.assessment.execution_mode.value,
        "extraction_run_id": extraction_run_id,
        "extraction_status": extraction.status.value,
        "ingestion_status": ingestion.status.value,
        "issues": [issue.model_dump(mode="json") for issue in extraction.issues],
        "provider_calls": len(extraction.provider_invocations),
        "provider_invocations": [
            invocation.model_dump(mode="json")
            for invocation in extraction.provider_invocations
        ],
        "source_sha256": EXPECTED_BEFORE_SHA256,
        "workflow_stage": workspace.assessment.current_stage.value,
    }
    write_json(RUN_DIR / "run_state_after_extraction.json", run_state)

    print("\n--- STAGE 1 ARTEFACTS WRITTEN ---")
    for name in (
        "ingestion_result.json",
        "candidate_extraction.json",
        "run_state_after_extraction.json",
        "workspace.db",
    ):
        path = RUN_DIR / name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"  {digest}  {path.relative_to(ROOT)}")

    assert ArtifactType.CANDIDATE_EXTRACTION_RESULT.value in active, "candidate not persisted"
    print("\nStage 1 complete. Workflow stage:", workspace.assessment.current_stage.value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the exact provider payload without any network call.",
    )
    group.add_argument(
        "--confirm-live-call",
        action="store_true",
        help="Perform the single approved live OpenAI extraction call.",
    )
    args = parser.parse_args(argv)

    install_case_data_guard()
    payload = read_before_document()

    if args.dry_run:
        describe_transmission(payload)
    else:
        run_live(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

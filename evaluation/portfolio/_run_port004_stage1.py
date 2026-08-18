"""Stage 1 operator script for the PORT-004 retrospective portfolio validation run.

Scope
-----
Phase 2 ingestion and Phase 3 live extraction for PORT-004 (USPTO patent examiner
prior-art search workflow, MPEP Ninth Edition Rev. 10.2019, Chapter 900, pages
900-40 to 900-46, sections 904-904.03), followed by export of the stage-1 product
artefacts. Operator harness only: no product logic, no change to policy, prompt,
schema, taxonomy, thresholds or configuration. It calls only the unchanged Phase
1-7 production entry points.

This script stops at candidate extraction. It does not run Phase 4 review,
approval, the assessment engine, the decision-support package or any
recommendation.

Case-data boundary
-------------------
The only case file this script may read for ingestion is the frozen BEFORE
corpus::

    evaluation/portfolio/product_inputs/port-004.before.txt

The frozen source PDF is opened once, for hash verification only, and is never
ingested or transmitted::

    evaluation/portfolio/source_documents/port-004-mpep-0900-e9r10-2019.pdf

This script must never read PORT-001, PORT-002 or PORT-003 case material, any
sealed AFTER packet (none exists for PORT-004), the case register, provenance
manifests, leakage audits, source captures, or freeze/correction records. That
boundary is enforced twice: by an explicit allowlist, and by a
``sys.addaudithook`` file-open guard that aborts the process if any other file
under ``evaluation/portfolio/`` is opened.

OCR-derived text (produced only during the pre-freeze audit of the
Sec. 904.02(b) decision-tree graphic) was never committed to this repository.
This script asserts that no OCR-named artefact exists anywhere under
``evaluation/portfolio/`` before doing anything else, as a structural
confirmation of that limitation.

Corpus history
---------------
The BEFORE corpus was corrected once, in commit 841d066, after the frozen
corpus in commit e24e495 was found to interleave the two MPEP columns (produced
with ``pdftotext -layout`` on a two-column source). No extraction was ever run
against the superseded corpus. This script hard-checks only the corrected
corpus hash.

Production baseline
--------------------
PORT-001, PORT-002 and PORT-003 ran against the Phase 8 portfolio baseline,
production subtree fingerprint ``4deca4251d4a9840d6948411544fdf506f1953c16a56e
aca803099d2cf81be5a``. Production code has moved on since then (most recently
the Case C review-UI provenance fix in commit de34e07). Re-running PORT-004
against the Phase 8 baseline would require reverting production code, which is
out of scope.

By operator decision, PORT-004 runs against the *current* production
fingerprint, ``3c5c86bd132d25745ee7fcba2e40c3e3d796a9ff404a36a93aecce60cbaf1a8
5`` (the same baseline Case C used). This is a deliberate departure from
PORT-001/002/003 and is recorded here, and must be carried into the PORT-004
freeze/observation record, as a **portfolio-comparability limitation**:
PORT-004 is not running under bit-identical production code to the cases it is
compared against in the portfolio narrative.

Chunk count: measured and pinned
-----------------------------------
``EXPECTED_CHUNK_COUNT`` was left unset (``None``) until a ``--dry-run``
measured the true, deterministic chunk plan for the corrected corpus
(``98fd4ece...7c01``) under the current production fingerprint
(``3c5c86bd...1a85``): 2 chunks, 13,458 and 9,273 characters, 30 and 27 blocks.
It is now pinned to that measured value, ``2``, exactly as Case C and PORT-003
each pin a value measured for their own document. If the document or the
extraction configuration changes, the chunk plan will no longer match ``2``
and ``run_live`` aborts before transmitting anything -- see
``run_safety_checks`` / the chunk-count consistency check in ``run_live``.

``EXPECTED_CHUNK_COUNT`` pins the deterministic Phase 2/3 chunk *plan* only. It
is deliberately never used as, or compared against, the number of provider
calls a live run makes -- see "Provider-call volume" below for why those are
different quantities and must stay different. Pinning this value makes live
execution reachable by this script; it does not by itself authorise running
it. A live call still requires ``--confirm-live-call``, ``OPENAI_API_KEY``,
and an empty run directory, and remains a separate, deliberate operator
action.

Provider-call volume
----------------------
Phase 3's chunk plan is deterministic (``plan_chunks`` depends only on the
document and the frozen chunking configuration), but the number of *provider
calls* it makes is not: ``ProcessExtractionService.extract`` in
``src/ai_adoption_engine/extraction/service.py`` issues one call per chunk and,
on invalid structured output or on an evidence-resolution issue, one
additional repair call for that chunk (never both -- a ``repair_consumed``
flag makes the two repair triggers mutually exclusive per chunk). The
constructor validates ``repair_attempts in {0, 1}``, so per chunk the call
count is 1 or 2, never more, under the current, unmodified production logic.
This is real production behaviour, not a hypothetical: Case C's 2-chunk run
made 3 provider calls because one chunk needed a repair.

Separately, ``OpenAIExtractionProvider`` configures the SDK client with
``max_retries=configuration.sdk_max_retries`` (transport-level retries for
things like transient network errors). Those retries happen *inside* a single
``extract_chunk`` call and are transparent to the SDK; they do not produce
additional ``ProviderInvocation`` records and are not counted here.

Given that, this script computes two numbers from the measured chunk count and
the frozen ``repair_attempts`` value, and treats both as descriptive, not as
gates:

* ``minimum_calls`` = chunk count -- what a run makes if no chunk needs repair.
* ``maximum_calls`` = chunk count x (1 + repair_attempts) -- the true upper
  bound under today's ``service.py`` logic, not an arbitrary buffer.

No new retry or repair policy is introduced here, and none of production's
existing repair behaviour is disabled or worked around. After a live run, the
actual provider-call count is reported as-is, checked only for falling inside
``[minimum_calls, maximum_calls]`` as a consistency observation -- never
compared for equality against the chunk count, and never used to abort or
discard a completed run.

Usage
-----
Inspect exactly what would be transmitted, with no network call and nothing
written to disk::

    .venv/bin/python evaluation/portfolio/_run_port004_stage1.py --dry-run

Attempt the live extraction (currently refuses; see "Live mode is not yet
approved" above)::

    .venv/bin/python evaluation/portfolio/_run_port004_stage1.py --confirm-live-call

The package is not installed into the virtual environment, so this script
prepends ``src/`` to ``sys.path`` in the same way ``streamlit_app.py`` does. No
``PYTHONPATH`` is required.
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
PORTFOLIO = SCRIPT_PATH.parent
ROOT = PORTFOLIO.parents[1]

# This script is executed directly; keep the repository runnable before install,
# matching the existing streamlit_app.py entrypoint convention.
sys.path.insert(0, str(ROOT / "src"))

CASE_ID = "PORT-004"
RUN_LABEL = "production-run-v0.1"
ASSESSMENT_TITLE = "PORT-004 production validation"
SOURCE_FILENAME = "port-004.before.txt"

BEFORE_PATH = PORTFOLIO / "product_inputs" / SOURCE_FILENAME
EXPECTED_BEFORE_SHA256 = (
    "98fd4ecece92f0bec27664241013677af1bd67e15816d3f8ba2291b23e017c01"
)

# Hash-checked for provenance only. This file is never opened for ingestion and
# its bytes are never included in any provider payload.
SOURCE_PDF_PATH = PORTFOLIO / "source_documents" / "port-004-mpep-0900-e9r10-2019.pdf"
EXPECTED_SOURCE_PDF_SHA256 = (
    "a74b4a685afea1976d6e4b035e11ac14aa8850d97dbb006ec14eca9ba2ec29e7"
)

EXPECTED_FINGERPRINT = (
    "3c5c86bd132d25745ee7fcba2e40c3e3d796a9ff404a36a93aecce60cbaf1a85"
)
PHASE8_PORTFOLIO_BASELINE_FINGERPRINT = (
    "4deca4251d4a9840d6948411544fdf506f1953c16a56eaca803099d2cf81be5a"
)

RUN_DIR = PORTFOLIO / "runs" / "port-004" / RUN_LABEL
DATABASE_PATH = RUN_DIR / "workspace.db"
EXTRACTION_CONFIG = ROOT / "config" / "extraction.v0.1.json"

# Measured by --dry-run against the corrected corpus (98fd4ece...7c01) and the
# current production fingerprint (3c5c86bd...1a85): 2 chunks (13,458 and 9,273
# characters; 30 and 27 blocks). This pins the deterministic Phase 2/3 chunk
# *plan* only. It is not, and must never become, a provider-call count -- see
# "Provider-call volume" above. A live run may legitimately make 2 to 4
# logical provider calls depending on whether either chunk needs a repair
# attempt; that is reported after the fact, not gated against this number.
EXPECTED_CHUNK_COUNT: int | None = 2

# Documentary only. The guard below enforces this by allowlist, not by this
# tuple; the tuple exists so an operator reading this file sees the boundary
# spelled out explicitly.
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
)


class CaseDataBoundaryError(RuntimeError):
    """A forbidden portfolio case file was opened during the production run."""


def install_case_data_guard() -> None:
    """Abort the process if any portfolio file outside the allowlist is opened."""

    portfolio_root = os.path.realpath(PORTFOLIO)
    allowed_files = {
        os.path.realpath(BEFORE_PATH),
        os.path.realpath(SOURCE_PDF_PATH),
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
            f"{CASE_ID} case-data guard refused to open {resolved}. Only the "
            "frozen BEFORE document, the frozen source PDF (hash check only), "
            "and this run's output directory are permitted."
        )

    sys.addaudithook(hook)


def assert_no_ocr_material() -> None:
    """Confirm no OCR-derived artefact has been committed under the portfolio.

    The Sec. 904.02(b) search-tool-selection decision tree exists in the source
    PDF only as a graphic. It was recovered with OCR once, during the pre-freeze
    audit, strictly to confirm the graphic contained no AI-assisted-search
    reference. That OCR text was never written into this repository and must
    never become part of the engine input. This is a structural check, not a
    content filter: it looks for the artefact, not for the tree's content.
    """

    hits = sorted(
        str(path.relative_to(ROOT))
        for path in PORTFOLIO.rglob("*")
        if path.is_file() and "ocr" in path.name.lower()
    )
    if hits:
        raise SystemExit(
            "ABORT: OCR-named artefact found under evaluation/portfolio/:\n"
            + "\n".join(f"  {hit}" for hit in hits)
            + "\nOCR-recovered text must never be part of the engine input. "
            "Nothing was transmitted."
        )
    print("  OCR material        ABSENT (verified; audit OCR was never committed)")


def assert_production_tree_clean() -> None:
    """Abort if config/, src/, streamlit_app.py or pyproject.toml have local edits.

    The fingerprint check below detects a *committed* production change, but not
    an uncommitted one sitting in the working tree at run time. Both must be
    ruled out before a live call is authorised.
    """

    result = subprocess.run(
        ["git", "status", "--porcelain", "--", "config", "src", "streamlit_app.py", "pyproject.toml"],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    if result.stdout.strip():
        raise SystemExit(
            "ABORT: production working tree is not clean.\n"
            f"{result.stdout}"
            "config/, src/, streamlit_app.py or pyproject.toml have uncommitted "
            "changes. Nothing was transmitted."
        )
    print("  production tree     CLEAN (config/, src/, streamlit_app.py, pyproject.toml)")


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
    """Verify every gate. Returns the frozen BEFORE bytes. Aborts on any mismatch."""

    print("--- SAFETY CHECKS ---")

    assert_no_ocr_material()
    assert_production_tree_clean()

    if not BEFORE_PATH.is_file():
        raise SystemExit(f"ABORT: frozen BEFORE document is missing: {BEFORE_PATH}")
    payload = BEFORE_PATH.read_bytes()
    before_digest = hashlib.sha256(payload).hexdigest()
    print(f"  before document      {BEFORE_PATH.relative_to(ROOT)}")
    print(f"  before sha256        {before_digest}")
    if before_digest != EXPECTED_BEFORE_SHA256:
        raise SystemExit(
            "ABORT: frozen BEFORE document hash mismatch.\n"
            f"  expected {EXPECTED_BEFORE_SHA256}\n"
            f"  actual   {before_digest}\n"
            "Refusing to run against an unfrozen or superseded input. Nothing "
            "was transmitted."
        )
    print("  before hash          MATCH")

    if not SOURCE_PDF_PATH.is_file():
        raise SystemExit(f"ABORT: frozen source PDF is missing: {SOURCE_PDF_PATH}")
    pdf_digest = hashlib.sha256(SOURCE_PDF_PATH.read_bytes()).hexdigest()
    print(f"  source pdf           {SOURCE_PDF_PATH.relative_to(ROOT)}")
    print(f"  source pdf sha256    {pdf_digest}")
    if pdf_digest != EXPECTED_SOURCE_PDF_SHA256:
        raise SystemExit(
            "ABORT: frozen source PDF hash mismatch.\n"
            f"  expected {EXPECTED_SOURCE_PDF_SHA256}\n"
            f"  actual   {pdf_digest}\n"
            "The source PDF is verified for provenance only and is never "
            "ingested, but a hash mismatch means the case is no longer in its "
            "frozen state. Nothing was transmitted."
        )
    print("  source pdf hash      MATCH (provenance check only; PDF is not ingested)")

    fingerprint = production_fingerprint()
    print(f"  fingerprint          {fingerprint}")
    if fingerprint != EXPECTED_FINGERPRINT:
        raise SystemExit(
            "ABORT: production subtree fingerprint mismatch.\n"
            f"  expected {EXPECTED_FINGERPRINT}\n"
            f"  actual   {fingerprint}\n"
            "Production code has changed since this script was approved. "
            "Nothing was transmitted."
        )
    print("  fingerprint          MATCH (current baseline, approved for PORT-004)")
    print(
        "  fingerprint note     differs from the Phase 8 portfolio baseline "
        f"{PHASE8_PORTFOLIO_BASELINE_FINGERPRINT}\n"
        "                       used by PORT-001/002/003. Recorded by operator "
        "decision as a portfolio-comparability limitation, not reverted."
    )
    print("  all safety checks    PASSED")
    return payload


def write_json(path: Path, payload: Any) -> str:
    document = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TransmissionPlan:
    """The exact provider payload, computed locally. Pure: no network, no state.

    Both modes derive their payload from this one function, so the hashes
    printed by --dry-run would be identical to those a live run would use for
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
    def minimum_calls(self) -> int:
        """Calls made if no chunk needs a repair attempt: one per chunk."""
        return len(self.chunks)

    @property
    def maximum_calls(self) -> int:
        """True upper bound under today's Phase 3 repair logic, not a guess.

        ProcessExtractionService.extract (src/ai_adoption_engine/extraction/
        service.py) issues at most one repair call per chunk -- triggered by
        either invalid structured output or an evidence-resolution issue,
        never both, via its repair_consumed flag -- and its constructor
        validates repair_attempts to be 0 or 1. So the per-chunk ceiling is
        (1 + repair_attempts) calls, and this is chunk_count times that.
        SDK-level retries (configuration.sdk_max_retries) happen inside a
        single logical call and are not counted here; they do not add
        ProviderInvocation records.
        """
        return len(self.chunks) * (1 + self.configuration.repair_attempts)

    @property
    def estimated_input_tokens(self) -> int:
        # Coarse estimate only (~4 characters per token). Not a substitute for
        # the usage figures a live call would report.
        system_chars, _ = self.system
        prompt_chars = sum(characters for _, characters, _ in self.prompts)
        return (system_chars * len(self.prompts) + prompt_chars) // 4


def compute_transmission_plan(payload: bytes) -> TransmissionPlan:
    """Ingest and plan chunks locally, using the current Phase 2/3 logic.

    Makes no network call and creates no state. The chunk count this produces
    is the TRUE count under the frozen configuration and today's production
    code -- it is measured here, never assumed.
    """

    from ai_adoption_engine.extraction.chunking import plan_chunks
    from ai_adoption_engine.extraction.configuration import load_extraction_configuration
    from ai_adoption_engine.extraction.prompting import SYSTEM_PROMPT, build_extraction_prompt
    from ai_adoption_engine.extraction.providers.base import ExtractionRequest
    from ai_adoption_engine.ingestion.text import ingest_text_bytes

    configuration = load_extraction_configuration(EXTRACTION_CONFIG)
    result = ingest_text_bytes(payload, SOURCE_FILENAME)
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
    """Print payload identity and size without printing any payload content."""

    system_chars, system_digest = plan.system
    print(f"  system prompt             {system_chars} chars  sha256={system_digest}")
    for chunk, characters, digest in plan.prompts:
        print(
            f"  chunk {chunk.chunk_id:<10} sequence={chunk.sequence:<3} "
            f"chunk_chars={chunk.character_count:<6} blocks={len(chunk.block_ids):<4} "
            f"prompt_chars={characters}"
        )
        print(f"    payload sha256          {digest}")


def describe_transmission(payload: bytes) -> None:
    """Summarise the provider payload without printing it. No network call is made."""

    from ai_adoption_engine.models.extraction import RawChunkExtraction

    plan = compute_transmission_plan(payload)
    configuration, result, document = plan.configuration, plan.result, plan.document

    print("\n--- PHASE 2 INGESTION (local, deterministic) ---")
    print(f"  status              {result.status.value}")
    print(f"  document_id         {document.document_id}")
    print(f"  input_type          {document.source.input_type.value}")
    print(f"  blocks              {len(document.blocks)}")
    print(f"  canonical_text      {len(document.canonical_text)} characters")
    print(f"  issues              {[issue.code for issue in result.issues] or 'none'}")

    print("\n--- PHASE 3 CHUNK PLAN (measured now, using current Phase 2/3 logic) ---")
    print(f"  chunks planned      {len(plan.chunks)}")
    for chunk in plan.chunks:
        print(
            f"    {chunk.chunk_id}  sequence={chunk.sequence}  "
            f"characters={chunk.character_count}  blocks={len(chunk.block_ids)}"
        )
    if EXPECTED_CHUNK_COUNT is None:
        print(
            "  chunk count check   NOT PINNED — EXPECTED_CHUNK_COUNT is None by "
            "design. This measured value is what a human must review before "
            "pinning it in a follow-up commit. Live mode is disabled until then."
        )
    elif len(plan.chunks) != EXPECTED_CHUNK_COUNT:
        print(
            f"  chunk count check   MISMATCH (measured {len(plan.chunks)}, "
            f"pinned {EXPECTED_CHUNK_COUNT})"
        )
    else:
        print(f"  chunk count check   MATCH ({EXPECTED_CHUNK_COUNT})")

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

    print("\n--- WHAT WOULD BE TRANSMITTED (hashed and sized, not printed) ---")
    print_payload_hashes(plan)

    print("\n--- PROVIDER-CALL VOLUME (both are descriptive, neither is a gate) ---")
    print(
        f"  minimum calls             {plan.minimum_calls} "
        "(one per chunk, if no chunk needs repair)"
    )
    print(
        f"  maximum calls             {plan.maximum_calls} "
        f"(chunk_count x (1 + repair_attempts), repair_attempts="
        f"{configuration.repair_attempts}; derived from "
        "extraction/service.py repair logic, see module docstring)"
    )
    print(
        "  NOTE                      the true count depends on how many "
        "chunks need repair and is only known after a live run; it is not "
        "predicted here and EXPECTED_CHUNK_COUNT is never used as this ceiling"
    )
    print(
        f"  estimated input tokens    ~{plan.estimated_input_tokens} "
        "(coarse ~4 chars/token estimate; not a substitute for measured usage)"
    )

    print("\n--- NOT TRANSMITTED ---")
    print(f"  {SOURCE_PDF_PATH.relative_to(ROOT)}  (hash-checked for provenance only)")
    for item in FORBIDDEN_CASE_MATERIAL:
        print(f"  excluded  {item}")
    print("  No AFTER material exists for PORT-004 and none was read.")
    print("  No OCR-derived text was read (see OCR material check above).")

    if "openai" in sys.modules:  # pragma: no cover - defensive assertion
        raise SystemExit("ABORT: the provider module was imported during a dry run.")
    print("\n--- DRY RUN COMPLETE — NO NETWORK CALL WAS MADE, NOTHING WAS WRITTEN ---")
    print("  provider module not loaded; verified via sys.modules")
    print(f"  {RUN_DIR.relative_to(ROOT)} was not created")
    if EXPECTED_CHUNK_COUNT is None:
        print(
            "  EXPECTED_CHUNK_COUNT is not yet pinned. Pin it to the measured "
            "value above in a follow-up committed change before "
            "--confirm-live-call can run."
        )
    else:
        print(
            f"  EXPECTED_CHUNK_COUNT is pinned to {EXPECTED_CHUNK_COUNT} and "
            "matches this measurement. --confirm-live-call would pass this "
            "gate; it still separately requires OPENAI_API_KEY and an empty "
            "run directory, and was not invoked by this dry run."
        )


def run_live(payload: bytes) -> None:
    if EXPECTED_CHUNK_COUNT is None:
        raise SystemExit(
            "ABORT: live execution is not yet approved for PORT-004.\n"
            "EXPECTED_CHUNK_COUNT is None. Run --dry-run, have a human review "
            "the measured chunk plan and estimated cost, then pin "
            "EXPECTED_CHUNK_COUNT to that measured value in a follow-up, "
            "committed change to this script before this mode is enabled. "
            "Nothing was transmitted."
        )

    from ai_adoption_engine.workspace.composition import build_workspace_service
    from ai_adoption_engine.workspace.models import ArtifactType, ExecutionMode

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("ABORT: OPENAI_API_KEY is not set. Nothing was transmitted.")

    if RUN_DIR.exists():
        existing = sorted(item.name for item in RUN_DIR.iterdir())
        if existing:
            raise SystemExit(
                f"ABORT: {RUN_DIR.relative_to(ROOT)} already exists and is not empty.\n"
                f"  contains: {existing}\n"
                "Refusing to reuse or overwrite an existing run. Nothing was "
                "transmitted. A deliberate rerun must use a separately named "
                "run directory; do not delete this one."
            )

    # ---- Pre-flight. Pure and local: no network, no workspace, no file created. ----
    plan = compute_transmission_plan(payload)
    configuration = plan.configuration
    if len(plan.chunks) != EXPECTED_CHUNK_COUNT:
        raise SystemExit(
            f"ABORT: chunk plan is {len(plan.chunks)}, expected {EXPECTED_CHUNK_COUNT}.\n"
            "The frozen document or the extraction configuration has changed "
            "since EXPECTED_CHUNK_COUNT was pinned. Nothing was transmitted."
        )

    print("\n--- PRE-TRANSMISSION SUMMARY ---")
    print(f"  before sha256             {EXPECTED_BEFORE_SHA256}  VERIFIED")
    print(f"  source pdf sha256         {EXPECTED_SOURCE_PDF_SHA256}  VERIFIED (not transmitted)")
    print(f"  production fingerprint    {EXPECTED_FINGERPRINT}  VERIFIED")
    print(f"  model                     {configuration.model}")
    print(f"  configuration             {configuration.configuration_id} v{configuration.version}")
    print(f"  prompt_version            {configuration.prompt_version}")
    print(f"  schema_version            {configuration.schema_version}")
    print(f"  reasoning_effort          {configuration.reasoning_effort}")
    print(f"  planned chunks            {len(plan.chunks)}")
    for chunk in plan.chunks:
        print(
            f"    {chunk.chunk_id}  sequence={chunk.sequence} "
            f"characters={chunk.character_count} blocks={len(chunk.block_ids)}"
        )
    print(f"  chunk count check         MATCH ({EXPECTED_CHUNK_COUNT})")
    print_payload_hashes(plan)
    print(
        f"  minimum provider calls    {plan.minimum_calls} "
        "(one per chunk, if no chunk needs repair)"
    )
    print(
        f"  maximum provider calls    {plan.maximum_calls} "
        f"(chunk_count x (1 + repair_attempts), repair_attempts="
        f"{configuration.repair_attempts}; see module docstring "
        "'Provider-call volume')"
    )
    print(
        "  NOTE                      the actual count is reported after the "
        "call, not predicted here, and is never compared for equality "
        "against the chunk count"
    )
    print("  all pre-flight gates      PASSED — creating workspace")

    # ---- Everything below this line creates state or transmits. ----
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    service = build_workspace_service(DATABASE_PATH)

    record = service.repository.create_assessment(ASSESSMENT_TITLE, ExecutionMode.LIVE_PROVIDER)
    print(f"\nassessment_id      {record.assessment_id}")

    ingestion = service.ingest_upload(
        record.assessment_id, payload=payload, filename=SOURCE_FILENAME
    )
    if ingestion.document is None:
        raise SystemExit(f"Ingestion failed: {[issue.code for issue in ingestion.issues]}")
    print(f"ingestion_status   {ingestion.status.value}")
    print(f"document_id        {ingestion.document.document_id}")
    print(f"blocks             {len(ingestion.document.blocks)}")

    print("\nCalling the live provider...")
    extraction = service.extract(record.assessment_id)
    candidate = extraction.candidate
    extraction_run_id = candidate.extraction_run_id if candidate is not None else None
    print(f"extraction_status  {extraction.status.value}")
    print(f"extraction_run_id  {extraction_run_id}")
    actual_calls = len(extraction.provider_invocations)
    in_range = plan.minimum_calls <= actual_calls <= plan.maximum_calls
    print(
        f"provider_calls     {actual_calls}  "
        f"(expected range [{plan.minimum_calls}, {plan.maximum_calls}] for "
        f"{len(plan.chunks)} chunk(s), repair_attempts="
        f"{configuration.repair_attempts}) -- "
        f"{'within range' if in_range else 'OUTSIDE range, see note below'}"
    )
    if not in_range:
        print(
            "  NOTE: this is reported, not enforced -- the run above already "
            "completed and its output is not discarded. An out-of-range count "
            "means the maximum_calls formula in this script's docstring is "
            "stale relative to today's extraction/service.py and should be "
            "re-derived, not that this run is invalid."
        )
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
        "case_id": CASE_ID,
        "document_id": ingestion.document.document_id,
        "before_sha256": EXPECTED_BEFORE_SHA256,
        "source_pdf_sha256": EXPECTED_SOURCE_PDF_SHA256,
        "execution_mode": workspace.assessment.execution_mode.value,
        "extraction_run_id": extraction_run_id,
        "extraction_status": extraction.status.value,
        "ingestion_status": ingestion.status.value,
        "issues": [issue.model_dump(mode="json") for issue in extraction.issues],
        "production_fingerprint": EXPECTED_FINGERPRINT,
        "production_fingerprint_baseline_drift": {
            "phase8_portfolio_baseline": PHASE8_PORTFOLIO_BASELINE_FINGERPRINT,
            "port004_baseline": EXPECTED_FINGERPRINT,
            "status": "recorded_portfolio_comparability_limitation_not_reverted",
        },
        "provider_calls": actual_calls,
        "provider_call_volume": {
            "chunk_count": len(plan.chunks),
            "repair_attempts": configuration.repair_attempts,
            "minimum_calls": plan.minimum_calls,
            "maximum_calls": plan.maximum_calls,
            "actual_calls": actual_calls,
            "within_expected_range": in_range,
            "note": (
                "minimum/maximum are descriptive bounds derived from "
                "extraction/service.py repair logic, not a gate. Actual is "
                "never compared for equality against chunk_count."
            ),
        },
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

    assert ArtifactType.CANDIDATE_EXTRACTION_RESULT.value in active, "candidate not persisted"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the exact provider payload plan (hashed, not printed) without any network call.",
    )
    group.add_argument(
        "--confirm-live-call",
        action="store_true",
        help="Attempt the live extraction. Currently refuses: see module docstring.",
    )
    args = parser.parse_args(argv)

    install_case_data_guard()
    print("=" * 78)
    print(f"{CASE_ID} STAGE 1 ({'DRY RUN' if args.dry_run else 'LIVE PROVIDER CALL ATTEMPT'})")
    print("=" * 78)
    payload = run_safety_checks()

    if args.dry_run:
        describe_transmission(payload)
    else:
        run_live(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

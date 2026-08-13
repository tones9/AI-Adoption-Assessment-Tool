"""Diagnostic Phase 1 command-line entry point."""

import argparse
import json
from pathlib import Path
from typing import Sequence

from ai_adoption_engine.decision.engine import AssessmentEngine
from ai_adoption_engine.decision.policy import load_policy
from ai_adoption_engine.models.process import BusinessProcess

DEFAULT_POLICY = Path("config/decision_policy.v0.1.json")
DEFAULT_PROCESS = Path("data/sample_processes/synthetic_customer_complaint_process.json")


def load_process(path: str | Path) -> BusinessProcess:
    process_path = Path(path)
    with process_path.open(encoding="utf-8") as handle:
        return BusinessProcess.model_validate(json.load(handle))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the deterministic Phase 1 AI-opportunity assessment."
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=DEFAULT_POLICY,
        help=f"Decision policy JSON (default: {DEFAULT_POLICY})",
    )
    parser.add_argument(
        "--process",
        type=Path,
        default=DEFAULT_PROCESS,
        help=f"Structured process JSON (default: {DEFAULT_PROCESS})",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Emit compact JSON rather than indented JSON.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assessment = AssessmentEngine(load_policy(args.policy)).assess(load_process(args.process))
    indent = None if args.compact else 2
    print(assessment.model_dump_json(indent=indent))
    return 0


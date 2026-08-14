from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_adoption_engine.decision.engine import AssessmentEngine
from ai_adoption_engine.decision.policy import load_policy
from ai_adoption_engine.models.process import BusinessProcess

from .case_loader import verify_case_packet
from .common import load_json, sha256_file
from .decision_metrics import calculate_decision_metrics
from .extraction_metrics import calculate_extraction_metrics


ROOT = Path(__file__).resolve().parents[2]


def validate_development_cases() -> dict[str, Any]:
    cases = ROOT / "evaluation" / "cases" / "development"
    results: dict[str, Any] = {}
    for directory in sorted(path for path in cases.iterdir() if path.is_dir()):
        manifest = verify_case_packet(directory)
        reference = load_json(directory / "reference" / "reference_annotation.json")
        observed = load_json(directory / "reference" / "observed_extraction.json")
        alignment = load_json(directory / "reference" / "alignment.json")
        result: dict[str, Any] = {
            "case_id": manifest["case_id"],
            "packet_verified": True,
            "extraction": calculate_extraction_metrics(reference, observed, alignment),
        }
        predictions = directory / "reference" / "decision_predictions.json"
        if predictions.is_file():
            result["decision"] = calculate_decision_metrics(
                reference["decision_references"], json.loads(predictions.read_text(encoding="utf-8"))
            )
        results[manifest["case_id"]] = result

    process = BusinessProcess.model_validate(load_json(ROOT / "data" / "sample_processes" / "synthetic_customer_complaint_process.json"))
    policy_path = ROOT / "config" / "decision_policy.v0.2.json"
    assessed = AssessmentEngine(load_policy(policy_path)).assess(process)
    results["frozen_engine_smoke"] = {
        "policy_id": assessed.policy_id,
        "step_count": len(assessed.step_assessments),
        "modes": sorted({item.recommendation_mode.value for item in assessed.step_assessments}),
        "policy_sha256": sha256_file(policy_path),
    }
    return {
        "schema_id": "phase8-development-validation.v0.1",
        "metrics_id": "phase8-primary-metrics.v0.1",
        "api_calls": 0,
        "confirmatory_runs": 0,
        "results": results,
    }


if __name__ == "__main__":
    print(json.dumps(validate_development_cases(), indent=2, sort_keys=True))

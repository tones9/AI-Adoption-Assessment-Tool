from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PORTFOLIO = ROOT / "evaluation" / "portfolio"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_frozen_portfolio_artifacts_match_manifest() -> None:
    manifest = json.loads((PORTFOLIO / "freeze_manifest.v0.1.json").read_text())
    for artifact in manifest["artifacts"]:
        path = ROOT / artifact["path"]
        assert path.is_file(), artifact["path"]
        assert _sha256(path) == artifact["sha256"], artifact["path"]


def test_hash_listing_includes_manifest_and_all_frozen_artifacts() -> None:
    listed = {}
    for line in (PORTFOLIO / "hashes.sha256").read_text().splitlines():
        digest, relative_path = line.split("  ", 1)
        listed[relative_path] = digest
    freeze_path = PORTFOLIO / "freeze_manifest.v0.1.json"
    assert listed["evaluation/portfolio/freeze_manifest.v0.1.json"] == _sha256(
        freeze_path
    )
    manifest = json.loads(freeze_path.read_text())
    for artifact in manifest["artifacts"]:
        assert listed[artifact["path"]] == artifact["sha256"]


def test_only_before_documents_are_registered_as_product_inputs() -> None:
    register = json.loads((PORTFOLIO / "register.v0.1.json").read_text())
    assert len(register["cases"]) == 3
    for case in register["cases"]:
        before_path = case["before_path"]
        assert before_path.startswith("product_inputs/")
        assert before_path.endswith(".before.txt")
        assert "sealed_after" not in before_path
        assert (PORTFOLIO / before_path).is_file()


def test_before_documents_are_anonymised_and_after_free() -> None:
    forbidden = {
        "port-001.before.txt": [
            r"\bEY\b",
            r"Fabric Document Intelligence",
            r"70%",
        ],
        "port-002.before.txt": [
            r"\bElisa\b",
            r"\bMindTitan\b",
            r"\bAnnika\b",
            r"90%",
            r"70%",
            r"34%",
            r"8%",
        ],
        "port-003.before.txt": [
            r"Morgan Stanley",
            r"\bDebrief\b",
            r"\bOpenAI\b",
            r"\bSalesforce\b",
            r"half an hour",
        ],
    }
    for filename, patterns in forbidden.items():
        text = (PORTFOLIO / "product_inputs" / filename).read_text()
        assert "Information not provided" in text
        assert not re.search(r"https?://", text, flags=re.IGNORECASE)
        assert not re.search(r"\bAI\b", text, flags=re.IGNORECASE)
        for pattern in patterns:
            assert not re.search(pattern, text, flags=re.IGNORECASE), pattern


def test_port002_researcher_inference_was_removed() -> None:
    register = json.loads((PORTFOLIO / "register.v0.1.json").read_text())
    case = next(item for item in register["cases"] if item["case_id"] == "PORT-002")
    manifest = json.loads(
        (PORTFOLIO / "provenance" / "port-002.manifest.json").read_text()
    )
    before_text = (PORTFOLIO / case["before_path"]).read_text()
    numbered = [line for line in before_text.splitlines() if re.match(r"^\d+\. ", line)]
    assert case["before_activity_count"] == 6
    assert len(numbered) == 6
    resolution = manifest["researcher_inference_resolution"]
    assert resolution["researcher_inference_in_product_input"] is False
    assert "establishes the customer's issue" not in before_text


def test_after_packets_remain_declared_sealed() -> None:
    freeze = json.loads((PORTFOLIO / "freeze_manifest.v0.1.json").read_text())
    assert freeze["experimental_boundary"]["after_status"] == "SEALED"
    for relative_path in freeze["experimental_boundary"]["sealed_after_paths"]:
        text = (ROOT / relative_path).read_text()
        assert "SEALED UNTIL PRODUCT OUTPUT IS FROZEN" in text


def test_production_code_does_not_import_portfolio_evaluation() -> None:
    prohibited = ("evaluation.portfolio", "evaluation/portfolio", "sealed_after")
    production_files = [ROOT / "streamlit_app.py", *sorted((ROOT / "src").rglob("*.py"))]
    for path in production_files:
        source = path.read_text()
        for token in prohibited:
            assert token not in source, f"{path.relative_to(ROOT)} references {token}"


def test_frozen_production_contract_files_are_unchanged() -> None:
    freeze = json.loads((PORTFOLIO / "freeze_manifest.v0.1.json").read_text())
    baseline = freeze["production_baseline"]
    expected = {
        baseline["decision_policy_path"]: baseline["decision_policy_sha256"],
        baseline["extraction_configuration_path"]: baseline[
            "extraction_configuration_sha256"
        ],
        baseline["extraction_prompt_path"]: baseline["extraction_prompt_sha256"],
        baseline["raw_extraction_contract_path"]: baseline[
            "raw_extraction_contract_sha256"
        ],
        baseline["candidate_contract_path"]: baseline["candidate_contract_sha256"],
    }
    for relative_path, digest in expected.items():
        assert _sha256(ROOT / relative_path) == digest, relative_path

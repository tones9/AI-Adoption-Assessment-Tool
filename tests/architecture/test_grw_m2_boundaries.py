from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_m2_service_cannot_use_baseline_reset_or_direct_engine_or_package_rewrite() -> None:
    source = (ROOT / "src" / "ai_adoption_engine" / "grw" / "m2" / "service.py").read_text(encoding="utf-8")
    assert "reset_to_review" not in source
    assert ".ingest_upload(" not in source
    assert ".extract(" not in source
    assert "AssessmentEngine(" not in source
    assert "save_artifact_and_advance(assessment_id" not in source


def test_m2_repository_has_no_normal_active_pointer_mutator() -> None:
    source = (ROOT / "src" / "ai_adoption_engine" / "persistence" / "reassessment.py").read_text(encoding="utf-8")
    assert "active_reassessment_artifacts" in source
    assert "INSERT INTO active_artifacts" not in source
    assert "UPDATE assessments" not in source

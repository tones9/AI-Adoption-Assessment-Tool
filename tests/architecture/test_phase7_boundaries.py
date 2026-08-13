from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_phase7_does_not_modify_or_duplicate_assessment_methodology() -> None:
    phase7_files = list((ROOT / "src/ai_adoption_engine/presentation").rglob("*.py"))
    phase7_files += list((ROOT / "src/ai_adoption_engine/persistence").rglob("*.py"))
    phase7_files += [
        ROOT / "src/ai_adoption_engine/workspace/service.py",
        ROOT / "src/ai_adoption_engine/workspace/composition.py",
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in phase7_files)
    assert "decision.gates" not in source
    assert "decision.scoring" not in source
    assert "OpenAI(" not in source
    assert "streamlit" not in (ROOT / "src/ai_adoption_engine/review/service.py").read_text()


def test_review_page_routes_mutations_through_phase4_service() -> None:
    source = (ROOT / "src/ai_adoption_engine/presentation/pages/review.py").read_text()
    for operation in (
        "accept_assertion",
        "correct_assertion",
        "reject_assertion",
        "resolve_unknown",
        "retain_unknown",
        "reorder_steps",
        "correct_dependency",
        "resolve_conflict",
    ):
        assert f".{operation}(" in source
    assert ".disposition =" not in source
    assert ".knowledge_state =" not in source
    assert ".origin =" not in source

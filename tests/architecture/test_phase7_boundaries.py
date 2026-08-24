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
    assert "decision.policy" not in source
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


def test_decision_narrative_is_a_pure_presentation_projection() -> None:
    """The narrative projection explains decisions; it never makes or reruns one."""

    source = (
        ROOT / "src/ai_adoption_engine/presentation/decision_narrative.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "streamlit",
        "decision.gates",
        "decision.scoring",
        "decision.policy",
        "ai_adoption_engine.persistence",
        "ai_adoption_engine.workspace",
        "ai_adoption_engine.review",
        "ai_adoption_engine.grw",
        "ai_adoption_engine.application",
        "ai_adoption_engine.decision_support",
    ):
        assert forbidden not in source


def test_labels_module_stays_vocabulary_only() -> None:
    """labels.py maps tokens to words; it must not compose or interpret."""

    source = (ROOT / "src/ai_adoption_engine/presentation/labels.py").read_text(
        encoding="utf-8"
    )
    for forbidden in (
        "streamlit",
        "decision.gates",
        "decision.scoring",
        "decision.policy",
        "import ai_adoption_engine",
        "from ai_adoption_engine",
    ):
        assert forbidden not in source

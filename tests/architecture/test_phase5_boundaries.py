import ast
from pathlib import Path

from ai_adoption_engine.application.assessment import IntegratedAssessmentService
from ai_adoption_engine.models.integrated_assessment import (
    IntegratedAssessmentFailure,
    IntegrationFailureCode,
)
from tests.fakes.review import FIXED_TIME, candidate_result, review_service


def _imports_under(root: Path) -> set[str]:
    imports: set[str] = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
    return imports


def test_earlier_phases_do_not_depend_on_phase5_application_layer() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "ai_adoption_engine"
    for package in ("decision", "ingestion", "extraction", "review"):
        imports = _imports_under(root / package)
        assert not any(
            item == "ai_adoption_engine.application"
            or item.startswith("ai_adoption_engine.application.")
            for item in imports
        )


def test_phase5_imports_engine_but_not_phase1_rule_implementations() -> None:
    root = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "ai_adoption_engine"
        / "application"
    )
    imports = _imports_under(root)
    assert "ai_adoption_engine.decision.engine" in imports
    assert "ai_adoption_engine.decision.policy" in imports
    assert not any(
        item.startswith(forbidden)
        for item in imports
        for forbidden in (
            "ai_adoption_engine.decision.capabilities",
            "ai_adoption_engine.decision.gates",
            "ai_adoption_engine.decision.scoring",
        )
    )


def test_phase5_has_no_provider_ui_or_persistence_imports() -> None:
    root = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "ai_adoption_engine"
        / "application"
    )
    imports = _imports_under(root)
    forbidden = (
        "ai_adoption_engine.extraction.providers",
        "openai",
        "sqlite3",
        "streamlit",
    )
    assert not any(
        imported == item or imported.startswith(f"{item}.")
        for imported in imports
        for item in forbidden
    )


def test_unapproved_review_cannot_reach_integrated_assessment() -> None:
    review = review_service().start_review(candidate_result())
    service = IntegratedAssessmentService(
        policy_loader=lambda: (_ for _ in ()).throw(
            AssertionError("Unapproved review reached policy loading")
        ),
        clock=lambda: FIXED_TIME,
        run_id_factory=lambda: "boundary-test",
    )
    result = service.assess(review)  # type: ignore[arg-type]
    assert isinstance(result, IntegratedAssessmentFailure)
    assert result.errors[0].code is IntegrationFailureCode.APPROVAL_REQUIRED

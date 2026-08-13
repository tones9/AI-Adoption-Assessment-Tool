import pytest
from pydantic import ValidationError

from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.models.evidence import BooleanCriterionInput, CriterionInput
from ai_adoption_engine.models.process import BusinessProcess


def test_unknown_criterion_requires_null_value() -> None:
    with pytest.raises(ValidationError, match="Unknown criteria must use a null value"):
        CriterionInput(
            value=3,
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="The value is not actually known.",
            evidence_ids=["E1"],
        )


def test_inferred_criterion_requires_confidence() -> None:
    with pytest.raises(ValidationError, match="Inferred criteria require a confidence"):
        CriterionInput(
            value=3,
            knowledge_state=KnowledgeState.INFERRED,
            rationale="An inference without confidence is incomplete.",
            evidence_ids=["E1"],
        )


def test_unknown_accountability_cannot_default_to_false() -> None:
    with pytest.raises(
        ValidationError,
        match="Unknown boolean criteria must use a null value",
    ):
        BooleanCriterionInput(
            value=False,
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="No accountability evidence was supplied.",
        )


def test_process_rejects_unknown_evidence_reference(process: BusinessProcess) -> None:
    raw = process.model_dump(mode="json")
    raw["steps"][0]["characteristics"]["business_value"]["evidence_ids"] = ["MISSING"]
    with pytest.raises(ValidationError, match="unknown evidence IDs"):
        BusinessProcess.model_validate(raw)


def test_process_rejects_duplicate_step_ids(process: BusinessProcess) -> None:
    raw = process.model_dump(mode="json")
    raw["steps"][1]["step_id"] = raw["steps"][0]["step_id"]
    with pytest.raises(ValidationError, match="Step IDs must be unique"):
        BusinessProcess.model_validate(raw)


def test_capability_signal_rejects_unknown_evidence_reference(
    process: BusinessProcess,
) -> None:
    raw = process.model_dump(mode="json")
    raw["steps"][0]["characteristics"]["capability_signals"][
        "reads_unstructured_documents"
    ] = {
        "value": True,
        "knowledge_state": "known",
        "rationale": "The activity reads an uploaded document.",
        "evidence_ids": ["MISSING"],
    }
    with pytest.raises(ValidationError, match="unknown evidence IDs"):
        BusinessProcess.model_validate(raw)


def test_descriptive_metadata_and_actor_may_be_unavailable(
    process: BusinessProcess,
) -> None:
    raw = process.model_dump(mode="json")
    raw.pop("description")
    raw.pop("business_objective")
    raw["steps"][0].pop("description")
    raw["steps"][0].pop("actor")
    validated = BusinessProcess.model_validate(raw)
    assert validated.description is None
    assert validated.business_objective is None
    assert validated.steps[0].description is None
    assert validated.steps[0].actor is None


@pytest.mark.parametrize(
    ("field", "scope"),
    [
        ("description", "process"),
        ("business_objective", "process"),
        ("description", "step"),
        ("actor", "step"),
    ],
)
def test_optional_text_rejects_whitespace_when_supplied(
    process: BusinessProcess, field: str, scope: str
) -> None:
    raw = process.model_dump(mode="json")
    target = raw if scope == "process" else raw["steps"][0]
    target[field] = "   "
    with pytest.raises(ValidationError, match="whitespace-only"):
        BusinessProcess.model_validate(raw)

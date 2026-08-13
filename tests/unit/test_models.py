import pytest
from pydantic import ValidationError

from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.models.evidence import CriterionInput
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


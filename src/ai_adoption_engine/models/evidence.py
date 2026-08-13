"""Evidence and criterion inputs with explicit provenance and knowledge state."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_adoption_engine.models.enums import KnowledgeState, UncertaintyStatus


class EvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_locator: str = Field(min_length=1)
    supporting_snippet: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    knowledge_state: KnowledgeState
    uncertainty_status: UncertaintyStatus
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_confidence(self) -> "EvidenceReference":
        if self.knowledge_state is KnowledgeState.INFERRED and self.confidence is None:
            raise ValueError("Inferred evidence requires a confidence value")
        if self.knowledge_state is KnowledgeState.UNKNOWN and self.confidence is not None:
            raise ValueError("Unknown evidence cannot carry a confidence value")
        return self


class CriterionInput(BaseModel):
    """A supplied 0-5 task characteristic and its evidence trail."""

    model_config = ConfigDict(extra="forbid")

    value: int | None = Field(default=None, ge=0, le=5)
    knowledge_state: KnowledgeState
    rationale: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_knowledge_state(self) -> "CriterionInput":
        if self.knowledge_state is KnowledgeState.UNKNOWN:
            if self.value is not None:
                raise ValueError("Unknown criteria must use a null value")
            if self.confidence is not None:
                raise ValueError("Unknown criteria cannot carry a confidence value")
            return self

        if self.value is None:
            raise ValueError("Known or inferred criteria require a value")
        if self.knowledge_state is KnowledgeState.INFERRED and self.confidence is None:
            raise ValueError("Inferred criteria require a confidence value")
        return self


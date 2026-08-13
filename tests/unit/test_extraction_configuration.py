from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_adoption_engine.extraction.configuration import (
    ExtractionConfiguration,
    load_extraction_configuration,
)


CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "extraction.v0.1.json"


def test_versioned_extraction_configuration_loads_approved_defaults() -> None:
    configuration = load_extraction_configuration(CONFIG_PATH)
    assert configuration.provider == "openai"
    assert configuration.model == "gpt-5.6-terra"
    assert configuration.reasoning_effort == "medium"
    assert configuration.tools_enabled is False
    assert configuration.streaming_enabled is False
    assert configuration.store_responses is False
    assert configuration.chunking_config().max_characters == 40_000


def test_configuration_rejects_tools_or_streaming() -> None:
    raw = load_extraction_configuration(CONFIG_PATH).model_dump()
    raw["tools_enabled"] = True
    with pytest.raises(ValidationError, match="must not enable model tools"):
        ExtractionConfiguration.model_validate(raw)
    raw["tools_enabled"] = False
    raw["streaming_enabled"] = True
    with pytest.raises(ValidationError, match="must not enable streaming"):
        ExtractionConfiguration.model_validate(raw)
    raw["streaming_enabled"] = False
    raw["store_responses"] = True
    with pytest.raises(ValidationError, match="must not request response storage"):
        ExtractionConfiguration.model_validate(raw)

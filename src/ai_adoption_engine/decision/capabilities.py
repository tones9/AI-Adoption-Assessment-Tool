"""Deterministic mapping from supplied task signals to broad AI capabilities."""

from ai_adoption_engine.models.enums import Capability
from ai_adoption_engine.models.process import CapabilitySignals

_SIGNAL_MAP: tuple[tuple[str, Capability], ...] = (
    ("reads_unstructured_documents", Capability.DOCUMENT_INFORMATION_EXTRACTION),
    ("categorises_items", Capability.CLASSIFICATION),
    ("predicts_future_outcomes", Capability.PREDICTION_FORECASTING),
    ("detects_anomalies_or_patterns", Capability.ANOMALY_PATTERN_DETECTION),
    ("creates_new_content", Capability.GENERATIVE_AI),
    ("searches_reference_knowledge", Capability.KNOWLEDGE_RETRIEVAL),
    ("ranks_or_suggests_options", Capability.RECOMMENDATION),
    ("supports_complex_decisions", Capability.DECISION_SUPPORT),
    ("interprets_images_or_video", Capability.COMPUTER_VISION),
    ("routes_or_orchestrates_work", Capability.WORKFLOW_AUTOMATION),
)


def map_capabilities(signals: CapabilitySignals) -> list[Capability]:
    """Return capabilities in stable taxonomy order for enabled work signals."""

    return [
        capability
        for field, capability in _SIGNAL_MAP
        if getattr(signals, field).value is True
    ]

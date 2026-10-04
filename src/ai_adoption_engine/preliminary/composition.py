"""Explicit composition for the opt-in Preliminary product journey."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai_adoption_engine.models.preliminary_journey import (
    PreliminaryCompatibilityIdentity,
)
from ai_adoption_engine.persistence.preliminary import SQLitePreliminaryJourneyStore
from ai_adoption_engine.preliminary.formal import PreliminaryFormalStartService
from ai_adoption_engine.preliminary.journey import (
    PreliminaryJourneyService,
    current_preliminary_compatibility_identity,
    require_supported_preliminary_compatibility_identity,
)
from ai_adoption_engine.preliminary.run import PreliminaryRunResultService


@dataclass(frozen=True)
class PreliminaryServiceBundle:
    store: SQLitePreliminaryJourneyStore
    journeys: PreliminaryJourneyService
    runs: PreliminaryRunResultService
    formal: PreliminaryFormalStartService


def build_preliminary_service_bundle(
    database_path: str | Path,
    *,
    supported_identity: PreliminaryCompatibilityIdentity | None = None,
) -> PreliminaryServiceBundle:
    """Construct the isolated services only after explicit feature activation."""

    identity = require_supported_preliminary_compatibility_identity(
        supported_identity or current_preliminary_compatibility_identity()
    )
    store = SQLitePreliminaryJourneyStore(database_path)
    return PreliminaryServiceBundle(
        store=store,
        journeys=PreliminaryJourneyService(store, supported_identity=identity),
        runs=PreliminaryRunResultService(store, supported_identity=identity),
        formal=PreliminaryFormalStartService(store),
    )

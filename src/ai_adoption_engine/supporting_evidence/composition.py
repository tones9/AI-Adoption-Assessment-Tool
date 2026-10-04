"""Explicit, opt-in composition for the supporting-evidence product workflow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_adoption_engine.persistence.formal_evidence import (
    SQLiteFormalEvidenceRepository,
)
from ai_adoption_engine.supporting_evidence.conversion import (
    SupportingEvidenceFormalInputService,
)
from ai_adoption_engine.supporting_evidence.extraction import (
    SupportingEvidenceExtractionService,
)
from ai_adoption_engine.supporting_evidence.ingestion import (
    SupportingDocumentIngestionService,
)
from ai_adoption_engine.supporting_evidence.intake import (
    SupportingDocumentIntakeService,
)
from ai_adoption_engine.supporting_evidence.openai import (
    OpenAISupportingEvidenceProvider,
    load_supporting_evidence_openai_configuration,
)
from ai_adoption_engine.supporting_evidence.provider import (
    SupportingEvidenceProvider,
)
from ai_adoption_engine.supporting_evidence.review import (
    SupportingEvidenceReviewService,
)


ProviderFactory = Callable[[], SupportingEvidenceProvider]
DEFAULT_SUPPORTING_EVIDENCE_CONFIGURATION = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "supporting_evidence_extraction.v0.1.json"
)


def _default_provider_factory() -> SupportingEvidenceProvider:
    configuration = load_supporting_evidence_openai_configuration(
        DEFAULT_SUPPORTING_EVIDENCE_CONFIGURATION
    )
    return OpenAISupportingEvidenceProvider(configuration)


@dataclass(frozen=True)
class SupportingEvidenceServiceBundle:
    repository: SQLiteFormalEvidenceRepository
    intake: SupportingDocumentIntakeService
    ingestion: SupportingDocumentIngestionService
    reviews: SupportingEvidenceReviewService
    formal_inputs: SupportingEvidenceFormalInputService
    _provider_factory: ProviderFactory

    def extraction(self) -> SupportingEvidenceExtractionService:
        """Construct the external-provider boundary only for an explicit extraction."""

        return SupportingEvidenceExtractionService(
            self.repository,
            self._provider_factory(),
        )


def build_supporting_evidence_service_bundle(
    database_path: str | Path,
    *,
    provider_factory: ProviderFactory | None = None,
) -> SupportingEvidenceServiceBundle:
    """Construct migration-7 services after explicit product activation."""

    repository = SQLiteFormalEvidenceRepository(database_path)
    return SupportingEvidenceServiceBundle(
        repository=repository,
        intake=SupportingDocumentIntakeService(repository),
        ingestion=SupportingDocumentIngestionService(repository),
        reviews=SupportingEvidenceReviewService(repository),
        formal_inputs=SupportingEvidenceFormalInputService(repository),
        _provider_factory=provider_factory or _default_provider_factory,
    )

"""Orchestrate candidate extraction without invoking Phase 1 assessment."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from ai_adoption_engine.extraction.chunking import ChunkingConfig, plan_chunks
from ai_adoption_engine.extraction.errors import ExtractionProviderError
from ai_adoption_engine.extraction.evidence import EvidenceResolver
from ai_adoption_engine.extraction.merge import merge_chunks
from ai_adoption_engine.extraction.providers.base import (
    ExtractionRequest,
    StructuredExtractionProvider,
)
from ai_adoption_engine.extraction.validation import validate_candidate_against_document
from ai_adoption_engine.models.document import IngestedDocument
from ai_adoption_engine.models.extraction import (
    CandidateExtractionResult,
    ExtractionIssue,
    ExtractionIssueSeverity,
    ExtractionStatus,
    ProviderInvocation,
)


class ProcessExtractionService:
    def __init__(
        self,
        provider: StructuredExtractionProvider,
        *,
        chunking: ChunkingConfig | None = None,
        schema_version: str = "candidate-process.v0.1",
        prompt_version: str = "process-extraction.v0.1",
        run_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.provider = provider
        self.chunking = chunking or ChunkingConfig()
        self.schema_version = schema_version
        self.prompt_version = prompt_version
        self.run_id_factory = run_id_factory or (
            lambda: f"extraction-{uuid.uuid4()}"
        )

    def extract(self, document: IngestedDocument) -> CandidateExtractionResult:
        chunks = plan_chunks(document, self.chunking)
        if not chunks:
            return CandidateExtractionResult(
                status=ExtractionStatus.FAILED,
                issues=[
                    ExtractionIssue(
                        severity=ExtractionIssueSeverity.ERROR,
                        code="no-extractable-text",
                        message="The document contains no extractable text for Phase 3.",
                    )
                ],
            )

        resolved_chunks = []
        issues: list[ExtractionIssue] = []
        invocations: list[ProviderInvocation] = []
        for chunk in chunks:
            request = ExtractionRequest(
                document_id=document.document_id,
                chunk=chunk,
                schema_version=self.schema_version,
                prompt_version=self.prompt_version,
            )
            try:
                response = self.provider.extract_chunk(request)
                invocations.append(response.invocation)
            except ExtractionProviderError as exc:
                issues.append(
                    ExtractionIssue(
                        severity=ExtractionIssueSeverity.ERROR,
                        code=exc.code,
                        message="The extraction provider could not process this chunk.",
                        chunk_id=chunk.chunk_id,
                    )
                )
                continue

            resolver = EvidenceResolver(document, chunk)
            resolved, resolution_issues = resolver.resolve_chunk(response.extraction)
            if resolution_issues:
                repair_request = ExtractionRequest(
                    document_id=document.document_id,
                    chunk=chunk,
                    schema_version=self.schema_version,
                    prompt_version=self.prompt_version,
                    attempt=2,
                    repair_feedback=tuple(
                        sorted({item.code for item in resolution_issues})
                    ),
                )
                try:
                    repair = self.provider.extract_chunk(repair_request)
                    invocations.append(repair.invocation)
                    repaired, repaired_issues = resolver.resolve_chunk(repair.extraction)
                    if not repaired_issues:
                        resolved = repaired
                        resolution_issues = []
                    else:
                        resolved = repaired
                        resolution_issues = repaired_issues
                except ExtractionProviderError as exc:
                    resolution_issues.append(
                        ExtractionIssue(
                            severity=ExtractionIssueSeverity.ERROR,
                            code=exc.code,
                            message="The provider could not complete evidence repair.",
                            chunk_id=chunk.chunk_id,
                        )
                    )
            resolved_chunks.append(resolved)
            issues.extend(resolution_issues)

        if not resolved_chunks:
            return CandidateExtractionResult(
                status=ExtractionStatus.FAILED,
                issues=issues
                or [
                    ExtractionIssue(
                        severity=ExtractionIssueSeverity.ERROR,
                        code="extraction-failed",
                        message="No document chunks produced candidate output.",
                    )
                ],
                provider_invocations=invocations,
            )

        candidate, merge_issues = merge_chunks(
            document_id=document.document_id,
            extraction_run_id=self.run_id_factory(),
            schema_version=self.schema_version,
            prompt_version=self.prompt_version,
            chunks=resolved_chunks,
        )
        issues.extend(merge_issues)
        if not candidate.steps:
            issues.append(
                ExtractionIssue(
                    severity=ExtractionIssueSeverity.ERROR,
                    code="no-candidate-steps",
                    message="No process activities had verifiable source evidence.",
                )
            )
            return CandidateExtractionResult(
                status=ExtractionStatus.FAILED,
                issues=issues,
                provider_invocations=invocations,
            )

        validate_candidate_against_document(candidate, document)
        status = (
            ExtractionStatus.PARTIAL
            if any(item.severity is ExtractionIssueSeverity.ERROR for item in issues)
            else ExtractionStatus.SUCCESS
        )
        return CandidateExtractionResult(
            status=status,
            candidate=candidate,
            issues=issues,
            provider_invocations=invocations,
        )

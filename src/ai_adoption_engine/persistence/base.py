"""Persistence boundary and errors kept outside the domain contracts."""

from __future__ import annotations

from typing import Protocol

from ai_adoption_engine.workspace.models import WorkspaceSnapshot


class AssessmentRepository(Protocol):
    """Small durable-workspace boundary consumed by Phase 7 orchestration."""

    def load_workspace(self, assessment_id: str) -> WorkspaceSnapshot: ...


class PersistenceError(RuntimeError):
    """A durable workspace operation failed safely."""


class ArtifactNotFoundError(PersistenceError):
    """A requested artifact or assessment does not exist."""


class ArtifactCorruptionError(PersistenceError):
    """A persisted artifact failed integrity or schema validation."""


class OperationAlreadyStartedError(PersistenceError):
    """An expensive operation is already in progress and needs explicit recovery."""

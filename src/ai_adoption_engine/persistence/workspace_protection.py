"""Narrow, side-effect-free protection for frozen evaluation workspaces."""

from __future__ import annotations

from pathlib import Path


class FrozenEvaluationWorkspaceError(PermissionError):
    """A write was attempted against a frozen evaluation portfolio workspace."""


class Phase4FrozenWorkspaceError(FrozenEvaluationWorkspaceError):
    """A Phase 4 review write was attempted against a protected workspace."""


def is_frozen_evaluation_portfolio_path(database_path: str | Path) -> bool:
    """Return whether a configured database path is within the frozen portfolio area.

    This check intentionally performs no database access.  It is a narrow safety
    boundary for evaluation artefacts, not a repository-wide read-only mode.
    """

    path = Path(database_path)
    if str(path) == ":memory:":
        return False
    parts = path.resolve(strict=False).parts
    return "evaluation" in parts and "portfolio" in parts


def assert_phase4_write_target_allowed(database_path: str | Path) -> None:
    """Fail closed before a protected Phase 4 write can access persistence."""

    if is_frozen_evaluation_portfolio_path(database_path):
        raise Phase4FrozenWorkspaceError(
            "Phase 4 review writes are refused for frozen evaluation portfolio workspaces"
        )

"""Low-level SQLite boundary for ``preliminary-journey-store.v0.1``.

The store owns isolated migrations and transaction boundaries. Public journey
commands remain explicitly constructed services rather than repository
side-effects or changes to the strict workflow.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from ai_adoption_engine.models.preliminary_persistence import (
    PRELIMINARY_JOURNEY_STORE_ID,
    PRELIMINARY_JOURNEY_STORE_VERSION,
)
from ai_adoption_engine.persistence.base import PersistenceError
from ai_adoption_engine.persistence.preliminary_migrations import (
    PRELIMINARY_JOURNEY_STORE_MIGRATIONS,
)
from ai_adoption_engine.persistence.workspace_protection import (
    assert_workspace_write_target_allowed,
)


class PreliminaryJourneyStoreError(PersistenceError):
    """The isolated Preliminary persistence schema could not be used safely."""


class SQLitePreliminaryJourneyStore:
    """Isolated store used only through explicit Preliminary services."""

    store_id = PRELIMINARY_JOURNEY_STORE_ID
    store_version = PRELIMINARY_JOURNEY_STORE_VERSION

    def __init__(self, path: str | Path, *, clock=None) -> None:
        self.path = Path(path)
        self.clock = clock or (lambda: datetime.now(UTC))
        assert_workspace_write_target_allowed(self.path)
        if str(self.path) != ":memory:" and not self.path.is_file():
            raise PreliminaryJourneyStoreError(
                "The Preliminary store requires an existing assessment database"
            )
        self._memory_connection: sqlite3.Connection | None = None
        self._migrate()
        if str(self.path) != ":memory:":
            self.path.chmod(0o600)

    def _connect(self) -> sqlite3.Connection:
        if str(self.path) == ":memory:":
            if self._memory_connection is None:
                self._memory_connection = sqlite3.connect(":memory:")
                self._configure(self._memory_connection)
            return self._memory_connection
        connection = sqlite3.connect(self.path)
        self._configure(connection)
        return connection

    @staticmethod
    def _configure(connection: sqlite3.Connection) -> None:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")

    @staticmethod
    def _require_core_schema(connection: sqlite3.Connection) -> None:
        present = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        required = {
            "schema_migrations",
            "assessments",
            "assessment_artifacts",
        }
        if not required <= present:
            raise PreliminaryJourneyStoreError(
                "The Preliminary store requires the existing strict workspace schema"
            )

    def _migrate(self) -> None:
        assert_workspace_write_target_allowed(self.path)
        connection = self._connect()
        try:
            self._require_core_schema(connection)
            table_exists = connection.execute(
                """SELECT 1 FROM sqlite_master
                   WHERE type = 'table'
                     AND name = 'preliminary_journey_schema_migrations'"""
            ).fetchone()
            applied = (
                {
                    row[0]
                    for row in connection.execute(
                        "SELECT version FROM preliminary_journey_schema_migrations"
                    )
                }
                if table_exists is not None
                else set()
            )
            for version, script in PRELIMINARY_JOURNEY_STORE_MIGRATIONS:
                if version in applied:
                    continue
                try:
                    connection.executescript("BEGIN IMMEDIATE;\n" + script)
                    connection.execute(
                        """INSERT INTO preliminary_journey_schema_migrations(
                               version, store_id, store_version, applied_at
                           ) VALUES (?, ?, ?, ?)""",
                        (
                            version,
                            self.store_id,
                            self.store_version,
                            self.clock().isoformat(),
                        ),
                    )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
        except sqlite3.Error as exc:
            raise PreliminaryJourneyStoreError(
                "The Preliminary persistence migration failed safely"
            ) from exc
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        assert_workspace_write_target_allowed(self.path)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        finally:
            if str(self.path) != ":memory:":
                connection.close()

    def migration_versions(self) -> tuple[int, ...]:
        """Return the isolated migration history without exposing record writes."""

        connection = self._connect()
        try:
            return tuple(
                row[0]
                for row in connection.execute(
                    """SELECT version
                       FROM preliminary_journey_schema_migrations
                       ORDER BY version"""
                )
            )
        finally:
            if str(self.path) != ":memory:":
                connection.close()

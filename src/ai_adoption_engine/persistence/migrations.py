"""Small explicit SQLite schema migration set for Phase 7."""

MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE assessments (
            assessment_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            execution_mode TEXT NOT NULL,
            current_stage TEXT NOT NULL,
            source_filename TEXT,
            source_input_type TEXT,
            document_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            row_version INTEGER NOT NULL CHECK (row_version >= 1)
        );

        CREATE TABLE assessment_artifacts (
            artifact_id TEXT PRIMARY KEY,
            assessment_id TEXT NOT NULL REFERENCES assessments(assessment_id) ON DELETE CASCADE,
            artifact_type TEXT NOT NULL,
            artifact_revision INTEGER NOT NULL CHECK (artifact_revision >= 1),
            artifact_schema_version TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL,
            parent_artifact_id TEXT REFERENCES assessment_artifacts(artifact_id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (assessment_id, artifact_type, artifact_revision)
        );

        CREATE TABLE active_artifacts (
            assessment_id TEXT NOT NULL REFERENCES assessments(assessment_id) ON DELETE CASCADE,
            artifact_type TEXT NOT NULL,
            artifact_id TEXT NOT NULL REFERENCES assessment_artifacts(artifact_id),
            PRIMARY KEY (assessment_id, artifact_type)
        );

        CREATE TABLE assessment_operations (
            operation_id TEXT PRIMARY KEY,
            assessment_id TEXT NOT NULL REFERENCES assessments(assessment_id) ON DELETE CASCADE,
            operation_kind TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            status TEXT NOT NULL,
            produced_artifact_id TEXT REFERENCES assessment_artifacts(artifact_id),
            sanitised_error_code TEXT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            UNIQUE (assessment_id, operation_kind, idempotency_key)
        );

        CREATE INDEX idx_artifacts_assessment_type
            ON assessment_artifacts(assessment_id, artifact_type, artifact_revision);
        CREATE INDEX idx_artifacts_parent ON assessment_artifacts(parent_artifact_id);
        CREATE INDEX idx_operations_assessment ON assessment_operations(assessment_id);
        """,
    ),
)


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
    (
        2,
        """
        CREATE TABLE reassessment_runs (
            run_id TEXT PRIMARY KEY,
            assessment_id TEXT NOT NULL REFERENCES assessments(assessment_id),
            baseline_package_artifact_id TEXT NOT NULL REFERENCES assessment_artifacts(artifact_id),
            baseline_package_sha256 TEXT NOT NULL,
            stage TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            row_version INTEGER NOT NULL CHECK (row_version >= 1),
            UNIQUE (assessment_id, baseline_package_artifact_id, run_id)
        );

        CREATE TABLE reassessment_documents (
            document_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES reassessment_runs(run_id),
            content_sha256 TEXT NOT NULL,
            content_type TEXT NOT NULL,
            filename TEXT NOT NULL,
            source_label TEXT NOT NULL,
            content_bytes BLOB NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (run_id),
            UNIQUE (run_id, content_sha256)
        );

        CREATE TABLE reassessment_artifacts (
            artifact_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES reassessment_runs(run_id),
            artifact_type TEXT NOT NULL,
            artifact_revision INTEGER NOT NULL CHECK (artifact_revision >= 1),
            artifact_schema_version TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL,
            parent_artifact_id TEXT REFERENCES reassessment_artifacts(artifact_id),
            created_at TEXT NOT NULL,
            UNIQUE (run_id, artifact_type, artifact_revision)
        );

        CREATE TABLE active_reassessment_artifacts (
            run_id TEXT NOT NULL REFERENCES reassessment_runs(run_id),
            artifact_type TEXT NOT NULL,
            artifact_id TEXT NOT NULL REFERENCES reassessment_artifacts(artifact_id),
            PRIMARY KEY (run_id, artifact_type)
        );

        CREATE TABLE reassessment_operations (
            operation_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES reassessment_runs(run_id),
            operation_kind TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            status TEXT NOT NULL,
            produced_artifact_id TEXT REFERENCES reassessment_artifacts(artifact_id),
            sanitised_error_code TEXT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            UNIQUE (run_id, operation_kind, idempotency_key)
        );

        CREATE INDEX idx_reassessment_runs_baseline ON reassessment_runs(assessment_id, baseline_package_artifact_id);
        CREATE INDEX idx_reassessment_artifacts_run_type ON reassessment_artifacts(run_id, artifact_type, artifact_revision);
        CREATE INDEX idx_reassessment_artifacts_parent ON reassessment_artifacts(parent_artifact_id);
        """,
    ),
    (
        3,
        """
        ALTER TABLE reassessment_runs
            ADD COLUMN creation_idempotency_key TEXT;

        CREATE UNIQUE INDEX idx_reassessment_runs_creation_key
            ON reassessment_runs(
                assessment_id,
                baseline_package_artifact_id,
                creation_idempotency_key
            );
        """,
    ),
    (
        4,
        """
        ALTER TABLE assessments
            ADD COLUMN decision_contract_version TEXT NOT NULL DEFAULT 'phase1-v0.3';
        ALTER TABLE assessments
            ADD COLUMN decision_policy_id TEXT NOT NULL DEFAULT 'decision_policy.v0.2';
        ALTER TABLE assessments
            ADD COLUMN decision_policy_version TEXT NOT NULL DEFAULT '0.2.0';
        ALTER TABLE assessments
            ADD COLUMN decision_policy_fingerprint TEXT NOT NULL
                DEFAULT 'b72e528b102bf893b45e6de9ec311e0888341d12b8aa3f99b8047e324d6a6d66';

        ALTER TABLE assessment_operations
            ADD COLUMN decision_contract_version TEXT;
        ALTER TABLE assessment_operations
            ADD COLUMN decision_policy_fingerprint TEXT;
        ALTER TABLE assessment_operations
            ADD COLUMN contract_idempotency_key TEXT;

        UPDATE assessment_operations
        SET decision_contract_version = 'phase1-v0.3',
            decision_policy_fingerprint =
                'b72e528b102bf893b45e6de9ec311e0888341d12b8aa3f99b8047e324d6a6d66'
        WHERE operation_kind IN ('assess', 'generate-package');

        UPDATE assessment_operations
        SET contract_idempotency_key =
            decision_contract_version || ':' ||
            decision_policy_fingerprint || ':' || idempotency_key
        WHERE operation_kind IN ('assess', 'generate-package');

        CREATE UNIQUE INDEX idx_operations_contract_identity
            ON assessment_operations(
                assessment_id,
                operation_kind,
                contract_idempotency_key
            )
            WHERE contract_idempotency_key IS NOT NULL;

        CREATE TRIGGER prevent_contract_pin_change_after_approval
        BEFORE UPDATE OF
            decision_contract_version,
            decision_policy_id,
            decision_policy_version,
            decision_policy_fingerprint
        ON assessments
        WHEN (
            OLD.decision_contract_version IS NOT NEW.decision_contract_version OR
            OLD.decision_policy_id IS NOT NEW.decision_policy_id OR
            OLD.decision_policy_version IS NOT NEW.decision_policy_version OR
            OLD.decision_policy_fingerprint IS NOT NEW.decision_policy_fingerprint
        ) AND EXISTS (
            SELECT 1
            FROM assessment_artifacts
            WHERE assessment_id = OLD.assessment_id
              AND artifact_type IN (
                  'APPROVED_REVIEW',
                  'INTEGRATED_ASSESSMENT_RESULT',
                  'DECISION_PACKAGE_RESULT'
              )
        )
        BEGIN
            SELECT RAISE(ABORT, 'assessment contract pin is immutable');
        END;
        """,
    ),
)

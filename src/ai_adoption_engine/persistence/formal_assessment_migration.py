"""Isolated additive migration 8 for formal-assessment run persistence."""

from __future__ import annotations


_BASE_SQL = r"""
CREATE TABLE preliminary_formal_assessment_lineages (
    formal_lifecycle_id TEXT PRIMARY KEY
        REFERENCES preliminary_formal_lifecycles(formal_lifecycle_id),
    formal_lifecycle_schema TEXT NOT NULL
        CHECK (formal_lifecycle_schema = 'preliminary-formal-lifecycle.v0.1'),
    journey_id TEXT NOT NULL REFERENCES preliminary_journeys(journey_id),
    source_assessment_id TEXT NOT NULL REFERENCES assessments(assessment_id),
    approved_review_artifact_id TEXT NOT NULL
        REFERENCES assessment_artifacts(artifact_id),
    approved_review_schema_version TEXT NOT NULL
        CHECK (approved_review_schema_version = 'phase4-v0.1'),
    approved_review_revision INTEGER NOT NULL CHECK (approved_review_revision >= 1),
    approved_review_payload_sha256 TEXT NOT NULL
        CHECK (length(approved_review_payload_sha256) = 64),
    source_document_id TEXT NOT NULL,
    source_document_sha256 TEXT NOT NULL CHECK (length(source_document_sha256) = 64),
    validated_process_id TEXT NOT NULL CHECK (length(trim(validated_process_id)) > 0),
    validated_process_fingerprint TEXT NOT NULL
        CHECK (length(validated_process_fingerprint) = 64),
    UNIQUE (formal_lifecycle_id, journey_id),
    CHECK (source_document_id = 'doc-' || source_document_sha256)
);

CREATE TABLE preliminary_formal_assessment_input_choices (
    input_choice_id TEXT PRIMARY KEY,
    formal_lifecycle_id TEXT NOT NULL
        REFERENCES preliminary_formal_assessment_lineages(formal_lifecycle_id),
    schema_version TEXT NOT NULL
        CHECK (schema_version = 'formal-assessment-input-choice.v0.1'),
    store_contract TEXT NOT NULL
        CHECK (store_contract = 'formal-assessment-run-store.v0.1'),
    mode TEXT NOT NULL CHECK (mode IN (
        'APPROVED_PROCESS_ONLY', 'APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE'
    )),
    disposition TEXT NOT NULL CHECK (disposition IN (
        'NO_SUPPORTING_HISTORY', 'CURRENT_SUPPORTING_EVIDENCE_INCLUDED',
        'CURRENT_SUPPORTING_EVIDENCE_EXPLICITLY_EXCLUDED'
    )),
    candidate_set_id TEXT,
    candidate_set_payload_sha256 TEXT,
    readiness_id TEXT,
    readiness_payload_sha256 TEXT,
    request_token TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    CHECK (
        (mode = 'APPROVED_PROCESS_ONLY'
         AND candidate_set_id IS NULL AND candidate_set_payload_sha256 IS NULL
         AND readiness_id IS NULL AND readiness_payload_sha256 IS NULL
         AND disposition != 'CURRENT_SUPPORTING_EVIDENCE_INCLUDED')
        OR
        (mode = 'APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE'
         AND disposition = 'CURRENT_SUPPORTING_EVIDENCE_INCLUDED'
         AND candidate_set_id IS NOT NULL AND candidate_set_payload_sha256 IS NOT NULL
         AND readiness_id IS NOT NULL AND readiness_payload_sha256 IS NOT NULL)
    )
);

CREATE TABLE preliminary_formal_assessment_authorizations (
    authorization_id TEXT PRIMARY KEY,
    formal_lifecycle_id TEXT NOT NULL
        REFERENCES preliminary_formal_assessment_lineages(formal_lifecycle_id),
    input_choice_id TEXT NOT NULL
        REFERENCES preliminary_formal_assessment_input_choices(input_choice_id),
    projection_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    input_mode TEXT NOT NULL,
    schema_version TEXT NOT NULL
        CHECK (schema_version = 'formal-assessment-authorization.v0.1'),
    store_contract TEXT NOT NULL
        CHECK (store_contract = 'formal-assessment-run-store.v0.1'),
    adapter_id TEXT NOT NULL CHECK (adapter_id = 'formal-four-gate-input-adapter.v0.1'),
    adapter_version TEXT NOT NULL CHECK (adapter_version = '0.1.0'),
    adapter_rules_id TEXT NOT NULL
        CHECK (adapter_rules_id = 'formal-four-gate-input-adapter-rules.v0.1'),
    adapter_rules_fingerprint TEXT NOT NULL CHECK (
        adapter_rules_fingerprint = '0472d8517f0a6176ac56ed5599b11c7b22d94092a8a85083551837fd54ec8b5d'
    ),
    policy_id TEXT NOT NULL CHECK (policy_id = 'decision_policy.v0.3'),
    policy_version TEXT NOT NULL CHECK (policy_version = '0.3.0'),
    policy_fingerprint TEXT NOT NULL CHECK (
        policy_fingerprint = '0a2f0040f78e8a4a48b9cc1d9d72f79b4b980f75b85cbd4fcbd8d9ad556e08f2'
    ),
    engine_id TEXT NOT NULL CHECK (engine_id = 'four-gate-assessment-engine.v0.1'),
    engine_version TEXT NOT NULL CHECK (engine_version = '0.1.0'),
    framework_id TEXT NOT NULL CHECK (framework_id = 'four-gate-framework.v0.1'),
    framework_version TEXT NOT NULL CHECK (framework_version = '0.1'),
    output_contract TEXT NOT NULL CHECK (output_contract = 'phase1-v0.4'),
    guidance_catalogue_id TEXT NOT NULL
        CHECK (guidance_catalogue_id = 'formal-evidence-guidance-catalogue.v0.1'),
    guidance_catalogue_fingerprint TEXT NOT NULL CHECK (
        guidance_catalogue_fingerprint = '99f10b4f527e3d920a3db0c9c9794086c84b0fa472b923437ea0e24264aab95c'
    ),
    request_token TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    UNIQUE (authorization_id, formal_lifecycle_id),
    UNIQUE (authorization_id, projection_id, run_id)
);

CREATE TABLE preliminary_formal_input_conflict_resolutions (
    resolution_id TEXT PRIMARY KEY,
    formal_lifecycle_id TEXT NOT NULL,
    authorization_id TEXT NOT NULL,
    projection_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    activity_id TEXT NOT NULL,
    target_key TEXT NOT NULL,
    schema_version TEXT NOT NULL
        CHECK (schema_version = 'formal-input-conflict-resolution.v0.1'),
    store_contract TEXT NOT NULL
        CHECK (store_contract = 'formal-assessment-run-store.v0.1'),
    request_token TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    UNIQUE (authorization_id, activity_id, target_key),
    FOREIGN KEY (authorization_id, formal_lifecycle_id)
        REFERENCES preliminary_formal_assessment_authorizations(
            authorization_id, formal_lifecycle_id
        )
);

CREATE TABLE preliminary_formal_assessment_projections (
    projection_id TEXT PRIMARY KEY,
    formal_lifecycle_id TEXT NOT NULL,
    authorization_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    projection_fingerprint TEXT NOT NULL UNIQUE
        CHECK (length(projection_fingerprint) = 64),
    schema_version TEXT NOT NULL
        CHECK (schema_version = 'formal-assessment-input-projection.v0.1'),
    store_contract TEXT NOT NULL
        CHECK (store_contract = 'formal-assessment-run-store.v0.1'),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    UNIQUE (projection_id, authorization_id, run_id),
    FOREIGN KEY (authorization_id, formal_lifecycle_id)
        REFERENCES preliminary_formal_assessment_authorizations(
            authorization_id, formal_lifecycle_id
        )
);

CREATE TABLE preliminary_formal_assessment_run_requests (
    request_token TEXT PRIMARY KEY,
    formal_lifecycle_id TEXT NOT NULL
        REFERENCES preliminary_formal_assessment_lineages(formal_lifecycle_id),
    run_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    canonical_request_sha256 TEXT NOT NULL CHECK (length(canonical_request_sha256) = 64),
    canonical_operation_payload_sha256 TEXT NOT NULL
        CHECK (length(canonical_operation_payload_sha256) = 64),
    schema_version TEXT NOT NULL
        CHECK (schema_version = 'formal-assessment-run-request.v0.1'),
    store_contract TEXT NOT NULL
        CHECK (store_contract = 'formal-assessment-run-store.v0.1'),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64)
);

CREATE TABLE preliminary_formal_assessment_run_manifests (
    run_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
    formal_lifecycle_id TEXT NOT NULL,
    authorization_id TEXT NOT NULL,
    projection_id TEXT NOT NULL,
    projection_fingerprint TEXT NOT NULL CHECK (length(projection_fingerprint) = 64),
    input_mode TEXT NOT NULL,
    predecessor_attempt_number INTEGER,
    request_token TEXT NOT NULL UNIQUE
        REFERENCES preliminary_formal_assessment_run_requests(request_token),
    schema_version TEXT NOT NULL
        CHECK (schema_version = 'formal-assessment-run-manifest.v0.1'),
    store_contract TEXT NOT NULL
        CHECK (store_contract = 'formal-assessment-run-store.v0.1'),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    PRIMARY KEY (run_id, attempt_number),
    FOREIGN KEY (authorization_id, projection_id, run_id)
        REFERENCES preliminary_formal_assessment_authorizations(
            authorization_id, projection_id, run_id
        ),
    FOREIGN KEY (projection_id, authorization_id, run_id)
        REFERENCES preliminary_formal_assessment_projections(
            projection_id, authorization_id, run_id
        ),
    CHECK ((attempt_number = 1 AND predecessor_attempt_number IS NULL)
        OR (attempt_number > 1 AND predecessor_attempt_number = attempt_number - 1))
);

CREATE TABLE preliminary_formal_assessment_run_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    operation TEXT NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    authorization_id TEXT NOT NULL,
    projection_id TEXT NOT NULL,
    projection_fingerprint TEXT NOT NULL CHECK (length(projection_fingerprint) = 64),
    request_token TEXT NOT NULL UNIQUE
        REFERENCES preliminary_formal_assessment_run_requests(request_token),
    schema_version TEXT NOT NULL
        CHECK (schema_version = 'formal-assessment-run-event.v0.1'),
    store_contract TEXT NOT NULL
        CHECK (store_contract = 'formal-assessment-run-store.v0.1'),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    UNIQUE (run_id, attempt_number, sequence),
    FOREIGN KEY (run_id, attempt_number)
        REFERENCES preliminary_formal_assessment_run_manifests(run_id, attempt_number)
);

CREATE TABLE preliminary_formal_assessment_run_states (
    run_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    event_count INTEGER NOT NULL CHECK (event_count >= 0),
    current_status TEXT NOT NULL,
    schema_version TEXT NOT NULL
        CHECK (schema_version = 'formal-assessment-run-state.v0.1'),
    store_contract TEXT NOT NULL
        CHECK (store_contract = 'formal-assessment-run-store.v0.1'),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    PRIMARY KEY (run_id, attempt_number, event_count),
    FOREIGN KEY (run_id, attempt_number)
        REFERENCES preliminary_formal_assessment_run_manifests(run_id, attempt_number)
);
CREATE INDEX idx_formal_assessment_latest_state
    ON preliminary_formal_assessment_run_states(run_id, attempt_number, event_count DESC);

CREATE TABLE preliminary_formal_assessment_terminal_records (
    terminal_record_id TEXT PRIMARY KEY,
    result_id TEXT UNIQUE,
    run_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    formal_lifecycle_id TEXT NOT NULL,
    record_kind TEXT NOT NULL CHECK (record_kind IN ('SUCCESS', 'FAILURE')),
    status TEXT NOT NULL,
    schema_version TEXT NOT NULL
        CHECK (schema_version = 'formal-assessment-result.v0.1'),
    store_contract TEXT NOT NULL
        CHECK (store_contract = 'formal-assessment-run-store.v0.1'),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    UNIQUE (run_id, attempt_number),
    FOREIGN KEY (run_id, attempt_number)
        REFERENCES preliminary_formal_assessment_run_manifests(run_id, attempt_number),
    CHECK ((record_kind = 'SUCCESS' AND result_id = terminal_record_id
            AND status = 'COMPLETED_PENDING_REVIEW')
        OR (record_kind = 'FAILURE' AND result_id IS NULL
            AND status IN ('FAILED', 'INTERRUPTED', 'ABANDONED')))
);

CREATE TABLE preliminary_formal_assessment_result_supersessions (
    supersession_id TEXT PRIMARY KEY,
    formal_lifecycle_id TEXT NOT NULL,
    superseded_result_id TEXT NOT NULL UNIQUE,
    successor_result_id TEXT NOT NULL UNIQUE,
    superseded_run_id TEXT NOT NULL,
    successor_run_id TEXT NOT NULL,
    request_token TEXT NOT NULL UNIQUE,
    schema_version TEXT NOT NULL
        CHECK (schema_version = 'formal-assessment-result-supersession.v0.1'),
    store_contract TEXT NOT NULL
        CHECK (store_contract = 'formal-assessment-run-store.v0.1'),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    FOREIGN KEY (superseded_result_id)
        REFERENCES preliminary_formal_assessment_terminal_records(result_id),
    FOREIGN KEY (successor_result_id)
        REFERENCES preliminary_formal_assessment_terminal_records(result_id),
    CHECK (superseded_result_id != successor_result_id),
    CHECK (superseded_run_id != successor_run_id)
);

CREATE TABLE preliminary_formal_evidence_guidance (
    guidance_id TEXT PRIMARY KEY,
    formal_lifecycle_id TEXT NOT NULL,
    source_result_id TEXT NOT NULL UNIQUE
        REFERENCES preliminary_formal_assessment_terminal_records(result_id),
    catalogue_id TEXT NOT NULL
        CHECK (catalogue_id = 'formal-evidence-guidance-catalogue.v0.1'),
    catalogue_fingerprint TEXT NOT NULL CHECK (
        catalogue_fingerprint = '99f10b4f527e3d920a3db0c9c9794086c84b0fa472b923437ea0e24264aab95c'
    ),
    schema_version TEXT NOT NULL CHECK (schema_version = 'formal-evidence-guidance.v0.1'),
    store_contract TEXT NOT NULL CHECK (store_contract = 'formal-assessment-run-store.v0.1'),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64)
);

CREATE TABLE preliminary_formal_assessment_operation_requests (
    request_token TEXT PRIMARY KEY,
    canonical_request_sha256 TEXT NOT NULL CHECK (length(canonical_request_sha256) = 64),
    operation_type TEXT NOT NULL,
    operation_payload_sha256 TEXT NOT NULL CHECK (length(operation_payload_sha256) = 64),
    result_schema_version TEXT NOT NULL,
    result_identity TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TRIGGER validate_formal_assessment_lineage
BEFORE INSERT ON preliminary_formal_assessment_lineages
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1
        FROM preliminary_formal_lifecycles lifecycle
        JOIN preliminary_journeys journey ON journey.journey_id = lifecycle.journey_id
        JOIN assessment_artifacts artifact
          ON artifact.artifact_id = lifecycle.approved_review_artifact_id
         AND artifact.assessment_id = lifecycle.source_assessment_id
        WHERE lifecycle.formal_lifecycle_id = NEW.formal_lifecycle_id
          AND lifecycle.schema_version = NEW.formal_lifecycle_schema
          AND lifecycle.journey_id = NEW.journey_id
          AND lifecycle.source_assessment_id = NEW.source_assessment_id
          AND lifecycle.approved_review_artifact_id = NEW.approved_review_artifact_id
          AND lifecycle.approved_review_payload_sha256 = NEW.approved_review_payload_sha256
          AND lifecycle.source_document_id = NEW.source_document_id
          AND lifecycle.validated_process_id = NEW.validated_process_id
          AND lifecycle.validated_process_fingerprint = NEW.validated_process_fingerprint
          AND artifact.artifact_schema_version = NEW.approved_review_schema_version
          AND artifact.artifact_revision = NEW.approved_review_revision
          AND artifact.payload_sha256 = NEW.approved_review_payload_sha256
    ) THEN RAISE(ABORT, 'formal-assessment lineage does not match persisted lifecycle') END;
END;

CREATE TRIGGER validate_formal_assessment_input_choice
BEFORE INSERT ON preliminary_formal_assessment_input_choices
WHEN NEW.mode = 'APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE'
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1
        FROM preliminary_supporting_formal_input_candidate_sets candidate
        JOIN preliminary_supporting_formal_evidence_readiness readiness
          ON readiness.candidate_set_id = candidate.candidate_set_id
        WHERE candidate.candidate_set_id = NEW.candidate_set_id
          AND candidate.formal_lifecycle_id = NEW.formal_lifecycle_id
          AND candidate.payload_sha256 = NEW.candidate_set_payload_sha256
          AND readiness.readiness_id = NEW.readiness_id
          AND readiness.formal_lifecycle_id = NEW.formal_lifecycle_id
          AND readiness.payload_sha256 = NEW.readiness_payload_sha256
          AND readiness.status = 'READY_TO_ATTEMPT'
    ) THEN RAISE(ABORT, 'formal-assessment supporting pins are not exact and ready') END;
END;

CREATE TRIGGER validate_formal_assessment_manifest_retry
BEFORE INSERT ON preliminary_formal_assessment_run_manifests
WHEN NEW.attempt_number > 1
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM preliminary_formal_assessment_run_manifests predecessor
        WHERE predecessor.run_id = NEW.run_id
          AND predecessor.attempt_number = NEW.predecessor_attempt_number
          AND predecessor.authorization_id = NEW.authorization_id
          AND predecessor.projection_id = NEW.projection_id
          AND predecessor.projection_fingerprint = NEW.projection_fingerprint
          AND predecessor.input_mode = NEW.input_mode
    ) THEN RAISE(ABORT, 'formal retry must preserve the exact predecessor projection') END;
END;

CREATE TRIGGER validate_formal_assessment_event_sequence
BEFORE INSERT ON preliminary_formal_assessment_run_events
BEGIN
    SELECT CASE WHEN NEW.sequence != COALESCE((
        SELECT MAX(sequence) + 1 FROM preliminary_formal_assessment_run_events
        WHERE run_id = NEW.run_id AND attempt_number = NEW.attempt_number
    ), 1) THEN RAISE(ABORT, 'formal run event sequence must be gap-free') END;
    SELECT CASE WHEN NEW.from_status != COALESCE((
        SELECT current_status FROM preliminary_formal_assessment_run_states
        WHERE run_id = NEW.run_id AND attempt_number = NEW.attempt_number
        ORDER BY event_count DESC LIMIT 1
    ), 'AUTHORIZED') THEN RAISE(ABORT, 'formal run event must continue current state') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM preliminary_formal_assessment_run_manifests manifest
        WHERE manifest.run_id = NEW.run_id
          AND manifest.attempt_number = NEW.attempt_number
          AND manifest.authorization_id = NEW.authorization_id
          AND manifest.projection_id = NEW.projection_id
          AND manifest.projection_fingerprint = NEW.projection_fingerprint
    ) THEN RAISE(ABORT, 'formal event pins must match its manifest') END;
END;

CREATE TRIGGER validate_formal_assessment_state
BEFORE INSERT ON preliminary_formal_assessment_run_states
BEGIN
    SELECT CASE WHEN NEW.event_count != (
        SELECT COUNT(*) FROM preliminary_formal_assessment_run_events
        WHERE run_id = NEW.run_id AND attempt_number = NEW.attempt_number
    ) THEN RAISE(ABORT, 'formal state event count must equal immutable history') END;
    SELECT CASE WHEN NEW.current_status != COALESCE((
        SELECT to_status FROM preliminary_formal_assessment_run_events
        WHERE run_id = NEW.run_id AND attempt_number = NEW.attempt_number
        ORDER BY sequence DESC LIMIT 1
    ), 'AUTHORIZED') THEN RAISE(ABORT, 'formal state must equal derived event status') END;
END;

CREATE TRIGGER validate_formal_assessment_terminal_record
BEFORE INSERT ON preliminary_formal_assessment_terminal_records
BEGIN
    SELECT CASE WHEN NEW.status != (
        SELECT current_status FROM preliminary_formal_assessment_run_states
        WHERE run_id = NEW.run_id AND attempt_number = NEW.attempt_number
        ORDER BY event_count DESC LIMIT 1
    ) THEN RAISE(ABORT, 'formal terminal record must equal current derived state') END;
END;

CREATE TRIGGER validate_formal_assessment_supersession
BEFORE INSERT ON preliminary_formal_assessment_result_supersessions
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1
        FROM preliminary_formal_assessment_terminal_records predecessor
        JOIN preliminary_formal_assessment_terminal_records successor
          ON successor.result_id = NEW.successor_result_id
        WHERE predecessor.result_id = NEW.superseded_result_id
          AND predecessor.record_kind = 'SUCCESS'
          AND successor.record_kind = 'SUCCESS'
          AND predecessor.formal_lifecycle_id = NEW.formal_lifecycle_id
          AND successor.formal_lifecycle_id = NEW.formal_lifecycle_id
          AND predecessor.run_id = NEW.superseded_run_id
          AND successor.run_id = NEW.successor_run_id
    ) THEN RAISE(ABORT, 'formal supersession requires same-lifecycle successful results') END;
    SELECT CASE WHEN EXISTS (
        WITH RECURSIVE successors(result_id) AS (
            SELECT NEW.successor_result_id
            UNION ALL
            SELECT link.successor_result_id
            FROM preliminary_formal_assessment_result_supersessions link
            JOIN successors current ON link.superseded_result_id = current.result_id
        )
        SELECT 1 FROM successors WHERE result_id = NEW.superseded_result_id
    ) THEN RAISE(ABORT, 'formal result supersession must be acyclic') END;
END;

CREATE TRIGGER validate_formal_evidence_guidance_source
BEFORE INSERT ON preliminary_formal_evidence_guidance
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM preliminary_formal_assessment_terminal_records result
        WHERE result.result_id = NEW.source_result_id
          AND result.formal_lifecycle_id = NEW.formal_lifecycle_id
          AND result.record_kind = 'SUCCESS'
    ) THEN RAISE(ABORT, 'formal guidance requires its exact successful source result') END;
END;
"""


_IMMUTABLE_TABLES = (
    "preliminary_formal_assessment_lineages",
    "preliminary_formal_assessment_input_choices",
    "preliminary_formal_assessment_authorizations",
    "preliminary_formal_input_conflict_resolutions",
    "preliminary_formal_assessment_projections",
    "preliminary_formal_assessment_run_requests",
    "preliminary_formal_assessment_run_manifests",
    "preliminary_formal_assessment_run_events",
    "preliminary_formal_assessment_run_states",
    "preliminary_formal_assessment_terminal_records",
    "preliminary_formal_assessment_result_supersessions",
    "preliminary_formal_evidence_guidance",
    "preliminary_formal_assessment_operation_requests",
)


def _immutable_triggers() -> str:
    statements: list[str] = []
    for table in _IMMUTABLE_TABLES:
        short = table.removeprefix("preliminary_")
        statements.extend(
            (
                f"CREATE TRIGGER {short}_immutable_update BEFORE UPDATE ON {table} "
                "BEGIN SELECT RAISE(ABORT, 'formal-assessment history is immutable'); END;",
                f"CREATE TRIGGER {short}_immutable_delete BEFORE DELETE ON {table} "
                "BEGIN SELECT RAISE(ABORT, 'formal-assessment history is immutable'); END;",
            )
        )
    return "\n".join(statements)


# Migration 8 is deliberately outside PRELIMINARY_JOURNEY_STORE_MIGRATIONS and
# is applied only by SQLiteFormalAssessmentRepository.
FORMAL_ASSESSMENT_MIGRATION: tuple[int, str] = (
    8,
    _BASE_SQL + "\n" + _immutable_triggers(),
)


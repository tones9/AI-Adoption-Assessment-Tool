"""Isolated additive migrations for ``preliminary-journey-store.v0.1``."""

PRELIMINARY_JOURNEY_STORE_MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        r"""
        CREATE TABLE IF NOT EXISTS preliminary_journey_schema_migrations (
            version INTEGER PRIMARY KEY,
            store_id TEXT NOT NULL CHECK (store_id = 'preliminary-journey-store.v0.1'),
            store_version TEXT NOT NULL CHECK (store_version = '0.1.0'),
            applied_at TEXT NOT NULL
        );

        CREATE TABLE preliminary_journeys (
            journey_id TEXT PRIMARY KEY,
            schema_version TEXT NOT NULL CHECK (schema_version = 'preliminary-journey.v0.1'),
            store_id TEXT NOT NULL CHECK (store_id = 'preliminary-journey-store.v0.1'),
            store_version TEXT NOT NULL CHECK (store_version = '0.1.0'),
            source_assessment_id TEXT NOT NULL REFERENCES assessments(assessment_id),
            approved_review_artifact_id TEXT NOT NULL REFERENCES assessment_artifacts(artifact_id),
            approved_review_schema_version TEXT NOT NULL CHECK (approved_review_schema_version = 'phase4-v0.1'),
            approved_review_payload_sha256 TEXT NOT NULL CHECK (length(approved_review_payload_sha256) = 64),
            source_document_id TEXT NOT NULL CHECK (source_document_id GLOB 'doc-[0-9a-f]*' AND length(source_document_id) = 68),
            extraction_run_id TEXT NOT NULL CHECK (length(trim(extraction_run_id)) > 0),
            review_id TEXT NOT NULL CHECK (length(trim(review_id)) > 0),
            approval_event_id TEXT NOT NULL CHECK (length(trim(approval_event_id)) > 0),
            approved_at TEXT NOT NULL,
            validated_process_id TEXT NOT NULL CHECK (length(trim(validated_process_id)) > 0),
            validated_process_fingerprint TEXT NOT NULL CHECK (length(validated_process_fingerprint) = 64),
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
            UNIQUE (approved_review_artifact_id),
            UNIQUE (journey_id, source_assessment_id)
        );

        CREATE TABLE preliminary_journey_events (
            event_id TEXT PRIMARY KEY,
            journey_id TEXT NOT NULL REFERENCES preliminary_journeys(journey_id),
            event_sequence INTEGER NOT NULL CHECK (event_sequence >= 1),
            schema_version TEXT NOT NULL CHECK (schema_version = 'preliminary-journey-event.v0.1'),
            event_type TEXT NOT NULL CHECK (event_type IN (
                'JOURNEY_CREATED', 'ROUTE_SELECTED', 'ROUTE_CHANGED',
                'RUN_LINKED', 'RUN_RECOVERY_RECORDED', 'RESULT_RECORDED',
                'RESULT_SUPERSEDED', 'FORMAL_LIFECYCLE_STARTED'
            )),
            payload_schema_version TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
            UNIQUE (journey_id, event_sequence),
            UNIQUE (event_id, journey_id, event_sequence)
        );

        CREATE UNIQUE INDEX idx_preliminary_one_journey_created
            ON preliminary_journey_events(journey_id)
            WHERE event_type = 'JOURNEY_CREATED';
        CREATE INDEX idx_preliminary_latest_route_choice
            ON preliminary_journey_events(journey_id, event_sequence DESC)
            WHERE event_type IN ('ROUTE_SELECTED', 'ROUTE_CHANGED');

        CREATE TABLE preliminary_run_manifests (
            preliminary_run_id TEXT PRIMARY KEY,
            journey_id TEXT NOT NULL REFERENCES preliminary_journeys(journey_id),
            schema_version TEXT NOT NULL CHECK (schema_version = 'preliminary-run-manifest.v0.1'),
            store_id TEXT NOT NULL CHECK (store_id = 'preliminary-journey-store.v0.1'),
            request_token TEXT NOT NULL CHECK (length(trim(request_token)) > 0),
            retry_of_run_id TEXT,
            route_choice_event_id TEXT NOT NULL,
            route_choice_event_sequence INTEGER NOT NULL CHECK (route_choice_event_sequence >= 1),
            source_assessment_id TEXT NOT NULL,
            approved_review_artifact_id TEXT NOT NULL,
            approved_review_payload_sha256 TEXT NOT NULL CHECK (length(approved_review_payload_sha256) = 64),
            source_document_id TEXT NOT NULL,
            validated_process_id TEXT NOT NULL,
            validated_process_fingerprint TEXT NOT NULL CHECK (length(validated_process_fingerprint) = 64),
            evaluator_id TEXT NOT NULL CHECK (evaluator_id = 'preliminary-evaluator.v0.1'),
            evaluator_version TEXT NOT NULL CHECK (evaluator_version = '0.1.0'),
            rule_set_id TEXT NOT NULL CHECK (rule_set_id = 'preliminary-evaluator-rules.v0.1'),
            rule_set_version TEXT NOT NULL CHECK (rule_set_version = '0.1.0'),
            rule_set_fingerprint TEXT NOT NULL CHECK (rule_set_fingerprint = '3db8a54561bcfe263a5483e5d4c49e203bfac40eafbc8bc778cf773ed6ad1790'),
            output_schema_version TEXT NOT NULL CHECK (output_schema_version = 'preliminary-assessment.v0.1'),
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
            UNIQUE (journey_id, request_token),
            UNIQUE (preliminary_run_id, journey_id),
            FOREIGN KEY (retry_of_run_id, journey_id)
                REFERENCES preliminary_run_manifests(preliminary_run_id, journey_id),
            FOREIGN KEY (route_choice_event_id, journey_id, route_choice_event_sequence)
                REFERENCES preliminary_journey_events(event_id, journey_id, event_sequence)
        );

        CREATE TABLE preliminary_run_events (
            run_event_id TEXT PRIMARY KEY,
            preliminary_run_id TEXT NOT NULL,
            journey_id TEXT NOT NULL,
            event_sequence INTEGER NOT NULL CHECK (event_sequence IN (1, 2)),
            schema_version TEXT NOT NULL CHECK (schema_version = 'preliminary-run-event.v0.1'),
            event_type TEXT NOT NULL CHECK (event_type IN (
                'RUN_STARTED', 'RUN_COMPLETED', 'RUN_FAILED', 'RUN_ABANDONED'
            )),
            payload_schema_version TEXT NOT NULL,
            preliminary_result_id TEXT,
            occurred_at TEXT NOT NULL,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
            UNIQUE (preliminary_run_id, event_sequence),
            UNIQUE (run_event_id, preliminary_run_id, journey_id),
            FOREIGN KEY (preliminary_run_id, journey_id)
                REFERENCES preliminary_run_manifests(preliminary_run_id, journey_id),
            FOREIGN KEY (preliminary_result_id, preliminary_run_id, journey_id)
                REFERENCES preliminary_results(
                    preliminary_result_id, preliminary_run_id, journey_id
                ) DEFERRABLE INITIALLY DEFERRED,
            CHECK (
                (event_type = 'RUN_COMPLETED' AND preliminary_result_id IS NOT NULL)
                OR
                (event_type != 'RUN_COMPLETED' AND preliminary_result_id IS NULL)
            )
        );

        CREATE UNIQUE INDEX idx_preliminary_one_run_start
            ON preliminary_run_events(preliminary_run_id)
            WHERE event_type = 'RUN_STARTED';
        CREATE UNIQUE INDEX idx_preliminary_one_run_terminal
            ON preliminary_run_events(preliminary_run_id)
            WHERE event_type IN ('RUN_COMPLETED', 'RUN_FAILED', 'RUN_ABANDONED');

        CREATE TABLE preliminary_results (
            preliminary_result_id TEXT PRIMARY KEY,
            preliminary_run_id TEXT NOT NULL,
            journey_id TEXT NOT NULL,
            completed_run_event_id TEXT NOT NULL,
            schema_version TEXT NOT NULL CHECK (schema_version = 'preliminary-result.v0.1'),
            source_assessment_id TEXT NOT NULL,
            approved_review_artifact_id TEXT NOT NULL,
            approved_review_payload_sha256 TEXT NOT NULL CHECK (length(approved_review_payload_sha256) = 64),
            source_document_id TEXT NOT NULL,
            validated_process_id TEXT NOT NULL,
            validated_process_fingerprint TEXT NOT NULL CHECK (length(validated_process_fingerprint) = 64),
            evaluator_id TEXT NOT NULL CHECK (evaluator_id = 'preliminary-evaluator.v0.1'),
            evaluator_version TEXT NOT NULL CHECK (evaluator_version = '0.1.0'),
            rule_set_id TEXT NOT NULL CHECK (rule_set_id = 'preliminary-evaluator-rules.v0.1'),
            rule_set_version TEXT NOT NULL CHECK (rule_set_version = '0.1.0'),
            rule_set_fingerprint TEXT NOT NULL CHECK (rule_set_fingerprint = '3db8a54561bcfe263a5483e5d4c49e203bfac40eafbc8bc778cf773ed6ad1790'),
            output_schema_version TEXT NOT NULL CHECK (output_schema_version = 'preliminary-assessment.v0.1'),
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
            UNIQUE (preliminary_run_id),
            UNIQUE (completed_run_event_id),
            UNIQUE (preliminary_result_id, journey_id),
            UNIQUE (preliminary_result_id, preliminary_run_id, journey_id),
            FOREIGN KEY (preliminary_run_id, journey_id)
                REFERENCES preliminary_run_manifests(preliminary_run_id, journey_id),
            FOREIGN KEY (completed_run_event_id, preliminary_run_id, journey_id)
                REFERENCES preliminary_run_events(
                    run_event_id, preliminary_run_id, journey_id
                ) DEFERRABLE INITIALLY DEFERRED
        );

        CREATE TABLE preliminary_run_state_index (
            preliminary_run_id TEXT PRIMARY KEY,
            journey_id TEXT NOT NULL,
            schema_version TEXT NOT NULL CHECK (schema_version = 'preliminary-run-state-projection.v0.1'),
            projected_status TEXT NOT NULL CHECK (projected_status IN (
                'STARTED', 'COMPLETED', 'FAILED', 'ABANDONED'
            )),
            terminal_event_id TEXT,
            projected_at TEXT NOT NULL,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
            FOREIGN KEY (preliminary_run_id, journey_id)
                REFERENCES preliminary_run_manifests(preliminary_run_id, journey_id),
            FOREIGN KEY (terminal_event_id, preliminary_run_id, journey_id)
                REFERENCES preliminary_run_events(
                    run_event_id, preliminary_run_id, journey_id
                ),
            CHECK (
                (projected_status = 'STARTED' AND terminal_event_id IS NULL)
                OR
                (projected_status != 'STARTED' AND terminal_event_id IS NOT NULL)
            )
        );

        CREATE UNIQUE INDEX idx_preliminary_one_started_run_per_journey
            ON preliminary_run_state_index(journey_id)
            WHERE projected_status = 'STARTED';

        CREATE TABLE preliminary_result_supersessions (
            supersession_id TEXT PRIMARY KEY,
            journey_id TEXT NOT NULL REFERENCES preliminary_journeys(journey_id),
            schema_version TEXT NOT NULL CHECK (schema_version = 'preliminary-result-supersession.v0.1'),
            superseded_result_id TEXT NOT NULL,
            superseding_result_id TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
            UNIQUE (superseded_result_id),
            FOREIGN KEY (superseded_result_id, journey_id)
                REFERENCES preliminary_results(preliminary_result_id, journey_id),
            FOREIGN KEY (superseding_result_id, journey_id)
                REFERENCES preliminary_results(preliminary_result_id, journey_id),
            CHECK (superseded_result_id != superseding_result_id)
        );

        CREATE TABLE preliminary_formal_lifecycles (
            formal_lifecycle_id TEXT PRIMARY KEY,
            journey_id TEXT NOT NULL REFERENCES preliminary_journeys(journey_id),
            schema_version TEXT NOT NULL CHECK (schema_version = 'preliminary-formal-lifecycle.v0.1'),
            source_assessment_id TEXT NOT NULL,
            approved_review_artifact_id TEXT NOT NULL,
            approved_review_payload_sha256 TEXT NOT NULL CHECK (length(approved_review_payload_sha256) = 64),
            source_document_id TEXT NOT NULL,
            validated_process_id TEXT NOT NULL,
            validated_process_fingerprint TEXT NOT NULL CHECK (length(validated_process_fingerprint) = 64),
            route_choice_event_id TEXT NOT NULL,
            route_choice_event_sequence INTEGER NOT NULL CHECK (route_choice_event_sequence >= 1),
            status TEXT NOT NULL CHECK (status = 'AWAITING_FORMAL_INPUTS'),
            preliminary_result_id TEXT,
            preliminary_result_use TEXT,
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
            UNIQUE (journey_id),
            FOREIGN KEY (route_choice_event_id, journey_id, route_choice_event_sequence)
                REFERENCES preliminary_journey_events(event_id, journey_id, event_sequence),
            FOREIGN KEY (preliminary_result_id, journey_id)
                REFERENCES preliminary_results(preliminary_result_id, journey_id),
            CHECK (
                (preliminary_result_id IS NULL AND preliminary_result_use IS NULL)
                OR
                (preliminary_result_id IS NOT NULL AND preliminary_result_use = 'CONTEXT_ONLY_NOT_FORMAL_EVIDENCE')
            )
        );

        CREATE TRIGGER validate_preliminary_journey_source
        BEFORE INSERT ON preliminary_journeys
        BEGIN
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1
                FROM assessment_artifacts ar
                JOIN assessments a ON a.assessment_id = ar.assessment_id
                WHERE ar.artifact_id = NEW.approved_review_artifact_id
                  AND ar.assessment_id = NEW.source_assessment_id
                  AND ar.artifact_type = 'APPROVED_REVIEW'
                  AND ar.artifact_schema_version = NEW.approved_review_schema_version
                  AND ar.payload_sha256 = NEW.approved_review_payload_sha256
                  AND json_extract(ar.payload_json, '$.review.review_id') = NEW.review_id
                  AND json_extract(ar.payload_json, '$.review.original_candidate.source_document_id') = NEW.source_document_id
                  AND json_extract(ar.payload_json, '$.review.original_candidate.extraction_run_id') = NEW.extraction_run_id
                  AND json_extract(ar.payload_json, '$.business_process.process_id') = NEW.validated_process_id
                  AND EXISTS (
                      SELECT 1 FROM json_each(ar.payload_json, '$.review.events') event
                      WHERE json_extract(event.value, '$.event_id') = NEW.approval_event_id
                        AND json_extract(event.value, '$.action') = 'approve'
                  )
            ) THEN RAISE(ABORT, 'approved review is not owned by the pinned source assessment') END;
            SELECT CASE WHEN
                json_extract(NEW.payload_json, '$.journey_id') != NEW.journey_id OR
                json_extract(NEW.payload_json, '$.source.source_assessment_id') != NEW.source_assessment_id OR
                json_extract(NEW.payload_json, '$.source.approved_review_artifact_id') != NEW.approved_review_artifact_id OR
                json_extract(NEW.payload_json, '$.source.approved_review_payload_sha256') != NEW.approved_review_payload_sha256 OR
                json_extract(NEW.payload_json, '$.source.source_document_id') != NEW.source_document_id OR
                json_extract(NEW.payload_json, '$.source.validated_process_id') != NEW.validated_process_id
            THEN RAISE(ABORT, 'journey columns do not match the immutable payload') END;
        END;

        CREATE TRIGGER validate_preliminary_journey_event
        BEFORE INSERT ON preliminary_journey_events
        BEGIN
            SELECT CASE WHEN NEW.event_sequence != COALESCE((
                SELECT MAX(event_sequence) + 1
                FROM preliminary_journey_events
                WHERE journey_id = NEW.journey_id
            ), 1) THEN RAISE(ABORT, 'journey event sequence must be gap-free and monotonic') END;
            SELECT CASE WHEN
                (NEW.event_type = 'JOURNEY_CREATED' AND NEW.payload_schema_version != 'journey-created.v0.1') OR
                (NEW.event_type IN ('ROUTE_SELECTED', 'ROUTE_CHANGED') AND NEW.payload_schema_version != 'journey-selection.v0.1') OR
                (NEW.event_type = 'RUN_LINKED' AND NEW.payload_schema_version != 'preliminary-run-link.v0.1') OR
                (NEW.event_type = 'RUN_RECOVERY_RECORDED' AND NEW.payload_schema_version != 'preliminary-run-recovery.v0.1') OR
                (NEW.event_type = 'RESULT_RECORDED' AND NEW.payload_schema_version != 'preliminary-result-recorded.v0.1') OR
                (NEW.event_type = 'RESULT_SUPERSEDED' AND NEW.payload_schema_version != 'preliminary-result-supersession.v0.1') OR
                (NEW.event_type = 'FORMAL_LIFECYCLE_STARTED' AND NEW.payload_schema_version != 'formal-lifecycle-start.v0.1')
            THEN RAISE(ABORT, 'journey event type and payload schema must match') END;
            SELECT CASE WHEN
                json_extract(NEW.payload_json, '$.event_id') != NEW.event_id OR
                json_extract(NEW.payload_json, '$.journey_id') != NEW.journey_id OR
                json_extract(NEW.payload_json, '$.event_sequence') != NEW.event_sequence OR
                json_extract(NEW.payload_json, '$.event_type') != NEW.event_type OR
                json_extract(NEW.payload_json, '$.payload.schema_version') != NEW.payload_schema_version
            THEN RAISE(ABORT, 'journey event columns do not match the immutable payload') END;
            SELECT CASE WHEN NEW.event_type = 'JOURNEY_CREATED' AND NEW.event_sequence != 1
                THEN RAISE(ABORT, 'JOURNEY_CREATED must be first') END;
            SELECT CASE WHEN NEW.event_type != 'JOURNEY_CREATED' AND NEW.event_sequence = 1
                THEN RAISE(ABORT, 'the first journey event must be JOURNEY_CREATED') END;
        END;

        CREATE TRIGGER validate_preliminary_run_manifest
        BEFORE INSERT ON preliminary_run_manifests
        BEGIN
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1 FROM preliminary_journeys j
                WHERE j.journey_id = NEW.journey_id
                  AND j.source_assessment_id = NEW.source_assessment_id
                  AND j.approved_review_artifact_id = NEW.approved_review_artifact_id
                  AND j.approved_review_payload_sha256 = NEW.approved_review_payload_sha256
                  AND j.source_document_id = NEW.source_document_id
                  AND j.validated_process_id = NEW.validated_process_id
                  AND j.validated_process_fingerprint = NEW.validated_process_fingerprint
            ) THEN RAISE(ABORT, 'run source identity must match its journey') END;
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1 FROM preliminary_journey_events e
                WHERE e.event_id = NEW.route_choice_event_id
                  AND e.journey_id = NEW.journey_id
                  AND e.event_sequence = NEW.route_choice_event_sequence
                  AND e.event_type IN ('ROUTE_SELECTED', 'ROUTE_CHANGED')
                  AND json_extract(e.payload_json, '$.payload.journey') = 'EXPLORE_PROCESS'
                  AND NOT EXISTS (
                      SELECT 1 FROM preliminary_journey_events later
                      WHERE later.journey_id = NEW.journey_id
                        AND later.event_type IN ('ROUTE_SELECTED', 'ROUTE_CHANGED')
                        AND later.event_sequence > e.event_sequence
                  )
            ) THEN RAISE(ABORT, 'run must pin the latest Explore route-choice event') END;
            SELECT CASE WHEN NEW.retry_of_run_id = NEW.preliminary_run_id
                THEN RAISE(ABORT, 'a retry must use a new run ID') END;
            SELECT CASE WHEN NEW.retry_of_run_id IS NOT NULL AND NOT EXISTS (
                SELECT 1
                FROM preliminary_run_manifests predecessor
                JOIN preliminary_run_events terminal
                  ON terminal.preliminary_run_id = predecessor.preliminary_run_id
                 AND terminal.journey_id = predecessor.journey_id
                WHERE predecessor.preliminary_run_id = NEW.retry_of_run_id
                  AND predecessor.journey_id = NEW.journey_id
                  AND predecessor.request_token != NEW.request_token
                  AND terminal.event_type IN ('RUN_FAILED', 'RUN_ABANDONED')
            ) THEN RAISE(ABORT, 'retry predecessor must be failed or abandoned in the same journey') END;
            SELECT CASE WHEN
                json_extract(NEW.payload_json, '$.preliminary_run_id') != NEW.preliminary_run_id OR
                json_extract(NEW.payload_json, '$.journey_id') != NEW.journey_id OR
                json_extract(NEW.payload_json, '$.request_token') != NEW.request_token OR
                json_extract(NEW.payload_json, '$.route_choice_event_id') != NEW.route_choice_event_id OR
                json_extract(NEW.payload_json, '$.route_choice_event_sequence') != NEW.route_choice_event_sequence OR
                json_extract(NEW.payload_json, '$.rule_set.rule_set_fingerprint') != NEW.rule_set_fingerprint
            THEN RAISE(ABORT, 'run manifest columns do not match the immutable payload') END;
        END;

        CREATE TRIGGER validate_preliminary_run_event
        BEFORE INSERT ON preliminary_run_events
        BEGIN
            SELECT CASE WHEN NEW.event_sequence != COALESCE((
                SELECT MAX(event_sequence) + 1
                FROM preliminary_run_events
                WHERE preliminary_run_id = NEW.preliminary_run_id
            ), 1) THEN RAISE(ABORT, 'run event sequence must be gap-free and monotonic') END;
            SELECT CASE WHEN
                (NEW.event_type = 'RUN_STARTED' AND NEW.payload_schema_version != 'preliminary-run-started.v0.1') OR
                (NEW.event_type = 'RUN_COMPLETED' AND NEW.payload_schema_version != 'preliminary-run-completed.v0.1') OR
                (NEW.event_type = 'RUN_FAILED' AND NEW.payload_schema_version != 'preliminary-run-failed.v0.1') OR
                (NEW.event_type = 'RUN_ABANDONED' AND NEW.payload_schema_version != 'preliminary-run-abandoned.v0.1')
            THEN RAISE(ABORT, 'run event type and payload schema must match') END;
            SELECT CASE WHEN
                json_extract(NEW.payload_json, '$.run_event_id') != NEW.run_event_id OR
                json_extract(NEW.payload_json, '$.preliminary_run_id') != NEW.preliminary_run_id OR
                json_extract(NEW.payload_json, '$.journey_id') != NEW.journey_id OR
                json_extract(NEW.payload_json, '$.event_sequence') != NEW.event_sequence OR
                json_extract(NEW.payload_json, '$.event_type') != NEW.event_type OR
                json_extract(NEW.payload_json, '$.payload.schema_version') != NEW.payload_schema_version
            THEN RAISE(ABORT, 'run event columns do not match the immutable payload') END;
            SELECT CASE WHEN NEW.event_type = 'RUN_STARTED' AND NEW.event_sequence != 1
                THEN RAISE(ABORT, 'RUN_STARTED must be first') END;
            SELECT CASE WHEN NEW.event_type != 'RUN_STARTED' AND (
                NEW.event_sequence != 2 OR NOT EXISTS (
                    SELECT 1 FROM preliminary_run_events started
                    WHERE started.preliminary_run_id = NEW.preliminary_run_id
                      AND started.event_type = 'RUN_STARTED'
                )
            ) THEN RAISE(ABORT, 'a terminal event requires one prior RUN_STARTED event') END;
            SELECT CASE WHEN NEW.event_type = 'RUN_STARTED' AND EXISTS (
                SELECT 1 FROM preliminary_run_events started
                WHERE started.journey_id = NEW.journey_id
                  AND started.event_type = 'RUN_STARTED'
                  AND NOT EXISTS (
                      SELECT 1 FROM preliminary_run_events terminal
                      WHERE terminal.preliminary_run_id = started.preliminary_run_id
                        AND terminal.event_type IN ('RUN_COMPLETED', 'RUN_FAILED', 'RUN_ABANDONED')
                  )
            ) THEN RAISE(ABORT, 'only one non-terminal run is permitted per journey') END;
            SELECT CASE WHEN NEW.event_type IN ('RUN_FAILED', 'RUN_ABANDONED') AND EXISTS (
                SELECT 1 FROM preliminary_results r
                WHERE r.preliminary_run_id = NEW.preliminary_run_id
            ) THEN RAISE(ABORT, 'failed or abandoned runs cannot have results') END;
            SELECT CASE WHEN NEW.event_type = 'RUN_COMPLETED' AND NOT EXISTS (
                SELECT 1 FROM preliminary_results r
                WHERE r.preliminary_result_id = NEW.preliminary_result_id
                  AND r.preliminary_run_id = NEW.preliminary_run_id
                  AND r.journey_id = NEW.journey_id
                  AND r.completed_run_event_id = NEW.run_event_id
            ) THEN RAISE(ABORT, 'RUN_COMPLETED requires its immutable result') END;
        END;

        CREATE TRIGGER validate_preliminary_result
        BEFORE INSERT ON preliminary_results
        BEGIN
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1 FROM preliminary_run_manifests m
                WHERE m.preliminary_run_id = NEW.preliminary_run_id
                  AND m.journey_id = NEW.journey_id
                  AND m.source_assessment_id = NEW.source_assessment_id
                  AND m.approved_review_artifact_id = NEW.approved_review_artifact_id
                  AND m.approved_review_payload_sha256 = NEW.approved_review_payload_sha256
                  AND m.source_document_id = NEW.source_document_id
                  AND m.validated_process_id = NEW.validated_process_id
                  AND m.validated_process_fingerprint = NEW.validated_process_fingerprint
                  AND m.evaluator_id = NEW.evaluator_id
                  AND m.evaluator_version = NEW.evaluator_version
                  AND m.rule_set_id = NEW.rule_set_id
                  AND m.rule_set_version = NEW.rule_set_version
                  AND m.rule_set_fingerprint = NEW.rule_set_fingerprint
                  AND m.output_schema_version = NEW.output_schema_version
            ) THEN RAISE(ABORT, 'result identity must match its run manifest') END;
            SELECT CASE WHEN EXISTS (
                SELECT 1 FROM preliminary_run_events terminal
                WHERE terminal.preliminary_run_id = NEW.preliminary_run_id
                  AND terminal.event_type IN ('RUN_COMPLETED', 'RUN_FAILED', 'RUN_ABANDONED')
            ) THEN RAISE(ABORT, 'a result must be inserted atomically before completion') END;
            SELECT CASE WHEN
                json_extract(NEW.payload_json, '$.preliminary_result_id') != NEW.preliminary_result_id OR
                json_extract(NEW.payload_json, '$.preliminary_run_id') != NEW.preliminary_run_id OR
                json_extract(NEW.payload_json, '$.journey_id') != NEW.journey_id OR
                json_extract(NEW.payload_json, '$.completed_run_event_id') != NEW.completed_run_event_id OR
                json_extract(NEW.payload_json, '$.assessment.preliminary_assessment_id') != NEW.preliminary_run_id OR
                json_extract(NEW.payload_json, '$.rule_set.rule_set_fingerprint') != NEW.rule_set_fingerprint
            THEN RAISE(ABORT, 'result columns do not match the immutable payload') END;
        END;

        CREATE TRIGGER validate_preliminary_run_state_insert
        BEFORE INSERT ON preliminary_run_state_index
        BEGIN
            SELECT CASE WHEN
                (NEW.projected_status = 'STARTED' AND NOT EXISTS (
                    SELECT 1 FROM preliminary_run_events started
                    WHERE started.preliminary_run_id = NEW.preliminary_run_id
                      AND started.event_type = 'RUN_STARTED'
                      AND NOT EXISTS (
                          SELECT 1 FROM preliminary_run_events terminal
                          WHERE terminal.preliminary_run_id = NEW.preliminary_run_id
                            AND terminal.event_type IN ('RUN_COMPLETED', 'RUN_FAILED', 'RUN_ABANDONED')
                      )
                )) OR
                (NEW.projected_status != 'STARTED' AND NOT EXISTS (
                    SELECT 1 FROM preliminary_run_events terminal
                    WHERE terminal.run_event_id = NEW.terminal_event_id
                      AND terminal.preliminary_run_id = NEW.preliminary_run_id
                      AND terminal.event_type = 'RUN_' || NEW.projected_status
                ))
            THEN RAISE(ABORT, 'run-state projection must match append-only run events') END;
        END;

        CREATE TRIGGER validate_preliminary_run_state_update
        BEFORE UPDATE ON preliminary_run_state_index
        BEGIN
            SELECT CASE WHEN NEW.preliminary_run_id != OLD.preliminary_run_id OR NEW.journey_id != OLD.journey_id
                THEN RAISE(ABORT, 'run-state projection identity is immutable') END;
            SELECT CASE WHEN
                (NEW.projected_status = 'STARTED' AND NOT EXISTS (
                    SELECT 1 FROM preliminary_run_events started
                    WHERE started.preliminary_run_id = NEW.preliminary_run_id
                      AND started.event_type = 'RUN_STARTED'
                      AND NOT EXISTS (
                          SELECT 1 FROM preliminary_run_events terminal
                          WHERE terminal.preliminary_run_id = NEW.preliminary_run_id
                            AND terminal.event_type IN ('RUN_COMPLETED', 'RUN_FAILED', 'RUN_ABANDONED')
                      )
                )) OR
                (NEW.projected_status != 'STARTED' AND NOT EXISTS (
                    SELECT 1 FROM preliminary_run_events terminal
                    WHERE terminal.run_event_id = NEW.terminal_event_id
                      AND terminal.preliminary_run_id = NEW.preliminary_run_id
                      AND terminal.event_type = 'RUN_' || NEW.projected_status
                ))
            THEN RAISE(ABORT, 'run-state projection must match append-only run events') END;
        END;

        CREATE TRIGGER validate_preliminary_supersession
        BEFORE INSERT ON preliminary_result_supersessions
        BEGIN
            SELECT CASE WHEN EXISTS (
                WITH RECURSIVE successors(result_id) AS (
                    SELECT NEW.superseding_result_id
                    UNION
                    SELECT link.superseding_result_id
                    FROM preliminary_result_supersessions link
                    JOIN successors current
                      ON link.superseded_result_id = current.result_id
                )
                SELECT 1 FROM successors
                WHERE result_id = NEW.superseded_result_id
            ) THEN RAISE(ABORT, 'result supersession must be acyclic') END;
        END;

        CREATE TRIGGER validate_preliminary_formal_lifecycle
        BEFORE INSERT ON preliminary_formal_lifecycles
        BEGIN
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1 FROM preliminary_journeys j
                WHERE j.journey_id = NEW.journey_id
                  AND j.source_assessment_id = NEW.source_assessment_id
                  AND j.approved_review_artifact_id = NEW.approved_review_artifact_id
                  AND j.approved_review_payload_sha256 = NEW.approved_review_payload_sha256
                  AND j.source_document_id = NEW.source_document_id
                  AND j.validated_process_id = NEW.validated_process_id
                  AND j.validated_process_fingerprint = NEW.validated_process_fingerprint
            ) THEN RAISE(ABORT, 'formal lifecycle source identity must match its journey') END;
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1 FROM preliminary_journey_events e
                WHERE e.event_id = NEW.route_choice_event_id
                  AND e.journey_id = NEW.journey_id
                  AND e.event_sequence = NEW.route_choice_event_sequence
                  AND e.event_type IN ('ROUTE_SELECTED', 'ROUTE_CHANGED')
                  AND json_extract(e.payload_json, '$.payload.journey') = 'ORGANISATIONAL_ASSESSMENT'
                  AND NOT EXISTS (
                      SELECT 1 FROM preliminary_journey_events later
                      WHERE later.journey_id = NEW.journey_id
                        AND later.event_type IN ('ROUTE_SELECTED', 'ROUTE_CHANGED')
                        AND later.event_sequence > e.event_sequence
                  )
            ) THEN RAISE(ABORT, 'formal lifecycle must pin the latest organisational route-choice event') END;
        END;

        CREATE TRIGGER validate_preliminary_journey_event_reference
        BEFORE INSERT ON preliminary_journey_events
        BEGIN
            SELECT CASE WHEN NEW.event_type = 'RUN_LINKED' AND NOT EXISTS (
                SELECT 1 FROM preliminary_run_manifests m
                WHERE m.preliminary_run_id = json_extract(NEW.payload_json, '$.payload.preliminary_run_id')
                  AND m.journey_id = NEW.journey_id
                  AND m.route_choice_event_id = json_extract(NEW.payload_json, '$.payload.route_choice_event_id')
                  AND m.route_choice_event_sequence = json_extract(NEW.payload_json, '$.payload.route_choice_event_sequence')
            ) THEN RAISE(ABORT, 'RUN_LINKED must reference a run in the same journey') END;
            SELECT CASE WHEN NEW.event_type = 'RUN_RECOVERY_RECORDED' AND NOT EXISTS (
                SELECT 1 FROM preliminary_run_manifests retry
                WHERE retry.preliminary_run_id = json_extract(NEW.payload_json, '$.payload.retry_run_id')
                  AND retry.retry_of_run_id = json_extract(NEW.payload_json, '$.payload.abandoned_run_id')
                  AND retry.journey_id = NEW.journey_id
            ) THEN RAISE(ABORT, 'recovery event must reference retry lineage in the same journey') END;
            SELECT CASE WHEN NEW.event_type = 'RESULT_RECORDED' AND NOT EXISTS (
                SELECT 1 FROM preliminary_results r
                WHERE r.preliminary_result_id = json_extract(NEW.payload_json, '$.payload.preliminary_result_id')
                  AND r.preliminary_run_id = json_extract(NEW.payload_json, '$.payload.preliminary_run_id')
                  AND r.journey_id = NEW.journey_id
            ) THEN RAISE(ABORT, 'RESULT_RECORDED must reference a result in the same journey') END;
            SELECT CASE WHEN NEW.event_type = 'RESULT_SUPERSEDED' AND NOT EXISTS (
                SELECT 1 FROM preliminary_result_supersessions s
                WHERE s.superseded_result_id = json_extract(NEW.payload_json, '$.payload.superseded_result_id')
                  AND s.superseding_result_id = json_extract(NEW.payload_json, '$.payload.superseding_result_id')
                  AND s.journey_id = NEW.journey_id
            ) THEN RAISE(ABORT, 'RESULT_SUPERSEDED must reference a same-journey link') END;
            SELECT CASE WHEN NEW.event_type = 'FORMAL_LIFECYCLE_STARTED' AND NOT EXISTS (
                SELECT 1 FROM preliminary_formal_lifecycles f
                WHERE f.formal_lifecycle_id = json_extract(NEW.payload_json, '$.payload.formal_lifecycle_id')
                  AND f.journey_id = NEW.journey_id
            ) THEN RAISE(ABORT, 'formal-start event must reference its same-journey lifecycle') END;
        END;

        CREATE TRIGGER preliminary_journeys_immutable_update BEFORE UPDATE ON preliminary_journeys
        BEGIN SELECT RAISE(ABORT, 'preliminary journey is immutable'); END;
        CREATE TRIGGER preliminary_journeys_immutable_delete BEFORE DELETE ON preliminary_journeys
        BEGIN SELECT RAISE(ABORT, 'preliminary journey is immutable'); END;
        CREATE TRIGGER preliminary_journey_events_immutable_update BEFORE UPDATE ON preliminary_journey_events
        BEGIN SELECT RAISE(ABORT, 'preliminary journey event is immutable'); END;
        CREATE TRIGGER preliminary_journey_events_immutable_delete BEFORE DELETE ON preliminary_journey_events
        BEGIN SELECT RAISE(ABORT, 'preliminary journey event is immutable'); END;
        CREATE TRIGGER preliminary_run_manifests_immutable_update BEFORE UPDATE ON preliminary_run_manifests
        BEGIN SELECT RAISE(ABORT, 'preliminary run manifest is immutable'); END;
        CREATE TRIGGER preliminary_run_manifests_immutable_delete BEFORE DELETE ON preliminary_run_manifests
        BEGIN SELECT RAISE(ABORT, 'preliminary run manifest is immutable'); END;
        CREATE TRIGGER preliminary_run_events_immutable_update BEFORE UPDATE ON preliminary_run_events
        BEGIN SELECT RAISE(ABORT, 'preliminary run event is immutable'); END;
        CREATE TRIGGER preliminary_run_events_immutable_delete BEFORE DELETE ON preliminary_run_events
        BEGIN SELECT RAISE(ABORT, 'preliminary run event is immutable'); END;
        CREATE TRIGGER preliminary_results_immutable_update BEFORE UPDATE ON preliminary_results
        BEGIN SELECT RAISE(ABORT, 'preliminary result is immutable'); END;
        CREATE TRIGGER preliminary_results_immutable_delete BEFORE DELETE ON preliminary_results
        BEGIN SELECT RAISE(ABORT, 'preliminary result is immutable'); END;
        CREATE TRIGGER preliminary_supersessions_immutable_update BEFORE UPDATE ON preliminary_result_supersessions
        BEGIN SELECT RAISE(ABORT, 'preliminary supersession is immutable'); END;
        CREATE TRIGGER preliminary_supersessions_immutable_delete BEFORE DELETE ON preliminary_result_supersessions
        BEGIN SELECT RAISE(ABORT, 'preliminary supersession is immutable'); END;
        CREATE TRIGGER preliminary_formal_lifecycles_immutable_update BEFORE UPDATE ON preliminary_formal_lifecycles
        BEGIN SELECT RAISE(ABORT, 'preliminary formal lifecycle is immutable'); END;
        CREATE TRIGGER preliminary_formal_lifecycles_immutable_delete BEFORE DELETE ON preliminary_formal_lifecycles
        BEGIN SELECT RAISE(ABORT, 'preliminary formal lifecycle is immutable'); END;
        """,
    ),
    (
        2,
        r"""
        CREATE UNIQUE INDEX idx_preliminary_event_journey_identity
            ON preliminary_journey_events(event_id, journey_id);

        CREATE TABLE preliminary_route_requests (
            route_request_id TEXT PRIMARY KEY,
            journey_id TEXT NOT NULL REFERENCES preliminary_journeys(journey_id),
            schema_version TEXT NOT NULL CHECK (schema_version = 'preliminary-route-request.v0.1'),
            request_token TEXT NOT NULL CHECK (length(trim(request_token)) > 0),
            requested_route TEXT NOT NULL CHECK (requested_route IN (
                'EXPLORE_PROCESS', 'ORGANISATIONAL_ASSESSMENT'
            )),
            expected_latest_sequence INTEGER NOT NULL CHECK (expected_latest_sequence >= 1),
            event_appended INTEGER NOT NULL CHECK (event_appended IN (0, 1)),
            resulting_event_id TEXT,
            effective_route_event_id TEXT NOT NULL,
            effective_route_event_sequence INTEGER NOT NULL CHECK (effective_route_event_sequence >= 1),
            latest_sequence_after_request INTEGER NOT NULL CHECK (latest_sequence_after_request >= 1),
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
            UNIQUE (journey_id, request_token),
            FOREIGN KEY (resulting_event_id, journey_id)
                REFERENCES preliminary_journey_events(event_id, journey_id),
            FOREIGN KEY (
                effective_route_event_id,
                journey_id,
                effective_route_event_sequence
            ) REFERENCES preliminary_journey_events(
                event_id,
                journey_id,
                event_sequence
            ),
            CHECK (
                (event_appended = 1 AND resulting_event_id IS NOT NULL)
                OR
                (event_appended = 0 AND resulting_event_id IS NULL)
            ),
            CHECK (
                (event_appended = 1 AND latest_sequence_after_request = expected_latest_sequence + 1)
                OR
                (event_appended = 0 AND latest_sequence_after_request = expected_latest_sequence)
            )
        );

        CREATE TRIGGER validate_preliminary_route_request
        BEFORE INSERT ON preliminary_route_requests
        BEGIN
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1 FROM preliminary_journey_events effective
                WHERE effective.event_id = NEW.effective_route_event_id
                  AND effective.journey_id = NEW.journey_id
                  AND effective.event_sequence = NEW.effective_route_event_sequence
                  AND effective.event_type IN ('ROUTE_SELECTED', 'ROUTE_CHANGED')
                  AND json_extract(effective.payload_json, '$.payload.journey') = NEW.requested_route
                  AND NOT EXISTS (
                      SELECT 1 FROM preliminary_journey_events later
                      WHERE later.journey_id = NEW.journey_id
                        AND later.event_type IN ('ROUTE_SELECTED', 'ROUTE_CHANGED')
                        AND later.event_sequence > effective.event_sequence
                  )
            ) THEN RAISE(ABORT, 'route request must identify the latest route-choice event') END;
            SELECT CASE WHEN NEW.event_appended = 1 AND (
                NEW.resulting_event_id != NEW.effective_route_event_id OR
                NEW.effective_route_event_sequence != NEW.latest_sequence_after_request
            ) THEN RAISE(ABORT, 'appended route request must identify its effective event') END;
            SELECT CASE WHEN NEW.latest_sequence_after_request != (
                SELECT MAX(event_sequence)
                FROM preliminary_journey_events
                WHERE journey_id = NEW.journey_id
            ) THEN RAISE(ABORT, 'route request sequence must match journey history') END;
            SELECT CASE WHEN
                json_extract(NEW.payload_json, '$.route_request_id') != NEW.route_request_id OR
                json_extract(NEW.payload_json, '$.journey_id') != NEW.journey_id OR
                json_extract(NEW.payload_json, '$.schema_version') != NEW.schema_version OR
                json_extract(NEW.payload_json, '$.request_token') != NEW.request_token OR
                json_extract(NEW.payload_json, '$.requested_route') != NEW.requested_route OR
                json_extract(NEW.payload_json, '$.expected_latest_sequence') != NEW.expected_latest_sequence OR
                json_extract(NEW.payload_json, '$.event_appended') != NEW.event_appended OR
                json_extract(NEW.payload_json, '$.resulting_event_id') IS NOT NEW.resulting_event_id OR
                json_extract(NEW.payload_json, '$.effective_route_event_id') != NEW.effective_route_event_id OR
                json_extract(NEW.payload_json, '$.effective_route_event_sequence') != NEW.effective_route_event_sequence OR
                json_extract(NEW.payload_json, '$.latest_sequence_after_request') != NEW.latest_sequence_after_request
            THEN RAISE(ABORT, 'route request columns do not match the immutable payload') END;
        END;

        CREATE TRIGGER preliminary_route_requests_immutable_update
        BEFORE UPDATE ON preliminary_route_requests
        BEGIN SELECT RAISE(ABORT, 'preliminary route request is immutable'); END;
        CREATE TRIGGER preliminary_route_requests_immutable_delete
        BEFORE DELETE ON preliminary_route_requests
        BEGIN SELECT RAISE(ABORT, 'preliminary route request is immutable'); END;
        """,
    ),
    (
        3,
        r"""
        CREATE UNIQUE INDEX idx_preliminary_one_predecessor_per_result
            ON preliminary_result_supersessions(superseding_result_id);

        CREATE UNIQUE INDEX idx_preliminary_one_result_recorded_event
            ON preliminary_journey_events(
                journey_id,
                json_extract(payload_json, '$.payload.preliminary_result_id')
            )
            WHERE event_type = 'RESULT_RECORDED';

        CREATE UNIQUE INDEX idx_preliminary_one_superseded_event
            ON preliminary_journey_events(
                journey_id,
                json_extract(payload_json, '$.payload.superseded_result_id')
            )
            WHERE event_type = 'RESULT_SUPERSEDED';

        CREATE TRIGGER validate_preliminary_supersession_v3
        BEFORE INSERT ON preliminary_result_supersessions
        BEGIN
            SELECT CASE WHEN
                json_extract(NEW.payload_json, '$.supersession_id') != NEW.supersession_id OR
                json_extract(NEW.payload_json, '$.journey_id') != NEW.journey_id OR
                json_extract(NEW.payload_json, '$.schema_version') != NEW.schema_version OR
                json_extract(NEW.payload_json, '$.superseded_result_id') != NEW.superseded_result_id OR
                json_extract(NEW.payload_json, '$.superseding_result_id') != NEW.superseding_result_id
            THEN RAISE(ABORT, 'supersession columns do not match the immutable payload') END;
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1
                FROM preliminary_results earlier
                JOIN preliminary_results later
                  ON later.preliminary_result_id = NEW.superseding_result_id
                 AND later.journey_id = NEW.journey_id
                JOIN preliminary_journey_events earlier_link
                  ON earlier_link.journey_id = earlier.journey_id
                 AND earlier_link.event_type = 'RUN_LINKED'
                 AND json_extract(
                     earlier_link.payload_json,
                     '$.payload.preliminary_run_id'
                 ) = earlier.preliminary_run_id
                JOIN preliminary_journey_events later_link
                  ON later_link.journey_id = later.journey_id
                 AND later_link.event_type = 'RUN_LINKED'
                 AND json_extract(
                     later_link.payload_json,
                     '$.payload.preliminary_run_id'
                 ) = later.preliminary_run_id
                WHERE earlier.preliminary_result_id = NEW.superseded_result_id
                  AND earlier.journey_id = NEW.journey_id
                  AND earlier_link.event_sequence < later_link.event_sequence
            ) THEN RAISE(ABORT, 'supersession must point from an earlier result to a later same-journey result') END;
        END;
        """,
    ),
    (
        4,
        r"""
        CREATE UNIQUE INDEX idx_preliminary_recovery_request_token
            ON preliminary_journey_events(
                journey_id,
                json_extract(payload_json, '$.payload.recovery_request_token')
            )
            WHERE event_type = 'RUN_RECOVERY_RECORDED'
              AND payload_schema_version = 'preliminary-run-recovery.v0.2';

        CREATE UNIQUE INDEX idx_preliminary_one_abandonment_recovery
            ON preliminary_journey_events(
                journey_id,
                json_extract(payload_json, '$.payload.predecessor_run_id')
            )
            WHERE event_type = 'RUN_RECOVERY_RECORDED'
              AND payload_schema_version = 'preliminary-run-recovery.v0.2'
              AND json_extract(payload_json, '$.payload.action') = 'ABANDON';

        CREATE UNIQUE INDEX idx_preliminary_one_retry_recovery
            ON preliminary_journey_events(
                journey_id,
                json_extract(payload_json, '$.payload.retry_run_id')
            )
            WHERE event_type = 'RUN_RECOVERY_RECORDED'
              AND payload_schema_version = 'preliminary-run-recovery.v0.2'
              AND json_extract(payload_json, '$.payload.action') = 'RETRY';

        DROP TRIGGER validate_preliminary_journey_event;
        CREATE TRIGGER validate_preliminary_journey_event
        BEFORE INSERT ON preliminary_journey_events
        BEGIN
            SELECT CASE WHEN NEW.event_sequence != COALESCE((
                SELECT MAX(event_sequence) + 1
                FROM preliminary_journey_events
                WHERE journey_id = NEW.journey_id
            ), 1) THEN RAISE(ABORT, 'journey event sequence must be gap-free and monotonic') END;
            SELECT CASE WHEN
                (NEW.event_type = 'JOURNEY_CREATED' AND NEW.payload_schema_version != 'journey-created.v0.1') OR
                (NEW.event_type IN ('ROUTE_SELECTED', 'ROUTE_CHANGED') AND NEW.payload_schema_version != 'journey-selection.v0.1') OR
                (NEW.event_type = 'RUN_LINKED' AND NEW.payload_schema_version != 'preliminary-run-link.v0.1') OR
                (NEW.event_type = 'RUN_RECOVERY_RECORDED' AND NEW.payload_schema_version NOT IN ('preliminary-run-recovery.v0.1', 'preliminary-run-recovery.v0.2')) OR
                (NEW.event_type = 'RESULT_RECORDED' AND NEW.payload_schema_version != 'preliminary-result-recorded.v0.1') OR
                (NEW.event_type = 'RESULT_SUPERSEDED' AND NEW.payload_schema_version != 'preliminary-result-supersession.v0.1') OR
                (NEW.event_type = 'FORMAL_LIFECYCLE_STARTED' AND NEW.payload_schema_version != 'formal-lifecycle-start.v0.1')
            THEN RAISE(ABORT, 'journey event type and payload schema must match') END;
            SELECT CASE WHEN
                json_extract(NEW.payload_json, '$.event_id') != NEW.event_id OR
                json_extract(NEW.payload_json, '$.journey_id') != NEW.journey_id OR
                json_extract(NEW.payload_json, '$.event_sequence') != NEW.event_sequence OR
                json_extract(NEW.payload_json, '$.event_type') != NEW.event_type OR
                json_extract(NEW.payload_json, '$.payload.schema_version') != NEW.payload_schema_version
            THEN RAISE(ABORT, 'journey event columns do not match the immutable payload') END;
            SELECT CASE WHEN NEW.event_type = 'JOURNEY_CREATED' AND NEW.event_sequence != 1
                THEN RAISE(ABORT, 'JOURNEY_CREATED must be first') END;
            SELECT CASE WHEN NEW.event_type != 'JOURNEY_CREATED' AND NEW.event_sequence = 1
                THEN RAISE(ABORT, 'the first journey event must be JOURNEY_CREATED') END;
        END;

        DROP TRIGGER validate_preliminary_journey_event_reference;
        CREATE TRIGGER validate_preliminary_journey_event_reference
        BEFORE INSERT ON preliminary_journey_events
        BEGIN
            SELECT CASE WHEN NEW.event_type = 'RUN_LINKED' AND NOT EXISTS (
                SELECT 1 FROM preliminary_run_manifests m
                WHERE m.preliminary_run_id = json_extract(NEW.payload_json, '$.payload.preliminary_run_id')
                  AND m.journey_id = NEW.journey_id
                  AND m.route_choice_event_id = json_extract(NEW.payload_json, '$.payload.route_choice_event_id')
                  AND m.route_choice_event_sequence = json_extract(NEW.payload_json, '$.payload.route_choice_event_sequence')
            ) THEN RAISE(ABORT, 'RUN_LINKED must reference a run in the same journey') END;
            SELECT CASE WHEN
                NEW.event_type = 'RUN_RECOVERY_RECORDED'
                AND NEW.payload_schema_version = 'preliminary-run-recovery.v0.1'
                AND NOT EXISTS (
                    SELECT 1 FROM preliminary_run_manifests retry
                    WHERE retry.preliminary_run_id = json_extract(NEW.payload_json, '$.payload.retry_run_id')
                      AND retry.retry_of_run_id = json_extract(NEW.payload_json, '$.payload.abandoned_run_id')
                      AND retry.journey_id = NEW.journey_id
                )
            THEN RAISE(ABORT, 'legacy recovery event must reference retry lineage in the same journey') END;
            SELECT CASE WHEN
                NEW.event_type = 'RUN_RECOVERY_RECORDED'
                AND NEW.payload_schema_version = 'preliminary-run-recovery.v0.2'
                AND json_extract(NEW.payload_json, '$.payload.action') = 'ABANDON'
                AND NOT EXISTS (
                    SELECT 1
                    FROM preliminary_run_manifests m
                    JOIN preliminary_run_events terminal
                      ON terminal.preliminary_run_id = m.preliminary_run_id
                     AND terminal.journey_id = m.journey_id
                    WHERE m.preliminary_run_id = json_extract(NEW.payload_json, '$.payload.predecessor_run_id')
                      AND m.journey_id = NEW.journey_id
                      AND terminal.run_event_id = json_extract(NEW.payload_json, '$.payload.terminal_run_event_id')
                      AND terminal.event_type = 'RUN_ABANDONED'
                      AND json_extract(NEW.payload_json, '$.payload.retry_run_id') IS NULL
                )
            THEN RAISE(ABORT, 'abandonment recovery must reference its abandoned same-journey run') END;
            SELECT CASE WHEN
                NEW.event_type = 'RUN_RECOVERY_RECORDED'
                AND NEW.payload_schema_version = 'preliminary-run-recovery.v0.2'
                AND json_extract(NEW.payload_json, '$.payload.action') = 'RETRY'
                AND NOT EXISTS (
                    SELECT 1 FROM preliminary_run_manifests retry
                    WHERE retry.preliminary_run_id = json_extract(NEW.payload_json, '$.payload.retry_run_id')
                      AND retry.retry_of_run_id = json_extract(NEW.payload_json, '$.payload.predecessor_run_id')
                      AND retry.request_token = json_extract(NEW.payload_json, '$.payload.recovery_request_token')
                      AND retry.journey_id = NEW.journey_id
                      AND json_extract(NEW.payload_json, '$.payload.terminal_run_event_id') IS NULL
                )
            THEN RAISE(ABORT, 'retry recovery must reference its same-journey retry manifest') END;
            SELECT CASE WHEN
                NEW.event_type = 'RUN_RECOVERY_RECORDED'
                AND NEW.payload_schema_version = 'preliminary-run-recovery.v0.2'
                AND (
                    json_extract(NEW.payload_json, '$.payload.action') IS NULL
                    OR json_extract(NEW.payload_json, '$.payload.action') NOT IN ('ABANDON', 'RETRY')
                )
            THEN RAISE(ABORT, 'recovery action is unsupported') END;
            SELECT CASE WHEN NEW.event_type = 'RESULT_RECORDED' AND NOT EXISTS (
                SELECT 1 FROM preliminary_results r
                WHERE r.preliminary_result_id = json_extract(NEW.payload_json, '$.payload.preliminary_result_id')
                  AND r.preliminary_run_id = json_extract(NEW.payload_json, '$.payload.preliminary_run_id')
                  AND r.journey_id = NEW.journey_id
            ) THEN RAISE(ABORT, 'RESULT_RECORDED must reference a result in the same journey') END;
            SELECT CASE WHEN NEW.event_type = 'RESULT_SUPERSEDED' AND NOT EXISTS (
                SELECT 1 FROM preliminary_result_supersessions s
                WHERE s.superseded_result_id = json_extract(NEW.payload_json, '$.payload.superseded_result_id')
                  AND s.superseding_result_id = json_extract(NEW.payload_json, '$.payload.superseding_result_id')
                  AND s.journey_id = NEW.journey_id
            ) THEN RAISE(ABORT, 'RESULT_SUPERSEDED must reference a same-journey link') END;
            SELECT CASE WHEN NEW.event_type = 'FORMAL_LIFECYCLE_STARTED' AND NOT EXISTS (
                SELECT 1 FROM preliminary_formal_lifecycles f
                WHERE f.formal_lifecycle_id = json_extract(NEW.payload_json, '$.payload.formal_lifecycle_id')
                  AND f.journey_id = NEW.journey_id
            ) THEN RAISE(ABORT, 'formal-start event must reference its same-journey lifecycle') END;
        END;
        """,
    ),
    (
        5,
        r"""
        CREATE UNIQUE INDEX idx_preliminary_formal_lifecycle_journey_identity
            ON preliminary_formal_lifecycles(formal_lifecycle_id, journey_id);

        CREATE UNIQUE INDEX idx_preliminary_one_formal_start_event
            ON preliminary_journey_events(journey_id)
            WHERE event_type = 'FORMAL_LIFECYCLE_STARTED';

        CREATE TRIGGER validate_preliminary_formal_lifecycle_v5
        BEFORE INSERT ON preliminary_formal_lifecycles
        BEGIN
            SELECT CASE WHEN
                json_extract(NEW.payload_json, '$.schema_version') != NEW.schema_version OR
                json_extract(NEW.payload_json, '$.formal_lifecycle_id') != NEW.formal_lifecycle_id OR
                json_extract(NEW.payload_json, '$.journey_id') != NEW.journey_id OR
                json_extract(NEW.payload_json, '$.source.source_assessment_id') != NEW.source_assessment_id OR
                json_extract(NEW.payload_json, '$.source.approved_review_artifact_id') != NEW.approved_review_artifact_id OR
                json_extract(NEW.payload_json, '$.source.approved_review_payload_sha256') != NEW.approved_review_payload_sha256 OR
                json_extract(NEW.payload_json, '$.source.source_document_id') != NEW.source_document_id OR
                json_extract(NEW.payload_json, '$.source.validated_process_id') != NEW.validated_process_id OR
                json_extract(NEW.payload_json, '$.source.validated_process_fingerprint') != NEW.validated_process_fingerprint OR
                json_extract(NEW.payload_json, '$.route_choice_event_id') != NEW.route_choice_event_id OR
                json_extract(NEW.payload_json, '$.route_choice_event_sequence') != NEW.route_choice_event_sequence OR
                json_extract(NEW.payload_json, '$.status') != NEW.status OR
                json_extract(NEW.payload_json, '$.preliminary_result_id') IS NOT NEW.preliminary_result_id OR
                json_extract(NEW.payload_json, '$.preliminary_result_use') IS NOT NEW.preliminary_result_use
            THEN RAISE(ABORT, 'formal lifecycle columns do not match the immutable payload') END;
            SELECT CASE WHEN NEW.preliminary_result_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM preliminary_results result
                WHERE result.preliminary_result_id = NEW.preliminary_result_id
                  AND result.journey_id = NEW.journey_id
                  AND result.source_assessment_id = NEW.source_assessment_id
                  AND result.approved_review_artifact_id = NEW.approved_review_artifact_id
                  AND result.approved_review_payload_sha256 = NEW.approved_review_payload_sha256
                  AND result.source_document_id = NEW.source_document_id
                  AND result.validated_process_id = NEW.validated_process_id
                  AND result.validated_process_fingerprint = NEW.validated_process_fingerprint
            ) THEN RAISE(ABORT, 'formal context must reference a valid same-source Preliminary result') END;
        END;

        CREATE TABLE preliminary_formal_start_requests (
            formal_start_request_id TEXT PRIMARY KEY,
            journey_id TEXT NOT NULL REFERENCES preliminary_journeys(journey_id),
            schema_version TEXT NOT NULL CHECK (
                schema_version = 'preliminary-formal-start-request.v0.1'
            ),
            request_token TEXT NOT NULL CHECK (length(trim(request_token)) > 0),
            formal_lifecycle_id TEXT NOT NULL,
            route_choice_event_id TEXT NOT NULL,
            route_choice_event_sequence INTEGER NOT NULL CHECK (
                route_choice_event_sequence >= 1
            ),
            preliminary_result_id TEXT,
            preliminary_result_use TEXT,
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
            UNIQUE (journey_id),
            UNIQUE (journey_id, request_token),
            UNIQUE (formal_lifecycle_id),
            FOREIGN KEY (formal_lifecycle_id, journey_id)
                REFERENCES preliminary_formal_lifecycles(
                    formal_lifecycle_id, journey_id
                ),
            FOREIGN KEY (
                route_choice_event_id,
                journey_id,
                route_choice_event_sequence
            ) REFERENCES preliminary_journey_events(
                event_id,
                journey_id,
                event_sequence
            ),
            FOREIGN KEY (preliminary_result_id, journey_id)
                REFERENCES preliminary_results(preliminary_result_id, journey_id),
            CHECK (
                (preliminary_result_id IS NULL AND preliminary_result_use IS NULL)
                OR
                (preliminary_result_id IS NOT NULL AND preliminary_result_use = 'CONTEXT_ONLY_NOT_FORMAL_EVIDENCE')
            )
        );

        CREATE TRIGGER validate_preliminary_formal_start_request
        BEFORE INSERT ON preliminary_formal_start_requests
        BEGIN
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1 FROM preliminary_formal_lifecycles lifecycle
                WHERE lifecycle.formal_lifecycle_id = NEW.formal_lifecycle_id
                  AND lifecycle.journey_id = NEW.journey_id
                  AND lifecycle.route_choice_event_id = NEW.route_choice_event_id
                  AND lifecycle.route_choice_event_sequence = NEW.route_choice_event_sequence
                  AND lifecycle.preliminary_result_id IS NEW.preliminary_result_id
                  AND lifecycle.preliminary_result_use IS NEW.preliminary_result_use
            ) THEN RAISE(ABORT, 'formal-start request must identify its immutable lifecycle') END;
            SELECT CASE WHEN
                json_extract(NEW.payload_json, '$.schema_version') != NEW.schema_version OR
                json_extract(NEW.payload_json, '$.formal_start_request_id') != NEW.formal_start_request_id OR
                json_extract(NEW.payload_json, '$.journey_id') != NEW.journey_id OR
                json_extract(NEW.payload_json, '$.request_token') != NEW.request_token OR
                json_extract(NEW.payload_json, '$.formal_lifecycle_id') != NEW.formal_lifecycle_id OR
                json_extract(NEW.payload_json, '$.route_choice_event_id') != NEW.route_choice_event_id OR
                json_extract(NEW.payload_json, '$.route_choice_event_sequence') != NEW.route_choice_event_sequence OR
                json_extract(NEW.payload_json, '$.preliminary_result_id') IS NOT NEW.preliminary_result_id OR
                json_extract(NEW.payload_json, '$.preliminary_result_use') IS NOT NEW.preliminary_result_use
            THEN RAISE(ABORT, 'formal-start request columns do not match the immutable payload') END;
        END;

        CREATE TRIGGER validate_preliminary_formal_start_event_v5
        BEFORE INSERT ON preliminary_journey_events
        WHEN NEW.event_type = 'FORMAL_LIFECYCLE_STARTED'
        BEGIN
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1
                FROM preliminary_formal_lifecycles lifecycle
                JOIN preliminary_formal_start_requests request
                  ON request.formal_lifecycle_id = lifecycle.formal_lifecycle_id
                 AND request.journey_id = lifecycle.journey_id
                WHERE lifecycle.formal_lifecycle_id = json_extract(
                    NEW.payload_json, '$.payload.formal_lifecycle_id'
                )
                  AND lifecycle.journey_id = NEW.journey_id
                  AND lifecycle.route_choice_event_id = json_extract(
                      NEW.payload_json, '$.payload.route_choice_event_id'
                  )
                  AND lifecycle.route_choice_event_sequence = json_extract(
                      NEW.payload_json, '$.payload.route_choice_event_sequence'
                  )
            ) THEN RAISE(ABORT, 'formal-start event requires its immutable request and lifecycle') END;
        END;

        CREATE TRIGGER preliminary_formal_start_requests_immutable_update
        BEFORE UPDATE ON preliminary_formal_start_requests
        BEGIN SELECT RAISE(ABORT, 'preliminary formal-start request is immutable'); END;

        CREATE TRIGGER preliminary_formal_start_requests_immutable_delete
        BEFORE DELETE ON preliminary_formal_start_requests
        BEGIN SELECT RAISE(ABORT, 'preliminary formal-start request is immutable'); END;
        """,
    ),
    (
        6,
        r"""
        CREATE TABLE preliminary_run_manifests_v0_2 (
            preliminary_run_id TEXT PRIMARY KEY,
            journey_id TEXT NOT NULL REFERENCES preliminary_journeys(journey_id),
            schema_version TEXT NOT NULL CHECK (schema_version = 'preliminary-run-manifest.v0.1'),
            store_id TEXT NOT NULL CHECK (store_id = 'preliminary-journey-store.v0.1'),
            request_token TEXT NOT NULL CHECK (length(trim(request_token)) > 0),
            retry_of_run_id TEXT,
            route_choice_event_id TEXT NOT NULL,
            route_choice_event_sequence INTEGER NOT NULL CHECK (route_choice_event_sequence >= 1),
            source_assessment_id TEXT NOT NULL,
            approved_review_artifact_id TEXT NOT NULL,
            approved_review_payload_sha256 TEXT NOT NULL CHECK (length(approved_review_payload_sha256) = 64),
            source_document_id TEXT NOT NULL,
            validated_process_id TEXT NOT NULL,
            validated_process_fingerprint TEXT NOT NULL CHECK (length(validated_process_fingerprint) = 64),
            evaluator_id TEXT NOT NULL CHECK (evaluator_id = 'preliminary-evaluator.v0.2'),
            evaluator_version TEXT NOT NULL CHECK (evaluator_version = '0.2.0'),
            rule_set_id TEXT NOT NULL CHECK (rule_set_id = 'preliminary-evaluator-rules.v0.2'),
            rule_set_version TEXT NOT NULL CHECK (rule_set_version = '0.2.0'),
            rule_set_fingerprint TEXT NOT NULL CHECK (rule_set_fingerprint = '1c06b6a9ce1fe9ee3f68c9b16a452ca2c283e3423a39ae6ef43bd5ccecb855c6'),
            output_schema_version TEXT NOT NULL CHECK (output_schema_version = 'preliminary-assessment.v0.2'),
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
            UNIQUE (journey_id, request_token),
            UNIQUE (preliminary_run_id, journey_id),
            FOREIGN KEY (retry_of_run_id, journey_id)
                REFERENCES preliminary_run_manifests_v0_2(preliminary_run_id, journey_id),
            FOREIGN KEY (route_choice_event_id, journey_id, route_choice_event_sequence)
                REFERENCES preliminary_journey_events(event_id, journey_id, event_sequence)
        );

        CREATE TABLE preliminary_run_events_v0_2 (
            run_event_id TEXT PRIMARY KEY,
            preliminary_run_id TEXT NOT NULL,
            journey_id TEXT NOT NULL,
            event_sequence INTEGER NOT NULL CHECK (event_sequence IN (1, 2)),
            schema_version TEXT NOT NULL CHECK (schema_version = 'preliminary-run-event.v0.1'),
            event_type TEXT NOT NULL CHECK (event_type IN ('RUN_STARTED', 'RUN_COMPLETED', 'RUN_FAILED', 'RUN_ABANDONED')),
            payload_schema_version TEXT NOT NULL,
            preliminary_result_id TEXT,
            occurred_at TEXT NOT NULL,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
            UNIQUE (preliminary_run_id, event_sequence),
            UNIQUE (run_event_id, preliminary_run_id, journey_id),
            FOREIGN KEY (preliminary_run_id, journey_id)
                REFERENCES preliminary_run_manifests_v0_2(preliminary_run_id, journey_id),
            FOREIGN KEY (preliminary_result_id, preliminary_run_id, journey_id)
                REFERENCES preliminary_results_v0_2(preliminary_result_id, preliminary_run_id, journey_id)
                DEFERRABLE INITIALLY DEFERRED,
            CHECK ((event_type = 'RUN_COMPLETED' AND preliminary_result_id IS NOT NULL)
                OR (event_type != 'RUN_COMPLETED' AND preliminary_result_id IS NULL))
        );

        CREATE TABLE preliminary_results_v0_2 (
            preliminary_result_id TEXT PRIMARY KEY,
            preliminary_run_id TEXT NOT NULL,
            journey_id TEXT NOT NULL,
            completed_run_event_id TEXT NOT NULL,
            schema_version TEXT NOT NULL CHECK (schema_version = 'preliminary-result.v0.1'),
            source_assessment_id TEXT NOT NULL,
            approved_review_artifact_id TEXT NOT NULL,
            approved_review_payload_sha256 TEXT NOT NULL CHECK (length(approved_review_payload_sha256) = 64),
            source_document_id TEXT NOT NULL,
            validated_process_id TEXT NOT NULL,
            validated_process_fingerprint TEXT NOT NULL CHECK (length(validated_process_fingerprint) = 64),
            evaluator_id TEXT NOT NULL CHECK (evaluator_id = 'preliminary-evaluator.v0.2'),
            evaluator_version TEXT NOT NULL CHECK (evaluator_version = '0.2.0'),
            rule_set_id TEXT NOT NULL CHECK (rule_set_id = 'preliminary-evaluator-rules.v0.2'),
            rule_set_version TEXT NOT NULL CHECK (rule_set_version = '0.2.0'),
            rule_set_fingerprint TEXT NOT NULL CHECK (rule_set_fingerprint = '1c06b6a9ce1fe9ee3f68c9b16a452ca2c283e3423a39ae6ef43bd5ccecb855c6'),
            output_schema_version TEXT NOT NULL CHECK (output_schema_version = 'preliminary-assessment.v0.2'),
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
            UNIQUE (preliminary_run_id),
            UNIQUE (completed_run_event_id),
            UNIQUE (preliminary_result_id, journey_id),
            UNIQUE (preliminary_result_id, preliminary_run_id, journey_id),
            FOREIGN KEY (preliminary_run_id, journey_id)
                REFERENCES preliminary_run_manifests_v0_2(preliminary_run_id, journey_id),
            FOREIGN KEY (completed_run_event_id, preliminary_run_id, journey_id)
                REFERENCES preliminary_run_events_v0_2(run_event_id, preliminary_run_id, journey_id)
                DEFERRABLE INITIALLY DEFERRED
        );

        CREATE TABLE preliminary_run_state_index_v0_2 (
            preliminary_run_id TEXT PRIMARY KEY,
            journey_id TEXT NOT NULL,
            schema_version TEXT NOT NULL CHECK (schema_version = 'preliminary-run-state-projection.v0.1'),
            projected_status TEXT NOT NULL CHECK (projected_status IN ('STARTED', 'COMPLETED', 'FAILED', 'ABANDONED')),
            terminal_event_id TEXT,
            projected_at TEXT NOT NULL,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
            FOREIGN KEY (preliminary_run_id, journey_id)
                REFERENCES preliminary_run_manifests_v0_2(preliminary_run_id, journey_id),
            FOREIGN KEY (terminal_event_id, preliminary_run_id, journey_id)
                REFERENCES preliminary_run_events_v0_2(run_event_id, preliminary_run_id, journey_id),
            CHECK ((projected_status = 'STARTED' AND terminal_event_id IS NULL)
                OR (projected_status != 'STARTED' AND terminal_event_id IS NOT NULL))
        );
        CREATE UNIQUE INDEX idx_preliminary_v0_2_one_started_run_per_journey
            ON preliminary_run_state_index_v0_2(journey_id)
            WHERE projected_status = 'STARTED';

        CREATE TABLE preliminary_result_supersessions_v0_2 (
            supersession_id TEXT PRIMARY KEY,
            journey_id TEXT NOT NULL REFERENCES preliminary_journeys(journey_id),
            schema_version TEXT NOT NULL CHECK (schema_version = 'preliminary-result-supersession.v0.1'),
            superseded_result_id TEXT NOT NULL,
            superseding_result_id TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
            UNIQUE (superseded_result_id),
            FOREIGN KEY (superseded_result_id, journey_id)
                REFERENCES preliminary_results_v0_2(preliminary_result_id, journey_id),
            FOREIGN KEY (superseding_result_id, journey_id)
                REFERENCES preliminary_results_v0_2(preliminary_result_id, journey_id),
            CHECK (superseded_result_id != superseding_result_id)
        );

        CREATE VIEW preliminary_run_manifests_all AS
            SELECT * FROM preliminary_run_manifests
            UNION ALL SELECT * FROM preliminary_run_manifests_v0_2;
        CREATE VIEW preliminary_run_events_all AS
            SELECT * FROM preliminary_run_events
            UNION ALL SELECT * FROM preliminary_run_events_v0_2;
        CREATE VIEW preliminary_results_all AS
            SELECT * FROM preliminary_results
            UNION ALL SELECT * FROM preliminary_results_v0_2;
        CREATE VIEW preliminary_result_supersessions_all AS
            SELECT * FROM preliminary_result_supersessions
            UNION ALL SELECT * FROM preliminary_result_supersessions_v0_2;

        CREATE TRIGGER validate_preliminary_run_manifest_v0_2
        BEFORE INSERT ON preliminary_run_manifests_v0_2
        BEGIN
            SELECT CASE WHEN EXISTS (
                SELECT 1 FROM preliminary_run_manifests
                WHERE preliminary_run_id = NEW.preliminary_run_id
                   OR (journey_id = NEW.journey_id AND request_token = NEW.request_token)
            ) THEN RAISE(ABORT, 'v0.2 run identity or token conflicts with v0.1 history') END;
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1 FROM preliminary_journeys j
                WHERE j.journey_id = NEW.journey_id
                  AND j.source_assessment_id = NEW.source_assessment_id
                  AND j.approved_review_artifact_id = NEW.approved_review_artifact_id
                  AND j.approved_review_payload_sha256 = NEW.approved_review_payload_sha256
                  AND j.source_document_id = NEW.source_document_id
                  AND j.validated_process_id = NEW.validated_process_id
                  AND j.validated_process_fingerprint = NEW.validated_process_fingerprint
            ) THEN RAISE(ABORT, 'v0.2 run source identity must match its journey') END;
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1 FROM preliminary_journey_events e
                WHERE e.event_id = NEW.route_choice_event_id
                  AND e.journey_id = NEW.journey_id
                  AND e.event_sequence = NEW.route_choice_event_sequence
                  AND e.event_type IN ('ROUTE_SELECTED', 'ROUTE_CHANGED')
                  AND json_extract(e.payload_json, '$.payload.journey') = 'EXPLORE_PROCESS'
                  AND NOT EXISTS (
                      SELECT 1 FROM preliminary_journey_events later
                      WHERE later.journey_id = NEW.journey_id
                        AND later.event_type IN ('ROUTE_SELECTED', 'ROUTE_CHANGED')
                        AND later.event_sequence > e.event_sequence
                  )
            ) THEN RAISE(ABORT, 'v0.2 run must pin the latest Explore route-choice event') END;
            SELECT CASE WHEN NEW.retry_of_run_id = NEW.preliminary_run_id
                THEN RAISE(ABORT, 'a retry must use a new run ID') END;
            SELECT CASE WHEN NEW.retry_of_run_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM preliminary_run_manifests_v0_2 predecessor
                JOIN preliminary_run_events_v0_2 terminal
                  ON terminal.preliminary_run_id = predecessor.preliminary_run_id
                 AND terminal.journey_id = predecessor.journey_id
                WHERE predecessor.preliminary_run_id = NEW.retry_of_run_id
                  AND predecessor.journey_id = NEW.journey_id
                  AND predecessor.request_token != NEW.request_token
                  AND terminal.event_type IN ('RUN_FAILED', 'RUN_ABANDONED')
            ) THEN RAISE(ABORT, 'v0.2 retry predecessor must be same-version and retryable') END;
            SELECT CASE WHEN
                json_extract(NEW.payload_json, '$.preliminary_run_id') != NEW.preliminary_run_id OR
                json_extract(NEW.payload_json, '$.journey_id') != NEW.journey_id OR
                json_extract(NEW.payload_json, '$.request_token') != NEW.request_token OR
                json_extract(NEW.payload_json, '$.evaluator.evaluator_id') != NEW.evaluator_id OR
                json_extract(NEW.payload_json, '$.evaluator.evaluator_version') != NEW.evaluator_version OR
                json_extract(NEW.payload_json, '$.rule_set.rule_set_id') != NEW.rule_set_id OR
                json_extract(NEW.payload_json, '$.rule_set.rule_set_version') != NEW.rule_set_version OR
                json_extract(NEW.payload_json, '$.rule_set.rule_set_fingerprint') != NEW.rule_set_fingerprint OR
                json_extract(NEW.payload_json, '$.output_schema_version') != NEW.output_schema_version
            THEN RAISE(ABORT, 'v0.2 manifest columns do not match immutable payload') END;
        END;

        CREATE TRIGGER preliminary_run_manifests_cross_version_insert
        BEFORE INSERT ON preliminary_run_manifests
        BEGIN
            SELECT CASE WHEN EXISTS (
                SELECT 1 FROM preliminary_run_manifests_v0_2
                WHERE preliminary_run_id = NEW.preliminary_run_id
                   OR (journey_id = NEW.journey_id AND request_token = NEW.request_token)
            ) THEN RAISE(ABORT, 'v0.1 run identity or token conflicts with v0.2 history') END;
        END;

        CREATE TRIGGER validate_preliminary_run_event_v0_2
        BEFORE INSERT ON preliminary_run_events_v0_2
        BEGIN
            SELECT CASE WHEN EXISTS (
                SELECT 1 FROM preliminary_run_events WHERE run_event_id = NEW.run_event_id
            ) THEN RAISE(ABORT, 'v0.2 run-event identity conflicts with v0.1 history') END;
            SELECT CASE WHEN NEW.event_sequence != COALESCE((
                SELECT MAX(event_sequence) + 1 FROM preliminary_run_events_v0_2
                WHERE preliminary_run_id = NEW.preliminary_run_id
            ), 1) THEN RAISE(ABORT, 'v0.2 run event sequence must be gap-free') END;
            SELECT CASE WHEN
                (NEW.event_type = 'RUN_STARTED' AND NEW.payload_schema_version != 'preliminary-run-started.v0.1') OR
                (NEW.event_type = 'RUN_COMPLETED' AND NEW.payload_schema_version != 'preliminary-run-completed.v0.1') OR
                (NEW.event_type = 'RUN_FAILED' AND NEW.payload_schema_version != 'preliminary-run-failed.v0.1') OR
                (NEW.event_type = 'RUN_ABANDONED' AND NEW.payload_schema_version != 'preliminary-run-abandoned.v0.1')
            THEN RAISE(ABORT, 'v0.2 run event type and payload schema must match') END;
            SELECT CASE WHEN
                json_extract(NEW.payload_json, '$.run_event_id') != NEW.run_event_id OR
                json_extract(NEW.payload_json, '$.preliminary_run_id') != NEW.preliminary_run_id OR
                json_extract(NEW.payload_json, '$.journey_id') != NEW.journey_id OR
                json_extract(NEW.payload_json, '$.event_sequence') != NEW.event_sequence OR
                json_extract(NEW.payload_json, '$.event_type') != NEW.event_type
            THEN RAISE(ABORT, 'v0.2 run-event columns do not match immutable payload') END;
            SELECT CASE WHEN NEW.event_type = 'RUN_STARTED' AND EXISTS (
                SELECT 1 FROM preliminary_run_events_all started
                WHERE started.journey_id = NEW.journey_id AND started.event_type = 'RUN_STARTED'
                  AND NOT EXISTS (
                      SELECT 1 FROM preliminary_run_events_all terminal
                      WHERE terminal.preliminary_run_id = started.preliminary_run_id
                        AND terminal.event_type IN ('RUN_COMPLETED', 'RUN_FAILED', 'RUN_ABANDONED')
                  )
            ) THEN RAISE(ABORT, 'only one non-terminal run is permitted per journey') END;
            SELECT CASE WHEN NEW.event_type = 'RUN_COMPLETED' AND NOT EXISTS (
                SELECT 1 FROM preliminary_results_v0_2 r
                WHERE r.preliminary_result_id = NEW.preliminary_result_id
                  AND r.preliminary_run_id = NEW.preliminary_run_id
                  AND r.journey_id = NEW.journey_id
                  AND r.completed_run_event_id = NEW.run_event_id
            ) THEN RAISE(ABORT, 'v0.2 completion requires its immutable result') END;
        END;

        CREATE TRIGGER preliminary_run_events_cross_version_insert
        BEFORE INSERT ON preliminary_run_events
        BEGIN
            SELECT CASE WHEN EXISTS (
                SELECT 1 FROM preliminary_run_events_v0_2 WHERE run_event_id = NEW.run_event_id
            ) THEN RAISE(ABORT, 'v0.1 run-event identity conflicts with v0.2 history') END;
            SELECT CASE WHEN NEW.event_type = 'RUN_STARTED' AND EXISTS (
                SELECT 1 FROM preliminary_run_events_v0_2 started
                WHERE started.journey_id = NEW.journey_id AND started.event_type = 'RUN_STARTED'
                  AND NOT EXISTS (
                      SELECT 1 FROM preliminary_run_events_v0_2 terminal
                      WHERE terminal.preliminary_run_id = started.preliminary_run_id
                        AND terminal.event_type IN ('RUN_COMPLETED', 'RUN_FAILED', 'RUN_ABANDONED')
                  )
            ) THEN RAISE(ABORT, 'only one cross-version non-terminal run is permitted per journey') END;
        END;

        CREATE TRIGGER validate_preliminary_result_v0_2
        BEFORE INSERT ON preliminary_results_v0_2
        BEGIN
            SELECT CASE WHEN EXISTS (
                SELECT 1 FROM preliminary_results WHERE preliminary_result_id = NEW.preliminary_result_id
            ) THEN RAISE(ABORT, 'v0.2 result identity conflicts with v0.1 history') END;
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1 FROM preliminary_run_manifests_v0_2 m
                WHERE m.preliminary_run_id = NEW.preliminary_run_id
                  AND m.journey_id = NEW.journey_id
                  AND m.source_assessment_id = NEW.source_assessment_id
                  AND m.approved_review_artifact_id = NEW.approved_review_artifact_id
                  AND m.approved_review_payload_sha256 = NEW.approved_review_payload_sha256
                  AND m.source_document_id = NEW.source_document_id
                  AND m.validated_process_id = NEW.validated_process_id
                  AND m.validated_process_fingerprint = NEW.validated_process_fingerprint
                  AND m.evaluator_id = NEW.evaluator_id
                  AND m.evaluator_version = NEW.evaluator_version
                  AND m.rule_set_id = NEW.rule_set_id
                  AND m.rule_set_version = NEW.rule_set_version
                  AND m.rule_set_fingerprint = NEW.rule_set_fingerprint
                  AND m.output_schema_version = NEW.output_schema_version
            ) THEN RAISE(ABORT, 'v0.2 result identity must match its manifest') END;
            SELECT CASE WHEN
                json_extract(NEW.payload_json, '$.preliminary_result_id') != NEW.preliminary_result_id OR
                json_extract(NEW.payload_json, '$.preliminary_run_id') != NEW.preliminary_run_id OR
                json_extract(NEW.payload_json, '$.journey_id') != NEW.journey_id OR
                json_extract(NEW.payload_json, '$.completed_run_event_id') != NEW.completed_run_event_id OR
                json_extract(NEW.payload_json, '$.assessment.schema_version') != NEW.output_schema_version OR
                json_extract(NEW.payload_json, '$.assessment.evaluator_id') != NEW.evaluator_id OR
                json_extract(NEW.payload_json, '$.assessment.evaluator_version') != NEW.evaluator_version OR
                json_extract(NEW.payload_json, '$.assessment.rule_set_id') != NEW.rule_set_id OR
                json_extract(NEW.payload_json, '$.assessment.rule_set_version') != NEW.rule_set_version OR
                json_extract(NEW.payload_json, '$.assessment.rule_set_fingerprint') != NEW.rule_set_fingerprint
            THEN RAISE(ABORT, 'v0.2 result columns do not match immutable payload') END;
        END;

        CREATE TRIGGER preliminary_results_cross_version_insert
        BEFORE INSERT ON preliminary_results
        BEGIN
            SELECT CASE WHEN EXISTS (
                SELECT 1 FROM preliminary_results_v0_2 WHERE preliminary_result_id = NEW.preliminary_result_id
            ) THEN RAISE(ABORT, 'v0.1 result identity conflicts with v0.2 history') END;
        END;

        CREATE TRIGGER validate_preliminary_run_state_v0_2_insert
        BEFORE INSERT ON preliminary_run_state_index_v0_2
        BEGIN
            SELECT CASE WHEN
                (NEW.projected_status = 'STARTED' AND NOT EXISTS (
                    SELECT 1 FROM preliminary_run_events_v0_2 e
                    WHERE e.preliminary_run_id = NEW.preliminary_run_id AND e.event_type = 'RUN_STARTED'
                )) OR
                (NEW.projected_status != 'STARTED' AND NOT EXISTS (
                    SELECT 1 FROM preliminary_run_events_v0_2 e
                    WHERE e.run_event_id = NEW.terminal_event_id
                      AND e.preliminary_run_id = NEW.preliminary_run_id
                      AND e.event_type = 'RUN_' || NEW.projected_status
                ))
            THEN RAISE(ABORT, 'v0.2 projection must match run events') END;
        END;
        CREATE TRIGGER validate_preliminary_run_state_v0_2_update
        BEFORE UPDATE ON preliminary_run_state_index_v0_2
        BEGIN
            SELECT CASE WHEN NEW.preliminary_run_id != OLD.preliminary_run_id OR NEW.journey_id != OLD.journey_id
                THEN RAISE(ABORT, 'v0.2 projection identity is immutable') END;
            SELECT CASE WHEN NEW.projected_status = 'STARTED' OR NOT EXISTS (
                SELECT 1 FROM preliminary_run_events_v0_2 e
                WHERE e.run_event_id = NEW.terminal_event_id
                  AND e.preliminary_run_id = NEW.preliminary_run_id
                  AND e.event_type = 'RUN_' || NEW.projected_status
            ) THEN RAISE(ABORT, 'v0.2 projection transition must match run events') END;
        END;

        CREATE TRIGGER validate_preliminary_supersession_v0_2
        BEFORE INSERT ON preliminary_result_supersessions_v0_2
        BEGIN
            SELECT CASE WHEN EXISTS (
                SELECT 1 FROM preliminary_result_supersessions WHERE supersession_id = NEW.supersession_id
            ) THEN RAISE(ABORT, 'v0.2 supersession identity conflicts with v0.1 history') END;
        END;
        CREATE TRIGGER preliminary_result_supersessions_cross_version_insert
        BEFORE INSERT ON preliminary_result_supersessions
        BEGIN
            SELECT CASE WHEN EXISTS (
                SELECT 1 FROM preliminary_result_supersessions_v0_2
                WHERE supersession_id = NEW.supersession_id
            ) THEN RAISE(ABORT, 'v0.1 supersession identity conflicts with v0.2 history') END;
        END;

        DROP TRIGGER validate_preliminary_journey_event_reference;
        CREATE TRIGGER validate_preliminary_journey_event_reference
        BEFORE INSERT ON preliminary_journey_events
        BEGIN
            SELECT CASE WHEN NEW.event_type = 'RUN_LINKED' AND NOT EXISTS (
                SELECT 1 FROM preliminary_run_manifests_all m
                WHERE m.preliminary_run_id = json_extract(NEW.payload_json, '$.payload.preliminary_run_id')
                  AND m.journey_id = NEW.journey_id
                  AND m.route_choice_event_id = json_extract(NEW.payload_json, '$.payload.route_choice_event_id')
                  AND m.route_choice_event_sequence = json_extract(NEW.payload_json, '$.payload.route_choice_event_sequence')
            ) THEN RAISE(ABORT, 'RUN_LINKED must reference a run in the same journey') END;
            SELECT CASE WHEN NEW.event_type = 'RUN_RECOVERY_RECORDED'
                AND NEW.payload_schema_version = 'preliminary-run-recovery.v0.1'
                AND NOT EXISTS (
                    SELECT 1 FROM preliminary_run_manifests retry
                    WHERE retry.preliminary_run_id = json_extract(NEW.payload_json, '$.payload.retry_run_id')
                      AND retry.retry_of_run_id = json_extract(NEW.payload_json, '$.payload.abandoned_run_id')
                      AND retry.journey_id = NEW.journey_id
                ) THEN RAISE(ABORT, 'legacy recovery event must reference v0.1 retry lineage') END;
            SELECT CASE WHEN NEW.event_type = 'RUN_RECOVERY_RECORDED'
                AND NEW.payload_schema_version = 'preliminary-run-recovery.v0.2'
                AND json_extract(NEW.payload_json, '$.payload.action') = 'ABANDON'
                AND NOT EXISTS (
                    SELECT 1 FROM preliminary_run_manifests_all m
                    JOIN preliminary_run_events_all terminal
                      ON terminal.preliminary_run_id = m.preliminary_run_id
                     AND terminal.journey_id = m.journey_id
                    WHERE m.preliminary_run_id = json_extract(NEW.payload_json, '$.payload.predecessor_run_id')
                      AND m.journey_id = NEW.journey_id
                      AND terminal.run_event_id = json_extract(NEW.payload_json, '$.payload.terminal_run_event_id')
                      AND terminal.event_type = 'RUN_ABANDONED'
                      AND json_extract(NEW.payload_json, '$.payload.retry_run_id') IS NULL
                ) THEN RAISE(ABORT, 'abandonment recovery must reference its run') END;
            SELECT CASE WHEN NEW.event_type = 'RUN_RECOVERY_RECORDED'
                AND NEW.payload_schema_version = 'preliminary-run-recovery.v0.2'
                AND json_extract(NEW.payload_json, '$.payload.action') = 'RETRY'
                AND NOT EXISTS (
                    SELECT 1 FROM preliminary_run_manifests_all retry
                    WHERE retry.preliminary_run_id = json_extract(NEW.payload_json, '$.payload.retry_run_id')
                      AND retry.retry_of_run_id = json_extract(NEW.payload_json, '$.payload.predecessor_run_id')
                      AND retry.request_token = json_extract(NEW.payload_json, '$.payload.recovery_request_token')
                      AND retry.journey_id = NEW.journey_id
                      AND json_extract(NEW.payload_json, '$.payload.terminal_run_event_id') IS NULL
                ) THEN RAISE(ABORT, 'retry recovery must reference its manifest') END;
            SELECT CASE WHEN NEW.event_type = 'RUN_RECOVERY_RECORDED'
                AND NEW.payload_schema_version = 'preliminary-run-recovery.v0.2'
                AND json_extract(NEW.payload_json, '$.payload.action') NOT IN ('ABANDON', 'RETRY')
                THEN RAISE(ABORT, 'recovery action is unsupported') END;
            SELECT CASE WHEN NEW.event_type = 'RESULT_RECORDED' AND NOT EXISTS (
                SELECT 1 FROM preliminary_results_all r
                WHERE r.preliminary_result_id = json_extract(NEW.payload_json, '$.payload.preliminary_result_id')
                  AND r.preliminary_run_id = json_extract(NEW.payload_json, '$.payload.preliminary_run_id')
                  AND r.journey_id = NEW.journey_id
            ) THEN RAISE(ABORT, 'RESULT_RECORDED must reference a result') END;
            SELECT CASE WHEN NEW.event_type = 'RESULT_SUPERSEDED' AND NOT EXISTS (
                SELECT 1 FROM preliminary_result_supersessions_all s
                WHERE s.superseded_result_id = json_extract(NEW.payload_json, '$.payload.superseded_result_id')
                  AND s.superseding_result_id = json_extract(NEW.payload_json, '$.payload.superseding_result_id')
                  AND s.journey_id = NEW.journey_id
            ) THEN RAISE(ABORT, 'RESULT_SUPERSEDED must reference its link') END;
            SELECT CASE WHEN NEW.event_type = 'FORMAL_LIFECYCLE_STARTED' AND NOT EXISTS (
                SELECT 1 FROM preliminary_formal_lifecycles f
                WHERE f.formal_lifecycle_id = json_extract(NEW.payload_json, '$.payload.formal_lifecycle_id')
                  AND f.journey_id = NEW.journey_id
            ) THEN RAISE(ABORT, 'formal-start event must reference its lifecycle') END;
        END;

        CREATE TRIGGER preliminary_run_manifests_v0_2_immutable_update BEFORE UPDATE ON preliminary_run_manifests_v0_2
        BEGIN SELECT RAISE(ABORT, 'v0.2 run manifest is immutable'); END;
        CREATE TRIGGER preliminary_run_manifests_v0_2_immutable_delete BEFORE DELETE ON preliminary_run_manifests_v0_2
        BEGIN SELECT RAISE(ABORT, 'v0.2 run manifest is immutable'); END;
        CREATE TRIGGER preliminary_run_events_v0_2_immutable_update BEFORE UPDATE ON preliminary_run_events_v0_2
        BEGIN SELECT RAISE(ABORT, 'v0.2 run event is immutable'); END;
        CREATE TRIGGER preliminary_run_events_v0_2_immutable_delete BEFORE DELETE ON preliminary_run_events_v0_2
        BEGIN SELECT RAISE(ABORT, 'v0.2 run event is immutable'); END;
        CREATE TRIGGER preliminary_results_v0_2_immutable_update BEFORE UPDATE ON preliminary_results_v0_2
        BEGIN SELECT RAISE(ABORT, 'v0.2 result is immutable'); END;
        CREATE TRIGGER preliminary_results_v0_2_immutable_delete BEFORE DELETE ON preliminary_results_v0_2
        BEGIN SELECT RAISE(ABORT, 'v0.2 result is immutable'); END;
        CREATE TRIGGER preliminary_result_supersessions_v0_2_immutable_update BEFORE UPDATE ON preliminary_result_supersessions_v0_2
        BEGIN SELECT RAISE(ABORT, 'v0.2 supersession is immutable'); END;
        CREATE TRIGGER preliminary_result_supersessions_v0_2_immutable_delete BEFORE DELETE ON preliminary_result_supersessions_v0_2
        BEGIN SELECT RAISE(ABORT, 'v0.2 supersession is immutable'); END;
        """,
    ),
)


# Migration 7 is deliberately not part of PRELIMINARY_JOURNEY_STORE_MIGRATIONS.
# It is applied only by the explicitly constructed supporting-evidence repository.
SUPPORTING_EVIDENCE_MIGRATION: tuple[int, str] = (
    7,
    r"""
    CREATE TABLE preliminary_formal_evidence_lineages (
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
        approved_review_revision INTEGER NOT NULL
            CHECK (approved_review_revision >= 1),
        approved_review_payload_sha256 TEXT NOT NULL
            CHECK (length(approved_review_payload_sha256) = 64),
        source_document_id TEXT NOT NULL
            CHECK (source_document_id GLOB 'doc-[0-9a-f]*'
                   AND length(source_document_id) = 68),
        source_document_sha256 TEXT NOT NULL
            CHECK (length(source_document_sha256) = 64),
        validated_process_id TEXT NOT NULL CHECK (length(trim(validated_process_id)) > 0),
        validated_process_fingerprint TEXT NOT NULL
            CHECK (length(validated_process_fingerprint) = 64),
        UNIQUE (formal_lifecycle_id, journey_id),
        UNIQUE (formal_lifecycle_id, approved_review_artifact_id)
    );

    CREATE TABLE preliminary_supporting_source_blobs (
        source_blob_id TEXT PRIMARY KEY,
        schema_version TEXT NOT NULL CHECK (schema_version = 'supporting-source-blob.v0.1'),
        contract_family TEXT NOT NULL CHECK (contract_family = 'preliminary-formal-evidence.v0.1'),
        content_sha256 TEXT NOT NULL UNIQUE CHECK (length(content_sha256) = 64),
        byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
        state TEXT NOT NULL CHECK (state IN ('ACCEPTED', 'REJECTED')),
        rejection_code TEXT,
        payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
        payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
        UNIQUE (source_blob_id, content_sha256),
        CHECK (source_blob_id = 'blob-' || content_sha256),
        CHECK ((state = 'ACCEPTED' AND rejection_code IS NULL)
            OR (state = 'REJECTED' AND rejection_code IS NOT NULL))
    );

    CREATE TABLE preliminary_supporting_source_blob_bytes (
        source_blob_id TEXT PRIMARY KEY
            REFERENCES preliminary_supporting_source_blobs(source_blob_id),
        content_sha256 TEXT NOT NULL UNIQUE,
        byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
        content_bytes BLOB NOT NULL,
        FOREIGN KEY (source_blob_id, content_sha256)
            REFERENCES preliminary_supporting_source_blobs(source_blob_id, content_sha256),
        CHECK (length(content_bytes) = byte_size)
    );

    CREATE TABLE preliminary_supporting_documents (
        document_id TEXT PRIMARY KEY,
        formal_lifecycle_id TEXT NOT NULL
            REFERENCES preliminary_formal_evidence_lineages(formal_lifecycle_id),
        schema_version TEXT NOT NULL CHECK (schema_version = 'supporting-document.v0.1'),
        contract_family TEXT NOT NULL CHECK (contract_family = 'preliminary-formal-evidence.v0.1'),
        source_blob_id TEXT NOT NULL
            REFERENCES preliminary_supporting_source_blobs(source_blob_id),
        source_blob_sha256 TEXT NOT NULL CHECK (length(source_blob_sha256) = 64),
        byte_size INTEGER NOT NULL CHECK (byte_size >= 0 AND byte_size <= 10485760),
        initial_metadata_revision_id TEXT NOT NULL,
        superseded_document_id TEXT,
        payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
        payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
        UNIQUE (formal_lifecycle_id, document_id),
        UNIQUE (formal_lifecycle_id, superseded_document_id),
        FOREIGN KEY (formal_lifecycle_id, superseded_document_id)
            REFERENCES preliminary_supporting_documents(formal_lifecycle_id, document_id),
        FOREIGN KEY (formal_lifecycle_id, document_id, initial_metadata_revision_id)
            REFERENCES preliminary_supporting_document_metadata_revisions(
                formal_lifecycle_id, document_id, revision_id
            ) DEFERRABLE INITIALLY DEFERRED,
        CHECK (superseded_document_id IS NULL OR superseded_document_id != document_id)
    );

    CREATE TABLE preliminary_supporting_document_metadata_revisions (
        revision_id TEXT PRIMARY KEY,
        formal_lifecycle_id TEXT NOT NULL
            REFERENCES preliminary_formal_evidence_lineages(formal_lifecycle_id),
        document_id TEXT NOT NULL,
        schema_version TEXT NOT NULL
            CHECK (schema_version = 'supporting-document-metadata-revision.v0.1'),
        contract_family TEXT NOT NULL CHECK (contract_family = 'preliminary-formal-evidence.v0.1'),
        revision_number INTEGER NOT NULL CHECK (revision_number >= 1),
        prior_revision_id TEXT,
        request_token TEXT NOT NULL CHECK (length(trim(request_token)) > 0),
        payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
        payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
        UNIQUE (formal_lifecycle_id, document_id, revision_number),
        UNIQUE (formal_lifecycle_id, document_id, revision_id),
        FOREIGN KEY (formal_lifecycle_id, document_id)
            REFERENCES preliminary_supporting_documents(formal_lifecycle_id, document_id)
            DEFERRABLE INITIALLY DEFERRED,
        FOREIGN KEY (prior_revision_id)
            REFERENCES preliminary_supporting_document_metadata_revisions(revision_id),
        CHECK ((revision_number = 1 AND prior_revision_id IS NULL)
            OR (revision_number > 1 AND prior_revision_id IS NOT NULL))
    );

    CREATE TABLE preliminary_supporting_provider_consents (
        consent_record_id TEXT PRIMARY KEY,
        formal_lifecycle_id TEXT NOT NULL
            REFERENCES preliminary_formal_evidence_lineages(formal_lifecycle_id),
        document_id TEXT NOT NULL
            REFERENCES preliminary_supporting_documents(document_id),
        schema_version TEXT NOT NULL CHECK (schema_version = 'external-provider-consent.v0.1'),
        contract_family TEXT NOT NULL CHECK (contract_family = 'preliminary-formal-evidence.v0.1'),
        provider_id TEXT NOT NULL,
        explicit_consent INTEGER NOT NULL CHECK (explicit_consent IN (0, 1)),
        payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
        payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64)
    );

    CREATE TABLE preliminary_supporting_ingestion_attempts (
        attempt_id TEXT PRIMARY KEY,
        formal_lifecycle_id TEXT NOT NULL
            REFERENCES preliminary_formal_evidence_lineages(formal_lifecycle_id),
        document_id TEXT NOT NULL
            REFERENCES preliminary_supporting_documents(document_id),
        document_content_sha256 TEXT NOT NULL CHECK (length(document_content_sha256) = 64),
        schema_version TEXT NOT NULL
            CHECK (schema_version = 'supporting-document-ingestion-attempt.v0.1'),
        contract_family TEXT NOT NULL CHECK (contract_family = 'preliminary-formal-evidence.v0.1'),
        attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
        predecessor_attempt_id TEXT
            REFERENCES preliminary_supporting_ingestion_attempts(attempt_id),
        status TEXT NOT NULL CHECK (status IN (
            'STARTED', 'SUCCEEDED', 'PARTIAL', 'FAILED', 'INTERRUPTED', 'ABANDONED'
        )),
        request_token TEXT NOT NULL CHECK (length(trim(request_token)) > 0),
        payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
        payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
        UNIQUE (formal_lifecycle_id, document_id, attempt_number),
        CHECK ((attempt_number = 1 AND predecessor_attempt_id IS NULL)
            OR (attempt_number > 1 AND predecessor_attempt_id IS NOT NULL)),
        CHECK (predecessor_attempt_id IS NULL OR predecessor_attempt_id != attempt_id)
    );
    CREATE UNIQUE INDEX idx_supporting_one_started_ingestion
        ON preliminary_supporting_ingestion_attempts(formal_lifecycle_id, document_id)
        WHERE status = 'STARTED';

    CREATE TABLE preliminary_supporting_extraction_attempts (
        attempt_id TEXT PRIMARY KEY,
        formal_lifecycle_id TEXT NOT NULL
            REFERENCES preliminary_formal_evidence_lineages(formal_lifecycle_id),
        document_id TEXT NOT NULL
            REFERENCES preliminary_supporting_documents(document_id),
        document_content_sha256 TEXT NOT NULL CHECK (length(document_content_sha256) = 64),
        ingestion_attempt_id TEXT NOT NULL
            REFERENCES preliminary_supporting_ingestion_attempts(attempt_id),
        schema_version TEXT NOT NULL
            CHECK (schema_version = 'supporting-evidence-extraction-attempt.v0.1'),
        contract_family TEXT NOT NULL CHECK (contract_family = 'preliminary-formal-evidence.v0.1'),
        attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
        predecessor_attempt_id TEXT
            REFERENCES preliminary_supporting_extraction_attempts(attempt_id),
        status TEXT NOT NULL CHECK (status IN (
            'STARTED', 'SUCCEEDED', 'PARTIAL', 'FAILED', 'INTERRUPTED', 'ABANDONED'
        )),
        request_token TEXT NOT NULL CHECK (length(trim(request_token)) > 0),
        payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
        payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
        UNIQUE (formal_lifecycle_id, document_id, attempt_number),
        CHECK ((attempt_number = 1 AND predecessor_attempt_id IS NULL)
            OR (attempt_number > 1 AND predecessor_attempt_id IS NOT NULL)),
        CHECK (predecessor_attempt_id IS NULL OR predecessor_attempt_id != attempt_id)
    );
    CREATE UNIQUE INDEX idx_supporting_one_started_extraction
        ON preliminary_supporting_extraction_attempts(formal_lifecycle_id, document_id)
        WHERE status = 'STARTED';

    CREATE TABLE preliminary_supporting_evidence_proposals (
        proposal_id TEXT PRIMARY KEY,
        formal_lifecycle_id TEXT NOT NULL
            REFERENCES preliminary_formal_evidence_lineages(formal_lifecycle_id),
        extraction_attempt_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        document_content_sha256 TEXT NOT NULL CHECK (length(document_content_sha256) = 64),
        schema_version TEXT NOT NULL CHECK (schema_version = 'supporting-evidence-proposal.v0.1'),
        contract_family TEXT NOT NULL CHECK (contract_family = 'preliminary-formal-evidence.v0.1'),
        payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
        payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
        FOREIGN KEY (extraction_attempt_id)
            REFERENCES preliminary_supporting_extraction_attempts(attempt_id)
            DEFERRABLE INITIALLY DEFERRED
    );

    CREATE TABLE preliminary_supporting_evidence_review_revisions (
        revision_id TEXT PRIMARY KEY,
        formal_lifecycle_id TEXT NOT NULL
            REFERENCES preliminary_formal_evidence_lineages(formal_lifecycle_id),
        proposal_id TEXT NOT NULL
            REFERENCES preliminary_supporting_evidence_proposals(proposal_id),
        schema_version TEXT NOT NULL
            CHECK (schema_version = 'supporting-evidence-review-revision.v0.1'),
        contract_family TEXT NOT NULL CHECK (contract_family = 'preliminary-formal-evidence.v0.1'),
        revision_number INTEGER NOT NULL CHECK (revision_number >= 1),
        prior_revision_id TEXT
            REFERENCES preliminary_supporting_evidence_review_revisions(revision_id),
        action TEXT NOT NULL CHECK (action IN ('ACCEPT', 'CORRECT', 'REJECT', 'MARK_UNRESOLVED')),
        approved_classification TEXT,
        request_token TEXT NOT NULL CHECK (length(trim(request_token)) > 0),
        payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
        payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
        UNIQUE (formal_lifecycle_id, proposal_id, revision_number),
        CHECK ((revision_number = 1 AND prior_revision_id IS NULL)
            OR (revision_number > 1 AND prior_revision_id IS NOT NULL)),
        CHECK ((action = 'REJECT' AND approved_classification IS NULL)
            OR (action != 'REJECT' AND approved_classification IS NOT NULL)),
        CHECK (prior_revision_id IS NULL OR prior_revision_id != revision_id)
    );

    CREATE TABLE preliminary_supporting_context_notes (
        context_note_id TEXT PRIMARY KEY,
        formal_lifecycle_id TEXT NOT NULL
            REFERENCES preliminary_formal_evidence_lineages(formal_lifecycle_id),
        schema_version TEXT NOT NULL CHECK (schema_version = 'context-note.v0.1'),
        contract_family TEXT NOT NULL CHECK (contract_family = 'preliminary-formal-evidence.v0.1'),
        request_token TEXT NOT NULL CHECK (length(trim(request_token)) > 0),
        payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
        payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64)
    );

    CREATE TABLE preliminary_supporting_formal_input_mappings (
        mapping_id TEXT PRIMARY KEY,
        formal_lifecycle_id TEXT NOT NULL
            REFERENCES preliminary_formal_evidence_lineages(formal_lifecycle_id),
        schema_version TEXT NOT NULL CHECK (schema_version = 'formal-input-mapping.v0.1'),
        contract_family TEXT NOT NULL CHECK (contract_family = 'preliminary-formal-evidence.v0.1'),
        activity_id TEXT NOT NULL,
        disposition TEXT NOT NULL CHECK (disposition IN ('MAPPED_FORMAL_INPUT', 'CONTEXT_ONLY')),
        request_token TEXT NOT NULL CHECK (length(trim(request_token)) > 0),
        payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
        payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64)
    );

    CREATE TABLE preliminary_supporting_formal_input_candidate_sets (
        candidate_set_id TEXT PRIMARY KEY,
        formal_lifecycle_id TEXT NOT NULL
            REFERENCES preliminary_formal_evidence_lineages(formal_lifecycle_id),
        schema_version TEXT NOT NULL CHECK (schema_version = 'formal-input-candidate-set.v0.1'),
        contract_family TEXT NOT NULL CHECK (contract_family = 'preliminary-formal-evidence.v0.1'),
        prior_candidate_set_id TEXT
            REFERENCES preliminary_supporting_formal_input_candidate_sets(candidate_set_id),
        request_token TEXT NOT NULL CHECK (length(trim(request_token)) > 0),
        payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
        payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
        CHECK (prior_candidate_set_id IS NULL OR prior_candidate_set_id != candidate_set_id)
    );

    CREATE TABLE preliminary_supporting_formal_evidence_readiness (
        readiness_id TEXT PRIMARY KEY,
        formal_lifecycle_id TEXT NOT NULL
            REFERENCES preliminary_formal_evidence_lineages(formal_lifecycle_id),
        candidate_set_id TEXT NOT NULL
            REFERENCES preliminary_supporting_formal_input_candidate_sets(candidate_set_id),
        schema_version TEXT NOT NULL CHECK (schema_version = 'formal-evidence-readiness.v0.1'),
        contract_family TEXT NOT NULL CHECK (contract_family = 'preliminary-formal-evidence.v0.1'),
        status TEXT NOT NULL CHECK (status IN ('NOT_READY', 'READY_TO_ATTEMPT')),
        payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
        payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64)
    );

    CREATE TABLE preliminary_supporting_formal_evidence_workflow_events (
        event_id TEXT PRIMARY KEY,
        formal_lifecycle_id TEXT NOT NULL
            REFERENCES preliminary_formal_evidence_lineages(formal_lifecycle_id),
        lifecycle_sequence INTEGER NOT NULL CHECK (lifecycle_sequence >= 1),
        prior_event_id TEXT
            REFERENCES preliminary_supporting_formal_evidence_workflow_events(event_id),
        schema_version TEXT NOT NULL
            CHECK (schema_version = 'formal-evidence-workflow-event.v0.1'),
        contract_family TEXT NOT NULL CHECK (contract_family = 'preliminary-formal-evidence.v0.1'),
        event_type TEXT NOT NULL,
        subject_id TEXT NOT NULL,
        request_token TEXT NOT NULL CHECK (length(trim(request_token)) > 0),
        payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
        payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
        UNIQUE (formal_lifecycle_id, lifecycle_sequence),
        CHECK ((lifecycle_sequence = 1 AND prior_event_id IS NULL)
            OR (lifecycle_sequence > 1 AND prior_event_id IS NOT NULL)),
        CHECK (prior_event_id IS NULL OR prior_event_id != event_id)
    );

    CREATE TABLE preliminary_supporting_operation_requests (
        request_token TEXT PRIMARY KEY CHECK (length(trim(request_token)) > 0),
        schema_version TEXT NOT NULL
            CHECK (schema_version = 'formal-evidence-operation-request.v0.1'),
        canonical_request_sha256 TEXT NOT NULL
            CHECK (length(canonical_request_sha256) = 64),
        operation_payload_sha256 TEXT NOT NULL
            CHECK (length(operation_payload_sha256) = 64),
        operation_type TEXT NOT NULL CHECK (operation_type IN (
            'STORE_SOURCE_BLOB', 'STORE_DOCUMENT', 'APPEND_METADATA_REVISION',
            'STORE_PROVIDER_CONSENT', 'APPEND_INGESTION_ATTEMPT',
            'STORE_EXTRACTION_BUNDLE', 'APPEND_REVIEW_REVISION',
            'APPEND_CONTEXT_NOTE', 'APPEND_FORMAL_MAPPING',
            'APPEND_CANDIDATE_SET', 'APPEND_READINESS', 'APPEND_WORKFLOW_EVENT'
        )),
        formal_lifecycle_id TEXT NOT NULL
            REFERENCES preliminary_formal_evidence_lineages(formal_lifecycle_id),
        target_identity TEXT NOT NULL,
        result_schema_version TEXT NOT NULL CHECK (result_schema_version IN (
            'supporting-source-blob.v0.1',
            'supporting-document.v0.1',
            'supporting-document-metadata-revision.v0.1',
            'supporting-document-ingestion-attempt.v0.1',
            'supporting-evidence-extraction-attempt.v0.1',
            'supporting-evidence-review-revision.v0.1',
            'formal-input-mapping.v0.1',
            'formal-input-candidate-set.v0.1',
            'formal-evidence-readiness.v0.1',
            'formal-evidence-workflow-event.v0.1',
            'external-provider-consent.v0.1',
            'context-note.v0.1'
        )),
        result_identity TEXT NOT NULL,
        result_payload_sha256 TEXT NOT NULL CHECK (length(result_payload_sha256) = 64),
        recorded_at TEXT NOT NULL
    );

    CREATE TRIGGER validate_formal_evidence_lineage
    BEFORE INSERT ON preliminary_formal_evidence_lineages
    BEGIN
        SELECT CASE WHEN NEW.source_document_id != 'doc-' || NEW.source_document_sha256
            THEN RAISE(ABORT, 'formal-evidence source document hash is invalid') END;
        SELECT CASE WHEN NOT EXISTS (
            SELECT 1
            FROM preliminary_formal_lifecycles lifecycle
            JOIN preliminary_journeys journey ON journey.journey_id = lifecycle.journey_id
            JOIN assessment_artifacts artifact
              ON artifact.artifact_id = lifecycle.approved_review_artifact_id
            WHERE lifecycle.formal_lifecycle_id = NEW.formal_lifecycle_id
              AND lifecycle.schema_version = NEW.formal_lifecycle_schema
              AND lifecycle.journey_id = NEW.journey_id
              AND lifecycle.source_assessment_id = NEW.source_assessment_id
              AND lifecycle.approved_review_artifact_id = NEW.approved_review_artifact_id
              AND lifecycle.approved_review_payload_sha256 = NEW.approved_review_payload_sha256
              AND lifecycle.source_document_id = NEW.source_document_id
              AND lifecycle.validated_process_id = NEW.validated_process_id
              AND lifecycle.validated_process_fingerprint = NEW.validated_process_fingerprint
              AND journey.approved_review_schema_version = NEW.approved_review_schema_version
              AND artifact.assessment_id = NEW.source_assessment_id
              AND artifact.artifact_schema_version = NEW.approved_review_schema_version
              AND artifact.artifact_revision = NEW.approved_review_revision
              AND artifact.payload_sha256 = NEW.approved_review_payload_sha256
        ) THEN RAISE(
            ABORT, 'formal-evidence lineage does not match persisted formal lifecycle'
        ) END;
    END;

    CREATE TRIGGER validate_supporting_blob_bytes
    BEFORE INSERT ON preliminary_supporting_source_blob_bytes
    BEGIN
        SELECT CASE WHEN NOT EXISTS (
            SELECT 1 FROM preliminary_supporting_source_blobs blob
            WHERE blob.source_blob_id = NEW.source_blob_id
              AND blob.content_sha256 = NEW.content_sha256
              AND blob.byte_size = NEW.byte_size
              AND blob.state = 'ACCEPTED'
        ) THEN RAISE(ABORT, 'source bytes require matching accepted blob metadata') END;
    END;

    CREATE TRIGGER validate_supporting_document
    BEFORE INSERT ON preliminary_supporting_documents
    BEGIN
        SELECT CASE WHEN NOT EXISTS (
            SELECT 1 FROM preliminary_supporting_source_blobs blob
            JOIN preliminary_supporting_source_blob_bytes bytes
              ON bytes.source_blob_id = blob.source_blob_id
            WHERE blob.source_blob_id = NEW.source_blob_id
              AND blob.content_sha256 = NEW.source_blob_sha256
              AND blob.byte_size = NEW.byte_size
              AND blob.state = 'ACCEPTED'
        ) THEN RAISE(ABORT, 'supporting document requires retained accepted source bytes') END;
        SELECT CASE WHEN NOT EXISTS (
            SELECT 1 FROM preliminary_supporting_document_metadata_revisions metadata
            WHERE metadata.revision_id = NEW.initial_metadata_revision_id
              AND metadata.formal_lifecycle_id = NEW.formal_lifecycle_id
              AND metadata.document_id = NEW.document_id
              AND metadata.revision_number = 1
        ) THEN RAISE(ABORT, 'supporting document requires its initial metadata revision') END;
        SELECT CASE WHEN NEW.superseded_document_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM preliminary_supporting_documents previous
            WHERE previous.document_id = NEW.superseded_document_id
              AND previous.formal_lifecycle_id = NEW.formal_lifecycle_id
        ) THEN RAISE(ABORT, 'document supersession must remain in one formal lifecycle') END;
        SELECT CASE WHEN NEW.superseded_document_id IS NOT NULL AND EXISTS (
            WITH RECURSIVE predecessors(document_id) AS (
                SELECT NEW.superseded_document_id
                UNION ALL
                SELECT current.superseded_document_id
                FROM preliminary_supporting_documents current
                JOIN predecessors prior ON current.document_id = prior.document_id
                WHERE current.superseded_document_id IS NOT NULL
            )
            SELECT 1 FROM predecessors WHERE document_id = NEW.document_id
        ) THEN RAISE(ABORT, 'document supersession must be acyclic') END;
        SELECT CASE WHEN (
            SELECT COUNT(*)
            FROM preliminary_supporting_documents current
            WHERE current.formal_lifecycle_id = NEW.formal_lifecycle_id
              AND NOT EXISTS (
                  SELECT 1 FROM preliminary_supporting_documents newer
                  WHERE newer.formal_lifecycle_id = current.formal_lifecycle_id
                    AND newer.superseded_document_id = current.document_id
              )
        ) + CASE WHEN NEW.superseded_document_id IS NULL THEN 1 ELSE 0 END > 20
        THEN RAISE(ABORT, 'formal lifecycle exceeds current supporting-document limit') END;
        SELECT CASE WHEN COALESCE((
            SELECT SUM(current.byte_size)
            FROM preliminary_supporting_documents current
            WHERE current.formal_lifecycle_id = NEW.formal_lifecycle_id
              AND NOT EXISTS (
                  SELECT 1 FROM preliminary_supporting_documents newer
                  WHERE newer.formal_lifecycle_id = current.formal_lifecycle_id
                    AND newer.superseded_document_id = current.document_id
              )
              AND current.document_id IS NOT NEW.superseded_document_id
        ), 0) + NEW.byte_size > 52428800
        THEN RAISE(ABORT, 'formal lifecycle exceeds current supporting-byte limit') END;
    END;

    CREATE TRIGGER validate_supporting_metadata_revision
    BEFORE INSERT ON preliminary_supporting_document_metadata_revisions
    WHEN NEW.revision_number > 1
    BEGIN
        SELECT CASE WHEN NOT EXISTS (
            SELECT 1 FROM preliminary_supporting_document_metadata_revisions prior
            WHERE prior.revision_id = NEW.prior_revision_id
              AND prior.formal_lifecycle_id = NEW.formal_lifecycle_id
              AND prior.document_id = NEW.document_id
              AND prior.revision_number = NEW.revision_number - 1
        ) THEN RAISE(ABORT, 'metadata revisions must be gap-free and predecessor-linked') END;
    END;

    CREATE TRIGGER validate_supporting_ingestion_retry
    BEFORE INSERT ON preliminary_supporting_ingestion_attempts
    WHEN NEW.attempt_number > 1
    BEGIN
        SELECT CASE WHEN NOT EXISTS (
            SELECT 1 FROM preliminary_supporting_ingestion_attempts prior
            WHERE prior.attempt_id = NEW.predecessor_attempt_id
              AND prior.formal_lifecycle_id = NEW.formal_lifecycle_id
              AND prior.document_id = NEW.document_id
              AND prior.attempt_number = NEW.attempt_number - 1
              AND prior.status != 'STARTED'
        ) THEN RAISE(ABORT, 'ingestion retries require the exact terminal predecessor') END;
    END;

    CREATE TRIGGER validate_supporting_extraction_retry
    BEFORE INSERT ON preliminary_supporting_extraction_attempts
    WHEN NEW.attempt_number > 1
    BEGIN
        SELECT CASE WHEN NOT EXISTS (
            SELECT 1 FROM preliminary_supporting_extraction_attempts prior
            WHERE prior.attempt_id = NEW.predecessor_attempt_id
              AND prior.formal_lifecycle_id = NEW.formal_lifecycle_id
              AND prior.document_id = NEW.document_id
              AND prior.attempt_number = NEW.attempt_number - 1
              AND prior.status != 'STARTED'
        ) THEN RAISE(ABORT, 'extraction retries require the exact terminal predecessor') END;
    END;

    CREATE TRIGGER validate_supporting_extraction_proposals
    BEFORE INSERT ON preliminary_supporting_extraction_attempts
    BEGIN
        SELECT CASE WHEN NEW.status NOT IN ('SUCCEEDED', 'PARTIAL')
          AND EXISTS (
              SELECT 1 FROM preliminary_supporting_evidence_proposals proposal
              WHERE proposal.extraction_attempt_id = NEW.attempt_id
          ) THEN RAISE(ABORT, 'failed extraction attempt cannot publish proposals') END;
        SELECT CASE WHEN NEW.status IN ('SUCCEEDED', 'PARTIAL') AND (
            SELECT COUNT(*) FROM preliminary_supporting_evidence_proposals proposal
            WHERE proposal.extraction_attempt_id = NEW.attempt_id
              AND proposal.formal_lifecycle_id = NEW.formal_lifecycle_id
              AND proposal.document_id = NEW.document_id
              AND proposal.document_content_sha256 = NEW.document_content_sha256
        ) != json_array_length(json_extract(NEW.payload_json, '$.proposal_ids'))
        THEN RAISE(ABORT, 'extraction proposal set must match its immutable attempt') END;
        SELECT CASE WHEN EXISTS (
            SELECT 1 FROM json_each(NEW.payload_json, '$.proposal_ids') expected
            WHERE NOT EXISTS (
                SELECT 1 FROM preliminary_supporting_evidence_proposals proposal
                WHERE proposal.proposal_id = expected.value
                  AND proposal.extraction_attempt_id = NEW.attempt_id
                  AND proposal.formal_lifecycle_id = NEW.formal_lifecycle_id
                  AND proposal.document_id = NEW.document_id
                  AND proposal.document_content_sha256 = NEW.document_content_sha256
            )
        ) THEN RAISE(ABORT, 'extraction attempt references an invalid proposal') END;
    END;

    CREATE TRIGGER validate_supporting_review_revision
    BEFORE INSERT ON preliminary_supporting_evidence_review_revisions
    BEGIN
        SELECT CASE WHEN NOT EXISTS (
            SELECT 1 FROM preliminary_supporting_evidence_proposals proposal
            WHERE proposal.proposal_id = NEW.proposal_id
              AND proposal.formal_lifecycle_id = NEW.formal_lifecycle_id
        ) THEN RAISE(ABORT, 'review revision must reference a same-lineage proposal') END;
        SELECT CASE WHEN NEW.revision_number > 1 AND NOT EXISTS (
            SELECT 1 FROM preliminary_supporting_evidence_review_revisions prior
            WHERE prior.revision_id = NEW.prior_revision_id
              AND prior.formal_lifecycle_id = NEW.formal_lifecycle_id
              AND prior.proposal_id = NEW.proposal_id
              AND prior.revision_number = NEW.revision_number - 1
        ) THEN RAISE(ABORT, 'review revisions must be gap-free and predecessor-linked') END;
    END;

    CREATE TRIGGER validate_supporting_candidate_predecessor
    BEFORE INSERT ON preliminary_supporting_formal_input_candidate_sets
    WHEN NEW.prior_candidate_set_id IS NOT NULL
    BEGIN
        SELECT CASE WHEN NOT EXISTS (
            SELECT 1 FROM preliminary_supporting_formal_input_candidate_sets prior
            WHERE prior.candidate_set_id = NEW.prior_candidate_set_id
              AND prior.formal_lifecycle_id = NEW.formal_lifecycle_id
        ) THEN RAISE(ABORT, 'candidate-set predecessor must share formal lineage') END;
    END;

    CREATE TRIGGER validate_supporting_readiness_candidate
    BEFORE INSERT ON preliminary_supporting_formal_evidence_readiness
    BEGIN
        SELECT CASE WHEN NOT EXISTS (
            SELECT 1 FROM preliminary_supporting_formal_input_candidate_sets candidate
            WHERE candidate.candidate_set_id = NEW.candidate_set_id
              AND candidate.formal_lifecycle_id = NEW.formal_lifecycle_id
              AND candidate.payload_json = json_extract(NEW.payload_json, '$.candidate_set')
        ) THEN RAISE(ABORT, 'readiness must retain its exact persisted candidate set') END;
    END;

    CREATE TRIGGER validate_supporting_workflow_event
    BEFORE INSERT ON preliminary_supporting_formal_evidence_workflow_events
    BEGIN
        SELECT CASE WHEN NEW.lifecycle_sequence > 1 AND NOT EXISTS (
            SELECT 1 FROM preliminary_supporting_formal_evidence_workflow_events prior
            WHERE prior.event_id = NEW.prior_event_id
              AND prior.formal_lifecycle_id = NEW.formal_lifecycle_id
              AND prior.lifecycle_sequence = NEW.lifecycle_sequence - 1
        ) THEN RAISE(ABORT, 'workflow events must be gap-free and predecessor-linked') END;
    END;

    CREATE TRIGGER preliminary_formal_evidence_lineages_immutable_update
        BEFORE UPDATE ON preliminary_formal_evidence_lineages
        BEGIN SELECT RAISE(ABORT, 'formal-evidence lineage is immutable'); END;
    CREATE TRIGGER preliminary_formal_evidence_lineages_immutable_delete
        BEFORE DELETE ON preliminary_formal_evidence_lineages
        BEGIN SELECT RAISE(ABORT, 'formal-evidence lineage is immutable'); END;
    CREATE TRIGGER preliminary_supporting_source_blobs_immutable_update
        BEFORE UPDATE ON preliminary_supporting_source_blobs
        BEGIN SELECT RAISE(ABORT, 'supporting source blob is immutable'); END;
    CREATE TRIGGER preliminary_supporting_source_blobs_immutable_delete
        BEFORE DELETE ON preliminary_supporting_source_blobs
        BEGIN SELECT RAISE(ABORT, 'supporting source blob is immutable'); END;
    CREATE TRIGGER preliminary_supporting_source_blob_bytes_immutable_update
        BEFORE UPDATE ON preliminary_supporting_source_blob_bytes
        BEGIN SELECT RAISE(ABORT, 'supporting source bytes are immutable'); END;
    CREATE TRIGGER preliminary_supporting_source_blob_bytes_immutable_delete
        BEFORE DELETE ON preliminary_supporting_source_blob_bytes
        BEGIN SELECT RAISE(ABORT, 'supporting source bytes are immutable'); END;
    CREATE TRIGGER preliminary_supporting_documents_immutable_update
        BEFORE UPDATE ON preliminary_supporting_documents
        BEGIN SELECT RAISE(ABORT, 'supporting document is immutable'); END;
    CREATE TRIGGER preliminary_supporting_documents_immutable_delete
        BEFORE DELETE ON preliminary_supporting_documents
        BEGIN SELECT RAISE(ABORT, 'supporting document is immutable'); END;
    CREATE TRIGGER preliminary_supporting_metadata_immutable_update
        BEFORE UPDATE ON preliminary_supporting_document_metadata_revisions
        BEGIN SELECT RAISE(ABORT, 'supporting metadata revision is immutable'); END;
    CREATE TRIGGER preliminary_supporting_metadata_immutable_delete
        BEFORE DELETE ON preliminary_supporting_document_metadata_revisions
        BEGIN SELECT RAISE(ABORT, 'supporting metadata revision is immutable'); END;
    CREATE TRIGGER preliminary_supporting_consents_immutable_update
        BEFORE UPDATE ON preliminary_supporting_provider_consents
        BEGIN SELECT RAISE(ABORT, 'supporting provider consent is immutable'); END;
    CREATE TRIGGER preliminary_supporting_consents_immutable_delete
        BEFORE DELETE ON preliminary_supporting_provider_consents
        BEGIN SELECT RAISE(ABORT, 'supporting provider consent is immutable'); END;
    CREATE TRIGGER preliminary_supporting_ingestion_immutable_update
        BEFORE UPDATE ON preliminary_supporting_ingestion_attempts
        BEGIN SELECT RAISE(ABORT, 'supporting ingestion attempt is immutable'); END;
    CREATE TRIGGER preliminary_supporting_ingestion_immutable_delete
        BEFORE DELETE ON preliminary_supporting_ingestion_attempts
        BEGIN SELECT RAISE(ABORT, 'supporting ingestion attempt is immutable'); END;
    CREATE TRIGGER preliminary_supporting_extraction_immutable_update
        BEFORE UPDATE ON preliminary_supporting_extraction_attempts
        BEGIN SELECT RAISE(ABORT, 'supporting extraction attempt is immutable'); END;
    CREATE TRIGGER preliminary_supporting_extraction_immutable_delete
        BEFORE DELETE ON preliminary_supporting_extraction_attempts
        BEGIN SELECT RAISE(ABORT, 'supporting extraction attempt is immutable'); END;
    CREATE TRIGGER preliminary_supporting_proposals_immutable_update
        BEFORE UPDATE ON preliminary_supporting_evidence_proposals
        BEGIN SELECT RAISE(ABORT, 'supporting evidence proposal is immutable'); END;
    CREATE TRIGGER preliminary_supporting_proposals_immutable_delete
        BEFORE DELETE ON preliminary_supporting_evidence_proposals
        BEGIN SELECT RAISE(ABORT, 'supporting evidence proposal is immutable'); END;
    CREATE TRIGGER preliminary_supporting_reviews_immutable_update
        BEFORE UPDATE ON preliminary_supporting_evidence_review_revisions
        BEGIN SELECT RAISE(ABORT, 'supporting evidence review is immutable'); END;
    CREATE TRIGGER preliminary_supporting_reviews_immutable_delete
        BEFORE DELETE ON preliminary_supporting_evidence_review_revisions
        BEGIN SELECT RAISE(ABORT, 'supporting evidence review is immutable'); END;
    CREATE TRIGGER preliminary_supporting_context_notes_immutable_update
        BEFORE UPDATE ON preliminary_supporting_context_notes
        BEGIN SELECT RAISE(ABORT, 'supporting context note is immutable'); END;
    CREATE TRIGGER preliminary_supporting_context_notes_immutable_delete
        BEFORE DELETE ON preliminary_supporting_context_notes
        BEGIN SELECT RAISE(ABORT, 'supporting context note is immutable'); END;
    CREATE TRIGGER preliminary_supporting_mappings_immutable_update
        BEFORE UPDATE ON preliminary_supporting_formal_input_mappings
        BEGIN SELECT RAISE(ABORT, 'supporting formal mapping is immutable'); END;
    CREATE TRIGGER preliminary_supporting_mappings_immutable_delete
        BEFORE DELETE ON preliminary_supporting_formal_input_mappings
        BEGIN SELECT RAISE(ABORT, 'supporting formal mapping is immutable'); END;
    CREATE TRIGGER preliminary_supporting_candidates_immutable_update
        BEFORE UPDATE ON preliminary_supporting_formal_input_candidate_sets
        BEGIN SELECT RAISE(ABORT, 'supporting candidate set is immutable'); END;
    CREATE TRIGGER preliminary_supporting_candidates_immutable_delete
        BEFORE DELETE ON preliminary_supporting_formal_input_candidate_sets
        BEGIN SELECT RAISE(ABORT, 'supporting candidate set is immutable'); END;
    CREATE TRIGGER preliminary_supporting_readiness_immutable_update
        BEFORE UPDATE ON preliminary_supporting_formal_evidence_readiness
        BEGIN SELECT RAISE(ABORT, 'supporting readiness is immutable'); END;
    CREATE TRIGGER preliminary_supporting_readiness_immutable_delete
        BEFORE DELETE ON preliminary_supporting_formal_evidence_readiness
        BEGIN SELECT RAISE(ABORT, 'supporting readiness is immutable'); END;
    CREATE TRIGGER preliminary_supporting_events_immutable_update
        BEFORE UPDATE ON preliminary_supporting_formal_evidence_workflow_events
        BEGIN SELECT RAISE(ABORT, 'supporting workflow event is immutable'); END;
    CREATE TRIGGER preliminary_supporting_events_immutable_delete
        BEFORE DELETE ON preliminary_supporting_formal_evidence_workflow_events
        BEGIN SELECT RAISE(ABORT, 'supporting workflow event is immutable'); END;
    CREATE TRIGGER preliminary_supporting_requests_immutable_update
        BEFORE UPDATE ON preliminary_supporting_operation_requests
        BEGIN SELECT RAISE(ABORT, 'supporting operation request is immutable'); END;
    CREATE TRIGGER preliminary_supporting_requests_immutable_delete
        BEFORE DELETE ON preliminary_supporting_operation_requests
        BEGIN SELECT RAISE(ABORT, 'supporting operation request is immutable'); END;
    """,
)

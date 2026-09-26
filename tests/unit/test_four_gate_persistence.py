from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_adoption_engine.application.four_gate_assessment import (
    FourGateIntegratedAssessmentService,
)
from ai_adoption_engine.decision.four_gate_policy import load_four_gate_policy
from ai_adoption_engine.decision_support.four_gate_service import (
    FourGateDecisionSupportPackageService,
)
from ai_adoption_engine.models.four_gate_decision_support import (
    FourGateDecisionPackageSuccess,
)
from ai_adoption_engine.models.four_gate_integrated_assessment import (
    FourGateIntegratedAssessmentSuccess,
)
from ai_adoption_engine.persistence.base import (
    ArtifactCorruptionError,
    PersistenceError,
)
from ai_adoption_engine.persistence.contract_pins import (
    LEGACY_CONTRACT_PIN,
    successor_contract_pin,
)
from ai_adoption_engine.persistence.four_gate import FourGatePersistenceAdapter
from ai_adoption_engine.persistence.migrations import MIGRATIONS
from ai_adoption_engine.persistence.serialization import (
    serialize_artifact_versioned,
)
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.workspace.models import (
    ArtifactType,
    ExecutionMode,
    OperationKind,
    WorkflowStage,
)
from tests.fakes.review import FIXED_TIME, approved_review


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "decision_policy.v0.3.json"


def _create_migration_three_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        for version, script in MIGRATIONS[:3]:
            connection.executescript(script)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, "2026-09-05T00:00:00+00:00"),
            )
        connection.commit()
    finally:
        connection.close()


def _insert_legacy_history(path: Path) -> None:
    payloads = {
        "legacy-phase5": '{"historical":"assessment"}',
        "legacy-phase6": (
            '{"recorded_outcome":"DO_NOT_RECOMMEND",'
            '"historical_report":"unchanged"}'
        ),
    }
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """INSERT INTO assessments(
                   assessment_id, title, execution_mode, current_stage,
                   created_at, updated_at, row_version
               ) VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (
                "legacy-assessment",
                "Legacy assessment",
                "offline-demo",
                "package-ready",
                "2026-09-05T00:00:00+00:00",
                "2026-09-05T00:00:00+00:00",
            ),
        )
        for artifact_id, artifact_type, schema, parent in (
            (
                "legacy-phase5",
                ArtifactType.INTEGRATED_ASSESSMENT_RESULT.value,
                "phase5-v0.1",
                None,
            ),
            (
                "legacy-phase6",
                ArtifactType.DECISION_PACKAGE_RESULT.value,
                "phase6-v0.1",
                "legacy-phase5",
            ),
        ):
            payload = payloads[artifact_id]
            connection.execute(
                """INSERT INTO assessment_artifacts(
                       artifact_id, assessment_id, artifact_type,
                       artifact_revision, artifact_schema_version, payload_json,
                       payload_sha256, parent_artifact_id, created_at, updated_at
                   ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?)""",
                (
                    artifact_id,
                    "legacy-assessment",
                    artifact_type,
                    schema,
                    payload,
                    hashlib.sha256(payload.encode()).hexdigest(),
                    parent,
                    "2026-09-05T00:00:00+00:00",
                    "2026-09-05T00:00:00+00:00",
                ),
            )
        connection.execute(
            "INSERT INTO active_artifacts VALUES (?, ?, ?)",
            (
                "legacy-assessment",
                ArtifactType.DECISION_PACKAGE_RESULT.value,
                "legacy-phase6",
            ),
        )
        connection.execute(
            """INSERT INTO assessment_operations(
                   operation_id, assessment_id, operation_kind, idempotency_key,
                   status, produced_artifact_id, started_at, completed_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "legacy-operation",
                "legacy-assessment",
                OperationKind.ASSESS.value,
                "legacy-approved-artifact",
                "completed",
                "legacy-phase5",
                "2026-09-05T00:00:00+00:00",
                "2026-09-05T00:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _save_approval(repository, assessment_id, approved):
    review = repository.save_artifact_and_advance(
        assessment_id,
        ArtifactType.REVIEW_SESSION,
        approved.review,
        artifact_schema_version="phase4-v0.1",
        stage=WorkflowStage.IN_REVIEW,
    )
    return repository.save_artifact_and_advance(
        assessment_id,
        ArtifactType.APPROVED_REVIEW,
        approved,
        artifact_schema_version="phase4-v0.1",
        stage=WorkflowStage.APPROVED,
        parent_artifact_id=review.artifact_id,
    )


def _successor_results():
    approved = approved_review()
    policy = load_four_gate_policy(POLICY_PATH)
    integrated = FourGateIntegratedAssessmentService(
        policy_loader=lambda: policy,
        clock=lambda: FIXED_TIME,
        run_id_factory=lambda: "persisted-successor-phase5",
    ).assess(approved)
    assert isinstance(integrated, FourGateIntegratedAssessmentSuccess)
    package = FourGateDecisionSupportPackageService().generate(integrated)
    assert isinstance(package, FourGateDecisionPackageSuccess)
    return approved, integrated, package


def test_migration_four_is_metadata_only_for_legacy_history(tmp_path: Path) -> None:
    path = tmp_path / "migration-three.db"
    _create_migration_three_database(path)
    _insert_legacy_history(path)
    before = sqlite3.connect(path)
    try:
        artifact_columns = before.execute(
            "PRAGMA table_info(assessment_artifacts)"
        ).fetchall()
        artifact_rows = before.execute(
            """SELECT artifact_id, artifact_type, artifact_schema_version,
                      payload_json, payload_sha256, parent_artifact_id
               FROM assessment_artifacts ORDER BY artifact_id"""
        ).fetchall()
        active_rows = before.execute(
            "SELECT * FROM active_artifacts ORDER BY artifact_type"
        ).fetchall()
    finally:
        before.close()

    repository = SQLiteAssessmentRepository(path)

    after = sqlite3.connect(path)
    try:
        assert after.execute(
            "PRAGMA table_info(assessment_artifacts)"
        ).fetchall() == artifact_columns
        assert after.execute(
            """SELECT artifact_id, artifact_type, artifact_schema_version,
                      payload_json, payload_sha256, parent_artifact_id
               FROM assessment_artifacts ORDER BY artifact_id"""
        ).fetchall() == artifact_rows
        assert after.execute(
            "SELECT * FROM active_artifacts ORDER BY artifact_type"
        ).fetchall() == active_rows
        pin = after.execute(
            """SELECT decision_contract_version, decision_policy_id,
                      decision_policy_version, decision_policy_fingerprint
               FROM assessments WHERE assessment_id = 'legacy-assessment'"""
        ).fetchone()
        assert pin == (
            LEGACY_CONTRACT_PIN.decision_contract_version,
            LEGACY_CONTRACT_PIN.policy_id,
            LEGACY_CONTRACT_PIN.policy_version,
            LEGACY_CONTRACT_PIN.decision_policy_fingerprint,
        )
        assert [row[0] for row in after.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        )] == [1, 2, 3, 4]
    finally:
        after.close()
    reused = repository.begin_operation(
        "legacy-assessment",
        OperationKind.ASSESS,
        "legacy-approved-artifact",
    )
    assert reused.operation_id == "legacy-operation"
    assert reused.status.value == "completed"


def test_contract_pin_can_change_before_approval_then_is_immutable(
    tmp_path: Path,
) -> None:
    repository = SQLiteAssessmentRepository(tmp_path / "pin.db")
    assessment = repository.create_assessment(
        "Pinned assessment",
        ExecutionMode.OFFLINE_DEMO,
    )
    successor = successor_contract_pin("a" * 64)
    changed = repository.pin_decision_contract(
        assessment.assessment_id,
        successor,
    )
    assert changed.contract_pin == successor

    approval = _save_approval(repository, assessment.assessment_id, approved_review())
    assert approval.artifact_id
    with pytest.raises(PersistenceError, match="immutable after approval"):
        repository.pin_decision_contract(
            assessment.assessment_id,
            LEGACY_CONTRACT_PIN,
        )

    connection = sqlite3.connect(repository.path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="pin is immutable"):
            connection.execute(
                """UPDATE assessments
                   SET decision_contract_version = 'phase1-v0.3'
                   WHERE assessment_id = ?""",
                (assessment.assessment_id,),
            )
        connection.rollback()
    finally:
        connection.close()


def test_assessment_and_package_idempotency_are_contract_aware(
    tmp_path: Path,
) -> None:
    repository = SQLiteAssessmentRepository(tmp_path / "operations.db")
    legacy = repository.create_assessment("Legacy", ExecutionMode.OFFLINE_DEMO)
    successor = repository.create_assessment(
        "Successor",
        ExecutionMode.OFFLINE_DEMO,
        contract_pin=successor_contract_pin("a" * 64),
    )
    operations = []
    for kind in (OperationKind.ASSESS, OperationKind.GENERATE_PACKAGE):
        legacy_operation = repository.begin_operation(
            legacy.assessment_id,
            kind,
            "same-source-artifact",
        )
        successor_operation = repository.begin_operation(
            successor.assessment_id,
            kind,
            "same-source-artifact",
        )
        operations.extend((legacy_operation, successor_operation))
        assert legacy_operation.idempotency_key == (
            successor_operation.idempotency_key
        )
        assert legacy_operation.decision_contract_version == "phase1-v0.3"
        assert successor_operation.decision_contract_version == "phase1-v0.4"
        assert legacy_operation.decision_policy_fingerprint != (
            successor_operation.decision_policy_fingerprint
        )

    connection = sqlite3.connect(repository.path)
    try:
        identities = [
            (row[0], row[1])
            for row in connection.execute(
                """SELECT operation_kind, contract_idempotency_key
                   FROM assessment_operations ORDER BY assessment_id"""
            )
        ]
    finally:
        connection.close()
    assert len(operations) == 4
    assert len(set(identities)) == 4
    assert sum(key.startswith("phase1-v0.3:") for _, key in identities) == 2
    assert sum(key.startswith("phase1-v0.4:") for _, key in identities) == 2

    repinned = repository.create_assessment(
        "Repinned before approval",
        ExecutionMode.OFFLINE_DEMO,
    )
    legacy_operation = repository.begin_operation(
        repinned.assessment_id,
        OperationKind.ASSESS,
        "same-operation-token",
    )
    repository.pin_decision_contract(
        repinned.assessment_id,
        successor_contract_pin("b" * 64),
    )
    successor_operation = repository.begin_operation(
        repinned.assessment_id,
        OperationKind.ASSESS,
        "same-operation-token",
    )
    assert successor_operation.operation_id != legacy_operation.operation_id
    assert successor_operation.idempotency_key == "same-operation-token"
    assert successor_operation.decision_contract_version == "phase1-v0.4"
    ingestion_operation = repository.begin_operation(
        repinned.assessment_id,
        OperationKind.INGEST,
        "successor-ingestion-token",
    )
    assert ingestion_operation.idempotency_key == "successor-ingestion-token"
    assert ingestion_operation.decision_contract_version is None


def test_successor_phase5_and_phase6_persist_and_hydrate_exactly(
    tmp_path: Path,
) -> None:
    approved, integrated, package = _successor_results()
    repository = SQLiteAssessmentRepository(tmp_path / "successor.db")
    adapter = FourGatePersistenceAdapter(repository)
    assessment = adapter.create_assessment(
        "Successor persistence",
        ExecutionMode.OFFLINE_DEMO,
        policy_fingerprint=integrated.policy.decision_policy_fingerprint,
    )
    approval = _save_approval(repository, assessment.assessment_id, approved)
    assessment_operation = adapter.begin_assessment_operation(
        assessment.assessment_id,
        approval.artifact_id,
    )
    integrated_reference = adapter.persist_integrated_assessment(
        assessment.assessment_id,
        integrated,
        approved_artifact_id=approval.artifact_id,
        operation_id=assessment_operation.operation_id,
    )
    package_operation = adapter.begin_package_operation(
        assessment.assessment_id,
        integrated_reference.artifact_id,
    )
    package_reference = adapter.persist_decision_package(
        assessment.assessment_id,
        package,
        integrated_artifact_id=integrated_reference.artifact_id,
        operation_id=package_operation.operation_id,
    )

    hydrated_integrated = adapter.load_integrated_assessment(
        integrated_reference.artifact_id
    )
    hydrated_package = adapter.load_decision_package(package_reference.artifact_id)
    assert hydrated_integrated.artifact_schema_version == "phase5-v0.2"
    assert hydrated_package.artifact_schema_version == "phase6-v0.2"
    assert hydrated_integrated.payload == integrated
    assert hydrated_package.payload == package
    assert hydrated_package.parent_artifact_id == integrated_reference.artifact_id
    assert repository.get_assessment(assessment.assessment_id).contract_pin == (
        successor_contract_pin(integrated.policy.decision_policy_fingerprint)
    )

    connection = sqlite3.connect(repository.path)
    try:
        rows = connection.execute(
            """SELECT artifact_schema_version, payload_json, payload_sha256
               FROM assessment_artifacts
               WHERE artifact_id IN (?, ?)
               ORDER BY artifact_schema_version""",
            (integrated_reference.artifact_id, package_reference.artifact_id),
        ).fetchall()
    finally:
        connection.close()
    assert [row[0] for row in rows] == ["phase5-v0.2", "phase6-v0.2"]
    assert all(hashlib.sha256(row[1].encode()).hexdigest() == row[2] for row in rows)
    payload_text = " ".join(row[1] for row in rows)
    for identity in (
        "phase1-v0.4",
        "four-gate-framework.v0.1",
        "decision_policy.v0.3",
        "0.3.0",
        integrated.policy.decision_policy_fingerprint,
    ):
        assert identity in payload_text


def test_unknown_versions_and_mixed_parent_chains_fail_before_write(
    tmp_path: Path,
) -> None:
    approved, integrated, package = _successor_results()
    with pytest.raises(ArtifactCorruptionError, match="Unsupported"):
        serialize_artifact_versioned(
            ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
            "phase5-v99",
            integrated,
        )

    repository = SQLiteAssessmentRepository(tmp_path / "mixed.db")
    adapter = FourGatePersistenceAdapter(repository)
    assessment = adapter.create_assessment(
        "Mixed-chain rejection",
        ExecutionMode.OFFLINE_DEMO,
        policy_fingerprint=integrated.policy.decision_policy_fingerprint,
    )
    approval = _save_approval(repository, assessment.assessment_id, approved)
    integrated_reference = adapter.persist_integrated_assessment(
        assessment.assessment_id,
        integrated,
        approved_artifact_id=approval.artifact_id,
    )
    connection = sqlite3.connect(repository.path)
    try:
        connection.execute(
            """UPDATE assessment_artifacts
               SET artifact_schema_version = 'phase5-v0.1'
               WHERE artifact_id = ?""",
            (integrated_reference.artifact_id,),
        )
        connection.commit()
        before_count = connection.execute(
            "SELECT COUNT(*) FROM assessment_artifacts"
        ).fetchone()[0]
    finally:
        connection.close()

    with pytest.raises(PersistenceError, match="Mixed legacy/successor"):
        adapter.persist_decision_package(
            assessment.assessment_id,
            package,
            integrated_artifact_id=integrated_reference.artifact_id,
        )
    connection = sqlite3.connect(repository.path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM assessment_artifacts"
        ).fetchone()[0] == before_count
    finally:
        connection.close()

    payload_json, payload_sha = serialize_artifact_versioned(
        ArtifactType.DECISION_PACKAGE_RESULT,
        "phase6-v0.2",
        package,
    )
    connection = sqlite3.connect(repository.path)
    try:
        connection.execute(
            """INSERT INTO assessment_artifacts(
                   artifact_id, assessment_id, artifact_type, artifact_revision,
                   artifact_schema_version, payload_json, payload_sha256,
                   parent_artifact_id, created_at, updated_at
               ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?)""",
            (
                "forged-mixed-package",
                assessment.assessment_id,
                ArtifactType.DECISION_PACKAGE_RESULT.value,
                "phase6-v0.2",
                payload_json,
                payload_sha,
                integrated_reference.artifact_id,
                datetime.now(UTC).isoformat(),
                datetime.now(UTC).isoformat(),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(PersistenceError, match="Mixed legacy/successor"):
        repository.load_artifact("forged-mixed-package")

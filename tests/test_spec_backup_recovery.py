"""Tests for backup and recovery plan CSV export."""

from __future__ import annotations

import csv
from io import StringIO

from max.spec.backup_recovery import (
    BACKUP_RECOVERY_CSV_COLUMNS,
    BACKUP_RECOVERY_SCHEMA_VERSION,
    generate_backup_recovery_plan,
    render_backup_recovery_plan_csv,
)


def _sample_spec() -> dict:
    """Create a sample TactSpec for testing backup and recovery plans."""
    return {
        "schema_version": "tact-spec/v3",
        "kind": "tact_spec_preview",
        "source": {
            "system": "max",
            "type": "tact_spec_preview",
            "idea_id": "test-idea-001",
            "status": "approved",
        },
        "project": {
            "title": "Data-Intensive Application",
            "summary": "An application requiring comprehensive backup and recovery",
            "workflow_context": "user data management and file processing",
        },
        "solution": {
            "technical_approach": "PostgreSQL database with S3 file storage and Redis cache",
            "suggested_stack": {
                "database": "PostgreSQL",
                "storage": "AWS S3",
                "cache": "Redis",
            },
        },
        "data_model": {
            "users": {"id": "string", "email": "string", "data": "json"},
            "files": {"id": "string", "path": "string", "uploaded_at": "timestamp"},
        },
        "execution": {
            "mvp_scope": ["User data storage", "File upload", "Data backup"],
            "validation_plan": "Verify backup and restore procedures",
            "risks": ["Data loss", "Recovery time exceeds SLA", "Backup corruption"],
        },
    }


def _minimal_spec() -> dict:
    """Create a minimal spec with no explicit backup requirements."""
    return {
        "schema_version": "tact-spec/v3",
        "kind": "tact_spec_preview",
        "source": {
            "idea_id": "minimal-001",
        },
        "project": {
            "title": "Minimal Service",
        },
    }


def test_generate_backup_recovery_plan_is_deterministic() -> None:
    """Verify backup recovery plan generation is deterministic."""
    spec = _sample_spec()

    first = generate_backup_recovery_plan(spec)
    second = generate_backup_recovery_plan(spec)

    assert first == second
    assert first["schema_version"] == BACKUP_RECOVERY_SCHEMA_VERSION
    assert first["kind"] == "max.backup_recovery_plan"


def test_generate_backup_recovery_plan_creates_expected_plans() -> None:
    """Verify expected backup plan types are created for a full spec."""
    spec = _sample_spec()

    plan = generate_backup_recovery_plan(spec)

    assert plan["summary"]["plan_count"] >= 3  # Should have database, files, audit logs, etc.

    backup_plans = plan["backup_plans"]
    plan_types = {p["type"] for p in backup_plans}

    assert "database" in plan_types
    assert "file_storage" in plan_types
    assert "audit_logs" in plan_types
    assert "code_deployment" in plan_types
    assert "disaster_recovery" in plan_types


def test_generate_backup_recovery_plan_assigns_priorities() -> None:
    """Verify backup plans are assigned appropriate priorities based on context."""
    spec = _sample_spec()

    plan = generate_backup_recovery_plan(spec)
    backup_plans = plan["backup_plans"]

    by_type = {p["type"]: p for p in backup_plans}

    # Critical plans
    assert by_type["database"]["priority"] in ["critical", "high"]
    assert by_type["code_deployment"]["priority"] == "critical"
    assert by_type["disaster_recovery"]["priority"] == "critical"

    # High priority plans
    assert by_type["audit_logs"]["priority"] == "high"


def test_generate_backup_recovery_plan_has_required_fields() -> None:
    """Verify each backup plan has all required fields."""
    spec = _sample_spec()

    plan = generate_backup_recovery_plan(spec)
    backup_plans = plan["backup_plans"]

    assert len(backup_plans) > 0

    for backup_plan in backup_plans:
        assert "id" in backup_plan
        assert backup_plan["id"].startswith("BP")
        assert "type" in backup_plan
        assert isinstance(backup_plan["type"], str)
        assert "category" in backup_plan
        assert backup_plan["category"] in [
            "data_backup",
            "config_backup",
            "state_backup",
            "log_backup",
            "deployment_backup",
            "recovery_coordination",
        ]
        assert "title" in backup_plan
        assert isinstance(backup_plan["title"], str)
        assert "owner" in backup_plan
        assert backup_plan["owner"] in [
            "data_owner",
            "platform_owner",
            "backend_owner",
            "security_owner",
            "engineering_owner",
            "product_owner",
        ]
        assert "priority" in backup_plan
        assert backup_plan["priority"] in ["critical", "high", "medium", "low"]
        assert "backup_frequency" in backup_plan
        assert "retention_period" in backup_plan
        assert "recovery_time_objective" in backup_plan
        assert "recovery_point_objective" in backup_plan
        assert "backup_scope" in backup_plan
        assert "backup_mechanism" in backup_plan
        assert "verification_procedure" in backup_plan
        assert "restoration_procedure" in backup_plan
        assert "source_fields" in backup_plan
        assert isinstance(backup_plan["source_fields"], list)


def test_generate_backup_recovery_plan_handles_minimal_spec() -> None:
    """Verify minimal spec gets baseline backup plans."""
    spec = _minimal_spec()

    plan = generate_backup_recovery_plan(spec)

    # Should still have essential plans even with minimal spec
    assert plan["summary"]["plan_count"] >= 3
    backup_plans = plan["backup_plans"]

    # Essential plans should always be present
    plan_types = {p["type"] for p in backup_plans}
    assert "audit_logs" in plan_types
    assert "code_deployment" in plan_types
    assert "disaster_recovery" in plan_types


def test_generate_backup_recovery_plan_context_detection() -> None:
    """Verify context detection influences backup recommendations."""
    spec = _sample_spec()

    plan = generate_backup_recovery_plan(spec)
    backup_plans = plan["backup_plans"]

    by_type = {p["type"]: p for p in backup_plans}

    # Database backup should reference database when detected
    db_plan = by_type["database"]
    assert db_plan["priority"] in ["critical", "high"]
    assert "database" in db_plan["backup_scope"].lower() or "snapshot" in db_plan["backup_mechanism"].lower()

    # File storage backup should be present when files are detected
    assert "file_storage" in by_type
    file_plan = by_type["file_storage"]
    assert "file" in file_plan["title"].lower() or "storage" in file_plan["title"].lower()


def test_render_backup_recovery_plan_csv_has_correct_headers() -> None:
    """Verify CSV output has correct header structure."""
    spec = _sample_spec()
    plan = generate_backup_recovery_plan(spec)

    csv_output = render_backup_recovery_plan_csv(plan)

    lines = csv_output.strip().split("\n")
    assert len(lines) >= 2  # At least header + one row

    header_line = lines[0]
    headers = header_line.split(",")

    assert len(headers) == len(BACKUP_RECOVERY_CSV_COLUMNS)
    assert headers[0] == "schema_version"
    assert headers[1] == "kind"
    assert headers[2] == "source_idea_id"
    assert headers[3] == "plan_id"
    assert headers[4] == "plan_type"
    assert headers[5] == "plan_category"
    assert headers[6] == "plan_title"
    assert headers[7] == "plan_owner"
    assert headers[8] == "plan_priority"
    assert headers[9] == "backup_frequency"
    assert headers[10] == "retention_period"
    assert headers[11] == "recovery_time_objective"
    assert headers[12] == "recovery_point_objective"
    assert headers[13] == "backup_scope"
    assert headers[14] == "backup_mechanism"
    assert headers[15] == "verification_procedure"
    assert headers[16] == "restoration_procedure"
    assert headers[17] == "source_fields"


def test_render_backup_recovery_plan_csv_formats_rows_correctly() -> None:
    """Verify CSV rows contain expected data."""
    spec = _sample_spec()
    plan = generate_backup_recovery_plan(spec)

    csv_output = render_backup_recovery_plan_csv(plan)

    reader = csv.DictReader(StringIO(csv_output))
    rows = list(reader)

    assert len(rows) == plan["summary"]["plan_count"]

    first_row = rows[0]
    assert first_row["schema_version"] == BACKUP_RECOVERY_SCHEMA_VERSION
    assert first_row["kind"] == "max.backup_recovery_plan"
    assert first_row["source_idea_id"] == "test-idea-001"
    assert first_row["plan_id"].startswith("BP")
    assert first_row["plan_type"] != ""
    assert first_row["plan_category"] != ""
    assert first_row["plan_title"] != ""
    assert first_row["plan_owner"] != ""
    assert first_row["plan_priority"] in ["critical", "high", "medium", "low"]
    assert first_row["backup_frequency"] != ""
    assert first_row["retention_period"] != ""


def test_render_backup_recovery_plan_csv_source_fields_formatted() -> None:
    """Verify source_fields are properly formatted in CSV."""
    spec = _sample_spec()
    plan = generate_backup_recovery_plan(spec)

    csv_output = render_backup_recovery_plan_csv(plan)

    reader = csv.DictReader(StringIO(csv_output))
    rows = list(reader)

    for row in rows:
        # All rows should have source_fields
        assert row["source_fields"] != ""
        # Source fields should be pipe-separated
        if " | " in row["source_fields"]:
            fields = row["source_fields"].split(" | ")
            assert len(fields) >= 1
            for field in fields:
                assert field.strip() != ""


def test_render_backup_recovery_plan_csv_empty_plan() -> None:
    """Verify CSV renderer handles empty plan gracefully."""
    empty_plan = {
        "schema_version": BACKUP_RECOVERY_SCHEMA_VERSION,
        "kind": "max.backup_recovery_plan",
        "source": {"idea_id": "empty-001"},
        "summary": {"plan_count": 0},
        "backup_plans": [],
    }

    csv_output = render_backup_recovery_plan_csv(empty_plan)

    lines = csv_output.strip().split("\n")
    # Should have header but no data rows
    assert len(lines) == 1
    assert lines[0].startswith("schema_version,kind,")


def test_csv_columns_constant_matches_implementation() -> None:
    """Verify BACKUP_RECOVERY_CSV_COLUMNS constant matches actual implementation."""
    expected_columns = [
        "schema_version",
        "kind",
        "source_idea_id",
        "plan_id",
        "plan_type",
        "plan_category",
        "plan_title",
        "plan_owner",
        "plan_priority",
        "backup_frequency",
        "retention_period",
        "recovery_time_objective",
        "recovery_point_objective",
        "backup_scope",
        "backup_mechanism",
        "verification_procedure",
        "restoration_procedure",
        "source_fields",
    ]

    assert list(BACKUP_RECOVERY_CSV_COLUMNS) == expected_columns


def test_generate_backup_recovery_plan_priority_ordering() -> None:
    """Verify plans are ordered by priority (critical > high > medium > low)."""
    spec = _sample_spec()

    plan = generate_backup_recovery_plan(spec)
    backup_plans = plan["backup_plans"]

    priority_map = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    # Verify plans are sorted by priority
    for i in range(len(backup_plans) - 1):
        current_priority = priority_map[backup_plans[i]["priority"]]
        next_priority = priority_map[backup_plans[i + 1]["priority"]]
        assert current_priority <= next_priority


def test_generate_backup_recovery_plan_assigns_unique_ids() -> None:
    """Verify each plan gets a unique sequential ID."""
    spec = _sample_spec()

    plan = generate_backup_recovery_plan(spec)
    backup_plans = plan["backup_plans"]

    plan_ids = [p["id"] for p in backup_plans]
    # All IDs should be unique
    assert len(plan_ids) == len(set(plan_ids))
    # IDs should start with BP
    assert all(id.startswith("BP") for id in plan_ids)
    # IDs should be sequential
    expected_ids = [f"BP{i:02d}" for i in range(1, len(backup_plans) + 1)]
    assert plan_ids == expected_ids


def test_generate_backup_recovery_plan_handles_missing_context() -> None:
    """Verify plans are generated with appropriate defaults when context is missing."""
    spec = {
        "schema_version": "tact-spec/v3",
        "kind": "tact_spec_preview",
        "source": {},
        "project": {},
        "solution": {},
        "execution": {},
    }

    plan = generate_backup_recovery_plan(spec)

    # Should still generate baseline plans
    assert plan["summary"]["plan_count"] >= 3
    backup_plans = plan["backup_plans"]

    # All plans should have valid structure even with minimal input
    for backup_plan in backup_plans:
        assert backup_plan["id"].startswith("BP")
        assert backup_plan["priority"] in ["critical", "high", "medium", "low"]


def test_render_backup_recovery_plan_csv_escapes_special_characters() -> None:
    """Verify CSV properly handles special characters in field values."""
    spec = _sample_spec()
    # Add special characters to test CSV escaping
    spec["project"]["title"] = 'Application with "quotes" and, commas'

    plan = generate_backup_recovery_plan(spec)
    csv_output = render_backup_recovery_plan_csv(plan)

    # Should be valid CSV
    reader = csv.DictReader(StringIO(csv_output))
    rows = list(reader)

    # Should successfully parse without errors
    assert len(rows) > 0

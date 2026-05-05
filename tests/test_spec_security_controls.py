"""Tests for security controls CSV export."""

from __future__ import annotations

import csv
from io import StringIO

from max.spec.security_controls import (
    SECURITY_CONTROLS_CSV_COLUMNS,
    SECURITY_CONTROLS_SCHEMA_VERSION,
    generate_security_controls,
    render_security_controls_csv,
)


def _sample_spec() -> dict:
    """Create a sample TactSpec for testing security controls."""
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
            "title": "Secure API Service",
            "summary": "A REST API service with comprehensive security controls",
            "workflow_context": "user authentication and data access",
            "specific_user": "authenticated users",
        },
        "solution": {
            "technical_approach": "FastAPI service with OAuth 2.0 authentication, RBAC authorization, and secret management",
            "composability_notes": "Integrate with external payment provider and email service",
            "suggested_stack": {
                "auth": "Auth0",
                "database": "PostgreSQL",
                "secrets": "AWS Secrets Manager",
            },
        },
        "execution": {
            "mvp_scope": ["User registration", "Authentication", "API access with role-based permissions"],
            "validation_plan": "Implement audit logging for all security events",
            "risks": ["Credential leakage", "Rate limiting bypass", "Data retention compliance"],
        },
        "security": {
            "auth": "OAuth 2.0 with JWT tokens",
        },
    }


def _minimal_spec() -> dict:
    """Create a minimal spec with no explicit security requirements."""
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


def test_generate_security_controls_is_deterministic() -> None:
    """Verify security controls generation is deterministic."""
    spec = _sample_spec()

    first = generate_security_controls(spec)
    second = generate_security_controls(spec)

    assert first == second
    assert first["schema_version"] == SECURITY_CONTROLS_SCHEMA_VERSION
    assert first["kind"] == "max.security_controls"


def test_generate_security_controls_creates_expected_controls() -> None:
    """Verify expected security control categories are created for a full spec."""
    spec = _sample_spec()

    config = generate_security_controls(spec)

    assert config["summary"]["control_count"] >= 7  # One for each category

    controls = config["controls"]
    control_categories = {control["category"] for control in controls}

    assert "authentication" in control_categories
    assert "authorization" in control_categories
    assert "secret_handling" in control_categories
    assert "data_retention" in control_categories
    assert "dependency_exposure" in control_categories
    assert "audit_logging" in control_categories
    assert "abuse_cases" in control_categories


def test_generate_security_controls_assigns_priorities() -> None:
    """Verify security controls are assigned appropriate priorities based on context."""
    spec = _sample_spec()

    config = generate_security_controls(spec)
    controls = config["controls"]

    by_category = {control["category"]: control for control in controls}

    # Secret handling should be critical when secrets are mentioned
    assert by_category["secret_handling"]["priority"] == "critical"

    # Authentication, authorization, and other controls should be high when mentioned
    assert by_category["authentication"]["priority"] == "high"
    assert by_category["authorization"]["priority"] == "high"


def test_generate_security_controls_has_required_fields() -> None:
    """Verify each security control has all required fields."""
    spec = _sample_spec()

    config = generate_security_controls(spec)
    controls = config["controls"]

    assert len(controls) > 0

    for control in controls:
        assert "id" in control
        assert control["id"].startswith("SC")
        assert "category" in control
        assert control["category"] in [
            "authentication",
            "authorization",
            "secret_handling",
            "data_retention",
            "dependency_exposure",
            "audit_logging",
            "abuse_cases",
        ]
        assert "category_title" in control
        assert isinstance(control["category_title"], str)
        assert "title" in control
        assert isinstance(control["title"], str)
        assert "owner" in control
        assert control["owner"] in [
            "security_owner",
            "backend_owner",
            "platform_owner",
            "data_owner",
            "integration_owner",
            "qa_owner",
        ]
        assert "status" in control
        assert control["status"] == "recommended"
        assert "priority" in control
        assert control["priority"] in ["critical", "high", "medium", "low"]
        assert "recommendation" in control
        assert isinstance(control["recommendation"], str)
        assert "implementation_notes" in control
        assert isinstance(control["implementation_notes"], str)
        assert "source_fields" in control
        assert isinstance(control["source_fields"], list)


def test_generate_security_controls_handles_minimal_spec() -> None:
    """Verify minimal spec gets baseline security controls with lower priorities."""
    spec = _minimal_spec()

    config = generate_security_controls(spec)

    assert config["summary"]["control_count"] >= 7  # All categories should have controls
    controls = config["controls"]

    # Minimal spec should have medium or low priority controls
    priorities = [control["priority"] for control in controls]
    assert "medium" in priorities or "low" in priorities
    assert priorities.count("critical") == 0  # No critical controls for minimal spec


def test_generate_security_controls_context_detection() -> None:
    """Verify context detection influences control recommendations."""
    spec = _sample_spec()

    config = generate_security_controls(spec)
    controls = config["controls"]

    by_category = {control["category"]: control for control in controls}

    # Authentication control should reference OAuth when detected
    auth_control = by_category["authentication"]
    assert "authentication boundary" in auth_control["title"].lower() or "define" in auth_control["title"].lower()

    # Secret handling should be critical when secrets are mentioned
    secret_control = by_category["secret_handling"]
    assert secret_control["priority"] == "critical"
    assert "secret manager" in secret_control["recommendation"].lower() or "encrypted" in secret_control["recommendation"].lower()


def test_render_security_controls_csv_has_correct_headers() -> None:
    """Verify CSV output has correct header structure."""
    spec = _sample_spec()
    config = generate_security_controls(spec)

    csv_output = render_security_controls_csv(config)

    lines = csv_output.strip().split("\n")
    assert len(lines) >= 2  # At least header + one row

    header_line = lines[0]
    headers = header_line.split(",")

    assert len(headers) == len(SECURITY_CONTROLS_CSV_COLUMNS)
    assert headers[0] == "schema_version"
    assert headers[1] == "kind"
    assert headers[2] == "source_idea_id"
    assert headers[3] == "control_id"
    assert headers[4] == "control_category"
    assert headers[5] == "control_title"
    assert headers[6] == "control_owner"
    assert headers[7] == "control_status"
    assert headers[8] == "control_priority"
    assert headers[9] == "control_recommendation"
    assert headers[10] == "control_implementation_notes"
    assert headers[11] == "source_fields"
    assert headers[12] == "related_findings"
    assert headers[13] == "related_questions"


def test_render_security_controls_csv_formats_rows_correctly() -> None:
    """Verify CSV rows contain expected data."""
    spec = _sample_spec()
    config = generate_security_controls(spec)

    csv_output = render_security_controls_csv(config)

    reader = csv.DictReader(StringIO(csv_output))
    rows = list(reader)

    assert len(rows) == config["summary"]["control_count"]

    first_row = rows[0]
    assert first_row["schema_version"] == SECURITY_CONTROLS_SCHEMA_VERSION
    assert first_row["kind"] == "max.security_controls"
    assert first_row["source_idea_id"] == "test-idea-001"
    assert first_row["control_id"].startswith("SC")
    assert first_row["control_category"] != ""
    assert first_row["control_title"] != ""
    assert first_row["control_owner"] != ""
    assert first_row["control_status"] == "recommended"
    assert first_row["control_priority"] in ["critical", "high", "medium", "low"]
    assert first_row["control_recommendation"] != ""
    assert first_row["control_implementation_notes"] != ""


def test_render_security_controls_csv_source_fields_formatted() -> None:
    """Verify source_fields are properly formatted in CSV."""
    spec = _sample_spec()
    config = generate_security_controls(spec)

    csv_output = render_security_controls_csv(config)

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


def test_render_security_controls_csv_handles_optional_fields() -> None:
    """Verify CSV handles optional fields like related_findings and related_questions correctly."""
    spec = _sample_spec()
    config = generate_security_controls(spec)

    csv_output = render_security_controls_csv(config)

    reader = csv.DictReader(StringIO(csv_output))
    rows = list(reader)

    # Optional fields should exist but may be empty
    for row in rows:
        assert "related_findings" in row
        assert "related_questions" in row
        # These fields are optional and may be empty strings
        assert isinstance(row["related_findings"], str)
        assert isinstance(row["related_questions"], str)


def test_render_security_controls_csv_empty_config() -> None:
    """Verify CSV renderer handles empty configuration gracefully."""
    empty_config = {
        "schema_version": SECURITY_CONTROLS_SCHEMA_VERSION,
        "kind": "max.security_controls",
        "source": {"idea_id": "empty-001"},
        "summary": {"control_count": 0},
        "controls": [],
    }

    csv_output = render_security_controls_csv(empty_config)

    lines = csv_output.strip().split("\n")
    # Should have header but no data rows
    assert len(lines) == 1
    assert lines[0].startswith("schema_version,kind,")


def test_csv_columns_constant_matches_implementation() -> None:
    """Verify SECURITY_CONTROLS_CSV_COLUMNS constant matches actual implementation."""
    expected_columns = [
        "schema_version",
        "kind",
        "source_idea_id",
        "control_id",
        "control_category",
        "control_title",
        "control_owner",
        "control_status",
        "control_priority",
        "control_recommendation",
        "control_implementation_notes",
        "source_fields",
        "related_findings",
        "related_questions",
    ]

    assert list(SECURITY_CONTROLS_CSV_COLUMNS) == expected_columns


def test_generate_security_controls_priority_ordering() -> None:
    """Verify controls are ordered by priority (critical > high > medium > low)."""
    spec = _sample_spec()

    config = generate_security_controls(spec)
    controls = config["controls"]

    priority_map = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    # Verify controls are sorted by priority
    for i in range(len(controls) - 1):
        current_priority = priority_map[controls[i]["priority"]]
        next_priority = priority_map[controls[i + 1]["priority"]]
        assert current_priority <= next_priority


def test_generate_security_controls_assigns_unique_ids() -> None:
    """Verify each control gets a unique sequential ID."""
    spec = _sample_spec()

    config = generate_security_controls(spec)
    controls = config["controls"]

    control_ids = [control["id"] for control in controls]
    # All IDs should be unique
    assert len(control_ids) == len(set(control_ids))
    # IDs should start with SC
    assert all(id.startswith("SC") for id in control_ids)
    # IDs should be sequential
    expected_ids = [f"SC{i:02d}" for i in range(1, len(controls) + 1)]
    assert control_ids == expected_ids


def test_generate_security_controls_handles_missing_context() -> None:
    """Verify controls are generated with appropriate defaults when context is missing."""
    spec = {
        "schema_version": "tact-spec/v3",
        "kind": "tact_spec_preview",
        "source": {},
        "project": {},
        "solution": {},
        "execution": {},
    }

    config = generate_security_controls(spec)

    # Should still generate all control categories
    assert config["summary"]["control_count"] >= 7
    controls = config["controls"]

    # All controls should have valid structure even with minimal input
    for control in controls:
        assert control["id"].startswith("SC")
        assert control["category"] in [
            "authentication",
            "authorization",
            "secret_handling",
            "data_retention",
            "dependency_exposure",
            "audit_logging",
            "abuse_cases",
        ]
        assert control["priority"] in ["critical", "high", "medium", "low"]
        assert control["status"] == "recommended"


def test_render_security_controls_csv_escapes_special_characters() -> None:
    """Verify CSV properly handles special characters in field values."""
    spec = _sample_spec()
    # Add a control with special characters
    spec["project"]["title"] = 'Service with "quotes" and, commas'

    config = generate_security_controls(spec)
    csv_output = render_security_controls_csv(config)

    # Should be valid CSV
    reader = csv.DictReader(StringIO(csv_output))
    rows = list(reader)

    # Should successfully parse without errors
    assert len(rows) > 0

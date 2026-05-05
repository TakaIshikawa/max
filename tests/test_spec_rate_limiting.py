"""Tests for rate limiting configuration CSV export."""

from __future__ import annotations

import csv
from io import StringIO

from max.spec.rate_limiting import (
    RATE_LIMITING_CSV_COLUMNS,
    RATE_LIMITING_SCHEMA_VERSION,
    generate_rate_limiting_config,
    render_rate_limiting_config_csv,
)


def _sample_spec() -> dict:
    """Create a sample TactSpec for testing rate limiting configuration."""
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
            "title": "API Service with Rate Limiting",
            "summary": "A REST API service requiring rate limiting",
        },
        "solution": {
            "technical_approach": "FastAPI service with OAuth authentication and Redis rate limiting",
            "composability_notes": "Expose webhooks for external integrations",
        },
        "endpoints": [
            {"path": "/api/v1/users", "method": "GET"},
            {"path": "/api/v1/users", "method": "POST"},
        ],
        "integrations": [
            {"name": "Stripe", "purpose": "payment processing"},
            {"name": "SendGrid", "purpose": "email notifications"},
        ],
        "data_model": {
            "users": {"id": "string", "email": "string", "name": "string"},
        },
        "security": {
            "auth": "OAuth 2.0 with JWT tokens",
        },
        "execution": {
            "mvp_scope": ["User registration", "Authentication", "API access"],
        },
    }


def _minimal_spec() -> dict:
    """Create a minimal spec with no explicit rate limiting requirements."""
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


def test_generate_rate_limiting_config_is_deterministic() -> None:
    """Verify rate limiting config generation is deterministic."""
    spec = _sample_spec()

    first = generate_rate_limiting_config(spec)
    second = generate_rate_limiting_config(spec)

    assert first == second
    assert first["schema_version"] == RATE_LIMITING_SCHEMA_VERSION
    assert first["kind"] == "max.rate_limiting_config"


def test_generate_rate_limiting_config_creates_expected_limits() -> None:
    """Verify expected rate limit types are created for a full spec."""
    spec = _sample_spec()

    config = generate_rate_limiting_config(spec)

    assert config["summary"]["rate_limit_count"] >= 4
    assert config["summary"]["critical_limit_count"] >= 2

    rate_limits = config["rate_limits"]
    limit_types = {limit["type"] for limit in rate_limits}

    assert "api_endpoint" in limit_types
    assert "api_endpoint_global" in limit_types
    assert "authentication" in limit_types
    assert "data_mutation" in limit_types
    assert "external_integration" in limit_types


def test_generate_rate_limiting_config_assigns_priorities() -> None:
    """Verify rate limits are assigned appropriate priorities."""
    spec = _sample_spec()

    config = generate_rate_limiting_config(spec)
    rate_limits = config["rate_limits"]

    by_type = {limit["type"]: limit for limit in rate_limits}

    assert by_type["api_endpoint_global"]["priority"] == "critical"
    assert by_type["authentication"]["priority"] == "critical"
    assert by_type["api_endpoint"]["priority"] == "high"
    assert by_type["data_mutation"]["priority"] == "high"


def test_generate_rate_limiting_config_has_required_fields() -> None:
    """Verify each rate limit has all required fields."""
    spec = _sample_spec()

    config = generate_rate_limiting_config(spec)
    rate_limits = config["rate_limits"]

    assert len(rate_limits) > 0

    for limit in rate_limits:
        assert "id" in limit
        assert limit["id"].startswith("RL")
        assert "type" in limit
        assert "threshold" in limit
        assert isinstance(limit["threshold"], int)
        assert limit["threshold"] > 0
        assert "time_window" in limit
        assert isinstance(limit["time_window"], str)
        assert "enforcement_strategy" in limit
        assert limit["enforcement_strategy"] in [
            "sliding_window",
            "fixed_window",
            "token_bucket",
            "leaky_bucket",
        ]
        assert "scope" in limit
        assert limit["scope"] in ["per_user", "per_ip", "per_integration", "global"]
        assert "priority" in limit
        assert limit["priority"] in ["critical", "high", "medium", "low"]
        assert "notes" in limit
        assert "source_fields" in limit
        assert isinstance(limit["source_fields"], list)


def test_generate_rate_limiting_config_handles_minimal_spec() -> None:
    """Verify minimal spec gets fallback rate limit."""
    spec = _minimal_spec()

    config = generate_rate_limiting_config(spec)

    assert config["summary"]["rate_limit_count"] == 1
    rate_limits = config["rate_limits"]
    assert len(rate_limits) == 1
    assert rate_limits[0]["type"] == "default"
    assert rate_limits[0]["priority"] == "medium"


def test_render_rate_limiting_config_csv_has_correct_headers() -> None:
    """Verify CSV output has correct header structure."""
    spec = _sample_spec()
    config = generate_rate_limiting_config(spec)

    csv_output = render_rate_limiting_config_csv(config)

    lines = csv_output.strip().split("\n")
    assert len(lines) >= 2  # At least header + one row

    header_line = lines[0]
    headers = header_line.split(",")

    assert len(headers) == len(RATE_LIMITING_CSV_COLUMNS)
    assert headers[0] == "schema_version"
    assert headers[1] == "kind"
    assert headers[2] == "source_idea_id"
    assert headers[3] == "rate_limit_id"
    assert headers[4] == "rate_limit_type"
    assert headers[5] == "threshold"
    assert headers[6] == "time_window"
    assert headers[7] == "enforcement_strategy"
    assert headers[8] == "exemptions"
    assert headers[9] == "scope"
    assert headers[10] == "priority"
    assert headers[11] == "notes"
    assert headers[12] == "source_fields"


def test_render_rate_limiting_config_csv_formats_rows_correctly() -> None:
    """Verify CSV rows contain expected data."""
    spec = _sample_spec()
    config = generate_rate_limiting_config(spec)

    csv_output = render_rate_limiting_config_csv(config)

    reader = csv.DictReader(StringIO(csv_output))
    rows = list(reader)

    assert len(rows) == config["summary"]["rate_limit_count"]

    first_row = rows[0]
    assert first_row["schema_version"] == RATE_LIMITING_SCHEMA_VERSION
    assert first_row["kind"] == "max.rate_limiting_config"
    assert first_row["source_idea_id"] == "test-idea-001"
    assert first_row["rate_limit_id"].startswith("RL")
    assert first_row["rate_limit_type"] != ""
    assert first_row["threshold"] != ""
    assert int(first_row["threshold"]) > 0
    assert first_row["time_window"] != ""
    assert first_row["enforcement_strategy"] != ""
    assert first_row["scope"] != ""
    assert first_row["priority"] in ["critical", "high", "medium", "low"]


def test_render_rate_limiting_config_csv_handles_optional_fields() -> None:
    """Verify CSV handles optional fields like exemptions correctly."""
    spec = _sample_spec()
    config = generate_rate_limiting_config(spec)

    csv_output = render_rate_limiting_config_csv(config)

    reader = csv.DictReader(StringIO(csv_output))
    rows = list(reader)

    # Some rows should have exemptions, some should not
    rows_with_exemptions = [row for row in rows if row["exemptions"]]
    rows_without_exemptions = [row for row in rows if not row["exemptions"]]

    # At least one rate limit should have exemptions (data_mutation has "admin_users")
    assert len(rows_with_exemptions) >= 1
    # Most rate limits should not have exemptions
    assert len(rows_without_exemptions) >= 3


def test_render_rate_limiting_config_csv_source_fields_formatted() -> None:
    """Verify source_fields are properly formatted in CSV."""
    spec = _sample_spec()
    config = generate_rate_limiting_config(spec)

    csv_output = render_rate_limiting_config_csv(config)

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


def test_render_rate_limiting_config_csv_empty_config() -> None:
    """Verify CSV renderer handles empty configuration gracefully."""
    empty_config = {
        "schema_version": RATE_LIMITING_SCHEMA_VERSION,
        "kind": "max.rate_limiting_config",
        "source": {"idea_id": "empty-001"},
        "summary": {"rate_limit_count": 0},
        "rate_limits": [],
    }

    csv_output = render_rate_limiting_config_csv(empty_config)

    lines = csv_output.strip().split("\n")
    # Should have header but no data rows
    assert len(lines) == 1
    assert lines[0].startswith("schema_version,kind,")


def test_csv_columns_constant_matches_implementation() -> None:
    """Verify RATE_LIMITING_CSV_COLUMNS constant matches actual implementation."""
    expected_columns = [
        "schema_version",
        "kind",
        "source_idea_id",
        "rate_limit_id",
        "rate_limit_type",
        "threshold",
        "time_window",
        "enforcement_strategy",
        "exemptions",
        "scope",
        "priority",
        "notes",
        "source_fields",
    ]

    assert list(RATE_LIMITING_CSV_COLUMNS) == expected_columns

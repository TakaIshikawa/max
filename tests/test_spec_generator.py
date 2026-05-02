"""Tests for tact-compatible spec preview generation."""

from __future__ import annotations

import json

from max.spec.generator import SPEC_PREVIEW_SCHEMA_VERSION, generate_spec_preview


def test_generate_spec_preview_maps_buildable_unit(sample_unit, sample_evaluation):
    spec = generate_spec_preview(sample_unit, sample_evaluation)

    assert spec["schema_version"] == SPEC_PREVIEW_SCHEMA_VERSION
    assert spec["kind"] == "tact.project_spec"
    assert spec["source"]["idea_id"] == "bu-test001"
    assert spec["project"]["title"] == "MCP Test Framework"
    assert spec["project"]["specific_user"] == "MCP server maintainer"
    assert spec["solution"]["suggested_stack"] == {"language": "typescript", "runtime": "node"}
    assert spec["execution"]["mvp_scope"] == [
        "A CLI tool that validates MCP server implementations",
        "TypeScript CLI with protocol-level validation",
        "run against five open-source MCP servers",
    ]
    assert spec["evidence"]["insight_ids"] == ["ins-test001"]
    assert spec["evaluation"]["overall_score"] == 78.0
    assert spec["evaluation"]["dimensions"]["pain_severity"] == {
        "value": 8.0,
        "confidence": 0.7,
        "reasoning": "test",
    }
    assert (
        spec["artifacts"]["stakeholder_handoff"]["schema_version"]
        == "max-stakeholder-handoff/v1"
    )
    assert spec["artifacts"]["stakeholder_handoff"]["idea_id"] == "bu-test001"
    assert spec["artifacts"]["stakeholder_handoff"]["source"]["tact_spec_schema_version"] == (
        SPEC_PREVIEW_SCHEMA_VERSION
    )


def test_generate_spec_preview_is_json_serializable(sample_unit, sample_evaluation):
    spec = generate_spec_preview(sample_unit, sample_evaluation)

    assert json.loads(json.dumps(spec))["source"]["created_at"]


def test_generate_spec_preview_allows_missing_evaluation(sample_unit):
    spec = generate_spec_preview(sample_unit)

    assert spec["evaluation"] is None
    assert spec["artifacts"]["stakeholder_handoff"]["source"]["evaluation_available"] is False

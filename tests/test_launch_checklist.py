"""Tests for launch checklist generation."""

from __future__ import annotations

import json

from max.spec.generator import generate_spec_preview
from max.spec.launch_checklist import (
    LAUNCH_CHECKLIST_SCHEMA_VERSION,
    generate_launch_checklist,
)


def test_generate_launch_checklist_structures_launch_sections(sample_unit, sample_evaluation):
    tact_spec = generate_spec_preview(sample_unit, sample_evaluation)

    checklist = generate_launch_checklist(sample_unit, sample_evaluation, tact_spec)

    assert checklist["schema_version"] == LAUNCH_CHECKLIST_SCHEMA_VERSION
    assert checklist["kind"] == "max.launch_checklist"
    assert checklist["idea_id"] == "bu-test001"
    assert checklist["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert checklist["summary"]["title"] == "MCP Test Framework"
    assert checklist["summary"]["recommendation"] == "yes"
    assert [section["id"] for section in checklist["sections"]] == [
        "repository_setup",
        "mvp_validation",
        "release_readiness",
        "telemetry",
        "risk_review",
        "feedback_capture",
    ]
    assert [item["id"] for item in checklist["checklist_items"]] == [
        f"LC{index}" for index in range(1, 19)
    ]
    assert any(risk["description"] == "protocol churn" for risk in checklist["risks"])
    assert any(risk["description"] == "Niche audience" for risk in checklist["risks"])


def test_generate_launch_checklist_is_json_serializable(sample_unit, sample_evaluation):
    checklist = generate_launch_checklist(sample_unit, sample_evaluation)

    assert json.loads(json.dumps(checklist))["kind"] == "max.launch_checklist"


def test_generate_launch_checklist_surfaces_missing_evaluation(sample_unit):
    checklist = generate_launch_checklist(sample_unit)

    assert checklist["summary"]["recommendation"] is None
    assert checklist["summary"]["launch_gate"] == "needs_approval"
    assert any(risk["source"] == "evaluation" for risk in checklist["risks"])

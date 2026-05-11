"""Tests for TactSpec error budget policy generation."""

from __future__ import annotations

import csv
import io
import json

from max.spec import generate_error_budget_policy as exported_generate
from max.spec import render_error_budget_policy_csv as exported_render_csv
from max.spec import render_error_budget_policy_markdown as exported_render_markdown
from max.spec.error_budget_policy import (
    ERROR_BUDGET_POLICY_CSV_COLUMNS,
    ERROR_BUDGET_POLICY_SCHEMA_VERSION,
    generate_error_budget_policy,
    render_error_budget_policy_csv,
    render_error_budget_policy_markdown,
)
from max.spec.generator import generate_spec_preview


def test_generate_error_budget_policy_has_stable_shape(sample_unit, sample_evaluation) -> None:
    tact_spec = generate_spec_preview(sample_unit, sample_evaluation)
    tact_spec["acceptance_criteria"] = {
        "criteria": [
            {"id": "AC1", "criterion": "CLI validates a compliant MCP server without errors."},
            {"id": "AC2", "criterion": "CI output includes actionable protocol failure details."},
        ]
    }

    first = generate_error_budget_policy(tact_spec)
    second = generate_error_budget_policy(tact_spec)

    assert first == second
    assert first["schema_version"] == ERROR_BUDGET_POLICY_SCHEMA_VERSION
    assert first["kind"] == "max.error_budget_policy"
    assert first["source"]["idea_id"] == "bu-test001"
    assert first["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert first["source"]["evidence_reference_count"] == 3
    assert first["summary"] == {
        "title": "MCP Test Framework",
        "workflow_context": "pre-release CI validation",
        "target_user": "MCP server maintainer",
        "buyer": "developer platform lead",
        "evaluation_score": 78.0,
        "recommendation": "yes",
        "risk_level": "high",
        "strictness": "strict",
        "acceptance_criteria_count": 2,
        "suggested_stack": "language=typescript, runtime=node",
    }
    assert set(first) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "slo_candidates",
        "budget_windows",
        "burn_rate_alerts",
        "release_gates",
        "freeze_criteria",
        "owner_actions",
        "evidence_references",
    }
    assert [item["id"] for item in first["slo_candidates"]] == ["SLO1", "SLO2", "SLO3", "SLO4"]
    assert first["slo_candidates"][1]["target"] == "p95 <= 1000 ms"
    assert first["budget_windows"][0]["name"] == "validation"
    assert first["freeze_criteria"][0]["condition"] == "25% of pilot budget consumed before midpoint."
    assert any(gate["id"] == "RG5" and gate["status"] == "required" for gate in first["release_gates"])
    assert first["owner_actions"][-1]["id"] == "OA5"
    assert [item["reference"] for item in first["evidence_references"]] == [
        "insight:ins-test001",
        "signal:sig-test001",
        "Insight shows lack of standardized testing.",
    ]


def test_low_score_and_high_execution_risk_produce_stricter_gates(sample_unit, sample_evaluation) -> None:
    tact_spec = generate_spec_preview(sample_unit, sample_evaluation)
    tact_spec["evaluation"]["overall_score"] = 42.0
    tact_spec["evaluation"]["recommendation"] = "no"
    tact_spec["execution"]["risks"] = [
        "privacy review may fail",
        "dependency outage during sync",
        "migration rollback is untested",
    ]

    policy = generate_error_budget_policy(tact_spec)

    assert policy["summary"]["risk_level"] == "high"
    assert policy["summary"]["strictness"] == "strict"
    assert policy["budget_windows"][1]["budget"] == "0.25% workflow failure budget"
    assert policy["burn_rate_alerts"][0]["condition"] == (
        "Error budget burns faster than 2x expected rate for 30 minutes."
    )
    assert policy["release_gates"][2]["status"] == "required"
    assert policy["freeze_criteria"][1]["condition"] == (
        "50% of pilot budget consumed or any critical alert remains open."
    )


def test_sparse_tact_spec_uses_defaults_and_standard_policy() -> None:
    policy = generate_error_budget_policy({"project": {"title": "Sparse Preview"}})

    assert policy["source"]["type"] == "tact_spec"
    assert policy["summary"]["title"] == "Sparse Preview"
    assert policy["summary"]["workflow_context"] == "primary workflow"
    assert policy["summary"]["target_user"] == "primary user"
    assert policy["summary"]["buyer"] == "launch sponsor"
    assert policy["summary"]["evaluation_score"] is None
    assert policy["summary"]["risk_level"] == "low"
    assert policy["summary"]["strictness"] == "standard"
    assert policy["slo_candidates"][0]["target"] == "99.0% during pilot; 99.5% after launch"
    assert policy["budget_windows"][0]["budget"] == "1.0% workflow failure budget"
    assert policy["release_gates"][2]["status"] == "recommended"
    assert policy["evidence_references"] == []


def test_render_error_budget_policy_markdown_is_deterministic(sample_unit, sample_evaluation) -> None:
    policy = generate_error_budget_policy(generate_spec_preview(sample_unit, sample_evaluation))

    first = render_error_budget_policy_markdown(policy)
    second = render_error_budget_policy_markdown(policy)

    assert first == second
    assert first.startswith("# MCP Test Framework Error Budget Policy")
    assert f"- Schema version: {ERROR_BUDGET_POLICY_SCHEMA_VERSION}" in first
    assert "- Strictness: strict" in first
    assert "## SLO Candidates" in first
    assert "## Budget Windows" in first
    assert "## Burn-Rate Alerts" in first
    assert "## Release Gates" in first
    assert "## Freeze Criteria" in first
    assert "## Owner Actions" in first
    assert "## Evidence References" in first
    assert "### SLO1: workflow_availability" in first
    assert "protocol churn" in first


def test_render_error_budget_policy_csv_is_parseable_and_stable(sample_unit, sample_evaluation) -> None:
    policy = generate_error_budget_policy(generate_spec_preview(sample_unit, sample_evaluation))

    first = render_error_budget_policy_csv(policy)
    second = render_error_budget_policy_csv(policy)
    reader = csv.DictReader(io.StringIO(first))
    rows = list(reader)

    assert first == second
    assert first.endswith("\n")
    assert reader.fieldnames == list(ERROR_BUDGET_POLICY_CSV_COLUMNS)
    assert first.splitlines()[0] == ",".join(ERROR_BUDGET_POLICY_CSV_COLUMNS)

    slo_row = next(row for row in rows if row["section"] == "slo_candidates" and row["item_id"] == "SLO1")
    assert slo_row["source_id"] == "bu-test001"
    assert slo_row["title"] == "MCP Test Framework"
    assert slo_row["strictness"] == "strict"
    assert slo_row["name"] == "workflow_availability"
    assert slo_row["target"] == "99.5% during staffed pilot windows"
    assert slo_row["owner"] == "on_call_owner"
    assert "signal:sig-test001" in slo_row["evidence_refs"]

    alert_row = next(row for row in rows if row["section"] == "burn_rate_alerts" and row["item_id"] == "BRA1")
    assert alert_row["severity"] == "critical"
    assert alert_row["condition"] == "Error budget burns faster than 2x expected rate for 30 minutes."
    assert alert_row["action"] == "Page on_call_owner and pause rollout expansion."

    gate_row = next(row for row in rows if row["section"] == "release_gates" and row["item_id"] == "RG5")
    assert gate_row["type"] == "required"
    assert gate_row["owner"] == "product_owner"


def test_error_budget_policy_is_json_serializable_and_exported(sample_unit, sample_evaluation) -> None:
    policy = exported_generate(generate_spec_preview(sample_unit, sample_evaluation))
    markdown = exported_render_markdown(policy)
    csv_text = exported_render_csv(policy)

    assert json.loads(json.dumps(policy))["source"]["idea_id"] == "bu-test001"
    assert markdown.startswith("# MCP Test Framework Error Budget Policy")
    assert csv_text.startswith(",".join(ERROR_BUDGET_POLICY_CSV_COLUMNS))

"""Tests for TactSpec API contract test plan generation."""

from __future__ import annotations

import json

from max.spec import API_CONTRACT_TEST_PLAN_KIND as exported_kind
from max.spec import API_CONTRACT_TEST_PLAN_SCHEMA_VERSION as exported_schema_version
from max.spec import generate_api_contract_test_plan as exported_generate
from max.spec import render_api_contract_test_plan_markdown as exported_render
from max.spec.api_contract_test_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_api_contract_test_plan,
    render_api_contract_test_plan_markdown,
)
from max.spec.generator import generate_spec_preview


def test_generate_api_contract_test_plan_has_stable_schema_shape(
    sample_unit, sample_evaluation
) -> None:
    spec = generate_spec_preview(sample_unit, sample_evaluation)
    spec["endpoints"] = [
        {
            "method": "POST",
            "path": "/v1/mcp/validate",
            "description": "Validate an MCP server manifest and protocol behavior.",
        }
    ]
    spec["integrations"] = [{"name": "GitHub Actions", "description": "CI consumer contract."}]
    spec["data_model"] = [
        {"name": "ValidationReport", "description": "Contract test response schema."}
    ]
    spec["acceptance_criteria"] = {
        "functional_criteria": [
            {
                "id": "AC-F1",
                "statement": "CLI validates a representative MCP server.",
            }
        ]
    }

    first = generate_api_contract_test_plan(spec)
    second = generate_api_contract_test_plan(spec)

    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["kind"] == KIND
    assert set(first) == {
        "schema_version",
        "kind",
        "summary",
        "contract_surfaces",
        "test_cases",
        "compatibility_checks",
        "traceability",
    }
    assert first["summary"]["title"] == "MCP Test Framework"
    assert first["summary"]["source_idea_id"] == "bu-test001"
    assert first["summary"]["fallback_contracts_used"] is False
    assert [surface["id"] for surface in first["contract_surfaces"]] == [
        "SURF-E1",
        "SURF-I1",
        "SURF-I2",
        "SURF-I3",
        "SURF-D1",
    ]
    assert first["contract_surfaces"][0]["name"] == "/v1/mcp/validate"
    assert first["contract_surfaces"][0]["method"] == "POST"
    assert [case["id"] for case in first["test_cases"]] == [
        "API-P1",
        "API-C1",
        "API-C2",
        "API-C3",
        "API-S1",
        "API-E1",
        "API-E2",
        "API-E3",
        "API-E4",
        "API-A1",
        "API-A2",
        "API-A3",
    ]
    assert {case["contract_type"] for case in first["test_cases"]} >= {
        "provider",
        "consumer",
        "schema_validation",
        "auth_error",
        "acceptance_trace",
    }
    assert [check["id"] for check in first["compatibility_checks"]] == [
        "COMP1",
        "COMP2",
        "COMP3",
        "COMP4",
    ]
    assert "execution.risks" in first["traceability"]["spec_fields"]
    assert "evaluation.weaknesses" in first["traceability"]["spec_fields"]
    assert "signal:sig-test001" in first["test_cases"][0]["evidence_reference_ids"]


def test_generate_api_contract_test_plan_is_json_serializable(sample_unit) -> None:
    spec = generate_spec_preview(sample_unit)

    report = generate_api_contract_test_plan(spec)

    assert json.loads(json.dumps(report))["kind"] == KIND


def test_generate_api_contract_test_plan_degrades_for_sparse_preview() -> None:
    report = generate_api_contract_test_plan(
        {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "project": {"title": "Sparse API"},
        }
    )

    assert report["summary"]["fallback_contracts_used"] is True
    assert report["contract_surfaces"] == [
        {
            "id": "SURF-F1",
            "category": "primary_contract",
            "name": "primary_workflow_contract",
            "method": "unspecified",
            "description": (
                "Conservative contract for primary workflow when explicit API surfaces "
                "are not listed."
            ),
            "source": "fallback",
            "derived_from": [
                "project.workflow_context",
                "execution.mvp_scope",
                "solution.technical_approach",
            ],
        }
    ]
    assert [case["id"] for case in report["test_cases"]] == [
        "API-P1",
        "API-C1",
        "API-S1",
        "API-E1",
        "API-E2",
        "API-A1",
    ]
    assert report["traceability"]["evidence_references"] == [
        {
            "id": "spec:fallback",
            "type": "fallback",
            "summary": (
                "No evidence references were provided; contract tests use conservative "
                "traceability defaults."
            ),
        }
    ]


def test_render_api_contract_test_plan_markdown_is_deterministic(
    sample_unit, sample_evaluation
) -> None:
    spec = generate_spec_preview(sample_unit, sample_evaluation)
    spec["endpoints"] = [{"method": "GET", "path": "/health"}]
    report = generate_api_contract_test_plan(spec)

    first = render_api_contract_test_plan_markdown(report)
    second = render_api_contract_test_plan_markdown(report)

    assert first == second
    assert first.startswith("# MCP Test Framework API Contract Test Plan")
    assert f"- Schema version: {SCHEMA_VERSION}" in first
    assert "## Contract Surfaces" in first
    assert "## Test Cases" in first
    assert "## Compatibility Checks" in first
    assert "## Evidence Traceability" in first
    assert "## Traceable Acceptance Criteria" in first
    assert "## Evidence References" in first
    for case in report["test_cases"]:
        assert f"### {case['id']}:" in first


def test_api_contract_test_plan_is_importable_from_spec_package(
    sample_unit, sample_evaluation
) -> None:
    spec = generate_spec_preview(sample_unit, sample_evaluation)

    report = exported_generate(spec)
    markdown = exported_render(report)

    assert exported_kind == KIND
    assert exported_schema_version == SCHEMA_VERSION
    assert report["schema_version"] == SCHEMA_VERSION
    assert markdown.startswith("# MCP Test Framework API Contract Test Plan")

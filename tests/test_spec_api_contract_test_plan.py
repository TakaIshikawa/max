"""Tests for TactSpec API contract test plan generation."""

from __future__ import annotations

import csv
import json
from io import StringIO

from max.spec import API_CONTRACT_TEST_PLAN_KIND as exported_kind
from max.spec import API_CONTRACT_TEST_PLAN_SCHEMA_VERSION as exported_schema_version
from max.spec import generate_api_contract_test_plan as exported_generate
from max.spec import render_api_contract_test_plan_csv as exported_render_csv
from max.spec import render_api_contract_test_plan_markdown as exported_render
from max.spec.api_contract_test_plan import (
    API_CONTRACT_TEST_PLAN_CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    generate_api_contract_test_plan,
    render_api_contract_test_plan_csv,
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


def test_render_api_contract_test_plan_csv_has_stable_header_and_sectioned_rows(
    sample_unit, sample_evaluation
) -> None:
    spec = generate_spec_preview(sample_unit, sample_evaluation)
    spec["endpoints"] = [{"method": "POST", "path": "/v1/mcp/validate"}]
    spec["integrations"] = [{"name": "GitHub Actions", "description": "CI consumer."}]
    spec["data_model"] = [{"name": "ValidationReport"}]
    report = generate_api_contract_test_plan(spec)

    rendered = render_api_contract_test_plan_csv(report)
    rows = list(csv.DictReader(StringIO(rendered)))

    assert rendered == render_api_contract_test_plan_csv(report)
    assert rendered.splitlines()[0] == ",".join(API_CONTRACT_TEST_PLAN_CSV_COLUMNS)
    assert {row["section"] for row in rows} == {
        "contract_surfaces",
        "test_cases",
        "compatibility_checks",
        "evidence_references",
    }

    surface = next(row for row in rows if row["item_id"] == "SURF-E1")
    assert surface["row_type"] == "surface"
    assert surface["surface_id"] == "SURF-E1"
    assert surface["surface_name"] == "/v1/mcp/validate"
    assert surface["method"] == "POST"
    assert surface["source"] == "spec"
    assert surface["source_fields"] == "endpoints; solution.technical_approach"


def test_render_api_contract_test_plan_csv_preserves_test_case_filter_fields(
    sample_unit, sample_evaluation
) -> None:
    spec = generate_spec_preview(sample_unit, sample_evaluation)
    spec["endpoints"] = [{"method": "GET", "path": "/health"}]
    spec["integrations"] = [{"name": "Partner API"}]
    spec["data_model"] = [{"name": "HealthReport"}]
    report = generate_api_contract_test_plan(spec)

    rows = list(csv.DictReader(StringIO(render_api_contract_test_plan_csv(report))))
    cases = {row["item_id"]: row for row in rows if row["section"] == "test_cases"}

    provider = cases["API-P1"]
    assert provider["contract_type"] == "provider"
    assert provider["surface_id"] == "SURF-E1"
    assert provider["surface_name"] == "/health"
    assert provider["priority"] == "high"
    assert provider["expected_behavior"].startswith("Request fixture receives")
    assert provider["source_fields"] == "contract_surfaces; endpoints; solution.technical_approach"
    assert "signal:sig-test001" in provider["evidence_reference_ids"]

    assert cases["API-C1"]["contract_type"] == "consumer"
    assert cases["API-C1"]["surface_id"] == "SURF-I1"
    assert cases["API-S1"]["contract_type"] == "schema_validation"
    assert cases["API-S1"]["surface_id"] == "SURF-D1"
    assert cases["API-E1"]["contract_type"] == "auth_error"
    assert cases["API-E1"]["surface_id"] == "SURF-E1"


def test_render_api_contract_test_plan_csv_includes_compatibility_and_evidence_rows(
    sample_unit, sample_evaluation
) -> None:
    spec = generate_spec_preview(sample_unit, sample_evaluation)
    spec["endpoints"] = [{"method": "GET", "path": "/health"}]
    report = generate_api_contract_test_plan(spec)

    rows = list(csv.DictReader(StringIO(render_api_contract_test_plan_csv(report))))
    compatibility = [row for row in rows if row["section"] == "compatibility_checks"]
    evidence = [row for row in rows if row["section"] == "evidence_references"]

    assert [row["item_id"] for row in compatibility] == ["COMP1", "COMP2", "COMP3", "COMP4"]
    assert compatibility[0]["row_type"] == "compatibility_check"
    assert compatibility[0]["priority"] == "medium"
    assert compatibility[0]["name"] == "backward_compatible_response_shape"
    assert compatibility[0]["expected_behavior"].startswith("Response fields used")
    assert compatibility[0]["source_fields"] == "contract_surfaces; test_cases.API-P"
    assert any(row["evidence_id"] == "signal:sig-test001" for row in evidence)
    assert all(row["row_type"] == "evidence" for row in evidence)


def test_render_api_contract_test_plan_csv_uses_csv_writer_escaping() -> None:
    report = {
        "contract_surfaces": [
            {
                "id": "SURF-Q1",
                "category": "endpoint",
                "name": '/v1/reports,"daily"',
                "method": "POST",
                "description": "Creates a report\nwith a quoted \"name\".",
                "source": "spec",
                "derived_from": ["endpoints"],
            }
        ],
        "test_cases": [
            {
                "id": "API-P1",
                "contract_type": "provider",
                "surface_id": "SURF-Q1",
                "surface_name": '/v1/reports,"daily"',
                "scenario": "Provider returns a comma, quote, and newline\ninside payload.",
                "expected_result": 'Status 200 with body field "report,name".',
                "fixture": "api_p1_fixture",
                "status": "pending",
                "derived_from": ["contract_surfaces", "endpoints"],
                "evidence_reference_ids": ["signal:quote,test"],
            }
        ],
        "compatibility_checks": [],
        "traceability": {
            "evidence_references": [
                {
                    "id": "signal:quote,test",
                    "type": "signal",
                    "summary": 'Contains comma, "quote", and newline\nfor escaping.',
                }
            ]
        },
    }

    rendered = render_api_contract_test_plan_csv(report)
    rows = list(csv.DictReader(StringIO(rendered)))

    assert '"/v1/reports,""daily"""' in rendered
    assert '"Creates a report with a quoted ""name""."' in rendered
    assert rows[0]["surface_name"] == '/v1/reports,"daily"'
    assert rows[0]["description"] == 'Creates a report with a quoted "name".'
    assert rows[1]["scenario"] == "Provider returns a comma, quote, and newline inside payload."
    assert rows[2]["evidence_summary"] == 'Contains comma, "quote", and newline for escaping.'


def test_api_contract_test_plan_is_importable_from_spec_package(
    sample_unit, sample_evaluation
) -> None:
    spec = generate_spec_preview(sample_unit, sample_evaluation)

    report = exported_generate(spec)
    markdown = exported_render(report)
    csv_text = exported_render_csv(report)

    assert exported_kind == KIND
    assert exported_schema_version == SCHEMA_VERSION
    assert report["schema_version"] == SCHEMA_VERSION
    assert markdown.startswith("# MCP Test Framework API Contract Test Plan")
    assert csv_text.startswith(",".join(API_CONTRACT_TEST_PLAN_CSV_COLUMNS))

"""Tests for stakeholder handoff generation."""

from __future__ import annotations

import csv
import json
from io import StringIO

from max.spec import render_stakeholder_handoff_csv as exported_render_csv
from max.spec.generator import generate_spec_preview
from max.spec.stakeholder_handoff import (
    STAKEHOLDER_HANDOFF_CSV_COLUMNS,
    STAKEHOLDER_HANDOFF_SCHEMA_VERSION,
    generate_stakeholder_handoff,
    render_stakeholder_handoff_csv,
    render_stakeholder_handoff_markdown,
)


def test_generate_stakeholder_handoff_maps_unit_and_spec(sample_unit, sample_evaluation):
    tact_spec = generate_spec_preview(sample_unit, sample_evaluation)

    handoff = generate_stakeholder_handoff(sample_unit, sample_evaluation, tact_spec)

    assert handoff["schema_version"] == STAKEHOLDER_HANDOFF_SCHEMA_VERSION
    assert handoff["kind"] == "max.stakeholder_handoff"
    assert handoff["idea_id"] == "bu-test001"
    assert handoff["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert handoff["summary"]["title"] == "MCP Test Framework"
    assert handoff["summary"]["target_user"] == "MCP server maintainer"
    assert handoff["summary"]["buyer"] == "developer platform lead"
    assert handoff["summary"]["recommendation"] == "yes"
    assert handoff["summary"]["overall_score"] == 78.0
    assert {role["role"] for role in handoff["owner_roles"]} >= {
        "product_owner",
        "technical_owner",
        "validation_owner",
        "launch_owner",
        "risk_owner",
    }
    assert [checkpoint["id"] for checkpoint in handoff["decision_checkpoints"]][:4] == [
        "DC1",
        "DC2",
        "DC3",
        "DC4",
    ]
    assert handoff["evidence_references"] == [
        {
            "id": "EV1",
            "type": "insight",
            "reference_id": "ins-test001",
            "description": "Problem, timing, or opportunity evidence used to create the idea.",
        },
        {
            "id": "EV2",
            "type": "signal",
            "reference_id": "sig-test001",
            "description": "Source signal supporting the idea or validation path.",
        },
    ]
    assert handoff["unresolved_risks"][0]["description"] == "protocol churn"
    assert any(risk["description"] == "Niche audience" for risk in handoff["unresolved_risks"])
    assert json.loads(json.dumps(handoff))["idea_id"] == "bu-test001"


def test_generate_stakeholder_handoff_degrades_without_evaluation_or_spec(sample_unit):
    handoff = generate_stakeholder_handoff(sample_unit)

    assert handoff["source"]["evaluation_available"] is False
    assert handoff["source"]["tact_spec_schema_version"] is None
    assert handoff["summary"]["validation_plan"] == "run against five open-source MCP servers"
    assert [checkpoint["id"] for checkpoint in handoff["decision_checkpoints"]][:2] == [
        "DC0",
        "DC1",
    ]
    assert "missing_evaluation" in {
        risk["category"] for risk in handoff["unresolved_risks"]
    }


def test_render_stakeholder_handoff_markdown_includes_handoff_sections(
    sample_unit, sample_evaluation
):
    handoff = generate_stakeholder_handoff(
        sample_unit,
        sample_evaluation,
        generate_spec_preview(sample_unit, sample_evaluation),
    )

    markdown = render_stakeholder_handoff_markdown(handoff)

    assert markdown.startswith("# MCP Test Framework Stakeholder Handoff")
    assert "- Schema version: max-stakeholder-handoff/v1" in markdown
    assert "- Idea ID: bu-test001" in markdown
    assert "## Owner Roles" in markdown
    assert "### OR1: product_owner" in markdown
    assert "## Decision Checkpoints" in markdown
    assert "### DC1: Scope confirmation" in markdown
    assert "## Evidence References" in markdown
    assert "EV1 [insight]: ins-test001" in markdown
    assert "## Launch-Readiness Questions" in markdown
    assert "## Open Risks" in markdown
    assert "protocol churn" in markdown


def test_render_stakeholder_handoff_csv_has_stable_headers_and_sections(
    sample_unit, sample_evaluation
):
    handoff = generate_stakeholder_handoff(
        sample_unit,
        sample_evaluation,
        generate_spec_preview(sample_unit, sample_evaluation),
    )

    first = render_stakeholder_handoff_csv(handoff)
    second = render_stakeholder_handoff_csv(handoff)
    reader = csv.DictReader(StringIO(first))
    rows = list(reader)

    assert first == second
    assert first.endswith("\n")
    assert reader.fieldnames == list(STAKEHOLDER_HANDOFF_CSV_COLUMNS)
    assert [row["section"] for row in rows[:4]] == [
        "summary",
        "owner_roles",
        "owner_roles",
        "owner_roles",
    ]
    assert {row["section"] for row in rows} == {
        "summary",
        "owner_roles",
        "decision_checkpoints",
        "evidence_references",
        "launch_readiness_questions",
        "unresolved_risks",
    }
    assert all(row["idea_id"] == "bu-test001" for row in rows)
    assert all(row["title"] == "MCP Test Framework" for row in rows)
    assert all(row["recommendation"] == "yes" for row in rows)
    assert all(row["overall_score"] == "78.0" for row in rows)
    assert all(row["source_status"] == handoff["source"]["status"] for row in rows)
    assert all(row["evaluation_available"] == "true" for row in rows)
    assert all(row["tact_spec_schema_version"] == "tact-spec-preview/v1" for row in rows)


def test_render_stakeholder_handoff_csv_includes_traceable_representative_rows(
    sample_unit, sample_evaluation
):
    handoff = generate_stakeholder_handoff(
        sample_unit,
        sample_evaluation,
        generate_spec_preview(sample_unit, sample_evaluation),
    )

    rows = list(csv.DictReader(StringIO(render_stakeholder_handoff_csv(handoff))))

    summary = next(row for row in rows if row["item_id"] == "SUMMARY")
    assert summary["row_type"] == "summary"
    assert summary["label"] == "MCP Test Framework"
    assert summary["role"] == "MCP server maintainer"
    assert summary["owner"] == "developer platform lead"
    assert "run against five open-source MCP servers" in summary["decision_criteria"]

    owner = next(row for row in rows if row["item_id"] == "OR1")
    assert owner["section"] == "owner_roles"
    assert owner["row_type"] == "owner_role"
    assert owner["label"] == "product_owner"
    assert owner["owner"] == "developer platform lead"
    assert "summary.primary_scope" in owner["source_references"]

    checkpoint = next(row for row in rows if row["item_id"] == "DC1")
    assert checkpoint["row_type"] == "decision_checkpoint"
    assert checkpoint["label"] == "Scope confirmation"
    assert checkpoint["role"] == "product_owner"
    assert checkpoint["timing"] == "before implementation"
    assert "A CLI tool that validates MCP server implementations" in checkpoint[
        "decision_criteria"
    ]

    evidence = next(row for row in rows if row["item_id"] == "EV2")
    assert evidence["section"] == "evidence_references"
    assert evidence["row_type"] == "evidence_reference"
    assert evidence["label"] == "sig-test001"
    assert evidence["evidence_ids"] == "EV2"
    assert evidence["source_references"] == "sig-test001"
    assert evidence["details"] == "type=signal"

    question = next(row for row in rows if row["item_id"] == "LRQ5")
    assert question["section"] == "launch_readiness_questions"
    assert question["role"] == "risk_owner"
    assert "open risks" in question["decision_criteria"]

    risk = next(row for row in rows if row["item_id"] == "UR1")
    assert risk["section"] == "unresolved_risks"
    assert risk["row_type"] == "risk"
    assert risk["label"] == "domain_risk"
    assert risk["decision_criteria"] == "protocol churn"
    assert risk["details"] == "severity=high; status=open"


def test_render_stakeholder_handoff_csv_degrades_without_evaluation_or_spec(sample_unit):
    handoff = generate_stakeholder_handoff(sample_unit)

    rows = list(csv.DictReader(StringIO(render_stakeholder_handoff_csv(handoff))))

    assert all(row["recommendation"] == "" for row in rows)
    assert all(row["overall_score"] == "" for row in rows)
    assert all(row["evaluation_available"] == "false" for row in rows)
    assert all(row["tact_spec_schema_version"] == "" for row in rows)
    assert rows[0]["section"] == "summary"
    assert any(
        row["section"] == "decision_checkpoints"
        and row["item_id"] == "DC0"
        and row["label"] == "Utility evaluation"
        for row in rows
    )
    assert any(
        row["section"] == "unresolved_risks"
        and row["label"] == "missing_evaluation"
        for row in rows
    )


def test_stakeholder_handoff_csv_is_importable_from_spec_package(
    sample_unit, sample_evaluation
):
    handoff = generate_stakeholder_handoff(sample_unit, sample_evaluation)

    csv_text = exported_render_csv(handoff)

    assert csv_text == render_stakeholder_handoff_csv(handoff)
    assert list(csv.DictReader(StringIO(csv_text)).fieldnames or []) == list(
        STAKEHOLDER_HANDOFF_CSV_COLUMNS
    )

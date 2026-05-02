from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis.design_brief_technical_feasibility import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    build_design_brief_technical_feasibility,
    render_design_brief_technical_feasibility,
    technical_feasibility_filename,
)


def _brief(**overrides) -> dict:
    brief = {
        "id": "dbf-feasibility",
        "title": "AgentAdversarialBench",
        "domain": "developer-tools",
        "theme": "agent-security-evaluation",
        "readiness_score": 86.0,
        "lead_idea_id": "bu-feasibility",
        "buyer": "engineering manager",
        "specific_user": "platform engineer",
        "workflow_context": "CI gate before deployment",
        "why_this_now": "Agent tool use is growing.",
        "merged_product_concept": "Run adversarial workflow fixtures through a CLI and GitHub integration.",
        "synthesis_rationale": "Teams need repeatable agent safety checks.",
        "mvp_scope": ["CLI runner", "GitHub check output"],
        "first_milestones": ["Prototype CLI", "Mock GitHub status integration"],
        "validation_plan": "Run with three teams using synthetic workflow data.",
        "risks": ["Framework API churn", "Customer workflow data may include PII"],
        "source_idea_ids": ["bu-feasibility"],
        "design_status": "candidate",
        "created_at": "2026-04-22T00:00:00+00:00",
        "updated_at": "2026-04-22T00:00:00+00:00",
    }
    brief.update(overrides)
    return brief


def test_build_design_brief_technical_feasibility_is_stable_and_complete() -> None:
    first = build_design_brief_technical_feasibility(_brief())
    second = build_design_brief_technical_feasibility(_brief())

    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["source"]["generated_at"] == "2026-04-22T00:00:00+00:00"
    assert first["design_brief"]["id"] == "dbf-feasibility"
    assert set(first) >= {
        "architecture_assumptions",
        "integration_surface",
        "data_dependencies",
        "build_complexity",
        "unknowns",
        "recommended_spike_plan",
        "feasibility_verdict",
    }

    assert first["feasibility_verdict"]["verdict"] in {
        "feasible_with_spikes",
        "conditionally_feasible",
        "spike_required",
    }
    assert first["feasibility_verdict"]["risk_level"] in {"low", "medium", "high"}
    assert any(item["type"] == "developer_platform" for item in first["integration_surface"])
    assert any(item["risk_level"] == "high" for item in first["data_dependencies"])
    assert first["build_complexity"]["level"] == "high"
    assert first["recommended_spike_plan"][0]["id"] == "S1"


def test_build_design_brief_technical_feasibility_adds_unknowns_for_sparse_brief() -> None:
    report = build_design_brief_technical_feasibility(
        _brief(
            workflow_context="",
            mvp_scope=[],
            first_milestones=[],
            validation_plan="",
            risks=[],
        )
    )

    unknown_text = [item["unknown"] for item in report["unknowns"]]
    assert "Target workflow boundaries are not explicit." in unknown_text
    assert "MVP scope is not decomposed." in unknown_text
    assert "Validation plan is missing." in unknown_text
    assert report["feasibility_verdict"]["risk_level"] in {"medium", "high"}


def test_render_design_brief_technical_feasibility_json_and_markdown() -> None:
    report = build_design_brief_technical_feasibility(_brief())

    parsed = json.loads(render_design_brief_technical_feasibility(report, fmt="json"))
    assert parsed == report

    markdown = render_design_brief_technical_feasibility(report, fmt="markdown")
    assert markdown.startswith("# Technical Feasibility: AgentAdversarialBench")
    assert "## Feasibility Verdict" in markdown
    assert "## Architecture Assumptions" in markdown
    assert "## Integration Surface" in markdown
    assert "## Data Dependencies" in markdown
    assert "## Build Complexity" in markdown
    assert "## Unknowns" in markdown
    assert "## Recommended Spike Plan" in markdown

    with pytest.raises(ValueError):
        render_design_brief_technical_feasibility(report, fmt="yaml")


def test_render_design_brief_technical_feasibility_csv_has_stable_headers_and_sections() -> None:
    report = build_design_brief_technical_feasibility(_brief())

    csv_text = render_design_brief_technical_feasibility(report, fmt="csv")
    repeated = render_design_brief_technical_feasibility(report, fmt="csv")
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert csv_text == repeated
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert [row["section"] for row in rows] == (
        ["architecture_assumptions"] * len(report["architecture_assumptions"])
        + ["integration_surface"] * len(report["integration_surface"])
        + ["data_dependencies"] * len(report["data_dependencies"])
        + ["unknowns"] * len(report["unknowns"])
        + ["recommended_spike_plan"] * len(report["recommended_spike_plan"])
    )
    assert len(rows) == sum(
        len(report[section])
        for section in (
            "architecture_assumptions",
            "integration_surface",
            "data_dependencies",
            "unknowns",
            "recommended_spike_plan",
        )
    )
    assert rows[0]["design_brief_id"] == "dbf-feasibility"
    assert rows[0]["design_brief_title"] == "AgentAdversarialBench"


def test_render_design_brief_technical_feasibility_csv_serializes_detail_json() -> None:
    report = build_design_brief_technical_feasibility(_brief())

    rows = list(
        csv.DictReader(StringIO(render_design_brief_technical_feasibility(report, fmt="csv")))
    )
    rows_by_id = {row["item_id"]: row for row in rows}

    assert rows_by_id["A1"]["details"] == '{"source_fields":["merged_product_concept"]}'
    assert json.loads(rows_by_id["A1"]["details"]) == {"source_fields": ["merged_product_concept"]}
    assert rows_by_id["D1"]["details"] == '{"source":"max.store.design_briefs"}'
    assert rows_by_id["S1"]["details"].startswith('{"steps":["Sketch the core workflow sequence')
    assert json.loads(rows_by_id["S1"]["details"]) == {
        "steps": report["recommended_spike_plan"][0]["steps"]
    }


def test_technical_feasibility_filename_supports_csv_extension() -> None:
    brief = _brief(id="dbf-technical/export")

    assert (
        technical_feasibility_filename(brief, fmt="markdown")
        == "dbf-technical-export-technical-feasibility.md"
    )
    assert (
        technical_feasibility_filename(brief, fmt="json")
        == "dbf-technical-export-technical-feasibility.json"
    )
    assert (
        technical_feasibility_filename(brief, fmt="csv")
        == "dbf-technical-export-technical-feasibility.csv"
    )

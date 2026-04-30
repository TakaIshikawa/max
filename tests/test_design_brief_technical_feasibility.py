from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_technical_feasibility import (
    SCHEMA_VERSION,
    build_design_brief_technical_feasibility,
    render_design_brief_technical_feasibility,
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

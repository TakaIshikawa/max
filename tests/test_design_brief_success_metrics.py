from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_success_metrics import (
    SCHEMA_VERSION,
    build_design_brief_success_metrics,
    render_design_brief_success_metrics,
    success_metrics_filename,
    write_design_brief_success_metrics,
)


def _brief(**overrides) -> dict:
    brief = {
        "id": "dbf-success",
        "title": "AgentAdversarialBench",
        "domain": "developer-tools",
        "theme": "agent-security-evaluation",
        "readiness_score": 86.0,
        "lead_idea_id": "bu-success",
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
        "source_idea_ids": ["bu-success"],
        "evidence_counts": {"signals": 4, "insights": 2, "source_ideas": 1},
        "design_status": "candidate",
        "created_at": "2026-04-22T00:00:00+00:00",
        "updated_at": "2026-04-22T00:00:00+00:00",
    }
    brief.update(overrides)
    return brief


def test_build_design_brief_success_metrics_is_stable_and_complete() -> None:
    first = build_design_brief_success_metrics(_brief())
    second = build_design_brief_success_metrics(_brief())

    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["brief_id"] == "dbf-success"
    assert first["title"] == "AgentAdversarialBench"
    assert set(first) == {
        "schema_version",
        "brief_id",
        "title",
        "north_star_metric",
        "activation_metrics",
        "retention_metrics",
        "validation_metrics",
        "risk_guardrails",
        "instrumentation_events",
        "missing_inputs",
    }

    assert first["north_star_metric"]["metric"] == "Qualified workflow success"
    assert first["north_star_metric"]["confidence"] == "high"
    assert first["activation_metrics"][0]["id"] == "A1"
    assert first["retention_metrics"][0]["id"] == "R1"
    assert first["validation_metrics"][1]["definition"] == (
        "Persisted evidence includes 7 linked evidence item(s) across 1 source idea(s)."
    )
    assert any(item["severity"] == "high" for item in first["risk_guardrails"])
    assert any(item["event"] == "first_value_reached" for item in first["instrumentation_events"])
    assert first["missing_inputs"] == []


def test_build_design_brief_success_metrics_adds_missing_inputs_for_sparse_brief() -> None:
    report = build_design_brief_success_metrics(
        _brief(
            specific_user="",
            workflow_context="",
            merged_product_concept="",
            mvp_scope=[],
            validation_plan="",
            risks=[],
            source_idea_ids=[],
            evidence_counts={},
        )
    )

    missing_fields = [item["field"] for item in report["missing_inputs"]]
    assert "specific_user" in missing_fields
    assert "workflow_context" in missing_fields
    assert "merged_product_concept" in missing_fields
    assert "mvp_scope" in missing_fields
    assert "validation_plan" in missing_fields
    assert "risks" in missing_fields
    assert "source_idea_ids" in missing_fields
    assert "evidence_counts" in missing_fields
    assert report["north_star_metric"]["confidence"] == "low"
    assert any(item["metric"] == "Uncaptured risk discovery" for item in report["risk_guardrails"])


def test_render_design_brief_success_metrics_json_and_markdown() -> None:
    report = build_design_brief_success_metrics(_brief())

    rendered_json = render_design_brief_success_metrics(report, fmt="json")
    assert rendered_json.endswith("\n")
    assert json.loads(rendered_json) == report

    markdown = render_design_brief_success_metrics(report, fmt="markdown")
    assert markdown.startswith("# Success Metrics: AgentAdversarialBench")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "## North Star Metric" in markdown
    assert "## Activation Metrics" in markdown
    assert "## Retention Metrics" in markdown
    assert "## Validation Metrics" in markdown
    assert "## Risk Guardrails" in markdown
    assert "## Instrumentation Events" in markdown
    assert "## Missing Inputs" in markdown
    assert "- None" in markdown

    with pytest.raises(ValueError):
        render_design_brief_success_metrics(report, fmt="yaml")


def test_write_design_brief_success_metrics_and_filename(tmp_path) -> None:
    report = build_design_brief_success_metrics(_brief())
    path = tmp_path / success_metrics_filename(_brief(), fmt="markdown")

    write_design_brief_success_metrics(path, report)

    assert path.name == "dbf-success-success-metrics.md"
    assert path.read_text(encoding="utf-8").startswith("# Success Metrics: AgentAdversarialBench")

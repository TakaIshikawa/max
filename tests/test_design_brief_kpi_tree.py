from __future__ import annotations

from max.analysis import generate_design_brief_kpi_tree as exported_generate
from max.analysis import render_design_brief_kpi_tree_markdown as exported_render
from max.analysis.design_brief_kpi_tree import (
    SCHEMA_VERSION,
    generate_design_brief_kpi_tree,
    render_design_brief_kpi_tree_markdown,
)


def _brief(**overrides) -> dict:
    brief = {
        "id": "dbf-kpi",
        "title": "AgentAdversarialBench",
        "domain": "developer-tools",
        "theme": "agent-security-evaluation",
        "readiness_score": 86.0,
        "lead_idea_id": "bu-kpi",
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
        "source_idea_ids": ["bu-kpi"],
        "evidence_counts": {"signals": 4, "insights": 2, "source_ideas": 1},
        "design_status": "candidate",
        "created_at": "2026-04-22T00:00:00+00:00",
        "updated_at": "2026-04-22T00:00:00+00:00",
    }
    brief.update(overrides)
    return brief


def test_generate_design_brief_kpi_tree_is_stable_and_complete() -> None:
    first = generate_design_brief_kpi_tree(_brief())
    second = generate_design_brief_kpi_tree(_brief())

    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["brief_id"] == "dbf-kpi"
    assert first["title"] == "AgentAdversarialBench"
    assert set(first) == {
        "schema_version",
        "brief_id",
        "title",
        "north_star_metric",
        "outcome_metrics",
        "input_metrics",
        "guardrail_metrics",
        "measurement_plan",
    }
    assert first["north_star_metric"]["metric"] == "Qualified workflow success"
    assert first["north_star_metric"]["owner"] == "Product lead with engineering manager"
    assert first["north_star_metric"]["children"] == ["O1", "O2", "O3"]
    assert first["outcome_metrics"][0]["id"] == "O1"
    assert first["input_metrics"][0]["parent_id"] == "O2"
    assert any(metric["owner"] == "Security and compliance owner" for metric in first["guardrail_metrics"])
    assert "idea:bu-kpi" in first["measurement_plan"]["source_reference_ids"]
    assert first["measurement_plan"]["open_questions"] == []


def test_generate_design_brief_kpi_tree_handles_sparse_briefs() -> None:
    report = generate_design_brief_kpi_tree(
        {
            "id": "dbf-sparse",
            "title": "",
            "readiness_score": None,
            "mvp_scope": [],
            "risks": [],
            "source_idea_ids": [],
            "evidence_counts": {},
        }
    )

    assert report["title"] == "Untitled Design Brief"
    assert report["north_star_metric"]["target"] == "1+ qualified teams reach repeatable workflow success within 30 days."
    assert report["outcome_metrics"][1]["definition"] == (
        "Qualified users complete the first MVP value path described by the first validation plan."
    )
    assert any(metric["metric"] == "Uncaptured risk discovery" for metric in report["guardrail_metrics"])
    assert report["measurement_plan"]["source_reference_ids"] == ["brief:fallback"]
    assert "Name the specific user segment that qualifies KPI measurements." in report["measurement_plan"]["open_questions"]


def test_render_design_brief_kpi_tree_markdown_includes_hierarchy_owners_cadence_and_evidence() -> None:
    report = generate_design_brief_kpi_tree(_brief())

    markdown = render_design_brief_kpi_tree_markdown(report)

    assert markdown.startswith("# KPI Tree: AgentAdversarialBench")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "## North-Star Metric" in markdown
    assert "- **Owner**: Product lead with engineering manager" in markdown
    assert "- **Cadence**: Weekly during validation, then monthly after launch" in markdown
    assert "## Metric Hierarchy" in markdown
    assert "### Outcome Metrics" in markdown
    assert "### Input Metrics" in markdown
    assert "### Guardrail Metrics" in markdown
    assert "**I1 Qualified setup starts** (parent: `O2`)" in markdown
    assert "Evidence/source ideas: `idea:bu-kpi`, `brief:evidence_counts`, `brief:validation_plan`" in markdown
    assert "## Measurement Plan" in markdown
    assert "### Instrumentation Events" in markdown
    assert "### Evidence References" in markdown


def test_design_brief_kpi_tree_is_importable_from_analysis_package() -> None:
    report = exported_generate(_brief())
    markdown = exported_render(report)

    assert report["north_star_metric"]["id"] == "NS1"
    assert markdown.startswith("# KPI Tree: AgentAdversarialBench")

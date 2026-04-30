from __future__ import annotations

from max.analysis.design_brief_okrs import (
    SCHEMA_VERSION,
    build_design_brief_okrs,
    render_design_brief_okrs_markdown,
)


def _brief(**overrides) -> dict:
    brief = {
        "id": "dbf-okrs",
        "title": "AgentAdversarialBench",
        "domain": "developer-tools",
        "theme": "agent-security-evaluation",
        "readiness_score": 88.0,
        "lead_idea_id": "bu-okrs",
        "buyer": "engineering manager",
        "specific_user": "platform engineer",
        "workflow_context": "CI gate before deployment",
        "why_this_now": "Agent tool use is growing.",
        "merged_product_concept": "Run adversarial workflow fixtures through a CLI and GitHub integration.",
        "synthesis_rationale": "Teams need repeatable agent safety checks.",
        "mvp_scope": ["CLI runner", "GitHub check output"],
        "first_milestones": ["Prototype CLI", "Mock GitHub status integration"],
        "validation_plan": "Run with three teams using synthetic workflow data.",
        "risks": [],
        "source_idea_ids": ["bu-okrs"],
        "design_status": "candidate",
        "created_at": "2026-04-22T00:00:00+00:00",
        "updated_at": "2026-04-22T00:00:00+00:00",
        "evaluation_scores": [{"id": "bu-okrs", "overall_score": 84.0, "recommendation": "build"}],
        "validation_experiments": [
            {
                "title": "Synthetic workflow pilot",
                "success_metric": "2 of 3 teams complete the CI fixture run",
            }
        ],
        "roadmap_items": [
            {
                "title": "Prototype CLI",
                "phase": "prototype",
                "owner_role": "Engineering lead",
                "exit_criteria": "CLI runs fixtures locally.",
            }
        ],
    }
    brief.update(overrides)
    return brief


def test_build_design_brief_okrs_returns_measurable_high_confidence_okrs() -> None:
    first = build_design_brief_okrs(_brief())
    second = build_design_brief_okrs(_brief())

    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["source"]["generated_at"] == "2026-04-22T00:00:00+00:00"
    assert first["design_brief"]["id"] == "dbf-okrs"
    assert first["confidence"]["level"] == "high"
    assert first["risk_summary"]["level"] == "low"
    assert first["summary"]["validation_required"] is False
    assert len(first["objectives"]) == 3
    assert all(objective["owner_hint"] for objective in first["objectives"])
    assert all(objective["confidence"] in {"low", "medium", "high"} for objective in first["objectives"])
    assert all(objective["risk_level"] in {"low", "medium", "high"} for objective in first["objectives"])
    assert all(
        {"id", "metric", "target", "evidence_source"} <= set(key_result)
        for objective in first["objectives"]
        for key_result in objective["key_results"]
    )


def test_build_design_brief_okrs_adds_validation_key_results_for_risky_or_weak_evidence_briefs() -> None:
    report = build_design_brief_okrs(
        _brief(
            readiness_score=42.0,
            validation_plan="",
            validation_experiments=[],
            roadmap_items=[],
            evaluation_scores=[],
            risks=["Customer workflow data may include PII.", "GitHub API churn could block checks."],
        )
    )

    assert report["confidence"]["level"] == "low"
    assert report["risk_summary"]["level"] == "high"
    assert report["risk_summary"]["weak_evidence"] is True
    assert report["summary"]["validation_required"] is True
    assert [objective["id"] for objective in report["objectives"]] == ["O1", "O2", "O3", "O4"]
    all_key_results = [
        key_result
        for objective in report["objectives"]
        for key_result in objective["key_results"]
    ]
    assert any("validation experiment" in key_result["metric"].lower() for key_result in all_key_results)
    assert any(key_result["evidence_source"] == "Risk register" for key_result in all_key_results)


def test_build_design_brief_okrs_handles_missing_optional_artifacts() -> None:
    report = build_design_brief_okrs(
        _brief(
            mvp_scope=[],
            first_milestones=[],
            validation_plan="",
            risks=[],
            evaluation_scores=None,
            validation_experiments=None,
            roadmap_items=None,
        )
    )

    assert report["evaluation_scores"] == []
    assert report["validation_experiments"] == []
    assert report["roadmap_items"] == []
    assert report["risk_summary"]["level"] == "medium"
    assert report["objectives"][1]["key_results"][0]["metric"] == "Ship core product workflow in a testable MVP slice"


def test_render_design_brief_okrs_markdown_uses_stable_headings_and_bullets() -> None:
    report = build_design_brief_okrs(_brief())

    markdown = render_design_brief_okrs_markdown(report)

    assert markdown.startswith("# OKRs: AgentAdversarialBench")
    assert "Schema: `max.design_brief.okrs.v1`" in markdown
    assert "## Summary" in markdown
    assert "## Objectives" in markdown
    assert "### O1: Validate demand for AgentAdversarialBench" in markdown
    assert "- Owner hint: Product lead with engineering manager" in markdown
    assert "- Key results:" in markdown
    assert "  - **KR1**:" in markdown
    assert "## Risk Annotations" in markdown

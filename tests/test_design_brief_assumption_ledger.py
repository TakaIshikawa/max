"""Tests for design brief assumption ledger generation."""

from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_assumption_ledger import (
    SCHEMA_VERSION,
    assumption_ledger_filename,
    build_design_brief_assumption_ledger,
    render_design_brief_assumption_ledger,
    write_design_brief_assumption_ledger,
)


def test_build_design_brief_assumption_ledger_groups_assumptions_and_evidence() -> None:
    first = build_design_brief_assumption_ledger(_brief())
    second = build_design_brief_assumption_ledger(_brief())

    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["kind"] == "max.design_brief.assumption_ledger"
    assert first["design_brief"]["id"] == "dbf-ledger-001"
    assert [group["id"] for group in first["assumption_groups"]] == [
        "desirability",
        "feasibility",
        "viability",
        "go_to_market",
    ]
    assert first["summary"]["assumption_count"] >= 8
    assert first["summary"]["evidence_link_count"] >= 4
    assert first["next_validation_actions"]

    by_group = {group["id"]: group for group in first["assumption_groups"]}
    assert any(
        "platform engineer has a recurring problem" in assumption["statement"]
        for assumption in by_group["desirability"]["assumptions"]
    )
    assert any(
        "technical approach" in assumption["statement"]
        for assumption in by_group["feasibility"]["assumptions"]
    )
    assert any(
        "VP of Engineering" in assumption["statement"]
        for assumption in by_group["viability"]["assumptions"]
    )
    assert any(
        "platform teams shipping production agents" in assumption["statement"]
        for assumption in by_group["go_to_market"]["assumptions"]
    )

    all_assumptions = [
        assumption for group in first["assumption_groups"] for assumption in group["assumptions"]
    ]
    assert {assumption["confidence_level"] for assumption in all_assumptions} <= {
        "low",
        "medium",
        "high",
    }
    assert any(assumption["evidence_links"] for assumption in all_assumptions)
    assert all(assumption["validation_action"] for assumption in all_assumptions)
    assert all(assumption["owner_hint"] for assumption in all_assumptions)
    assert json.loads(json.dumps(first))["schema_version"] == SCHEMA_VERSION


def test_build_design_brief_assumption_ledger_sparse_brief_has_actionable_fallbacks() -> None:
    ledger = build_design_brief_assumption_ledger(
        {
            "id": "dbf-sparse",
            "title": "Sparse Brief",
        }
    )

    assert ledger["design_brief"]["id"] == "dbf-sparse"
    assert [len(group["assumptions"]) for group in ledger["assumption_groups"]] == [
        1,
        1,
        1,
        1,
    ]
    assert ledger["summary"]["low_confidence_count"] == 4
    assert ledger["unresolved_assumptions"]
    assert any(
        "Attach evidence links" in assumption for assumption in ledger["unresolved_assumptions"]
    )
    assert all(
        "Prioritize filling or falsifying" in group["assumptions"][0]["validation_action"]
        for group in ledger["assumption_groups"]
    )


def test_render_design_brief_assumption_ledger_markdown_json_and_invalid_format() -> None:
    ledger = build_design_brief_assumption_ledger(_brief())

    markdown = render_design_brief_assumption_ledger(ledger, fmt="markdown")
    assert markdown.startswith("# Assumption Ledger: Assumption Ledger Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "Design brief: `dbf-ledger-001`" in markdown
    assert "### Desirability" in markdown
    assert "### Feasibility" in markdown
    assert "### Viability" in markdown
    assert "### Go-to-Market" in markdown
    assert "Confidence: `" in markdown
    assert "Validation action:" in markdown
    assert "## Next Validation Actions" in markdown

    parsed = json.loads(render_design_brief_assumption_ledger(ledger, fmt="json"))
    assert parsed["schema_version"] == SCHEMA_VERSION

    with pytest.raises(ValueError, match="Unsupported assumption ledger format: yaml"):
        render_design_brief_assumption_ledger(ledger, fmt="yaml")


def test_write_design_brief_assumption_ledger_and_filename(tmp_path) -> None:
    ledger = build_design_brief_assumption_ledger(_brief())
    path = tmp_path / assumption_ledger_filename(_brief(), fmt="markdown")

    write_design_brief_assumption_ledger(path, ledger)

    assert path.name == "dbf-ledger-001-assumption-ledger.md"
    assert path.read_text(encoding="utf-8").startswith(
        "# Assumption Ledger: Assumption Ledger Brief"
    )
    assert (
        assumption_ledger_filename({"id": "dbf-ledger-001"}, fmt="json")
        == "dbf-ledger-001-assumption-ledger.json"
    )


def _brief() -> dict[str, object]:
    return {
        "id": "dbf-ledger-001",
        "title": "Assumption Ledger Brief",
        "domain": "developer-tools",
        "theme": "agent-release-governance",
        "lead_idea_id": "bu-ledger-lead",
        "source_idea_ids": ["bu-ledger-lead", "bu-ledger-support"],
        "readiness_score": 86.0,
        "design_status": "approved",
        "specific_user": "platform engineer",
        "buyer": "VP of Engineering",
        "workflow_context": "agent release governance review",
        "problem": "Platform teams cannot see which releases need governance review.",
        "current_workaround": "manual release notes and ad hoc approval chats",
        "why_this_now": "Agent releases are moving from experiments into production.",
        "merged_product_concept": "A release governance brief that names assumptions before build.",
        "value_proposition": "Reduce approval delays and make release risk explicit.",
        "mvp_scope": ["JSON assumption ledger", "Markdown assumption ledger"],
        "first_milestones": ["Generate deterministic ledger"],
        "tech_approach": "Deterministic Python report over persisted design brief records.",
        "suggested_stack": {"language": "python"},
        "risks": ["Security approval may block rollout."],
        "validation_plan": "Interview platform engineers and engineering buyers before implementation.",
        "success_metric": "4 of 6 interviewees confirm the release governance workflow is urgent.",
        "first_10_customers": "platform teams shipping production agents",
        "evidence_counts": {"signals": 2, "insights": 1, "source_ideas": 2},
        "evidence_signals": ["sig-budget", "sig-user-pain"],
        "inspiring_insights": ["ins-release-governance"],
    }

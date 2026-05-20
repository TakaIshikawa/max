from __future__ import annotations

from max.analysis.profile_backfill_plan import (
    build_profile_backfill_plan,
    render_profile_backfill_plan_markdown,
)


def test_profile_backfill_plan_identifies_missing_and_under_threshold_categories() -> None:
    plan = build_profile_backfill_plan(
        [
            {"profile": "buyer", "category": "jobs", "target_count": 3, "suggested_sources": ["calls"]},
            {"profile": "buyer", "category": "budget", "target_count": 2, "suggested_sources": ["crm"]},
            {"profile": "admin", "category": "security", "target_count": 1},
        ],
        [
            {"profile": "buyer", "category": "jobs", "count": 1},
            {"profile": "admin", "category": "security", "count": 1},
        ],
    )

    assert plan["schema_version"] == "max.profile_backfill_plan.v1"
    assert plan["kind"] == "max.profile_backfill_plan"
    assert plan["summary"]["required_category_count"] == 3
    assert plan["summary"]["backfill_count"] == 2
    rows = {(row["profile"], row["category"]): row for row in plan["backfill_rows"]}
    assert rows[("buyer", "jobs")]["current_count"] == 1
    assert rows[("buyer", "jobs")]["gap_size"] == 2
    assert rows[("buyer", "budget")]["current_count"] == 0


def test_profile_backfill_plan_includes_recommendation_fields_and_priority() -> None:
    plan = build_profile_backfill_plan(
        [
            {"profile": "buyer", "category": "jobs", "target_count": 4, "sources": ["calls", "survey"]},
            {"profile": "buyer", "category": "tools", "target_count": 4, "sources": ["enrichment"]},
        ],
        [
            {"profile": "buyer", "category": "jobs", "count": 3},
            {"profile": "buyer", "category": "tools", "count": 1},
        ],
    )

    assert [row["category"] for row in plan["backfill_rows"]] == ["tools", "jobs"]
    critical = plan["backfill_rows"][0]
    moderate = plan["backfill_rows"][1]
    assert critical["priority"] == "critical"
    assert moderate["priority"] == "moderate"
    assert critical["suggested_sources"] == ["enrichment"]
    assert "backfill 3 evidence item(s)" in critical["recommendation"]


def test_profile_backfill_plan_uses_default_sources_for_missing_suggestions() -> None:
    plan = build_profile_backfill_plan(
        [{"profile": "admin", "category": "compliance", "target_count": 2}],
        [],
    )

    row = plan["backfill_rows"][0]
    assert row["suggested_sources"] == ["customer_interviews", "support_tickets"]
    assert row["priority"] == "critical"


def test_profile_backfill_plan_markdown_groups_critical_before_moderate() -> None:
    plan = build_profile_backfill_plan(
        [
            {"profile": "buyer", "category": "jobs", "target_count": 4, "sources": ["calls"]},
            {"profile": "buyer", "category": "tools", "target_count": 4, "sources": ["survey"]},
        ],
        [
            {"profile": "buyer", "category": "jobs", "count": 3},
            {"profile": "buyer", "category": "tools", "count": 0},
        ],
    )

    first = render_profile_backfill_plan_markdown(plan)
    second = render_profile_backfill_plan_markdown(plan)

    assert first == second
    assert first.startswith("# Profile Backfill Plan")
    assert first.index("## Critical Gaps") < first.index("## Moderate Gaps")
    assert first.index("buyer / tools") < first.index("buyer / jobs")
    assert "- Suggested sources:" in first
    assert "- Priority:" in first

"""Tests for profile signal query plan generation."""

from __future__ import annotations

import json

import pytest

from max.analysis.profile_signal_query_plan import (
    SCHEMA_VERSION,
    build_profile_signal_query_plan,
    build_profile_signal_query_plan_by_name,
    profile_signal_query_plan_filename,
    render_profile_signal_query_plan,
    write_profile_signal_query_plan,
)
from max.profiles.loader import load_profile
from max.profiles.schema import DomainContext, PipelineProfile, SourceConfig


def test_devtools_profile_produces_multiple_source_query_entries() -> None:
    first = build_profile_signal_query_plan(load_profile("devtools"))
    second = build_profile_signal_query_plan(load_profile("devtools"))

    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["kind"] == "max.profile.signal_query_plan"
    assert first["profile"]["name"] == "devtools"
    assert first["profile"]["domain"] == "developer-tools"
    assert first["summary"]["enabled_source_count"] > 5
    assert first["summary"]["source_entry_count"] == first["summary"]["enabled_source_count"]
    assert first["summary"]["suggested_query_count"] >= first["summary"]["enabled_source_count"]
    assert json.loads(json.dumps(first))["schema_version"] == SCHEMA_VERSION

    adapters = [source["adapter"] for source in first["sources"]]
    assert "hackernews" in adapters
    assert "reddit" in adapters
    assert "github_issues" in adapters


def test_suggested_queries_include_domain_category_and_user_language() -> None:
    plan = build_profile_signal_query_plan(load_profile("devtools"))
    query_text = " ".join(
        query
        for source in plan["sources"]
        for query in source["suggested_queries"]
    ).lower()

    assert "developer-tools" in query_text
    assert "mcp_server" in query_text
    assert "humans" in query_text or "ai tool builders" in query_text
    assert any("local development" in query for source in plan["sources"] for query in source["suggested_queries"])
    assert any(
        source["adapter"] == "github_issues" and '"developer-tools" is:open' in source["suggested_queries"]
        for source in plan["sources"]
    )


def test_report_identifies_missing_or_weak_profile_inputs_without_failing() -> None:
    profile = PipelineProfile(
        name="sparse",
        domain=DomainContext(
            name="tiny",
            description="Short",
            categories=[],
            target_user_types=[],
        ),
        sources=[SourceConfig(adapter="hackernews")],
    )

    plan = build_profile_signal_query_plan(profile)

    gaps = {(gap["field"], gap["severity"]) for gap in plan["gaps"]}
    assert ("domain.categories", "missing") in gaps
    assert ("domain.target_user_types", "missing") in gaps
    assert ("domain.description", "weak") in gaps
    assert ("sources.hackernews.params", "weak") in gaps
    assert plan["sources"][0]["suggested_queries"] == ["tiny signal discovery"]
    assert plan["sources"][0]["freshness_window"] == "14 days"


def test_markdown_output_is_stable_and_includes_sources_queries_and_freshness() -> None:
    plan = build_profile_signal_query_plan_by_name("devtools")

    markdown = render_profile_signal_query_plan(plan, fmt="markdown")

    assert markdown.startswith("# Profile Signal Query Plan: devtools")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "Domain: `developer-tools`" in markdown
    assert "## Source Queries" in markdown
    assert "| Source | Query Terms | Suggested Queries | Freshness Window | Expected Signal Roles |" in markdown
    assert "`hackernews`" in markdown
    assert "`developer`" in markdown
    assert "developer-tools mcp_server for humans" in markdown
    assert "14 days" in markdown
    assert "30 days" in markdown
    assert "## Gaps" in markdown

    parsed = json.loads(render_profile_signal_query_plan(plan, fmt="json"))
    assert parsed["schema_version"] == SCHEMA_VERSION

    with pytest.raises(ValueError, match="Unsupported profile signal query plan format: yaml"):
        render_profile_signal_query_plan(plan, fmt="yaml")


def test_write_profile_signal_query_plan_and_filename(tmp_path) -> None:
    profile = load_profile("devtools")
    plan = build_profile_signal_query_plan(profile)
    path = tmp_path / profile_signal_query_plan_filename(profile, fmt="markdown")

    write_profile_signal_query_plan(path, plan)

    assert path.name == "devtools-signal-query-plan.md"
    assert path.read_text(encoding="utf-8").startswith("# Profile Signal Query Plan: devtools")
    assert (
        profile_signal_query_plan_filename({"name": "devtools"}, fmt="json")
        == "devtools-signal-query-plan.json"
    )

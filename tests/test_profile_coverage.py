"""Tests for profile signal coverage analysis."""

from __future__ import annotations

from max.analysis.profile_coverage import (
    compute_profile_coverage_gaps,
    compute_profile_coverage_matrix,
)
from max.profiles.schema import DomainContext, PipelineProfile, SourceConfig
from max.types.signal import Signal, SignalSourceType


def _coverage_profile() -> PipelineProfile:
    return PipelineProfile(
        name="coverage",
        domain=DomainContext(
            name="testing",
            description="testing domain",
            categories=["mcp", "workflow automation"],
            target_user_types=["developers"],
        ),
        sources=[
            SourceConfig(
                adapter="hackernews",
                watchlist=["mcp", "agent testing"],
                params={"filter_keywords": ["developer workflow"]},
            ),
            SourceConfig(
                adapter="reddit",
                params={"queries": ["agent testing", "uncovered term"]},
            ),
            SourceConfig(
                adapter="github",
                enabled=False,
                params={"topics": ["disabled only"]},
            ),
        ],
    )


def test_profile_coverage_reports_uncovered_watchlist_terms(store) -> None:
    store.insert_signal(
        Signal(
            id="sig-covered-title",
            source_type=SignalSourceType.FORUM,
            source_adapter="hackernews",
            title="MCP server testing catches integration gaps",
            content="Tooling for agents",
            url="https://example.com/covered-title",
            tags=["devtools"],
        )
    )
    store.insert_signal(
        Signal(
            id="sig-covered-tag",
            source_type=SignalSourceType.FORUM,
            source_adapter="hackernews",
            title="A workflow note",
            content="Useful for platform teams",
            url="https://example.com/covered-tag",
            tags=["developer workflow"],
        )
    )

    report = compute_profile_coverage_gaps(_coverage_profile(), store)

    gaps = {term.term: term for term in report.terms}
    assert report.profile_name == "coverage"
    assert report.enabled_adapters == ["hackernews", "reddit"]
    assert "mcp" not in gaps
    assert "developer workflow" not in gaps
    assert gaps["agent testing"].adapter_counts == {"hackernews": 0, "reddit": 0}
    assert gaps["agent testing"].suggested_source_adapters == ["hackernews", "reddit"]
    assert gaps["uncovered term"].enabled_adapters == ["reddit"]
    assert "disabled only" not in gaps


def test_profile_coverage_counts_content_matches_and_ignores_archived(store) -> None:
    profile = PipelineProfile(
        name="content",
        domain=DomainContext(
            name="testing",
            description="testing domain",
            categories=["workflow automation"],
            target_user_types=["developers"],
        ),
        sources=[
            SourceConfig(adapter="reddit", params={"queries": ["agent testing"]}),
        ],
    )
    store.insert_signal(
        Signal(
            id="sig-content",
            source_type=SignalSourceType.FORUM,
            source_adapter="reddit",
            title="Release notes",
            content="Teams need better agent testing in CI.",
            url="https://example.com/content",
            tags=[],
        )
    )
    store.insert_signal(
        Signal(
            id="sig-archived",
            source_type=SignalSourceType.FORUM,
            source_adapter="reddit",
            title="Workflow automation",
            content="Archived coverage should not count",
            url="https://example.com/archived",
            tags=[],
        )
    )
    store.archive_signal("sig-archived")

    report = compute_profile_coverage_gaps(profile, store)

    gaps = {term.term: term for term in report.terms}
    assert "agent testing" not in gaps
    assert gaps["workflow automation"].total_count == 0
    assert gaps["workflow automation"].adapter_counts == {"reddit": 0}


def test_profile_coverage_matrix_includes_covered_and_undercovered_terms(store) -> None:
    store.insert_signal(
        Signal(
            id="sig-mcp-hn",
            source_type=SignalSourceType.FORUM,
            source_adapter="hackernews",
            title="MCP support for agents",
            content="A launch note",
            url="https://example.com/mcp",
            tags=[],
        )
    )
    store.insert_signal(
        Signal(
            id="sig-workflow-reddit",
            source_type=SignalSourceType.FORUM,
            source_adapter="reddit",
            title="Workflow automation playbook",
            content="Teams compare options",
            url="https://example.com/workflow",
            tags=[],
        )
    )

    matrix = compute_profile_coverage_matrix(_coverage_profile(), store)

    rows = {row.term: row for row in matrix.rows}
    assert matrix.profile_name == "coverage"
    assert matrix.enabled_adapters == ["hackernews", "reddit"]
    assert list(rows) == [
        "workflow automation",
        "mcp",
        "agent testing",
        "developer workflow",
        "uncovered term",
    ]
    assert rows["mcp"].term_type == "category+watchlist"
    assert rows["mcp"].status == "covered"
    assert rows["mcp"].adapter_counts == {"hackernews": 1, "reddit": 0}
    assert rows["workflow automation"].status == "covered"
    assert rows["agent testing"].status == "undercovered"
    assert rows["agent testing"].recommended_adapters == ["hackernews", "reddit"]
    assert "disabled only" not in rows

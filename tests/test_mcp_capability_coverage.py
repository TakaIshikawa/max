"""Tests for MCP capability coverage analysis."""

from __future__ import annotations

from max.analysis.mcp_capability_coverage import (
    build_mcp_capability_coverage_report,
    classify_mcp_capability,
)
from max.store.db import Store
from max.types.signal import Signal, SignalSourceType


def _insert_signal(
    store: Store,
    *,
    signal_id: str,
    source_adapter: str,
    title: str,
    content: str = "MCP server",
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> None:
    store.insert_signal(
        Signal(
            id=signal_id,
            source_type=SignalSourceType.REGISTRY,
            source_adapter=source_adapter,
            title=title,
            content=content,
            url=f"https://example.com/{signal_id}",
            tags=["mcp"] if tags is None else tags,
            metadata=metadata or {},
        )
    )


def test_classify_mcp_capability_uses_tags_title_content_and_metadata() -> None:
    assert (
        classify_mcp_capability(
            {
                "title": "Generic MCP connector",
                "content": "",
                "tags": ["observability"],
                "metadata": {},
            }
        )
        == "observability"
    )
    assert (
        classify_mcp_capability(
            {
                "title": "MCP server",
                "content": "Connects agents to tools",
                "tags": [],
                "metadata": {"capability": "FHIR patient records"},
            }
        )
        == "healthcare"
    )
    assert (
        classify_mcp_capability(
            {
                "title": "MCP server",
                "content": "Connects agents to tools",
                "tags": [],
                "metadata": {},
            }
        )
        == "unknown"
    )


def test_build_mcp_capability_coverage_counts_categories_and_adapters(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "coverage.db"))
    try:
        _insert_signal(
            store,
            signal_id="sig-filesystem",
            source_adapter="mcp_registry",
            title="Filesystem MCP server",
            content="Read files and directories",
        )
        _insert_signal(
            store,
            signal_id="sig-browser",
            source_adapter="npm_registry",
            title="Browser automation MCP",
            content="Playwright browser tools",
        )
        _insert_signal(
            store,
            signal_id="sig-security",
            source_adapter="github",
            title="Security audit MCP",
            content="Find secrets and CVEs",
        )
        _insert_signal(
            store,
            signal_id="sig-healthcare",
            source_adapter="awesome_lists",
            title="Clinical MCP connector",
            content="FHIR patient workflow",
            tags=["mcp", "healthcare"],
            metadata={"domain": "healthcare"},
        )
        _insert_signal(
            store,
            signal_id="sig-unknown",
            source_adapter="mcp_registry",
            title="Generic MCP tools",
        )
        _insert_signal(
            store,
            signal_id="sig-unrelated",
            source_adapter="reddit",
            title="General developer tool",
            content="No protocol mention",
            tags=[],
        )

        report = build_mcp_capability_coverage_report(
            store,
            min_count=2,
            limit_representatives=1,
        )
    finally:
        store.close()

    by_category = {category.category: category for category in report.categories}
    assert report.total_signals == 5
    assert by_category["filesystem"].total_count == 1
    assert by_category["browser"].total_count == 1
    assert by_category["security"].source_adapters == {"github": 1}
    assert by_category["unknown"].total_count == 1
    assert len(by_category["filesystem"].representative_signal_ids) == 1
    assert report.category_percentages["filesystem"] == 20.0
    assert "finance" in report.undercovered_categories
    assert "filesystem" in report.undercovered_categories

    by_adapter = {adapter.source_adapter: adapter for adapter in report.top_source_adapters}
    assert by_adapter["mcp_registry"].total_count == 2
    assert by_adapter["mcp_registry"].categories == {"filesystem": 1, "unknown": 1}


def test_build_mcp_capability_coverage_filters_domain_and_source_adapter(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "coverage_filters.db"))
    try:
        _insert_signal(
            store,
            signal_id="sig-healthcare",
            source_adapter="awesome_lists",
            title="Clinical MCP connector",
            content="FHIR patient data",
            tags=["mcp", "healthcare"],
            metadata={"domain": "healthcare"},
        )
        _insert_signal(
            store,
            signal_id="sig-finance",
            source_adapter="npm_registry",
            title="Finance MCP connector",
            content="Payments and ledger data",
            tags=["mcp", "finance"],
            metadata={"domain": "finance"},
        )

        report = build_mcp_capability_coverage_report(
            store,
            domain="healthcare",
            source_adapter="awesome_lists",
        )
    finally:
        store.close()

    by_category = {category.category: category for category in report.categories}
    assert report.total_signals == 1
    assert report.domain == "healthcare"
    assert report.source_adapter_filter == "awesome_lists"
    assert by_category["healthcare"].total_count == 1
    assert by_category["finance"].total_count == 0

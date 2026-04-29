"""Tests for the Glama MCP ecosystem stats adapter."""

from __future__ import annotations

import json

import pytest

from max.sources.glama_mcp_stats import GlamaMcpStatsAdapter
from max.types.signal import SignalSourceType


def test_string_list_config_values_filter_blanks_and_deduplicate() -> None:
    adapter = GlamaMcpStatsAdapter(
        config={
            "local_paths": ["", " /tmp/glama.json ", "/tmp/glama.json", "  ", "/tmp/other.json"],
            "categories": (" Developer Tools ", "", "Developer Tools", "Data"),
        }
    )

    assert adapter.local_paths == ["/tmp/glama.json", "/tmp/other.json"]
    assert adapter.categories == ["Developer Tools", "Data"]


def test_scalar_string_list_config_values_are_ignored_safely() -> None:
    adapter = GlamaMcpStatsAdapter(
        config={
            "stats_urls": 123,
            "local_paths": False,
            "categories": 12.5,
        }
    )

    assert adapter.stats_urls == []
    assert adapter.local_paths == []
    assert adapter.categories == []


@pytest.mark.asyncio
async def test_json_snapshot_emits_aggregate_mcp_ecosystem_signals(tmp_path) -> None:
    report_path = tmp_path / "glama-mcp-stats.json"
    report_path.write_text(
        json.dumps(
            {
                "snapshot_date": "2026-04-20",
                "source_url": "https://glama.ai/mcp/stats",
                "summary": {
                    "server_count": 2480,
                    "sdk_downloads": 1250000,
                    "investment_usd": 42000000,
                },
                "categories": [
                    {
                        "category": "Developer Tools",
                        "server_count": 620,
                        "verified_servers": 144,
                    },
                    {
                        "category": "Data",
                        "server_count": 180,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    adapter = GlamaMcpStatsAdapter(config={"local_paths": [str(report_path)]})

    signals = await adapter.fetch(limit=20)

    by_metric = {
        (signal.metadata["category"], signal.metadata["metric_name"]): signal
        for signal in signals
    }
    assert (None, "server_count") in by_metric
    assert (None, "sdk_downloads") in by_metric
    assert ("Developer Tools", "server_count") in by_metric
    assert ("Developer Tools", "verified_servers") in by_metric

    server_count = by_metric[(None, "server_count")]
    assert server_count.source_type == SignalSourceType.REPORT
    assert server_count.source_adapter == "glama_mcp_stats"
    assert server_count.url == "https://glama.ai/mcp/stats"
    assert server_count.author == "Glama MCP Stats"
    assert server_count.metadata["metric_value"] == 2480
    assert server_count.metadata["snapshot_date"] == "2026-04-20"
    assert server_count.metadata["source_url"] == "https://glama.ai/mcp/stats"
    assert server_count.metadata["signal_role"] == "market"
    assert server_count.metadata["adapter_scope"] == "aggregate_ecosystem_stats"


@pytest.mark.asyncio
async def test_markdown_table_rows_are_extracted_as_metric_signals(tmp_path) -> None:
    report_path = tmp_path / "glama-report.md"
    report_path.write_text(
        "| Category | Server Count | SDK Downloads | Snapshot Date |\n"
        "| --- | ---: | ---: | --- |\n"
        "| Developer Tools | 620 | 1,250,000 | 2026-04-20 |\n"
        "| Data | 180 | 260,000 | 2026-04-20 |\n\n"
        "| Metric | Value | Category | Source URL |\n"
        "| --- | ---: | --- | --- |\n"
        "| Verified Servers | 144 | Developer Tools | https://glama.ai/mcp/stats |\n",
        encoding="utf-8",
    )
    adapter = GlamaMcpStatsAdapter(config={"local_paths": [str(report_path)]})

    signals = await adapter.fetch(limit=20)

    rows = {(signal.metadata["category"], signal.metadata["metric_name"]) for signal in signals}
    assert rows == {
        ("Developer Tools", "server_count"),
        ("Developer Tools", "sdk_downloads"),
        ("Data", "server_count"),
        ("Data", "sdk_downloads"),
        ("Developer Tools", "verified_servers"),
    }
    verified = next(signal for signal in signals if signal.metadata["metric_name"] == "verified_servers")
    assert verified.metadata["metric_value"] == 144
    assert verified.metadata["signal_role"] == "trust"
    assert verified.metadata["source_url"] == "https://glama.ai/mcp/stats"


@pytest.mark.asyncio
async def test_category_and_minimum_count_filters_change_emitted_signals(tmp_path) -> None:
    report_path = tmp_path / "glama-filtered.json"
    report_path.write_text(
        json.dumps(
            {
                "snapshot_date": "2026-04-20",
                "categories": [
                    {"category": "Developer Tools", "server_count": 620, "sdk_downloads": 1250000},
                    {"category": "Data", "server_count": 180, "sdk_downloads": 260000},
                    {"category": "Healthcare", "server_count": 55, "sdk_downloads": 9000},
                ],
            }
        ),
        encoding="utf-8",
    )
    adapter = GlamaMcpStatsAdapter(
        config={
            "local_paths": [str(report_path)],
            "categories": ["Developer", "Data"],
            "min_server_count": 200,
        }
    )

    signals = await adapter.fetch(limit=20)

    assert {(signal.metadata["category"], signal.metadata["metric_name"]) for signal in signals} == {
        ("Developer Tools", "server_count"),
        ("Developer Tools", "sdk_downloads"),
    }


@pytest.mark.asyncio
async def test_signals_do_not_look_like_mcp_registry_server_package_records(tmp_path) -> None:
    report_path = tmp_path / "glama-mcp-stats.json"
    report_path.write_text(
        json.dumps(
            {
                "snapshot_date": "2026-04-20",
                "summary": {"server_count": 2480},
                "categories": [{"category": "Search", "server_count": 70}],
            }
        ),
        encoding="utf-8",
    )
    adapter = GlamaMcpStatsAdapter(config={"local_paths": [str(report_path)]})

    signals = await adapter.fetch(limit=10)

    assert signals
    assert all(signal.source_type == SignalSourceType.REPORT for signal in signals)
    assert all(signal.source_adapter == "glama_mcp_stats" for signal in signals)
    assert all("metric_name" in signal.metadata for signal in signals)
    assert all("metric_value" in signal.metadata for signal in signals)
    assert all("server_name" not in signal.metadata for signal in signals)
    assert all("package_urls" not in signal.metadata for signal in signals)
    assert all("registry_url" not in signal.metadata for signal in signals)

"""Tests for Snyk security report adapter."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest

from max.sources.registry import get_adapter, get_adapter_metadata, list_adapters, reload_registry
from max.sources.snyk_reports import SnykReportsAdapter
from max.types.signal import SignalSourceType


@pytest.mark.asyncio
async def test_markdown_headings_are_extracted_as_security_report_signals(tmp_path):
    report_path = tmp_path / "snyk-security-2026.md"
    report_path.write_text(
        "# Snyk security research 2026\n\n"
        "Overview of changing security teams and application risk.\n\n"
        "## Open source vulnerability trends\n\n"
        "Open source dependency vulnerabilities remain a major remediation burden.\n\n"
        "## AI and MCP security\n\n"
        "AI coding agents and MCP servers increase supply chain review needs.\n",
        encoding="utf-8",
    )
    adapter = SnykReportsAdapter(config={"local_paths": [str(report_path)]})

    signals = await adapter.fetch(limit=10)

    by_section = {signal.metadata["section"]: signal for signal in signals}
    assert set(by_section) == {
        "Snyk security research 2026",
        "Open source vulnerability trends",
        "AI and MCP security",
    }
    vuln_signal = by_section["Open source vulnerability trends"]
    assert vuln_signal.id.startswith("snyk_reports:")
    assert vuln_signal.source_type == SignalSourceType.SECURITY
    assert vuln_signal.source_adapter == "snyk_reports"
    assert vuln_signal.title == "Open source vulnerability trends"
    assert vuln_signal.content == (
        "Open source dependency vulnerabilities remain a major remediation burden."
    )
    assert vuln_signal.metadata["heading_level"] == 2
    assert vuln_signal.metadata["year"] == 2026
    assert vuln_signal.metadata["signal_role"] == "problem"
    assert {"snyk", "security-report", "vulnerability", "dependency", "open-source"}.issubset(
        set(vuln_signal.tags)
    )
    assert {"ai", "mcp", "supply-chain"}.issubset(
        set(by_section["AI and MCP security"].tags)
    )


@pytest.mark.asyncio
async def test_json_items_are_ingested_from_containers(tmp_path):
    report_path = tmp_path / "snyk-report.json"
    report_path.write_text(
        json.dumps(
            {
                "sections": {
                    "Supply chain": [
                        {
                            "title": "Package provenance gaps",
                            "summary": "Teams need stronger SBOM and dependency provenance controls.",
                            "keywords": ["sbom", "provenance"],
                            "published": "2026-04-20T12:00:00Z",
                        }
                    ],
                    "AI security": {
                        "headline": "AI adoption creates review queues",
                        "body": "Security review queues grew around generative AI services.",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    adapter = SnykReportsAdapter(config={"local_paths": [str(report_path)]})

    signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == [
        "Package provenance gaps",
        "AI adoption creates review queues",
    ]
    assert signals[0].metadata["section"] == "Supply chain"
    assert signals[0].source_type == SignalSourceType.SECURITY
    assert signals[0].published_at is not None
    assert {"supply-chain", "dependency", "sbom", "provenance"}.issubset(
        set(signals[0].tags)
    )
    assert signals[1].metadata["section"] == "AI security"
    assert signals[1].source_type == SignalSourceType.REPORT
    assert "ai" in signals[1].tags


@pytest.mark.asyncio
async def test_section_and_keyword_filters_reduce_output_deterministically(tmp_path):
    report_path = tmp_path / "snyk.md"
    report_path.write_text(
        "## Open source risk\n\n"
        "Dependency vulnerabilities affect common application frameworks.\n\n"
        "## AI and MCP security\n\n"
        "MCP server permissions need stronger security review.\n\n"
        "## Container security\n\n"
        "Base image patching still drives remediation work.\n",
        encoding="utf-8",
    )
    adapter = SnykReportsAdapter(
        config={
            "local_paths": [str(report_path)],
            "sections": ["security"],
            "keywords": ["MCP"],
        }
    )

    signals = await adapter.fetch(limit=10)

    assert [signal.metadata["section"] for signal in signals] == ["AI and MCP security"]
    assert signals[0].metadata["matched_keywords"] == ["MCP"]
    assert "mcp" in signals[0].tags


@pytest.mark.asyncio
async def test_http_report_urls_are_fetched_and_parsed():
    adapter = SnykReportsAdapter(config={"report_urls": ["https://example.com/snyk.md"]})
    response = httpx.Response(
        200,
        text="## Vulnerability remediation\n\nCritical CVE remediation is slow in legacy apps.\n",
    )

    with patch("max.sources.snyk_reports.fetch_with_retry", return_value=response) as mock_fetch:
        signals = await adapter.fetch(limit=5)

    assert mock_fetch.await_count == 1
    assert [signal.title for signal in signals] == ["Vulnerability remediation"]
    assert signals[0].url == "https://example.com/snyk.md"
    assert signals[0].source_type == SignalSourceType.SECURITY


@pytest.mark.asyncio
async def test_signal_ids_are_stable_for_same_local_report(tmp_path):
    report_path = tmp_path / "snyk-2026.md"
    report_path.write_text(
        "## Supply chain controls\n\n"
        "Open source dependency provenance is becoming a security requirement.\n",
        encoding="utf-8",
    )
    adapter = SnykReportsAdapter(config={"local_paths": [str(report_path)]})

    first = await adapter.fetch(limit=5)
    second = await adapter.fetch(limit=5)

    assert [signal.id for signal in first] == [signal.id for signal in second]


def test_snyk_reports_adapter_is_registered() -> None:
    try:
        with patch("max.config.MAX_ADAPTERS", "snyk_reports"), \
             patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
            reload_registry()

            assert list_adapters() == ["snyk_reports"]
            adapter = get_adapter("snyk_reports")
    finally:
        reload_registry()

    assert adapter.name == "snyk_reports"


def test_snyk_reports_adapter_metadata_documents_config_keys() -> None:
    try:
        with patch("max.config.MAX_ADAPTERS", "snyk_reports"), \
             patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
            reload_registry()
            metadata = get_adapter_metadata()
    finally:
        reload_registry()

    assert set(metadata) == {"snyk_reports"}
    assert metadata["snyk_reports"].config_keys == [
        "report_urls",
        "local_paths",
        "sections",
        "keywords",
        "max_items",
    ]
    assert metadata["snyk_reports"].required_keys == []
    assert "Snyk-style Markdown and JSON security research reports" in metadata[
        "snyk_reports"
    ].description

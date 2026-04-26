"""Tests for AgentSeal MCP security scan adapter."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest

from max.sources.agentseal_mcp_scan import AgentSealMcpScanAdapter
from max.sources.registry import get_adapter, get_adapter_metadata, list_adapters, reload_registry
from max.types.signal import SignalSourceType


def _finding(**overrides):
    finding = {
        "server_name": "filesystem-server",
        "package": "@modelcontextprotocol/server-filesystem",
        "finding_id": "AS-MCP-001",
        "severity": "high",
        "category": "prompt_injection",
        "summary": "Untrusted prompt reaches filesystem tool",
        "evidence": {"tool": "write_file", "input_origin": "prompt"},
        "remediation": "Require an explicit allowlist before tool execution.",
        "url": "https://agentseal.example/findings/as-mcp-001",
        "discovered_at": "2026-04-24T10:30:00Z",
    }
    finding.update(overrides)
    return finding


@pytest.mark.asyncio
async def test_json_fixture_produces_security_finding_signal_with_stable_id(tmp_path):
    report_path = tmp_path / "agentseal.json"
    report_path.write_text(json.dumps({"findings": [_finding()]}), encoding="utf-8")
    adapter = AgentSealMcpScanAdapter(config={"local_paths": [str(report_path)]})

    first = await adapter.fetch(limit=10)
    second = await adapter.fetch(limit=10)

    assert [signal.id for signal in first] == [signal.id for signal in second]
    signal = first[0]
    assert signal.id == "agentseal_mcp_scan:filesystem-server:as-mcp-001"
    assert signal.source_type == SignalSourceType.SECURITY
    assert signal.source_adapter == "agentseal_mcp_scan"
    assert signal.title == (
        "AgentSeal MCP high finding: filesystem-server - "
        "Untrusted prompt reaches filesystem tool"
    )
    assert "Evidence:" in signal.content
    assert "Remediation: Require an explicit allowlist" in signal.content
    assert signal.url == "https://agentseal.example/findings/as-mcp-001"
    assert {
        "mcp-security",
        "agentseal",
        "high",
        "severity:high",
        "prompt-injection",
        "category:prompt-injection",
    }.issubset(set(signal.tags))
    assert signal.metadata["package"] == "@modelcontextprotocol/server-filesystem"
    assert signal.metadata["finding_id"] == "AS-MCP-001"
    assert signal.metadata["evidence"] == {"tool": "write_file", "input_origin": "prompt"}
    assert signal.metadata["remediation"] == "Require an explicit allowlist before tool execution."
    assert signal.metadata["signal_role"] == "problem"


@pytest.mark.asyncio
async def test_jsonl_fixture_and_severity_min_filter_low_findings(tmp_path):
    report_path = tmp_path / "agentseal.jsonl"
    report_path.write_text(
        "\n".join(
            [
                json.dumps(_finding(finding_id="low-1", severity="low")),
                json.dumps(_finding(finding_id="medium-1", severity="medium")),
                json.dumps(_finding(finding_id="critical-1", severity="critical")),
            ]
        ),
        encoding="utf-8",
    )
    adapter = AgentSealMcpScanAdapter(
        config={"local_paths": [str(report_path)], "severity_min": "medium"}
    )

    signals = await adapter.fetch(limit=10)

    assert [signal.metadata["finding_id"] for signal in signals] == ["medium-1", "critical-1"]
    assert [signal.metadata["severity"] for signal in signals] == ["medium", "critical"]


@pytest.mark.asyncio
async def test_category_filtering_is_slug_normalized(tmp_path):
    report_path = tmp_path / "agentseal.json"
    report_path.write_text(
        json.dumps(
            [
                _finding(finding_id="one", category="prompt_injection"),
                _finding(finding_id="two", category="unsafe_tool_permissions"),
            ]
        ),
        encoding="utf-8",
    )
    adapter = AgentSealMcpScanAdapter(
        config={"local_paths": [str(report_path)], "categories": ["unsafe tool permissions"]}
    )

    signals = await adapter.fetch(limit=10)

    assert [signal.metadata["finding_id"] for signal in signals] == ["two"]
    assert signals[0].metadata["category"] == "unsafe_tool_permissions"


@pytest.mark.asyncio
async def test_include_remediated_false_excludes_resolved_findings(tmp_path):
    report_path = tmp_path / "agentseal.json"
    report_path.write_text(
        json.dumps(
            {
                "findings": [
                    _finding(finding_id="active", status="open"),
                    _finding(finding_id="fixed", status="remediated"),
                    _finding(finding_id="resolved", remediated=True),
                ]
            }
        ),
        encoding="utf-8",
    )
    adapter = AgentSealMcpScanAdapter(
        config={"local_paths": [str(report_path)], "include_remediated": False}
    )

    signals = await adapter.fetch(limit=10)

    assert [signal.metadata["finding_id"] for signal in signals] == ["active"]


@pytest.mark.asyncio
async def test_missing_optional_fields_get_defaults_and_hash_id(tmp_path):
    report_path = tmp_path / "minimal.json"
    report_path.write_text(
        json.dumps(
            {
                "server": "memory-server",
                "findings": [
                    {
                        "severity": "medium",
                        "category": "secret_exposure",
                        "summary": "Environment variable leak",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    adapter = AgentSealMcpScanAdapter(config={"local_paths": [str(report_path)]})

    signals = await adapter.fetch(limit=10)

    signal = signals[0]
    assert signal.id.startswith("agentseal_mcp_scan:memory-server:")
    assert signal.metadata["package"] is None
    assert signal.metadata["finding_id"] is None
    assert signal.metadata["evidence"] is None
    assert signal.metadata["remediation"] is None
    assert signal.url == report_path.resolve().as_uri()


@pytest.mark.asyncio
async def test_http_report_urls_are_fetched_and_parsed():
    adapter = AgentSealMcpScanAdapter(
        config={"report_urls": ["https://agentseal.example/report.json"]}
    )
    response = httpx.Response(200, text=json.dumps({"findings": [_finding()]}))

    with patch("max.sources.agentseal_mcp_scan.fetch_with_retry", return_value=response) as mock_fetch:
        signals = await adapter.fetch(limit=5)

    assert mock_fetch.await_count == 1
    assert [signal.metadata["finding_id"] for signal in signals] == ["AS-MCP-001"]
    assert signals[0].source_type == SignalSourceType.SECURITY


def test_agentseal_mcp_scan_adapter_is_registered() -> None:
    try:
        with patch("max.config.MAX_ADAPTERS", "agentseal_mcp_scan"), \
             patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
            reload_registry()

            assert list_adapters() == ["agentseal_mcp_scan"]
            adapter = get_adapter("agentseal_mcp_scan")
    finally:
        reload_registry()

    assert adapter.name == "agentseal_mcp_scan"


def test_agentseal_mcp_scan_adapter_metadata_documents_config_keys() -> None:
    try:
        with patch("max.config.MAX_ADAPTERS", "agentseal_mcp_scan"), \
             patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
            reload_registry()
            metadata = get_adapter_metadata()
    finally:
        reload_registry()

    assert set(metadata) == {"agentseal_mcp_scan"}
    assert metadata["agentseal_mcp_scan"].config_keys == [
        "local_paths",
        "report_urls",
        "severity_min",
        "categories",
        "max_items",
        "include_remediated",
    ]
    assert metadata["agentseal_mcp_scan"].required_keys == []
    assert "AgentSeal-style MCP server security scan" in metadata[
        "agentseal_mcp_scan"
    ].description

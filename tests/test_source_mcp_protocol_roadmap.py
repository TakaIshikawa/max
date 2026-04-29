"""Tests for MCP protocol roadmap adapter."""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

import pytest

from max.sources.mcp_protocol_roadmap import McpProtocolRoadmapAdapter, _string_list
from max.sources.registry import get_adapter, get_adapter_metadata, list_adapters, reload_registry
from max.types.signal import SignalSourceType


@pytest.mark.asyncio
async def test_markdown_local_roadmap_produces_deterministic_roadmap_signals(tmp_path) -> None:
    roadmap_path = tmp_path / "mcp-roadmap-2026.md"
    roadmap_path.write_text(
        "# MCP protocol roadmap 2026\n\n"
        "Overview text for the roadmap.\n\n"
        "## Streamable HTTP transport\n\n"
        "Capability: transports\n"
        "Date: 2026-Q2\n"
        "Evidence: Protocol maintainers are aligning around resumable streams.\n"
        "Summary: Streamable HTTP will reduce friction for remote MCP servers.\n\n"
        "## Authorization profiles\n\n"
        "Capability: auth\n"
        "Date: 2026-09-15\n"
        "Evidence: OAuth guidance is becoming a recurring protocol roadmap item.\n",
        encoding="utf-8",
    )
    adapter = McpProtocolRoadmapAdapter(config={"local_paths": [str(roadmap_path)]})

    signals = await adapter.fetch(limit=10)
    repeated = await adapter.fetch(limit=10)

    assert [signal.id for signal in signals] == [signal.id for signal in repeated]
    by_section = {signal.metadata["section"]: signal for signal in signals}
    assert set(by_section) == {
        "MCP protocol roadmap 2026",
        "Streamable HTTP transport",
        "Authorization profiles",
    }
    signal = by_section["Streamable HTTP transport"]
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "mcp_protocol_roadmap"
    assert signal.title == "Streamable HTTP transport"
    assert signal.content.startswith("Streamable HTTP will reduce friction")
    assert signal.metadata["capability_area"] == "transports"
    assert signal.metadata["target_date"] == "2026-Q2"
    assert signal.metadata["evidence_snippet"].startswith("Protocol maintainers")
    assert signal.metadata["heading_level"] == 2
    assert signal.metadata["signal_role"] == "solution"
    assert {"mcp", "protocol-roadmap", "roadmap", "streamable", "http", "transports"}.issubset(
        set(signal.tags)
    )


@pytest.mark.asyncio
async def test_json_local_roadmap_produces_stable_ids_and_useful_tags(tmp_path) -> None:
    roadmap_path = tmp_path / "mcp-roadmap.json"
    roadmap_path.write_text(
        json.dumps(
            {
                "roadmap_items": [
                    {
                        "title": "Sampling permissions",
                        "capability_area": "security",
                        "section": "Agent safety",
                        "summary": "Hosts need clearer controls for model sampling requests.",
                        "evidence": "Roadmap notes call out explicit user consent for sampling.",
                        "target_date": "2026-05-01",
                        "keywords": ["sampling", "consent"],
                    },
                    {
                        "name": "Registry metadata",
                        "area": "Discovery",
                        "description": (
                            "Server metadata should expose trust and compatibility hints."
                        ),
                        "quarter": "2026-Q3",
                        "tags": ["registry", "metadata"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    adapter = McpProtocolRoadmapAdapter(config={"local_paths": [str(roadmap_path)]})

    signals = await adapter.fetch(limit=10)
    repeated = await adapter.fetch(limit=10)

    assert [signal.id for signal in signals] == [signal.id for signal in repeated]
    assert [signal.title for signal in signals] == ["Sampling permissions", "Registry metadata"]
    assert signals[0].id.startswith("mcp_protocol_roadmap:")
    assert signals[0].metadata["section"] == "Agent safety"
    assert signals[0].metadata["capability_area"] == "security"
    assert signals[0].metadata["target_date"] == "2026-05-01"
    assert {"mcp", "protocol-roadmap", "roadmap", "agent", "safety", "sampling"}.issubset(
        set(signals[0].tags)
    )
    assert {"discovery", "registry", "metadata"}.issubset(set(signals[1].tags))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, []),
        (" sampling ", ["sampling"]),
        (["sampling", 7, None, "consent"], ["sampling", "7", "consent"]),
        (["sampling", " ", "sampling", "", "consent"], ["sampling", "consent"]),
        (42, []),
    ],
)
def test_string_list_normalizes_malformed_list_metadata(value: object, expected: list[str]) -> None:
    assert _string_list(value) == expected


@pytest.mark.asyncio
async def test_json_roadmap_tags_normalize_malformed_list_metadata(tmp_path) -> None:
    roadmap_path = tmp_path / "mcp-roadmap.json"
    roadmap_path.write_text(
        json.dumps(
            {
                "roadmap_items": [
                    {
                        "title": "None tags",
                        "summary": "Hosts should tolerate missing tag metadata.",
                        "tags": None,
                    },
                    {
                        "title": "String tags",
                        "summary": "Hosts should normalize one tag string.",
                        "tags": "Single Tag",
                    },
                    {
                        "title": "Mixed iterable tags",
                        "summary": "Hosts should normalize mixed tag collections.",
                        "tags": ["Mixed Tag", 7, None],
                    },
                    {
                        "title": "Duplicate blank tags",
                        "summary": "Hosts should dedupe and drop blank tags.",
                        "tags": ["Repeat Tag", " ", "Repeat Tag", ""],
                    },
                    {
                        "title": "Scalar tags",
                        "summary": "Hosts should ignore unsupported scalar tag metadata.",
                        "tags": 42,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    adapter = McpProtocolRoadmapAdapter(config={"local_paths": [str(roadmap_path)]})

    signals = await adapter.fetch(limit=10)

    by_title = {signal.title: signal for signal in signals}
    assert "single-tag" in by_title["String tags"].tags
    assert {"mixed-tag", "7"}.issubset(set(by_title["Mixed iterable tags"].tags))
    assert "none" not in by_title["Mixed iterable tags"].tags
    assert by_title["Duplicate blank tags"].tags.count("repeat-tag") == 1
    assert "" not in by_title["Duplicate blank tags"].tags
    assert "42" not in by_title["Scalar tags"].tags
    assert {"none", "tags"}.issubset(set(by_title["None tags"].tags))


@pytest.mark.asyncio
async def test_sections_keywords_and_max_items_constrain_results(tmp_path) -> None:
    roadmap_path = tmp_path / "mcp-roadmap.md"
    roadmap_path.write_text(
        "## Transport reliability\n\n"
        "Stream resumption and reconnect behavior are planned for remote servers.\n\n"
        "## Transport observability\n\n"
        "Tracing hooks are being discussed, but not the selected term.\n\n"
        "## Authorization profiles\n\n"
        "OAuth profile guidance is planned for hosts and servers.\n",
        encoding="utf-8",
    )
    adapter = McpProtocolRoadmapAdapter(
        config={
            "local_paths": [str(roadmap_path)],
            "sections": ["Transport"],
            "keywords": ["resumption"],
            "max_items": 1,
        }
    )

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["section"] == "Transport reliability"
    assert signals[0].metadata["matched_keywords"] == ["resumption"]
    assert "resumption" in signals[0].tags


@pytest.mark.asyncio
async def test_malformed_local_files_are_logged_and_skipped(tmp_path, caplog) -> None:
    broken_path = tmp_path / "broken.json"
    broken_path.write_text("{not valid json", encoding="utf-8")
    valid_path = tmp_path / "valid.md"
    valid_path.write_text(
        "## Elicitation improvements\n\n"
        "Client elicitation support is expected to improve interactive workflows.\n",
        encoding="utf-8",
    )
    adapter = McpProtocolRoadmapAdapter(
        config={"local_paths": [str(broken_path), str(valid_path)], "format": "auto"}
    )

    with caplog.at_level(logging.WARNING):
        signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == ["Elicitation improvements"]
    assert "skipping malformed roadmap file" in caplog.text
    assert "Malformed MCP protocol roadmap JSON" in caplog.text


def test_mcp_protocol_roadmap_adapter_is_registered() -> None:
    with patch("max.config.MAX_ADAPTERS", "mcp_protocol_roadmap"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        assert list_adapters() == ["mcp_protocol_roadmap"]
        adapter = get_adapter("mcp_protocol_roadmap")

    assert adapter.name == "mcp_protocol_roadmap"


def test_mcp_protocol_roadmap_adapter_metadata_documents_config_keys() -> None:
    with patch("max.config.MAX_ADAPTERS", "mcp_protocol_roadmap"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()
        metadata = get_adapter_metadata()

    assert set(metadata) == {"mcp_protocol_roadmap"}
    assert metadata["mcp_protocol_roadmap"].config_keys == [
        "roadmap_urls",
        "local_paths",
        "sections",
        "keywords",
        "max_items",
        "format",
    ]
    assert metadata["mcp_protocol_roadmap"].required_keys == []
    assert "MCP protocol roadmap" in metadata["mcp_protocol_roadmap"].description

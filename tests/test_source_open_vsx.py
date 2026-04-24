"""Tests for the Open VSX Registry source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.open_vsx import (
    OPEN_VSX_EXTENSION,
    OPEN_VSX_SEARCH,
    OpenVsxAdapter,
    _DEFAULT_QUERIES,
)
from max.types.signal import SignalSourceType


SEARCH_RESPONSE = {
    "extensions": [
        {
            "namespace": "Continue",
            "name": "continue",
            "version": "1.2.3",
            "displayName": "Continue",
            "description": "Open-source coding agent extension.",
            "downloadCount": 125000,
            "averageRating": 4.7,
            "categories": ["Programming Languages", "Machine Learning"],
            "tags": ["agent", "llm"],
            "repository": {"url": "https://github.com/continuedev/continue"},
            "license": "Apache-2.0",
            "timestamp": "2026-04-20T12:30:00Z",
            "url": "https://open-vsx.org/extension/Continue/continue",
        },
        {
            "namespace": "GitHub",
            "name": "copilot-chat",
            "version": "0.9.0",
            "description": "Chat with your coding assistant.",
            "download_count": 50000,
            "average_rating": 4.3,
            "categories": ["Other"],
            "tags": ["assistant"],
            "repository": "https://github.com/github/copilot",
            "license": "MIT",
            "publishedAt": "2026-04-18T09:00:00Z",
        },
    ]
}

DIRECT_RESPONSE = {
    "namespace": "OpenAI",
    "name": "chatgpt",
    "version": "2.0.0",
    "displayName": "ChatGPT",
    "description": "Use ChatGPT in compatible editors.",
    "downloadCount": 82000,
    "averageRating": 4.5,
    "categories": ["AI"],
    "tags": ["chatgpt", "agent"],
    "repository": {"url": "https://github.com/openai/chatgpt-vscode"},
    "license": "MIT",
    "lastUpdated": "2026-04-19T10:15:00Z",
}


def test_open_vsx_adapter_properties() -> None:
    adapter = OpenVsxAdapter()

    assert adapter.name == "open_vsx"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.queries == _DEFAULT_QUERIES
    assert adapter.extensions == []


def test_open_vsx_adapter_custom_config_and_alias() -> None:
    adapter = OpenVsxAdapter(
        config={
            "queries": ["agent"],
            "watchlist_terms": ["mcp"],
            "extension_identifiers": ["OpenAI/chatgpt", "bad", "OpenAI/chatgpt"],
        }
    )

    assert adapter.queries == ["agent", "mcp"]
    assert adapter.extensions == ["OpenAI/chatgpt"]


@pytest.mark.asyncio
async def test_open_vsx_fetch_emits_signals_from_search_results() -> None:
    adapter = OpenVsxAdapter(config={"queries": ["agent"]})

    with patch("max.sources.open_vsx.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: SEARCH_RESPONSE)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args.args[0] == OPEN_VSX_SEARCH
    assert mock_fetch.call_args.kwargs["params"] == {"query": "agent", "size": 10}

    first = signals[0]
    assert first.source_type == SignalSourceType.REGISTRY
    assert first.source_adapter == "open_vsx"
    assert first.title == "Continue@1.2.3"
    assert first.content == "Open-source coding agent extension."
    assert first.url == "https://open-vsx.org/extension/Continue/continue"
    assert first.author == "Continue"
    assert first.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert first.tags == ["Programming Languages", "Machine Learning", "agent", "llm"]
    assert first.credibility > 0.8
    assert first.metadata["namespace"] == "Continue"
    assert first.metadata["name"] == "continue"
    assert first.metadata["version"] == "1.2.3"
    assert first.metadata["download_count"] == 125000
    assert first.metadata["average_rating"] == 4.7
    assert first.metadata["categories"] == ["Programming Languages", "Machine Learning"]
    assert first.metadata["tags"] == ["agent", "llm"]
    assert first.metadata["repository"] == "https://github.com/continuedev/continue"
    assert first.metadata["license"] == "Apache-2.0"
    assert first.metadata["published_at"] == "2026-04-20T12:30:00+00:00"
    assert first.metadata["source_url"] == first.url
    assert first.metadata["search_query"] == "agent"


@pytest.mark.asyncio
async def test_open_vsx_fetch_emits_signals_from_direct_extension_lookup() -> None:
    adapter = OpenVsxAdapter(config={"queries": [], "extensions": ["OpenAI/chatgpt"]})

    with patch("max.sources.open_vsx.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: DIRECT_RESPONSE)

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert mock_fetch.call_args.args[0] == OPEN_VSX_EXTENSION.format(
        namespace="OpenAI",
        name="chatgpt",
    )
    assert mock_fetch.call_args.kwargs["params"] == {}
    assert signals[0].title == "ChatGPT@2.0.0"
    assert signals[0].url == "https://open-vsx.org/extension/OpenAI/chatgpt"
    assert signals[0].metadata["extension_identifier"] == "OpenAI/chatgpt"
    assert signals[0].metadata["repository"] == "https://github.com/openai/chatgpt-vscode"


@pytest.mark.asyncio
async def test_open_vsx_handles_missing_optional_fields() -> None:
    adapter = OpenVsxAdapter(config={"queries": ["minimal"]})
    response = {"extensions": [{"namespace": "Minimal", "name": "extension"}]}

    with patch("max.sources.open_vsx.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: response)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "Minimal/extension"
    assert signal.content == "extension"
    assert signal.published_at is None
    assert signal.tags == ["minimal"]
    assert signal.metadata["version"] is None
    assert signal.metadata["download_count"] is None
    assert signal.metadata["average_rating"] is None
    assert signal.metadata["categories"] == []
    assert signal.metadata["tags"] == []
    assert signal.metadata["repository"] is None
    assert signal.metadata["license"] is None
    assert signal.metadata["source_url"] == "https://open-vsx.org/extension/Minimal/extension"


@pytest.mark.asyncio
async def test_open_vsx_skips_bad_records_and_deduplicates() -> None:
    adapter = OpenVsxAdapter(config={"queries": ["agent", "llm"]})
    first_response = {
        "extensions": [
            {"name": "missing-namespace"},
            {"namespace": "Continue", "name": "continue", "version": "1.0.0"},
        ]
    }
    second_response = {
        "extensions": [
            {"namespace": "continue", "name": "Continue", "version": "9.9.9"},
            {"namespace": "Other", "name": "assistant", "version": "0.1.0"},
        ]
    }

    with patch("max.sources.open_vsx.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: first_response),
            MagicMock(json=lambda: second_response),
        ]

        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["namespace"] for signal in signals] == ["Continue", "Other"]
    assert [signal.metadata["name"] for signal in signals] == ["continue", "assistant"]


@pytest.mark.asyncio
async def test_open_vsx_respects_limit_across_search_and_direct_lookup() -> None:
    adapter = OpenVsxAdapter(config={"queries": ["agent"], "extensions": ["OpenAI/chatgpt"]})

    with patch("max.sources.open_vsx.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: SEARCH_RESPONSE)

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].metadata["namespace"] == "Continue"
    assert mock_fetch.call_count == 1
    assert mock_fetch.call_args.kwargs["params"] == {"query": "agent", "size": 1}


def test_open_vsx_registry_discovery() -> None:
    from max.sources.registry import get_adapter, get_adapter_metadata, reload_registry

    reload_registry()
    adapter = get_adapter("open_vsx")
    metadata = get_adapter_metadata()["open_vsx"]

    assert isinstance(adapter, OpenVsxAdapter)
    assert metadata.config_keys == ["queries", "extensions", "extension_identifiers"]
    assert "Open VSX Registry" in metadata.description

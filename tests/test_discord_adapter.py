"""Tests for the Discord source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.imports.discord_adapter import DiscordAdapter, _extract_tags
from max.sources.base import AdapterFetchError
from max.types.signal import SignalSourceType


MOCK_MESSAGES = [
    {
        "id": "msg-001",
        "content": "Has anyone tried the new MCP server integration? It seems like a great feature request for our bot.",
        "author": {"username": "dev_alice"},
        "timestamp": "2024-04-25T10:00:00+00:00",
        "reactions": [
            {"emoji": {"name": "thumbsup"}, "count": 5},
            {"emoji": {"name": "eyes"}, "count": 3},
        ],
        "thread": None,
        "referenced_message": None,
    },
    {
        "id": "msg-002",
        "content": "I found a bug in the AI module - it crashes on empty input",
        "author": {"username": "tester_bob"},
        "timestamp": "2024-04-25T12:30:00+00:00",
        "reactions": [{"emoji": {"name": "bug"}, "count": 2}],
        "thread": {"id": "thread-001"},
        "referenced_message": {"id": "msg-001"},
    },
    {
        "id": "msg-003",
        "content": "",
        "author": {"username": "empty_user"},
        "timestamp": "2024-04-25T13:00:00+00:00",
        "reactions": [],
    },
]


def test_discord_adapter_properties() -> None:
    adapter = DiscordAdapter()

    assert adapter.name == "discord"
    assert adapter.source_type == SignalSourceType.FORUM.value


def test_discord_adapter_config() -> None:
    adapter = DiscordAdapter(
        config={
            "channels": ["123456", "789012"],
            "bot_token": "my-bot-token",
        }
    )

    assert adapter.channels == ["123456", "789012"]
    assert adapter._bot_token == "my-bot-token"


def test_discord_adapter_auth_headers() -> None:
    adapter = DiscordAdapter(config={"bot_token": "test-token"})
    headers = adapter._auth_headers()

    assert headers["Authorization"] == "Bot test-token"


def test_discord_adapter_auth_headers_no_token() -> None:
    adapter = DiscordAdapter()
    headers = adapter._auth_headers()

    assert "Authorization" not in headers


@pytest.mark.asyncio
async def test_discord_fetch_no_channels() -> None:
    adapter = DiscordAdapter(config={"channels": []})

    signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_discord_fetch_parses_messages() -> None:
    adapter = DiscordAdapter(config={"channels": ["channel-001"]})

    with patch("max.imports.discord_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_MESSAGES)

        signals = await adapter.fetch(limit=10)

    # msg-003 has empty content, should be skipped
    assert len(signals) == 2

    first = signals[0]
    assert first.source_type == SignalSourceType.FORUM
    assert first.source_adapter == "discord"
    assert "MCP server integration" in first.title
    assert first.url == "https://discord.com/channels/-/channel-001/msg-001"
    assert first.author == "dev_alice"
    assert first.published_at == datetime(2024, 4, 25, 10, 0, tzinfo=timezone.utc)
    assert first.metadata["channel_id"] == "channel-001"
    assert first.metadata["reaction_count"] == 8
    assert first.metadata["has_thread"] is False
    assert first.metadata["referenced_message"] is False

    second = signals[1]
    assert second.metadata["reaction_count"] == 2
    assert second.metadata["has_thread"] is True
    assert second.metadata["referenced_message"] is True


@pytest.mark.asyncio
async def test_discord_fetch_handles_errors() -> None:
    adapter = DiscordAdapter(config={"channels": ["bad-channel"]})

    with patch("max.imports.discord_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = AdapterFetchError("discord", 403, "https://discord.com/api/v10/channels/bad-channel/messages")

        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_discord_fetch_handles_non_list_response() -> None:
    adapter = DiscordAdapter(config={"channels": ["channel-001"]})

    with patch("max.imports.discord_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"error": "forbidden"})

        signals = await adapter.fetch(limit=10)

    assert signals == []


def test_extract_tags_mcp() -> None:
    tags = _extract_tags("Working on MCP integration for our project")
    assert "discord" in tags
    assert "mcp" in tags


def test_extract_tags_bug() -> None:
    tags = _extract_tags("Found a bug in the authentication module")
    assert "discord" in tags
    assert "bug" in tags


def test_extract_tags_feature_request() -> None:
    tags = _extract_tags("It would be nice to have a feature request for dark mode")
    assert "discord" in tags
    assert "feature-request" in tags

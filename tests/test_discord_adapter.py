"""Tests for the Discord source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.imports.discord_adapter import DiscordAdapter
from max.types.signal import SignalSourceType


def _response(payload: object) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


def _message(
    msg_id: str,
    *,
    content: str = "Check out this new AI agent framework!",
    reactions: list[dict] | None = None,
    bot: bool = False,
    thread: dict | None = None,
    timestamp: str = "2026-04-22T10:00:00+00:00",
) -> dict:
    return {
        "id": msg_id,
        "content": content,
        "timestamp": timestamp,
        "author": {
            "id": "user123",
            "username": "devuser",
            "global_name": "Dev User",
            "bot": bot,
        },
        "reactions": reactions or [],
        "thread": thread,
        "mentions": [],
        "attachments": [],
    }


def test_discord_adapter_properties() -> None:
    adapter = DiscordAdapter(
        config={
            "channel_ids": ["111", "222"],
            "guild_ids": ["999"],
            "bot_token_env": "MY_DISCORD_TOKEN",
            "min_reactions": 2,
        }
    )

    assert adapter.name == "discord"
    assert adapter.source_type == SignalSourceType.FORUM.value
    assert adapter.channel_ids == ["111", "222"]
    assert adapter.guild_ids == ["999"]
    assert adapter.bot_token_env == "MY_DISCORD_TOKEN"
    assert adapter.min_reactions == 2


def test_discord_adapter_default_properties() -> None:
    adapter = DiscordAdapter()

    assert adapter.name == "discord"
    assert adapter.channel_ids == []
    assert adapter.guild_ids == []
    assert adapter.bot_token_env == "DISCORD_BOT_TOKEN"
    assert adapter.min_reactions == 0


@pytest.mark.asyncio
async def test_discord_returns_empty_without_token() -> None:
    adapter = DiscordAdapter(config={"channel_ids": ["111"]})
    with patch.dict("os.environ", {}, clear=True):
        signals = await adapter.fetch(limit=10)
    assert signals == []


@pytest.mark.asyncio
async def test_discord_fetches_channel_messages() -> None:
    adapter = DiscordAdapter(config={"channel_ids": ["ch1"]})

    messages = [
        _message("m1", content="New LLM agent framework released"),
        _message("m2", content="MCP protocol discussion thread"),
    ]

    mock_resp = _response(messages)

    with (
        patch.dict("os.environ", {"DISCORD_BOT_TOKEN": "test-token"}),
        patch("max.imports.discord_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.return_value = mock_resp
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert signals[0].source_adapter == "discord"
    assert signals[0].source_type == SignalSourceType.FORUM
    assert "LLM" in signals[0].title
    assert signals[0].author == "Dev User"
    assert signals[0].metadata["channel_id"] == "ch1"
    assert signals[0].metadata["message_id"] == "m1"


@pytest.mark.asyncio
async def test_discord_skips_bot_messages() -> None:
    adapter = DiscordAdapter(config={"channel_ids": ["ch1"]})

    messages = [
        _message("m1", bot=True, content="Bot auto-message"),
        _message("m2", content="Human message about Python"),
    ]

    with (
        patch.dict("os.environ", {"DISCORD_BOT_TOKEN": "test-token"}),
        patch("max.imports.discord_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.return_value = _response(messages)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["message_id"] == "m2"


@pytest.mark.asyncio
async def test_discord_filters_by_min_reactions() -> None:
    adapter = DiscordAdapter(config={"channel_ids": ["ch1"], "min_reactions": 3})

    messages = [
        _message("m1", reactions=[{"emoji": {"name": "👍"}, "count": 5}]),
        _message("m2", reactions=[{"emoji": {"name": "👍"}, "count": 1}]),
    ]

    with (
        patch.dict("os.environ", {"DISCORD_BOT_TOKEN": "test-token"}),
        patch("max.imports.discord_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.return_value = _response(messages)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["message_id"] == "m1"
    assert signals[0].metadata["reactions"] == 5


@pytest.mark.asyncio
async def test_discord_deduplicates_messages() -> None:
    adapter = DiscordAdapter(config={"channel_ids": ["ch1", "ch2"]})

    messages = [_message("m1", content="Duplicate message")]

    with (
        patch.dict("os.environ", {"DISCORD_BOT_TOKEN": "test-token"}),
        patch("max.imports.discord_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.return_value = _response(messages)
        signals = await adapter.fetch(limit=10)

    # Same message ID from two channels should only appear once
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_discord_extracts_thread_metadata() -> None:
    adapter = DiscordAdapter(config={"channel_ids": ["ch1"]})

    messages = [
        _message("m1", thread={"id": "thread123", "name": "Discussion"}),
    ]

    with (
        patch.dict("os.environ", {"DISCORD_BOT_TOKEN": "test-token"}),
        patch("max.imports.discord_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.return_value = _response(messages)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["has_thread"] is True
    assert signals[0].metadata["thread_id"] == "thread123"


@pytest.mark.asyncio
async def test_discord_fetches_guild_channels() -> None:
    adapter = DiscordAdapter(config={"guild_ids": ["g1"]})

    channels = [
        {"id": "ch1", "type": 0, "name": "general"},
        {"id": "ch2", "type": 2, "name": "voice"},  # voice channel, should skip
        {"id": "ch3", "type": 15, "name": "forum"},
    ]

    messages = [_message("m1", content="Guild message")]

    with (
        patch.dict("os.environ", {"DISCORD_BOT_TOKEN": "test-token"}),
        patch("max.imports.discord_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        # First call returns channels, subsequent calls return messages
        mock_fetch.side_effect = [
            _response(channels),
            _response(messages),
            _response([_message("m2", content="Forum post")]),
        ]
        signals = await adapter.fetch(limit=10)

    # Should have fetched from text (ch1) and forum (ch3) channels, not voice (ch2)
    assert len(signals) == 2
    assert mock_fetch.call_count == 3


@pytest.mark.asyncio
async def test_discord_handles_fetch_error_gracefully() -> None:
    from max.sources.base import AdapterFetchError

    adapter = DiscordAdapter(config={"channel_ids": ["ch1"]})

    with (
        patch.dict("os.environ", {"DISCORD_BOT_TOKEN": "test-token"}),
        patch("max.imports.discord_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.side_effect = AdapterFetchError("discord", 403, "https://discord.com/api/...")
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_discord_respects_limit() -> None:
    adapter = DiscordAdapter(config={"channel_ids": ["ch1"]})

    messages = [_message(f"m{i}", content=f"Message {i}") for i in range(20)]

    with (
        patch.dict("os.environ", {"DISCORD_BOT_TOKEN": "test-token"}),
        patch("max.imports.discord_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.return_value = _response(messages)
        signals = await adapter.fetch(limit=5)

    assert len(signals) == 5


@pytest.mark.asyncio
async def test_discord_returns_empty_for_zero_limit() -> None:
    adapter = DiscordAdapter(config={"channel_ids": ["ch1"]})
    with patch.dict("os.environ", {"DISCORD_BOT_TOKEN": "test-token"}):
        signals = await adapter.fetch(limit=0)
    assert signals == []


def test_discord_tags_extraction() -> None:
    adapter = DiscordAdapter(config={"channel_ids": ["ch1"]})

    messages = [_message("m1", content="Working on an AI agent with MCP protocol")]

    # Verify tags by creating signal directly
    from max.imports.discord_adapter import _extract_tags

    tags = _extract_tags("Working on an AI agent with MCP protocol", "dev-chat")
    assert "discord" in tags
    assert "ai" in tags
    assert "agent" in tags
    assert "mcp" in tags
    assert "dev_chat" in tags


def test_discord_message_url_with_guild() -> None:
    from max.imports.discord_adapter import _message_url

    url = _message_url(guild_id="g1", channel_id="ch1", message_id="m1")
    assert url == "https://discord.com/channels/g1/ch1/m1"


def test_discord_message_url_without_guild() -> None:
    from max.imports.discord_adapter import _message_url

    url = _message_url(guild_id=None, channel_id="ch1", message_id="m1")
    assert url == "https://discord.com/channels/@me/ch1/m1"


def test_discord_credibility_calculation() -> None:
    from max.imports.discord_adapter import _credibility

    # Baseline: no reactions, no thread
    assert _credibility(total_reactions=0, has_thread=False) == 0.2

    # With thread
    cred_thread = _credibility(total_reactions=0, has_thread=True)
    assert cred_thread > 0.2

    # With reactions
    cred_reactions = _credibility(total_reactions=10, has_thread=False)
    assert cred_reactions > 0.2

    # Capped at 1.0
    assert _credibility(total_reactions=1000, has_thread=True) == 1.0


def test_discord_skips_empty_content() -> None:
    adapter = DiscordAdapter()
    signal = adapter._message_to_signal(
        {"id": "m1", "content": "", "author": {"id": "u1", "username": "test"}, "timestamp": "2026-04-22T10:00:00Z"},
        channel_id="ch1",
    )
    assert signal is None

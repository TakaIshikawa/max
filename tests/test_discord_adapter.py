"""Tests for Discord source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.imports.discord_adapter import (
    DiscordAdapter,
    _extract_tags,
    _parse_datetime,
    _reaction_credibility,
)
from max.sources.base import AdapterFetchError, SourceAdapter
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────

MOCK_DISCORD_MESSAGES = [
    {
        "id": "msg_001",
        "content": "Has anyone tried the new MCP agent framework? Looks promising for LLM workflows.",
        "author": {"id": "user_001", "username": "alice_dev"},
        "timestamp": "2026-04-10T14:00:00Z",
        "reactions": [
            {"emoji": {"name": "thumbsup"}, "count": 5},
            {"emoji": {"name": "heart"}, "count": 3},
        ],
        "thread": None,
    },
    {
        "id": "msg_002",
        "content": "Bug report: the API returns 500 when you send more than 100 items in a batch.",
        "author": {"id": "user_002", "username": "bob_qa"},
        "timestamp": "2026-04-11T10:30:00Z",
        "reactions": [
            {"emoji": {"name": "eyes"}, "count": 10},
        ],
        "thread": {"id": "thread_001"},
    },
    {
        "id": "msg_003",
        "content": "",
        "author": {"id": "user_003", "username": "bot_notifications"},
        "timestamp": "2026-04-12T08:00:00Z",
        "reactions": [],
    },
]

MOCK_CHANNEL_INFO = {"id": "chan_001", "name": "general-dev"}


# ── Unit Tests: _extract_tags ────────────────────────────────────────


class TestExtractTags:
    def test_includes_discord(self) -> None:
        tags = _extract_tags("some text", "general")
        assert "discord" in tags

    def test_includes_channel_name(self) -> None:
        tags = _extract_tags("some text", "ai-discussion")
        assert "ai-discussion" in tags

    def test_keyword_detection(self) -> None:
        tags = _extract_tags("MCP agent for LLM", "general")
        assert "mcp" in tags
        assert "agent" in tags
        assert "llm" in tags

    def test_bug_keyword(self) -> None:
        tags = _extract_tags("Found a bug in the parser", "dev")
        assert "bug" in tags

    def test_feature_keyword(self) -> None:
        tags = _extract_tags("Feature request: dark mode", "suggestions")
        assert "feature-request" in tags

    def test_limits_to_10(self) -> None:
        text = "agent llm mcp openai langchain rag embedding claude anthropic bug feature"
        tags = _extract_tags(text, "long-channel-name")
        assert len(tags) <= 10

    def test_none_channel(self) -> None:
        tags = _extract_tags("text", None)
        assert "discord" in tags


# ── Unit Tests: _parse_datetime ──────────────────────────────────────


class TestParseDatetime:
    def test_iso_with_z(self) -> None:
        dt = _parse_datetime("2026-04-10T14:00:00Z")
        assert dt is not None
        assert dt.year == 2026

    def test_none_input(self) -> None:
        assert _parse_datetime(None) is None

    def test_empty_string(self) -> None:
        assert _parse_datetime("") is None

    def test_invalid(self) -> None:
        assert _parse_datetime("not-a-date") is None


# ── Unit Tests: _reaction_credibility ────────────────────────────────


class TestReactionCredibility:
    def test_zero_reactions(self) -> None:
        assert _reaction_credibility(0) == pytest.approx(0.2)

    def test_high_reactions_caps_at_1(self) -> None:
        assert _reaction_credibility(1000) == 1.0

    def test_moderate_reactions(self) -> None:
        # 8 reactions -> 0.2 + 8/50 = 0.36
        cred = _reaction_credibility(8)
        assert 0.3 < cred < 0.5


# ── Adapter Property Tests ───────────────────────────────────────────


class TestDiscordAdapterProperties:
    def test_name(self) -> None:
        assert DiscordAdapter().name == "discord"

    def test_source_type(self) -> None:
        assert DiscordAdapter().source_type == SignalSourceType.FORUM.value

    def test_inherits_from_source_adapter(self) -> None:
        assert isinstance(DiscordAdapter(), SourceAdapter)

    def test_no_channel_ids_by_default(self) -> None:
        assert DiscordAdapter().channel_ids == []

    def test_config_channel_ids(self) -> None:
        a = DiscordAdapter(config={"channel_ids": ["123", "456"]})
        assert a.channel_ids == ["123", "456"]

    def test_bot_token_env_default(self) -> None:
        assert DiscordAdapter().bot_token_env == "DISCORD_BOT_TOKEN"


# ── Adapter Fetch Tests ──────────────────────────────────────────────


class TestDiscordAdapterFetch:
    @pytest.mark.asyncio
    async def test_fetch_returns_empty_without_token(self) -> None:
        adapter = DiscordAdapter(config={"channel_ids": ["123"]})

        with patch.dict("os.environ", {}, clear=True):
            signals = await adapter.fetch(limit=10)

        assert signals == []

    @pytest.mark.asyncio
    async def test_fetch_returns_empty_without_channels(self) -> None:
        adapter = DiscordAdapter()

        with patch.dict("os.environ", {"DISCORD_BOT_TOKEN": "test-token"}):
            signals = await adapter.fetch(limit=10)

        assert signals == []

    @pytest.mark.asyncio
    async def test_fetch_parses_messages(self) -> None:
        adapter = DiscordAdapter(config={"channel_ids": ["chan_001"]})

        mock_msg_resp = MagicMock()
        mock_msg_resp.json.return_value = MOCK_DISCORD_MESSAGES
        mock_msg_resp.status_code = 200

        mock_chan_resp = MagicMock()
        mock_chan_resp.json.return_value = MOCK_CHANNEL_INFO
        mock_chan_resp.status_code = 200

        with patch.dict("os.environ", {"DISCORD_BOT_TOKEN": "test-token"}):
            with patch(
                "max.imports.discord_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                side_effect=[mock_msg_resp, mock_chan_resp],
            ):
                signals = await adapter.fetch(limit=10)

        # msg_003 has empty content, should be skipped
        assert len(signals) == 2
        assert signals[0].source_adapter == "discord"
        assert signals[0].source_type == SignalSourceType.FORUM
        assert "MCP" in signals[0].title
        assert signals[0].author == "alice_dev"
        assert signals[0].metadata["channel_id"] == "chan_001"

    @pytest.mark.asyncio
    async def test_fetch_reaction_count(self) -> None:
        adapter = DiscordAdapter(config={"channel_ids": ["chan_001"]})

        mock_msg_resp = MagicMock()
        mock_msg_resp.json.return_value = MOCK_DISCORD_MESSAGES
        mock_msg_resp.status_code = 200

        mock_chan_resp = MagicMock()
        mock_chan_resp.json.return_value = MOCK_CHANNEL_INFO
        mock_chan_resp.status_code = 200

        with patch.dict("os.environ", {"DISCORD_BOT_TOKEN": "test-token"}):
            with patch(
                "max.imports.discord_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                side_effect=[mock_msg_resp, mock_chan_resp],
            ):
                signals = await adapter.fetch(limit=10)

        # msg_001: 5 + 3 = 8 reactions
        assert signals[0].metadata["reaction_count"] == 8
        # msg_002: 10 reactions
        assert signals[1].metadata["reaction_count"] == 10

    @pytest.mark.asyncio
    async def test_fetch_thread_detection(self) -> None:
        adapter = DiscordAdapter(config={"channel_ids": ["chan_001"]})

        mock_msg_resp = MagicMock()
        mock_msg_resp.json.return_value = MOCK_DISCORD_MESSAGES
        mock_msg_resp.status_code = 200

        mock_chan_resp = MagicMock()
        mock_chan_resp.json.return_value = MOCK_CHANNEL_INFO
        mock_chan_resp.status_code = 200

        with patch.dict("os.environ", {"DISCORD_BOT_TOKEN": "test-token"}):
            with patch(
                "max.imports.discord_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                side_effect=[mock_msg_resp, mock_chan_resp],
            ):
                signals = await adapter.fetch(limit=10)

        assert signals[0].metadata["has_thread"] is False
        assert signals[1].metadata["has_thread"] is True

    @pytest.mark.asyncio
    async def test_fetch_respects_limit(self) -> None:
        adapter = DiscordAdapter(config={"channel_ids": ["chan_001"]})

        mock_msg_resp = MagicMock()
        mock_msg_resp.json.return_value = MOCK_DISCORD_MESSAGES
        mock_msg_resp.status_code = 200

        mock_chan_resp = MagicMock()
        mock_chan_resp.json.return_value = MOCK_CHANNEL_INFO
        mock_chan_resp.status_code = 200

        with patch.dict("os.environ", {"DISCORD_BOT_TOKEN": "test-token"}):
            with patch(
                "max.imports.discord_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                side_effect=[mock_msg_resp, mock_chan_resp],
            ):
                signals = await adapter.fetch(limit=1)

        assert len(signals) == 1


# ── Error Handling Tests ─────────────────────────────────────────────


class TestDiscordAdapterErrors:
    @pytest.mark.asyncio
    async def test_fetch_continues_on_channel_error(self) -> None:
        adapter = DiscordAdapter(config={"channel_ids": ["bad_chan", "chan_001"]})

        mock_msg_resp = MagicMock()
        mock_msg_resp.json.return_value = MOCK_DISCORD_MESSAGES
        mock_msg_resp.status_code = 200

        mock_chan_resp = MagicMock()
        mock_chan_resp.json.return_value = MOCK_CHANNEL_INFO
        mock_chan_resp.status_code = 200

        with patch.dict("os.environ", {"DISCORD_BOT_TOKEN": "test-token"}):
            with patch(
                "max.imports.discord_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                side_effect=[
                    AdapterFetchError("discord", 403, "url"),
                    mock_msg_resp,
                    mock_chan_resp,
                ],
            ):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 2

    @pytest.mark.asyncio
    async def test_fetch_all_fail_returns_empty(self) -> None:
        adapter = DiscordAdapter(config={"channel_ids": ["bad"]})

        with patch.dict("os.environ", {"DISCORD_BOT_TOKEN": "test-token"}):
            with patch(
                "max.imports.discord_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                side_effect=AdapterFetchError("discord", 500, "url"),
            ):
                signals = await adapter.fetch(limit=10)

        assert signals == []

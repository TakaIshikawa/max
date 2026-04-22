"""Tests for Dev.to source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.devto import (
    DevtoAdapter,
    _extract_tags,
    _parse_datetime,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────


MOCK_DEVTO_ARTICLES = [
    {
        "id": 1001,
        "title": "Building an AI Agent with MCP and Claude",
        "description": "A step-by-step guide to building AI agents using MCP servers.",
        "url": "https://dev.to/alice/building-ai-agent-mcp",
        "published_at": "2026-04-10T14:00:00Z",
        "positive_reactions_count": 75,
        "comments_count": 12,
        "reading_time_minutes": 8,
        "tag_list": ["ai", "mcp", "python"],
        "user": {"name": "Alice Dev"},
    },
    {
        "id": 1002,
        "title": "RAG Pipeline Best Practices for 2026",
        "description": "What I learned building production RAG systems.",
        "url": "https://dev.to/bob/rag-best-practices",
        "published_at": "2026-04-11T10:30:00Z",
        "positive_reactions_count": 150,
        "comments_count": 25,
        "reading_time_minutes": 12,
        "tag_list": ["rag", "llm", "embedding"],
        "user": {"name": "Bob ML"},
    },
    {
        "id": 1003,
        "title": "TypeScript Tips for CLI Tools",
        "description": "Quick tips for building CLI tools.",
        "url": "https://dev.to/charlie/ts-cli-tips",
        "published_at": "2026-04-12T08:00:00Z",
        "positive_reactions_count": 30,
        "comments_count": 5,
        "reading_time_minutes": 4,
        "tag_list": ["typescript", "cli"],
        "user": {"name": "Charlie TS"},
    },
]


# ── Unit Tests ────────────────────────────────────────────────────────


class TestExtractTags:
    def test_includes_article_tags(self) -> None:
        tags = _extract_tags(["ai", "mcp", "python"], "some title")
        assert "ai" in tags
        assert "mcp" in tags
        assert "python" in tags

    def test_extracts_keywords_from_title(self) -> None:
        tags = _extract_tags([], "Building an agent with LangChain for RAG")
        assert "agent" in tags
        assert "langchain" in tags
        assert "rag" in tags

    def test_always_includes_devto(self) -> None:
        tags = _extract_tags([], "random title")
        assert "devto" in tags

    def test_limits_to_10(self) -> None:
        many_tags = [f"tag-{i}" for i in range(15)]
        tags = _extract_tags(many_tags, "agent llm mcp rag embedding openai claude")
        assert len(tags) <= 10

    def test_lowercases_tags(self) -> None:
        tags = _extract_tags(["AI", "MCP"], "title")
        assert "ai" in tags
        assert "mcp" in tags


class TestParseDatetime:
    def test_iso_with_z(self) -> None:
        dt = _parse_datetime("2026-04-10T14:00:00Z")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 4
        assert dt.day == 10

    def test_iso_with_offset(self) -> None:
        dt = _parse_datetime("2026-04-10T14:00:00+05:30")
        assert dt is not None
        assert dt.year == 2026

    def test_none_input(self) -> None:
        assert _parse_datetime(None) is None

    def test_empty_string(self) -> None:
        assert _parse_datetime("") is None

    def test_invalid(self) -> None:
        assert _parse_datetime("not-a-date") is None


# ── Adapter Tests ────────────────────────────────────────────────────


class TestDevtoAdapter:
    def test_name(self) -> None:
        assert DevtoAdapter().name == "devto"

    def test_source_type(self) -> None:
        assert DevtoAdapter().source_type == SignalSourceType.FORUM.value

    def test_config_defaults(self) -> None:
        a = DevtoAdapter()
        assert "ai" in a.tags
        assert a.period == 7

    def test_config_overrides(self) -> None:
        a = DevtoAdapter(config={"tags": ["rust", "wasm"], "period": 14})
        assert a.tags == ["rust", "wasm"]
        assert a.period == 14

    @pytest.mark.asyncio
    async def test_fetch_parses_articles(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["ai"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_DEVTO_ARTICLES
        mock_resp.status_code = 200

        with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert len(signals) == 3
        assert signals[0].source_adapter == "devto"
        assert "AI Agent" in signals[0].title
        assert signals[0].url == "https://dev.to/alice/building-ai-agent-mcp"
        assert signals[0].author == "Alice Dev"
        assert signals[0].metadata["devto_id"] == 1001

    @pytest.mark.asyncio
    async def test_fetch_credibility_from_reactions(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["ai"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_DEVTO_ARTICLES
        mock_resp.status_code = 200

        with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        # 75 reactions → 75/100 = 0.75
        assert signals[0].credibility == pytest.approx(0.75)
        # 150 reactions → min(150/100, 1.0) = 1.0
        assert signals[1].credibility == pytest.approx(1.0)
        # 30 reactions → 30/100 = 0.3
        assert signals[2].credibility == pytest.approx(0.3)

    @pytest.mark.asyncio
    async def test_fetch_respects_limit(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["ai"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_DEVTO_ARTICLES
        mock_resp.status_code = 200

        with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=1)

        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_fetch_deduplicates_across_tags(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["ai", "llm", "mcp"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_DEVTO_ARTICLES
        mock_resp.status_code = 200

        with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        # Same articles returned for all tags, dedup by devto_id
        assert len(signals) == 3

    @pytest.mark.asyncio
    async def test_fetch_handles_tag_list_as_string(self) -> None:
        """Some Dev.to responses return tag_list as comma-separated string."""
        adapter = DevtoAdapter(config={"tags": ["test"]})

        articles = [{
            "id": 2001,
            "title": "Test Article",
            "description": "Test desc",
            "url": "https://dev.to/test",
            "published_at": "2026-04-10T00:00:00Z",
            "positive_reactions_count": 10,
            "comments_count": 1,
            "reading_time_minutes": 3,
            "tag_list": "python, ai, tools",
            "user": {"name": "Tester"},
        }]

        mock_resp = MagicMock()
        mock_resp.json.return_value = articles
        mock_resp.status_code = 200

        with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert len(signals) == 1
        assert "python" in signals[0].tags or "ai" in signals[0].tags

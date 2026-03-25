"""Tests for source adapters with mocked HTTP responses."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.hackernews import HackerNewsAdapter, _extract_tags
from max.sources.npm_registry import NpmRegistryAdapter
from max.sources.registry import get_adapter, get_all_adapters, list_adapters


# ── HackerNews ───────────────────────────────────────────────────────


def _mock_hn_item(story_id: int, title: str, score: int = 100) -> dict:
    return {
        "id": story_id,
        "type": "story",
        "title": title,
        "url": f"https://example.com/{story_id}",
        "by": "testuser",
        "time": 1711000000,
        "score": score,
        "descendants": 50,
    }


@pytest.mark.asyncio
async def test_hackernews_fetch_parses_stories() -> None:
    adapter = HackerNewsAdapter()

    mock_responses = {
        "topstories.json": MagicMock(
            json=lambda: [101, 102, 103],
            raise_for_status=lambda: None,
        ),
        "item/101.json": MagicMock(
            json=lambda: _mock_hn_item(101, "Show HN: AI Agent Testing Framework"),
            raise_for_status=lambda: None,
        ),
        "item/102.json": MagicMock(
            json=lambda: _mock_hn_item(102, "MCP Server Security Audit Results", score=400),
            raise_for_status=lambda: None,
        ),
        "item/103.json": MagicMock(
            json=lambda: _mock_hn_item(103, "Rust Package Manager Update"),
            raise_for_status=lambda: None,
        ),
    }

    async def mock_get(url: str) -> MagicMock:
        for key, resp in mock_responses.items():
            if url.endswith(key):
                return resp
        raise ValueError(f"Unexpected URL: {url}")

    with patch("max.sources.hackernews.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        signals = await adapter.fetch(limit=3)

    assert len(signals) == 3
    assert signals[0].title == "Show HN: AI Agent Testing Framework"
    assert signals[0].source_adapter == "hackernews"
    assert signals[0].source_type.value == "forum"
    assert signals[0].author == "testuser"
    assert signals[0].metadata["hn_id"] == 101

    # Score-based credibility
    assert signals[1].credibility == 400 / 500  # 0.8
    assert signals[0].credibility == 100 / 500  # 0.2


@pytest.mark.asyncio
async def test_hackernews_skips_non_story_items() -> None:
    adapter = HackerNewsAdapter()

    mock_responses = {
        "topstories.json": MagicMock(
            json=lambda: [201],
            raise_for_status=lambda: None,
        ),
        "item/201.json": MagicMock(
            json=lambda: {"id": 201, "type": "comment", "text": "just a comment"},
            raise_for_status=lambda: None,
        ),
    }

    async def mock_get(url: str) -> MagicMock:
        for key, resp in mock_responses.items():
            if url.endswith(key):
                return resp
        raise ValueError(f"Unexpected URL: {url}")

    with patch("max.sources.hackernews.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 0


def test_extract_tags_ai() -> None:
    assert "ai" in _extract_tags("New Claude AI model released")
    assert "ai" in _extract_tags("LLM benchmarks for 2026")


def test_extract_tags_mcp() -> None:
    assert "mcp" in _extract_tags("MCP server for database access")


def test_extract_tags_multiple() -> None:
    tags = _extract_tags("Python AI Agent Security Vulnerability")
    assert "python" in tags
    assert "ai" in tags
    assert "agent" in tags
    assert "security" in tags


def test_extract_tags_no_match() -> None:
    assert _extract_tags("random unrelated title") == []


# ── npm registry ─────────────────────────────────────────────────────


def _mock_npm_response(packages: list[dict]) -> dict:
    return {
        "objects": [
            {
                "package": pkg,
                "searchScore": pkg.get("_score", 50000),
            }
            for pkg in packages
        ]
    }


@pytest.mark.asyncio
async def test_npm_fetch_parses_packages() -> None:
    adapter = NpmRegistryAdapter()

    mock_data = _mock_npm_response([
        {
            "name": "@test/mcp-server",
            "description": "An MCP server for testing",
            "version": "1.0.0",
            "date": "2026-03-20T00:00:00Z",
            "publisher": {"username": "testpublisher"},
            "keywords": ["mcp", "server"],
            "_score": 80000,
        },
    ])

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: mock_data,
            raise_for_status=lambda: None,
        )

    with patch("max.sources.npm_registry.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        signals = await adapter.fetch(limit=5)

    assert len(signals) >= 1
    first = signals[0]
    assert first.title == "@test/mcp-server@1.0.0"
    assert first.source_adapter == "npm_registry"
    assert first.source_type.value == "registry"
    assert first.author == "testpublisher"
    assert first.metadata["npm_name"] == "@test/mcp-server"
    assert first.credibility == 80000 / 100_000


@pytest.mark.asyncio
async def test_npm_respects_limit() -> None:
    adapter = NpmRegistryAdapter()

    # Return many packages per query
    many_pkgs = [
        {"name": f"pkg-{i}", "description": f"Package {i}", "version": "1.0.0"}
        for i in range(20)
    ]
    mock_data = _mock_npm_response(many_pkgs)

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: mock_data,
            raise_for_status=lambda: None,
        )

    with patch("max.sources.npm_registry.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        signals = await adapter.fetch(limit=3)

    assert len(signals) <= 3


# ── Registry ─────────────────────────────────────────────────────────


def test_list_adapters() -> None:
    adapters = list_adapters()
    assert "hackernews" in adapters
    assert "npm_registry" in adapters


def test_get_adapter() -> None:
    adapter = get_adapter("hackernews")
    assert adapter.name == "hackernews"


def test_get_adapter_unknown() -> None:
    with pytest.raises(KeyError, match="Unknown adapter"):
        get_adapter("nonexistent")


def test_get_all_adapters() -> None:
    adapters = get_all_adapters()
    assert len(adapters) >= 2
    names = {a.name for a in adapters}
    assert "hackernews" in names
    assert "npm_registry" in names

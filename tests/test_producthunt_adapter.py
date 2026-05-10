"""Tests for Product Hunt import adapter — launch signal collection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.imports.producthunt_adapter import (
    ProductHuntAdapter,
    _build_tags,
    _extract_topics,
    _parse_dt,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────

MOCK_PH_RESPONSE = {
    "data": {
        "posts": {
            "edges": [
                {
                    "node": {
                        "id": "123",
                        "name": "DevTool AI",
                        "tagline": "AI-powered developer productivity tool",
                        "url": "https://www.producthunt.com/posts/devtool-ai",
                        "votesCount": 450,
                        "commentsCount": 32,
                        "createdAt": "2024-04-15T10:00:00Z",
                        "featuredAt": "2024-04-15T12:00:00Z",
                        "website": "https://devtool.ai",
                        "topics": {
                            "edges": [
                                {"node": {"name": "Developer Tools", "slug": "developer-tools"}},
                                {"node": {"name": "Artificial Intelligence", "slug": "artificial-intelligence"}},
                            ]
                        },
                        "makers": [
                            {"id": "m1", "name": "Jane Doe", "username": "janedoe"},
                        ],
                        "thumbnail": {"url": "https://ph.cdn/thumb.png"},
                    }
                },
                {
                    "node": {
                        "id": "456",
                        "name": "SaaS Metrics",
                        "tagline": "Track your SaaS KPIs in real-time",
                        "url": "https://www.producthunt.com/posts/saas-metrics",
                        "votesCount": 120,
                        "commentsCount": 8,
                        "createdAt": "2024-04-14T08:00:00Z",
                        "featuredAt": None,
                        "website": "https://saasmetrics.io",
                        "topics": {
                            "edges": [
                                {"node": {"name": "SaaS", "slug": "saas"}},
                                {"node": {"name": "Analytics", "slug": "analytics"}},
                            ]
                        },
                        "makers": [],
                        "thumbnail": None,
                    }
                },
            ],
            "pageInfo": {
                "hasNextPage": False,
                "endCursor": "cursor_abc",
            },
        }
    }
}

MOCK_PH_EMPTY = {
    "data": {
        "posts": {
            "edges": [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }
    }
}


def _mock_response(payload: dict, *, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = payload
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


# ── Unit tests ───────────────────────────────────────────────────────


def test_parse_dt_valid() -> None:
    dt = _parse_dt("2024-04-15T10:00:00Z")
    assert dt is not None
    assert dt.year == 2024
    assert dt.month == 4
    assert dt.day == 15


def test_parse_dt_none() -> None:
    assert _parse_dt(None) is None
    assert _parse_dt("") is None


def test_extract_topics() -> None:
    edges = [
        {"node": {"name": "AI", "slug": "artificial-intelligence"}},
        {"node": {"name": "Dev", "slug": "developer-tools"}},
    ]
    topics = _extract_topics(edges)
    assert topics == ["artificial-intelligence", "developer-tools"]


def test_extract_topics_empty() -> None:
    assert _extract_topics([]) == []


def test_build_tags_known_topics() -> None:
    tags = _build_tags(["developer-tools", "artificial-intelligence"], "saas")
    assert "devtools" in tags
    assert "ai" in tags
    assert "saas" in tags
    assert "producthunt" in tags


def test_build_tags_unknown_topic() -> None:
    tags = _build_tags(["some-new-category"], "developer-tools")
    assert "some-new-category" in tags
    assert "devtools" in tags
    assert "producthunt" in tags


# ── Adapter property tests ───────────────────────────────────────────


def test_adapter_name() -> None:
    adapter = ProductHuntAdapter()
    assert adapter.name == "producthunt_import"


def test_adapter_source_type() -> None:
    adapter = ProductHuntAdapter()
    assert adapter.source_type == SignalSourceType.MARKETPLACE.value


def test_adapter_default_topics() -> None:
    adapter = ProductHuntAdapter()
    assert "developer-tools" in adapter.topics
    assert "artificial-intelligence" in adapter.topics


def test_adapter_custom_topics() -> None:
    adapter = ProductHuntAdapter(config={"topics": ["fintech", "no-code"]})
    assert adapter.topics == ["fintech", "no-code"]


# ── Fetch tests with mocked API ─────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_returns_empty_without_token() -> None:
    adapter = ProductHuntAdapter()

    with patch("max.imports.producthunt_adapter._get_token", return_value=None):
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_parses_products() -> None:
    adapter = ProductHuntAdapter(config={"topics": ["developer-tools"]})

    with (
        patch("max.imports.producthunt_adapter._get_token", return_value="test-token"),
        patch(
            "max.imports.producthunt_adapter.fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.return_value = _mock_response(MOCK_PH_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    sig = signals[0]
    assert sig.title == "DevTool AI"
    assert sig.source_adapter == "producthunt_import"
    assert sig.source_type == SignalSourceType.MARKETPLACE
    assert sig.url == "https://www.producthunt.com/posts/devtool-ai"
    assert sig.author == "Jane Doe"
    assert sig.metadata["post_id"] == "123"
    assert sig.metadata["votes"] == 450
    assert sig.metadata["comments"] == 32
    assert sig.metadata["website"] == "https://devtool.ai"
    assert len(sig.metadata["makers"]) == 1
    assert sig.metadata["makers"][0]["username"] == "janedoe"


@pytest.mark.asyncio
async def test_fetch_product_without_makers() -> None:
    adapter = ProductHuntAdapter(config={"topics": ["saas"]})

    with (
        patch("max.imports.producthunt_adapter._get_token", return_value="test-token"),
        patch(
            "max.imports.producthunt_adapter.fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.return_value = _mock_response(MOCK_PH_RESPONSE)
        signals = await adapter.fetch(limit=10)

    no_maker = [s for s in signals if s.title == "SaaS Metrics"][0]
    assert no_maker.author is None
    assert no_maker.metadata["makers"] == []


@pytest.mark.asyncio
async def test_fetch_respects_limit() -> None:
    adapter = ProductHuntAdapter(config={"topics": ["developer-tools"]})

    with (
        patch("max.imports.producthunt_adapter._get_token", return_value="test-token"),
        patch(
            "max.imports.producthunt_adapter.fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.return_value = _mock_response(MOCK_PH_RESPONSE)
        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_deduplicates() -> None:
    dup_response = {
        "data": {
            "posts": {
                "edges": [
                    MOCK_PH_RESPONSE["data"]["posts"]["edges"][0],
                    MOCK_PH_RESPONSE["data"]["posts"]["edges"][0],
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }
    }
    adapter = ProductHuntAdapter(config={"topics": ["developer-tools"]})

    with (
        patch("max.imports.producthunt_adapter._get_token", return_value="test-token"),
        patch(
            "max.imports.producthunt_adapter.fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.return_value = _mock_response(dup_response)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_handles_api_error() -> None:
    adapter = ProductHuntAdapter(config={"topics": ["developer-tools"]})

    with (
        patch("max.imports.producthunt_adapter._get_token", return_value="test-token"),
        patch(
            "max.imports.producthunt_adapter.fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.side_effect = Exception("API error")
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_empty_response() -> None:
    adapter = ProductHuntAdapter(config={"topics": ["developer-tools"]})

    with (
        patch("max.imports.producthunt_adapter._get_token", return_value="test-token"),
        patch(
            "max.imports.producthunt_adapter.fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.return_value = _mock_response(MOCK_PH_EMPTY)
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_credibility_capped() -> None:
    high_vote_response = {
        "data": {
            "posts": {
                "edges": [
                    {
                        "node": {
                            **MOCK_PH_RESPONSE["data"]["posts"]["edges"][0]["node"],
                            "votesCount": 50000,
                        }
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }
    }
    adapter = ProductHuntAdapter(config={"topics": ["developer-tools"]})

    with (
        patch("max.imports.producthunt_adapter._get_token", return_value="test-token"),
        patch(
            "max.imports.producthunt_adapter.fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.return_value = _mock_response(high_vote_response)
        signals = await adapter.fetch(limit=10)

    assert signals[0].credibility == 1.0

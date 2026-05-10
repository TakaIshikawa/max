"""Tests for Indie Hackers import adapter — bootstrapped startup signals."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.imports.indiehackers_adapter import (
    IndieHackersAdapter,
    _build_tags,
    _compute_credibility,
    _extract_revenue,
    _extract_tech_stack,
    _parse_dt,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────

MOCK_POST = {
    "id": "post-001",
    "title": "Just hit $5,000/mo MRR with my SaaS",
    "body": "Built with Next.js and Supabase. Growth came from SEO and content marketing.",
    "author": {"username": "indiemaker"},
    "category": "milestones",
    "url": "https://www.indiehackers.com/post/post-001",
    "published_at": "2024-03-15T10:00:00Z",
    "upvotes": 42,
    "comment_count": 15,
    "product": {"name": "MySaaS", "tagline": "A bootstrapped tool"},
}

MOCK_POST_2 = {
    "id": "post-002",
    "title": "How I launched my bootstrapped app",
    "body": "Used React and Stripe for payments. Shipped in 2 weeks.",
    "author": {"username": "builder"},
    "category": "products",
    "url": "https://www.indiehackers.com/post/post-002",
    "published_at": "2024-03-10T08:00:00Z",
    "upvotes": 20,
    "comment_count": 8,
    "product": {"name": "LaunchApp", "tagline": "Ship fast"},
}

MOCK_POST_MINIMAL = {
    "id": "post-003",
    "title": "Discussion about growth",
    "body": "",
    "author": {},
    "category": "",
    "published_at": None,
    "upvotes": 0,
    "comment_count": 0,
}

MOCK_RESPONSE = {"posts": [MOCK_POST, MOCK_POST_2]}
MOCK_EMPTY_RESPONSE = {"posts": []}


def _mock_response(payload: dict, *, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = payload
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


# ── Unit tests ───────────────────────────────────────────────────────


def test_parse_dt_valid() -> None:
    dt = _parse_dt("2024-03-15T10:00:00+00:00")
    assert dt is not None
    assert dt.year == 2024
    assert dt.month == 3


def test_parse_dt_zulu() -> None:
    dt = _parse_dt("2024-03-15T10:00:00Z")
    assert dt is not None


def test_parse_dt_none() -> None:
    assert _parse_dt(None) is None


def test_parse_dt_invalid() -> None:
    assert _parse_dt("not-a-date") is None


def test_extract_tech_stack() -> None:
    text = "Built with Next.js and Supabase, using Tailwind for styling"
    stack = _extract_tech_stack(text)
    assert "next.js" in stack
    assert "supabase" in stack
    assert "tailwind" in stack


def test_extract_tech_stack_empty() -> None:
    assert _extract_tech_stack("") == []
    assert _extract_tech_stack("no tech here") == []


def test_extract_revenue_mrr() -> None:
    result = _extract_revenue("Just hit $5,000/mo MRR")
    assert result is not None
    assert "$5,000/mo" in result


def test_extract_revenue_none() -> None:
    assert _extract_revenue("no revenue data") is None
    assert _extract_revenue("") is None


def test_build_tags_milestone() -> None:
    tags = _build_tags(MOCK_POST, "milestones")
    assert "indiehackers" in tags
    assert "bootstrapped" in tags
    assert "milestones" in tags
    assert "revenue" in tags


def test_build_tags_launch() -> None:
    tags = _build_tags(MOCK_POST_2, "products")
    assert "launch" in tags
    assert "products" in tags


def test_compute_credibility_high() -> None:
    score = _compute_credibility({"upvotes": 100, "comment_count": 50})
    assert score == 1.0


def test_compute_credibility_low() -> None:
    score = _compute_credibility({"upvotes": 0, "comment_count": 0})
    assert score == 0.1


def test_compute_credibility_moderate() -> None:
    score = _compute_credibility({"upvotes": 42, "comment_count": 15})
    assert 0.1 < score < 1.0


# ── Adapter property tests ───────────────────────────────────────────


def test_adapter_name() -> None:
    adapter = IndieHackersAdapter()
    assert adapter.name == "indiehackers_import"


def test_adapter_source_type() -> None:
    adapter = IndieHackersAdapter()
    assert adapter.source_type == SignalSourceType.FORUM.value


def test_adapter_default_categories() -> None:
    adapter = IndieHackersAdapter()
    assert "products" in adapter.categories
    assert "milestones" in adapter.categories


def test_adapter_custom_search_terms() -> None:
    adapter = IndieHackersAdapter(config={"search_terms": ["ai", "llm"]})
    assert adapter.search_terms == ["ai", "llm"]


def test_adapter_query() -> None:
    adapter = IndieHackersAdapter(config={"query": "saas revenue"})
    assert adapter.query == "saas revenue"


# ── Fetch tests with mocked API ──────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_posts() -> None:
    adapter = IndieHackersAdapter(config={"query": "saas"})

    with patch(
        "max.imports.indiehackers_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    sig = signals[0]
    assert sig.title == "Just hit $5,000/mo MRR with my SaaS"
    assert sig.source_adapter == "indiehackers_import"
    assert sig.source_type == SignalSourceType.FORUM
    assert sig.url == "https://www.indiehackers.com/post/post-001"
    assert sig.author == "indiemaker"
    assert sig.metadata["post_id"] == "post-001"
    assert sig.metadata["upvotes"] == 42
    assert sig.metadata["comment_count"] == 15
    assert sig.metadata["product_name"] == "MySaaS"
    assert "next.js" in sig.metadata["tech_stack"]
    assert "supabase" in sig.metadata["tech_stack"]
    assert sig.metadata["revenue_mention"] is not None


@pytest.mark.asyncio
async def test_fetch_respects_limit() -> None:
    adapter = IndieHackersAdapter(config={"query": "saas"})

    with patch(
        "max.imports.indiehackers_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_RESPONSE)
        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_deduplicates() -> None:
    dup_response = {"posts": [MOCK_POST, MOCK_POST]}
    adapter = IndieHackersAdapter(config={"query": "saas"})

    with patch(
        "max.imports.indiehackers_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(dup_response)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_handles_api_error() -> None:
    adapter = IndieHackersAdapter(config={"query": "saas"})

    with patch(
        "max.imports.indiehackers_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.side_effect = Exception("API error")
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_empty_response() -> None:
    adapter = IndieHackersAdapter(config={"query": "saas"})

    with patch(
        "max.imports.indiehackers_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_EMPTY_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_handles_missing_fields() -> None:
    response = {"posts": [MOCK_POST_MINIMAL]}
    adapter = IndieHackersAdapter(config={"query": "growth"})

    with patch(
        "max.imports.indiehackers_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(response)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    sig = signals[0]
    assert sig.title == "Discussion about growth"
    assert sig.author is None
    assert sig.published_at is None
    assert sig.metadata["tech_stack"] == []
    assert sig.metadata["revenue_mention"] is None


@pytest.mark.asyncio
async def test_fetch_multiple_search_terms() -> None:
    adapter = IndieHackersAdapter(config={"search_terms": ["saas", "launch"]})

    with patch(
        "max.imports.indiehackers_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert mock_fetch.call_count >= 1
    assert len(signals) >= 2

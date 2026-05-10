"""Tests for Wikipedia import adapter — technology article signals."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.imports.wikipedia_adapter import (
    WikipediaAdapter,
    _build_tags,
    _parse_dt,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────

MOCK_SEARCH_RESULT = {
    "query": {
        "search": [
            {
                "title": "Rust (programming language)",
                "pageid": 46981109,
                "snippet": "Rust is a multi-paradigm, general-purpose programming language",
                "timestamp": "2024-03-01T12:00:00Z",
                "wordcount": 8500,
            },
            {
                "title": "Kubernetes",
                "pageid": 44571355,
                "snippet": "Kubernetes is an open-source container orchestration system",
                "timestamp": "2024-02-28T10:00:00Z",
                "wordcount": 12000,
            },
        ]
    }
}

MOCK_CATEGORIES_RESPONSE = {
    "query": {
        "pages": {
            "46981109": {
                "categories": [
                    {"title": "Category:Programming languages"},
                    {"title": "Category:Systems programming languages"},
                ]
            }
        }
    }
}

MOCK_EMPTY_RESPONSE = {"query": {"search": []}}


def _mock_response(payload: dict, *, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = payload
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


# ── Unit tests ───────────────────────────────────────────────────────


def test_parse_dt_valid() -> None:
    dt = _parse_dt("2024-03-01T12:00:00+00:00")
    assert dt is not None
    assert dt.year == 2024


def test_parse_dt_zulu() -> None:
    dt = _parse_dt("2024-03-01T12:00:00Z")
    assert dt is not None


def test_parse_dt_none() -> None:
    assert _parse_dt(None) is None


def test_build_tags_programming() -> None:
    tags = _build_tags("Rust (programming language)", ["Programming languages"])
    assert "wikipedia" in tags
    assert "knowledge" in tags
    assert "programming" in tags


def test_build_tags_infrastructure() -> None:
    tags = _build_tags("Kubernetes", ["Cloud computing"])
    assert "infrastructure" in tags


def test_build_tags_basic() -> None:
    tags = _build_tags("Some Article", [])
    assert "wikipedia" in tags
    assert "knowledge" in tags


# ── Adapter property tests ───────────────────────────────────────────


def test_adapter_name() -> None:
    adapter = WikipediaAdapter()
    assert adapter.name == "wikipedia_import"


def test_adapter_source_type() -> None:
    adapter = WikipediaAdapter()
    assert adapter.source_type == SignalSourceType.ARTICLE.value


def test_adapter_default_search_terms() -> None:
    adapter = WikipediaAdapter()
    assert len(adapter.search_terms) > 0


def test_adapter_custom_search_terms() -> None:
    adapter = WikipediaAdapter(config={"search_terms": ["Python"]})
    assert adapter.search_terms == ["Python"]


def test_adapter_query() -> None:
    adapter = WikipediaAdapter(config={"query": "machine learning"})
    assert adapter.query == "machine learning"


# ── Fetch tests with mocked API ──────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_articles() -> None:
    adapter = WikipediaAdapter(config={"query": "rust programming"})

    with patch(
        "max.imports.wikipedia_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_SEARCH_RESULT)
        # Second call is for categories
        mock_fetch.side_effect = [
            _mock_response(MOCK_SEARCH_RESULT),
            _mock_response(MOCK_CATEGORIES_RESPONSE),
            _mock_response(MOCK_CATEGORIES_RESPONSE),
        ]
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    sig = signals[0]
    assert sig.title == "Rust (programming language)"
    assert sig.source_adapter == "wikipedia_import"
    assert sig.source_type == SignalSourceType.ARTICLE
    assert "wikipedia" in sig.url
    assert sig.metadata["page_id"] == 46981109
    assert sig.metadata["word_count"] == 8500


@pytest.mark.asyncio
async def test_fetch_respects_limit() -> None:
    adapter = WikipediaAdapter(config={"query": "rust"})

    with patch(
        "max.imports.wikipedia_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_SEARCH_RESULT)
        mock_fetch.side_effect = [
            _mock_response(MOCK_SEARCH_RESULT),
            _mock_response(MOCK_CATEGORIES_RESPONSE),
        ]
        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_handles_api_error() -> None:
    adapter = WikipediaAdapter(config={"query": "rust"})

    with patch(
        "max.imports.wikipedia_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.side_effect = Exception("API error")
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_empty_response() -> None:
    adapter = WikipediaAdapter(config={"query": "nonexistent"})

    with patch(
        "max.imports.wikipedia_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_EMPTY_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_deduplicates() -> None:
    dup_response = {
        "query": {
            "search": [
                MOCK_SEARCH_RESULT["query"]["search"][0],
                MOCK_SEARCH_RESULT["query"]["search"][0],
            ]
        }
    }
    adapter = WikipediaAdapter(config={"query": "rust"})

    with patch(
        "max.imports.wikipedia_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(dup_response)
        mock_fetch.side_effect = [
            _mock_response(dup_response),
            _mock_response(MOCK_CATEGORIES_RESPONSE),
        ]
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1

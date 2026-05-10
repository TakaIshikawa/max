"""Tests for W3Techs import adapter — web technology usage signals."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.imports.w3techs_adapter import (
    W3TechsAdapter,
    _build_tags,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────

MOCK_HTML = """
<html><body>
<table>
<tr><td>PHP 77.4%</td></tr>
<tr><td>ASP.NET 6.5%</td></tr>
<tr><td>Ruby 5.4%</td></tr>
<tr><td>Java 4.5%</td></tr>
<tr><td>Python 2.1%</td></tr>
<tr><td>JavaScript/Node 1.8%</td></tr>
</table>
</body></html>
"""

MOCK_HTML_EMPTY = "<html><body><p>No data available</p></body></html>"


def _mock_response(text: str = "", payload: dict | None = None, *, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    if payload:
        resp.json.return_value = payload
    return resp


# ── Unit tests ───────────────────────────────────────────────────────


def test_build_tags_programming() -> None:
    tags = _build_tags("PHP", "programming_languages")
    assert "w3techs" in tags
    assert "market-share" in tags
    assert "programming" in tags
    assert "programming-languages" in tags


def test_build_tags_cms() -> None:
    tags = _build_tags("WordPress", "content_management")
    assert "cms" in tags
    assert "content-management" in tags


def test_build_tags_webserver() -> None:
    tags = _build_tags("Nginx", "web_servers")
    assert "webserver" in tags


def test_build_tags_javascript() -> None:
    tags = _build_tags("jQuery", "javascript_libraries")
    assert "javascript" in tags


# ── Adapter property tests ───────────────────────────────────────────


def test_adapter_name() -> None:
    adapter = W3TechsAdapter()
    assert adapter.name == "w3techs_import"


def test_adapter_source_type() -> None:
    adapter = W3TechsAdapter()
    assert adapter.source_type == SignalSourceType.MARKET.value


def test_adapter_default_categories() -> None:
    adapter = W3TechsAdapter()
    assert "programming_languages" in adapter.categories
    assert "content_management" in adapter.categories


def test_adapter_custom_categories() -> None:
    adapter = W3TechsAdapter(config={"categories": ["web_servers"]})
    assert adapter.categories == ["web_servers"]


def test_adapter_query() -> None:
    adapter = W3TechsAdapter(config={"query": "programming_languages"})
    assert adapter.query == "programming_languages"


# ── Parse tests ──────────────────────────────────────────────────────


def test_parse_usage_data() -> None:
    adapter = W3TechsAdapter()
    entries = adapter._parse_usage_data(MOCK_HTML)
    assert len(entries) >= 4
    # Should be sorted by percentage descending
    names = [name for name, _ in entries]
    assert "PHP" in names
    percentages = [pct for _, pct in entries]
    assert percentages == sorted(percentages, reverse=True)


def test_parse_usage_data_empty() -> None:
    adapter = W3TechsAdapter()
    entries = adapter._parse_usage_data(MOCK_HTML_EMPTY)
    assert entries == []


# ── Fetch tests with mocked API ──────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_category() -> None:
    adapter = W3TechsAdapter(config={"query": "programming_languages"})

    with patch(
        "max.imports.w3techs_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(text=MOCK_HTML)
        signals = await adapter.fetch(limit=10)

    assert len(signals) >= 4
    sig = signals[0]
    assert sig.source_adapter == "w3techs_import"
    assert sig.source_type == SignalSourceType.MARKET
    assert "market share" in sig.title
    assert sig.metadata["percentage"] > 0
    assert sig.metadata["category"] == "programming_languages"


@pytest.mark.asyncio
async def test_fetch_respects_limit() -> None:
    adapter = W3TechsAdapter(config={"query": "programming_languages"})

    with patch(
        "max.imports.w3techs_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(text=MOCK_HTML)
        signals = await adapter.fetch(limit=2)

    assert len(signals) == 2


@pytest.mark.asyncio
async def test_fetch_handles_api_error() -> None:
    adapter = W3TechsAdapter(config={"query": "programming_languages"})

    with patch(
        "max.imports.w3techs_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.side_effect = Exception("Network error")
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_empty_html() -> None:
    adapter = W3TechsAdapter(config={"query": "programming_languages"})

    with patch(
        "max.imports.w3techs_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(text=MOCK_HTML_EMPTY)
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_multiple_categories() -> None:
    adapter = W3TechsAdapter(config={"categories": ["programming_languages", "web_servers"]})

    with patch(
        "max.imports.w3techs_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(text=MOCK_HTML)
        signals = await adapter.fetch(limit=30)

    # Called once per category
    assert mock_fetch.call_count == 2


@pytest.mark.asyncio
async def test_fetch_deduplicates_across_categories() -> None:
    adapter = W3TechsAdapter(config={"categories": ["programming_languages", "programming_languages"]})

    with patch(
        "max.imports.w3techs_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(text=MOCK_HTML)
        signals = await adapter.fetch(limit=30)

    # Even though fetched twice, should deduplicate
    titles = [s.title for s in signals]
    assert len(titles) == len(set(titles))

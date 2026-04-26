"""Tests for the Chrome Web Store source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.chrome_web_store import (
    CHROME_WEB_STORE_SEARCH_URL,
    ChromeWebStoreAdapter,
    _DEFAULT_QUERIES,
    parse_chrome_web_store_response,
)
from max.types.signal import SignalSourceType


JSON_RESPONSE = {
    "extensions": [
        {
            "extension_id": "agent-tools",
            "name": "Agent Tools",
            "description": "Run agent workflows from the browser.",
            "publisher": "Example DevTools",
            "category": "Developer Tools",
            "users": "125,000+",
            "rating": 4.7,
            "rating_count": 900,
            "url": "/detail/agent-tools",
            "published_at": "2026-04-20T12:30:00Z",
        },
        {
            "extensionId": "tab-helper",
            "displayName": "Tab Helper",
            "summary": "Organize browser tabs.",
            "developer": "Tab Co",
            "categories": ["Productivity"],
            "userCount": 50000,
            "averageRating": 4.1,
            "url": "https://chromewebstore.google.com/detail/tab-helper",
        },
    ]
}


HTML_RESPONSE = """
<html>
  <body>
    <a
      data-extension-id="agent-tools"
      data-name="Agent Tools"
      data-description="Run agent workflows from the browser."
      data-publisher="Example DevTools"
      data-category="Developer Tools"
      data-users="125,000+"
      data-rating="4.7"
      data-rating-count="900"
      href="/detail/agent-tools">
    </a>
    <script type="application/ld+json">
      {
        "@type": "SoftwareApplication",
        "id": "json-extension",
        "name": "JSON Extension",
        "description": "Structured data extension.",
        "author": "JSON Co",
        "category": "Productivity",
        "userCount": 25000,
        "aggregateRating": {"ratingValue": 4.5, "ratingCount": 300},
        "url": "https://chromewebstore.google.com/detail/json-extension"
      }
    </script>
  </body>
</html>
"""


def test_chrome_web_store_adapter_properties() -> None:
    adapter = ChromeWebStoreAdapter()

    assert adapter.name == "chrome_web_store"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.queries == _DEFAULT_QUERIES
    assert adapter.categories == []
    assert adapter.min_rating is None
    assert adapter.min_users is None
    assert adapter.max_items is None


def test_chrome_web_store_adapter_custom_config_and_watchlist() -> None:
    adapter = ChromeWebStoreAdapter(
        config={
            "queries": ["agent"],
            "watchlist_terms": ["mcp"],
            "categories": ["Developer Tools"],
            "min_rating": "4.2",
            "min_users": "10000",
            "max_items": "5",
        }
    )

    assert adapter.queries == ["agent", "mcp"]
    assert adapter.categories == ["Developer Tools"]
    assert adapter.min_rating == 4.2
    assert adapter.min_users == 10000
    assert adapter.max_items == 5


def test_parse_chrome_web_store_json_fixture_without_network() -> None:
    rows = parse_chrome_web_store_response(__import__("json").dumps(JSON_RESPONSE))

    assert len(rows) == 2
    assert rows[0]["extension_id"] == "agent-tools"
    assert rows[0]["name"] == "Agent Tools"
    assert rows[0]["user_count"] == 125000
    assert rows[0]["rating"] == 4.7
    assert rows[0]["category"] == "Developer Tools"
    assert rows[0]["extension_url"] == "https://chromewebstore.google.com/detail/agent-tools"


def test_parse_chrome_web_store_html_fixture_without_network() -> None:
    rows = parse_chrome_web_store_response(HTML_RESPONSE)

    assert len(rows) == 2
    assert rows[0]["extension_id"] == "agent-tools"
    assert rows[0]["user_count"] == 125000
    assert rows[0]["rating"] == 4.7
    assert rows[1]["extension_id"] == "json-extension"
    assert rows[1]["category"] == "Productivity"


@pytest.mark.asyncio
async def test_chrome_web_store_fetch_emits_signals_from_search_results() -> None:
    adapter = ChromeWebStoreAdapter(config={"queries": ["agent"], "categories": ["Developer Tools"]})

    with patch("max.sources.chrome_web_store.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(text=__import__("json").dumps(JSON_RESPONSE))

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert mock_fetch.call_args_list[0].args[0] == CHROME_WEB_STORE_SEARCH_URL.format(query="agent")
    assert mock_fetch.call_args_list[0].kwargs["params"] == {"hl": "en"}

    signal = signals[0]
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "chrome_web_store"
    assert signal.title == "Agent Tools"
    assert signal.content == "Run agent workflows from the browser."
    assert signal.url == "https://chromewebstore.google.com/detail/agent-tools"
    assert signal.author == "Example DevTools"
    assert signal.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert signal.tags == ["Developer Tools", "agent"]
    assert signal.credibility > 0.8
    assert signal.metadata["install_count"] == 125000
    assert signal.metadata["user_count"] == 125000
    assert signal.metadata["rating"] == 4.7
    assert signal.metadata["average_rating"] == 4.7
    assert signal.metadata["rating_count"] == 900
    assert signal.metadata["category"] == "Developer Tools"
    assert signal.metadata["extension_url"] == signal.url
    assert signal.metadata["source_url"] == signal.url
    assert signal.metadata["search_query"] == "agent"


@pytest.mark.asyncio
async def test_chrome_web_store_filters_are_deterministic() -> None:
    adapter = ChromeWebStoreAdapter(
        config={
            "queries": ["agent"],
            "categories": ["Developer Tools"],
            "min_rating": 4.5,
            "min_users": 100000,
            "max_items": 1,
        }
    )

    with patch("max.sources.chrome_web_store.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(text=__import__("json").dumps(JSON_RESPONSE))

        signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == ["Agent Tools"]
    assert len(signals) == 1

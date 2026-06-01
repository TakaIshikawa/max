from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.cloudflare_changelog import CloudflareChangelogAdapter
from max.types.signal import SignalSourceType


RSS_XML = """\
<rss version="2.0">
  <channel>
    <item>
      <title>Workers AI adds batch inference</title>
      <link>https://developers.cloudflare.com/changelog/workers-ai-batch/</link>
      <description>Batch inference is now available.</description>
      <pubDate>Mon, 01 Jun 2026 12:00:00 GMT</pubDate>
      <category>Workers AI</category>
      <guid>workers-ai-batch</guid>
    </item>
    <item>
      <title>DNS analytics update</title>
      <link>https://developers.cloudflare.com/changelog/dns-analytics/</link>
      <description>DNS analytics has new filters.</description>
      <pubDate>Mon, 01 Jun 2026 13:00:00 GMT</pubDate>
      <category>DNS</category>
    </item>
  </channel>
</rss>
"""


def _response(xml: str = RSS_XML) -> MagicMock:
    response = MagicMock()
    response.text = xml
    response.status_code = 200
    return response


def test_name_and_source_type() -> None:
    adapter = CloudflareChangelogAdapter()

    assert adapter.name == "cloudflare_changelog"
    assert adapter.source_type == SignalSourceType.NEWS.value


@pytest.mark.asyncio
async def test_fetch_converts_changelog_entries_to_news_signals() -> None:
    adapter = CloudflareChangelogAdapter(config={"feed_url": "https://example.com/cf.xml"})

    with patch("max.sources.cloudflare_changelog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert signals[0].source_type == SignalSourceType.NEWS
    assert signals[0].source_adapter == "cloudflare_changelog"
    assert signals[0].published_at == datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    assert signals[0].tags == ["cloudflare", "Workers AI"]
    assert signals[0].metadata["products"] == ["Workers AI"]


@pytest.mark.asyncio
async def test_product_and_keyword_filters_apply_before_limit() -> None:
    adapter = CloudflareChangelogAdapter(config={
        "products": ["DNS"],
        "keywords": ["analytics"],
    })

    with patch("max.sources.cloudflare_changelog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=1)

    assert [signal.title for signal in signals] == ["DNS analytics update"]

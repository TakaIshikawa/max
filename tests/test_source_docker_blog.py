from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.docker_blog import DockerBlogAdapter
from max.types.signal import SignalSourceType

RSS_XML = """\
<rss version="2.0"><channel>
  <item>
    <title>Docker Desktop adds model runner</title>
    <link>https://www.docker.com/blog/model-runner/</link>
    <description>Docker Desktop now supports local AI workflows.</description>
    <pubDate>Mon, 01 Jun 2026 08:00:00 -0700</pubDate>
    <category>Product</category>
    <guid>docker-model-runner</guid>
  </item>
  <item>
    <title>Duplicate model runner</title>
    <link>https://www.docker.com/blog/model-runner-copy/</link>
    <description>Duplicate guid.</description>
    <pubDate>Mon, 01 Jun 2026 08:30:00 -0700</pubDate>
    <category>Product</category>
    <guid>docker-model-runner</guid>
  </item>
  <item>
    <title>Docker security update</title>
    <link>https://www.docker.com/blog/security-update/</link>
    <description>Security improvements for images.</description>
    <pubDate>Mon, 01 Jun 2026 09:00:00 GMT</pubDate>
    <category>Security</category>
  </item>
  <item>
    <title>Old Docker event</title>
    <link>https://www.docker.com/blog/old-event/</link>
    <description>Old event.</description>
    <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
    <category>Events</category>
  </item>
</channel></rss>
"""


def _response() -> MagicMock:
    response = MagicMock()
    response.text = RSS_XML
    return response


@pytest.mark.asyncio
async def test_fetch_converts_rss_items_and_deduplicates_guid() -> None:
    adapter = DockerBlogAdapter(config={"feed_url": "https://example.com/docker.xml"})

    with patch("max.sources.docker_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == [
        "Docker Desktop adds model runner",
        "Docker security update",
        "Old Docker event",
    ]
    assert signals[0].id == "docker_blog:14f05359295e84cd"
    assert signals[0].source_type == SignalSourceType.NEWS
    assert signals[0].source_adapter == "docker_blog"
    assert signals[0].url == "https://www.docker.com/blog/model-runner/"
    assert signals[0].published_at == datetime(2026, 6, 1, 15, 0, tzinfo=timezone.utc)
    assert signals[0].tags == ["docker", "Product"]
    assert signals[0].metadata["categories"] == ["Product"]


@pytest.mark.asyncio
async def test_filters_apply_before_limit_truncation() -> None:
    adapter = DockerBlogAdapter(
        config={"categories": ["Security"], "keywords": ["images"], "max_age_days": 10}
    )

    with patch("max.sources.docker_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=1)

    assert [signal.title for signal in signals] == ["Docker security update"]

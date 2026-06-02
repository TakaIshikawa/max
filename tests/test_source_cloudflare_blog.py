from __future__ import annotations

import pytest

from max.sources.cloudflare_blog import CloudflareBlogAdapter, parse_cloudflare_blog
from max.types.signal import SignalSourceType


RSS = """\
<rss version="2.0">
  <channel>
    <item>
      <title>Workers AI platform update</title>
      <link>https://blog.cloudflare.com/workers-ai-platform/?utm_source=feed</link>
      <description><![CDATA[<p>New AI platform features.</p>]]></description>
      <pubDate>Mon, 01 Jun 2026 12:00:00 GMT</pubDate>
      <category>Workers AI</category>
      <category>Developer Platform</category>
    </item>
    <item>
      <title>Workers AI duplicate</title>
      <link>https://blog.cloudflare.com/workers-ai-platform/#comments</link>
      <description>Duplicate URL should be collapsed.</description>
    </item>
  </channel>
</rss>
"""


def test_parse_cloudflare_blog_normalizes_feed_entries_and_dedupes() -> None:
    signals = parse_cloudflare_blog(RSS)

    assert len(signals) == 1
    assert signals[0].id.startswith("cloudflare_blog:")
    assert signals[0].source_type == SignalSourceType.NEWS
    assert signals[0].title == "Workers AI platform update"
    assert signals[0].url == "https://blog.cloudflare.com/workers-ai-platform"
    assert signals[0].content == "New AI platform features."
    assert signals[0].tags == ["cloudflare", "Workers AI", "Developer Platform"]
    assert signals[0].metadata["categories"] == ["Workers AI", "Developer Platform"]


def test_parse_cloudflare_blog_uses_title_when_summary_and_tags_missing() -> None:
    signals = parse_cloudflare_blog([
        {"title": "Cloudflare Radar update", "url": "https://blog.cloudflare.com/radar-update"}
    ])

    assert signals[0].content == "Cloudflare Radar update"
    assert signals[0].tags == ["cloudflare"]


@pytest.mark.asyncio
async def test_adapter_empty_feed_and_limit_handling() -> None:
    assert await CloudflareBlogAdapter(config={"payload": []}).fetch(limit=5) == []

    adapter = CloudflareBlogAdapter(config={"payload": [
        {"title": "One", "url": "https://blog.cloudflare.com/one"},
        {"title": "Two", "url": "https://blog.cloudflare.com/two"},
    ]})

    assert [signal.title for signal in await adapter.fetch(limit=1)] == ["One"]

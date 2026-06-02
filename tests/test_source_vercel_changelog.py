from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.vercel_changelog import VercelChangelogAdapter

RSS_XML = """\
<rss version="2.0"><channel>
  <item><title>Vercel Functions update</title><link>https://vercel.com/changelog/functions</link><pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate><category>Functions</category><guid>vercel-functions</guid></item>
  <item><title>Duplicate Functions update</title><link>https://vercel.com/changelog/functions-copy</link><description>Duplicate.</description><pubDate>Mon, 01 Jun 2026 11:00:00 GMT</pubDate><category>Functions</category><guid>vercel-functions</guid></item>
  <item><title>Vercel Analytics improves funnels</title><link>https://vercel.com/changelog/analytics</link><description>Analytics funnel reporting.</description><pubDate>Mon, 01 Jun 2026 12:00:00 GMT</pubDate><category>Analytics</category></item>
</channel></rss>
"""


def _response() -> MagicMock:
    response = MagicMock()
    response.text = RSS_XML
    return response


@pytest.mark.asyncio
async def test_fetch_handles_missing_summaries_and_deduplicates() -> None:
    adapter = VercelChangelogAdapter()

    with patch("max.sources.docker_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == [
        "Vercel Functions update",
        "Vercel Analytics improves funnels",
    ]
    assert signals[0].content == "Vercel Functions update"
    assert signals[0].metadata["products"] == ["Functions"]


@pytest.mark.asyncio
async def test_product_and_keyword_filters_run_before_limit() -> None:
    adapter = VercelChangelogAdapter(config={"products": ["Analytics"], "keywords": ["funnel"]})

    with patch("max.sources.docker_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=1)

    assert [signal.title for signal in signals] == ["Vercel Analytics improves funnels"]

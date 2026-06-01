from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.python_dev_blog import PythonDevBlogAdapter


RSS = """<rss><channel>
<item><title>Python 3.14 beta</title><link>https://blog.python.org/a</link><description>Release news</description><pubDate>Mon, 01 Jun 2026 08:00:00 GMT</pubDate><author>release team</author><category>release</category></item>
<item><title>Duplicate</title><link>https://blog.python.org/a</link><description>dup</description></item>
<item><title>No date</title><link>https://blog.python.org/b</link><description></description></item>
</channel></rss>"""


def _response(text: str = RSS) -> MagicMock:
    response = MagicMock()
    response.text = text
    return response


@pytest.mark.asyncio
async def test_fetch_normalizes_feed_entries_and_deduplicates_links() -> None:
    adapter = PythonDevBlogAdapter(config={"feed_url": "https://example.test/feed.xml"})
    with patch("max.sources.python_dev_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=10)
    assert [signal.title for signal in signals] == ["Python 3.14 beta", "No date"]
    assert signals[0].author == "release team"
    assert signals[0].published_at is not None
    assert signals[0].metadata["tags"] == ["release"]
    assert signals[1].published_at is None
    assert signals[1].content == "No date"


@pytest.mark.asyncio
async def test_limit_is_applied() -> None:
    adapter = PythonDevBlogAdapter()
    with patch("max.sources.python_dev_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        assert len(await adapter.fetch(limit=1)) == 1

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.nodejs_blog import NodejsBlogAdapter


RSS = """<rss><channel>
<item><title>Node.js v22.3.0 released</title><link>https://nodejs.org/en/blog/release/v22.3.0</link><description>Release notes</description><pubDate>Mon, 01 Jun 2026 08:00:00 GMT</pubDate></item>
<item><title>Project update</title><link>https://nodejs.org/en/blog/update</link><description>Community post</description></item>
</channel></rss>"""


def _response(text: str = RSS) -> MagicMock:
    response = MagicMock()
    response.text = text
    return response


@pytest.mark.asyncio
async def test_release_post_parses_version_and_line() -> None:
    adapter = NodejsBlogAdapter()
    with patch("max.sources.python_dev_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=10)
    assert signals[0].metadata["version"] == "22.3.0"
    assert signals[0].metadata["release_line"] == "22.x"
    assert "nodejs" in signals[0].tags


@pytest.mark.asyncio
async def test_non_release_missing_metadata_empty_feed_and_limit() -> None:
    adapter = NodejsBlogAdapter()
    with patch("max.sources.python_dev_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=2)
    assert signals[1].metadata["version"] is None
    with patch("max.sources.python_dev_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response("<rss><channel /></rss>")):
        assert await adapter.fetch(limit=10) == []
    with patch("max.sources.python_dev_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        assert len(await adapter.fetch(limit=1)) == 1

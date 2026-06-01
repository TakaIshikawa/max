from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.ruby_news import RubyNewsAdapter


RSS = """<rss><channel>
<item><title>Ruby 3.4.1 Released</title><link>https://www.ruby-lang.org/en/news/2026/06/01/ruby-3-4-1-released/</link><description>Bug fixes</description><category>Releases</category></item>
<item><title>Security note</title><link>https://www.ruby-lang.org/en/news/security/</link></item>
</channel></rss>"""


def _response(text: str = RSS) -> MagicMock:
    response = MagicMock()
    response.text = text
    return response


@pytest.mark.asyncio
async def test_announcement_normalization_version_and_missing_summary() -> None:
    adapter = RubyNewsAdapter()
    with patch("max.sources.python_dev_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=10)
    assert signals[0].metadata["version"] == "3.4.1"
    assert signals[0].metadata["category"] == "Releases"
    assert signals[0].title == "Ruby 3.4.1 Released"
    assert signals[1].content == "Security note"


@pytest.mark.asyncio
async def test_deterministic_id_behavior() -> None:
    adapter = RubyNewsAdapter()
    with patch("max.sources.python_dev_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        first = await adapter.fetch(limit=1)
    with patch("max.sources.python_dev_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        second = await adapter.fetch(limit=1)
    assert first[0].id == second[0].id

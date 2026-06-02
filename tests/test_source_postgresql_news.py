from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.postgresql_news import PostgresqlNewsAdapter

RSS_XML = """\
<rss version="2.0"><channel>
  <item><title>PostgreSQL 18 beta released</title><link>https://postgresql.org/about/news/postgresql-18-beta</link><description>Release testing begins.</description><pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate><category>Releases</category><guid>pg-18-beta</guid></item>
  <item><title>Community event announced</title><link>https://postgresql.org/about/news/community-event</link><description>Community conference.</description><pubDate>Mon, 01 Jun 2026 12:00:00 GMT</pubDate><category>Community</category></item>
</channel></rss>
"""


def _response() -> MagicMock:
    response = MagicMock()
    response.text = RSS_XML
    return response


@pytest.mark.asyncio
async def test_fetch_converts_postgresql_news() -> None:
    adapter = PostgresqlNewsAdapter()

    with patch("max.sources.docker_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == [
        "PostgreSQL 18 beta released",
        "Community event announced",
    ]
    assert signals[0].source_adapter == "postgresql_news"
    assert signals[0].metadata["categories"] == ["Releases"]


@pytest.mark.asyncio
async def test_category_and_keyword_filters_run_before_limit() -> None:
    adapter = PostgresqlNewsAdapter(config={"categories": ["Community"], "keywords": ["conference"]})

    with patch("max.sources.docker_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=1)

    assert [signal.title for signal in signals] == ["Community event announced"]

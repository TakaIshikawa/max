from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.supabase_changelog import SupabaseChangelogAdapter

RSS_XML = """\
<rss version="2.0"><channel>
  <item><title>Supabase Auth update</title><link>https://supabase.com/changelog/auth</link><description>Auth providers update.</description><pubDate>not a date</pubDate><category>Auth</category><guid>supabase-auth</guid></item>
  <item><title>Supabase Edge Functions logs</title><link>https://supabase.com/changelog/functions</link><description>Function log search.</description><pubDate>Mon, 01 Jun 2026 12:00:00 GMT</pubDate><category>Functions</category></item>
</channel></rss>
"""


def _response() -> MagicMock:
    response = MagicMock()
    response.text = RSS_XML
    return response


@pytest.mark.asyncio
async def test_fetch_returns_stable_signals_and_ignores_invalid_dates() -> None:
    adapter = SupabaseChangelogAdapter()

    with patch("max.sources.docker_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == [
        "Supabase Auth update",
        "Supabase Edge Functions logs",
    ]
    assert signals[0].published_at is None
    assert signals[0].id == "supabase_changelog:3bc82cc3b5765699"
    assert signals[0].metadata["products"] == ["Auth"]


@pytest.mark.asyncio
async def test_product_keyword_and_limit_filters() -> None:
    adapter = SupabaseChangelogAdapter(config={"products": ["Functions"], "keywords": ["log"]})

    with patch("max.sources.docker_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=1)

    assert [signal.title for signal in signals] == ["Supabase Edge Functions logs"]

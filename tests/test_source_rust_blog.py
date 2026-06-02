from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.rust_blog import RustBlogAdapter

RSS_XML = """\
<rss version="2.0"><channel>
  <item><title>Rust 1.90.0 release</title><link>https://blog.rust-lang.org/2026/06/01/Rust-1.90.0.html</link><description>Release announcement.</description><pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate><category>Release</category><guid>rust-190</guid></item>
  <item><title>Duplicate Rust release</title><link>https://blog.rust-lang.org/duplicate</link><description>Duplicate.</description><pubDate>Mon, 01 Jun 2026 11:00:00 GMT</pubDate><category>Release</category><guid>rust-190</guid></item>
  <item><title>Rust security advisory process</title><link>https://blog.rust-lang.org/security-process</link><description>Security process update.</description><pubDate>Mon, 01 Jun 2026 12:00:00 GMT</pubDate><category>Security</category></item>
</channel></rss>
"""


def _response() -> MagicMock:
    response = MagicMock()
    response.text = RSS_XML
    return response


@pytest.mark.asyncio
async def test_fetch_converts_rust_blog_and_deduplicates() -> None:
    adapter = RustBlogAdapter()

    with patch("max.sources.docker_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == [
        "Rust 1.90.0 release",
        "Rust security advisory process",
    ]
    assert signals[0].source_adapter == "rust_blog"
    assert signals[0].metadata["is_release"] is True
    assert signals[1].metadata["is_security"] is True


@pytest.mark.asyncio
async def test_release_security_and_keyword_filters() -> None:
    adapter = RustBlogAdapter(config={"security": True, "keywords": ["process"]})

    with patch("max.sources.docker_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=1)

    assert [signal.title for signal in signals] == ["Rust security advisory process"]

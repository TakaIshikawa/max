from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.cncf_blog import CncfBlogAdapter

RSS_XML = """\
<rss version="2.0"><channel>
  <item><title>CNCF Kubernetes platform update</title><link>https://cncf.io/blog/kubernetes-platform</link><description>Platform engineering update.</description><pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate><category>Kubernetes</category><guid>cncf-kubernetes</guid></item>
  <item><title>Duplicate Kubernetes update</title><link>https://cncf.io/blog/kubernetes-copy</link><description>Duplicate.</description><pubDate>Mon, 01 Jun 2026 11:00:00 GMT</pubDate><category>Kubernetes</category><guid>cncf-kubernetes</guid></item>
  <item><title>CNCF observability case study</title><link>https://cncf.io/blog/observability</link><description>Observability adoption summary.</description><pubDate>Mon, 01 Jun 2026 12:00:00 GMT</pubDate><category>Observability</category></item>
</channel></rss>
"""


def _response() -> MagicMock:
    response = MagicMock()
    response.text = RSS_XML
    return response


@pytest.mark.asyncio
async def test_fetch_preserves_summaries_and_evidence_urls() -> None:
    adapter = CncfBlogAdapter()

    with patch("max.sources.docker_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == [
        "CNCF Kubernetes platform update",
        "CNCF observability case study",
    ]
    assert signals[0].content == "Platform engineering update."
    assert signals[0].url == "https://cncf.io/blog/kubernetes-platform"
    assert signals[0].metadata["tags"] == ["Kubernetes"]


@pytest.mark.asyncio
async def test_tag_keyword_and_limit_filters() -> None:
    adapter = CncfBlogAdapter(config={"tags": ["Observability"], "keywords": ["adoption"]})

    with patch("max.sources.docker_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=1)

    assert [signal.title for signal in signals] == ["CNCF observability case study"]

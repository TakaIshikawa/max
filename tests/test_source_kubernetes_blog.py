from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.kubernetes_blog import KubernetesBlogAdapter
from max.types.signal import SignalSourceType


RSS_XML = """\
<rss version="2.0">
  <channel>
    <item>
      <title>Kubernetes v1.31 release</title>
      <link>https://kubernetes.io/blog/2026/06/01/kubernetes-131/</link>
      <description>Kubernetes release notes and upgrade details.</description>
      <pubDate>Mon, 01 Jun 2026 08:00:00 GMT</pubDate>
      <category>Release</category>
      <guid>kubernetes-131</guid>
    </item>
    <item>
      <title>Kubernetes v1.31 duplicate</title>
      <link>https://kubernetes.io/blog/2026/06/01/kubernetes-131-duplicate/</link>
      <description>Duplicate guid should be ignored.</description>
      <pubDate>Mon, 01 Jun 2026 08:30:00 GMT</pubDate>
      <category>Release</category>
      <guid>kubernetes-131</guid>
    </item>
    <item>
      <title>Community update</title>
      <link>https://kubernetes.io/blog/2026/06/01/community/</link>
      <description>Community news.</description>
      <category>Community</category>
    </item>
  </channel>
</rss>
"""


def _response(xml: str = RSS_XML) -> MagicMock:
    response = MagicMock()
    response.text = xml
    response.status_code = 200
    return response


def test_name_and_source_type() -> None:
    adapter = KubernetesBlogAdapter()

    assert adapter.name == "kubernetes_blog"
    assert adapter.source_type == SignalSourceType.NEWS.value


@pytest.mark.asyncio
async def test_fetch_converts_blog_posts_and_deduplicates_by_guid() -> None:
    adapter = KubernetesBlogAdapter(config={"feed_url": "https://example.com/kubernetes.xml"})

    with patch("max.sources.kubernetes_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == [
        "Kubernetes v1.31 release",
        "Community update",
    ]
    assert signals[0].source_type == SignalSourceType.NEWS
    assert signals[0].source_adapter == "kubernetes_blog"
    assert signals[0].tags == ["kubernetes", "Release"]
    assert signals[0].metadata["tags"] == ["Release"]


@pytest.mark.asyncio
async def test_tag_and_keyword_filters_match_categories() -> None:
    adapter = KubernetesBlogAdapter(config={"tags": ["Release"], "keywords": ["upgrade"]})

    with patch("max.sources.kubernetes_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == ["Kubernetes v1.31 release"]

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.aws_whats_new import AwsWhatsNewAdapter
from max.types.signal import SignalSourceType


RSS_XML = """\
<rss version="2.0">
  <channel>
    <item>
      <title>Amazon Bedrock adds model evaluation</title>
      <link>https://aws.amazon.com/about-aws/whats-new/2026/06/bedrock-evaluation/</link>
      <description><![CDATA[<p>Amazon Bedrock now supports evaluation workflows.</p>]]></description>
      <pubDate>Mon, 01 Jun 2026 10:30:00 GMT</pubDate>
      <category>Machine Learning</category>
      <guid>bedrock-evaluation</guid>
    </item>
    <item>
      <title>Amazon S3 storage update</title>
      <link>https://aws.amazon.com/about-aws/whats-new/2026/06/s3-update/</link>
      <description>S3 lifecycle update.</description>
      <pubDate>Mon, 01 Jun 2026 11:30:00 GMT</pubDate>
      <category>Storage</category>
    </item>
    <item>
      <description>Malformed item without title and link.</description>
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
    adapter = AwsWhatsNewAdapter()

    assert adapter.name == "aws_whats_new"
    assert adapter.source_type == SignalSourceType.NEWS.value


@pytest.mark.asyncio
async def test_fetch_converts_rss_items_to_news_signals() -> None:
    adapter = AwsWhatsNewAdapter(config={"feed_url": "https://example.com/aws.xml"})

    with patch("max.sources.aws_whats_new.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    signal = signals[0]
    assert signal.source_type == SignalSourceType.NEWS
    assert signal.source_adapter == "aws_whats_new"
    assert signal.title == "Amazon Bedrock adds model evaluation"
    assert signal.content == "Amazon Bedrock now supports evaluation workflows."
    assert signal.url.endswith("/bedrock-evaluation/")
    assert signal.published_at == datetime(2026, 6, 1, 10, 30, tzinfo=timezone.utc)
    assert signal.tags == ["aws", "Machine Learning"]
    assert signal.metadata["feed_url"] == "https://example.com/aws.xml"
    assert signal.metadata["categories"] == ["Machine Learning"]


@pytest.mark.asyncio
async def test_fetch_respects_keyword_and_category_filters() -> None:
    adapter = AwsWhatsNewAdapter(config={
        "categories": ["Machine Learning"],
        "keywords": ["evaluation"],
    })

    with patch("max.sources.aws_whats_new.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == ["Amazon Bedrock adds model evaluation"]


@pytest.mark.asyncio
async def test_malformed_rss_entries_are_skipped() -> None:
    adapter = AwsWhatsNewAdapter()

    with patch("max.sources.aws_whats_new.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=10)

    assert all(signal.title for signal in signals)
    assert len(signals) == 2

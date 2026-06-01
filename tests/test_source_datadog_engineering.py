from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.datadog_engineering import DatadogEngineeringAdapter


RSS = """<rss><channel>
<item><title>Scaling telemetry</title><link>https://www.datadoghq.com/blog/engineering/scaling-telemetry/</link><description>Engineering details</description><author>Ada</author><category>Python</category><category>Infra</category></item>
<item><title>Duplicate</title><link>https://www.datadoghq.com/blog/engineering/scaling-telemetry/</link><description>dup</description></item>
<item><title>No author</title><link>https://www.datadoghq.com/blog/engineering/no-author/</link><category>Infra</category></item>
</channel></rss>"""


def _response(text: str = RSS) -> MagicMock:
    response = MagicMock()
    response.text = text
    return response


@pytest.mark.asyncio
async def test_normal_feed_absent_authors_tag_normalization_and_duplicate_urls() -> None:
    adapter = DatadogEngineeringAdapter()
    with patch("max.sources.python_dev_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=10)
    assert [signal.title for signal in signals] == ["Scaling telemetry", "No author"]
    assert signals[0].author == "Ada"
    assert signals[0].metadata["tags"] == ["infra", "python"]
    assert signals[1].author is None
    assert signals[1].content == "No author"


@pytest.mark.asyncio
async def test_limit_behavior() -> None:
    adapter = DatadogEngineeringAdapter()
    with patch("max.sources.python_dev_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        assert len(await adapter.fetch(limit=1)) == 1

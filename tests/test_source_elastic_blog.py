from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.elastic_blog import ElasticBlogAdapter


RSS = """<rss><channel>
<item><title>Elasticsearch vector search</title><link>https://www.elastic.co/search-labs/blog/elasticsearch-vector-search</link><description>Vector search updates</description><category>Elasticsearch</category></item>
<item><title>Kibana dashboard update</title><link>https://www.elastic.co/blog/kibana-dashboard</link></item>
</channel></rss>"""


def _response(text: str = RSS) -> MagicMock:
    response = MagicMock()
    response.text = text
    return response


@pytest.mark.asyncio
async def test_tag_extraction_product_area_and_missing_fields() -> None:
    adapter = ElasticBlogAdapter()
    with patch("max.sources.python_dev_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=10)
    assert signals[0].metadata["tags"] == ["Elasticsearch"]
    assert signals[0].metadata["product_area"] == "elasticsearch"
    assert signals[1].metadata["product_area"] == "kibana"
    assert signals[1].content == "Kibana dashboard update"


@pytest.mark.asyncio
async def test_limit_behavior() -> None:
    adapter = ElasticBlogAdapter()
    with patch("max.sources.python_dev_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        assert len(await adapter.fetch(limit=1)) == 1

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.hashicorp_blog import HashicorpBlogAdapter

RSS_XML = """\
<rss version="2.0"><channel>
  <item><title>Terraform provider update</title><link>https://hashicorp.com/blog/terraform-provider</link><description>Terraform provider workflows.</description><pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate><category>Terraform</category><guid>terraform-provider</guid></item>
  <item><title>Duplicate Terraform update</title><link>https://hashicorp.com/blog/terraform-provider-2</link><description>Duplicate.</description><pubDate>Mon, 01 Jun 2026 11:00:00 GMT</pubDate><category>Terraform</category><guid>terraform-provider</guid></item>
  <item><title>Vault secrets release</title><link>https://hashicorp.com/blog/vault-secrets</link><description>Vault improves secrets workflows.</description><pubDate>Mon, 01 Jun 2026 12:00:00 GMT</pubDate><category>Vault</category></item>
</channel></rss>
"""


def _response() -> MagicMock:
    response = MagicMock()
    response.text = RSS_XML
    return response


@pytest.mark.asyncio
async def test_fetch_converts_rss_items_and_deduplicates() -> None:
    adapter = HashicorpBlogAdapter()

    with patch("max.sources.docker_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == ["Terraform provider update", "Vault secrets release"]
    assert signals[0].id == "hashicorp_blog:097f18785a3b9ecf"
    assert signals[0].source_adapter == "hashicorp_blog"
    assert signals[0].tags == ["hashicorp", "Terraform"]
    assert signals[0].metadata["products"] == ["Terraform"]


@pytest.mark.asyncio
async def test_product_and_keyword_filters_run_before_limit() -> None:
    adapter = HashicorpBlogAdapter(config={"products": ["Vault"], "keywords": ["secrets"]})

    with patch("max.sources.docker_blog.fetch_with_retry", new_callable=AsyncMock, return_value=_response()):
        signals = await adapter.fetch(limit=1)

    assert [signal.title for signal in signals] == ["Vault secrets release"]

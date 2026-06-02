"""HashiCorp Blog RSS source adapter."""

from __future__ import annotations

from max.sources.docker_blog import RssBlogAdapter

DEFAULT_FEED_URL = "https://www.hashicorp.com/blog/feed.xml"


class HashicorpBlogAdapter(RssBlogAdapter):
    """Fetches HashiCorp Blog posts from the public RSS feed."""

    adapter_name = "hashicorp_blog"
    default_feed_url = DEFAULT_FEED_URL
    source_tag = "hashicorp"
    category_config_key = "products"
    config_keys = ["feed_url", "products", "keywords", "max_age_days", "timeout"]
    description = "Fetches HashiCorp Blog posts from the public RSS feed."

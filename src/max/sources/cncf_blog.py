"""CNCF Blog RSS source adapter."""

from __future__ import annotations

from max.sources.docker_blog import RssBlogAdapter

DEFAULT_FEED_URL = "https://www.cncf.io/feed/"


class CncfBlogAdapter(RssBlogAdapter):
    """Fetches CNCF Blog posts from the public RSS feed."""

    adapter_name = "cncf_blog"
    default_feed_url = DEFAULT_FEED_URL
    source_tag = "cncf"
    category_config_key = "tags"
    config_keys = ["feed_url", "tags", "keywords", "max_age_days", "timeout"]
    description = "Fetches CNCF Blog posts from the public RSS feed."

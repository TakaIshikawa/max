"""PostgreSQL News RSS source adapter."""

from __future__ import annotations

from max.sources.docker_blog import RssBlogAdapter

DEFAULT_FEED_URL = "https://www.postgresql.org/about/newsarchive.xml"


class PostgresqlNewsAdapter(RssBlogAdapter):
    """Fetches PostgreSQL release and community news from the public RSS feed."""

    adapter_name = "postgresql_news"
    default_feed_url = DEFAULT_FEED_URL
    source_tag = "postgresql"
    category_config_key = "categories"
    config_keys = ["feed_url", "categories", "keywords", "max_age_days", "timeout"]
    description = "Fetches PostgreSQL release and community news from the public RSS feed."

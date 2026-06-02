"""Vercel Changelog RSS source adapter."""

from __future__ import annotations

from max.sources.docker_blog import RssBlogAdapter

DEFAULT_FEED_URL = "https://vercel.com/changelog/rss"


class VercelChangelogAdapter(RssBlogAdapter):
    """Fetches Vercel Changelog entries from the public RSS feed."""

    adapter_name = "vercel_changelog"
    default_feed_url = DEFAULT_FEED_URL
    source_tag = "vercel"
    category_config_key = "products"
    config_keys = ["feed_url", "products", "keywords", "max_age_days", "timeout"]
    description = "Fetches Vercel Changelog entries from the public RSS feed."

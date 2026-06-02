"""Supabase Changelog RSS source adapter."""

from __future__ import annotations

from max.sources.docker_blog import RssBlogAdapter

DEFAULT_FEED_URL = "https://supabase.com/changelog/rss"


class SupabaseChangelogAdapter(RssBlogAdapter):
    """Fetches Supabase Changelog entries from the public RSS feed."""

    adapter_name = "supabase_changelog"
    default_feed_url = DEFAULT_FEED_URL
    source_tag = "supabase"
    category_config_key = "products"
    config_keys = ["feed_url", "products", "keywords", "max_age_days", "timeout"]
    description = "Fetches Supabase Changelog entries from the public RSS feed."

"""Stripe Changelog RSS source adapter."""

from __future__ import annotations

from max.sources.docker_blog import RssBlogAdapter

DEFAULT_FEED_URL = "https://stripe.com/changelog.atom"


class StripeChangelogAdapter(RssBlogAdapter):
    """Fetches Stripe changelog entries from the public feed."""

    adapter_name = "stripe_changelog"
    default_feed_url = DEFAULT_FEED_URL
    source_tag = "stripe"
    category_config_key = "products"
    config_keys = ["feed_url", "products", "keywords", "max_age_days", "timeout"]
    description = "Fetches Stripe changelog entries from the public feed."

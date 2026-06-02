"""Jira Cloud Platform Changelog RSS source adapter."""

from __future__ import annotations

from max.sources.docker_blog import RssBlogAdapter

DEFAULT_FEED_URL = "https://developer.atlassian.com/cloud/jira/platform/changelog/rss/"


class JiraCloudPlatformChangelogAdapter(RssBlogAdapter):
    """Fetches Jira Cloud Platform changelog entries from the public RSS feed."""

    adapter_name = "jira_cloud_platform_changelog"
    default_feed_url = DEFAULT_FEED_URL
    source_tag = "jira"
    category_config_key = "products"
    config_keys = ["feed_url", "products", "keywords", "max_age_days", "timeout"]
    description = "Fetches Jira Cloud Platform changelog entries from the public RSS feed."

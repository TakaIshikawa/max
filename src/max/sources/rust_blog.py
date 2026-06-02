"""Rust Blog RSS source adapter."""

from __future__ import annotations

from max.sources.docker_blog import RssBlogAdapter

DEFAULT_FEED_URL = "https://blog.rust-lang.org/feed.xml"


class RustBlogAdapter(RssBlogAdapter):
    """Fetches Rust Blog posts from the public RSS feed."""

    adapter_name = "rust_blog"
    default_feed_url = DEFAULT_FEED_URL
    source_tag = "rust"
    category_config_key = "tags"
    config_keys = [
        "feed_url",
        "release",
        "security",
        "keywords",
        "max_age_days",
        "timeout",
    ]
    description = "Fetches Rust Blog posts from the public RSS feed."

    @property
    def release_filter(self) -> bool | None:
        value = self._config.get("release")
        return bool(value) if value is not None else None

    @property
    def security_filter(self) -> bool | None:
        value = self._config.get("security")
        return bool(value) if value is not None else None

    def _matches_extra_filters(self, entry: dict) -> bool:
        text = f"{entry['title']} {entry['content']} {' '.join(entry['categories'])}".lower()
        if self.release_filter is True and "release" not in text:
            return False
        if self.release_filter is False and "release" in text:
            return False
        if self.security_filter is True and "security" not in text:
            return False
        if self.security_filter is False and "security" in text:
            return False
        return True

    def _metadata(self, entry: dict) -> dict:
        metadata = super()._metadata(entry)
        metadata["is_release"] = "release" in f"{entry['title']} {' '.join(entry['categories'])}".lower()
        metadata["is_security"] = "security" in f"{entry['title']} {' '.join(entry['categories'])}".lower()
        return metadata

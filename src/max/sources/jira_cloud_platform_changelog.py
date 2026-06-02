"""Jira Cloud Platform Changelog RSS source adapter."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.sources.docker_blog import RssBlogAdapter
from max.types.signal import Signal, SignalSourceType

DEFAULT_FEED_URL = "https://developer.atlassian.com/cloud/jira/platform/changelog/rss/"
DEFAULT_JIRA_CHANGELOG_URL = "https://developer.atlassian.com/cloud/jira/platform/changelog/"


class JiraCloudPlatformChangelogAdapter(RssBlogAdapter):
    """Fetches Jira Cloud Platform changelog entries from the public RSS feed."""

    adapter_name = "jira_cloud_platform_changelog"
    default_feed_url = DEFAULT_FEED_URL
    source_tag = "jira"
    category_config_key = "products"
    config_keys = ["feed_url", "products", "keywords", "max_age_days", "timeout"]
    description = "Fetches Jira Cloud Platform changelog entries from the public RSS feed."

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        entries = _configured_entries(self._config.get("entries"))
        if entries:
            return [_signal(entry) for entry in entries[: max(0, limit)]]
        return await super().fetch(limit=limit)


def _signal(entry: Mapping[str, Any]) -> Signal:
    title = _text(entry.get("title")) or "Jira Cloud Platform changelog update"
    url = _text(entry.get("url") or entry.get("link")) or DEFAULT_JIRA_CHANGELOG_URL
    product_area = _text(entry.get("product_area") or entry.get("area") or entry.get("category")) or "platform"
    published_at = _parse_datetime(entry.get("published_at") or entry.get("date"))
    summary = _text(entry.get("content") or entry.get("summary") or entry.get("description")) or title
    deprecation = _is_deprecation(entry)
    tags = ["jira_cloud_platform", product_area]
    if deprecation:
        tags.append("deprecation")
    return Signal(
        source_type=SignalSourceType.ARTICLE,
        source_adapter="jira_cloud_platform_changelog",
        title=title,
        content=summary,
        url=url,
        published_at=published_at,
        tags=tags,
        metadata={
            "product_area": product_area,
            "deprecation": deprecation,
            "source": "jira_cloud_platform_changelog",
        },
    )


def _configured_entries(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _is_deprecation(entry: Mapping[str, Any]) -> bool:
    if isinstance(entry.get("deprecation"), bool):
        return bool(entry["deprecation"])
    if isinstance(entry.get("deprecated"), bool):
        return bool(entry["deprecated"])
    text = f"{entry.get('title', '')} {entry.get('content', '')} {entry.get('summary', '')}".lower()
    return "deprecat" in text or "sunset" in text


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

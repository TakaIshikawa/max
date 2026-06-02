"""Stripe Changelog RSS source adapter."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.sources.docker_blog import RssBlogAdapter
from max.types.signal import Signal, SignalSourceType

DEFAULT_FEED_URL = "https://stripe.com/changelog.atom"
DEFAULT_STRIPE_CHANGELOG_URL = "https://docs.stripe.com/changelog"


class StripeChangelogAdapter(RssBlogAdapter):
    """Fetches Stripe changelog entries from the public feed."""

    adapter_name = "stripe_changelog"
    default_feed_url = DEFAULT_FEED_URL
    source_tag = "stripe"
    category_config_key = "products"
    config_keys = ["feed_url", "products", "keywords", "max_age_days", "timeout"]
    description = "Fetches Stripe changelog entries from the public feed."

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        entries = _configured_entries(self._config.get("entries"))
        if entries:
            return [_signal(entry) for entry in entries[: max(0, limit)]]
        return await super().fetch(limit=limit)


def _signal(entry: Mapping[str, Any]) -> Signal:
    title = _text(entry.get("title")) or "Stripe changelog update"
    url = _text(entry.get("url") or entry.get("link")) or DEFAULT_STRIPE_CHANGELOG_URL
    category = _text(entry.get("category") or entry.get("product") or entry.get("area")) or "changelog"
    published_at = _parse_datetime(entry.get("published_at") or entry.get("date"))
    summary = _text(entry.get("content") or entry.get("summary") or entry.get("description")) or title
    return Signal(
        source_type=SignalSourceType.ARTICLE,
        source_adapter="stripe_changelog",
        title=title,
        content=summary,
        url=url,
        published_at=published_at,
        tags=["stripe", category],
        metadata={"category": category, "source": "stripe_changelog"},
    )


def _configured_entries(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


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

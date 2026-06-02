"""Stripe changelog source adapter."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

DEFAULT_STRIPE_CHANGELOG_URL = "https://docs.stripe.com/changelog"


class StripeChangelogAdapter(SourceAdapter):
    """Fetch Stripe product and API changelog entries."""

    @property
    def name(self) -> str:
        return "stripe_changelog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ARTICLE.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        entries = _configured_entries(self._config.get("entries"))
        if not entries:
            entries = await self._fetch_live_entries()
        return [_signal(entry) for entry in entries[: max(0, limit)]]

    async def _fetch_live_entries(self) -> list[Mapping[str, Any]]:
        url = _text(self._config.get("feed_url") or self._config.get("changelog_url"))
        if not url:
            return []
        async with httpx.AsyncClient(timeout=float(self._config.get("timeout") or 30)) as client:
            response = await fetch_with_retry(url, client, adapter_name=self.name)
        return _entries_from_payload(response.text, url)


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


def _entries_from_payload(text: str, url: str) -> list[Mapping[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return []
    return [{"title": "Stripe changelog update", "url": url, "content": stripped[:500]}]


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

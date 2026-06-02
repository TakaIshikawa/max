"""Sentry changelog source adapter."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from max.sources.base import SourceAdapter
from max.sources.twilio_changelog import _entries_from_config_or_feed
from max.types.signal import Signal, SignalSourceType

DEFAULT_FEED_URL = "https://sentry.io/changelog/feed.xml"


class SentryChangelogAdapter(SourceAdapter):
    config_keys = ["entries", "feed_url", "timeout"]
    required_keys: list[str] = []
    description = "Converts Sentry changelog entries into observability product signals."

    @property
    def name(self) -> str:
        return "sentry_changelog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        entries = await _entries_from_config_or_feed(
            {**self._config, "feed_url": self._config.get("feed_url") or DEFAULT_FEED_URL},
            self.name,
        )
        return parse_sentry_changelog(entries, limit=limit)


def parse_sentry_changelog(value: Any, *, limit: int | None = None) -> list[Signal]:
    signals: list[Signal] = []
    seen: set[str] = set()
    for entry in _entries(value):
        title = _text(entry.get("title") or entry.get("name"))
        url = _text(entry.get("url") or entry.get("link"))
        if not title or not url or url in seen:
            continue
        seen.add(url)
        platform = _text(entry.get("platform"))
        product = _text(entry.get("product") or entry.get("category"))
        tags = _dedupe(["sentry", "observability", "error-monitoring", platform, product, *_strings(entry.get("tags"))])
        signals.append(Signal(
            id=f"sentry_changelog:{hashlib.sha1(url.encode()).hexdigest()[:12]}",
            source_type=SignalSourceType.ROADMAP,
            source_adapter="sentry_changelog",
            title=title,
            content=_text(entry.get("content") or entry.get("summary") or entry.get("description"))[:1000],
            url=url,
            published_at=_datetime(entry.get("published_at") or entry.get("date")),
            tags=tags,
            metadata={"platform": platform, "product": product, "tags": _strings(entry.get("tags"))},
        ))
        if limit is not None and len(signals) >= max(0, limit):
            break
    return signals


def _entries(value: Any) -> list[dict[str, Any]]:
    payload = value.get("entries") or value.get("items") or value.get("data") if isinstance(value, dict) else value
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    return [_text(item) for item in value if _text(item)] if isinstance(value, list) else []


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        clean = _text(value)
        if clean and clean not in result:
            result.append(clean)
    return result


def _datetime(value: Any) -> datetime | None:
    clean = _text(value)
    if not clean:
        return None
    try:
        parsed = datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

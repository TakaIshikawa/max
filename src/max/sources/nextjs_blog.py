"""Next.js Blog source adapter."""

from __future__ import annotations

import re
from typing import Any

from max.sources.twilio_changelog import _entries_from_config_or_feed
from max.sources.cloudflare_blog import _canonical_url, _dt, _id, _text
from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

DEFAULT_FEED_URL = "https://nextjs.org/atom"


class NextjsBlogAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "nextjs_blog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.NEWS.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if self._config.get("entries") is not None or self._config.get("payload") is not None:
            entries = self._config.get("entries") or self._config.get("payload") or []
        else:
            entries = await _entries_from_config_or_feed(
                {**self._config, "feed_url": self._config.get("feed_url") or DEFAULT_FEED_URL},
                self.name,
            )
        return parse_nextjs_blog(entries, limit=limit)


def parse_nextjs_blog(payload: Any, *, limit: int | None = None) -> list[Signal]:
    entries = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return []
    signals: list[Signal] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        title = _text(entry.get("title") or entry.get("name"))
        url = _canonical_url(entry.get("url") or entry.get("link") or entry.get("href"))
        if not title or not url or url in seen:
            continue
        seen.add(url)
        version = _version(title) or _text(entry.get("version"))
        area = _area(title, entry)
        tags = [value for value in ["nextjs", area] if value]
        metadata = {"source_name": "Next.js Blog", "framework": "Next.js"}
        if version:
            metadata["version"] = version
        if area:
            metadata["area"] = area
        signals.append(Signal(id=_id("nextjs_blog", url), source_type=SignalSourceType.NEWS, source_adapter="nextjs_blog", title=title, content=(_text(entry.get("summary") or entry.get("description") or entry.get("content")) or title)[:1000], url=url, author=_text(entry.get("author")) or None, published_at=_dt(entry.get("published_at") or entry.get("date")), tags=tags, metadata=metadata))
        if limit is not None and len(signals) >= limit:
            break
    return signals


def _version(title: str) -> str:
    match = re.search(r"\bNext\.?js\s+(\d+(?:\.\d+){0,2})\b|\bv(\d+(?:\.\d+){0,2})\b", title, re.I)
    return next((group for group in match.groups() if group), "") if match else ""


def _area(title: str, entry: dict[str, Any]) -> str:
    text = f"{title} {_text(entry.get('category'))} {_text(entry.get('tags'))}".lower()
    for area in ("app router", "turbopack", "compiler", "server actions", "middleware", "image"):
        if area in text:
            return area
    return ""

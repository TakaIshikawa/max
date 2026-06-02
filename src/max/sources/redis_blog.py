"""Redis Blog source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.cloudflare_blog import _canonical_url, _dt, _id, _text
from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

TOPICS = ("cache", "vector", "search", "streams", "cloud")


class RedisBlogAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "redis_blog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.NEWS.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_redis_blog(self._config.get("entries") or self._config.get("payload") or [], limit=limit)


def parse_redis_blog(payload: Any, *, limit: int | None = None) -> list[Signal]:
    entries = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return []
    signals: list[Signal] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        title = _text(entry.get("title"))
        url = _canonical_url(entry.get("url") or entry.get("link"))
        if not title or not url or url in seen:
            continue
        seen.add(url)
        categories = _list(entry.get("categories") or entry.get("tags") or entry.get("category"))
        topics = _topics(title, categories)
        signals.append(Signal(id=_id("redis_blog", url), source_type=SignalSourceType.NEWS, source_adapter="redis_blog", title=title, content=(_text(entry.get("summary") or entry.get("content") or entry.get("description")) or title)[:1000], url=url, author=_text(entry.get("author")) or None, published_at=_dt(entry.get("published_at") or entry.get("date")), tags=["redis", *categories], metadata={"source_name": "Redis Blog", "categories": categories, "topics": topics}))
        if limit is not None and len(signals) >= limit:
            break
    return signals


def _topics(title: str, categories: list[str]) -> list[str]:
    text = f"{title} {' '.join(categories)}".lower()
    return [topic for topic in TOPICS if topic in text]


def _list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    return [_text(item) for item in value if _text(item)] if isinstance(value, list) else []

"""MongoDB changelog source adapter."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class MongoDBChangelogAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "mongodb_changelog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_mongodb_changelog(self._config.get("entries") or self._config.get("payload") or [])[:limit]


def parse_mongodb_changelog(payload: Any) -> list[Signal]:
    entries = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return []
    signals = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        title = _text(entry.get("title") or entry.get("name"))
        published_at = _dt(entry.get("published_at") or entry.get("date"))
        version = _text(entry.get("version"))
        product = _text(entry.get("product") or entry.get("project"))
        if not title or (not _text(entry.get("url") or entry.get("link")) and not (published_at or version)):
            continue
        url = _text(entry.get("url") or entry.get("link")) or f"mongodb_changelog://{_id_key(title, published_at, version)}"
        metadata = {"source_name": "MongoDB"}
        if product:
            metadata["product"] = product
        if version:
            metadata["version"] = version
        signals.append(Signal(id=f"mongodb_changelog:{_id_key(url, published_at, version or title)}", source_type=SignalSourceType.ROADMAP, source_adapter="mongodb_changelog", title=title, content=_text(entry.get("summary") or entry.get("description") or entry.get("content"))[:1000], url=url, published_at=published_at, tags=[product] if product else [], metadata=metadata))
    signals.sort(key=lambda signal: (signal.published_at or datetime.min.replace(tzinfo=timezone.utc), signal.title), reverse=True)
    return signals


def _id_key(*parts: Any) -> str:
    return hashlib.sha1("|".join(_text(part) for part in parts).encode()).hexdigest()[:12]


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return " ".join(str(value).split()) if value is not None else ""

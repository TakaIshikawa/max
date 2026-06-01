"""Fly.io changelog source adapter."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class FlyIoChangelogAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "fly_io_changelog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_fly_io_changelog(self._config.get("entries") or self._config.get("payload") or [])[:limit]


def parse_fly_io_changelog(payload: Any) -> list[Signal]:
    return _parse(payload, "fly_io_changelog", "Fly.io", ("platform", "category"))


def _parse(payload: Any, adapter: str, source_name: str, metadata_keys: tuple[str, ...]) -> list[Signal]:
    entries = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return []
    signals: list[Signal] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        title = _text(entry.get("title") or entry.get("name"))
        url = _text(entry.get("url") or entry.get("link"))
        if not title or not url:
            continue
        metadata = {"source_name": source_name, **{key: entry.get(key) for key in metadata_keys if entry.get(key) not in (None, "")}}
        signal = Signal(id=_id(adapter, url, title), source_type=SignalSourceType.ROADMAP, source_adapter=adapter, title=title, content=_text(entry.get("summary") or entry.get("content") or entry.get("description"))[:1000], url=url, published_at=_dt(entry.get("published_at") or entry.get("date")), tags=[_text(entry.get("category"))] if _text(entry.get("category")) else [], metadata=metadata)
        signals.append(signal)
    return signals


def _id(adapter: str, url: str, title: str) -> str:
    return f"{adapter}:{hashlib.sha1(f'{url}|{title}'.encode()).hexdigest()[:12]}"


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None

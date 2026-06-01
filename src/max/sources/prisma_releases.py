"""Prisma releases source adapter."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class PrismaReleasesAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "prisma_releases"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_prisma_releases(self._config.get("entries") or self._config.get("payload") or [])[:limit]


def parse_prisma_releases(payload: Any) -> list[Signal]:
    return _parse(payload, "prisma_releases", "Prisma", ("version", "channel", "affected_package", "package"))


def _parse(payload: Any, adapter: str, source_name: str, metadata_keys: tuple[str, ...]) -> list[Signal]:
    entries = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return []
    signals = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        title = _text(entry.get("title") or entry.get("name") or entry.get("version"))
        url = _text(entry.get("url") or entry.get("link") or entry.get("html_url"))
        if not title or not url:
            continue
        version = _text(entry.get("version")) or _version(title)
        metadata = {"source_name": source_name}
        for key in metadata_keys:
            value = version if key == "version" and version else entry.get(key)
            if value not in (None, ""):
                metadata[key] = value
        signals.append(_signal(adapter, title, url, entry, metadata))
    signals.sort(key=lambda signal: (signal.published_at or datetime.min.replace(tzinfo=timezone.utc), signal.id), reverse=True)
    return signals


def _signal(adapter: str, title: str, url: str, entry: dict[str, Any], metadata: dict[str, Any]) -> Signal:
    return Signal(id=_id(adapter, _text(metadata.get("version")) or url, title), source_type=SignalSourceType.ROADMAP, source_adapter=adapter, title=title, content=_text(entry.get("summary") or entry.get("body") or entry.get("content") or entry.get("description"))[:1000], url=url, published_at=_dt(entry.get("published_at") or entry.get("date") or entry.get("created_at")), tags=[_text(metadata.get("channel"))] if _text(metadata.get("channel")) else [], metadata=metadata)


def _id(adapter: str, key: str, title: str) -> str:
    return f"{adapter}:{hashlib.sha1(f'{key}|{title}'.encode()).hexdigest()[:12]}"


def _version(text: str) -> str:
    match = re.search(r"\bv?\d+\.\d+(?:\.\d+)?(?:[-\w.]*)?", text)
    return match.group(0).lstrip("v") if match else ""


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""

"""Grafana changelog source adapter."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class GrafanaChangelogAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "grafana_changelog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_grafana_changelog(self._config.get("entries") or self._config.get("payload") or [])[:limit]


def parse_grafana_changelog(payload: Any) -> list[Signal]:
    entries = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return []
    signals = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        title = _text(entry.get("title") or entry.get("name"))
        url = _text(entry.get("url") or entry.get("link"))
        if not title or not url:
            continue
        published_at = _dt(entry.get("published_at") or entry.get("date"))
        product = _text(entry.get("product") or entry.get("project"))
        version = _text(entry.get("version"))
        metadata = {"source_name": "Grafana"}
        if product:
            metadata["product"] = product
        if version:
            metadata["version"] = version
        signals.append(Signal(id=f"grafana_changelog:{_hash(url, title)}", source_type=SignalSourceType.ROADMAP, source_adapter="grafana_changelog", title=title, content=_text(entry.get("summary") or entry.get("description") or entry.get("content"))[:1000], url=url, published_at=published_at, tags=[product] if product else [], metadata=metadata))
    signals.sort(key=lambda signal: (signal.published_at or datetime.min.replace(tzinfo=timezone.utc), signal.title, signal.id), reverse=True)
    return signals


def _hash(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


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

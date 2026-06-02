"""OpenAI status incidents source adapter."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from max.sources.base import SourceAdapter
from max.sources.twilio_changelog import _entries_from_config_or_feed
from max.types.signal import Signal, SignalSourceType

DEFAULT_FEED_URL = "https://status.openai.com/history.rss"


class OpenAIStatusIncidentsAdapter(SourceAdapter):
    config_keys = ["entries", "feed_url", "status_url", "timeout"]
    required_keys: list[str] = []
    description = "Converts OpenAI status incident rows into reliability signals."

    @property
    def name(self) -> str:
        return "openai_status_incidents"

    @property
    def source_type(self) -> str:
        return SignalSourceType.NEWS.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        entries = await _entries_from_config_or_feed(
            {**self._config, "feed_url": self._config.get("feed_url") or self._config.get("status_url") or DEFAULT_FEED_URL},
            self.name,
        )
        return parse_openai_status_incidents(entries, limit=limit)


def parse_openai_status_incidents(value: Any, *, limit: int | None = None) -> list[Signal]:
    signals: list[Signal] = []
    seen: set[str] = set()
    for entry in _entries(value):
        title = _text(entry.get("title") or entry.get("name"))
        url = _text(entry.get("url") or entry.get("link") or entry.get("shortlink"))
        if not title or not url or url in seen:
            continue
        seen.add(url)
        status = _normalize_status(entry.get("status") or entry.get("incident_status"))
        components = _strings(entry.get("components"))
        started_at = _datetime(entry.get("started_at") or entry.get("created_at") or entry.get("date"))
        resolved_at = _datetime(entry.get("resolved_at"))
        signals.append(Signal(
            id=f"openai_status_incidents:{hashlib.sha1(url.encode()).hexdigest()[:12]}",
            source_type=SignalSourceType.NEWS,
            source_adapter="openai_status_incidents",
            title=title,
            content=_text(entry.get("content") or entry.get("summary") or entry.get("description") or status)[:1000],
            url=url,
            published_at=started_at,
            tags=_dedupe(["openai", "status", "incident", status, *components]),
            metadata={"status": status, "components": components, "started_at": _iso(started_at), "resolved_at": _iso(resolved_at)},
        ))
        if limit is not None and len(signals) >= max(0, limit):
            break
    return signals


def _normalize_status(value: Any) -> str:
    status = _text(value).casefold().replace(" ", "_").replace("-", "_")
    return status or "unknown"


def _entries(value: Any) -> list[dict[str, Any]]:
    payload = value.get("incidents") or value.get("entries") or value.get("items") or value.get("data") if isinstance(value, dict) else value
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


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

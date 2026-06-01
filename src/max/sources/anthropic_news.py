"""Anthropic news source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

DEFAULT_URL = "https://www.anthropic.com/news"


class AnthropicNewsAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "anthropic_news"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ARTICLE.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        entries = self._config.get("entries")
        if entries is None:
            async with httpx.AsyncClient(timeout=float(self._config.get("timeout", 30))) as client:
                response = await fetch_with_retry(str(self._config.get("url") or DEFAULT_URL), client, adapter_name=self.name)
                entries = response.json()
        signals: list[Signal] = []
        for entry in _entries(entries):
            signal = _entry_to_signal(entry, self.name)
            if signal is not None:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals


def _entries(payload: Any) -> list[dict[str, Any]]:
    value = payload.get("data") or payload.get("entries") or payload.get("items") if isinstance(payload, dict) else payload
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _entry_to_signal(entry: dict[str, Any], adapter_name: str) -> Signal | None:
    title = _text(entry.get("title") or entry.get("name"))
    url = _text(entry.get("url") or entry.get("canonical_url"))
    if not title or not url:
        return None
    category = _text(entry.get("category") or entry.get("type"))
    published = _parse_datetime(entry.get("published_at") or entry.get("date"))
    summary = _text(entry.get("summary") or entry.get("content") or title)
    return Signal(
        id="anthropic_news:" + url.rstrip("/").rsplit("/", 1)[-1],
        source_type=SignalSourceType.ARTICLE,
        source_adapter=adapter_name,
        title=title,
        content=summary[:1000],
        url=url,
        published_at=published,
        tags=[category] if category else [],
        credibility=0.7,
        metadata={"category": category, "canonical_url": url},
    )


def _parse_datetime(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""

"""Hacker News front page source adapter."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class HackerNewsFrontpageAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "hackernews_frontpage"

    @property
    def source_type(self) -> str:
        return SignalSourceType.TRENDING.value

    @property
    def api_url(self) -> str:
        return str(self._config.get("hn_api_url") or "https://hacker-news.firebaseio.com/v0").strip().rstrip("/")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        max_items = int(self._config.get("max_items") or limit)
        min_score = int(self._config.get("min_score") or 0)
        async with httpx.AsyncClient(timeout=30) as client:
            ids_response = await client.get(f"{self.api_url}/topstories.json")
            if ids_response.status_code >= 400:
                return []
            signals = []
            for item_id in ids_response.json()[:max_items]:
                item_response = await client.get(f"{self.api_url}/item/{item_id}.json")
                if item_response.status_code >= 400:
                    continue
                item = item_response.json() or {}
                if int(item.get("score") or 0) < min_score:
                    continue
                signals.append(_signal(item, bool(self._config.get("include_text"))))
                if len(signals) >= limit:
                    break
        return signals


def _signal(item: dict[str, Any], include_text: bool) -> Signal:
    item_id = item.get("id")
    hn_url = f"https://news.ycombinator.com/item?id={item_id}"
    content = str(item.get("text") or "")[:500] if include_text else ""
    return Signal(
        id=_id("hn-frontpage", item_id),
        source_type=SignalSourceType.TRENDING,
        source_adapter="hackernews_frontpage",
        title=str(item.get("title") or f"Hacker News item {item_id}"),
        content=content or f"{item.get('score', 0)} points and {item.get('descendants', 0)} comments on Hacker News.",
        url=str(item.get("url") or hn_url),
        author=item.get("by"),
        published_at=_dt(item.get("time")),
        tags=["hackernews", "frontpage"],
        credibility=min(max(float(item.get("score") or 0) / 500, 0.1), 1.0),
        metadata={
            "hn_id": item_id,
            "score": item.get("score") or 0,
            "descendants": item.get("descendants") or 0,
            "author": item.get("by") or "",
            "external_url": item.get("url") or "",
            "hn_url": hn_url,
            "text_snippet": str(item.get("text") or "")[:500],
            "signal_role": "market",
        },
    )


def _dt(value: Any) -> datetime:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return datetime.now(timezone.utc)


def _id(*parts: object) -> str:
    return hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()[:16]

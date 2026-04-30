"""Hacker News Show HN adapter — recent prototype and launch posts."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.sources.errors import SourceParseError
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

ALGOLIA_SEARCH_BY_DATE_API = "https://hn.algolia.com/api/v1/search_by_date"
_SHOW_HN_QUERY = "Show HN:"
_BASE_TAGS = ["show_hn", "product_launch", "prototype"]


class HackerNewsShowHNAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "hackernews_showhn"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def algolia_url(self) -> str:
        return str(self._config.get("algolia_url", ALGOLIA_SEARCH_BY_DATE_API)).rstrip("/")

    @property
    def query(self) -> str:
        return str(self._config.get("query", _SHOW_HN_QUERY))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []

        async with httpx.AsyncClient(timeout=30) as client:
            response = await fetch_with_retry(
                self.algolia_url,
                client,
                adapter_name=self.name,
                params={
                    "query": self.query,
                    "tags": "story",
                    "restrictSearchableAttributes": "title",
                    "hitsPerPage": limit,
                },
            )

        try:
            payload = response.json()
        except (ValueError, TypeError) as e:
            logger.warning("%s: failed to parse Algolia response", self.name, exc_info=True)
            raise SourceParseError(
                f"failed to parse Algolia response: {e}",
                adapter_name=self.name,
            ) from e

        hits = payload.get("hits", []) if isinstance(payload, dict) else []
        if not isinstance(hits, list):
            return []

        signals: list[Signal] = []
        for hit in hits:
            signal = _hit_to_signal(hit, adapter_name=self.name)
            if signal is None:
                continue
            signals.append(signal)
            if len(signals) >= limit:
                break

        return signals


def _hit_to_signal(hit: Any, *, adapter_name: str) -> Signal | None:
    if not isinstance(hit, dict):
        return None

    title = str(hit.get("title") or hit.get("story_title") or "").strip()
    if not title or not title.lower().startswith("show hn:"):
        return None

    raw_id = hit.get("objectID") or hit.get("story_id")
    try:
        hn_id = int(raw_id)
    except (TypeError, ValueError):
        logger.warning("%s: skipping Show HN hit without valid objectID", adapter_name)
        return None

    source_url = f"https://news.ycombinator.com/item?id={hn_id}"
    url = str(hit.get("url") or "").strip() or source_url
    score = _int_or_default(hit.get("points"), 0)
    comments = _int_or_default(hit.get("num_comments"), 0)
    published_at = _parse_published_at(hit)

    metadata = {
        "hn_id": hn_id,
        "score": score,
        "comments": comments,
        "source_url": source_url,
        "signal_role": "market",
        "source_kind": "show_hn",
    }

    return Signal(
        id=f"{adapter_name}:{hn_id}",
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter_name,
        title=title,
        content=title,
        url=url,
        author=hit.get("author"),
        published_at=published_at,
        tags=_build_tags(title),
        credibility=min(score / 500, 1.0),
        metadata=metadata,
    )


def _parse_published_at(hit: dict[str, Any]) -> datetime | None:
    created_at_i = hit.get("created_at_i")
    if isinstance(created_at_i, int):
        return datetime.fromtimestamp(created_at_i, tz=timezone.utc)

    created_at = hit.get("created_at")
    if not isinstance(created_at, str) or not created_at:
        return None
    try:
        return datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return None


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_tags(title: str) -> list[str]:
    tags = list(_BASE_TAGS)
    lower = title.lower()
    if any(term in lower for term in ("ai", "llm", "gpt", "claude")):
        tags.append("ai")
    if any(term in lower for term in ("developer", "devtool", "api", "sdk", "cli")):
        tags.append("devtools")
    if any(term in lower for term in ("open source", "github", "oss")):
        tags.append("open_source")
    return tags

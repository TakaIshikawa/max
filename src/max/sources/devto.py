"""Dev.to source adapter — practitioner experience signals via Forem API."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

DEVTO_API = "https://dev.to/api"

_DEFAULT_TAGS = ["ai", "llm", "mcp", "developer-tools", "python", "typescript"]


def _extract_tags(tag_list: list[str], title: str) -> list[str]:
    """Build signal tags from Dev.to article tags and title."""
    tags: set[str] = set()
    for t in tag_list[:8]:
        tags.add(t.lower())
    kw_map = {
        "agent": "agent", "llm": "llm", "mcp": "mcp",
        "openai": "openai", "langchain": "langchain",
        "rag": "rag", "embedding": "embedding",
        "claude": "claude", "anthropic": "anthropic",
    }
    title_lower = title.lower()
    for keyword, tag in kw_map.items():
        if keyword in title_lower:
            tags.add(tag)
    tags.add("devto")
    return sorted(tags)[:10]


def _parse_datetime(date_str: str | None) -> datetime | None:
    """Parse ISO 8601 datetime from Dev.to API."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


class DevtoAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "devto"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def tags(self) -> list[str]:
        return self._config.get("tags", _DEFAULT_TAGS)

    @property
    def period(self) -> int:
        """Top articles from last N days."""
        return self._config.get("period", 7)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_ids: set[int] = set()
        per_tag = max(limit // len(self.tags), 3) if self.tags else limit

        headers = {
            "User-Agent": "max-signal-fetcher/1.0",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for i, tag in enumerate(self.tags):
                if len(signals) >= limit:
                    break
                if i > 0:
                    await asyncio.sleep(1)  # rate-limit courtesy

                try:
                    resp = await fetch_with_retry(
                        f"{DEVTO_API}/articles",
                        client,
                        adapter_name=self.name,
                        params={
                            "tag": tag,
                            "top": self.period,
                            "per_page": min(per_tag, 30),
                        },
                    )
                    articles = resp.json()
                except Exception:
                    logger.warning("Dev.to fetch failed for tag: %s", tag, exc_info=True)
                    continue

                if not isinstance(articles, list):
                    continue

                for article in articles:
                    article_id = article.get("id")
                    if not article_id or article_id in seen_ids:
                        continue
                    seen_ids.add(article_id)

                    reactions = article.get("positive_reactions_count", 0)
                    tag_list = article.get("tag_list", [])
                    if isinstance(tag_list, str):
                        tag_list = [t.strip() for t in tag_list.split(",") if t.strip()]

                    signals.append(Signal(
                        source_type=SignalSourceType.FORUM,
                        source_adapter=self.name,
                        title=article.get("title", ""),
                        content=(article.get("description") or "")[:500],
                        url=article.get("url", ""),
                        author=(article.get("user") or {}).get("name"),
                        published_at=_parse_datetime(article.get("published_at")),
                        tags=_extract_tags(tag_list, article.get("title", "")),
                        credibility=min(reactions / 100, 1.0),
                        metadata={
                            "devto_id": article_id,
                            "reactions": reactions,
                            "comments": article.get("comments_count", 0),
                            "reading_time": article.get("reading_time_minutes"),
                            "tag_list": tag_list[:10],
                        },
                    ))

                    if len(signals) >= limit:
                        break

        return signals[:limit]

"""Postman changelog source adapter."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Iterable

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

TOPIC_TERMS = {
    "api_client": ("api client", "client", "request", "agent"),
    "collections": ("collection", "collections"),
    "mock_servers": ("mock", "mock server"),
    "monitoring": ("monitor", "monitoring"),
    "collaboration": ("collaboration", "workspace", "team", "comments", "share"),
}


class PostmanChangelogAdapter(SourceAdapter):
    """Converts supplied Postman changelog entries into signals."""

    config_keys = ["entries"]
    required_keys: list[str] = []
    description = "Converts mocked Postman changelog entries into Signals."

    @property
    def name(self) -> str:
        return "postman_changelog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_urls: set[str] = set()
        for entry in _entries(self._config.get("entries")):
            url = _text(entry.get("url") or entry.get("link"))
            title = _text(entry.get("title"))
            if not url or not title or url in seen_urls:
                continue
            seen_urls.add(url)
            tags = _tags(entry.get("tags"))
            topic = _workflow_topic(title, tags)
            signals.append(
                Signal(
                    id=f"postman_changelog:{hashlib.sha1(url.encode()).hexdigest()[:12]}",
                    source_type=SignalSourceType.ROADMAP,
                    source_adapter=self.name,
                    title=title,
                    content=_text(entry.get("content") or entry.get("summary") or entry.get("description"))[:1000],
                    url=url,
                    published_at=_datetime(entry.get("published_at") or entry.get("date")),
                    tags=["postman", *tags],
                    metadata={
                        "workflow_topic": topic,
                        "change_category": _text(entry.get("change_category") or entry.get("category") or entry.get("type")),
                    },
                )
            )
            if len(signals) >= max(0, limit):
                break
        return signals


def _entries(value: Any) -> Iterable[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _workflow_topic(title: str, tags: list[str]) -> str:
    haystack = f"{title} {' '.join(tags)}".casefold()
    for topic, terms in TOPIC_TERMS.items():
        if any(term in haystack for term in terms):
            return topic
    return "collaboration"


def _tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        tag = _text(item)
        if tag and tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


def _datetime(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

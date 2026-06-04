"""Django Weblog source adapter."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class DjangoWeblogAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "django_weblog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ARTICLE.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        payload = self._config.get("entries") or self._config.get("payload") or []
        return parse_django_weblog(payload, limit=limit)


def parse_django_weblog(payload: Any, *, limit: int | None = None) -> list[Signal]:
    return parse_configured_entries(
        payload,
        adapter="django_weblog",
        source_name="Django Weblog",
        source_type=SignalSourceType.ARTICLE,
        metadata_keys=("category", "author", "tags"),
        default_tags=("django",),
        limit=limit,
    )


def parse_configured_entries(
    payload: Any,
    *,
    adapter: str,
    source_name: str,
    source_type: SignalSourceType,
    metadata_keys: tuple[str, ...],
    default_tags: tuple[str, ...] = (),
    limit: int | None = None,
) -> list[Signal]:
    signals: list[Signal] = []
    seen_urls: set[str] = set()
    for entry in _entries(payload):
        title = _text(entry.get("title") or entry.get("name") or entry.get("headline"))
        url = _canonical_url(
            entry.get("url") or entry.get("link") or entry.get("href") or entry.get("id")
        )
        if not title or not url or url in seen_urls:
            continue
        seen_urls.add(url)
        metadata = {"source_name": source_name}
        for key in metadata_keys:
            value = entry.get(key)
            if value not in (None, "", []):
                metadata[key] = value
        tags = _tags(default_tags, entry)
        signals.append(
            Signal(
                id=_id(adapter, url),
                source_type=source_type,
                source_adapter=adapter,
                title=title,
                content=(
                    _text(
                        entry.get("summary")
                        or entry.get("description")
                        or entry.get("content")
                        or entry.get("body")
                    )
                    or title
                )[:1000],
                url=url,
                author=_text(entry.get("author")) or None,
                published_at=_dt(
                    entry.get("published_at")
                    or entry.get("published")
                    or entry.get("date")
                    or entry.get("pubDate")
                ),
                tags=tags,
                metadata=metadata,
            )
        )
        if limit is not None and len(signals) >= limit:
            break
    return signals


def _entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        value = payload.get("entries") or payload.get("items") or payload.get("results") or []
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def _tags(default_tags: tuple[str, ...], entry: dict[str, Any]) -> list[str]:
    values: list[Any] = [*default_tags]
    for key in ("tags", "categories", "category", "topic", "product", "channel", "platform"):
        raw = entry.get(key)
        if isinstance(raw, list):
            values.extend(raw)
        elif raw:
            values.append(raw)
    seen: set[str] = set()
    tags: list[str] = []
    for value in values:
        tag = _text(value)
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def _canonical_url(value: Any) -> str:
    url = _text(value)
    if not url:
        return ""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/") or parts.path, "", ""))


def _id(adapter: str, url: str) -> str:
    return f"{adapter}:{hashlib.sha1(url.encode()).hexdigest()[:12]}"


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

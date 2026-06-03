"""GitLab Blog source adapter."""

from __future__ import annotations

from typing import Any

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.sources.cloudflare_blog import _canonical_url, _dt, _entries, _id, _text
from max.types.signal import Signal, SignalSourceType

DEFAULT_FEED_URL = "https://about.gitlab.com/atom.xml"


class GitLabBlogAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "gitlab_blog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.NEWS.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        payload = self._config.get("entries") or self._config.get("payload") or self._config.get("feed")
        if payload is None:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await fetch_with_retry(str(self._config.get("feed_url") or DEFAULT_FEED_URL), client, adapter_name=self.name)
                payload = response.text
        return parse_gitlab_blog(payload, limit=limit)


def parse_gitlab_blog(payload: Any, *, limit: int | None = None) -> list[Signal]:
    signals: list[Signal] = []
    seen_urls: set[str] = set()
    for entry in _entries(payload):
        title = _text(entry.get("title") or entry.get("name"))
        url = _canonical_url(entry.get("url") or entry.get("link") or entry.get("guid") or entry.get("id"))
        if not title or not url or url in seen_urls:
            continue
        seen_urls.add(url)
        categories = _tags(entry)
        summary = _text(entry.get("summary") or entry.get("description") or entry.get("content") or entry.get("body")) or title
        author = _text(entry.get("author") or entry.get("creator"))
        signals.append(
            Signal(
                id=_id("gitlab_blog", url),
                source_type=SignalSourceType.NEWS,
                source_adapter="gitlab_blog",
                title=title,
                content=summary[:1000],
                url=url,
                author=author or None,
                published_at=_dt(entry.get("published_at") or entry.get("published") or entry.get("date") or entry.get("pubDate") or entry.get("updated")),
                tags=["gitlab", *categories],
                metadata={"source_name": "GitLab Blog", "author": author or None, "categories": categories},
            )
        )
        if limit is not None and len(signals) >= limit:
            break
    return signals


def _tags(entry: dict[str, Any]) -> list[str]:
    values = entry.get("tags") or entry.get("categories") or entry.get("category") or []
    if isinstance(values, str):
        values = [values]
    seen: set[str] = set()
    tags: list[str] = []
    for value in values if isinstance(values, list) else []:
        tag = _text(value)
        if tag and tag.lower() != "gitlab" and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags

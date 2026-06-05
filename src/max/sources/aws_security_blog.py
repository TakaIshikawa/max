"""AWS Security Blog source adapter."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.sources.cloudflare_blog import _canonical_url, _dt, _entries, _id, _text
from max.sources.gitlab_blog import _tags
from max.types.signal import Signal, SignalSourceType

DEFAULT_FEED_URL = "https://aws.amazon.com/blogs/security/feed/"


class AwsSecurityBlogAdapter(SourceAdapter):
    config_keys = ["entries", "payload", "feed_url", "keywords", "max_age_days", "timeout"]
    required_keys: list[str] = []
    description = "Ingests AWS Security Blog posts as cloud security and compliance signals."

    @property
    def name(self) -> str:
        return "aws_security_blog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SECURITY.value

    @property
    def timeout(self) -> float:
        return float(self._config.get("timeout", 30))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        payload = self._config.get("entries") or self._config.get("payload") or self._config.get("feed")
        feed_url = str(self._config.get("feed_url") or DEFAULT_FEED_URL)
        if payload is None:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await fetch_with_retry(feed_url, client, adapter_name=self.name)
                payload = response.text
        return parse_aws_security_blog(
            payload,
            limit=limit,
            feed_url=feed_url,
            keywords=[str(value) for value in self._config.get("keywords", [])],
            max_age_days=self._config.get("max_age_days"),
        )


def parse_aws_security_blog(
    payload: Any,
    *,
    limit: int | None = None,
    feed_url: str = DEFAULT_FEED_URL,
    keywords: list[str] | None = None,
    max_age_days: int | str | None = None,
) -> list[Signal]:
    signals: list[Signal] = []
    seen_urls: set[str] = set()
    cutoff = _cutoff(max_age_days)
    terms = keywords or []

    for entry in _entries(payload):
        title = _text(entry.get("title") or entry.get("name"))
        url = _canonical_url(entry.get("url") or entry.get("link") or entry.get("guid") or entry.get("id"))
        if not title or not url or url in seen_urls:
            continue

        summary = _text(entry.get("summary") or entry.get("description") or entry.get("content") or entry.get("body")) or title
        if terms and not _matches_any(f"{title} {summary}", terms):
            continue

        published_at = _dt(entry.get("published_at") or entry.get("published") or entry.get("date") or entry.get("pubDate") or entry.get("updated"))
        if cutoff is not None and published_at is not None and published_at < cutoff:
            continue

        seen_urls.add(url)
        categories = _tags(entry)
        signals.append(
            Signal(
                id=_id("aws_security_blog", url),
                source_type=SignalSourceType.SECURITY,
                source_adapter="aws_security_blog",
                title=title,
                content=summary[:1000],
                url=url,
                author=_text(entry.get("author")) or None,
                published_at=published_at,
                tags=_dedupe(["aws", "security", "cloud-security", *categories]),
                metadata={
                    "source_name": "AWS Security Blog",
                    "canonical_url": url,
                    "feed_url": feed_url,
                    "categories": categories,
                },
            )
        )
        if limit is not None and len(signals) >= limit:
            break
    return signals


def _matches_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _cutoff(max_age_days: int | str | None) -> datetime | None:
    if max_age_days is None:
        return None
    try:
        days = int(max_age_days)
    except (TypeError, ValueError):
        return None
    return datetime.now(timezone.utc) - timedelta(days=days)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        tag = _text(value)
        key = tag.lower()
        if tag and key not in seen:
            seen.add(key)
            result.append(tag)
    return result

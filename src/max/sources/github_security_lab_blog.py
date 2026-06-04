"""GitHub Security Lab Blog source adapter."""

from __future__ import annotations

from typing import Any

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.sources.cloudflare_blog import _canonical_url, _dt, _entries, _id, _text
from max.sources.gitlab_blog import _tags
from max.types.signal import Signal, SignalSourceType

DEFAULT_FEED_URL = "https://github.blog/security-lab/feed/"


class GitHubSecurityLabBlogAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "github_security_lab_blog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SECURITY.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        payload = self._config.get("entries") or self._config.get("payload") or self._config.get("feed")
        if payload is None:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await fetch_with_retry(
                    str(self._config.get("feed_url") or DEFAULT_FEED_URL),
                    client,
                    adapter_name=self.name,
                )
                payload = response.text
        return parse_github_security_lab_blog(payload, limit=limit)


def parse_github_security_lab_blog(
    payload: Any, *, limit: int | None = None
) -> list[Signal]:
    signals: list[Signal] = []
    seen_urls: set[str] = set()
    for entry in _entries(payload):
        title = _text(entry.get("title") or entry.get("name"))
        url = _canonical_url(
            entry.get("url") or entry.get("link") or entry.get("guid") or entry.get("id")
        )
        if not title or not url or url in seen_urls:
            continue
        seen_urls.add(url)
        cve_ids = _cve_ids(entry.get("cve_ids") or entry.get("cves") or entry.get("cve"))
        categories = _tags(entry)
        tags = _dedupe(["github", "security-lab", *categories, *cve_ids])
        summary = _text(
            entry.get("summary")
            or entry.get("description")
            or entry.get("content")
            or entry.get("body")
        ) or title
        source_type = (
            SignalSourceType.SECURITY
            if cve_ids or _security_tagged(categories, title, summary)
            else SignalSourceType.ARTICLE
        )
        signals.append(
            Signal(
                id=_id("github_security_lab_blog", url),
                source_type=source_type,
                source_adapter="github_security_lab_blog",
                title=title,
                content=summary[:1000],
                url=url,
                published_at=_dt(
                    entry.get("published_at")
                    or entry.get("published")
                    or entry.get("date")
                    or entry.get("pubDate")
                    or entry.get("updated")
                ),
                tags=tags,
                metadata={
                    "source_name": "GitHub Security Lab Blog",
                    "canonical_url": url,
                    "cve_ids": cve_ids,
                    "categories": categories,
                },
            )
        )
        if limit is not None and len(signals) >= limit:
            break
    return signals


def _cve_ids(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    seen: set[str] = set()
    cves: list[str] = []
    for item in values:
        cve = _text(item).upper()
        if cve and cve.startswith("CVE-") and cve not in seen:
            seen.add(cve)
            cves.append(cve)
    return cves


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


def _security_tagged(categories: list[str], title: str, summary: str) -> bool:
    text = " ".join([title, summary, *categories]).lower()
    return any(term in text for term in ("security", "vulnerability", "exploit", "cve"))

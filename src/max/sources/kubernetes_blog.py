"""Kubernetes Blog RSS source adapter."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

DEFAULT_FEED_URL = "https://kubernetes.io/feed.xml"
_CONTENT_NS = "{http://purl.org/rss/1.0/modules/content/}"


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


def _child_text(element: ET.Element, tag: str) -> str:
    child = element.find(tag)
    return _normalize_text(child.text) if child is not None else ""


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value.strip())
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError, OverflowError):
        logger.debug("Failed to parse Kubernetes Blog datetime: %s", value, exc_info=True)
        return None


def _categories(item: ET.Element) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for child in item.findall("category"):
        tag = _normalize_text(child.text)
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def _parse_items(xml_text: str, feed_url: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("Failed to parse Kubernetes Blog feed: %s", feed_url)
        return []

    channel = root.find("channel")
    items = channel.findall("item") if channel is not None else root.findall("item")
    entries: list[dict] = []
    for item in items:
        title = _child_text(item, "title")
        url = _child_text(item, "link")
        guid = _child_text(item, "guid")
        if not title or not (url or guid):
            continue
        content = _child_text(item, "description") or _child_text(item, f"{_CONTENT_NS}encoded")
        entries.append({
            "title": title,
            "content": content,
            "url": url or guid,
            "published_at": _parse_datetime(_child_text(item, "pubDate")),
            "tags": _categories(item),
            "guid": guid,
        })
    return entries


def _contains_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return not terms or any(term.lower() in lowered for term in terms)


class KubernetesBlogAdapter(SourceAdapter):
    """Fetches Kubernetes Blog posts from the public RSS feed."""

    config_keys = ["feed_url", "tags", "keywords", "max_age_days", "timeout"]
    required_keys: list[str] = []
    description = "Fetches Kubernetes Blog posts from the public RSS feed."

    @property
    def name(self) -> str:
        return "kubernetes_blog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.NEWS.value

    @property
    def feed_url(self) -> str:
        return str(self._config.get("feed_url") or DEFAULT_FEED_URL)

    @property
    def tags(self) -> list[str]:
        return [str(value) for value in self._config.get("tags", [])]

    @property
    def keywords(self) -> list[str]:
        return [str(value) for value in self._config.get("keywords", [])]

    @property
    def max_age_days(self) -> int | None:
        value = self._config.get("max_age_days")
        return int(value) if value is not None else None

    @property
    def timeout(self) -> float:
        return float(self._config.get("timeout", 30))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        headers = {
            "User-Agent": "max-signal-fetcher/1.0",
            "Accept": "application/rss+xml, application/xml, text/xml",
        }
        async with httpx.AsyncClient(timeout=self.timeout, headers=headers, follow_redirects=True) as client:
            try:
                response = await fetch_with_retry(self.feed_url, client, adapter_name=self.name)
            except Exception:
                logger.warning("Kubernetes Blog feed fetch failed: %s", self.feed_url, exc_info=True)
                return []

        cutoff = None
        if self.max_age_days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.max_age_days)

        signals: list[Signal] = []
        seen_keys: set[str] = set()
        for entry in _parse_items(response.text, self.feed_url):
            published_at = entry["published_at"]
            if cutoff is not None and published_at is not None and published_at < cutoff:
                continue
            tags = entry["tags"]
            if self.tags and not any(wanted.lower() == tag.lower() for wanted in self.tags for tag in tags):
                continue
            if not _contains_any(f"{entry['title']} {entry['content']}", self.keywords):
                continue
            dedupe_key = entry["guid"] or entry["url"]
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)

            signals.append(
                Signal(
                    source_type=SignalSourceType.NEWS,
                    source_adapter=self.name,
                    title=entry["title"],
                    content=entry["content"][:1000],
                    url=entry["url"],
                    published_at=published_at,
                    tags=["kubernetes", *tags],
                    metadata={"feed_url": self.feed_url, "tags": tags, "guid": entry["guid"]},
                )
            )
            if len(signals) >= limit:
                break
        return signals

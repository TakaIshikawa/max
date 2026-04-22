"""RSS/Atom source adapter for configured article feeds."""

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

_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_CONTENT_NS = "{http://purl.org/rss/1.0/modules/content/}"


def _normalize_text(text: str | None) -> str:
    """Collapse markup and whitespace in feed text fields."""
    if not text:
        return ""
    without_tags = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


def _child_text(element: ET.Element, tag: str) -> str:
    child = element.find(tag)
    return _normalize_text(child.text) if child is not None else ""


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse common RSS and Atom datetime formats."""
    if not value:
        return None

    date_str = value.strip()
    if not date_str:
        return None

    try:
        parsed = parsedate_to_datetime(date_str)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError, OverflowError):
        pass

    try:
        parsed = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        logger.debug("Failed to parse RSS/Atom datetime: %s", value, exc_info=True)
        return None


def _atom_link(entry: ET.Element) -> str:
    fallback = ""
    for link in entry.findall(f"{_ATOM_NS}link"):
        href = (link.get("href") or "").strip()
        if not href:
            continue
        rel = link.get("rel", "alternate")
        if rel == "alternate":
            return href
        if not fallback:
            fallback = href
    return fallback


def _parse_rss_entries(xml_text: str, feed_url: str = "") -> list[dict]:
    """Parse RSS/Atom XML into normalized entry dictionaries."""
    entries: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("Failed to parse RSS/Atom feed: %s", feed_url or "(unknown)")
        return entries

    if root.tag == f"{_ATOM_NS}feed":
        for entry in root.findall(f"{_ATOM_NS}entry"):
            title = _child_text(entry, f"{_ATOM_NS}title")
            url = _atom_link(entry) or _child_text(entry, f"{_ATOM_NS}id")
            if not title or not url:
                continue

            summary = _child_text(entry, f"{_ATOM_NS}summary")
            if not summary:
                summary = _child_text(entry, f"{_ATOM_NS}content")
            published = (
                _child_text(entry, f"{_ATOM_NS}published")
                or _child_text(entry, f"{_ATOM_NS}updated")
            )

            entries.append({
                "title": title,
                "content": summary,
                "url": url,
                "published_at": _parse_datetime(published),
            })
        return entries

    channel = root.find("channel")
    items = channel.findall("item") if channel is not None else root.findall("item")
    for item in items:
        title = _child_text(item, "title")
        url = _child_text(item, "link") or _child_text(item, "guid")
        if not title or not url:
            continue

        content = _child_text(item, "description")
        if not content:
            content = _child_text(item, f"{_CONTENT_NS}encoded")

        entries.append({
            "title": title,
            "content": content,
            "url": url,
            "published_at": _parse_datetime(_child_text(item, "pubDate")),
        })

    return entries


class RssFeedAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "rss_feed"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ARTICLE.value

    @property
    def feeds(self) -> list[str]:
        return list(self._config.get("feeds", []))

    @property
    def tags(self) -> list[str]:
        return list(self._config.get("tags", []))

    @property
    def max_age_days(self) -> int | None:
        value = self._config.get("max_age_days")
        return int(value) if value is not None else None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_urls: set[str] = set()
        cutoff = None
        if self.max_age_days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.max_age_days)

        headers = {
            "User-Agent": "max-signal-fetcher/1.0",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
        }

        async with httpx.AsyncClient(timeout=30, headers=headers, follow_redirects=True) as client:
            for feed_url in self.feeds:
                if len(signals) >= limit:
                    break

                try:
                    response = await fetch_with_retry(
                        feed_url,
                        client,
                        adapter_name=self.name,
                    )
                except Exception:
                    logger.warning("RSS feed fetch failed: %s", feed_url, exc_info=True)
                    continue

                for entry in _parse_rss_entries(response.text, feed_url):
                    published_at = entry["published_at"]
                    if cutoff is not None and published_at is not None and published_at < cutoff:
                        continue

                    url = entry["url"]
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    signals.append(
                        Signal(
                            source_type=SignalSourceType.ARTICLE,
                            source_adapter=self.name,
                            title=entry["title"],
                            content=entry["content"][:1000],
                            url=url,
                            published_at=published_at,
                            tags=self.tags,
                            credibility=0.5,
                            metadata={"feed_url": feed_url},
                        )
                    )

                    if len(signals) >= limit:
                        break

        return signals[:limit]

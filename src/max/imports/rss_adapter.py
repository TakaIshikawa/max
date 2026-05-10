"""RSS/Atom feed source adapter for blog aggregation.

Aggregates content from tech blogs and news feeds.  Parses RSS 2.0 and Atom
feed formats, extracts articles with titles, summaries, authors, and
publication dates.  Supports multiple feed URLs for broad content collection.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

_DEFAULT_FEEDS: list[str] = []

# Atom namespace
_ATOM_NS = "http://www.w3.org/2005/Atom"


def _strip_html(text: str) -> str:
    """Remove HTML tags from feed content."""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def _parse_rfc822(date_str: str | None) -> datetime | None:
    """Parse RFC 822 date (RSS 2.0 pubDate format)."""
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str.strip())
    except Exception:
        return None


def _parse_iso(date_str: str | None) -> datetime | None:
    """Parse ISO 8601 / RFC 3339 date (Atom updated/published format)."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _parse_rss_items(root: ET.Element) -> list[dict]:
    """Extract items from an RSS 2.0 feed."""
    entries: list[dict] = []
    channel = root.find("channel")
    if channel is None:
        return entries

    feed_title = (channel.findtext("title") or "").strip()

    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = _strip_html(item.findtext("description") or "")
        author = (item.findtext("author") or item.findtext("{http://purl.org/dc/elements/1.1/}creator") or "").strip()
        pub_date = _parse_rfc822(item.findtext("pubDate"))

        if not title:
            continue

        entries.append({
            "title": title,
            "link": link,
            "summary": description[:1000],
            "author": author or None,
            "published_at": pub_date,
            "feed_title": feed_title,
        })

    return entries


def _parse_atom_items(root: ET.Element) -> list[dict]:
    """Extract entries from an Atom feed."""
    entries: list[dict] = []
    feed_title = ""
    title_el = root.find(f"{{{_ATOM_NS}}}title")
    if title_el is not None and title_el.text:
        feed_title = title_el.text.strip()

    for entry in root.findall(f"{{{_ATOM_NS}}}entry"):
        title_el = entry.find(f"{{{_ATOM_NS}}}title")
        title = (title_el.text if title_el is not None and title_el.text else "").strip()

        link = ""
        for link_el in entry.findall(f"{{{_ATOM_NS}}}link"):
            rel = link_el.get("rel", "alternate")
            if rel == "alternate":
                link = link_el.get("href", "")
                break
        if not link:
            link_el = entry.find(f"{{{_ATOM_NS}}}link")
            if link_el is not None:
                link = link_el.get("href", "")

        summary_el = entry.find(f"{{{_ATOM_NS}}}summary")
        content_el = entry.find(f"{{{_ATOM_NS}}}content")
        summary = _strip_html(
            (summary_el.text if summary_el is not None and summary_el.text else "")
            or (content_el.text if content_el is not None and content_el.text else "")
        )

        author_name = None
        author_el = entry.find(f"{{{_ATOM_NS}}}author")
        if author_el is not None:
            name_el = author_el.find(f"{{{_ATOM_NS}}}name")
            if name_el is not None and name_el.text:
                author_name = name_el.text.strip()

        published = _parse_iso(
            (entry.findtext(f"{{{_ATOM_NS}}}published"))
            or (entry.findtext(f"{{{_ATOM_NS}}}updated"))
        )

        if not title:
            continue

        entries.append({
            "title": title,
            "link": link,
            "summary": summary[:1000],
            "author": author_name,
            "published_at": published,
            "feed_title": feed_title,
        })

    return entries


def parse_feed(xml_content: str) -> list[dict]:
    """Parse RSS 2.0 or Atom feed XML into entry dicts."""
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        logger.warning("Failed to parse feed XML")
        return []

    # Detect format: Atom feeds have the Atom namespace on root
    if root.tag == f"{{{_ATOM_NS}}}feed":
        return _parse_atom_items(root)
    elif root.tag == "rss":
        return _parse_rss_items(root)
    else:
        logger.warning("Unknown feed format: root tag=%s", root.tag)
        return []


class RSSAdapter(SourceAdapter):
    """Fetches and parses RSS 2.0 and Atom feeds from configured URLs.

    Extracts article titles, summaries, authors, and publication dates.
    Supports batch fetching from multiple feed URLs.

    Config options:
        feeds: list of feed URLs to fetch
    """

    @property
    def name(self) -> str:
        return "rss_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ARTICLE.value

    @property
    def feeds(self) -> list[str]:
        f = self._config.get("feeds", _DEFAULT_FEEDS)
        return f if isinstance(f, list) else []

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_links: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for feed_url in self.feeds:
                if len(signals) >= limit:
                    break

                try:
                    resp = await fetch_with_retry(
                        feed_url,
                        client,
                        adapter_name=self.name,
                    )
                    entries = parse_feed(resp.text)
                except Exception:
                    logger.warning("RSS fetch failed for %s", feed_url, exc_info=True)
                    continue

                for entry in entries:
                    link = entry.get("link", "")
                    if link and link in seen_links:
                        continue
                    if link:
                        seen_links.add(link)

                    signals.append(
                        Signal(
                            source_type=SignalSourceType.ARTICLE,
                            source_adapter=self.name,
                            title=entry["title"],
                            content=entry.get("summary", "")[:500],
                            url=link,
                            author=entry.get("author"),
                            published_at=entry.get("published_at"),
                            tags=["rss", "blog"],
                            credibility=0.6,
                            metadata={
                                "feed_url": feed_url,
                                "feed_title": entry.get("feed_title", ""),
                            },
                        )
                    )

                    if len(signals) >= limit:
                        break

        return signals[:limit]

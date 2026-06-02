"""Docker Blog RSS source adapter."""

from __future__ import annotations

import hashlib
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

DEFAULT_FEED_URL = "https://www.docker.com/blog/feed/"
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
    except (TypeError, ValueError, IndexError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            logger.debug("Failed to parse RSS datetime: %s", value, exc_info=True)
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _categories(item: ET.Element) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for child in item.findall("category"):
        category = _normalize_text(child.text)
        key = category.lower()
        if category and key not in seen:
            seen.add(key)
            values.append(category)
    return values


def _parse_items(xml_text: str, feed_url: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("Failed to parse RSS feed: %s", feed_url)
        return []

    channel = root.find("channel")
    items = channel.findall("item") if channel is not None else root.findall("item")
    entries: list[dict] = []
    for item in items:
        title = _child_text(item, "title")
        link = _child_text(item, "link")
        guid = _child_text(item, "guid")
        url = link or guid
        if not title or not url:
            continue
        content = _child_text(item, "description") or _child_text(item, f"{_CONTENT_NS}encoded")
        entries.append(
            {
                "title": title,
                "content": content,
                "url": url,
                "published_at": _parse_datetime(_child_text(item, "pubDate")),
                "categories": _categories(item),
                "guid": guid,
            }
        )
    return entries


def _matches_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return not terms or any(term.lower() in lowered for term in terms)


def _stable_id(source_name: str, dedupe_key: str) -> str:
    return f"{source_name}:{hashlib.sha256(dedupe_key.encode()).hexdigest()[:16]}"


class RssBlogAdapter(SourceAdapter):
    """Base adapter for compact public RSS blog/changelog feeds."""

    adapter_name = ""
    default_feed_url = ""
    source_tag = ""
    category_config_key = "categories"
    config_keys = ["feed_url", "categories", "keywords", "max_age_days", "timeout"]
    required_keys: list[str] = []
    description = "Fetches public RSS feed entries."

    @property
    def name(self) -> str:
        return self.adapter_name

    @property
    def source_type(self) -> str:
        return SignalSourceType.NEWS.value

    @property
    def feed_url(self) -> str:
        return str(self._config.get("feed_url") or self.default_feed_url)

    @property
    def category_filters(self) -> list[str]:
        return [str(value) for value in self._config.get(self.category_config_key, [])]

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

    def _matches_extra_filters(self, entry: dict) -> bool:
        return True

    def _metadata(self, entry: dict) -> dict:
        return {
            "feed_url": self.feed_url,
            self.category_config_key: entry["categories"],
            "guid": entry["guid"],
        }

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []
        headers = {
            "User-Agent": "max-signal-fetcher/1.0",
            "Accept": "application/rss+xml, application/xml, text/xml",
        }
        async with httpx.AsyncClient(timeout=self.timeout, headers=headers, follow_redirects=True) as client:
            try:
                response = await fetch_with_retry(self.feed_url, client, adapter_name=self.name)
            except Exception:
                logger.warning("%s feed fetch failed: %s", self.name, self.feed_url, exc_info=True)
                return []

        cutoff = None
        if self.max_age_days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.max_age_days)

        signals: list[Signal] = []
        seen: set[str] = set()
        for entry in _parse_items(response.text, self.feed_url):
            published_at = entry["published_at"]
            if cutoff is not None and published_at is not None and published_at < cutoff:
                continue
            if self.category_filters and not any(
                wanted.lower() == category.lower()
                for wanted in self.category_filters
                for category in entry["categories"]
            ):
                continue
            if not _matches_any(f"{entry['title']} {entry['content']}", self.keywords):
                continue
            if not self._matches_extra_filters(entry):
                continue

            dedupe_key = entry["guid"] or entry["url"]
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            tags = [self.source_tag, *entry["categories"]] if self.source_tag else entry["categories"]
            signals.append(
                Signal(
                    id=_stable_id(self.name, dedupe_key),
                    source_type=SignalSourceType.NEWS,
                    source_adapter=self.name,
                    title=entry["title"],
                    content=(entry["content"] or entry["title"])[:1000],
                    url=entry["url"],
                    published_at=published_at,
                    tags=tags,
                    metadata=self._metadata(entry),
                )
            )
            if len(signals) >= limit:
                break
        return signals


class DockerBlogAdapter(RssBlogAdapter):
    """Fetches Docker Blog posts from the public RSS feed."""

    adapter_name = "docker_blog"
    default_feed_url = DEFAULT_FEED_URL
    source_tag = "docker"
    category_config_key = "categories"
    config_keys = ["feed_url", "categories", "keywords", "max_age_days", "timeout"]
    description = "Fetches Docker Blog posts from the public RSS feed."

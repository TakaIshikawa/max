"""Cloudflare Changelog RSS source adapter."""

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

DEFAULT_FEED_URL = "https://developers.cloudflare.com/changelog/index.xml"
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
        logger.debug("Failed to parse Cloudflare Changelog datetime: %s", value, exc_info=True)
        return None


def _categories(item: ET.Element) -> list[str]:
    products: list[str] = []
    seen: set[str] = set()
    for child in item.findall("category"):
        product = _normalize_text(child.text)
        if product and product not in seen:
            seen.add(product)
            products.append(product)
    return products


def _parse_items(xml_text: str, feed_url: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("Failed to parse Cloudflare Changelog feed: %s", feed_url)
        return []

    channel = root.find("channel")
    items = channel.findall("item") if channel is not None else root.findall("item")
    entries: list[dict] = []
    for item in items:
        title = _child_text(item, "title")
        url = _child_text(item, "link") or _child_text(item, "guid")
        if not title or not url:
            continue
        content = _child_text(item, "description") or _child_text(item, f"{_CONTENT_NS}encoded")
        products = _categories(item)
        entries.append({
            "title": title,
            "content": content,
            "url": url,
            "published_at": _parse_datetime(_child_text(item, "pubDate")),
            "products": products,
            "guid": _child_text(item, "guid"),
        })
    return entries


def _contains_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return not terms or any(term.lower() in lowered for term in terms)


class CloudflareChangelogAdapter(SourceAdapter):
    """Fetches Cloudflare developer changelog entries from the public RSS feed."""

    config_keys = ["feed_url", "products", "keywords", "max_age_days", "timeout"]
    required_keys: list[str] = []
    description = "Fetches Cloudflare developer changelog entries from the public RSS feed."

    @property
    def name(self) -> str:
        return "cloudflare_changelog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.NEWS.value

    @property
    def feed_url(self) -> str:
        return str(self._config.get("feed_url") or DEFAULT_FEED_URL)

    @property
    def products(self) -> list[str]:
        return [str(value) for value in self._config.get("products", [])]

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
                logger.warning("Cloudflare Changelog feed fetch failed: %s", self.feed_url, exc_info=True)
                return []

        cutoff = None
        if self.max_age_days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.max_age_days)

        signals: list[Signal] = []
        seen_urls: set[str] = set()
        for entry in _parse_items(response.text, self.feed_url):
            published_at = entry["published_at"]
            if cutoff is not None and published_at is not None and published_at < cutoff:
                continue
            products = entry["products"]
            if self.products and not any(
                wanted.lower() == product.lower()
                for wanted in self.products
                for product in products
            ):
                continue
            if not _contains_any(f"{entry['title']} {entry['content']}", self.keywords):
                continue
            if entry["url"] in seen_urls:
                continue
            seen_urls.add(entry["url"])

            signals.append(
                Signal(
                    source_type=SignalSourceType.NEWS,
                    source_adapter=self.name,
                    title=entry["title"],
                    content=entry["content"][:1000],
                    url=entry["url"],
                    published_at=published_at,
                    tags=["cloudflare", *products],
                    metadata={"feed_url": self.feed_url, "products": products, "guid": entry["guid"]},
                )
            )
            if len(signals) >= limit:
                break
        return signals

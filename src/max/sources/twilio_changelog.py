"""Twilio changelog source adapter."""

from __future__ import annotations

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

DEFAULT_FEED_URL = "https://www.twilio.com/changelog/rss"
logger = logging.getLogger(__name__)


class TwilioChangelogAdapter(SourceAdapter):
    """Converts Twilio changelog entries into signals."""

    config_keys = ["entries", "payload", "feed_url", "products", "keywords", "max_age_days", "timeout"]
    required_keys: list[str] = []
    description = "Converts Twilio changelog entries into communications platform signals."

    @property
    def name(self) -> str:
        return "twilio_changelog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        try:
            entries = await _entries_from_config_or_feed(
                {**self._config, "feed_url": self._config.get("feed_url") or DEFAULT_FEED_URL},
                self.name,
            )
            return parse_twilio_changelog(
                entries,
                products=self._config.get("products"),
                keywords=self._config.get("keywords"),
                max_age_days=self._config.get("max_age_days"),
                limit=limit,
            )
        except Exception:
            logger.warning("Twilio changelog fetch failed", exc_info=True)
            return []


def parse_twilio_changelog(
    payload: Any,
    *,
    feed_url: str = DEFAULT_FEED_URL,
    products: Any = None,
    keywords: Any = None,
    max_age_days: Any = None,
    limit: int | None = None,
) -> list[Signal]:
    return _parse(payload, "twilio_changelog", "twilio", feed_url, products, keywords, max_age_days, limit=limit)


def _entry_to_signal(entry: dict[str, Any]) -> Signal | None:
    title = text(entry.get("title") or entry.get("name"))
    url = text(entry.get("url") or entry.get("link"))
    if not title or not url:
        return None
    products = strings(entry.get("products") or entry.get("product") or entry.get("tags"))
    category = text(entry.get("change_category") or entry.get("category") or entry.get("type"))
    tags = _dedupe(["twilio", "communications", *products, category])
    return Signal(
        id=f"twilio_changelog:{hashlib.sha1(url.encode()).hexdigest()[:12]}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter="twilio_changelog",
        title=title,
        content=text(entry.get("content") or entry.get("summary") or entry.get("description"))[:1000],
        url=url,
        published_at=parse_datetime(entry.get("published_at") or entry.get("date")),
        tags=tags,
        metadata={"products": products, "category": category, "entry_id": text(entry.get("id"))},
    )


async def _entries_from_config_or_feed(config: dict[str, Any], adapter_name: str) -> list[dict[str, Any]]:
    if config.get("entries") is not None:
        return _entries(config.get("entries"))
    if config.get("payload") is not None:
        return _entries(config.get("payload"))
    feed_url = text(config.get("feed_url") or DEFAULT_FEED_URL)
    headers = {"User-Agent": "max-signal-fetcher/1.0", "Accept": "application/rss+xml, application/xml, text/xml"}
    async with httpx.AsyncClient(timeout=float(config.get("timeout", 30)), headers=headers, follow_redirects=True) as client:
        try:
            response = await fetch_with_retry(feed_url, client, adapter_name=adapter_name)
        except Exception:
            logger.warning("%s feed fetch failed: %s", adapter_name, feed_url, exc_info=True)
            return []
    return _parse_feed(response.text)


async def _fetch_text(feed_url: str, timeout: float) -> str:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(feed_url)
        response.raise_for_status()
        return response.text


def _parse(
    payload: Any,
    adapter: str,
    vendor_tag: str,
    feed_url: str,
    products: Any,
    keywords: Any,
    max_age_days: Any,
    *,
    limit: int | None = None,
) -> list[Signal]:
    product_terms = _terms(products)
    keyword_terms = _terms(keywords)
    max_age = _int(max_age_days)
    seen: set[str] = set()
    signals: list[Signal] = []
    for entry in _entries(payload):
        title = text(entry.get("title") or entry.get("name"))
        url = text(entry.get("url") or entry.get("link"))
        content = text(entry.get("content") or entry.get("summary") or entry.get("description")) or title
        categories = _dedupe([*strings(entry.get("categories")), *strings(entry.get("tags")), text(entry.get("category"))])
        published_at = parse_datetime(entry.get("published_at") or entry.get("date"))
        haystack = " ".join([title, content, " ".join(categories)]).casefold()
        category_terms = [category.casefold() for category in categories]
        if not title or not url or url in seen:
            continue
        if product_terms and not any(term in haystack or term in category_terms for term in product_terms):
            continue
        if keyword_terms and not any(term in haystack for term in keyword_terms):
            continue
        if max_age is not None and published_at is not None and _now() - published_at > max_age:
            continue
        seen.add(url)
        tags = _dedupe([vendor_tag, *categories])
        metadata: dict[str, Any] = {"feed_url": feed_url, "categories": [category.casefold() for category in categories]}
        if adapter == "twilio_changelog":
            products_metadata = strings(entry.get("products") or entry.get("product") or entry.get("tags"))
            category = text(entry.get("change_category") or entry.get("category") or entry.get("type")) or (categories[0] if categories else "")
            tags = _dedupe(["twilio", "communications", *products_metadata, category])
            metadata.update({"products": products_metadata, "category": category, "entry_id": text(entry.get("id"))})
        signals.append(
            Signal(
                id=f"{adapter}:{hashlib.sha1(url.encode()).hexdigest()[:12]}",
                source_type=SignalSourceType.ROADMAP,
                source_adapter=adapter,
                title=title,
                content=content[:1000],
                url=url,
                published_at=published_at,
                tags=tags,
                metadata=metadata,
            )
        )
        if limit is not None and len(signals) >= max(0, limit):
            break
    signals.sort(key=lambda signal: (signal.published_at or datetime.min.replace(tzinfo=timezone.utc), signal.id), reverse=True)
    return signals


def _entries(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        payload = value.get("entries") or value.get("items") or value.get("data") or []
    else:
        payload = value
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, str):
        return _parse_feed(payload)
    return []


def _parse_feed(xml_text: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    entries: list[dict[str, Any]] = []
    for item in root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry"):
        categories = [
            _clean(child.text) or _clean(child.get("term"))
            for child in item.findall("category") + item.findall("{http://www.w3.org/2005/Atom}category")
            if _clean(child.text) or _clean(child.get("term"))
        ]
        atom_link = item.find("{http://www.w3.org/2005/Atom}link")
        entries.append(
            {
                "title": _child(item, "title", "{http://www.w3.org/2005/Atom}title"),
                "url": _child(item, "link") or (text(atom_link.get("href")) if atom_link is not None else "") or _child(item, "guid"),
                "content": _child(item, "description", "summary", "{http://www.w3.org/2005/Atom}summary"),
                "published_at": _child(item, "pubDate", "published", "{http://www.w3.org/2005/Atom}published"),
                "categories": categories,
                "tags": categories,
                "category": categories[0] if categories else "",
                "id": _child(item, "guid", "id", "{http://www.w3.org/2005/Atom}id"),
            }
        )
    return entries


def _child(element: ET.Element, *tags: str) -> str:
    for tag in tags:
        child = element.find(tag)
        if child is not None:
            return _clean(child.text)
    return ""


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(str(value)))).strip()


def parse_datetime(value: Any) -> datetime | None:
    value_text = text(value)
    if not value_text:
        return None
    try:
        parsed = datetime.fromisoformat(value_text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value_text)
        except (TypeError, ValueError, IndexError, OverflowError):
            return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def strings(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    if not isinstance(value, list):
        return []
    return _dedupe([text(item) for item in value])


def _terms(value: Any) -> list[str]:
    if isinstance(value, str):
        source = [value]
    elif isinstance(value, list | tuple | set):
        source = list(value)
    else:
        source = []
    return [text(item).casefold() for item in source if text(item)]


def _int(value: Any) -> timedelta | None:
    try:
        days = max(0, int(float(value))) if value is not None else None
    except (TypeError, ValueError):
        return None
    return timedelta(days=days) if days is not None else None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = text(value)
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

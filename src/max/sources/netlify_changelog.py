"""Netlify changelog source adapter."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

DEFAULT_FEED_URL = "https://www.netlify.com/changelog/rss/"


class NetlifyChangelogAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "netlify_changelog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.NEWS.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        try:
            payload = self._config.get("entries") or self._config.get("payload")
            if payload is None:
                payload = await _fetch_text(_text(self._config.get("feed_url")) or DEFAULT_FEED_URL, float(self._config.get("timeout", 10)))
            return parse_netlify_changelog(
                payload,
                feed_url=_text(self._config.get("feed_url")) or DEFAULT_FEED_URL,
                products=self._config.get("products"),
                keywords=self._config.get("keywords"),
                max_age_days=self._config.get("max_age_days"),
            )[:limit]
        except Exception:
            return []


def parse_netlify_changelog(
    payload: Any,
    *,
    feed_url: str = DEFAULT_FEED_URL,
    products: Any = None,
    keywords: Any = None,
    max_age_days: Any = None,
) -> list[Signal]:
    return _parse(payload, "netlify_changelog", "netlify", feed_url, products, keywords, max_age_days)


async def _fetch_text(feed_url: str, timeout: float) -> str:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(feed_url)
        response.raise_for_status()
        return response.text


def _parse(payload: Any, adapter: str, vendor_tag: str, feed_url: str, products: Any, keywords: Any, max_age_days: Any) -> list[Signal]:
    entries = _entries(payload)
    terms = _terms(products)
    keyword_terms = _terms(keywords)
    max_age = _int(max_age_days)
    seen: set[str] = set()
    signals: list[Signal] = []
    for entry in entries:
        title = _text(entry.get("title"))
        url = _text(entry.get("url") or entry.get("link"))
        content = _text(entry.get("content") or entry.get("summary") or entry.get("description")) or title
        categories = [_text(item).casefold() for item in entry.get("categories", []) if _text(item)]
        published_at = _dt(entry.get("published_at") or entry.get("date"))
        haystack = " ".join([title, content, " ".join(categories)]).casefold()
        if not title or not url or url in seen:
            continue
        if terms and not any(term in haystack or term in categories for term in terms):
            continue
        if keyword_terms and not any(term in haystack for term in keyword_terms):
            continue
        if max_age is not None and published_at is not None and _now() - published_at > timedelta(days=max_age):
            continue
        seen.add(url)
        tags = [vendor_tag, *[category for category in categories if category]]
        signals.append(
            Signal(
                id=f"{adapter}:{hashlib.sha1(url.encode()).hexdigest()[:12]}",
                source_type=SignalSourceType.NEWS,
                source_adapter=adapter,
                title=title,
                content=content[:1000],
                url=url,
                published_at=published_at,
                tags=tags,
                metadata={"feed_url": feed_url, "categories": categories},
            )
        )
    signals.sort(key=lambda signal: (signal.published_at or datetime.min.replace(tzinfo=timezone.utc), signal.id), reverse=True)
    return signals


def _entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        source = payload.get("entries") or payload.get("items") or []
    else:
        source = payload
    if isinstance(source, list):
        return [item for item in source if isinstance(item, dict)]
    if isinstance(source, str):
        try:
            root = ET.fromstring(source)
        except ET.ParseError:
            return []
        rows = []
        for item in root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry"):
            categories = [_node_text(node) for node in item.findall("category") + item.findall("{http://www.w3.org/2005/Atom}category")]
            atom_link = item.find("{http://www.w3.org/2005/Atom}link")
            rows.append(
                {
                    "title": _node_text(_first(item, "title", "{http://www.w3.org/2005/Atom}title")),
                    "url": _node_text(item.find("link")) or (atom_link.get("href") if atom_link is not None else ""),
                    "description": _node_text(_first(item, "description", "summary", "{http://www.w3.org/2005/Atom}summary")),
                    "published_at": _node_text(_first(item, "pubDate", "published", "{http://www.w3.org/2005/Atom}published")),
                    "categories": categories,
                }
            )
        return rows
    return []


def _first(item: ET.Element, *names: str) -> ET.Element | None:
    for name in names:
        node = item.find(name)
        if node is not None:
            return node
    return None


def _node_text(node: Any) -> str:
    return _text(getattr(node, "text", None))


def _dt(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %z",):
        try:
            return datetime.strptime(text, fmt).astimezone(timezone.utc)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _terms(value: Any) -> list[str]:
    if isinstance(value, str):
        source = [value]
    elif isinstance(value, list | tuple | set):
        source = list(value)
    else:
        source = []
    return [_text(item).casefold() for item in source if _text(item)]


def _int(value: Any) -> int | None:
    try:
        return max(0, int(float(value))) if value is not None else None
    except (TypeError, ValueError):
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

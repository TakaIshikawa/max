"""Cloudflare Blog source adapter."""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

ATOM_NS = "{http://www.w3.org/2005/Atom}"


class CloudflareBlogAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "cloudflare_blog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.NEWS.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        payload = self._config.get("entries") or self._config.get("payload") or self._config.get("feed") or []
        return parse_cloudflare_blog(payload, limit=limit)


def parse_cloudflare_blog(payload: Any, *, limit: int | None = None) -> list[Signal]:
    entries = _entries(payload)
    signals: list[Signal] = []
    seen_urls: set[str] = set()
    for entry in entries:
        title = _text(entry.get("title") or entry.get("name"))
        url = _canonical_url(entry.get("url") or entry.get("link") or entry.get("guid") or entry.get("id"))
        if not title or not url or url in seen_urls:
            continue
        seen_urls.add(url)
        summary = _text(entry.get("summary") or entry.get("description") or entry.get("content") or entry.get("body"))
        if not summary:
            summary = title
        tags = _tags(entry)
        signals.append(
            Signal(
                id=_id("cloudflare_blog", url),
                source_type=SignalSourceType.NEWS,
                source_adapter="cloudflare_blog",
                title=title,
                content=summary[:1000],
                url=url,
                author=_text(entry.get("author")) or None,
                published_at=_dt(entry.get("published_at") or entry.get("published") or entry.get("date") or entry.get("pubDate")),
                tags=["cloudflare", *tags],
                metadata={"source_name": "Cloudflare Blog", "categories": tags},
            )
        )
        if limit is not None and len(signals) >= limit:
            break
    return signals


def _entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, str):
        return _xml_entries(payload)
    if isinstance(payload, dict):
        value = payload.get("entries") or payload.get("items") or payload.get("feed") or []
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def _xml_entries(xml_text: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items = root.findall(".//item")
    if items:
        return [_rss_item(item) for item in items]
    return [_atom_entry(entry) for entry in root.findall(f".//{ATOM_NS}entry")]


def _rss_item(item: ET.Element) -> dict[str, Any]:
    return {
        "title": _child(item, "title"),
        "url": _child(item, "link") or _child(item, "guid"),
        "summary": _child(item, "description"),
        "published_at": _child(item, "pubDate"),
        "categories": [_clean(child.text) for child in item.findall("category") if _clean(child.text)],
    }


def _atom_entry(entry: ET.Element) -> dict[str, Any]:
    link = entry.find(f"{ATOM_NS}link")
    return {
        "title": _child(entry, f"{ATOM_NS}title"),
        "url": link.get("href") if link is not None else _child(entry, f"{ATOM_NS}id"),
        "summary": _child(entry, f"{ATOM_NS}summary") or _child(entry, f"{ATOM_NS}content"),
        "published_at": _child(entry, f"{ATOM_NS}published") or _child(entry, f"{ATOM_NS}updated"),
        "categories": [category.get("term", "") for category in entry.findall(f"{ATOM_NS}category") if category.get("term")],
    }


def _tags(entry: dict[str, Any]) -> list[str]:
    values = entry.get("tags") or entry.get("categories") or entry.get("category") or []
    if isinstance(values, str):
        values = [values]
    seen: set[str] = set()
    tags: list[str] = []
    for value in values if isinstance(values, list) else []:
        tag = _text(value)
        if tag and tag.lower() != "cloudflare" and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def _child(element: ET.Element, tag: str) -> str:
    child = element.find(tag)
    return _clean(child.text) if child is not None else ""


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", str(value)))).strip() if value is not None else ""


def _text(value: Any) -> str:
    return _clean(value)


def _canonical_url(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    parts = urlsplit(text)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or parts.path, "", ""))


def _dt(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text) if "," in text else datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def _id(adapter: str, url: str) -> str:
    return f"{adapter}:{hashlib.sha1(url.encode()).hexdigest()[:12]}"

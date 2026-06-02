"""Twilio changelog source adapter."""

from __future__ import annotations

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
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

    config_keys = ["entries", "feed_url", "timeout"]
    required_keys: list[str] = []
    description = "Converts Twilio changelog entries into communications platform signals."

    @property
    def name(self) -> str:
        return "twilio_changelog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        entries = await _entries_from_config_or_feed(self._config, self.name)
        signals: list[Signal] = []
        seen_urls: set[str] = set()
        for entry in entries:
            signal = _entry_to_signal(entry)
            if signal is None or signal.url in seen_urls:
                continue
            seen_urls.add(signal.url)
            signals.append(signal)
            if len(signals) >= max(0, limit):
                break
        return signals


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


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = text(value)
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


async def _entries_from_config_or_feed(config: dict[str, Any], adapter_name: str) -> list[dict[str, Any]]:
    if config.get("entries") is not None:
        return _entries(config.get("entries"))
    feed_url = text(config.get("feed_url") or DEFAULT_FEED_URL)
    headers = {"User-Agent": "max-signal-fetcher/1.0", "Accept": "application/rss+xml, application/xml, text/xml"}
    async with httpx.AsyncClient(timeout=float(config.get("timeout", 30)), headers=headers, follow_redirects=True) as client:
        try:
            response = await fetch_with_retry(feed_url, client, adapter_name=adapter_name)
        except Exception:
            logger.warning("Twilio changelog feed fetch failed: %s", feed_url, exc_info=True)
            return []
    return _parse_feed(response.text)


def _entries(value: Any) -> list[dict[str, Any]]:
    payload = value.get("entries") or value.get("items") or value.get("data") if isinstance(value, dict) else value
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def _parse_feed(xml_text: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    channel = root.find("channel")
    items = channel.findall("item") if channel is not None else root.findall("item")
    entries: list[dict[str, Any]] = []
    for item in items:
        categories = [_clean(child.text) for child in item.findall("category") if _clean(child.text)]
        entries.append({
            "title": _child(item, "title"),
            "url": _child(item, "link") or _child(item, "guid"),
            "content": _child(item, "description"),
            "published_at": _child(item, "pubDate"),
            "tags": categories,
            "category": categories[0] if categories else "",
            "id": _child(item, "guid"),
        })
    return entries


def _child(element: ET.Element, tag: str) -> str:
    child = element.find(tag)
    return _clean(child.text) if child is not None else ""


def _clean(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(value))).strip()


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


def text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

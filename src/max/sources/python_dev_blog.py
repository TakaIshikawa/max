"""Python Developer Blog source adapter."""

from __future__ import annotations

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
DEFAULT_FEED_URL = "https://blog.python.org/feeds/posts/default"


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _id(url: str) -> str:
    return "python_dev_blog:" + hashlib.sha256(url.encode()).hexdigest()[:16]


def _entries(xml_text: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    atom = "{http://www.w3.org/2005/Atom}"
    items = root.findall(f"{atom}entry") or root.findall("./channel/item")
    entries: list[dict] = []
    for item in items:
        is_atom = item.tag.endswith("entry")
        title = _clean((item.find(f"{atom}title") if is_atom else item.find("title")).text if (item.find(f"{atom}title") if is_atom else item.find("title")) is not None else "")
        link = ""
        if is_atom:
            for child in item.findall(f"{atom}link"):
                if child.get("href"):
                    link = child.get("href", "")
                    break
        else:
            link_node = item.find("link")
            link = _clean(link_node.text if link_node is not None else "")
        summary_node = item.find(f"{atom}summary") or item.find(f"{atom}content") or item.find("description")
        author_node = item.find(f"{atom}author/{atom}name") or item.find("author")
        date_node = item.find(f"{atom}published") or item.find(f"{atom}updated") or item.find("pubDate")
        tags = [_clean(c.get("term") or c.text) for c in item.findall(f"{atom}category") + item.findall("category")]
        if title and link:
            entries.append({"title": title, "url": link, "summary": _clean(summary_node.text if summary_node is not None else ""), "author": _clean(author_node.text if author_node is not None else ""), "published_at": _dt(date_node.text if date_node is not None else None), "tags": [t for t in tags if t]})
    return entries


class PythonDevBlogAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "python_dev_blog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.NEWS.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []
        feed_url = str(self._config.get("feed_url") or DEFAULT_FEED_URL)
        async with httpx.AsyncClient(timeout=float(self._config.get("timeout", 30))) as client:
            try:
                response = await fetch_with_retry(feed_url, client, adapter_name=self.name)
            except Exception:
                logger.warning("Python developer blog fetch failed: %s", feed_url, exc_info=True)
                return []
        signals: list[Signal] = []
        seen: set[str] = set()
        for entry in _entries(response.text):
            if entry["url"] in seen:
                continue
            seen.add(entry["url"])
            signals.append(Signal(id=_id(entry["url"]), source_type=SignalSourceType.NEWS, source_adapter=self.name, title=entry["title"], content=entry["summary"] or entry["title"], url=entry["url"], author=entry["author"] or None, published_at=entry["published_at"], tags=["python", *entry["tags"]], metadata={"feed_url": feed_url, "tags": entry["tags"]}))
            if len(signals) >= limit:
                break
        return signals

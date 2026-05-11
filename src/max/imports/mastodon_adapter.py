"""Mastodon import adapter for public tag and query timelines."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import quote

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


class MastodonImportAdapter(SourceAdapter):
    """Fetch public Mastodon tag timelines as import signals."""

    @property
    def name(self) -> str:
        return "mastodon_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def instance_url(self) -> str:
        value = self._config.get("instance_url", "https://mastodon.social")
        text = str(value).strip().rstrip("/")
        return text if text.startswith(("http://", "https://")) else f"https://{text}"

    @property
    def tags(self) -> list[str]:
        configured = self._config.get("tags", [])
        return [str(tag).strip().lstrip("#") for tag in configured if str(tag).strip()]

    @property
    def query(self) -> str:
        value = self._config.get("query", "")
        return value if isinstance(value, str) else ""

    @property
    def access_token_env(self) -> str:
        value = self._config.get("access_token_env", "MASTODON_ACCESS_TOKEN")
        return value if isinstance(value, str) and value else "MASTODON_ACCESS_TOKEN"

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []
        headers = {"Accept": "application/json", "User-Agent": "max-mastodon-import-adapter/0.1"}
        if token := os.environ.get(self.access_token_env):
            headers["Authorization"] = f"Bearer {token}"

        signals: list[Signal] = []
        seen: set[str] = set()
        async with httpx.AsyncClient(timeout=30, headers=headers, follow_redirects=True) as client:
            for tag in self.tags or ([self.query] if self.query else []):
                if len(signals) >= limit:
                    break
                statuses = await self._fetch_tag(client, tag=tag, limit=limit - len(signals))
                for status in statuses:
                    if len(signals) >= limit:
                        break
                    signal = _status_to_signal(status, adapter_name=self.name, query=tag)
                    if signal is None:
                        continue
                    key = signal.metadata["status_id"] or signal.url
                    if key in seen:
                        continue
                    seen.add(key)
                    signals.append(signal)
        return signals[:limit]

    async def _fetch_tag(self, client: httpx.AsyncClient, *, tag: str, limit: int) -> list[dict]:
        try:
            response = await fetch_with_retry(
                f"{self.instance_url}/api/v1/timelines/tag/{quote(tag, safe='')}",
                client,
                adapter_name=self.name,
                params={"limit": min(max(limit, 1), 40)},
            )
            data = response.json()
        except Exception:
            logger.warning("Failed to fetch Mastodon tag %s", tag, exc_info=True)
            return []
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _status_to_signal(status: dict, *, adapter_name: str, query: str) -> Signal | None:
    content = _html_to_text(status.get("content"))
    if not content:
        return None
    account = status.get("account") if isinstance(status.get("account"), dict) else {}
    status_id = str(status.get("id") or "")
    url = str(status.get("url") or status.get("uri") or "")
    favourites = _int(status.get("favourites_count"))
    reblogs = _int(status.get("reblogs_count"))
    tags = sorted({"mastodon", "fediverse", "community", query.lower(), *_hashtags(status)})
    return Signal(
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter_name,
        title=content[:120],
        content=content[:1000],
        url=url,
        author=str(account.get("acct") or account.get("username") or "") or None,
        published_at=_parse_dt(status.get("created_at")),
        tags=tags,
        credibility=min(1.0, 0.35 + min(favourites + reblogs, 50) / 100),
        metadata={
            "status_id": status_id,
            "account": account.get("acct") or account.get("username"),
            "display_name": account.get("display_name"),
            "created_at": status.get("created_at"),
            "reblogs": reblogs,
            "favourites": favourites,
            "query": query,
            "url": url,
        },
    )


def _html_to_text(value: object) -> str:
    parser = _TextExtractor()
    parser.feed(str(value or ""))
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def _hashtags(status: dict) -> set[str]:
    raw = status.get("tags")
    if not isinstance(raw, list):
        return set()
    return {str(item.get("name", "")).strip().lower() for item in raw if isinstance(item, dict) and item.get("name")}


def _int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _parse_dt(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None

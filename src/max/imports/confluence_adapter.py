"""Confluence page import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from html.parser import HTMLParser
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class ConfluenceAdapter(SourceAdapter):
    """Fetch Confluence pages or search results and convert them to signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        bearer_token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.base_url = (base_url or _optional(self._config.get("base_url")) or os.getenv("CONFLUENCE_BASE_URL") or "").rstrip("/")
        self.email = email if email is not None else os.getenv("CONFLUENCE_EMAIL")
        self.api_token = api_token if api_token is not None else os.getenv("CONFLUENCE_API_TOKEN")
        self.bearer_token = bearer_token if bearer_token is not None else os.getenv("CONFLUENCE_BEARER_TOKEN")
        self._client = client

    @property
    def name(self) -> str:
        return "confluence_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def cql(self) -> str | None:
        return _optional(self._config.get("cql"))

    @property
    def space_key(self) -> str | None:
        return _optional(self._config.get("space_key"))

    @property
    def expand(self) -> str:
        configured = _strings(self._config.get("expand"))
        return ",".join(configured or ["body.storage", "body.view", "version", "history", "space", "metadata.labels", "ancestors"])

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.base_url:
            return []
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            pages = await self._get_pages(client, limit)
        finally:
            if close_client:
                await client.aclose()
        return [_page_signal(page, self.name, self.base_url) for page in pages[:limit] if isinstance(page, dict)]

    async def _get_pages(self, client: httpx.AsyncClient, limit: int) -> list[dict[str, Any]]:
        path = "/wiki/rest/api/content/search" if self.cql else "/wiki/rest/api/content"
        params: dict[str, Any] = {"limit": limit, "expand": self.expand}
        if self.cql:
            params["cql"] = self.cql
        elif self.space_key:
            params["spaceKey"] = self.space_key
            params["type"] = "page"
        headers = {"Authorization": f"Bearer {self.bearer_token}"} if self.bearer_token else None
        auth = (self.email, self.api_token) if self.email and self.api_token and not self.bearer_token else None
        try:
            response = await client.get(f"{self.base_url}{path}", headers=headers, auth=auth, params=params)
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Confluence page fetch failed", exc_info=True)
            return []
        results = body.get("results") if isinstance(body, dict) else None
        return results if isinstance(results, list) else []


ConfluencePageAdapter = ConfluenceAdapter


def _page_signal(page: dict[str, Any], adapter_name: str, base_url: str) -> Signal:
    body = page.get("body") if isinstance(page.get("body"), dict) else {}
    storage = body.get("storage") if isinstance(body.get("storage"), dict) else {}
    view = body.get("view") if isinstance(body.get("view"), dict) else {}
    content = _html_text(storage.get("value")) or _html_text(view.get("value"))
    history = page.get("history") if isinstance(page.get("history"), dict) else {}
    created_by = history.get("createdBy") if isinstance(history.get("createdBy"), dict) else {}
    version = page.get("version") if isinstance(page.get("version"), dict) else {}
    by = version.get("by") if isinstance(version.get("by"), dict) else {}
    space = page.get("space") if isinstance(page.get("space"), dict) else {}
    links = page.get("_links") if isinstance(page.get("_links"), dict) else {}
    labels = _labels(page)
    ancestors = [{"id": item.get("id"), "title": item.get("title")} for item in page.get("ancestors", []) if isinstance(item, dict)]
    webui = _text(links.get("webui") or links.get("tinyui"))
    url = webui if webui.startswith("http") else f"{base_url}{webui}" if webui else base_url
    return Signal(
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_text(page.get("title")) or _text(page.get("id")),
        content=content[:1000],
        url=url,
        author=_text(by.get("displayName")) or _text(created_by.get("displayName")) or None,
        published_at=_parse_dt(history.get("createdDate")),
        tags=sorted({"confluence", _text(space.get("key")), *labels} - {""})[:10],
        credibility=0.65,
        metadata={
            "confluence_page_id": page.get("id"),
            "space": {"id": space.get("id"), "key": space.get("key"), "name": space.get("name")},
            "labels": labels,
            "version": {"number": version.get("number"), "when": version.get("when"), "by": by.get("displayName")},
            "created_date": history.get("createdDate"),
            "updated_date": version.get("when"),
            "author": created_by.get("displayName") or by.get("displayName"),
            "ancestors": ancestors,
        },
    )


def _labels(page: dict[str, Any]) -> list[str]:
    metadata = page.get("metadata") if isinstance(page.get("metadata"), dict) else {}
    labels = metadata.get("labels") if isinstance(metadata.get("labels"), dict) else {}
    results = labels.get("results") if isinstance(labels.get("results"), list) else []
    return [_text(item.get("name")) for item in results if isinstance(item, dict) and _text(item.get("name"))]


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)


def _html_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    parser = _TextExtractor()
    parser.feed(value)
    return " ".join(parser.parts).strip() or value.strip()


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

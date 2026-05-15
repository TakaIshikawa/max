"""Confluence pages import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class ConfluencePagesImportAdapter(SourceAdapter):
    """Fetch Confluence pages from a configured space and convert them to signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        api_url: str | None = None,
        base_url: str | None = None,
        cloud_id: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        bearer_token: str | None = None,
        space_key: str | None = None,
        status: str | None = None,
        expand: list[str] | str | None = None,
        per_page: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.base_url = (
            base_url
            or _optional(self._config.get("base_url"))
            or os.getenv("CONFLUENCE_BASE_URL")
            or ""
        ).rstrip("/")
        self.cloud_id = _optional(
            cloud_id or self._config.get("cloud_id") or os.getenv("CONFLUENCE_CLOUD_ID")
        )
        raw_api_url = api_url or _optional(self._config.get("api_url")) or os.getenv("CONFLUENCE_API_URL")
        self.api_url = (
            raw_api_url.rstrip()
            if raw_api_url
            else f"https://api.atlassian.com/ex/confluence/{self.cloud_id}"
            if self.cloud_id
            else self.base_url
        ).rstrip("/")
        self.email = email if email is not None else os.getenv("CONFLUENCE_EMAIL")
        self.api_token = api_token if api_token is not None else os.getenv("CONFLUENCE_API_TOKEN")
        self.bearer_token = bearer_token if bearer_token is not None else os.getenv("CONFLUENCE_BEARER_TOKEN")
        self.space_key = _optional(space_key if space_key is not None else self._config.get("space_key"))
        self.status = _optional(status if status is not None else self._config.get("status")) or "current"
        self.expand = ",".join(
            _strings(expand if expand is not None else self._config.get("expand"))
            or ["body.storage", "body.view", "version", "history", "space", "metadata.labels"]
        )
        self.per_page = _positive_int(
            per_page if per_page is not None else self._config.get("per_page"),
            default=25,
            maximum=100,
        )
        self._client = client

    @property
    def name(self) -> str:
        return "confluence_pages_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.api_url or not self.space_key or not self._has_credentials():
            return []
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            pages = await self._fetch_pages(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()
        browse_base = self.base_url or self.api_url
        return [_page_signal(page, self.name, browse_base) for page in pages[:limit] if isinstance(page, dict)]

    async def _fetch_pages(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        pages: list[dict[str, Any]] = []
        start = 0
        path: str | None = "/wiki/rest/api/content"
        params: dict[str, Any] | None = self._params(start=start, limit=min(self.per_page, limit))
        while path and len(pages) < limit:
            try:
                response = await client.get(
                    f"{self.api_url}{path}",
                    headers=self._headers(),
                    auth=self._auth(),
                    params=params,
                )
                response.raise_for_status()
                body = response.json()
            except Exception:
                logger.warning("Confluence pages fetch failed", exc_info=True)
                return []
            results = body.get("results") if isinstance(body, dict) else []
            page = [item for item in results if isinstance(item, dict)] if isinstance(results, list) else []
            pages.extend(page)
            path, params, start = self._next_request(body, received=len(page), start=start, fetched=len(pages), limit=limit)
        return pages[:limit]

    def _params(self, *, start: int | None, limit: int) -> dict[str, Any]:
        params: dict[str, Any] = {
            "type": "page",
            "status": self.status,
            "spaceKey": self.space_key,
            "expand": self.expand,
            "limit": limit,
        }
        if start is not None:
            params["start"] = start
        return params

    def _next_request(
        self,
        body: object,
        *,
        received: int,
        start: int,
        fetched: int,
        limit: int,
    ) -> tuple[str | None, dict[str, Any] | None, int]:
        if not isinstance(body, dict) or fetched >= limit or received == 0:
            return None, None, start
        next_link = _next_link(body)
        if next_link:
            parsed = urlparse(next_link)
            path = parsed.path or next_link
            query = parse_qs(parsed.query)
            params = {key: values[-1] for key, values in query.items() if values}
            return path, params or None, _int(params.get("start"), start + received)
        cursor = _optional(body.get("cursor") or body.get("nextCursor") or body.get("next_cursor"))
        if cursor:
            return "/wiki/rest/api/content", self._cursor_params(cursor=cursor, limit=min(self.per_page, limit - fetched)), start
        page_limit = min(self.per_page, limit - fetched)
        if received < page_limit:
            return None, None, start
        next_start = start + received
        return "/wiki/rest/api/content", self._params(start=next_start, limit=page_limit), next_start

    def _cursor_params(self, *, cursor: str, limit: int) -> dict[str, Any]:
        params = self._params(start=None, limit=limit)
        params["cursor"] = cursor
        return params

    def _headers(self) -> dict[str, str]:
        if self.bearer_token:
            return {"Authorization": f"Bearer {self.bearer_token}", "Accept": "application/json"}
        return {"Accept": "application/json"}

    def _auth(self) -> tuple[str, str] | None:
        return (self.email, self.api_token) if self.email and self.api_token and not self.bearer_token else None

    def _has_credentials(self) -> bool:
        return bool(self.bearer_token or (self.email and self.api_token))


ConfluencePagesAdapter = ConfluencePagesImportAdapter


def _page_signal(page: dict[str, Any], adapter_name: str, base_url: str) -> Signal:
    page_id = _text(page.get("id"))
    body = _dict(page.get("body"))
    storage = _dict(body.get("storage"))
    view = _dict(body.get("view"))
    history = _dict(page.get("history"))
    created_by = _dict(history.get("createdBy"))
    version = _dict(page.get("version"))
    by = _dict(version.get("by"))
    space = _dict(page.get("space"))
    space_key = _text(space.get("key") or page.get("spaceKey"))
    labels = _labels(page)
    excerpt = _excerpt_text(page)
    storage_text = _html_text(storage.get("value"))
    content = excerpt or storage_text or _html_text(view.get("value"))
    web_url = _web_url(page, base_url)
    author = _text(by.get("displayName") or created_by.get("displayName")) or None
    return Signal(
        id=f"confluence-page:{space_key}:{page_id}" if page_id else "",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_text(page.get("title")) or page_id,
        content=content[:1000],
        url=web_url,
        author=author,
        published_at=_parse_dt(version.get("when") or history.get("lastUpdated") or history.get("createdDate")),
        tags=sorted({"confluence", "page", space_key, *labels} - {""})[:10],
        credibility=0.66,
        metadata={
            "confluence_page_id": page.get("id"),
            "space_key": space_key,
            "space": {"id": space.get("id"), "key": space.get("key"), "name": space.get("name")},
            "labels": labels,
            "version": {"number": version.get("number"), "when": version.get("when"), "by": by.get("displayName")},
            "author": {
                "account_id": by.get("accountId") or created_by.get("accountId"),
                "display_name": by.get("displayName") or created_by.get("displayName"),
            },
            "created_date": history.get("createdDate"),
            "updated_date": version.get("when"),
            "web_url": web_url,
            "excerpt": excerpt,
        },
    )


def _excerpt_text(page: dict[str, Any]) -> str:
    excerpt = page.get("excerpt")
    if isinstance(excerpt, dict):
        return _html_text(excerpt.get("value"))
    return _html_text(excerpt)


def _web_url(page: dict[str, Any], base_url: str) -> str:
    links = _dict(page.get("_links"))
    webui = _text(links.get("webui") or links.get("tinyui") or links.get("base"))
    if webui.startswith("http"):
        return webui
    return f"{base_url}{webui}" if webui else base_url


def _next_link(body: dict[str, Any]) -> str | None:
    links = _dict(body.get("_links"))
    return _optional(links.get("next") or body.get("next"))


def _labels(page: dict[str, Any]) -> list[str]:
    labels = _dict(_dict(page.get("metadata")).get("labels"))
    results = labels.get("results") if isinstance(labels.get("results"), list) else []
    return [_text(item.get("name")) for item in results if isinstance(item, dict) and _text(item.get("name"))]


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def _html_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    parser = _TextExtractor()
    parser.feed(value)
    return " ".join(parser.parts).strip() or value.strip()


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse_dt(value: object) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _positive_int(value: object, *, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, 1), maximum)


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    if not isinstance(value, list | tuple | set):
        return []
    return [_text(item) for item in value if _text(item)]


def _int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional(value: object) -> str | None:
    return _text(value) or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

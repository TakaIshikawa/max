"""Confluence blog posts import adapter."""

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


class ConfluenceBlogPostsImportAdapter(SourceAdapter):
    """Fetch Confluence blog posts and convert them to roadmap signals."""

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
        space_keys: list[str] | str | None = None,
        label: str | None = None,
        status: str | None = None,
        expand: list[str] | str | None = None,
        per_page: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.base_url = (base_url or _optional(self._config.get("base_url")) or os.getenv("CONFLUENCE_BASE_URL") or "").rstrip("/")
        self.cloud_id = _optional(cloud_id or self._config.get("cloud_id") or os.getenv("CONFLUENCE_CLOUD_ID"))
        raw_api_url = api_url or _optional(self._config.get("api_url")) or os.getenv("CONFLUENCE_API_URL")
        self.api_url = (raw_api_url.rstrip("/") if raw_api_url else f"https://api.atlassian.com/ex/confluence/{self.cloud_id}" if self.cloud_id else self.base_url)
        self.email = email if email is not None else os.getenv("CONFLUENCE_EMAIL")
        self.api_token = api_token if api_token is not None else os.getenv("CONFLUENCE_API_TOKEN")
        self.bearer_token = bearer_token if bearer_token is not None else os.getenv("CONFLUENCE_BEARER_TOKEN")
        self.space_keys = _strings(space_keys if space_keys is not None else self._config.get("space_keys"))
        self.label = _optional(label if label is not None else self._config.get("label"))
        self.status = _optional(status if status is not None else self._config.get("status")) or "current"
        self.expand = ",".join(_strings(expand if expand is not None else self._config.get("expand")) or ["body.storage", "version", "history", "space", "metadata.labels"])
        self.per_page = _positive_int(per_page if per_page is not None else self._config.get("per_page"), default=25, maximum=100)
        self._client = client

    @property
    def name(self) -> str:
        return "confluence_blog_posts_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.api_url or not (self.bearer_token or (self.email and self.api_token)):
            return []
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            posts = await self._fetch_posts(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()
        browse_base = self.base_url or self.api_url
        return [_post_signal(post, self.name, browse_base) for post in posts[:limit] if isinstance(post, dict)]

    async def _fetch_posts(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        posts: list[dict[str, Any]] = []
        start = 0
        while len(posts) < limit:
            page_limit = min(self.per_page, limit - len(posts))
            try:
                response = await client.get(
                    f"{self.api_url}/wiki/rest/api/content",
                    headers=self._headers(),
                    auth=self._auth(),
                    params=self._params(start=start, limit=page_limit),
                )
                response.raise_for_status()
                body = response.json()
            except Exception:
                logger.warning("Confluence blog posts fetch failed", exc_info=True)
                return []
            results = body.get("results") if isinstance(body, dict) else []
            page = [item for item in results if isinstance(item, dict)] if isinstance(results, list) else []
            posts.extend(page)
            if len(page) < page_limit:
                break
            start += page_limit
        return posts[:limit]

    def _params(self, *, start: int, limit: int) -> dict[str, Any]:
        params: dict[str, Any] = {"type": "blogpost", "status": self.status, "expand": self.expand, "start": start, "limit": limit}
        if self.space_keys:
            params["spaceKey"] = ",".join(self.space_keys)
        if self.label:
            params["label"] = self.label
        return params

    def _headers(self) -> dict[str, str] | None:
        if self.bearer_token:
            return {"Authorization": f"Bearer {self.bearer_token}", "Accept": "application/json"}
        return {"Accept": "application/json"}

    def _auth(self) -> tuple[str, str] | None:
        return (self.email, self.api_token) if self.email and self.api_token and not self.bearer_token else None


ConfluenceBlogPostsAdapter = ConfluenceBlogPostsImportAdapter


def _post_signal(post: dict[str, Any], adapter_name: str, base_url: str) -> Signal:
    body = _dict(post.get("body"))
    storage = _dict(body.get("storage"))
    history = _dict(post.get("history"))
    created_by = _dict(history.get("createdBy"))
    version = _dict(post.get("version"))
    by = _dict(version.get("by"))
    space = _dict(post.get("space"))
    links = _dict(post.get("_links"))
    labels = _labels(post)
    webui = _text(links.get("webui") or links.get("tinyui"))
    url = webui if webui.startswith("http") else f"{base_url}{webui}" if webui else base_url
    return Signal(
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_text(post.get("title") or post.get("id")),
        content=_html_text(storage.get("value"))[:1000],
        url=url,
        author=_text(by.get("displayName") or created_by.get("displayName")) or None,
        published_at=_parse_dt(history.get("createdDate") or version.get("when")),
        tags=sorted({"confluence", "blogpost", _text(space.get("key")), *labels} - {""})[:10],
        credibility=0.66,
        metadata={
            "confluence_blog_post_id": post.get("id"),
            "space": {"id": space.get("id"), "key": space.get("key"), "name": space.get("name")},
            "labels": labels,
            "status": post.get("status"),
            "created_date": history.get("createdDate"),
            "updated_date": version.get("when"),
            "version": version.get("number"),
        },
    )


def _labels(post: dict[str, Any]) -> list[str]:
    labels = _dict(_dict(post.get("metadata")).get("labels"))
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


def _optional(value: object) -> str | None:
    return _text(value) or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

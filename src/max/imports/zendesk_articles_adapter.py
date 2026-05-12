"""Zendesk Help Center article import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class ZendeskHelpCenterArticlesAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        base_url: str | None = None,
        email: str | None = None,
        token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        subdomain = _optional(self._config.get("subdomain")) or os.getenv("ZENDESK_SUBDOMAIN")
        self.base_url = (base_url or _optional(self._config.get("base_url")) or (f"https://{subdomain}.zendesk.com" if subdomain else "")).rstrip("/")
        self.email = email if email is not None else (_optional(self._config.get("email")) or os.getenv("ZENDESK_EMAIL"))
        self.token = token if token is not None else (_optional(self._config.get("token")) or os.getenv("ZENDESK_API_TOKEN"))
        self._client = client

    @property
    def name(self) -> str:
        return "zendesk_help_center_articles_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ARTICLE.value

    @property
    def locale(self) -> str:
        return _optional(self._config.get("locale")) or "en-us"

    @property
    def category_id(self) -> str | None:
        return _optional(self._config.get("category_id"))

    @property
    def section_id(self) -> str | None:
        return _optional(self._config.get("section_id"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size"), default=100, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.base_url:
            return []
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            articles: list[dict[str, Any]] = []
            url = self._initial_url()
            params: dict[str, Any] | None = {"per_page": min(self.page_size, limit)}
            while url and len(articles) < limit:
                body = await self._get(client, url, params=params)
                page = body.get("articles") if isinstance(body.get("articles"), list) else []
                articles.extend([item for item in page if isinstance(item, dict)])
                url = _optional(body.get("next_page")) or _optional(((body.get("links") or {}) if isinstance(body.get("links"), dict) else {}).get("next"))
                params = None
                if not page:
                    break
        finally:
            if close_client:
                await client.aclose()
        return [_article_signal(article, self.name) for article in articles[:limit]]

    def _initial_url(self) -> str:
        prefix = f"{self.base_url}/api/v2/help_center/{self.locale}"
        if self.section_id:
            return f"{prefix}/sections/{self.section_id}/articles.json"
        if self.category_id:
            return f"{prefix}/categories/{self.category_id}/articles.json"
        return f"{prefix}/articles.json"

    async def _get(self, client: httpx.AsyncClient, url: str, *, params: dict[str, Any] | None) -> dict[str, Any]:
        try:
            response = await client.get(url, params=params, auth=(f"{self.email}/token", self.token or "") if self.email and self.token else None)
            response.raise_for_status()
            body = response.json()
            return body if isinstance(body, dict) else {}
        except Exception:
            logger.warning("Zendesk Help Center article fetch failed for %s", url, exc_info=True)
            return {}


ZendeskArticlesAdapter = ZendeskHelpCenterArticlesAdapter


def _article_signal(article: dict[str, Any], adapter_name: str) -> Signal:
    labels = [_text(label) for label in article.get("label_names", []) if _text(label)] if isinstance(article.get("label_names"), list) else []
    title = _text(article.get("title")) or _text(article.get("name")) or _text(article.get("id"))
    return Signal(
        id=f"zendesk-article:{_text(article.get('id'))}",
        source_type=SignalSourceType.ARTICLE,
        source_adapter=adapter_name,
        title=title,
        content=(_text(article.get("body")) or _text(article.get("html_body")))[:1000],
        url=_text(article.get("html_url")),
        author=_text(article.get("author_id")) or None,
        published_at=_parse_dt(article.get("created_at")),
        tags=sorted({"zendesk", "help-center", *labels} - {""})[:10],
        credibility=0.6,
        metadata={
            "zendesk_article_id": article.get("id"),
            "section_id": article.get("section_id"),
            "category_id": article.get("category_id"),
            "author_id": article.get("author_id"),
            "locale": article.get("locale"),
            "labels": labels,
            "draft": article.get("draft"),
            "archived": article.get("archived"),
            "promoted": article.get("promoted"),
            "created_at": article.get("created_at"),
            "updated_at": article.get("updated_at"),
            "raw": article,
        },
    )


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _positive_int(value: object, *, default: int, maximum: int) -> int:
    return min(value, maximum) if isinstance(value, int) and not isinstance(value, bool) and value > 0 else default


def _optional(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

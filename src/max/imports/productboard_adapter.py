"""Productboard insight import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
PRODUCTBOARD_API = "https://api.productboard.com"


class ProductboardAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            token
            if token is not None
            else (_optional(self._config.get("token")) or os.getenv("PRODUCTBOARD_API_TOKEN"))
        )
        self.api_url = (
            api_url
            or _optional(self._config.get("api_url") or self._config.get("base_url"))
            or PRODUCTBOARD_API
        ).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "productboard_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def query(self) -> str | None:
        return _optional(self._config.get("query"))

    @property
    def status(self) -> str | None:
        return _optional(self._config.get("status"))

    @property
    def page_size(self) -> int:
        value = self._config.get("page_size")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return min(value, 100)
        return 50

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token:
            return []
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            insights: list[dict[str, Any]] = []
            page_cursor: str | None = None
            while len(insights) < limit:
                body = await self._get_page(client, cursor=page_cursor)
                page = _items(body)
                if not page:
                    break
                insights.extend(page)
                page_cursor = _next_cursor(body)
                if not page_cursor or len(page) < self.page_size:
                    break
        finally:
            if close_client:
                await client.aclose()
        return [
            _insight_signal(item, self.name) for item in insights[:limit] if isinstance(item, dict)
        ]

    async def _get_page(self, client: httpx.AsyncClient, *, cursor: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": self.page_size}
        if cursor:
            params["pageCursor"] = cursor
        if self.query:
            params["query"] = self.query
        if self.status:
            params["status"] = self.status
        try:
            response = await client.get(
                f"{self.api_url}/notes",
                headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Productboard insight fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


ProductboardInsightAdapter = ProductboardAdapter


def _insight_signal(insight: dict[str, Any], adapter_name: str) -> Signal:
    customer = _summary(insight.get("customer"))
    company = _summary(insight.get("company"))
    features = [
        _summary(item) for item in _list_value(insight.get("features")) if isinstance(item, dict)
    ]
    tags = _tag_names(insight.get("tags"))
    source = _text(insight.get("source"))
    content = _text(insight.get("content") or insight.get("description") or insight.get("body"))
    return Signal(
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_text(insight.get("title") or insight.get("name")) or _text(insight.get("id")),
        content=content[:1000],
        url=_text(insight.get("url") or insight.get("html_url")),
        author=customer.get("name") or company.get("name") or None,
        published_at=_parse_dt(insight.get("created_at") or insight.get("createdAt")),
        tags=sorted(
            {"productboard", source, *tags, *[_text(feature.get("name")) for feature in features]}
            - {""}
        )[:10],
        credibility=0.65,
        metadata={
            "productboard_insight_id": insight.get("id"),
            "source": insight.get("source"),
            "customer": customer,
            "company": company,
            "tags": tags,
            "features": features,
            "created_at": insight.get("created_at") or insight.get("createdAt"),
            "updated_at": insight.get("updated_at") or insight.get("updatedAt"),
        },
    )


def _items(body: dict[str, Any]) -> list[dict[str, Any]]:
    data = body.get("data")
    if isinstance(data, list):
        return data
    value = body.get("notes") or body.get("insights")
    return value if isinstance(value, list) else []


def _next_cursor(body: dict[str, Any]) -> str | None:
    links = body.get("links") if isinstance(body.get("links"), dict) else {}
    page = body.get("page") if isinstance(body.get("page"), dict) else {}
    return _optional(body.get("nextPageCursor") or page.get("next") or links.get("next"))


def _summary(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {"id": value.get("id"), "name": value.get("name"), "email": value.get("email")}


def _list_value(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _tag_names(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        name = _text(item.get("name")) if isinstance(item, dict) else _text(item)
        if name:
            names.append(name)
    return names


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _optional(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

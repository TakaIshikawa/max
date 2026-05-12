"""Datadog events import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class DatadogEventsAdapter(SourceAdapter):
    """Fetch Datadog events and convert them to Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        api_key: str | None = None,
        app_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.api_key = api_key if api_key is not None else os.getenv("DATADOG_API_KEY")
        self.app_key = app_key if app_key is not None else os.getenv("DATADOG_APP_KEY")
        self._client = client

    @property
    def name(self) -> str:
        return "datadog_events_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def site(self) -> str:
        return _text(self._config.get("site")) or "datadoghq.com"

    @property
    def base_url(self) -> str:
        configured = _text(self._config.get("base_url"))
        return configured.rstrip("/") if configured else f"https://api.{self.site}".rstrip("/")

    @property
    def query(self) -> str | None:
        return _optional(self._config.get("query"))

    @property
    def tags_filter(self) -> list[str]:
        return _strings(self._config.get("tags"))

    @property
    def configured_limit(self) -> int | None:
        value = self._config.get("limit")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        return None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = min(limit, self.configured_limit) if self.configured_limit else limit
        if effective_limit <= 0 or not (self.api_key and self.app_key):
            return []
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            events = await self._get_events(client, effective_limit)
        finally:
            if close_client:
                await client.aclose()
        return [_event_signal(event, self.name) for event in events[:effective_limit] if isinstance(event, dict)]

    async def _get_events(self, client: httpx.AsyncClient, limit: int) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"unaggregated": "true", "limit": limit}
        if self._config.get("from_ts") is not None:
            params["start"] = self._config["from_ts"]
        if self._config.get("to_ts") is not None:
            params["end"] = self._config["to_ts"]
        query_parts = []
        if self.query:
            query_parts.append(self.query)
        query_parts.extend(f"tags:{tag}" for tag in self.tags_filter)
        if query_parts:
            params["filter"] = " ".join(query_parts)
        headers = {"DD-API-KEY": self.api_key or "", "DD-APPLICATION-KEY": self.app_key or ""}
        try:
            response = await client.get(f"{self.base_url}/api/v1/events", headers=headers, params=params)
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Datadog events fetch failed", exc_info=True)
            return []
        events = body.get("events") if isinstance(body, dict) else None
        return events if isinstance(events, list) else []


DatadogEventAdapter = DatadogEventsAdapter


def _event_signal(event: dict[str, Any], adapter_name: str) -> Signal:
    tags = [_text(tag) for tag in event.get("tags", []) if _text(tag)] if isinstance(event.get("tags"), list) else []
    event_id = _text(event.get("id"))
    alert_type = _text(event.get("alert_type"))
    priority = _text(event.get("priority"))
    return Signal(
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=_text(event.get("title")) or event_id,
        content=_text(event.get("text"))[:1000],
        url=_text(event.get("url")),
        author=_text(event.get("source_type_name")) or None,
        published_at=_timestamp(event.get("date_happened")),
        tags=sorted({"datadog", alert_type, priority, *tags} - {""})[:10],
        credibility=0.7,
        metadata={
            "datadog_event_id": event.get("id"),
            "tags": tags,
            "alert_type": event.get("alert_type"),
            "priority": event.get("priority"),
            "source_type_name": event.get("source_type_name"),
            "host": event.get("host"),
            "aggregation_key": event.get("aggregation_key"),
            "date_happened": event.get("date_happened"),
            "monitor_id": event.get("monitor_id") or event.get("related_event_id"),
            "url": event.get("url"),
        },
    )


def _timestamp(value: object) -> datetime | None:
    try:
        if value in (None, ""):
            return None
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
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

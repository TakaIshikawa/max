"""Datadog downtimes import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class DatadogDowntimesAdapter(SourceAdapter):
    """Fetch Datadog downtimes and convert them to Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        api_key: str | None = None,
        app_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.api_key = api_key if api_key is not None else (
            _optional(self._config.get("api_key")) or os.getenv("DATADOG_API_KEY") or os.getenv("DD_API_KEY")
        )
        self.app_key = app_key if app_key is not None else (
            _optional(self._config.get("app_key"))
            or _optional(self._config.get("application_key"))
            or os.getenv("DATADOG_APP_KEY")
            or os.getenv("DATADOG_APPLICATION_KEY")
            or os.getenv("DD_APPLICATION_KEY")
        )
        self._client = client

    @property
    def name(self) -> str:
        return "datadog_downtimes_import"

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

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = min(limit, _positive_int(self._config.get("limit"), default=limit, maximum=100000))
        if effective_limit <= 0 or not (self.api_key and self.app_key):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            downtimes = await self._get_downtimes(client)
        finally:
            if close_client:
                await client.aclose()
        return [_downtime_signal(item, self.name) for item in downtimes[:effective_limit] if isinstance(item, dict)]

    async def _get_downtimes(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        try:
            response = await client.get(
                f"{self.base_url}/api/v1/downtime",
                headers={"DD-API-KEY": self.api_key or "", "DD-APPLICATION-KEY": self.app_key or ""},
                params=self._params(),
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Datadog downtimes fetch failed", exc_info=True)
            return []
        return body if isinstance(body, list) else []

    def _params(self) -> dict[str, Any]:
        params: dict[str, Any] = {}
        for key in ("current_only", "monitor_id", "scope", "start", "end"):
            value = self._config.get(key)
            if value is None:
                continue
            if key == "scope" and isinstance(value, list | tuple | set):
                params[key] = ",".join(_text(item) for item in value if _text(item))
            else:
                params[key] = bool(value) if key == "current_only" else value
        return params


DatadogDowntimeAdapter = DatadogDowntimesAdapter


def _downtime_signal(downtime: dict[str, Any], adapter_name: str) -> Signal:
    downtime_id = _text(downtime.get("id"))
    message = _text(downtime.get("message")) or f"Datadog downtime {downtime_id}"
    status = _status(downtime)
    scope = _strings(downtime.get("scope"))
    monitor_ids = _monitor_ids(downtime.get("monitor_id") if downtime.get("monitor_id") is not None else downtime.get("monitor_ids"))
    tags = _strings(downtime.get("tags"))
    creator = _person(downtime.get("creator"))
    updater = _person(downtime.get("updater"))
    return Signal(
        id=f"datadog-downtime-{downtime_id}" if downtime_id else "",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"Datadog downtime {downtime_id} {status}".strip(),
        content=message[:1000],
        url=_downtime_url(downtime),
        author=creator.get("handle") or creator.get("name") or creator.get("email"),
        published_at=_timestamp(downtime.get("start") or downtime.get("created")),
        tags=sorted({"datadog", "downtime", status, *scope, *tags} - {""})[:10],
        credibility=0.74,
        metadata={
            "datadog_downtime_id": downtime.get("id"),
            "message": downtime.get("message"),
            "scope": scope,
            "monitor_ids": monitor_ids,
            "monitor_tags": _strings(downtime.get("monitor_tags")),
            "status": status,
            "active": status == "active",
            "canceled": bool(downtime.get("canceled")),
            "disabled": bool(downtime.get("disabled")),
            "start": downtime.get("start"),
            "end": downtime.get("end"),
            "created": downtime.get("created"),
            "modified": downtime.get("modified"),
            "creator": creator,
            "updater": updater,
            "recurrence": downtime.get("recurrence") if isinstance(downtime.get("recurrence"), dict) else downtime.get("recurrence"),
            "tags": tags,
            "url": _downtime_url(downtime),
            "raw": downtime,
        },
    )


def _status(downtime: dict[str, Any]) -> str:
    if downtime.get("canceled"):
        return "canceled"
    if downtime.get("disabled"):
        return "disabled"
    now = int(datetime.now(timezone.utc).timestamp())
    start = _int_or_none(downtime.get("start"))
    end = _int_or_none(downtime.get("end"))
    if start is not None and start > now:
        return "scheduled"
    if end is not None and end <= now:
        return "ended"
    return "active"


def _downtime_url(downtime: dict[str, Any]) -> str:
    explicit = _optional(downtime.get("url"))
    if explicit:
        return explicit
    downtime_id = _optional(downtime.get("id"))
    return f"https://app.datadoghq.com/monitors/downtimes/{downtime_id}" if downtime_id else ""


def _person(value: object) -> dict[str, Any]:
    person = value if isinstance(value, dict) else {}
    return {
        "id": person.get("id"),
        "handle": person.get("handle"),
        "name": person.get("name"),
        "email": person.get("email"),
    }


def _monitor_ids(value: object) -> list[Any]:
    if isinstance(value, list):
        return value[:20]
    if value is None:
        return []
    return [value]


def _timestamp(value: object) -> datetime | None:
    number = _int_or_none(value)
    if number is None:
        return None
    try:
        return datetime.fromtimestamp(number, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        return int(_text(value))
    except (TypeError, ValueError):
        return None


def _positive_int(value: object, *, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number <= 0:
        return default
    return min(number, maximum)


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list | tuple | set):
        return [_text(item) for item in value if _text(item)]
    return []


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

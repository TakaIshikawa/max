"""Datadog monitors import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class DatadogMonitorsAdapter(SourceAdapter):
    """Fetch Datadog monitors and convert them to Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        api_key: str | None = None,
        app_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.api_key = (
            api_key
            if api_key is not None
            else (
                _optional(self._config.get("api_key"))
                or os.getenv("DATADOG_API_KEY")
                or os.getenv("DD_API_KEY")
            )
        )
        self.app_key = (
            app_key
            if app_key is not None
            else (
                _optional(self._config.get("app_key"))
                or _optional(self._config.get("application_key"))
                or os.getenv("DATADOG_APP_KEY")
                or os.getenv("DATADOG_APPLICATION_KEY")
                or os.getenv("DD_APPLICATION_KEY")
            )
        )
        self._client = client

    @property
    def name(self) -> str:
        return "datadog_monitors_import"

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
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size"), default=100, maximum=1000)

    @property
    def configured_limit(self) -> int | None:
        value = self._config.get("limit")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        return None

    @property
    def status_filter(self) -> set[str]:
        return {item.lower() for item in _strings(self._config.get("statuses") or self._config.get("status"))}

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = min(limit, self.configured_limit) if self.configured_limit else limit
        if effective_limit <= 0 or not (self.api_key and self.app_key):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            monitors = await self._get_monitors(client, effective_limit)
        finally:
            if close_client:
                await client.aclose()
        return [_monitor_signal(monitor, self.name) for monitor in monitors[:effective_limit] if isinstance(monitor, dict)]

    async def _get_monitors(self, client: httpx.AsyncClient, limit: int) -> list[dict[str, Any]]:
        monitors: list[dict[str, Any]] = []
        page = 0
        request_size = min(self.page_size, limit)
        while len(monitors) < limit:
            page_monitors = await self._get_monitor_page(client, page=page, page_size=request_size)
            if not page_monitors:
                break
            for monitor in page_monitors:
                if len(monitors) >= limit:
                    break
                if not isinstance(monitor, dict) or not self._matches_status(monitor):
                    continue
                monitors.append(monitor)
            if len(page_monitors) < request_size:
                break
            page += 1
        return monitors[:limit]

    async def _get_monitor_page(
        self,
        client: httpx.AsyncClient,
        *,
        page: int,
        page_size: int,
    ) -> list[dict[str, Any]]:
        params = self._params(page=page, page_size=page_size)
        headers = {"DD-API-KEY": self.api_key or "", "DD-APPLICATION-KEY": self.app_key or ""}
        try:
            response = await client.get(f"{self.base_url}/api/v1/monitor", headers=headers, params=params)
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Datadog monitors fetch failed", exc_info=True)
            return []
        return body if isinstance(body, list) else []

    def _params(self, *, page: int, page_size: int) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        group_states = _optional(self._config.get("group_states"))
        name = _optional(self._config.get("name"))
        tags = _strings(self._config.get("tags"))
        monitor_tags = _strings(self._config.get("monitor_tags"))
        if group_states:
            params["group_states"] = group_states
        if name:
            params["name"] = name
        if tags:
            params["tags"] = ",".join(tags)
        if monitor_tags:
            params["monitor_tags"] = ",".join(monitor_tags)
        if self._config.get("with_downtimes") is not None:
            params["with_downtimes"] = bool(self._config["with_downtimes"])
        return params

    def _matches_status(self, monitor: dict[str, Any]) -> bool:
        if not self.status_filter:
            return True
        status = _text(monitor.get("overall_state") or monitor.get("status")).lower()
        return status in self.status_filter


DatadogMonitorAdapter = DatadogMonitorsAdapter


def _monitor_signal(monitor: dict[str, Any], adapter_name: str) -> Signal:
    monitor_id = _text(monitor.get("id"))
    name = _text(monitor.get("name")) or monitor_id
    message = _text(monitor.get("message"))
    overall_state = _text(monitor.get("overall_state") or monitor.get("status"))
    priority = _text(monitor.get("priority"))
    tags = _strings(monitor.get("tags"))
    monitor_tags = _strings(monitor.get("monitor_tags"))
    datadog_url = _monitor_url(monitor)
    return Signal(
        id=f"datadog-monitor-{monitor_id}" if monitor_id else "",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{name} {overall_state}".strip(),
        content=message[:1000],
        url=datadog_url,
        author=_creator_name(monitor),
        published_at=_timestamp(monitor.get("created")),
        tags=sorted({"datadog", "monitor", overall_state, priority, *tags, *monitor_tags} - {""})[:10],
        credibility=0.75,
        metadata={
            "datadog_monitor_id": monitor.get("id"),
            "name": monitor.get("name"),
            "message": monitor.get("message"),
            "overall_state": monitor.get("overall_state") or monitor.get("status"),
            "priority": monitor.get("priority"),
            "query": monitor.get("query"),
            "type": monitor.get("type"),
            "tags": tags,
            "monitor_tags": monitor_tags,
            "created": monitor.get("created"),
            "modified": monitor.get("modified"),
            "creator": _creator(monitor),
            "options": monitor.get("options") if isinstance(monitor.get("options"), dict) else {},
            "url": datadog_url,
        },
    )


def _monitor_url(monitor: dict[str, Any]) -> str:
    if _optional(monitor.get("url")):
        return _text(monitor.get("url"))
    monitor_id = _optional(monitor.get("id"))
    return f"https://app.datadoghq.com/monitors/{monitor_id}" if monitor_id else ""


def _creator_name(monitor: dict[str, Any]) -> str | None:
    creator = monitor.get("creator")
    if not isinstance(creator, dict):
        return None
    return _optional(creator.get("handle") or creator.get("name") or creator.get("email"))


def _creator(monitor: dict[str, Any]) -> dict[str, Any]:
    creator = monitor.get("creator")
    if not isinstance(creator, dict):
        return {}
    return {
        "id": creator.get("id"),
        "handle": creator.get("handle"),
        "name": creator.get("name"),
        "email": creator.get("email"),
    }


def _timestamp(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _positive_int(value: object, *, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number <= 0:
        return default
    return min(number, maximum)


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

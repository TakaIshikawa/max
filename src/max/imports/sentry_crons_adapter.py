"""Sentry cron monitors import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
SENTRY_API = "https://sentry.io/api/0"


class SentryCronsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        auth_token: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            auth_token
            if auth_token is not None
            else (
                token
                if token is not None
                else (
                    _optional(self._config.get("auth_token"))
                    or _optional(self._config.get("token"))
                    or os.getenv("SENTRY_AUTH_TOKEN")
                )
            )
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or SENTRY_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "sentry_crons_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def organization_slug(self) -> str | None:
        return _optional(self._config.get("organization_slug") or self._config.get("org"))

    @property
    def project_slugs(self) -> list[str]:
        return _strings(
            self._config.get("project_slugs")
            or self._config.get("projects")
            or self._config.get("project_slug")
            or self._config.get("project")
        )

    @property
    def cursor(self) -> str | None:
        return _optional(self._config.get("cursor"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=25, maximum=100)

    @property
    def per_project_limit(self) -> int | None:
        value = self._config.get("per_project_limit")
        if value is None:
            return None
        return _positive_int(value, default=0, maximum=10_000) or None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.organization_slug:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            monitors = await self._fetch_monitors(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        seen: set[str] = set()
        signals: list[Signal] = []
        for monitor in monitors:
            if not isinstance(monitor, dict):
                continue
            monitor_id = _text(monitor.get("id") or monitor.get("slug") or monitor.get("name"))
            if monitor_id and monitor_id in seen:
                continue
            if monitor_id:
                seen.add(monitor_id)
            signals.append(
                _monitor_signal(
                    monitor,
                    organization_slug=self.organization_slug or "",
                    adapter_name=self.name,
                )
            )
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_monitors(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        if self.project_slugs:
            monitors: list[dict[str, Any]] = []
            for project_slug in self.project_slugs:
                if len(monitors) >= limit:
                    break
                project_limit = min(self.per_project_limit or limit, limit - len(monitors))
                monitors.extend(
                    await self._fetch_scope_monitors(
                        client,
                        project_slug=project_slug,
                        cursor=self.cursor,
                        limit=project_limit,
                    )
                )
            return monitors[:limit]
        return await self._fetch_scope_monitors(client, project_slug=None, cursor=self.cursor, limit=limit)

    async def _fetch_scope_monitors(
        self,
        client: httpx.AsyncClient,
        *,
        project_slug: str | None,
        cursor: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        monitors: list[dict[str, Any]] = []
        while len(monitors) < limit:
            page_size = min(self.page_size, limit - len(monitors))
            page_monitors, cursor = await self._fetch_page(
                client,
                project_slug=project_slug,
                cursor=cursor,
                page_size=page_size,
            )
            if not page_monitors:
                break
            monitors.extend(page_monitors[: limit - len(monitors)])
            if not cursor:
                break
        return monitors[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        project_slug: str | None,
        cursor: str | None,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        params: dict[str, Any] = {"per_page": page_size}
        if cursor:
            params["cursor"] = cursor
        if project_slug:
            params["project"] = project_slug
        for source, target in (("query", "query"), ("status", "status"), ("environment", "environment")):
            value = _optional(self._config.get(source))
            if value:
                params[target] = value

        url = f"{self.api_url}/organizations/{quote(self.organization_slug or '', safe='')}/monitors/"
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-sentry-crons-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Sentry crons fetch failed", exc_info=True)
            return [], None

        monitors, body_cursor = _monitors_and_cursor(body)
        return monitors, _next_cursor(response) or body_cursor


SentryCronMonitorsAdapter = SentryCronsAdapter
SentryCronsImportAdapter = SentryCronsAdapter


def _monitor_signal(monitor: dict[str, Any], *, organization_slug: str, adapter_name: str) -> Signal:
    monitor_id = _text(monitor.get("id") or monitor.get("slug") or monitor.get("name"))
    slug = _text(monitor.get("slug"))
    name = _text(monitor.get("name") or monitor.get("displayName") or slug or monitor_id)
    status = _text(monitor.get("status"))
    schedule = _schedule_text(monitor)
    latest_checkin = _latest_checkin(monitor)
    health = _checkin_health(monitor, latest_checkin)
    environment = _environment(monitor, latest_checkin)
    owner = _owner(monitor)
    created_at = monitor.get("dateCreated") or monitor.get("date_created") or monitor.get("createdAt")
    updated_at = monitor.get("dateModified") or monitor.get("date_modified") or monitor.get("updatedAt")
    last_checkin_at = _checkin_timestamp(latest_checkin) or monitor.get("lastCheckIn") or monitor.get("last_checkin")
    next_checkin_at = monitor.get("nextCheckIn") or monitor.get("next_checkin")
    project_slug = _project_slug(monitor)

    return Signal(
        id=f"sentry-cron-monitor:{monitor_id}" if monitor_id else f"sentry-cron-monitor:{slug or name}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=name,
        content=_content(
            name=name,
            status=status,
            schedule=schedule,
            health=health,
            environment=environment,
            owner=owner,
            last_checkin_at=_text(last_checkin_at),
        ),
        url=_monitor_url(monitor, organization_slug=organization_slug, slug=slug or monitor_id),
        author=owner,
        published_at=_parse_dt(last_checkin_at or updated_at or created_at),
        tags=sorted({"sentry", "cron", "monitor", status, health, environment, project_slug} - {""})[:10],
        credibility=0.7,
        metadata={
            "signal_role": "problem",
            "sentry_organization_slug": organization_slug,
            "sentry_monitor_id": monitor.get("id"),
            "sentry_monitor_slug": monitor.get("slug"),
            "sentry_project_slug": project_slug or None,
            "name": name or None,
            "status": status or None,
            "schedule": schedule or None,
            "schedule_config": _schedule_config(monitor),
            "checkin_health": health or None,
            "environment": environment or None,
            "owner": owner or None,
            "date_created": created_at,
            "date_modified": updated_at,
            "last_checkin": last_checkin_at,
            "next_checkin": next_checkin_at,
            "latest_checkin": latest_checkin,
            "url": _monitor_url(monitor, organization_slug=organization_slug, slug=slug or monitor_id),
            "raw": monitor,
        },
    )


def _content(
    *,
    name: str,
    status: str,
    schedule: str,
    health: str,
    environment: str,
    owner: str,
    last_checkin_at: str,
) -> str:
    parts = [f"Sentry cron monitor {name or 'unknown'}"]
    if status:
        parts.append(f"status {status}")
    if schedule:
        parts.append(f"schedule {schedule}")
    if health:
        parts.append(f"check-in health {health}")
    if environment:
        parts.append(f"environment {environment}")
    if owner:
        parts.append(f"owner {owner}")
    if last_checkin_at:
        parts.append(f"last check-in {last_checkin_at}")
    return "; ".join(parts)


def _monitors_and_cursor(body: object) -> tuple[list[dict[str, Any]], str | None]:
    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)], None
    if not isinstance(body, dict):
        return [], None

    items: object = body.get("data") or body.get("results") or body.get("monitors") or body.get("items") or []
    monitors = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    return monitors, _body_cursor(body)


def _body_cursor(body: dict[str, Any]) -> str | None:
    cursor = body.get("cursor")
    if isinstance(cursor, dict):
        if cursor.get("hasMore") is False or cursor.get("has_more") is False:
            return None
        return _optional(cursor.get("next") or cursor.get("nextCursor") or cursor.get("next_cursor"))
    next_value = body.get("next") or body.get("nextCursor") or body.get("next_cursor")
    if isinstance(next_value, dict):
        if next_value.get("results") is False or next_value.get("hasMore") is False or next_value.get("has_more") is False:
            return None
        return _optional(next_value.get("cursor") or next_value.get("next") or next_value.get("url"))
    return _optional(next_value)


def _next_cursor(response: httpx.Response) -> str | None:
    next_link = response.links.get("next") if response.links else None
    if not next_link:
        return None
    if _text(next_link.get("results")).lower() == "false":
        return None
    cursor = _optional(next_link.get("cursor"))
    if cursor:
        return cursor
    next_url = _optional(next_link.get("url"))
    if not next_url:
        return None
    return _optional(str(httpx.URL(next_url).params.get("cursor")))


def _schedule_text(monitor: dict[str, Any]) -> str:
    schedule = monitor.get("schedule")
    if schedule is None:
        schedule = _schedule_config(monitor).get("schedule")
    if isinstance(schedule, list) and len(schedule) >= 2:
        return f"every {schedule[0]} {schedule[1]}"
    if isinstance(schedule, dict):
        return _schedule_from_dict(schedule)
    text = _text(schedule)
    if text:
        return text

    config = _schedule_config(monitor)
    for key in ("crontab", "cron", "rrule"):
        value = _text(config.get(key))
        if value:
            return value
    return _schedule_from_dict(config)


def _schedule_from_dict(value: dict[str, Any]) -> str:
    schedule_type = _text(value.get("type"))
    schedule_value = _text(value.get("value"))
    if schedule_type and schedule_value:
        return f"{schedule_type} {schedule_value}"
    if value.get("interval") and value.get("unit"):
        return f"every {value['interval']} {value['unit']}"
    if value.get("frequency") and value.get("unit"):
        return f"every {value['frequency']} {value['unit']}"
    return _text(value.get("display") or value.get("label"))


def _schedule_config(monitor: dict[str, Any]) -> dict[str, Any]:
    config = monitor.get("config")
    return config if isinstance(config, dict) else {}


def _latest_checkin(monitor: dict[str, Any]) -> dict[str, Any]:
    for key in ("latestCheckIn", "latest_checkin", "lastCheckIn", "last_checkin"):
        value = monitor.get(key)
        if isinstance(value, dict):
            return value
    checkins = monitor.get("checkins")
    if isinstance(checkins, list):
        for checkin in checkins:
            if isinstance(checkin, dict):
                return checkin
    monitor_environment = monitor.get("monitorEnvironment") or monitor.get("monitor_environment")
    if isinstance(monitor_environment, dict):
        last_checkin = monitor_environment.get("lastCheckIn") or monitor_environment.get("last_checkin")
        if isinstance(last_checkin, dict):
            return last_checkin
    return {}


def _checkin_health(monitor: dict[str, Any], latest_checkin: dict[str, Any]) -> str:
    for key in ("status", "health", "checkinStatus", "checkin_status"):
        value = _text(latest_checkin.get(key))
        if value:
            return value
    for key in ("health", "checkinStatus", "checkin_status"):
        value = _text(monitor.get(key))
        if value:
            return value
    monitor_environment = monitor.get("monitorEnvironment") or monitor.get("monitor_environment")
    if isinstance(monitor_environment, dict):
        return _text(monitor_environment.get("status") or monitor_environment.get("health"))
    return _text(monitor.get("lastCheckInStatus") or monitor.get("last_checkin_status"))


def _environment(monitor: dict[str, Any], latest_checkin: dict[str, Any]) -> str:
    for source in (latest_checkin, monitor):
        value = source.get("environment")
        if isinstance(value, dict):
            return _text(value.get("name") or value.get("displayName") or value.get("id"))
        text = _text(value)
        if text:
            return text
    monitor_environment = monitor.get("monitorEnvironment") or monitor.get("monitor_environment")
    if isinstance(monitor_environment, dict):
        return _text(monitor_environment.get("name") or monitor_environment.get("environment"))
    return ""


def _owner(monitor: dict[str, Any]) -> str:
    for key in ("owner", "team", "user"):
        value = monitor.get(key)
        if isinstance(value, dict):
            text = _text(value.get("name") or value.get("username") or value.get("email") or value.get("slug") or value.get("id"))
            if text:
                return text
        text = _text(value)
        if text:
            return text
    return ""


def _checkin_timestamp(checkin: dict[str, Any]) -> object:
    for key in ("dateCreated", "date_created", "createdAt", "dateUpdated", "date_updated"):
        value = checkin.get(key)
        if value:
            return value
    return None


def _project_slug(monitor: dict[str, Any]) -> str:
    project = monitor.get("project")
    if isinstance(project, dict):
        return _text(project.get("slug") or project.get("id") or project.get("name"))
    return _text(project or monitor.get("projectSlug") or monitor.get("project_slug"))


def _monitor_url(monitor: dict[str, Any], *, organization_slug: str, slug: str) -> str:
    links = monitor.get("links")
    if isinstance(links, dict):
        for key in ("html", "url"):
            value = _text(links.get(key))
            if value:
                return value
    for key in ("url", "permalink"):
        value = _text(monitor.get(key))
        if value:
            return value
    if not organization_slug or not slug:
        return ""
    return f"https://sentry.io/organizations/{organization_slug}/crons/{quote(slug, safe='')}/"


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
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
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        value = [value]
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, bool):
            continue
        if isinstance(item, dict):
            item = item.get("slug") or item.get("id") or item.get("name")
        text = _text(item)
        if text and text not in seen:
            seen.add(text)
            strings.append(text)
    return strings


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

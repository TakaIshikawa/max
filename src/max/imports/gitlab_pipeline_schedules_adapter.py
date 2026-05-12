"""GitLab pipeline schedules import adapter."""

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
GITLAB_API = "https://gitlab.com/api/v4"


class GitLabPipelineSchedulesAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        project_id: str | None = None,
        api_url: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = token if token is not None else (_optional(self._config.get("token")) or os.getenv("GITLAB_TOKEN"))
        self.project_id = project_id if project_id is not None else (
            _optional(self._config.get("project_id"))
            or _optional(self._config.get("project_path"))
            or os.getenv("GITLAB_PROJECT_ID")
            or os.getenv("GITLAB_PROJECT_PATH")
        )
        configured_url = api_url or base_url or _optional(self._config.get("api_url")) or _optional(self._config.get("base_url")) or os.getenv("GITLAB_API_URL") or GITLAB_API
        self.api_url = configured_url.rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "gitlab_pipeline_schedules_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.project_id:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            schedules = await self._fetch_schedules(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        for schedule in schedules:
            if not isinstance(schedule, dict):
                continue
            signals.append(_schedule_signal(schedule, self.project_id, self.name))
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_schedules(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        schedules: list[dict[str, Any]] = []
        page = 1
        while len(schedules) < limit:
            page_size = min(self.per_page, limit - len(schedules))
            body = await self._get(client, page=page, per_page=page_size)
            if not isinstance(body, list) or not body:
                break
            schedules.extend(item for item in body if isinstance(item, dict))
            if len(body) < page_size:
                break
            page += 1
        return schedules[:limit]

    async def _get(self, client: httpx.AsyncClient, *, page: int, per_page: int) -> object:
        try:
            response = await client.get(
                self._endpoint,
                params=self._params(page=page, per_page=per_page),
                headers={
                    "PRIVATE-TOKEN": self.token or "",
                    "Accept": "application/json",
                    "User-Agent": "max-gitlab-pipeline-schedules-import/1",
                },
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.warning("GitLab pipeline schedules fetch failed for %s", self._endpoint, exc_info=True)
            return []

    @property
    def _endpoint(self) -> str:
        project = quote(self.project_id or "", safe="")
        return f"{self.api_url}/projects/{project}/pipeline_schedules"

    def _params(self, *, page: int, per_page: int) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        for key in ("scope", "ref", "owner"):
            value = _optional(self._config.get(key))
            if value:
                params[key] = value
        active = self._config.get("active")
        if active is not None:
            params["active"] = bool(active)
        return params


GitLabPipelineScheduleAdapter = GitLabPipelineSchedulesAdapter


def _schedule_signal(schedule: dict[str, Any], project_id: str, adapter_name: str) -> Signal:
    schedule_id = _text(schedule.get("id"))
    description = _text(schedule.get("description")) or schedule_id or "GitLab pipeline schedule"
    ref = _text(schedule.get("ref"))
    active = schedule.get("active")
    owner = schedule.get("owner") if isinstance(schedule.get("owner"), dict) else {}
    status = "active" if active is True else "inactive" if active is False else ""
    web_url = _text(schedule.get("web_url"))
    return Signal(
        id=f"gitlab-pipeline-schedule:{project_id}:{schedule_id}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{description} {status}".strip(),
        content=_content(description=description, ref=ref, cron=_text(schedule.get("cron")), active=active),
        url=web_url,
        author=_text(owner.get("username") or owner.get("name")) or None,
        published_at=_parse_dt(schedule.get("created_at") or schedule.get("updated_at") or schedule.get("next_run_at")),
        tags=sorted({"gitlab", "pipeline-schedule", status, ref} - {""})[:10],
        credibility=0.7,
        metadata={
            "gitlab_pipeline_schedule_id": schedule.get("id"),
            "project_id": project_id,
            "description": schedule.get("description"),
            "ref": schedule.get("ref"),
            "cron": schedule.get("cron"),
            "cron_timezone": schedule.get("cron_timezone"),
            "active": active,
            "next_run_at": schedule.get("next_run_at"),
            "owner": _summary(owner, ("id", "username", "name", "state", "web_url", "avatar_url")),
            "created_at": schedule.get("created_at"),
            "updated_at": schedule.get("updated_at"),
            "web_url": schedule.get("web_url"),
            "raw": schedule,
        },
    )


def _content(*, description: str, ref: str, cron: str, active: object) -> str:
    parts = [f"GitLab pipeline schedule {description}"]
    if ref:
        parts.append(f"ref {ref}")
    if cron:
        parts.append(f"cron {cron}")
    if active is not None:
        parts.append("active" if bool(active) else "inactive")
    return "; ".join(parts)


def _summary(value: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: value.get(key) for key in keys if value.get(key) is not None}


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


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

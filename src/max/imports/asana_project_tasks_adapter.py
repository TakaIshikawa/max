"""Asana project tasks import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
ASANA_API = "https://app.asana.com/api/1.0"
DEFAULT_OPT_FIELDS = ",".join(
    [
        "gid",
        "name",
        "notes",
        "completed",
        "completed_at",
        "created_at",
        "modified_at",
        "due_on",
        "due_at",
        "permalink_url",
        "assignee.gid",
        "assignee.name",
        "memberships.section.gid",
        "memberships.section.name",
        "tags.name",
        "custom_fields.name",
        "custom_fields.display_value",
    ]
)


class AsanaProjectTasksAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        access_token: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = access_token if access_token is not None else (
            token
            if token is not None
            else (
                _optional(self._config.get("access_token"))
                or _optional(self._config.get("token"))
                or os.getenv("ASANA_ACCESS_TOKEN")
            )
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or ASANA_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "asana_project_tasks_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def project_gids(self) -> list[str]:
        return _strings(
            self._config.get("project_gids")
            or self._config.get("project_ids")
            or self._config.get("projects")
            or self._config.get("project_gid")
            or self._config.get("project_id")
        )

    @property
    def completed_since(self) -> str | None:
        return _optional(self._config.get("completed_since"))

    @property
    def modified_since(self) -> str | None:
        return _optional(self._config.get("modified_since"))

    @property
    def sections(self) -> set[str]:
        return {section.lower() for section in _strings(self._config.get("sections") or self._config.get("section"))}

    @property
    def assignees(self) -> set[str]:
        return {assignee.lower() for assignee in _strings(self._config.get("assignees") or self._config.get("assignee"))}

    @property
    def opt_fields(self) -> str:
        fields = _strings(self._config.get("opt_fields"))
        return ",".join(fields) if fields else DEFAULT_OPT_FIELDS

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("limit"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.project_gids:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            seen: set[str] = set()
            for project_gid in self.project_gids:
                if len(signals) >= limit:
                    break
                tasks = await self._fetch_project_tasks(
                    client,
                    project_gid=project_gid,
                    limit=limit - len(signals),
                )
                for task in tasks:
                    signal = _task_signal(task, project_gid=project_gid, adapter_name=self.name, seen=seen)
                    if signal:
                        signals.append(signal)
                    if len(signals) >= limit:
                        break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_project_tasks(
        self,
        client: httpx.AsyncClient,
        *,
        project_gid: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        offset: str | None = None
        while len(tasks) < limit:
            page_size = min(self.page_size, limit - len(tasks))
            page_tasks, offset = await self._fetch_page(
                client,
                project_gid=project_gid,
                offset=offset,
                page_size=page_size,
            )
            if not page_tasks:
                break
            for item in page_tasks:
                if self._matches_filters(item):
                    tasks.append(item)
                if len(tasks) >= limit:
                    break
            if not offset or len(page_tasks) < page_size:
                break
        return tasks[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        project_gid: str,
        offset: str | None,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        params: dict[str, Any] = {"limit": page_size, "opt_fields": self.opt_fields}
        if offset:
            params["offset"] = offset
        if self.completed_since:
            params["completed_since"] = self.completed_since
        if self.modified_since:
            params["modified_since"] = self.modified_since
        try:
            response = await client.get(
                f"{self.api_url}/projects/{project_gid}/tasks",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-asana-project-tasks-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Asana project tasks fetch failed for project %s", project_gid, exc_info=True)
            return [], None
        data = body.get("data") if isinstance(body, dict) else None
        tasks = [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
        return tasks, _next_offset(body)

    def _matches_filters(self, task: dict[str, Any]) -> bool:
        if self.assignees:
            assignee = task.get("assignee") if isinstance(task.get("assignee"), dict) else {}
            values = {_text(assignee.get("gid")).lower(), _text(assignee.get("name")).lower()} - {""}
            if not values.intersection(self.assignees):
                return False
        if self.sections:
            values = {section.lower() for section in _section_names(task)}
            if not values.intersection(self.sections):
                return False
        return True


AsanaProjectTaskAdapter = AsanaProjectTasksAdapter


def _task_signal(
    task: dict[str, Any],
    *,
    project_gid: str,
    adapter_name: str,
    seen: set[str],
) -> Signal | None:
    task_gid = _optional(task.get("gid"))
    if not task_gid:
        return None
    external_id = f"asana-project-task:{project_gid}:{task_gid}"
    if external_id in seen:
        return None
    seen.add(external_id)

    assignee = task.get("assignee") if isinstance(task.get("assignee"), dict) else {}
    tag_names = [_text(tag.get("name")) for tag in task.get("tags", []) if isinstance(tag, dict) and _text(tag.get("name"))]
    custom_fields = {
        field.get("name"): field.get("display_value")
        for field in task.get("custom_fields", [])
        if isinstance(field, dict) and field.get("name")
    }
    section_names = _section_names(task)
    completed = bool(task.get("completed"))
    return Signal(
        id=external_id,
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_text(task.get("name")) or task_gid,
        content=_text(task.get("notes"))[:1000],
        url=_text(task.get("permalink_url")),
        author=_optional(assignee.get("name")),
        published_at=_parse_dt(task.get("created_at")),
        tags=sorted({"asana", "task", "completed" if completed else "open", *tag_names, *section_names} - {""})[:10],
        credibility=0.6,
        metadata={
            "asana_project_gid": project_gid,
            "asana_task_gid": task.get("gid"),
            "name": task.get("name"),
            "notes": task.get("notes"),
            "completed": completed,
            "completed_at": task.get("completed_at"),
            "assignee": {
                "gid": assignee.get("gid"),
                "name": assignee.get("name"),
            },
            "sections": section_names,
            "tags": tag_names,
            "due_on": task.get("due_on"),
            "due_at": task.get("due_at"),
            "custom_fields": custom_fields,
            "created_at": task.get("created_at"),
            "modified_at": task.get("modified_at"),
            "permalink_url": task.get("permalink_url"),
            "raw": task,
        },
    )


def _section_names(task: dict[str, Any]) -> list[str]:
    memberships = task.get("memberships") if isinstance(task.get("memberships"), list) else []
    names: list[str] = []
    for membership in memberships:
        if not isinstance(membership, dict):
            continue
        section = membership.get("section") if isinstance(membership.get("section"), dict) else {}
        name = _text(section.get("name") or section.get("gid"))
        if name:
            names.append(name)
    return names


def _next_offset(body: object) -> str | None:
    if not isinstance(body, dict):
        return None
    next_page = body.get("next_page")
    if not isinstance(next_page, dict):
        return None
    return _optional(next_page.get("offset"))


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
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

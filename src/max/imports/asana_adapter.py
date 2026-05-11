"""Asana task import adapter."""

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


class AsanaAdapter(SourceAdapter):
    def __init__(self, config: dict | None = None, *, token: str | None = None, api_url: str = ASANA_API, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(config)
        self.token = token if token is not None else os.getenv("ASANA_ACCESS_TOKEN")
        self.api_url = api_url.rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "asana_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def project_ids(self) -> list[str]:
        return _strings(self._config.get("project_ids"))

    @property
    def workspace_ids(self) -> list[str]:
        return _strings(self._config.get("workspace_ids"))

    @property
    def completed(self) -> bool | None:
        value = self._config.get("completed")
        return value if isinstance(value, bool) else None

    @property
    def tags(self) -> list[str]:
        return _strings(self._config.get("tags"))

    @property
    def modified_since(self) -> str | None:
        value = self._config.get("modified_since")
        return value if isinstance(value, str) and value else None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token:
            return []
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            tasks: list[dict[str, Any]] = []
            for project_id in self.project_ids:
                tasks.extend(await self._get_tasks(client, "/tasks", {"project": project_id}))
            for workspace_id in self.workspace_ids:
                tasks.extend(await self._get_tasks(client, "/tasks", {"workspace": workspace_id}))
        finally:
            if close_client:
                await client.aclose()

        seen: set[str] = set()
        signals: list[Signal] = []
        for task in tasks:
            gid = _text(task.get("gid"))
            if not gid or gid in seen:
                continue
            seen.add(gid)
            if self.completed is not None and bool(task.get("completed")) != self.completed:
                continue
            tag_names = [_text(tag.get("name")) for tag in task.get("tags", []) if isinstance(tag, dict)]
            if self.tags and not set(self.tags).intersection(tag_names):
                continue
            signals.append(_task_signal(task, self.name, tag_names))
            if len(signals) >= limit:
                break
        return signals

    async def _get_tasks(self, client: httpx.AsyncClient, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        params = {**params, "limit": 100, "opt_fields": "gid,name,notes,completed,assignee.name,tags.name,due_on,permalink_url,custom_fields.name,custom_fields.display_value,modified_at,created_at"}
        if self.modified_since:
            params["modified_since"] = self.modified_since
        try:
            response = await client.get(f"{self.api_url}{path}", headers={"Authorization": f"Bearer {self.token}"}, params=params)
            response.raise_for_status()
            data = response.json()
        except Exception:
            logger.warning("Asana task fetch failed", exc_info=True)
            return []
        return data.get("data") if isinstance(data.get("data"), list) else []


AsanaTaskAdapter = AsanaAdapter


def _task_signal(task: dict[str, Any], adapter_name: str, tag_names: list[str]) -> Signal:
    assignee = task.get("assignee") if isinstance(task.get("assignee"), dict) else {}
    custom_fields = {field.get("name"): field.get("display_value") for field in task.get("custom_fields", []) if isinstance(field, dict)}
    return Signal(
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_text(task.get("name")) or _text(task.get("gid")),
        content=_text(task.get("notes"))[:1000],
        url=_text(task.get("permalink_url")),
        author=_text(assignee.get("name")) or None,
        published_at=_parse_dt(task.get("created_at")),
        tags=sorted({"asana", *tag_names} - {""})[:10],
        credibility=0.6,
        metadata={"asana_task_id": task.get("gid"), "completed": bool(task.get("completed")), "assignee": assignee.get("name"), "tags": tag_names, "due_on": task.get("due_on"), "custom_fields": custom_fields, "modified_at": task.get("modified_at")},
    )


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

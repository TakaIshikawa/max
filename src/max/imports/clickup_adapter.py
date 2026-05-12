"""ClickUp task import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
CLICKUP_API = "https://api.clickup.com/api/v2"


class ClickUpAdapter(SourceAdapter):
    """Fetch ClickUp tasks and convert them to Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str = CLICKUP_API,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = token if token is not None else os.getenv("CLICKUP_API_TOKEN")
        self.api_url = api_url.rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "clickup_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def list_id(self) -> str | None:
        return _optional(self._config.get("list_id"))

    @property
    def statuses(self) -> list[str]:
        return _strings(self._config.get("statuses"))

    @property
    def page_size(self) -> int:
        value = self._config.get("page_size")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return min(value, 100)
        return 100

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.token and self.list_id):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            tasks: list[dict[str, Any]] = []
            page = 0
            while len(tasks) < limit:
                page_tasks = await self._get_page(client, page=page)
                if not page_tasks:
                    break
                tasks.extend(page_tasks)
                if len(page_tasks) < self.page_size:
                    break
                page += 1
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        allowed_statuses = {status.lower() for status in self.statuses}
        for task in tasks:
            if not isinstance(task, dict):
                continue
            task_id = _text(task.get("id"))
            if not task_id or task_id in seen:
                continue
            seen.add(task_id)
            status = _status(task)
            if allowed_statuses and status.lower() not in allowed_statuses:
                continue
            signals.append(_task_signal(task, self.name, self.list_id, status))
            if len(signals) >= limit:
                break
        return signals

    async def _get_page(self, client: httpx.AsyncClient, *, page: int) -> list[dict[str, Any]]:
        try:
            response = await client.get(
                f"{self.api_url}/list/{self.list_id}/task",
                headers={"Authorization": self.token or ""},
                params={"page": page, "limit": self.page_size, "include_closed": "true"},
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("ClickUp task fetch failed", exc_info=True)
            return []
        return body.get("tasks") if isinstance(body.get("tasks"), list) else []


ClickUpTaskAdapter = ClickUpAdapter


def _task_signal(task: dict[str, Any], adapter_name: str, list_id: str | None, status: str) -> Signal:
    assignees = _assignees(task.get("assignees"))
    priority = task.get("priority") if isinstance(task.get("priority"), dict) else {}
    tag_names = [_text(tag.get("name")) for tag in task.get("tags", []) if isinstance(tag, dict)]
    tag_names = [tag for tag in tag_names if tag]
    due_date = _timestamp_ms(task.get("due_date"))
    date_created = _timestamp_ms(task.get("date_created"))
    custom_fields = _custom_fields(task.get("custom_fields"))
    return Signal(
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_text(task.get("name")) or _text(task.get("id")),
        content=(_text(task.get("description")) or _text(task.get("text_content")))[:1000],
        url=_text(task.get("url")),
        author=assignees[0].get("username") if assignees else None,
        published_at=date_created,
        tags=sorted({"clickup", status, *tag_names} - {""})[:10],
        credibility=0.6,
        metadata={
            "clickup_task_id": task.get("id"),
            "list_id": list_id,
            "status": status or None,
            "priority": priority.get("priority") or priority.get("name"),
            "priority_id": priority.get("id"),
            "assignees": assignees,
            "due_date": task.get("due_date"),
            "due_at": due_date.isoformat() if due_date else None,
            "date_created": task.get("date_created"),
            "created_at": date_created.isoformat() if date_created else None,
            "tags": tag_names,
            "custom_fields": custom_fields,
        },
    )


def _assignees(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    assignees: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            assignees.append({"id": item.get("id"), "username": item.get("username") or item.get("name"), "email": item.get("email")})
    return assignees


def _custom_fields(value: object) -> dict[str, Any]:
    if not isinstance(value, list):
        return {}
    fields: dict[str, Any] = {}
    for field in value:
        if not isinstance(field, dict):
            continue
        name = _text(field.get("name") or field.get("id"))
        if name:
            fields[name] = field.get("value")
    return fields


def _status(task: dict[str, Any]) -> str:
    status = task.get("status")
    if isinstance(status, dict):
        return _text(status.get("status") or status.get("name"))
    return _text(status)


def _timestamp_ms(value: object) -> datetime | None:
    try:
        if value in (None, ""):
            return None
        return datetime.fromtimestamp(int(str(value)) / 1000)
    except (TypeError, ValueError, OSError):
        return None


def _optional(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

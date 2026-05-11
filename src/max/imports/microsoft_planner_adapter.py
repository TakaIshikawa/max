"""Microsoft Planner task import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
GRAPH_API = "https://graph.microsoft.com/v1.0"


class MicrosoftPlannerAdapter(SourceAdapter):
    def __init__(self, config: dict | None = None, *, token: str | None = None, api_url: str = GRAPH_API, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(config)
        self.token = token if token is not None else (os.getenv("MICROSOFT_GRAPH_TOKEN") or os.getenv("PLANNER_ACCESS_TOKEN"))
        self.api_url = api_url.rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "microsoft_planner_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def plan_ids(self) -> list[str]:
        return _strings(self._config.get("plan_ids"))

    @property
    def bucket_ids(self) -> list[str]:
        return _strings(self._config.get("bucket_ids"))

    @property
    def include_completed(self) -> bool:
        return bool(self._config.get("include_completed", False))

    @property
    def updated_since(self) -> str | None:
        value = self._config.get("updated_since")
        return value if isinstance(value, str) and value else None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token:
            return []
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            tasks: list[dict[str, Any]] = []
            for plan_id in self.plan_ids:
                tasks.extend(await self._get_plan_tasks(client, plan_id))
        finally:
            if close_client:
                await client.aclose()
        seen: set[str] = set()
        signals: list[Signal] = []
        for task in tasks:
            task_id = _text(task.get("id"))
            if not task_id or task_id in seen:
                continue
            seen.add(task_id)
            if self.updated_since and _text(task.get("lastModifiedDateTime")) < self.updated_since:
                continue
            if self.bucket_ids and task.get("bucketId") not in self.bucket_ids:
                continue
            if not self.include_completed and int(task.get("percentComplete") or 0) >= 100:
                continue
            signals.append(_planner_signal(task, self.name))
            if len(signals) >= limit:
                break
        return signals

    async def _get_plan_tasks(self, client: httpx.AsyncClient, plan_id: str) -> list[dict[str, Any]]:
        try:
            response = await client.get(f"{self.api_url}/planner/plans/{plan_id}/tasks", headers={"Authorization": f"Bearer {self.token}"})
            response.raise_for_status()
            data = response.json()
        except Exception:
            logger.warning("Microsoft Planner task fetch failed for plan %s", plan_id, exc_info=True)
            return []
        return data.get("value") if isinstance(data.get("value"), list) else []


MicrosoftPlannerTaskAdapter = MicrosoftPlannerAdapter


def _planner_signal(task: dict[str, Any], adapter_name: str) -> Signal:
    assignments = list((task.get("assignments") or {}).keys()) if isinstance(task.get("assignments"), dict) else []
    return Signal(
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_text(task.get("title")) or _text(task.get("id")),
        content=f"Planner task {_text(task.get('id'))}",
        url=_text(task.get("webUrl")),
        author=", ".join(assignments) or None,
        published_at=_parse_dt(task.get("createdDateTime")),
        tags=sorted({"planner", _text(task.get("bucketId")), _text(task.get("planId"))} - {""})[:10],
        credibility=0.6,
        metadata={"planner_task_id": task.get("id"), "percent_complete": task.get("percentComplete"), "priority": task.get("priority"), "due_date": task.get("dueDateTime"), "start_date": task.get("startDateTime"), "completed_at": task.get("completedDateTime"), "assignments": assignments, "bucket_id": task.get("bucketId"), "plan_id": task.get("planId"), "updated_at": task.get("lastModifiedDateTime")},
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

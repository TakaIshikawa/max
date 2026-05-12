"""Azure DevOps work item import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class AzureDevOpsWorkItemsAdapter(SourceAdapter):
    """Run WIQL and import Azure DevOps work items as Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        organization: str | None = None,
        project: str | None = None,
        personal_access_token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.organization = organization or _optional(self._config.get("organization")) or os.getenv("AZURE_DEVOPS_ORGANIZATION") or ""
        self.project = project or _optional(self._config.get("project")) or os.getenv("AZURE_DEVOPS_PROJECT") or ""
        self.personal_access_token = personal_access_token if personal_access_token is not None else os.getenv("AZURE_DEVOPS_PAT")
        self._client = client

    @property
    def name(self) -> str:
        return "azure_devops_work_items_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def api_version(self) -> str:
        return _text(self._config.get("api_version")) or "7.1"

    @property
    def wiql(self) -> str:
        return _text(self._config.get("wiql")) or "SELECT [System.Id] FROM WorkItems ORDER BY [System.ChangedDate] DESC"

    @property
    def configured_limit(self) -> int | None:
        value = self._config.get("limit")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        return None

    @property
    def base_url(self) -> str:
        return f"https://dev.azure.com/{self.organization}/{self.project}".rstrip("/")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = min(limit, self.configured_limit) if self.configured_limit else limit
        if effective_limit <= 0 or not (self.organization and self.project and self.personal_access_token):
            return []
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            ids = await self._query_ids(client, effective_limit)
            items = await self._fetch_items(client, ids[:effective_limit])
        finally:
            if close_client:
                await client.aclose()
        return [_work_item_signal(item, self.name, self.organization, self.project) for item in items[:effective_limit] if isinstance(item, dict)]

    async def _query_ids(self, client: httpx.AsyncClient, limit: int) -> list[int]:
        try:
            response = await client.post(
                f"{self.base_url}/_apis/wit/wiql",
                auth=("", self.personal_access_token or ""),
                params={"api-version": self.api_version},
                json={"query": self.wiql},
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Azure DevOps WIQL fetch failed", exc_info=True)
            return []
        refs = body.get("workItems") if isinstance(body, dict) else None
        ids = [_int(item.get("id")) for item in refs if isinstance(item, dict)] if isinstance(refs, list) else []
        return [item_id for item_id in ids if item_id][:limit]

    async def _fetch_items(self, client: httpx.AsyncClient, ids: list[int]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for offset in range(0, len(ids), 200):
            batch_ids = ids[offset : offset + 200]
            try:
                response = await client.post(
                    f"{self.base_url}/_apis/wit/workitemsbatch",
                    auth=("", self.personal_access_token or ""),
                    params={"api-version": self.api_version},
                    json={"ids": batch_ids, "$expand": "Relations"},
                )
                response.raise_for_status()
                body = response.json()
            except Exception:
                logger.warning("Azure DevOps work item batch fetch failed", exc_info=True)
                return items
            values = body.get("value") if isinstance(body, dict) else None
            if isinstance(values, list):
                items.extend(item for item in values if isinstance(item, dict))
        return items


AzureDevOpsWorkItemAdapter = AzureDevOpsWorkItemsAdapter


def _work_item_signal(item: dict[str, Any], adapter_name: str, organization: str, project: str) -> Signal:
    fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
    item_id = _text(item.get("id"))
    links = item.get("_links") if isinstance(item.get("_links"), dict) else {}
    html = links.get("html") if isinstance(links.get("html"), dict) else {}
    url = _text(html.get("href")) or f"https://dev.azure.com/{organization}/{project}/_workitems/edit/{item_id}"
    assigned_to = _identity(fields.get("System.AssignedTo"))
    created_by = _identity(fields.get("System.CreatedBy"))
    tags = [_text(tag) for tag in _text(fields.get("System.Tags")).split(";") if _text(tag)]
    return Signal(
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_text(fields.get("System.Title")) or item_id,
        content=_text(fields.get("System.Description"))[:1000],
        url=url,
        author=created_by.get("displayName"),
        published_at=_parse_dt(fields.get("System.CreatedDate")),
        tags=sorted({"azure-devops", _text(fields.get("System.State")), _text(fields.get("System.WorkItemType")), *tags} - {""})[:10],
        credibility=0.7,
        metadata={
            "azure_devops_work_item_id": item.get("id"),
            "title": fields.get("System.Title"),
            "state": fields.get("System.State"),
            "reason": fields.get("System.Reason"),
            "work_item_type": fields.get("System.WorkItemType"),
            "assigned_to": assigned_to,
            "created_by": created_by,
            "tags": tags,
            "area_path": fields.get("System.AreaPath"),
            "iteration_path": fields.get("System.IterationPath"),
            "created_date": fields.get("System.CreatedDate"),
            "changed_date": fields.get("System.ChangedDate"),
            "web_url": url,
            "relations": item.get("relations") if isinstance(item.get("relations"), list) else [],
        },
    )


def _identity(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return {"displayName": value.get("displayName"), "uniqueName": value.get("uniqueName"), "id": value.get("id")}
    text = _text(value)
    return {"displayName": text, "uniqueName": None, "id": None} if text else {}


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

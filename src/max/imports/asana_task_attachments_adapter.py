"""Asana task attachments import adapter."""

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
OPT_FIELDS = ",".join(
    [
        "gid",
        "name",
        "resource_type",
        "resource_subtype",
        "created_at",
        "download_url",
        "permanent_url",
        "view_url",
        "host",
        "parent.gid",
        "parent.name",
    ]
)


class AsanaTaskAttachmentsAdapter(SourceAdapter):
    """Import Asana task attachments as evidence signals."""

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
        self.token = (
            access_token
            if access_token is not None
            else (
                token
                if token is not None
                else (
                    _optional(self._config.get("access_token"))
                    or _optional(self._config.get("token"))
                    or os.getenv("ASANA_ACCESS_TOKEN")
                )
            )
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or ASANA_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "asana_task_attachments_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def task_gids(self) -> list[str]:
        return _task_gids(
            self._config.get("task_gids")
            or self._config.get("tasks")
            or self._config.get("task_gid")
        )

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("limit"), default=30, maximum=100)

    @property
    def per_task_limit(self) -> int | None:
        value = self._config.get("per_task_limit")
        if value is None:
            return None
        return _positive_int(value, default=0, maximum=10_000) or None

    @property
    def opt_fields(self) -> str:
        fields = self._config.get("opt_fields")
        if isinstance(fields, list):
            return ",".join(_strings(fields)) or OPT_FIELDS
        return _optional(fields) or OPT_FIELDS

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.task_gids:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            seen_attachment_ids: set[str] = set()
            for task_gid in self.task_gids:
                if len(signals) >= limit:
                    break
                task_limit = min(self.per_task_limit or limit, limit)
                attachments = await self._fetch_task_attachments(client, task_gid=task_gid, limit=task_limit)
                for attachment in attachments:
                    attachment_id = _optional(attachment.get("gid"))
                    if not attachment_id or attachment_id in seen_attachment_ids:
                        continue
                    seen_attachment_ids.add(attachment_id)
                    signals.append(_attachment_signal(attachment, task_gid=task_gid, adapter_name=self.name))
                    if len(signals) >= limit:
                        break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_task_attachments(
        self,
        client: httpx.AsyncClient,
        *,
        task_gid: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        attachments: list[dict[str, Any]] = []
        offset: str | None = None
        while len(attachments) < limit:
            page_size = min(self.page_size, limit - len(attachments))
            page_attachments, offset = await self._fetch_page(
                client,
                task_gid=task_gid,
                offset=offset,
                page_size=page_size,
            )
            if not page_attachments:
                break
            attachments.extend(page_attachments[: limit - len(attachments)])
            if not offset or len(page_attachments) < page_size:
                break
        return attachments[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        task_gid: str,
        offset: str | None,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        params: dict[str, Any] = {"limit": page_size, "opt_fields": self.opt_fields}
        if offset:
            params["offset"] = offset
        url = f"{self.api_url}/tasks/{task_gid}/attachments"
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-asana-task-attachments-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Asana task attachments fetch failed for task %s", task_gid, exc_info=True)
            return [], None
        data = body.get("data") if isinstance(body, dict) else None
        attachments = [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
        return attachments, _next_offset(body)


AsanaTaskAttachmentAdapter = AsanaTaskAttachmentsAdapter


def _attachment_signal(attachment: dict[str, Any], *, task_gid: str, adapter_name: str) -> Signal:
    attachment_gid = _text(attachment.get("gid"))
    name = _text(attachment.get("name")) or attachment_gid or "Asana attachment"
    parent = attachment.get("parent") if isinstance(attachment.get("parent"), dict) else {}
    parent_gid = _text(parent.get("gid")) or task_gid
    resource_subtype = _text(attachment.get("resource_subtype"))
    host = _text(attachment.get("host"))
    url = _text(attachment.get("permanent_url") or attachment.get("view_url") or attachment.get("download_url"))
    return Signal(
        id=f"asana-task-attachment:{parent_gid}:{attachment_gid}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"Asana attachment {name}",
        content=_content(name=name, resource_subtype=resource_subtype, host=host),
        url=url,
        author=None,
        published_at=_parse_dt(attachment.get("created_at")),
        tags=sorted({"asana", "task-attachment", resource_subtype, host} - {""})[:10],
        credibility=0.6,
        metadata={
            "asana_task_gid": task_gid,
            "parent_task_gid": parent_gid,
            "parent_task": {"gid": parent.get("gid"), "name": parent.get("name")},
            "asana_attachment_gid": attachment.get("gid"),
            "attachment_gid": attachment.get("gid"),
            "name": attachment.get("name"),
            "resource_type": attachment.get("resource_type"),
            "resource_subtype": attachment.get("resource_subtype"),
            "permanent_url": attachment.get("permanent_url"),
            "download_url": attachment.get("download_url"),
            "view_url": attachment.get("view_url"),
            "host": attachment.get("host"),
            "created_at": attachment.get("created_at"),
            "raw": attachment,
        },
    )


def _content(*, name: str, resource_subtype: str, host: str) -> str:
    parts = [f"Asana task attachment {name}"]
    if resource_subtype:
        parts.append(resource_subtype.replace("_", " "))
    if host:
        parts.append(f"host {host}")
    return "; ".join(parts)


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
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        value = [value]
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    for item in value:
        if isinstance(item, bool):
            continue
        text = _text(item)
        if text:
            strings.append(text)
    return strings


def _task_gids(value: object) -> list[str]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    gids: list[str] = []
    for item in value:
        if isinstance(item, dict):
            gid = _text(item.get("gid") or item.get("task_gid") or item.get("id"))
        else:
            gid = _text(item)
        if gid:
            gids.append(gid)
    return gids


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

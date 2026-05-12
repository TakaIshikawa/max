"""Asana project status updates import adapter."""

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
        "title",
        "text",
        "html_text",
        "color",
        "author.gid",
        "author.name",
        "created_by.gid",
        "created_by.name",
        "created_at",
        "modified_at",
        "permalink_url",
    ]
)


class AsanaProjectStatusUpdatesAdapter(SourceAdapter):
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
        return "asana_project_status_updates_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def project_gids(self) -> list[str]:
        return _strings(
            self._config.get("project_gids")
            or self._config.get("projects")
            or self._config.get("project_gid")
        )

    @property
    def workspace_gid(self) -> str | None:
        return _optional(self._config.get("workspace_gid"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("limit"), default=30, maximum=100)

    @property
    def per_project_limit(self) -> int | None:
        value = self._config.get("per_project_limit")
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    @property
    def include_html_text(self) -> bool:
        return bool(self._config.get("include_html_text"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.project_gids:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for project_gid in self.project_gids:
                if len(signals) >= limit:
                    break
                project_limit = limit - len(signals)
                if self.per_project_limit:
                    project_limit = min(project_limit, self.per_project_limit)
                statuses = await self._fetch_project_statuses(
                    client,
                    project_gid=project_gid,
                    limit=project_limit,
                )
                signals.extend(
                    _status_signal(
                        status,
                        project_gid=project_gid,
                        adapter_name=self.name,
                        include_html_text=self.include_html_text,
                    )
                    for status in statuses
                    if isinstance(status, dict)
                )
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_project_statuses(
        self,
        client: httpx.AsyncClient,
        *,
        project_gid: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        statuses: list[dict[str, Any]] = []
        offset: str | None = None
        while len(statuses) < limit:
            page_size = min(self.page_size, limit - len(statuses))
            page_statuses, offset = await self._fetch_page(
                client,
                project_gid=project_gid,
                offset=offset,
                page_size=page_size,
            )
            if not page_statuses:
                break
            statuses.extend(page_statuses[: limit - len(statuses)])
            if not offset or len(page_statuses) < page_size:
                break
        return statuses[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        project_gid: str,
        offset: str | None,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        params: dict[str, Any] = {
            "limit": page_size,
            "opt_fields": OPT_FIELDS,
        }
        if offset:
            params["offset"] = offset
        if self.workspace_gid:
            params["workspace"] = self.workspace_gid
        url = f"{self.api_url}/projects/{project_gid}/project_statuses"
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-asana-project-status-updates-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Asana project status updates fetch failed for project %s", project_gid, exc_info=True)
            return [], None
        data = body.get("data") if isinstance(body, dict) else None
        statuses = [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
        return statuses, _next_offset(body)


AsanaProjectStatusUpdateAdapter = AsanaProjectStatusUpdatesAdapter


def _status_signal(
    status: dict[str, Any],
    *,
    project_gid: str,
    adapter_name: str,
    include_html_text: bool,
) -> Signal:
    author = status.get("author") if isinstance(status.get("author"), dict) else {}
    if not author:
        author = status.get("created_by") if isinstance(status.get("created_by"), dict) else {}
    status_gid = _text(status.get("gid"))
    title = _text(status.get("title")) or f"Asana project {project_gid} status"
    text = _text(status.get("text"))
    metadata: dict[str, Any] = {
        "asana_project_gid": project_gid,
        "asana_status_gid": status.get("gid"),
        "title": title,
        "text": text,
        "color": status.get("color"),
        "author": {
            "gid": author.get("gid"),
            "name": author.get("name"),
        },
        "created_at": status.get("created_at"),
        "modified_at": status.get("modified_at"),
        "permalink_url": status.get("permalink_url"),
        "raw": status,
    }
    if include_html_text:
        metadata["html_text"] = status.get("html_text")
    return Signal(
        id=f"asana-project-status:{project_gid}:{status_gid}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=title,
        content=text[:1000],
        url=_text(status.get("permalink_url")),
        author=_optional(author.get("name")),
        published_at=_parse_dt(status.get("created_at")),
        tags=sorted({"asana", "project-status", _text(status.get("color"))} - {""})[:10],
        credibility=0.65,
        metadata=metadata,
    )


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
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

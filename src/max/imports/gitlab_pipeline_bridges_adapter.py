"""GitLab pipeline bridges import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any
from urllib.parse import quote, unquote

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
GITLAB_API = "https://gitlab.com/api/v4"
FAILURE_STATUSES = {"failed", "canceled", "cancelled", "skipped", "manual"}


class GitLabPipelineBridgesAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        private_token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            private_token
            if private_token is not None
            else (
                token
                if token is not None
                else (
                    _optional(self._config.get("private_token"))
                    or _optional(self._config.get("token"))
                    or os.getenv("GITLAB_PRIVATE_TOKEN")
                    or os.getenv("GITLAB_TOKEN")
                )
            )
        )
        self.api_url = _api_url(
            api_url
            or _optional(self._config.get("api_url"))
            or _optional(self._config.get("gitlab_url"))
            or os.getenv("GITLAB_API_URL")
            or GITLAB_API
        )
        self._client = client

    @property
    def name(self) -> str:
        return "gitlab_pipeline_bridges_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def project_ids(self) -> list[str]:
        return _strings(
            self._config.get("project_ids")
            or self._config.get("projects")
            or self._config.get("project_id")
        )

    @property
    def pipeline_ids(self) -> list[str]:
        return _strings(
            self._config.get("pipeline_ids")
            or self._config.get("pipelines")
            or self._config.get("pipeline_id")
        )

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=30, maximum=100)

    @property
    def per_pipeline_limit(self) -> int | None:
        value = self._config.get("per_pipeline_limit")
        if value is None:
            return None
        return _positive_int(value, default=0, maximum=10_000) or None

    @property
    def status(self) -> str | None:
        return _optional(self._config.get("status"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.project_ids or not self.pipeline_ids:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for project_id in self.project_ids:
                for pipeline_id in self.pipeline_ids:
                    if len(signals) >= limit:
                        break
                    pipeline_limit = min(self.per_pipeline_limit or limit, limit - len(signals))
                    bridges = await self._fetch_bridges(
                        client,
                        project_id=project_id,
                        pipeline_id=pipeline_id,
                        limit=pipeline_limit,
                    )
                    signals.extend(
                        _bridge_signal(
                            bridge,
                            project_id=project_id,
                            pipeline_id=pipeline_id,
                            adapter_name=self.name,
                        )
                        for bridge in bridges
                        if isinstance(bridge, dict)
                    )
                if len(signals) >= limit:
                    break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_bridges(
        self,
        client: httpx.AsyncClient,
        *,
        project_id: str,
        pipeline_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        bridges: list[dict[str, Any]] = []
        page = 1
        while len(bridges) < limit:
            page_size = min(self.page_size, limit - len(bridges))
            page_bridges, next_page = await self._fetch_page(
                client,
                project_id=project_id,
                pipeline_id=pipeline_id,
                page=page,
                page_size=page_size,
            )
            if not page_bridges:
                break
            bridges.extend(page_bridges[: limit - len(bridges)])
            if next_page:
                page = next_page
            else:
                break
        return bridges[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        project_id: str,
        pipeline_id: str,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int | None]:
        params: dict[str, Any] = {"page": page, "per_page": page_size}
        if self.status:
            params["status"] = self.status
        url = f"{self.api_url}/projects/{_encode_project(project_id)}/pipelines/{quote(pipeline_id, safe='')}/bridges"
        try:
            response = await client.get(
                url,
                headers={
                    "PRIVATE-TOKEN": self.token or "",
                    "Accept": "application/json",
                    "User-Agent": "max-gitlab-pipeline-bridges-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitLab pipeline bridges fetch failed for %s pipeline %s", project_id, pipeline_id, exc_info=True)
            return [], None
        bridges = [item for item in body if isinstance(item, dict)] if isinstance(body, list) else []
        return bridges, _next_page(response)


GitLabPipelineBridgeAdapter = GitLabPipelineBridgesAdapter


def _bridge_signal(
    bridge: dict[str, Any],
    *,
    project_id: str,
    pipeline_id: str,
    adapter_name: str,
) -> Signal:
    bridge_id = _text(bridge.get("id"))
    name = _text(bridge.get("name")) or bridge_id or "GitLab bridge"
    status = _normalized_status(bridge.get("status"))
    stage = _text(bridge.get("stage"))
    user = bridge.get("user") if isinstance(bridge.get("user"), dict) else {}
    downstream = bridge.get("downstream_pipeline") if isinstance(bridge.get("downstream_pipeline"), dict) else {}
    source_type = SignalSourceType.FAILURE_DATA if status in FAILURE_STATUSES else SignalSourceType.ROADMAP
    return Signal(
        id=f"gitlab-bridge:{project_id}:{pipeline_id}:{bridge_id}",
        source_type=source_type,
        source_adapter=adapter_name,
        title=f"{name} {status or 'unknown'}",
        content=_content(name=name, status=status, stage=stage, downstream=downstream),
        url=_text(bridge.get("web_url")),
        author=_optional(user.get("username") or user.get("name")),
        published_at=_parse_dt(bridge.get("created_at") or bridge.get("updated_at") or bridge.get("finished_at")),
        tags=sorted({"gitlab", "pipeline-bridge", status, stage} - {""})[:10],
        credibility=0.7,
        metadata={
            "gitlab_bridge_id": bridge.get("id"),
            "project_id": project_id,
            "pipeline_id": pipeline_id,
            "name": name,
            "status": status or bridge.get("status"),
            "stage": stage or None,
            "user": _summary(user, ("id", "username", "name", "web_url")),
            "created_at": bridge.get("created_at"),
            "updated_at": bridge.get("updated_at"),
            "started_at": bridge.get("started_at"),
            "finished_at": bridge.get("finished_at"),
            "duration": bridge.get("duration"),
            "queued_duration": bridge.get("queued_duration"),
            "web_url": bridge.get("web_url"),
            "downstream_pipeline": _summary(
                downstream,
                ("id", "iid", "project_id", "sha", "ref", "status", "web_url", "created_at", "updated_at"),
            ),
            "raw": bridge,
        },
    )


def _content(*, name: str, status: str, stage: str, downstream: dict[str, Any]) -> str:
    parts = [f"GitLab bridge {name}"]
    if status:
        parts.append(f"status {status}")
    if stage:
        parts.append(f"stage {stage}")
    downstream_id = _text(downstream.get("id"))
    if downstream_id:
        parts.append(f"downstream pipeline {downstream_id}")
    return "; ".join(parts)


def _api_url(value: str) -> str:
    url = value.strip().rstrip("/")
    if not url.endswith("/api/v4"):
        url = f"{url}/api/v4"
    return url


def _encode_project(project: str) -> str:
    return quote(unquote(str(project).strip()), safe="")


def _next_page(response: httpx.Response) -> int | None:
    value = _optional(response.headers.get("X-Next-Page"))
    if not value:
        return None
    try:
        number = int(value)
    except ValueError:
        return None
    return number if number > 0 else None


def _summary(value: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: value.get(key) for key in keys if value.get(key) is not None}


def _normalized_status(value: object) -> str:
    status = _text(value).lower()
    return "canceled" if status == "cancelled" else status


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
            item = item.get("id") or item.get("iid") or item.get("path")
        text = _text(item)
        if text and text not in seen:
            seen.add(text)
            strings.append(text)
    return strings


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

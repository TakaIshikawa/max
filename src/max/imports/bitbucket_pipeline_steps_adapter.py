"""Bitbucket pipeline steps import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
BITBUCKET_API = "https://api.bitbucket.org/2.0"


class BitbucketPipelineStepsImportAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        username: str | None = None,
        app_password: str | None = None,
        token: str | None = None,
        bearer_token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.username = username if username is not None else (
            _optional(self._config.get("username")) or os.getenv("BITBUCKET_USERNAME")
        )
        self.app_password = app_password if app_password is not None else (
            _optional(self._config.get("app_password"))
            or _optional(self._config.get("password"))
            or os.getenv("BITBUCKET_APP_PASSWORD")
        )
        self.token = token if token is not None else (
            bearer_token
            or _optional(self._config.get("token"))
            or _optional(self._config.get("bearer_token"))
            or os.getenv("BITBUCKET_TOKEN")
            or os.getenv("BITBUCKET_BEARER_TOKEN")
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or BITBUCKET_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "bitbucket_pipeline_steps_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def workspace(self) -> str | None:
        return _optional(self._config.get("workspace"))

    @property
    def repo_slug(self) -> str | None:
        repository = _optional(
            self._config.get("repo_slug")
            or self._config.get("repository")
            or self._config.get("repo")
        )
        if repository and "/" in repository:
            return repository.rsplit("/", 1)[1]
        return repository

    @property
    def pipeline_uuids(self) -> list[str]:
        return _strings(
            self._config.get("pipeline_uuids")
            or self._config.get("pipeline_uuid")
            or self._config.get("pipeline_ids")
            or self._config.get("pipeline_id")
        )

    @property
    def statuses(self) -> set[str]:
        return {status.upper() for status in _strings(self._config.get("statuses") or self._config.get("status"))}

    @property
    def page_size(self) -> int:
        return _positive_int(
            self._config.get("page_size") or self._config.get("page_len") or self._config.get("pagelen"),
            default=30,
            maximum=100,
        )

    @property
    def _has_auth(self) -> bool:
        return bool(self.token or (self.username and self.app_password))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.workspace and self.repo_slug and self.pipeline_uuids and self._has_auth):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            seen: set[str] = set()
            for pipeline_uuid in self.pipeline_uuids:
                if len(signals) >= limit:
                    break
                steps = await self._fetch_steps(client, pipeline_uuid=pipeline_uuid, limit=limit - len(signals))
                for step in steps:
                    signal = _step_signal(
                        step,
                        workspace=self.workspace,
                        repo_slug=self.repo_slug,
                        pipeline_uuid=pipeline_uuid,
                        adapter_name=self.name,
                        seen=seen,
                    )
                    if signal:
                        signals.append(signal)
                    if len(signals) >= limit:
                        break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_steps(
        self,
        client: httpx.AsyncClient,
        *,
        pipeline_uuid: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        url: str | None = (
            f"{self.api_url}/repositories/{self.workspace}/{self.repo_slug}"
            f"/pipelines/{pipeline_uuid}/steps/"
        )
        params: dict[str, Any] | None = {"pagelen": min(self.page_size, limit)}
        while url and len(steps) < limit:
            body = await self._get(client, url, params=params)
            values = body.get("values") if isinstance(body.get("values"), list) else []
            if not values:
                break
            for item in values:
                if isinstance(item, dict) and self._matches_status(item):
                    steps.append(item)
                if len(steps) >= limit:
                    break
            url = _optional(body.get("next"))
            params = None
        return steps[:limit]

    def _matches_status(self, step: dict[str, Any]) -> bool:
        statuses = self.statuses
        if not statuses:
            return True
        return (_status(step) or "").upper() in statuses

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json", "User-Agent": "max-bitbucket-pipeline-steps-import/1"}
        auth = None
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        else:
            auth = httpx.BasicAuth(self.username or "", self.app_password or "")
        try:
            response = await client.get(url, headers=headers, auth=auth, params=params)
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Bitbucket pipeline steps fetch failed for %s", url, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


BitbucketPipelineStepsAdapter = BitbucketPipelineStepsImportAdapter


def _step_signal(
    step: dict[str, Any],
    *,
    workspace: str,
    repo_slug: str,
    pipeline_uuid: str,
    adapter_name: str,
    seen: set[str],
) -> Signal | None:
    step_id = _optional(step.get("uuid") or step.get("id") or step.get("name") or step.get("started_on"))
    if not step_id:
        return None
    external_id = f"bitbucket-pipeline-step:{workspace}:{repo_slug}:{pipeline_uuid}:{step_id}"
    if external_id in seen:
        return None
    seen.add(external_id)

    status = _status(step)
    name = _optional(step.get("name") or step.get("label") or step.get("key"))
    duration = _int(step.get("duration_in_seconds") or step.get("duration") or step.get("build_seconds_used"))
    started_on = step.get("started_on") or step.get("created_on")
    completed_on = step.get("completed_on") or step.get("finished_on")
    url = _step_url(step)
    return Signal(
        id=external_id,
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{workspace}/{repo_slug} pipeline step {name or step_id} {status or 'unknown'}",
        content=_content(name=name, status=status, duration=duration)[:1000],
        url=url,
        author=None,
        published_at=_parse_dt(started_on),
        tags=sorted({"bitbucket", "pipeline", "step", (status or "").lower()} - {""})[:10],
        credibility=0.66,
        metadata={
            "signal_role": "failure_data",
            "workspace": workspace,
            "repository": repo_slug,
            "pipeline_uuid": pipeline_uuid,
            "step_uuid": step.get("uuid") or step.get("id"),
            "name": name,
            "status": status,
            "state": step.get("state"),
            "duration": duration,
            "duration_in_seconds": duration,
            "started_on": started_on,
            "completed_on": completed_on,
            "url": url,
            "links": step.get("links"),
            "raw": step,
        },
    )


def _status(step: dict[str, Any]) -> str | None:
    state = step.get("state") if isinstance(step.get("state"), dict) else {}
    result = state.get("result") if isinstance(state.get("result"), dict) else {}
    return _optional(
        result.get("name")
        or result.get("type")
        or state.get("name")
        or state.get("type")
        or step.get("status")
        or step.get("result")
    )


def _content(*, name: str | None, status: str | None, duration: int) -> str:
    parts = [
        f"step {name}" if name else "",
        f"status {status}" if status else "",
        f"duration {duration}s" if duration else "",
    ]
    return ", ".join(part for part in parts if part) or "Bitbucket pipeline step"


def _step_url(step: dict[str, Any]) -> str:
    links = step.get("links") if isinstance(step.get("links"), dict) else {}
    for key in ("html", "self", "log"):
        href = _link_href(links.get(key))
        if href:
            return href
    return ""


def _link_href(value: object) -> str:
    if isinstance(value, dict):
        return _text(value.get("href"))
    return ""


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


def _int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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

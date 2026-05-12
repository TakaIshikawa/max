"""CircleCI workflows import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
CIRCLECI_API = "https://circleci.com/api/v2"


class CircleCIWorkflowsImportAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            token
            if token is not None
            else (
                _optional(self._config.get("token"))
                or os.getenv("CIRCLECI_TOKEN")
                or os.getenv("CIRCLE_TOKEN")
            )
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or CIRCLECI_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "circleci_workflows_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def project_slugs(self) -> list[str]:
        return _strings(
            self._config.get("project_slugs")
            or self._config.get("projects")
            or self._config.get("project_slug")
        )

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.project_slugs:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for project_slug in self.project_slugs:
                if len(signals) >= limit:
                    break
                workflows = await self._fetch_project_workflows(
                    client,
                    project_slug=project_slug,
                    limit=limit - len(signals),
                )
                signals.extend(
                    _workflow_signal(workflow, pipeline, self.name)
                    for workflow, pipeline in workflows
                    if isinstance(workflow, dict) and isinstance(pipeline, dict)
                )
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_project_workflows(
        self,
        client: httpx.AsyncClient,
        *,
        project_slug: str,
        limit: int,
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        workflows: list[tuple[dict[str, Any], dict[str, Any]]] = []
        page_token: str | None = None
        while len(workflows) < limit:
            pipelines_body = await self._get(
                client,
                f"{self.api_url}/project/{project_slug}/pipeline",
                params=self._pipeline_params(page_token=page_token),
            )
            pipelines = pipelines_body.get("items") if isinstance(pipelines_body, dict) else []
            if not isinstance(pipelines, list) or not pipelines:
                break
            for pipeline in pipelines:
                if len(workflows) >= limit:
                    break
                if not isinstance(pipeline, dict):
                    continue
                pipeline_id = _optional(pipeline.get("id"))
                if not pipeline_id:
                    continue
                workflows.extend(
                    await self._fetch_pipeline_workflows(
                        client,
                        pipeline_id=pipeline_id,
                        pipeline=pipeline,
                        limit=limit - len(workflows),
                    )
                )
            page_token = _optional(pipelines_body.get("next_page_token"))
            if not page_token:
                break
        return workflows[:limit]

    async def _fetch_pipeline_workflows(
        self,
        client: httpx.AsyncClient,
        *,
        pipeline_id: str,
        pipeline: dict[str, Any],
        limit: int,
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        workflows: list[tuple[dict[str, Any], dict[str, Any]]] = []
        page_token: str | None = None
        while len(workflows) < limit:
            params = {"page-token": page_token} if page_token else {}
            body = await self._get(
                client,
                f"{self.api_url}/pipeline/{pipeline_id}/workflow",
                params=params,
            )
            items = body.get("items") if isinstance(body, dict) else []
            if not isinstance(items, list) or not items:
                break
            workflows.extend((item, pipeline) for item in items if isinstance(item, dict))
            page_token = _optional(body.get("next_page_token"))
            if len(items) < self.page_size or not page_token:
                break
        return workflows[:limit]

    def _pipeline_params(self, *, page_token: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        branch = _optional(self._config.get("branch"))
        if branch:
            params["branch"] = branch
        if page_token:
            params["page-token"] = page_token
        return params

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            response = await client.get(
                url,
                headers={"Circle-Token": self.token or "", "Accept": "application/json"},
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("CircleCI workflows fetch failed for %s", url, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


CircleCIWorkflowsAdapter = CircleCIWorkflowsImportAdapter


def _workflow_signal(
    workflow: dict[str, Any],
    pipeline: dict[str, Any],
    adapter_name: str,
) -> Signal:
    status = _text(workflow.get("status"))
    name = _text(workflow.get("name")) or "Workflow"
    project_slug = _text(workflow.get("project_slug") or pipeline.get("project_slug"))
    pipeline_number = workflow.get("pipeline_number") or pipeline.get("number")
    vcs = pipeline.get("vcs") if isinstance(pipeline.get("vcs"), dict) else {}
    commit = _text(vcs.get("revision") or workflow.get("commit") or pipeline.get("commit"))
    branch = _text(vcs.get("branch") or workflow.get("branch") or pipeline.get("branch"))
    workflow_id = _text(workflow.get("id"))
    created_at = workflow.get("created_at") or pipeline.get("created_at")
    stopped_at = workflow.get("stopped_at")
    commit_subject = _commit_subject(vcs)
    return Signal(
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{project_slug} {name} #{pipeline_number or 'unknown'} {status or 'unknown'}",
        content=_text(workflow.get("tag") or commit_subject)[:1000],
        url=_workflow_url(workflow),
        author=_text(workflow.get("started_by")) or None,
        published_at=_parse_dt(created_at),
        tags=sorted({"circleci", "workflow", status, branch} - {""})[:10],
        credibility=0.7,
        metadata={
            "workflow_id": workflow.get("id"),
            "workflow_name": workflow.get("name"),
            "project_slug": project_slug,
            "status": workflow.get("status"),
            "duration_seconds": _duration_seconds(created_at, stopped_at),
            "pipeline_id": workflow.get("pipeline_id") or pipeline.get("id"),
            "pipeline_number": pipeline_number,
            "branch": branch,
            "commit": commit,
            "created_at": created_at,
            "stopped_at": stopped_at,
            "tag": workflow.get("tag"),
            "auto_rerun_number": workflow.get("auto_rerun_number"),
            "workflow_url": _workflow_url(workflow),
            "pipeline_url": _text(pipeline.get("web_url")),
        },
    )


def _workflow_url(workflow: dict[str, Any]) -> str:
    return _text(workflow.get("url") or workflow.get("web_url"))


def _commit_subject(vcs: dict[str, Any]) -> str:
    commit = vcs.get("commit")
    if not isinstance(commit, dict):
        return ""
    return _text(commit.get("subject"))


def _duration_seconds(start: object, end: object) -> int | None:
    started = _parse_dt(start)
    finished = _parse_dt(end)
    if not started or not finished:
        return None
    return max(0, int((finished - started).total_seconds()))


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
    return [_text(item) for item in value if _text(item)]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

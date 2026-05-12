"""GitLab pipeline jobs import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
GITLAB_API = "https://gitlab.com/api/v4"
JOB_OUTCOME_STATUSES = {"failed", "manual", "canceled", "success", "successful"}


class GitLabPipelineJobsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        project_id: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            token
            if token is not None
            else (_optional(self._config.get("token")) or os.getenv("GITLAB_TOKEN"))
        )
        self.project_id = (
            project_id
            if project_id is not None
            else (_optional(self._config.get("project_id")) or os.getenv("GITLAB_PROJECT_ID"))
        )
        self.api_url = (
            api_url
            or _optional(self._config.get("api_url"))
            or os.getenv("GITLAB_API_URL")
            or GITLAB_API
        ).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "gitlab_pipeline_jobs_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def pipeline_id(self) -> str | None:
        return _optional(self._config.get("pipeline_id"))

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.project_id:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            jobs = await self._fetch_jobs(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        for job in jobs:
            if not isinstance(job, dict) or not _is_job_outcome(job):
                continue
            signals.append(_job_signal(job, self.project_id, self.name))
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_jobs(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        page = 1
        while len(jobs) < limit:
            page_size = min(self.per_page, limit - len(jobs))
            body = await self._get(client, page=page, per_page=page_size)
            if not isinstance(body, list) or not body:
                break
            jobs.extend(item for item in body if isinstance(item, dict))
            if len(body) < page_size:
                break
            page += 1
        return jobs[:limit]

    async def _get(self, client: httpx.AsyncClient, *, page: int, per_page: int) -> object:
        try:
            response = await client.get(
                self._endpoint,
                params=self._params(page=page, per_page=per_page),
                headers={
                    "PRIVATE-TOKEN": self.token or "",
                    "Accept": "application/json",
                    "User-Agent": "max-gitlab-pipeline-jobs-import/1",
                },
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.warning("GitLab pipeline jobs fetch failed for %s", self._endpoint, exc_info=True)
            return []

    @property
    def _endpoint(self) -> str:
        project = quote(self.project_id or "", safe="")
        if self.pipeline_id:
            pipeline = quote(self.pipeline_id, safe="")
            return f"{self.api_url}/projects/{project}/pipelines/{pipeline}/jobs"
        return f"{self.api_url}/projects/{project}/jobs"

    def _params(self, *, page: int, per_page: int) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        for key in ("scope", "ref"):
            value = self._config.get(key)
            if isinstance(value, list):
                values = [_text(item) for item in value if _text(item)]
                if values:
                    params[key] = values
            else:
                text = _optional(value)
                if text:
                    params[key] = text
        return params


GitLabPipelineJobAdapter = GitLabPipelineJobsAdapter


def _job_signal(job: dict[str, Any], project_id: str, adapter_name: str) -> Signal:
    name = _text(job.get("name")) or _text(job.get("id")) or "GitLab job"
    status = _normalized_status(job.get("status"))
    stage = _text(job.get("stage"))
    ref = _text(job.get("ref"))
    pipeline = job.get("pipeline") if isinstance(job.get("pipeline"), dict) else {}
    commit = job.get("commit") if isinstance(job.get("commit"), dict) else {}
    runner = job.get("runner") if isinstance(job.get("runner"), dict) else {}
    runner_label = _text(runner.get("description")) or _text(runner.get("short_sha")) or _text(runner.get("id"))
    return Signal(
        id=f"gitlab-job:{project_id}:{_text(job.get('id'))}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{name} {status or 'unknown'}",
        content=_content(name=name, status=status, stage=stage, ref=ref),
        url=_text(job.get("web_url")),
        author=_text(job.get("user", {}).get("username")) if isinstance(job.get("user"), dict) else None,
        published_at=_parse_dt(job.get("created_at") or job.get("started_at") or job.get("finished_at")),
        tags=sorted({"gitlab", "pipeline-job", status, stage, ref} - {""})[:10],
        credibility=0.7,
        metadata={
            "gitlab_job_id": job.get("id"),
            "project_id": project_id,
            "name": name,
            "status": status or job.get("status"),
            "stage": stage or None,
            "ref": ref or None,
            "pipeline_id": pipeline.get("id"),
            "pipeline": _summary(pipeline, ("id", "iid", "project_id", "sha", "ref", "status", "web_url")),
            "commit_sha": commit.get("id") or commit.get("short_id"),
            "commit": _summary(commit, ("id", "short_id", "title", "message", "author_name", "web_url")),
            "duration": job.get("duration"),
            "queued_duration": job.get("queued_duration"),
            "runner": _summary(runner, ("id", "description", "runner_type", "status", "active")),
            "runner_label": runner_label or None,
            "created_at": job.get("created_at"),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "web_url": job.get("web_url"),
            "raw": job,
        },
    )


def _content(*, name: str, status: str, stage: str, ref: str) -> str:
    parts = [f"GitLab CI job {name}"]
    if status:
        parts.append(f"status {status}")
    if stage:
        parts.append(f"stage {stage}")
    if ref:
        parts.append(f"ref {ref}")
    return "; ".join(parts)


def _is_job_outcome(job: dict[str, Any]) -> bool:
    return _normalized_status(job.get("status")) in JOB_OUTCOME_STATUSES


def _normalized_status(value: object) -> str:
    status = _text(value).lower()
    return "success" if status == "successful" else status


def _summary(value: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: value.get(key) for key in keys if value.get(key) is not None}


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


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

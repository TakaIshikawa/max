"""CircleCI jobs import adapter."""

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


class CircleCIJobsImportAdapter(SourceAdapter):
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
        return "circleci_jobs_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def workflow_ids(self) -> list[str]:
        return _strings(self._config.get("workflow_ids") or self._config.get("workflow_id"))

    @property
    def project_slug(self) -> str:
        return _text(self._config.get("project_slug"))

    @property
    def statuses(self) -> set[str]:
        return set(_strings(self._config.get("statuses") or self._config.get("status")))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.workflow_ids:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for workflow_id in self.workflow_ids:
                if len(signals) >= limit:
                    break
                jobs = await self._fetch_workflow_jobs(
                    client,
                    workflow_id=workflow_id,
                    limit=limit - len(signals),
                )
                if jobs is None:
                    return []
                signals.extend(
                    _job_signal(job, workflow_id, self.project_slug, self.name)
                    for job in jobs
                    if isinstance(job, dict)
                )
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_workflow_jobs(
        self,
        client: httpx.AsyncClient,
        *,
        workflow_id: str,
        limit: int,
    ) -> list[dict[str, Any]] | None:
        jobs: list[dict[str, Any]] = []
        page_token: str | None = None
        while len(jobs) < limit:
            body = await self._get(
                client,
                f"{self.api_url}/workflow/{workflow_id}/job",
                params=self._params(page_token=page_token),
            )
            if body is None:
                return None
            items = body.get("items") if isinstance(body, dict) else []
            if not isinstance(items, list) or not items:
                break
            for item in items:
                if len(jobs) >= limit:
                    break
                if isinstance(item, dict) and self._matches_status(item):
                    jobs.append(item)
            page_token = _optional(body.get("next_page_token"))
            if not page_token:
                break
        return jobs[:limit]

    def _params(self, *, page_token: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {"page-size": self.page_size}
        if page_token:
            params["page-token"] = page_token
        return params

    def _matches_status(self, job: dict[str, Any]) -> bool:
        statuses = self.statuses
        if not statuses:
            return True
        return _text(job.get("status")) in statuses

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, Any],
    ) -> dict[str, Any] | None:
        try:
            response = await client.get(
                url,
                headers={"Circle-Token": self.token or "", "Accept": "application/json"},
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("CircleCI jobs fetch failed for %s", url, exc_info=True)
            return None
        return body if isinstance(body, dict) else {}


CircleCIJobsAdapter = CircleCIJobsImportAdapter


def _job_signal(
    job: dict[str, Any],
    workflow_id: str,
    configured_project_slug: str,
    adapter_name: str,
) -> Signal:
    job_name = _text(job.get("name")) or "Job"
    job_number = job.get("job_number") or job.get("number")
    status = _text(job.get("status"))
    project_slug = _text(job.get("project_slug")) or configured_project_slug
    started_at = job.get("started_at") or job.get("created_at")
    stopped_at = job.get("stopped_at")
    duration = job.get("duration") or job.get("duration_seconds")
    job_id = _text(job.get("id") or job.get("job_number") or job.get("number"))
    return Signal(
        id=f"circleci-job:{workflow_id}:{job_id}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{project_slug or 'CircleCI'} {job_name} #{job_number or 'unknown'} {status or 'unknown'}",
        content=_job_content(job)[:1000],
        url=_job_url(job),
        author=_text(job.get("started_by")) or None,
        published_at=_parse_dt(started_at),
        tags=sorted({"circleci", "job", status, project_slug} - {""})[:10],
        credibility=0.7,
        metadata={
            "job_id": job.get("id"),
            "job_number": job_number,
            "job_name": job.get("name"),
            "workflow_id": workflow_id,
            "project_slug": project_slug,
            "status": job.get("status"),
            "type": job.get("type"),
            "duration_seconds": _duration_seconds(started_at, stopped_at, duration),
            "started_at": started_at,
            "stopped_at": stopped_at,
            "dependencies": job.get("dependencies"),
            "parallel_runs": job.get("parallel_runs"),
            "job_url": _job_url(job),
            "raw": job,
        },
    )


def _job_url(job: dict[str, Any]) -> str:
    return _text(job.get("web_url") or job.get("url"))


def _job_content(job: dict[str, Any]) -> str:
    message = _optional(job.get("message"))
    if message:
        return message
    executor = job.get("executor") if isinstance(job.get("executor"), dict) else {}
    return _text(executor.get("type"))


def _duration_seconds(start: object, end: object, duration: object) -> int | None:
    try:
        if duration is not None:
            number = int(duration)
            if number >= 0:
                return number
    except (TypeError, ValueError):
        pass
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
        value = [item.strip() for item in value.split(",")]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

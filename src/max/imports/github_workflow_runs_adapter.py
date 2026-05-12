"""GitHub workflow runs import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
GITHUB_API = "https://api.github.com"


class GitHubWorkflowRunsImportAdapter(SourceAdapter):
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
            else (_optional(self._config.get("token")) or os.getenv("GITHUB_TOKEN"))
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or GITHUB_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "github_workflow_runs_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def repositories(self) -> list[str]:
        return _strings(self._config.get("repositories") or self._config.get("repos"))

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.repositories:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for repository in self.repositories:
                if len(signals) >= limit:
                    break
                repo = _owner_repo(repository)
                if not repo:
                    continue
                runs = await self._fetch_repository(client, repository=repo, limit=limit - len(signals))
                signals.extend(
                    _workflow_run_signal(item, repo, self.name)
                    for item in runs
                    if isinstance(item, dict)
                )
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_repository(
        self,
        client: httpx.AsyncClient,
        *,
        repository: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        page = 1
        while len(runs) < limit:
            page_size = min(self.per_page, limit - len(runs))
            params = self._params(page_size=page_size, page=page)
            body = await self._get(
                client,
                f"{self.api_url}/repos/{repository}/actions/runs",
                params=params,
            )
            page_runs = body.get("workflow_runs") if isinstance(body, dict) else []
            if not isinstance(page_runs, list) or not page_runs:
                break
            runs.extend(item for item in page_runs if isinstance(item, dict))
            if len(page_runs) < page_size:
                break
            page += 1
        return runs[:limit]

    def _params(self, *, page_size: int, page: int) -> dict[str, Any]:
        params: dict[str, Any] = {"per_page": page_size, "page": page}
        for key in ("branch", "event", "status"):
            value = _optional(self._config.get(key))
            if value:
                params[key] = value
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
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitHub workflow runs fetch failed for %s", url, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


GitHubWorkflowRunsAdapter = GitHubWorkflowRunsImportAdapter


def _workflow_run_signal(run: dict[str, Any], repository: str, adapter_name: str) -> Signal:
    actor = run.get("actor") if isinstance(run.get("actor"), dict) else {}
    status = _text(run.get("status"))
    conclusion = _text(run.get("conclusion"))
    duration = _duration_seconds(run.get("run_started_at") or run.get("created_at"), run.get("updated_at"))
    workflow_name = _text(run.get("name") or run.get("display_title") or run.get("workflow_name"))
    run_number = _int(run.get("run_number"))
    title_state = conclusion or status or "unknown"
    return Signal(
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{repository} {workflow_name or 'Workflow'} #{run_number} {title_state}",
        content=_text(run.get("display_title") or workflow_name)[:1000],
        url=_text(run.get("html_url")),
        author=_text(actor.get("login")) or None,
        published_at=_parse_dt(run.get("created_at")),
        tags=sorted({"github", "workflow-run", status, conclusion, _text(run.get("event"))} - {""})[:10],
        credibility=0.7,
        metadata={
            "run_id": run.get("id"),
            "repository": repository,
            "workflow_name": workflow_name,
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "branch": run.get("head_branch"),
            "event": run.get("event"),
            "run_number": run.get("run_number"),
            "duration_seconds": duration,
            "actor": _summary(actor),
            "created_at": run.get("created_at"),
            "updated_at": run.get("updated_at"),
            "run_started_at": run.get("run_started_at"),
            "head_sha": run.get("head_sha"),
        },
    )


def _duration_seconds(start: object, end: object) -> int | None:
    started = _parse_dt(start)
    finished = _parse_dt(end)
    if not started or not finished:
        return None
    return max(0, int((finished - started).total_seconds()))


def _summary(value: dict[str, Any]) -> dict[str, Any]:
    return {"login": value.get("login"), "id": value.get("id"), "html_url": value.get("html_url")}


def _owner_repo(value: str) -> str | None:
    text = value.strip()
    if "/" not in text:
        return None
    owner, repo = text.split("/", 1)
    return f"{owner}/{repo}" if owner and repo else None


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


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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

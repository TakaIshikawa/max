"""GitLab project environments import adapter."""

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


class GitLabProjectEnvironmentsAdapter(SourceAdapter):
    """Import GitLab project environments as deployment signals."""

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
        return "gitlab_project_environments_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def project_id(self) -> str:
        return (
            _optional(self._config.get("project_id"))
            or _optional(self._config.get("project_path"))
            or os.getenv("GITLAB_PROJECT_ID")
            or os.getenv("GITLAB_PROJECT_PATH")
            or ""
        )

    @property
    def search(self) -> str | None:
        return _optional(self._config.get("search"))

    @property
    def states(self) -> str | None:
        values = _strings(self._config.get("states") or self._config.get("state"))
        return ",".join(values) if values else None

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.project_id:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            environments = await self._fetch_environments(client, limit=limit)
            return [
                _environment_signal(environment, project_id=self.project_id, adapter_name=self.name)
                for environment in environments
                if isinstance(environment, dict)
            ][:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_environments(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        environments: list[dict[str, Any]] = []
        page = 1
        while len(environments) < limit:
            page_size = min(self.page_size, limit - len(environments))
            page_environments, next_page = await self._fetch_page(client, page=page, page_size=page_size)
            if not page_environments:
                break
            environments.extend(page_environments[: limit - len(environments)])
            if next_page:
                page = next_page
            elif len(page_environments) < page_size:
                break
            else:
                page += 1
        return environments[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int | None]:
        params: dict[str, Any] = {"page": page, "per_page": page_size}
        if self.search:
            params["search"] = self.search
        if self.states:
            params["states"] = self.states
        url = f"{self.api_url}/projects/{_encode_project(self.project_id)}/environments"
        try:
            response = await client.get(
                url,
                headers={
                    "PRIVATE-TOKEN": self.token or "",
                    "Accept": "application/json",
                    "User-Agent": "max-gitlab-project-environments-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitLab project environments fetch failed for %s", self.project_id, exc_info=True)
            return [], None
        environments = [item for item in body if isinstance(item, dict)] if isinstance(body, list) else []
        return environments, _next_page(response)


GitLabProjectEnvironmentAdapter = GitLabProjectEnvironmentsAdapter


def _environment_signal(
    environment: dict[str, Any],
    *,
    project_id: str,
    adapter_name: str,
) -> Signal:
    environment_id = _text(environment.get("id"))
    name = _text(environment.get("name")) or environment_id or "GitLab environment"
    state = _text(environment.get("state")).lower()
    tier = _text(environment.get("tier"))
    latest_deployment = _deployment_summary(environment.get("last_deployment") or environment.get("latest_deployment"))
    return Signal(
        id=f"gitlab-project-environment:{project_id}:{environment_id}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"GitLab environment {name}",
        content=_content(name=name, state=state, tier=tier, latest_deployment=latest_deployment),
        url=_text(environment.get("external_url") or environment.get("url")),
        author=None,
        published_at=_parse_dt(environment.get("updated_at") or environment.get("created_at")),
        tags=sorted({"gitlab", "project-environment", state, tier} - {""})[:10],
        credibility=0.66,
        metadata={
            "signal_role": "problem",
            "gitlab_environment_id": environment.get("id"),
            "environment_id": environment.get("id"),
            "project_id": project_id,
            "name": environment.get("name"),
            "slug": environment.get("slug"),
            "state": environment.get("state"),
            "tier": environment.get("tier"),
            "external_url": environment.get("external_url"),
            "created_at": environment.get("created_at"),
            "updated_at": environment.get("updated_at"),
            "latest_deployment": latest_deployment,
            "raw": environment,
        },
    )


def _content(*, name: str, state: str, tier: str, latest_deployment: dict[str, Any]) -> str:
    parts = [f"GitLab environment {name}"]
    if state:
        parts.append(f"state {state}")
    if tier:
        parts.append(f"tier {tier}")
    status = _text(latest_deployment.get("status"))
    if status:
        parts.append(f"latest deployment {status}")
    return "; ".join(parts)


def _deployment_summary(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    deployable = value.get("deployable") if isinstance(value.get("deployable"), dict) else {}
    return {
        key: result
        for key, result in {
            "id": value.get("id"),
            "iid": value.get("iid"),
            "status": value.get("status"),
            "ref": value.get("ref"),
            "sha": value.get("sha"),
            "created_at": value.get("created_at"),
            "updated_at": value.get("updated_at"),
            "finished_at": value.get("finished_at"),
            "deployable": {
                "id": deployable.get("id"),
                "name": deployable.get("name"),
                "status": deployable.get("status"),
            }
            if deployable
            else {},
        }.items()
        if result not in (None, {}, "")
    }


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


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

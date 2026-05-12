"""GitHub deployments import adapter."""

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


class GitHubDeploymentsImportAdapter(SourceAdapter):
    """Fetch GitHub deployments and convert them to Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str | None = None,
        repository: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            token
            if token is not None
            else (_optional(self._config.get("token")) or os.getenv("GITHUB_TOKEN"))
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or GITHUB_API).rstrip("/")
        self._repository = repository
        self._owner = owner
        self._repo = repo
        self._client = client

    @property
    def name(self) -> str:
        return "github_deployments_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def repositories(self) -> list[str]:
        explicit = _owner_repo_from_parts(self._owner, self._repo) or _owner_repo(self._repository)
        if explicit:
            return [explicit]

        configured = (
            self._config.get("repository")
            or self._config.get("repo")
            or self._config.get("repositories")
            or self._config.get("repos")
            or os.getenv("GITHUB_REPOSITORY")
        )
        repositories = _strings(configured)
        from_parts = _owner_repo_from_parts(self._config.get("owner"), self._config.get("repo"))
        if from_parts:
            repositories.insert(0, from_parts)
        return _dedupe([repo for repo in (_owner_repo(item) for item in repositories) if repo])

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
                deployments = await self._fetch_repository(
                    client,
                    repository=repository,
                    limit=limit - len(signals),
                )
                for deployment in deployments:
                    signal = _deployment_signal(deployment, repository, self.name)
                    if signal:
                        signals.append(signal)
                    if len(signals) >= limit:
                        break
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
        deployments: list[dict[str, Any]] = []
        page = 1
        while len(deployments) < limit:
            page_size = min(self.per_page, limit - len(deployments))
            body = await self._get(
                client,
                f"{self.api_url}/repos/{repository}/deployments",
                params=self._params(page_size=page_size, page=page),
            )
            if not isinstance(body, list) or not body:
                break
            deployments.extend(item for item in body if isinstance(item, dict))
            if len(body) < page_size:
                break
            page += 1
        return deployments[:limit]

    def _params(self, *, page_size: int, page: int) -> dict[str, Any]:
        params: dict[str, Any] = {"per_page": page_size, "page": page}
        for key in ("sha", "ref", "task", "environment"):
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
    ) -> object:
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "max-github-deployments-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.warning("GitHub deployments fetch failed for %s", url, exc_info=True)
            return []


GitHubDeploymentsAdapter = GitHubDeploymentsImportAdapter


def _deployment_signal(
    deployment: dict[str, Any],
    repository: str,
    adapter_name: str,
) -> Signal | None:
    deployment_id = _optional(deployment.get("id"))
    if not deployment_id:
        return None

    creator = deployment.get("creator") if isinstance(deployment.get("creator"), dict) else {}
    environment = _text(deployment.get("environment"))
    ref = _text(deployment.get("ref"))
    task = _text(deployment.get("task")) or "deploy"
    sha = _text(deployment.get("sha"))
    production = _bool_or_none(deployment.get("production_environment"))
    transient = _bool_or_none(deployment.get("transient_environment"))
    source_url = _text(deployment.get("html_url") or deployment.get("url"))
    return Signal(
        id=f"github-deployment:{repository}:{deployment_id}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{repository} deployment {deployment_id} {environment or ref or task}",
        content=_text(deployment.get("description") or deployment.get("payload"))[:1000],
        url=source_url,
        author=_text(creator.get("login")) or None,
        published_at=_parse_dt(deployment.get("created_at")),
        tags=sorted({"github", "deployment", environment, ref, task, _readiness_tag(production, transient)} - {""})[:10],
        credibility=0.7,
        metadata={
            "github_deployment_id": deployment.get("id"),
            "deployment_id": deployment.get("id"),
            "repository": repository,
            "sha": deployment.get("sha"),
            "ref": deployment.get("ref"),
            "task": deployment.get("task"),
            "environment": deployment.get("environment"),
            "creator": _summary(creator),
            "payload": deployment.get("payload"),
            "transient_environment": transient,
            "production_environment": production,
            "original_environment": deployment.get("original_environment"),
            "created_at": deployment.get("created_at"),
            "updated_at": deployment.get("updated_at"),
            "deployment_url": deployment.get("url"),
            "html_url": deployment.get("html_url"),
            "statuses_url": deployment.get("statuses_url"),
            "environment_url": deployment.get("environment_url"),
            "description": deployment.get("description"),
            "signal_role": "release_readiness",
        },
    )


def _readiness_tag(production: bool | None, transient: bool | None) -> str:
    if production is True:
        return "production"
    if transient is True:
        return "transient"
    return ""


def _owner_repo_from_parts(owner: object, repo: object) -> str | None:
    owner_text = _optional(owner)
    repo_text = _optional(repo)
    return f"{owner_text}/{repo_text}" if owner_text and repo_text else None


def _owner_repo(value: object) -> str | None:
    text = _optional(value)
    if not text or "/" not in text:
        return None
    owner, repo = text.split("/", 1)
    return f"{owner}/{repo}" if owner and repo else None


def _summary(value: dict[str, Any]) -> dict[str, Any]:
    return {"login": value.get("login"), "id": value.get("id"), "html_url": value.get("html_url")}


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


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",")]
    if not isinstance(value, list | tuple | set):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

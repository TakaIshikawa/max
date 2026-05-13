"""GitHub workflow artifacts import adapter."""

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


class GitHubWorkflowArtifactsImportAdapter(SourceAdapter):
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
        return "github_workflow_artifacts_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def repositories(self) -> list[str]:
        return _strings(self._config.get("repositories") or self._config.get("repos"))

    @property
    def artifact_name(self) -> str | None:
        return _optional(self._config.get("name"))

    @property
    def expired(self) -> bool | None:
        return _optional_bool(self._config.get("expired"))

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
                owner_repo = _owner_repo(repository)
                if not owner_repo:
                    continue
                artifacts = await self._fetch_repository(
                    client,
                    repository=owner_repo,
                    limit=limit - len(signals),
                )
                signals.extend(
                    _artifact_signal(item, owner_repo, self.name)
                    for item in artifacts
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
        artifacts: list[dict[str, Any]] = []
        page = 1
        while len(artifacts) < limit:
            page_size = min(self.per_page, limit - len(artifacts))
            body = await self._get(
                client,
                f"{self.api_url}/repos/{repository}/actions/artifacts",
                params=self._params(page_size=page_size, page=page),
            )
            page_artifacts = body.get("artifacts") if isinstance(body, dict) else []
            if not isinstance(page_artifacts, list) or not page_artifacts:
                break
            filtered = [
                item
                for item in page_artifacts
                if isinstance(item, dict) and self._matches_filters(item)
            ]
            artifacts.extend(filtered[: limit - len(artifacts)])
            if len(page_artifacts) < page_size:
                break
            page += 1
        return artifacts[:limit]

    def _params(self, *, page_size: int, page: int) -> dict[str, Any]:
        params: dict[str, Any] = {"per_page": page_size, "page": page}
        if self.artifact_name:
            params["name"] = self.artifact_name
        return params

    def _matches_filters(self, artifact: dict[str, Any]) -> bool:
        if self.artifact_name and _text(artifact.get("name")) != self.artifact_name:
            return False
        if self.expired is not None and bool(artifact.get("expired")) is not self.expired:
            return False
        return True

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
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "max-github-workflow-artifacts-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitHub workflow artifacts fetch failed for %s", url, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


GitHubWorkflowArtifactsAdapter = GitHubWorkflowArtifactsImportAdapter


def _artifact_signal(artifact: dict[str, Any], repository: str, adapter_name: str) -> Signal:
    workflow_run = artifact.get("workflow_run") if isinstance(artifact.get("workflow_run"), dict) else {}
    artifact_id = _text(artifact.get("id")) or _text(artifact.get("node_id")) or _text(artifact.get("name"))
    name = _text(artifact.get("name")) or "workflow artifact"
    expired = bool(artifact.get("expired"))
    size = artifact.get("size_in_bytes")
    workflow_run_summary = _workflow_run_summary(workflow_run)
    return Signal(
        id=f"github-workflow-artifact:{repository}:{artifact_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{repository} workflow artifact {name}",
        content=_content(name=name, size=size, expired=expired, workflow_run=workflow_run_summary),
        url=_text(artifact.get("archive_download_url")),
        author=None,
        published_at=_parse_dt(artifact.get("created_at")),
        tags=sorted(
            {
                "github",
                "workflow-artifact",
                repository,
                name,
                "expired" if expired else "active",
            }
            - {""}
        )[:10],
        credibility=0.65,
        metadata={
            "signal_role": "roadmap",
            "artifact_id": artifact.get("id"),
            "node_id": artifact.get("node_id"),
            "repository": repository,
            "name": name,
            "size": size,
            "size_in_bytes": size,
            "expired": expired,
            "archive_download_url": artifact.get("archive_download_url"),
            "workflow_run": workflow_run_summary,
            "created_at": artifact.get("created_at"),
            "updated_at": artifact.get("updated_at"),
            "expires_at": artifact.get("expires_at"),
            "url": artifact.get("archive_download_url"),
            "raw": artifact,
        },
    )


def _workflow_run_summary(workflow_run: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": workflow_run.get("id"),
        "repository_id": workflow_run.get("repository_id"),
        "head_repository_id": workflow_run.get("head_repository_id"),
        "head_branch": workflow_run.get("head_branch"),
        "head_sha": workflow_run.get("head_sha"),
    }


def _content(*, name: str, size: object, expired: bool, workflow_run: dict[str, Any]) -> str:
    parts = [f"GitHub workflow artifact {name}"]
    if size is not None:
        parts.append(f"size {size} bytes")
    parts.append("expired" if expired else "active")
    run_id = _text(workflow_run.get("id"))
    if run_id:
        parts.append(f"workflow run {run_id}")
    branch = _text(workflow_run.get("head_branch"))
    if branch:
        parts.append(f"branch {branch}")
    return "; ".join(parts)[:1000]


def _owner_repo(value: str) -> str | None:
    text = value.strip()
    parts = text.split("/")
    if len(parts) != 2:
        return None
    owner, repo = parts
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


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

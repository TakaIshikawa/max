"""CircleCI job artifacts import adapter."""

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


class CircleCIJobArtifactsImportAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str | None = None,
        project_slug: str | None = None,
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
        self._project_slug = project_slug
        self._client = client

    @property
    def name(self) -> str:
        return "circleci_job_artifacts_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def project_slug(self) -> str:
        return _text(self._project_slug or self._config.get("project_slug"))

    @property
    def job_numbers(self) -> list[str]:
        return _strings(self._config.get("job_numbers") or self._config.get("job_number"))

    @property
    def branches(self) -> set[str]:
        return set(_strings(self._config.get("branches") or self._config.get("branch")))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.project_slug or not self.job_numbers:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for job_number in self.job_numbers:
                if len(signals) >= limit:
                    break
                artifacts = await self._fetch_job_artifacts(
                    client,
                    job_number=job_number,
                    limit=limit - len(signals),
                )
                if artifacts is None:
                    return []
                signals.extend(
                    _artifact_signal(artifact, self.project_slug, job_number, self.name)
                    for artifact in artifacts
                    if isinstance(artifact, dict)
                )
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_job_artifacts(
        self,
        client: httpx.AsyncClient,
        *,
        job_number: str,
        limit: int,
    ) -> list[dict[str, Any]] | None:
        artifacts: list[dict[str, Any]] = []
        page_token: str | None = None
        while len(artifacts) < limit:
            body = await self._get(
                client,
                f"{self.api_url}/project/{self.project_slug}/{job_number}/artifacts",
                params=self._params(page_token=page_token),
            )
            if body is None:
                return None
            items = body.get("items") if isinstance(body, dict) else []
            if not isinstance(items, list) or not items:
                break
            for item in items:
                if len(artifacts) >= limit:
                    break
                if isinstance(item, dict) and self._matches_branch(item):
                    artifacts.append(item)
            page_token = _optional(body.get("next_page_token"))
            if not page_token:
                break
        return artifacts[:limit]

    def _params(self, *, page_token: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {"page-size": self.page_size}
        if page_token:
            params["page-token"] = page_token
        return params

    def _matches_branch(self, artifact: dict[str, Any]) -> bool:
        branches = self.branches
        if not branches:
            return True
        branch = _artifact_branch(artifact)
        return not branch or branch in branches

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
            logger.warning("CircleCI job artifacts fetch failed for %s", url, exc_info=True)
            return None
        return body if isinstance(body, dict) else {}


CircleCIJobArtifactsAdapter = CircleCIJobArtifactsImportAdapter


def _artifact_signal(
    artifact: dict[str, Any],
    project_slug: str,
    job_number: str,
    adapter_name: str,
) -> Signal:
    path = _text(artifact.get("path")) or "artifact"
    url = _text(artifact.get("url"))
    branch = _artifact_branch(artifact)
    build_number = artifact.get("build_num") or artifact.get("build_number") or artifact.get("build")
    node_index = artifact.get("node_index")
    return Signal(
        id=f"circleci-artifact:{project_slug}:{job_number}:{node_index}:{path}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{project_slug} job #{job_number} artifact: {path}",
        content=_artifact_content(artifact),
        url=url,
        author=_optional(artifact.get("username") or artifact.get("user")),
        published_at=_parse_dt(artifact.get("created_at") or artifact.get("updated_at")),
        tags=sorted({"circleci", "artifact", project_slug, branch} - {""})[:10],
        credibility=0.65,
        metadata={
            "artifact_path": path,
            "node_index": node_index,
            "url": url,
            "job_number": job_number,
            "project_slug": project_slug,
            "branch": branch,
            "build_number": build_number,
            "build_url": artifact.get("build_url"),
            "workflow_id": artifact.get("workflow_id"),
            "job_name": artifact.get("job_name"),
            "pretty_path": artifact.get("pretty_path"),
            "raw": artifact,
        },
    )


def _artifact_content(artifact: dict[str, Any]) -> str:
    parts = [_text(artifact.get("path")) or "CircleCI artifact"]
    node_index = artifact.get("node_index")
    if node_index is not None:
        parts.append(f"node {node_index}")
    branch = _artifact_branch(artifact)
    if branch:
        parts.append(f"branch {branch}")
    return " | ".join(parts)[:1000]


def _artifact_branch(artifact: dict[str, Any]) -> str:
    branch = _optional(artifact.get("branch"))
    if branch:
        return branch
    vcs = artifact.get("vcs") if isinstance(artifact.get("vcs"), dict) else {}
    branch = _optional(vcs.get("branch"))
    if branch:
        return branch
    build_parameters = (
        artifact.get("build_parameters")
        if isinstance(artifact.get("build_parameters"), dict)
        else {}
    )
    return _text(build_parameters.get("CIRCLE_BRANCH") or build_parameters.get("branch"))


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
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",")]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

"""Azure DevOps git commits import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class AzureDevOpsGitCommitsAdapter(SourceAdapter):
    """Import Azure DevOps git commits as roadmap signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        organization: str | None = None,
        project: str | None = None,
        repository_id: str | None = None,
        personal_access_token: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.organization = organization or _optional(self._config.get("organization")) or os.getenv("AZURE_DEVOPS_ORGANIZATION") or ""
        self.project = project or _optional(self._config.get("project")) or os.getenv("AZURE_DEVOPS_PROJECT") or ""
        self.repository_id = (
            repository_id
            or _optional(self._config.get("repository_id"))
            or _optional(self._config.get("repository"))
            or os.getenv("AZURE_DEVOPS_REPOSITORY_ID")
            or os.getenv("AZURE_DEVOPS_REPOSITORY")
            or ""
        )
        configured_token = personal_access_token if personal_access_token is not None else token
        self.personal_access_token = (
            configured_token
            if configured_token is not None
            else (
                _optional(self._config.get("personal_access_token"))
                or _optional(self._config.get("pat"))
                or _optional(self._config.get("token"))
                or os.getenv("AZURE_DEVOPS_PAT")
                or os.getenv("AZURE_DEVOPS_TOKEN")
            )
        )
        self.bearer_token = (
            _optional(self._config.get("bearer_token"))
            or os.getenv("AZURE_DEVOPS_BEARER_TOKEN")
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or "https://dev.azure.com").rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "azure_devops_git_commits_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def api_version(self) -> str:
        return _text(self._config.get("api_version")) or "7.1"

    @property
    def branch(self) -> str:
        return _text(self._config.get("branch") or self._config.get("ref") or self._config.get("source_branch"))

    @property
    def from_date(self) -> str:
        return _text(self._config.get("from_date") or self._config.get("fromDate"))

    @property
    def to_date(self) -> str:
        return _text(self._config.get("to_date") or self._config.get("toDate"))

    @property
    def page_size(self) -> int:
        return _positive_int(
            self._config.get("page_size") or self._config.get("per_page"),
            default=100,
            maximum=500,
        )

    @property
    def use_bearer_token(self) -> bool:
        auth_type = _text(
            self._config.get("auth_type")
            or self._config.get("auth_scheme")
            or self._config.get("token_type")
        ).lower()
        return bool(self.bearer_token) or auth_type in {"bearer", "oauth", "oauth2"}

    @property
    def effective_token(self) -> str:
        return self.bearer_token if self.use_bearer_token else _text(self.personal_access_token)

    @property
    def base_url(self) -> str:
        return f"{self.api_url}/{self.organization}/{self.project}".rstrip("/")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (
            self.organization
            and self.project
            and self.repository_id
            and self.effective_token
        ):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            commits = await self._fetch_commits(client, limit=limit)
            return [
                _commit_signal(
                    commit,
                    adapter_name=self.name,
                    organization=self.organization,
                    project=self.project,
                    repository_id=self.repository_id,
                    branch=self.branch,
                    from_date=self.from_date,
                    to_date=self.to_date,
                )
                for commit in commits[:limit]
            ]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_commits(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        commits: list[dict[str, Any]] = []
        continuation_token: str | None = None
        while len(commits) < limit:
            page_size = min(self.page_size, limit - len(commits))
            body, continuation_token = await self._fetch_page(
                client,
                page_size=page_size,
                continuation_token=continuation_token,
            )
            if body is None:
                return []
            if not body:
                break
            commits.extend(body)
            if not continuation_token or len(body) < page_size:
                break
        return commits[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        page_size: int,
        continuation_token: str | None,
    ) -> tuple[list[dict[str, Any]] | None, str | None]:
        params: dict[str, Any] = {"api-version": self.api_version, "searchCriteria.$top": page_size}
        if continuation_token:
            params["continuationToken"] = continuation_token
        if self.branch:
            params["searchCriteria.itemVersion.version"] = self.branch.removeprefix("refs/heads/")
            params["searchCriteria.itemVersion.versionType"] = "branch"
        if self.from_date:
            params["searchCriteria.fromDate"] = self.from_date
        if self.to_date:
            params["searchCriteria.toDate"] = self.to_date

        try:
            response = await client.get(
                f"{self.base_url}/_apis/git/repositories/{self.repository_id}/commits",
                auth=None if self.use_bearer_token else ("", self.personal_access_token or ""),
                headers=self._headers(),
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Azure DevOps git commits fetch failed for repository %s", self.repository_id, exc_info=True)
            return None, None
        values = body.get("value") if isinstance(body, dict) else body
        if not isinstance(values, list):
            return None, None
        next_token = (
            response.headers.get("x-ms-continuationtoken")
            or response.headers.get("X-MS-ContinuationToken")
            or response.headers.get("continuationToken")
        )
        return [item for item in values if isinstance(item, dict)], _optional(next_token)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "max-azure-devops-git-commits-import/1",
        }
        if self.use_bearer_token:
            headers["Authorization"] = f"Bearer {self.effective_token}"
        return headers


AzureDevOpsGitCommitAdapter = AzureDevOpsGitCommitsAdapter


def _commit_signal(
    commit: dict[str, Any],
    *,
    adapter_name: str,
    organization: str,
    project: str,
    repository_id: str,
    branch: str,
    from_date: str,
    to_date: str,
) -> Signal:
    commit_id = _text(commit.get("commitId") or commit.get("commit_id") or commit.get("id"))
    comment = _text(commit.get("comment"))
    author = _identity(commit.get("author"))
    committer = _identity(commit.get("committer"))
    change_counts = commit.get("changeCounts") if isinstance(commit.get("changeCounts"), dict) else {}
    remote_url = _text(commit.get("remoteUrl") or commit.get("remote_url"))
    web_url = _web_url(commit, remote_url, organization, project, repository_id, commit_id)
    title = _first_line(comment) or commit_id or "Azure DevOps commit"
    return Signal(
        id=f"azure-devops-commit:{organization}/{project}/{repository_id}:{commit_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{project} commit {commit_id[:8]}: {title}" if commit_id else title,
        content=comment[:1000],
        url=web_url,
        author=author.get("name") or author.get("email"),
        published_at=_parse_dt(author.get("date") or committer.get("date")),
        tags=sorted({"azure-devops", "commit", branch} - {""})[:10],
        credibility=0.7,
        metadata={
            "organization": organization,
            "project": project,
            "repository_id": repository_id,
            "commit_id": commit_id,
            "comment": comment,
            "author": author,
            "committer": committer,
            "author_date": author.get("date"),
            "committer_date": committer.get("date"),
            "change_counts": {
                "add": _int(change_counts.get("Add")),
                "edit": _int(change_counts.get("Edit")),
                "delete": _int(change_counts.get("Delete")),
            },
            "branch": branch,
            "from_date": from_date,
            "to_date": to_date,
            "remote_url": remote_url,
            "url": _text(commit.get("url")),
            "web_url": web_url,
            "parents": commit.get("parents") if isinstance(commit.get("parents"), list) else [],
            "raw": commit,
        },
    )


def _identity(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "name": value.get("name"),
            "email": value.get("email"),
            "date": value.get("date"),
            "image_url": value.get("imageUrl"),
        }
    text = _text(value)
    return {"name": text, "email": None, "date": None, "image_url": None} if text else {}


def _web_url(
    commit: dict[str, Any],
    remote_url: str,
    organization: str,
    project: str,
    repository_id: str,
    commit_id: str,
) -> str:
    links = commit.get("_links") if isinstance(commit.get("_links"), dict) else {}
    web = links.get("web") if isinstance(links.get("web"), dict) else {}
    href = _text(web.get("href"))
    if href:
        return href
    if remote_url:
        return remote_url
    if commit_id:
        return f"https://dev.azure.com/{organization}/{project}/_git/{repository_id}/commit/{commit_id}"
    return ""


def _first_line(value: object) -> str:
    text = _text(value)
    return text.splitlines()[0].strip() if text else ""


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
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

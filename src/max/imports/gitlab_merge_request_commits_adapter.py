"""GitLab merge request commits import adapter."""

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


class GitLabMergeRequestCommitsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        gitlab_url: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            token
            if token is not None
            else (
                _optional(self._config.get("private_token"))
                or _optional(self._config.get("token"))
                or os.getenv("GITLAB_PRIVATE_TOKEN")
                or os.getenv("GITLAB_TOKEN")
            )
        )
        configured_url = (
            api_url
            or _optional(self._config.get("api_url"))
            or gitlab_url
            or _optional(self._config.get("gitlab_url"))
            or os.getenv("GITLAB_API_URL")
            or GITLAB_API
        )
        self.api_url = _api_url(configured_url)
        self._client = client

    @property
    def name(self) -> str:
        return "gitlab_merge_request_commits_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def merge_requests(self) -> list[dict[str, str]]:
        configured = self._config.get("merge_requests")
        if configured is not None:
            return _configured_merge_requests(configured)
        project = (
            self._config.get("project_id")
            or self._config.get("project_path")
            or self._config.get("project")
        )
        projects = _strings(
            self._config.get("project_ids")
            or self._config.get("project_paths")
            or self._config.get("projects")
            or project
        )
        iids = _strings(
            self._config.get("merge_request_iids")
            or self._config.get("merge_requests_iids")
            or self._config.get("merge_request_iid")
            or self._config.get("iid")
        )
        return [{"project_id": project_id, "iid": iid} for project_id in projects for iid in iids]

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page"), default=30, maximum=100)

    @property
    def since(self) -> str | None:
        return _optional(self._config.get("since"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.merge_requests:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            rows: list[tuple[dict[str, str], dict[str, Any]]] = []
            for merge_request in self.merge_requests:
                if len(rows) >= limit:
                    break
                commits = await self._fetch_commits(
                    client,
                    merge_request=merge_request,
                    limit=limit - len(rows),
                )
                if commits is None:
                    return []
                rows.extend((merge_request, commit) for commit in commits)
            return [_commit_signal(mr, commit, self.name) for mr, commit in rows[:limit]]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_commits(
        self,
        client: httpx.AsyncClient,
        *,
        merge_request: dict[str, str],
        limit: int,
    ) -> list[dict[str, Any]] | None:
        commits: list[dict[str, Any]] = []
        page = 1
        while len(commits) < limit:
            page_size = min(self.per_page, limit - len(commits))
            body, next_page = await self._fetch_page(
                client,
                merge_request=merge_request,
                page=page,
                page_size=page_size,
            )
            if body is None:
                return None
            if not body:
                break
            commits.extend(body)
            if not next_page and len(body) < page_size:
                break
            page = next_page or page + 1
        return commits[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        merge_request: dict[str, str],
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]] | None, int | None]:
        project_id = merge_request["project_id"]
        iid = merge_request["iid"]
        url = (
            f"{self.api_url}/projects/{quote(project_id, safe='')}"
            f"/merge_requests/{quote(iid, safe='')}/commits"
        )
        params: dict[str, Any] = {"page": page, "per_page": page_size}
        if self.since:
            params["since"] = self.since
        try:
            response = await client.get(
                url,
                headers={
                    "PRIVATE-TOKEN": self.token or "",
                    "Accept": "application/json",
                    "User-Agent": "max-gitlab-merge-request-commits-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitLab merge request commits fetch failed for %s !%s", project_id, iid, exc_info=True)
            return None, None
        next_page = _positive_int(response.headers.get("X-Next-Page"), default=0, maximum=1_000_000) or None
        return ([item for item in body if isinstance(item, dict)] if isinstance(body, list) else []), next_page


GitLabMergeRequestCommitAdapter = GitLabMergeRequestCommitsAdapter


def _commit_signal(
    merge_request: dict[str, str],
    commit: dict[str, Any],
    adapter_name: str,
) -> Signal:
    project_id = merge_request["project_id"]
    iid = merge_request["iid"]
    sha = _text(commit.get("id") or commit.get("sha"))
    short_id = _text(commit.get("short_id"))
    title = _text(commit.get("title")) or _first_line(commit.get("message")) or short_id or sha
    message = _text(commit.get("message"))
    author_name = _optional(commit.get("author_name") or commit.get("author_email"))
    committed_date = commit.get("committed_date") or commit.get("created_at")
    web_url = _text(commit.get("web_url") or commit.get("url"))
    return Signal(
        id=f"gitlab-mr-commit:{project_id}:{iid}:{sha or short_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{project_id} !{iid} commit {short_id or sha}: {title}",
        content=(message or title)[:1000],
        url=web_url,
        author=author_name,
        published_at=_parse_dt(committed_date),
        tags=sorted({"gitlab", "merge-request", "commit", project_id} - {""})[:10],
        credibility=0.65,
        metadata={
            "project_id": project_id,
            "merge_request_iid": iid,
            "sha": sha,
            "short_id": short_id,
            "title": title,
            "message": message,
            "author_name": commit.get("author_name"),
            "author_email": commit.get("author_email"),
            "authored_date": commit.get("authored_date"),
            "committer_name": commit.get("committer_name"),
            "committer_email": commit.get("committer_email"),
            "committed_date": committed_date,
            "created_at": commit.get("created_at"),
            "web_url": web_url,
            "parent_ids": commit.get("parent_ids"),
            "trailers": commit.get("trailers"),
            "extended_trailers": commit.get("extended_trailers"),
            "raw": commit,
        },
    )


def _api_url(value: str) -> str:
    url = value.rstrip("/")
    return f"{url}/api/v4" if not url.endswith("/api/v4") else url


def _configured_merge_requests(value: object) -> list[dict[str, str]]:
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []
    merge_requests: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        project_id = _optional(item.get("project_id") or item.get("project_path") or item.get("project"))
        iid = _optional(item.get("iid") or item.get("merge_request_iid"))
        if project_id and iid:
            merge_requests.append({"project_id": project_id, "iid": iid})
    return merge_requests


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

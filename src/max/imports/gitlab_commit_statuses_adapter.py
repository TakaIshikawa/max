"""GitLab commit statuses import adapter."""

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


class GitLabCommitStatusesAdapter(SourceAdapter):
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
        return "gitlab_commit_statuses_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def project_ids(self) -> list[str]:
        return _strings(
            self._config.get("project_ids")
            or self._config.get("projects")
            or self._config.get("project_id")
        )

    @property
    def commit_shas(self) -> list[str]:
        return _strings(
            self._config.get("commit_shas")
            or self._config.get("commits_sha")
            or self._config.get("commit_sha")
            or self._config.get("shas")
        )

    @property
    def commits(self) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for commit in _list(self._config.get("commits") or self._config.get("commit_statuses")):
            if isinstance(commit, dict):
                project_id = _optional(
                    commit.get("project_id")
                    or commit.get("project")
                    or commit.get("project_path")
                    or commit.get("id")
                )
                commit_sha = _optional(
                    commit.get("commit_sha")
                    or commit.get("sha")
                    or commit.get("commit")
                    or commit.get("ref")
                )
                if project_id and commit_sha:
                    pairs.append((project_id, commit_sha))

        for project_id in self.project_ids:
            for commit_sha in self.commit_shas:
                pairs.append((project_id, commit_sha))
        return _dedupe_pairs(pairs)

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        commits = self.commits
        if limit <= 0 or not self.token or not commits:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for project_id, commit_sha in commits:
                if len(signals) >= limit:
                    break
                statuses = await self._fetch_statuses(
                    client,
                    project_id=project_id,
                    commit_sha=commit_sha,
                    limit=limit - len(signals),
                )
                signals.extend(
                    _status_signal(
                        status,
                        project_id=project_id,
                        commit_sha=commit_sha,
                        adapter_name=self.name,
                    )
                    for status in statuses
                    if isinstance(status, dict)
                )
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_statuses(
        self,
        client: httpx.AsyncClient,
        *,
        project_id: str,
        commit_sha: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        statuses: list[dict[str, Any]] = []
        page = 1
        while len(statuses) < limit:
            page_size = min(self.page_size, limit - len(statuses))
            page_statuses, next_page = await self._fetch_page(
                client,
                project_id=project_id,
                commit_sha=commit_sha,
                page=page,
                page_size=page_size,
            )
            if not page_statuses:
                break
            statuses.extend(page_statuses[: limit - len(statuses)])
            if next_page:
                page = next_page
            else:
                break
        return statuses[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        project_id: str,
        commit_sha: str,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int | None]:
        url = (
            f"{self.api_url}/projects/{_encode_project(project_id)}"
            f"/repository/commits/{quote(commit_sha, safe='')}/statuses"
        )
        try:
            response = await client.get(
                url,
                headers={
                    "PRIVATE-TOKEN": self.token or "",
                    "Accept": "application/json",
                    "User-Agent": "max-gitlab-commit-statuses-import/1",
                },
                params={"page": page, "per_page": page_size},
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitLab commit statuses fetch failed for %s commit %s", project_id, commit_sha, exc_info=True)
            return [], None
        statuses = [item for item in body if isinstance(item, dict)] if isinstance(body, list) else []
        return statuses, _next_page(response)


GitLabCommitStatusAdapter = GitLabCommitStatusesAdapter


def _status_signal(
    status: dict[str, Any],
    *,
    project_id: str,
    commit_sha: str,
    adapter_name: str,
) -> Signal:
    status_id = _text(status.get("id"))
    name = _text(status.get("name")) or _text(status.get("context")) or status_id or "GitLab commit status"
    state = _normalized_status(status.get("status"))
    stage = _text(status.get("stage"))
    ref = _text(status.get("ref"))
    target_url = _text(status.get("target_url"))
    author = status.get("author") if isinstance(status.get("author"), dict) else {}
    commit = status.get("commit") if isinstance(status.get("commit"), dict) else {}
    resolved_sha = _text(status.get("sha")) or _text(commit.get("id")) or commit_sha
    stable_status_id = status_id or _stable_status_key(status, name=name, state=state)
    return Signal(
        id=f"gitlab-commit-status:{project_id}:{commit_sha}:{stable_status_id}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{name} {state or 'unknown'}",
        content=_content(name=name, state=state, stage=stage, ref=ref),
        url=target_url or _text(status.get("web_url")),
        author=_optional(author.get("username") or author.get("name") or status.get("author")),
        published_at=_parse_dt(status.get("created_at") or status.get("started_at") or status.get("finished_at")),
        tags=sorted({"gitlab", "commit", "status", state, stage, ref} - {""})[:10],
        credibility=0.7,
        metadata={
            "gitlab_status_id": status.get("id"),
            "project_id": project_id,
            "commit_sha": resolved_sha,
            "configured_commit_sha": commit_sha,
            "ref": ref or None,
            "stage": stage or None,
            "status": state or status.get("status"),
            "name": name,
            "target_url": target_url or None,
            "author": _summary(author, ("id", "username", "name", "web_url", "avatar_url")),
            "created_at": status.get("created_at"),
            "started_at": status.get("started_at"),
            "finished_at": status.get("finished_at"),
            "allow_failure": status.get("allow_failure"),
            "description": status.get("description"),
            "commit": _summary(commit, ("id", "short_id", "title", "message", "author_name", "web_url")),
            "raw": status,
        },
    )


def _content(*, name: str, state: str, stage: str, ref: str) -> str:
    parts = [f"GitLab commit status {name}"]
    if state:
        parts.append(f"status {state}")
    if stage:
        parts.append(f"stage {stage}")
    if ref:
        parts.append(f"ref {ref}")
    return "; ".join(parts)


def _api_url(value: str) -> str:
    url = value.strip().rstrip("/")
    if not url.endswith("/api/v4"):
        url = f"{url}/api/v4"
    return url


def _dedupe_pairs(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for project_id, commit_sha in pairs:
        pair = (_text(project_id), _text(commit_sha))
        if not all(pair) or pair in seen:
            continue
        seen.add(pair)
        deduped.append(pair)
    return deduped


def _encode_project(project: str) -> str:
    return quote(unquote(str(project).strip()), safe="")


def _list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list | tuple | set):
        return list(value)
    return [value]


def _next_page(response: httpx.Response) -> int | None:
    value = _optional(response.headers.get("X-Next-Page"))
    if not value:
        return None
    try:
        number = int(value)
    except ValueError:
        return None
    return number if number > 0 else None


def _normalized_status(value: object) -> str:
    return _text(value).lower()


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


def _stable_status_key(status: dict[str, Any], *, name: str, state: str) -> str:
    parts = (
        _text(status.get("sha")),
        _text(status.get("ref")),
        _text(status.get("stage")),
        name,
        state,
        _text(status.get("target_url")),
        _text(status.get("created_at")),
        _text(status.get("started_at")),
        _text(status.get("finished_at")),
    )
    return quote(":".join(part for part in parts if part), safe="")


def _strings(value: object) -> list[str]:
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        value = [value]
    if not isinstance(value, list | tuple | set):
        return []
    strings: list[str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, bool):
            continue
        if isinstance(item, dict):
            item = item.get("id") or item.get("sha") or item.get("path")
        text = _text(item)
        if text and text not in seen:
            seen.add(text)
            strings.append(text)
    return strings


def _summary(value: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: value.get(key) for key in keys if value.get(key) is not None}


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

"""GitLab issue discussions import adapter."""

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


class GitLabIssueDiscussionsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        private_token: str | None = None,
        gitlab_url: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = private_token if private_token is not None else (
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
        return "gitlab_issue_discussions_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def issues(self) -> list[dict[str, str]]:
        configured = self._config.get("issues")
        if configured is not None and isinstance(configured, (dict, list)):
            structured = _configured_issues(configured)
            if structured:
                return structured
        project = self._config.get("project_id") or self._config.get("project_path") or self._config.get("project")
        projects = _strings(
            self._config.get("project_ids")
            or self._config.get("project_paths")
            or self._config.get("projects")
            or project
        )
        iids = _strings(
            self._config.get("issue_iids")
            or self._config.get("iids")
            or self._config.get("issue_iid")
            or self._config.get("iid")
        )
        return [{"project_id": project_id, "issue_iid": iid} for project_id in projects for iid in iids]

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.issues:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            rows: list[tuple[dict[str, str], dict[str, Any], dict[str, Any]]] = []
            for issue in self.issues:
                if len(rows) >= limit:
                    break
                discussions = await self._fetch_discussions(client, issue=issue, limit=limit - len(rows))
                if discussions is None:
                    return []
                for discussion in discussions:
                    notes = discussion.get("notes") if isinstance(discussion.get("notes"), list) else []
                    for note in notes:
                        if isinstance(note, dict):
                            rows.append((issue, discussion, note))
                        if len(rows) >= limit:
                            break
                    if len(rows) >= limit:
                        break
            return [_note_signal(issue, discussion, note, self.name) for issue, discussion, note in rows[:limit]]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_discussions(
        self,
        client: httpx.AsyncClient,
        *,
        issue: dict[str, str],
        limit: int,
    ) -> list[dict[str, Any]] | None:
        discussions: list[dict[str, Any]] = []
        page = 1
        while len(discussions) < limit:
            page_size = min(self.per_page, limit - len(discussions))
            body, next_page = await self._fetch_page(client, issue=issue, page=page, page_size=page_size)
            if body is None:
                return None
            if not body:
                break
            discussions.extend(body)
            if not next_page and len(body) < page_size:
                break
            page = next_page or page + 1
        return discussions[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        issue: dict[str, str],
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]] | None, int | None]:
        project_id = issue["project_id"]
        issue_iid = issue["issue_iid"]
        url = f"{self.api_url}/projects/{quote(project_id, safe='')}/issues/{quote(issue_iid, safe='')}/discussions"
        try:
            response = await client.get(
                url,
                headers={
                    "PRIVATE-TOKEN": self.token or "",
                    "Accept": "application/json",
                    "User-Agent": "max-gitlab-issue-discussions-import/1",
                },
                params={"page": page, "per_page": page_size},
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitLab issue discussions fetch failed for %s #%s", project_id, issue_iid, exc_info=True)
            return None, None
        next_page = _positive_int(response.headers.get("X-Next-Page"), default=0, maximum=1_000_000) or None
        return ([item for item in body if isinstance(item, dict)] if isinstance(body, list) else []), next_page


GitLabIssueDiscussionAdapter = GitLabIssueDiscussionsAdapter


def _note_signal(issue: dict[str, str], discussion: dict[str, Any], note: dict[str, Any], adapter_name: str) -> Signal:
    project_id = issue["project_id"]
    issue_iid = issue["issue_iid"]
    author_data = note.get("author") if isinstance(note.get("author"), dict) else {}
    note_id = _text(note.get("id")) or _text(note.get("noteable_id")) or _text(note.get("created_at"))
    system_tag = "system" if note.get("system") is True else "comment"
    resolvable_tag = "resolvable" if note.get("resolvable") is True else ""
    return Signal(
        id=f"gitlab-issue-discussion-note:{project_id}:{issue_iid}:{discussion.get('id')}:{note_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{project_id} issue #{issue_iid} discussion note",
        content=_text(note.get("body"))[:1000],
        url=_text(note.get("url")),
        author=_optional(author_data.get("username") or author_data.get("name")),
        published_at=_parse_dt(note.get("created_at")),
        tags=sorted({"gitlab", "issue", "discussion", system_tag, resolvable_tag} - {""})[:10],
        credibility=0.65,
        metadata={
            "project_id": project_id,
            "issue_iid": issue_iid,
            "discussion_id": discussion.get("id"),
            "individual_note": discussion.get("individual_note"),
            "note_id": note.get("id"),
            "noteable_id": note.get("noteable_id"),
            "noteable_type": note.get("noteable_type"),
            "system": note.get("system"),
            "resolvable": note.get("resolvable"),
            "resolved": note.get("resolved"),
            "author": _user_summary(author_data),
            "created_at": note.get("created_at"),
            "updated_at": note.get("updated_at"),
            "raw_discussion": discussion,
            "raw": note,
        },
    )


def _api_url(value: str) -> str:
    url = value.rstrip("/")
    return f"{url}/api/v4" if not url.endswith("/api/v4") else url


def _configured_issues(value: object) -> list[dict[str, str]]:
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []
    issues: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        project_id = _optional(item.get("project_id") or item.get("project_path") or item.get("project"))
        issue_iid = _optional(item.get("issue_iid") or item.get("iid"))
        if project_id and issue_iid:
            issues.append({"project_id": project_id, "issue_iid": issue_iid})
    return issues


def _user_summary(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": value.get("id"),
        "username": value.get("username"),
        "name": value.get("name"),
        "web_url": value.get("web_url"),
        "avatar_url": value.get("avatar_url"),
    }


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

"""Azure DevOps pull request threads import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class AzureDevOpsPullRequestThreadsAdapter(SourceAdapter):
    """Import Azure DevOps pull request discussion threads as Max signals."""

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
        self.repository_id = repository_id or _optional(self._config.get("repository_id")) or _optional(self._config.get("repository")) or ""
        configured_token = personal_access_token if personal_access_token is not None else token
        self.personal_access_token = (
            configured_token
            if configured_token is not None
            else (
                _optional(self._config.get("personal_access_token"))
                or _optional(self._config.get("token"))
                or os.getenv("AZURE_DEVOPS_PAT")
                or os.getenv("AZURE_DEVOPS_TOKEN")
            )
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or "https://dev.azure.com").rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "azure_devops_pull_request_threads_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def api_version(self) -> str:
        return _text(self._config.get("api_version")) or "7.1"

    @property
    def pull_request_ids(self) -> list[int]:
        return [_id for _id in (_int(value) for value in _list(self._config.get("pull_request_ids") or self._config.get("pull_request_id"))) if _id]

    @property
    def include_resolved(self) -> bool:
        return _bool(self._config.get("include_resolved") or self._config.get("include_closed"))

    @property
    def per_pr_limit(self) -> int | None:
        value = self._config.get("per_pr_limit")
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    @property
    def base_url(self) -> str:
        return f"{self.api_url}/{self.organization}/{self.project}".rstrip("/")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (
            self.organization
            and self.project
            and self.repository_id
            and self.personal_access_token
            and self.pull_request_ids
        ):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for pull_request_id in self.pull_request_ids:
                if len(signals) >= limit:
                    break
                pr_limit = limit - len(signals)
                if self.per_pr_limit:
                    pr_limit = min(pr_limit, self.per_pr_limit)
                threads = await self._fetch_threads(client, pull_request_id=pull_request_id)
                for thread in threads:
                    if not self.include_resolved and _is_resolved(thread):
                        continue
                    for signal in _thread_signals(
                        thread,
                        adapter_name=self.name,
                        organization=self.organization,
                        project=self.project,
                        repository_id=self.repository_id,
                        pull_request_id=pull_request_id,
                    ):
                        signals.append(signal)
                        if len(signals) >= limit or sum(1 for item in signals if item.metadata.get("pull_request_id") == pull_request_id) >= pr_limit:
                            break
                    if len(signals) >= limit or sum(1 for item in signals if item.metadata.get("pull_request_id") == pull_request_id) >= pr_limit:
                        break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_threads(self, client: httpx.AsyncClient, *, pull_request_id: int) -> list[dict[str, Any]]:
        try:
            response = await client.get(
                (
                    f"{self.base_url}/_apis/git/repositories/{self.repository_id}"
                    f"/pullRequests/{pull_request_id}/threads"
                ),
                auth=("", self.personal_access_token or ""),
                params={"api-version": self.api_version},
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Azure DevOps pull request threads fetch failed for PR %s", pull_request_id, exc_info=True)
            return []
        values = body.get("value") if isinstance(body, dict) else body
        return [item for item in values if isinstance(item, dict)] if isinstance(values, list) else []


AzureDevOpsPullRequestThreadAdapter = AzureDevOpsPullRequestThreadsAdapter


def _thread_signals(
    thread: dict[str, Any],
    *,
    adapter_name: str,
    organization: str,
    project: str,
    repository_id: str,
    pull_request_id: int,
) -> list[Signal]:
    thread_id = _text(thread.get("id"))
    status = _text(thread.get("status"))
    comments = thread.get("comments") if isinstance(thread.get("comments"), list) else []
    context = _thread_context(thread)
    signals: list[Signal] = []
    for comment in comments:
        if not isinstance(comment, dict) or comment.get("isDeleted"):
            continue
        comment_id = _text(comment.get("id"))
        if not comment_id:
            continue
        author = _identity(comment.get("author"))
        content = _text(comment.get("content"))
        url = _thread_url(organization, project, repository_id, pull_request_id, thread_id)
        signals.append(
            Signal(
                id=f"azure-devops-pr-thread-comment:{organization}/{project}/{repository_id}:{pull_request_id}:{thread_id}:{comment_id}",
                source_type=SignalSourceType.ROADMAP,
                source_adapter=adapter_name,
                title=f"{project} PR {pull_request_id} thread {thread_id} comment",
                content=content[:1000],
                url=url,
                author=author.get("displayName") or author.get("uniqueName"),
                published_at=_parse_dt(comment.get("publishedDate") or comment.get("lastUpdatedDate")),
                tags=sorted({"azure-devops", "pull-request-thread", status, _text(context.get("file_path"))} - {""})[:10],
                credibility=0.65,
                metadata={
                    "organization": organization,
                    "project": project,
                    "repository_id": repository_id,
                    "pull_request_id": pull_request_id,
                    "thread_id": thread.get("id"),
                    "comment_id": comment.get("id"),
                    "status": thread.get("status"),
                    "is_resolved": _is_resolved(thread),
                    "author": author,
                    "content": content,
                    "comment_type": comment.get("commentType"),
                    "published_date": comment.get("publishedDate"),
                    "last_updated_date": comment.get("lastUpdatedDate"),
                    "file_path": context.get("file_path"),
                    "right_file_start": context.get("right_file_start"),
                    "right_file_end": context.get("right_file_end"),
                    "left_file_start": context.get("left_file_start"),
                    "left_file_end": context.get("left_file_end"),
                    "thread_context": thread.get("threadContext") if isinstance(thread.get("threadContext"), dict) else {},
                    "pull_request_thread_context": (
                        thread.get("pullRequestThreadContext")
                        if isinstance(thread.get("pullRequestThreadContext"), dict)
                        else {}
                    ),
                    "properties": thread.get("properties") if isinstance(thread.get("properties"), dict) else {},
                    "web_url": url,
                    "raw": {"thread": thread, "comment": comment},
                },
            )
        )
    return signals


def _thread_context(thread: dict[str, Any]) -> dict[str, Any]:
    context = thread.get("threadContext") if isinstance(thread.get("threadContext"), dict) else {}
    return {
        "file_path": context.get("filePath"),
        "right_file_start": _position(context.get("rightFileStart")),
        "right_file_end": _position(context.get("rightFileEnd")),
        "left_file_start": _position(context.get("leftFileStart")),
        "left_file_end": _position(context.get("leftFileEnd")),
    }


def _position(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {"line": value.get("line"), "offset": value.get("offset")}


def _thread_url(organization: str, project: str, repository_id: str, pull_request_id: int, thread_id: str) -> str:
    return (
        f"https://dev.azure.com/{organization}/{project}/_git/{repository_id}"
        f"/pullrequest/{pull_request_id}?_a=files&discussionId={thread_id}"
    )


def _is_resolved(thread: dict[str, Any]) -> bool:
    status = _text(thread.get("status")).lower()
    return status in {"closed", "fixed", "wontfix", "bydesign", "unknown"} or bool(thread.get("isDeleted"))


def _identity(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return {"displayName": value.get("displayName"), "uniqueName": value.get("uniqueName"), "id": value.get("id")}
    text = _text(value)
    return {"displayName": text, "uniqueName": None, "id": None} if text else {}


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value is None:
        return []
    return [value]


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

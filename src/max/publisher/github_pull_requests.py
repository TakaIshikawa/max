"""GitHub pull request publisher for Max payloads."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

DEFAULT_GITHUB_API_URL = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS = 10.0


class GitHubPullRequestPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubPullRequestPayload:
    title: str
    body: str
    head: str
    base: str
    draft: bool
    maintainer_can_modify: bool
    labels: list[str]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "body": self.body,
            "head": self.head,
            "base": self.base,
            "draft": self.draft,
            "maintainer_can_modify": self.maintainer_can_modify,
            "labels": self.labels,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class GitHubPullRequestPublishResult:
    status_code: int | None
    repository: str
    pull_request_number: int | None
    pull_request_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class GitHubPullRequestPublisher:
    def __init__(
        self,
        repository: str,
        *,
        token: str | None = None,
        api_url: str = DEFAULT_GITHUB_API_URL,
        base: str = "main",
        head: str | None = None,
        draft: bool = False,
        maintainer_can_modify: bool = True,
        labels: list[str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.repository = _validate_repository(repository)
        self.token = token
        self.api_url = api_url.rstrip("/")
        self.base = _required(base, "GitHub PR base branch is required")
        self.head = head
        self.draft = draft
        self.maintainer_can_modify = maintainer_can_modify
        self.labels = labels or []
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> "GitHubPullRequestPublisher":
        repository = kwargs.pop("repository", None) or os.getenv("GITHUB_REPOSITORY")
        if not repository:
            raise GitHubPullRequestPublishError("GITHUB_REPOSITORY is required")
        draft_value = kwargs.pop("draft", None)
        return cls(
            repository,
            token=kwargs.pop("token", None) or os.getenv("GITHUB_TOKEN"),
            api_url=kwargs.pop("api_url", None) or os.getenv("GITHUB_API_URL", DEFAULT_GITHUB_API_URL),
            base=kwargs.pop("base", None) or os.getenv("GITHUB_PR_BASE", "main"),
            head=kwargs.pop("head", None) or os.getenv("GITHUB_PR_HEAD"),
            draft=_bool(os.getenv("GITHUB_PR_DRAFT")) if draft_value is None else bool(draft_value),
            **kwargs,
        )

    @property
    def pull_request_endpoint(self) -> str:
        return f"{self.api_url}/repos/{self.repository}/pulls"

    def build_payload(self, source: Any, *, head: str | None = None, base: str | None = None, labels: list[str] | None = None) -> GitHubPullRequestPayload:
        data = source if isinstance(source, dict) else _model_dict(source)
        source_block = data.get("source") if isinstance(data.get("source"), dict) else {}
        project = data.get("project") if isinstance(data.get("project"), dict) else {}
        title = _text(data.get("title") or project.get("title") or source_block.get("idea_id") or data.get("id") or "Max change")
        idea_id = _text(data.get("id") or source_block.get("idea_id"))
        resolved_head = _required(head or self.head or (f"max/{idea_id}" if idea_id else ""), "GitHub PR head branch is required")
        merged_labels = _unique([*_labels_from_source(data), *(labels or self.labels)])
        metadata = {
            "publisher": "max.github_pull_requests",
            "source_type": source_block.get("type") or ("tact_spec" if project else "buildable_unit"),
            "idea_id": idea_id or None,
            "schema_version": data.get("schema_version"),
            "kind": data.get("kind"),
            "repository": self.repository,
            "base": base or self.base,
            "head": resolved_head,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return GitHubPullRequestPayload(
            title=f"[Max] {title}",
            body=_body(data),
            head=resolved_head,
            base=base or self.base,
            draft=self.draft,
            maintainer_can_modify=self.maintainer_can_modify,
            labels=merged_labels,
            metadata=metadata,
        )

    def publish(self, source: Any, *, dry_run: bool = True, **kwargs: Any) -> GitHubPullRequestPublishResult:
        return self.publish_payload(self.build_payload(source, **kwargs).to_dict(), dry_run=dry_run)

    def publish_payload(self, payload: dict[str, Any], *, dry_run: bool = True) -> GitHubPullRequestPublishResult:
        if dry_run:
            return GitHubPullRequestPublishResult(None, self.repository, None, None, True, payload)
        if not self.token:
            raise GitHubPullRequestPublishError("GITHUB_TOKEN is required for live GitHub pull request publishing")
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.pull_request_endpoint,
                    json=_github_payload(payload),
                    headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "User-Agent": "max-github-pr-publisher/1", "X-GitHub-Api-Version": "2022-11-28"},
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise GitHubPullRequestPublishError(_redact(f"GitHub pull request publish failed for {self.pull_request_endpoint}: {exc}", self.token)) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise GitHubPullRequestPublishError(_redact(f"GitHub pull request publish failed with HTTP {response.status_code}: {response.text[:500]}", self.token), status_code=response.status_code)
        body = response.json()
        pr_url = body.get("html_url") if isinstance(body, dict) else None
        pr_number = body.get("number") if isinstance(body, dict) and isinstance(body.get("number"), int) else None
        return GitHubPullRequestPublishResult(response.status_code, self.repository, pr_number, str(pr_url) if pr_url else None, False, {**payload, "metadata": {**payload.get("metadata", {}), "github_pull_request_url": pr_url, "github_pull_request_number": pr_number}})


GitHubPullRequestsPublisher = GitHubPullRequestPublisher


def _github_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload[key] for key in ("title", "body", "head", "base", "draft", "maintainer_can_modify") if key in payload}


def _body(data: dict[str, Any]) -> str:
    return "\n".join(["# " + _text(data.get("title") or (data.get("project") or {}).get("title") or "Max change"), "", _text(data.get("one_liner") or (data.get("project") or {}).get("summary") or data.get("problem") or ""), "", "## Source", "```json", json.dumps(data, indent=2, sort_keys=True, default=str), "```"])


def _labels_from_source(data: dict[str, Any]) -> list[str]:
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    values = ["max", _text(data.get("category") or source.get("category")), _text(data.get("domain") or source.get("domain")), _text(data.get("status") or source.get("status"))]
    return [_label(value) for value in values if _label(value)]


def _model_dict(source: Any) -> dict[str, Any]:
    if hasattr(source, "model_dump"):
        return source.model_dump()
    if hasattr(source, "dict"):
        return source.dict()
    return dict(getattr(source, "__dict__", {}))


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        label = _label(value)
        if label and label not in result:
            result.append(label)
    return result


def _label(value: object) -> str:
    text = _text(value).lower().replace("_", "-").replace(" ", "-")
    return "".join(ch for ch in text if ch.isalnum() or ch in "-./")[:50]


def _bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _redact(message: str, token: str | None) -> str:
    if token:
        message = message.replace(token, "[redacted]")
    return re.sub(r"(https?://)[^/@\s]+@", r"\1***@", message)


def _required(value: str | None, message: str) -> str:
    text = _text(value)
    if not text:
        raise GitHubPullRequestPublishError(message)
    return text


def _validate_repository(repository: str) -> str:
    value = repository.strip()
    if value.count("/") != 1 or any(not part for part in value.split("/", 1)):
        raise GitHubPullRequestPublishError("GitHub repository must be in owner/repo format")
    return value


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""

"""GitHub commit status publisher for generated TactSpec readiness."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, dict_value, metadata, optional_text, redact_text, required_text, required_url, response_json, response_preview, title, validate_tact_spec

DEFAULT_API_URL = "https://api.github.com"
DEFAULT_CONTEXT = "max/tactspec-readiness"
ALLOWED_STATES = {"error", "failure", "pending", "success"}


class GitHubCommitStatusPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubCommitStatusPayload:
    repository: str
    sha: str
    status: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"repository": self.repository, "sha": self.sha, "status": self.status, "metadata": self.metadata}


@dataclass(frozen=True)
class GitHubCommitStatusPublishResult:
    status_code: int | None
    status_id: str | None
    status_url: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class GitHubCommitStatusPublisher:
    def __init__(
        self,
        *,
        token: str | None = None,
        repository: str | None = None,
        sha: str | None = None,
        context: str | None = None,
        api_url: str = DEFAULT_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.token = optional_text(token)
        self.repository = optional_text(repository)
        self.sha = optional_text(sha)
        self.context = optional_text(context) or DEFAULT_CONTEXT
        self.api_url = required_url(api_url, "GitHub api_url must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> GitHubCommitStatusPublisher:
        return cls(
            token=kwargs.pop("token", None) or os.getenv("GITHUB_TOKEN"),
            repository=kwargs.pop("repository", None) or os.getenv("GITHUB_REPOSITORY"),
            sha=kwargs.pop("sha", None) or os.getenv("GITHUB_SHA"),
            context=kwargs.pop("context", None) or os.getenv("GITHUB_STATUS_CONTEXT"),
            api_url=kwargs.pop("api_url", None) or os.getenv("GITHUB_API_URL", DEFAULT_API_URL),
            **kwargs,
        )

    @property
    def statuses_endpoint(self) -> str:
        repository = required_text(self.repository, "GITHUB_REPOSITORY is required for GitHub commit status publishing")
        sha = required_text(self.sha, "GITHUB_SHA is required for GitHub commit status publishing")
        owner, repo = _split_repository(repository)
        return f"{self.api_url}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/statuses/{quote(sha, safe='')}"

    def build_status_payload(self, tact_spec: dict[str, Any], *, state: str = "success", target_url: str | None = None, description: str | None = None) -> GitHubCommitStatusPayload:
        if state not in ALLOWED_STATES:
            raise GitHubCommitStatusPublishError(f"GitHub commit status state must be one of {', '.join(sorted(ALLOWED_STATES))}")
        try:
            validate_tact_spec(tact_spec, label="GitHub commit status")
            repository = required_text(self.repository, "GITHUB_REPOSITORY is required for GitHub commit status publishing")
            sha = required_text(self.sha, "GITHUB_SHA is required for GitHub commit status publishing")
        except ValueError as exc:
            raise GitHubCommitStatusPublishError(str(exc)) from exc

        meta = metadata(tact_spec, publisher="max.github_commit_statuses", extra={"repository": repository, "sha": sha})
        status = {
            "state": state,
            "context": self.context,
            "description": _description(tact_spec, description),
            "target_url": optional_text(target_url),
        }
        return GitHubCommitStatusPayload(repository, sha, status, meta)

    def publish(self, tact_spec: dict[str, Any], *, state: str = "success", target_url: str | None = None, description: str | None = None, dry_run: bool = True) -> GitHubCommitStatusPublishResult:
        payload = self.build_status_payload(tact_spec, state=state, target_url=target_url, description=description).to_dict()
        endpoint = self.statuses_endpoint
        if dry_run:
            return GitHubCommitStatusPublishResult(None, None, None, True, endpoint, payload)
        if not self.token:
            raise GitHubCommitStatusPublishError("GITHUB_TOKEN is required for live GitHub commit status publishing; use dry_run to preview")
        response = self._post(endpoint, _request_json(payload["status"]))
        body = response_json(response, GitHubCommitStatusPublishError, "GitHub commit status publish failed: response was not valid JSON")
        return GitHubCommitStatusPublishResult(response.status_code, optional_text(body.get("id")), optional_text(body.get("url")) or optional_text(body.get("target_url")), False, endpoint, payload, body)

    def _post(self, endpoint: str, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise GitHubCommitStatusPublishError(f"GitHub commit status publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.token])}", status_code=response.status_code, token=self.token)
        return response

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "User-Agent": "max-github-commit-statuses-publisher/1", "X-GitHub-Api-Version": "2022-11-28"}


GitHubCommitStatusesPublisher = GitHubCommitStatusPublisher


def _description(tact_spec: dict[str, Any], explicit: str | None) -> str:
    text = optional_text(explicit)
    if text:
        return text[:140]
    evaluation = dict_value(tact_spec, "evaluation")
    recommendation = optional_text(evaluation.get("recommendation")) or "ready"
    return f"Max TactSpec {recommendation}: {title(tact_spec)}"[:140]


def _split_repository(repository: str) -> tuple[str, str]:
    parts = repository.split("/", 1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        raise GitHubCommitStatusPublishError("GITHUB_REPOSITORY must be in owner/repo form")
    return parts[0], parts[1]


def _request_json(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}

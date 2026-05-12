"""GitHub Actions workflow run rerun publisher."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_GITHUB_API_URL = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS = 10.0
REDACTED = "[redacted]"


class GitHubWorkflowRunRerunPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubWorkflowRunRerunPayload:
    repository: str
    run_id: int
    failed_jobs_only: bool
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "run_id": self.run_id,
            "failed_jobs_only": self.failed_jobs_only,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class GitHubWorkflowRunRerunPublishResult:
    status_code: int | None
    repository: str
    run_id: int
    endpoint: str
    dry_run: bool
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class GitHubWorkflowRunRerunPublisher:
    def __init__(
        self,
        repository: str | None = None,
        *,
        token: str | None = None,
        run_id: int | str | None = None,
        failed_jobs_only: bool = False,
        api_url: str = DEFAULT_GITHUB_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.repository = _validate_repository(repository)
        self.owner, self.repo = self.repository.split("/", 1)
        self.run_id = _positive_run_id(run_id)
        self.failed_jobs_only = bool(failed_jobs_only)
        self.token = _optional_text(token)
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> GitHubWorkflowRunRerunPublisher:
        return cls(
            repository=kwargs.pop("repository", None) or os.getenv("GITHUB_REPOSITORY"),
            token=kwargs.pop("token", None) or os.getenv("GITHUB_TOKEN"),
            run_id=kwargs.pop("run_id", None) or os.getenv("GITHUB_WORKFLOW_RUN_ID"),
            failed_jobs_only=(
                kwargs.pop("failed_jobs_only", None)
                if "failed_jobs_only" in kwargs
                else _env_bool("GITHUB_RERUN_FAILED_JOBS_ONLY") or False
            ),
            api_url=kwargs.pop("api_url", None) or os.getenv("GITHUB_API_URL", DEFAULT_GITHUB_API_URL),
            **kwargs,
        )

    @property
    def rerun_endpoint(self) -> str:
        suffix = "rerun-failed-jobs" if self.failed_jobs_only else "rerun"
        return f"{self.api_url}/repos/{self.owner}/{self.repo}/actions/runs/{self.run_id}/{suffix}"

    def build_payload(self) -> GitHubWorkflowRunRerunPayload:
        return GitHubWorkflowRunRerunPayload(
            repository=self.repository,
            run_id=self.run_id,
            failed_jobs_only=self.failed_jobs_only,
            metadata={
                "publisher": "max.github_workflow_run_rerun",
                "repository": self.repository,
                "run_id": self.run_id,
                "endpoint": self.rerun_endpoint,
            },
        )

    def publish(self, *, dry_run: bool = True) -> GitHubWorkflowRunRerunPublishResult:
        payload = self.build_payload().to_dict()
        if dry_run:
            return GitHubWorkflowRunRerunPublishResult(
                None, self.repository, self.run_id, self.rerun_endpoint, True, payload
            )
        if not self.token:
            raise GitHubWorkflowRunRerunPublishError(
                "GITHUB_TOKEN is required for live GitHub workflow run rerun publishing; use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.rerun_endpoint,
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                        "User-Agent": "max-github-workflow-run-rerun-publisher/1",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise GitHubWorkflowRunRerunPublishError(
                    _redact_text(f"GitHub workflow run rerun failed for {self.rerun_endpoint}: {exc}", self.token)
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise GitHubWorkflowRunRerunPublishError(
                _redact_text(
                    f"GitHub workflow run rerun failed with HTTP {response.status_code}: {_response_preview(response)}",
                    self.token,
                ),
                status_code=response.status_code,
            )
        return GitHubWorkflowRunRerunPublishResult(
            response.status_code,
            self.repository,
            self.run_id,
            self.rerun_endpoint,
            False,
            {
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "github_workflow_run_rerun_status_code": response.status_code,
                },
            },
            _response_json(response),
        )


GitHubWorkflowRunRerunsPublisher = GitHubWorkflowRunRerunPublisher


def _validate_repository(repository: str | None) -> str:
    value = _optional_text(repository)
    if not value:
        raise GitHubWorkflowRunRerunPublishError(
            "GitHub repository is required; pass repository or set GITHUB_REPOSITORY"
        )
    if value.count("/") != 1 or any(not part for part in value.split("/", 1)):
        raise GitHubWorkflowRunRerunPublishError("GitHub repository must be in owner/repo format")
    return value


def _positive_run_id(value: int | str | None) -> int:
    try:
        run_id = int(value) if value is not None else 0
    except (TypeError, ValueError):
        run_id = 0
    if run_id <= 0:
        raise GitHubWorkflowRunRerunPublishError(
            "GitHub workflow run_id must be a positive integer"
        )
    return run_id


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _env_bool(name: str) -> bool | None:
    value = _optional_text(os.getenv(name))
    if value is None:
        return None
    return value.lower() in {"1", "true", "yes", "y", "on"}


def _redact_text(text: str, token: str | None) -> str:
    return text.replace(token, REDACTED) if token else text


def _response_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) > limit:
        text = text[:limit] + "..."
    return text


def _response_json(response: httpx.Response) -> dict[str, Any] | None:
    if not response.content:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None

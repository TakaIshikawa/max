"""GitHub check-run publisher for generated TactSpec previews."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, markdown_summary, metadata, optional_text, required_text, required_url, response_json, response_preview, title, validate_tact_spec

DEFAULT_API_URL = "https://api.github.com"


class GitHubCheckRunPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubCheckRunPayload:
    repository: str
    check_run: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"repository": self.repository, "check_run": self.check_run, "metadata": self.metadata}


@dataclass(frozen=True)
class GitHubCheckRunPublishResult:
    status_code: int | None
    check_run_id: str | None
    check_run_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class GitHubCheckRunPublisher:
    def __init__(self, *, repository: str | None = None, head_sha: str | None = None, token: str | None = None, api_url: str = DEFAULT_API_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.repository = optional_text(repository)
        self.head_sha = optional_text(head_sha)
        self.token = optional_text(token)
        self.api_url = required_url(api_url, "GitHub api_url must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, *, repository: str | None = None, head_sha: str | None = None, token: str | None = None, api_url: str | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> GitHubCheckRunPublisher:
        return cls(repository=repository or os.getenv("GITHUB_REPOSITORY"), head_sha=head_sha or os.getenv("GITHUB_HEAD_SHA") or os.getenv("GITHUB_SHA"), token=token or os.getenv("GITHUB_TOKEN"), api_url=api_url or os.getenv("GITHUB_API_URL", DEFAULT_API_URL), timeout=timeout, client=client)

    @property
    def check_runs_endpoint(self) -> str:
        repository = required_text(self.repository, "GITHUB_REPOSITORY is required for GitHub check run publishing")
        return f"{self.api_url}/repos/{repository}/check-runs"

    def build_check_run_payload(self, tact_spec: dict[str, Any]) -> GitHubCheckRunPayload:
        try:
            validate_tact_spec(tact_spec, label="GitHub check run")
            repository = required_text(self.repository, "GITHUB_REPOSITORY is required for GitHub check run publishing")
            head_sha = required_text(self.head_sha, "GITHUB_HEAD_SHA or GITHUB_SHA is required for GitHub check run publishing")
        except ValueError as exc:
            raise GitHubCheckRunPublishError(str(exc)) from exc
        meta = metadata(tact_spec, publisher="max.github_check_runs")
        body = markdown_summary(tact_spec, meta)
        check_run = {
            "name": f"Max TactSpec: {title(tact_spec)}"[:100],
            "head_sha": head_sha,
            "status": "completed",
            "conclusion": "success",
            "output": {"title": title(tact_spec), "summary": body[:65000], "text": body[:65000]},
        }
        return GitHubCheckRunPayload(repository, check_run, meta)

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True) -> GitHubCheckRunPublishResult:
        payload = self.build_check_run_payload(tact_spec).to_dict()
        if dry_run:
            return GitHubCheckRunPublishResult(None, None, None, True, payload)
        if not self.token:
            raise GitHubCheckRunPublishError("GITHUB_TOKEN is required for live GitHub check run publishing; use dry_run to preview")
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.check_runs_endpoint, json=payload["check_run"], headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "User-Agent": "max-github-check-runs-publisher/1", "X-GitHub-Api-Version": "2022-11-28"}, timeout=self.timeout)
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise GitHubCheckRunPublishError(f"GitHub check run publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.token])}", status_code=response.status_code)
        body = response_json(response, GitHubCheckRunPublishError, "GitHub check run publish failed: response was not valid JSON")
        return GitHubCheckRunPublishResult(response.status_code, optional_text(body.get("id")), optional_text(body.get("html_url")), False, payload)


GitHubCheckRunsPublisher = GitHubCheckRunPublisher

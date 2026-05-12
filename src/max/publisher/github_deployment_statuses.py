"""GitHub deployment status publisher for Max rollout artifacts."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, redact_text, required_text, required_url, response_json, response_preview
from max.publisher.stripe_customer_notes import _RETRYABLE_STATUS_CODES, _unit_fields

DEFAULT_API_URL = "https://api.github.com"
DEFAULT_ENVIRONMENT = "production"
ALLOWED_STATES = {"queued", "in_progress", "success", "failure", "inactive"}


class GitHubDeploymentStatusPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubDeploymentStatusPublishResult:
    status_code: int | None
    deployment_status_id: str | None
    deployment_status_url: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class GitHubDeploymentStatusPublisher:
    def __init__(self, *, token: str | None = None, repository: str | None = None, deployment_id: str | None = None, api_url: str = DEFAULT_API_URL, environment: str | None = None, log_url: str | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS, max_retries: int = 2, client: httpx.Client | None = None) -> None:
        self.token = optional_text(token)
        self.repository = optional_text(repository)
        self.deployment_id = optional_text(deployment_id)
        self.api_url = required_url(api_url, "GitHub api_url must be an absolute http(s) URL")
        self.environment = optional_text(environment) or DEFAULT_ENVIRONMENT
        self.log_url = optional_text(log_url)
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> GitHubDeploymentStatusPublisher:
        return cls(token=kwargs.pop("token", None) or os.getenv("GITHUB_TOKEN"), repository=kwargs.pop("repository", None) or os.getenv("GITHUB_REPOSITORY"), deployment_id=kwargs.pop("deployment_id", None) or os.getenv("GITHUB_DEPLOYMENT_ID"), api_url=kwargs.pop("api_url", None) or os.getenv("GITHUB_API_URL", DEFAULT_API_URL), environment=kwargs.pop("environment", None) or os.getenv("GITHUB_DEPLOYMENT_ENVIRONMENT"), log_url=kwargs.pop("log_url", None) or os.getenv("GITHUB_DEPLOYMENT_LOG_URL"), **kwargs)

    @property
    def statuses_endpoint(self) -> str:
        repository = required_text(self.repository, "GITHUB_REPOSITORY is required for GitHub deployment status publishing")
        deployment_id = required_text(self.deployment_id, "GITHUB_DEPLOYMENT_ID is required for GitHub deployment status publishing")
        owner, repo = _split_repository(repository)
        return f"{self.api_url}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/deployments/{quote(deployment_id, safe='')}/statuses"

    def build_status_payload(self, unit: dict[str, Any], *, state: str = "queued") -> dict[str, Any]:
        if state not in ALLOWED_STATES:
            raise GitHubDeploymentStatusPublishError(f"GitHub deployment status state must be one of {', '.join(sorted(ALLOWED_STATES))}")
        fields = _unit_fields(unit)
        metadata = {"publisher": "max.github_deployment_statuses", "idea_id": fields["idea_id"], "status": fields["status"], "score": fields["score"], "repository": self.repository, "deployment_id": self.deployment_id}
        payload: dict[str, Any] = {"state": state, "environment": self.environment, "description": f"Max {fields['status']} idea {fields['idea_id']}: {fields['title']}", "context": f"max/{fields['idea_id']}", "metadata": metadata}
        if self.log_url:
            payload["log_url"] = self.log_url
        return payload

    def publish(self, unit: dict[str, Any], *, state: str = "queued", dry_run: bool = True) -> GitHubDeploymentStatusPublishResult:
        payload = self.build_status_payload(unit, state=state)
        endpoint = self.statuses_endpoint
        if dry_run:
            return GitHubDeploymentStatusPublishResult(None, None, None, True, endpoint, _redacted(payload))
        if not self.token:
            raise GitHubDeploymentStatusPublishError("GITHUB_TOKEN is required for live GitHub deployment status publishing; use dry_run to preview")
        response = self._post_with_retries(endpoint, _request_json(payload))
        body = response_json(response, GitHubDeploymentStatusPublishError, "GitHub deployment status publish failed: response was not valid JSON")
        return GitHubDeploymentStatusPublishResult(response.status_code, optional_text(body.get("id")), optional_text(body.get("url")) or optional_text(body.get("html_url")), False, endpoint, _redacted(payload), body)

    def _post_with_retries(self, endpoint: str, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            last_response: httpx.Response | None = None
            for attempt in range(self.max_retries + 1):
                response = client.post(endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
                last_response = response
                if response.status_code not in _RETRYABLE_STATUS_CODES or attempt >= self.max_retries:
                    break
            assert last_response is not None
            if not 200 <= last_response.status_code < 300:
                raise GitHubDeploymentStatusPublishError(f"GitHub deployment status publish failed with HTTP {last_response.status_code}: {response_preview(last_response, secrets=[self.token])}", status_code=last_response.status_code, token=self.token)
            return last_response
        finally:
            if close_client:
                client.close()

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "User-Agent": "max-github-deployment-statuses-publisher/1", "X-GitHub-Api-Version": "2022-11-28"}


GitHubDeploymentStatusesPublisher = GitHubDeploymentStatusPublisher


def _split_repository(repository: str) -> tuple[str, str]:
    parts = repository.split("/", 1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        raise ValueError("GITHUB_REPOSITORY must be in owner/repo form")
    return parts[0], parts[1]


def _request_json(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "metadata" and value is not None}


def _redacted(payload: dict[str, Any]) -> dict[str, Any]:
    return dict(payload)

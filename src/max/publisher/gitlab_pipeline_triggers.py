"""GitLab pipeline trigger publisher for Max summaries."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._summary_payloads import summary_markdown, summary_metadata, summary_title
from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, quote_path, required_text, required_url, response_json, response_preview

DEFAULT_GITLAB_API_URL = "https://gitlab.com/api/v4"


class GitLabPipelineTriggerPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(_redact(message, token))
        self.status_code = status_code


@dataclass(frozen=True)
class GitLabPipelineTriggerPublishResult:
    status_code: int | None
    pipeline_id: str | None
    web_url: str | None
    dry_run: bool
    endpoint: str
    headers: dict[str, str]
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class GitLabPipelineTriggerPublisher:
    def __init__(
        self,
        *,
        project_id: str,
        ref: str,
        trigger_token: str | None = None,
        variables: dict[str, str] | None = None,
        api_url: str = DEFAULT_GITLAB_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.project_id = required_text(project_id, "GitLab project_id is required")
        self.ref = required_text(ref, "GitLab ref is required")
        self.trigger_token = optional_text(trigger_token)
        self.variables = {str(key): str(value) for key, value in (variables or {}).items()}
        self.api_url = required_url(api_url, "GitLab api_url must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> GitLabPipelineTriggerPublisher:
        return cls(
            project_id=kwargs.pop("project_id", None) or os.getenv("GITLAB_PROJECT_ID") or os.getenv("GITLAB_PROJECT"),
            ref=kwargs.pop("ref", None) or os.getenv("GITLAB_REF", "main"),
            trigger_token=kwargs.pop("trigger_token", None) or os.getenv("GITLAB_TRIGGER_TOKEN"),
            api_url=kwargs.pop("api_url", None) or os.getenv("GITLAB_API_URL", DEFAULT_GITLAB_API_URL),
            **kwargs,
        )

    @property
    def endpoint(self) -> str:
        return f"{self.api_url}/projects/{quote_path(self.project_id)}/trigger/pipeline"

    def build_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        metadata = summary_metadata(payload, publisher="max.gitlab_pipeline_triggers")
        variables = {
            **self.variables,
            "MAX_TITLE": summary_title(payload),
            "MAX_SUMMARY": summary_markdown(payload),
            "MAX_SOURCE_TYPE": str(metadata.get("source_type") or ""),
            "MAX_SOURCE_ID": str(metadata.get("source_id") or ""),
            "MAX_IDEA_ID": str(metadata.get("idea_id") or ""),
        }
        return {"ref": self.ref, "token": self.trigger_token or "[REDACTED]", "variables": variables, "metadata": metadata}

    def publish(self, payload: dict[str, Any], *, dry_run: bool = True) -> GitLabPipelineTriggerPublishResult:
        request_payload = self.build_payload(payload)
        headers = self._preview_headers()
        if dry_run:
            return GitLabPipelineTriggerPublishResult(None, None, None, True, self.endpoint, headers, {**request_payload, "token": "[REDACTED]"})
        if not self.trigger_token:
            raise GitLabPipelineTriggerPublishError("GITLAB_TRIGGER_TOKEN is required for live GitLab pipeline trigger publishing; use dry_run to preview")
        response = self._post(request_payload)
        body = response_json(response, GitLabPipelineTriggerPublishError, "GitLab pipeline trigger failed: response was not valid JSON")
        return GitLabPipelineTriggerPublishResult(response.status_code, _text(body.get("id")), _text(body.get("web_url")), False, self.endpoint, self._headers(), {**request_payload, "token": "[REDACTED]"}, body)

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise GitLabPipelineTriggerPublishError(f"GitLab pipeline trigger failed for {self.endpoint}: {exc}", token=self.trigger_token) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise GitLabPipelineTriggerPublishError(f"GitLab pipeline trigger failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.trigger_token])}", status_code=response.status_code, token=self.trigger_token)
        return response

    def _headers(self) -> dict[str, str]:
        return {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "max-gitlab-pipeline-triggers-publisher/1"}

    def _preview_headers(self) -> dict[str, str]:
        return self._headers()


def _text(value: object) -> str | None:
    return str(value) if value is not None else None


def _redact(message: str, secret: str | None) -> str:
    return message.replace(secret, "[REDACTED]") if secret else message

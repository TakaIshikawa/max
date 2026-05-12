"""Jira issue transition publisher for Max readiness outcomes."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._summary_payloads import summary_markdown
from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, quote_path, redact_text, required_text, required_url, response_preview

DEFAULT_JIRA_API_VERSION = "3"


class JiraIssueTransitionPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, secrets: list[str | None] | None = None) -> None:
        super().__init__(redact_text(message, secrets=secrets))
        self.status_code = status_code


@dataclass(frozen=True)
class JiraIssueTransitionPublishResult:
    status_code: int | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response_body: str = ""


class JiraIssueTransitionPublisher:
    def __init__(self, *, base_url: str | None = None, email: str | None = None, api_token: str | None = None, issue_key: str | None = None, transition_id: str | None = None, comment: str | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.base_url = required_url(base_url, "Jira base URL must be an absolute http(s) URL") if optional_text(base_url) else None
        self.email = optional_text(email)
        self.api_token = optional_text(api_token)
        self.issue_key = optional_text(issue_key)
        self.transition_id = optional_text(transition_id)
        self.comment = optional_text(comment)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> JiraIssueTransitionPublisher:
        return cls(base_url=kwargs.pop("base_url", None) or os.getenv("JIRA_BASE_URL"), email=kwargs.pop("email", None) or os.getenv("JIRA_EMAIL"), api_token=kwargs.pop("api_token", None) or os.getenv("JIRA_API_TOKEN"), issue_key=kwargs.pop("issue_key", None) or os.getenv("JIRA_ISSUE_KEY"), transition_id=kwargs.pop("transition_id", None) or os.getenv("JIRA_TRANSITION_ID"), comment=kwargs.pop("comment", None) or os.getenv("JIRA_TRANSITION_COMMENT"), **kwargs)

    @property
    def endpoint(self) -> str:
        base = self.base_url or ""
        key = required_text(self.issue_key, "JIRA_ISSUE_KEY is required for Jira transition publishing")
        return f"{base}/rest/api/{DEFAULT_JIRA_API_VERSION}/issue/{quote_path(key)}/transitions"

    def build_transition_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        transition_id = required_text(self.transition_id, "JIRA_TRANSITION_ID is required for Jira transition publishing")
        request: dict[str, Any] = {"transition": {"id": transition_id}}
        comment = self.comment or summary_markdown(payload)
        if comment:
            request["update"] = {"comment": [{"add": {"body": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": comment[:30000]}]}]}}}]}
        return request

    def publish(self, payload: dict[str, Any], *, dry_run: bool = True) -> JiraIssueTransitionPublishResult:
        request_payload = self.build_transition_payload(payload)
        endpoint = self.endpoint
        if dry_run:
            return JiraIssueTransitionPublishResult(None, True, endpoint, request_payload)
        if not self.base_url or not self.email or not self.api_token:
            raise JiraIssueTransitionPublishError("JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN are required for live Jira transition publishing; use dry_run to preview", secrets=self._secrets)
        response = self._post(endpoint, request_payload)
        return JiraIssueTransitionPublishResult(response.status_code, False, endpoint, request_payload, response.text)

    def _post(self, endpoint: str, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise JiraIssueTransitionPublishError(f"Jira transition publish failed for {endpoint}: {exc}", secrets=self._secrets) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise JiraIssueTransitionPublishError(f"Jira transition publish failed with HTTP {response.status_code}: {response_preview(response, secrets=self._secrets)}", status_code=response.status_code, secrets=self._secrets)
        return response

    @property
    def _secrets(self) -> list[str | None]:
        return [self.api_token]

    def _headers(self) -> dict[str, str]:
        assert self.email is not None and self.api_token is not None
        token = base64.b64encode(f"{self.email}:{self.api_token}".encode()).decode()
        return {"Accept": "application/json", "Authorization": f"Basic {token}", "Content-Type": "application/json", "User-Agent": "max-jira-issue-transitions-publisher/1"}

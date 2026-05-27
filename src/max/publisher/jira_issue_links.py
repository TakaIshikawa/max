"""Jira issue link publisher for generated TactSpec previews."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, markdown_summary, metadata, optional_text, quote_path, required_text, required_url, response_json, response_preview, validate_tact_spec


class JiraIssueLinkPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class JiraIssueLinkPublishResult:
    status_code: int | None
    dry_run: bool
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class JiraIssueLinkPublisher:
    def __init__(self, *, base_url: str | None = None, email: str | None = None, api_token: str | None = None, source_issue_key: str | None = None, target_issue_key: str | None = None, link_type: str = "Relates", timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.base_url = required_url(base_url or "https://jira.example.invalid", "Jira base_url must be an absolute http(s) URL")
        self.email = optional_text(email)
        self.api_token = optional_text(api_token)
        self.source_issue_key = optional_text(source_issue_key)
        self.target_issue_key = optional_text(target_issue_key)
        self.link_type = required_text(link_type, "Jira link_type is required")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> JiraIssueLinkPublisher:
        return cls(base_url=kwargs.get("base_url") or os.getenv("JIRA_BASE_URL"), email=kwargs.get("email") or os.getenv("JIRA_EMAIL"), api_token=kwargs.get("api_token") or os.getenv("JIRA_API_TOKEN"), source_issue_key=kwargs.get("source_issue_key") or os.getenv("JIRA_SOURCE_ISSUE_KEY"), target_issue_key=kwargs.get("target_issue_key") or os.getenv("JIRA_TARGET_ISSUE_KEY"), link_type=kwargs.get("link_type") or os.getenv("JIRA_LINK_TYPE", "Relates"), timeout=kwargs.get("timeout", DEFAULT_TIMEOUT_SECONDS), client=kwargs.get("client"))

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/rest/api/3/issueLink"

    def build_link_payload(self, tact_spec: dict[str, Any], *, source_issue_key: str | None = None, target_issue_key: str | None = None) -> dict[str, Any]:
        try:
            validate_tact_spec(tact_spec, label="Jira issue link")
            source = required_text(optional_text(source_issue_key) or self.source_issue_key, "JIRA_SOURCE_ISSUE_KEY is required for Jira issue link publishing")
            target = required_text(optional_text(target_issue_key) or self.target_issue_key, "JIRA_TARGET_ISSUE_KEY is required for Jira issue link publishing")
        except ValueError as exc:
            raise JiraIssueLinkPublishError(str(exc)) from exc
        meta = metadata(tact_spec, publisher="max.jira_issue_links")
        payload = {"type": {"name": self.link_type}, "inwardIssue": {"key": source}, "outwardIssue": {"key": target}, "comment": {"body": markdown_summary(tact_spec, meta)}}
        return {"endpoint": self.endpoint, "payload": payload, "metadata": meta}

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True) -> JiraIssueLinkPublishResult:
        built = self.build_link_payload(tact_spec)
        if dry_run:
            return JiraIssueLinkPublishResult(None, True, built)
        if not (self.email and self.api_token):
            raise JiraIssueLinkPublishError("JIRA_EMAIL and JIRA_API_TOKEN are required for live Jira issue link publishing; use dry_run to preview")
        client = self._client or httpx.Client(timeout=self.timeout)
        close_client = self._client is None
        try:
            response = client.post(self.endpoint, json=built["payload"], auth=(self.email, self.api_token), timeout=self.timeout)
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise JiraIssueLinkPublishError(f"Jira issue link publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.api_token])}", status_code=response.status_code)
        return JiraIssueLinkPublishResult(response.status_code, False, built, response_json(response, JiraIssueLinkPublishError, "Jira issue link response was not valid JSON"))

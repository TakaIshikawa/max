"""Jira Cloud project version publisher."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, redact_text, required_text, required_url, response_json, response_preview
from max.publisher.stripe_customer_notes import _RETRYABLE_STATUS_CODES

DEFAULT_API_PATH = "/rest/api/3/version"


class JiraVersionPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class JiraVersionPublishResult:
    status_code: int | None
    version_id: str | None
    version_url: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class JiraVersionPublisher:
    def __init__(self, *, site_url: str | None = None, email: str | None = None, api_token: str | None = None, bearer_token: str | None = None, project_key: str | None = None, project_id: str | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS, max_retries: int = 2, client: httpx.Client | None = None) -> None:
        self.site_url = required_url(site_url, "Jira site_url must be an absolute http(s) URL")
        self.email = optional_text(email)
        self.api_token = optional_text(api_token)
        self.bearer_token = optional_text(bearer_token)
        self.project_key = optional_text(project_key)
        self.project_id = optional_text(project_id)
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> JiraVersionPublisher:
        return cls(site_url=kwargs.pop("site_url", None) or os.getenv("JIRA_SITE_URL"), email=kwargs.pop("email", None) or os.getenv("JIRA_EMAIL"), api_token=kwargs.pop("api_token", None) or os.getenv("JIRA_API_TOKEN"), bearer_token=kwargs.pop("bearer_token", None) or os.getenv("JIRA_BEARER_TOKEN"), project_key=kwargs.pop("project_key", None) or os.getenv("JIRA_PROJECT_KEY"), project_id=kwargs.pop("project_id", None) or os.getenv("JIRA_PROJECT_ID"), **kwargs)

    @property
    def version_endpoint(self) -> str:
        return f"{self.site_url}{DEFAULT_API_PATH}"

    def build_version_payload(self, *, name: str, description: str | None = None, release_date: str | None = None, start_date: str | None = None, archived: bool | None = None, released: bool | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": required_text(name, "Jira version name is required")}
        if self.project_id:
            payload["projectId"] = self.project_id
        else:
            payload["project"] = required_text(self.project_key, "JIRA_PROJECT_KEY or JIRA_PROJECT_ID is required for Jira version publishing")
        for key, value in {"description": description, "releaseDate": release_date, "startDate": start_date}.items():
            text = optional_text(value)
            if text:
                payload[key] = text
        if archived is not None:
            payload["archived"] = archived
        if released is not None:
            payload["released"] = released
        return payload

    def publish(self, *, name: str, dry_run: bool = True, description: str | None = None, release_date: str | None = None, start_date: str | None = None, archived: bool | None = None, released: bool | None = None) -> JiraVersionPublishResult:
        payload = self.build_version_payload(name=name, description=description, release_date=release_date, start_date=start_date, archived=archived, released=released)
        if dry_run:
            return JiraVersionPublishResult(None, None, None, True, self.version_endpoint, payload)
        if not (self.bearer_token or (self.email and self.api_token)):
            raise JiraVersionPublishError("Jira email/api_token or bearer_token is required for live Jira version publishing; use dry_run to preview", token=self.api_token or self.bearer_token)
        response = self._post_with_retries(payload)
        body = response_json(response, JiraVersionPublishError, "Jira version publish failed: response was not valid JSON")
        return JiraVersionPublishResult(response.status_code, optional_text(body.get("id")), optional_text(body.get("self")), False, self.version_endpoint, payload, body)

    def _post_with_retries(self, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            last_response: httpx.Response | None = None
            for attempt in range(self.max_retries + 1):
                response = client.post(self.version_endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
                last_response = response
                if response.status_code not in _RETRYABLE_STATUS_CODES or attempt >= self.max_retries:
                    break
            assert last_response is not None
            if not 200 <= last_response.status_code < 300:
                raise JiraVersionPublishError(f"Jira version publish failed with HTTP {last_response.status_code}: {response_preview(last_response, secrets=[self.api_token, self.bearer_token])}", status_code=last_response.status_code, token=self.api_token or self.bearer_token)
            return last_response
        finally:
            if close_client:
                client.close()

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "max-jira-versions-publisher/1"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        else:
            assert self.email is not None and self.api_token is not None
            headers["Authorization"] = "Basic " + base64.b64encode(f"{self.email}:{self.api_token}".encode()).decode("ascii")
        return headers


JiraVersionsPublisher = JiraVersionPublisher

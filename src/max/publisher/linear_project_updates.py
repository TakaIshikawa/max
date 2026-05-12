"""Linear project update publisher for generated TactSpec previews."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, markdown_summary, metadata, optional_text, required_text, required_url, response_json, response_preview, title, validate_tact_spec

DEFAULT_API_URL = "https://api.linear.app/graphql"


class LinearProjectUpdatePublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class LinearProjectUpdatePayload:
    project_id: str
    body: str
    request: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"project_id": self.project_id, "body": self.body, "request": self.request, "metadata": self.metadata}


@dataclass(frozen=True)
class LinearProjectUpdatePublishResult:
    status_code: int | None
    update_id: str | None
    update_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class LinearProjectUpdatePublisher:
    def __init__(self, *, project_id: str | None = None, api_key: str | None = None, api_url: str = DEFAULT_API_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.project_id = optional_text(project_id)
        self.api_key = optional_text(api_key)
        self.api_url = required_url(api_url, "Linear api_url must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, *, project_id: str | None = None, api_key: str | None = None, api_url: str | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> LinearProjectUpdatePublisher:
        return cls(project_id=project_id or os.getenv("LINEAR_PROJECT_ID"), api_key=api_key or os.getenv("LINEAR_API_KEY"), api_url=api_url or os.getenv("LINEAR_API_URL", DEFAULT_API_URL), timeout=timeout, client=client)

    def build_update_payload(self, tact_spec: dict[str, Any], *, project_id: str | None = None) -> LinearProjectUpdatePayload:
        try:
            validate_tact_spec(tact_spec, label="Linear project update")
            resolved_project_id = required_text(optional_text(project_id) or self.project_id, "LINEAR_PROJECT_ID is required for Linear project update publishing")
        except ValueError as exc:
            raise LinearProjectUpdatePublishError(str(exc)) from exc
        meta = metadata(tact_spec, publisher="max.linear_project_updates")
        body = markdown_summary(tact_spec, meta)
        request = _graphql_request(resolved_project_id, body, title(tact_spec))
        return LinearProjectUpdatePayload(resolved_project_id, body, request, meta)

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True, project_id: str | None = None) -> LinearProjectUpdatePublishResult:
        payload = self.build_update_payload(tact_spec, project_id=project_id).to_dict()
        if dry_run:
            return LinearProjectUpdatePublishResult(None, None, None, True, payload)
        if not self.api_key:
            raise LinearProjectUpdatePublishError("LINEAR_API_KEY is required for live Linear project update publishing; use dry_run to preview")
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.api_url, json=payload["request"], headers={"Authorization": self.api_key, "Content-Type": "application/json", "User-Agent": "max-linear-project-updates-publisher/1"}, timeout=self.timeout)
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise LinearProjectUpdatePublishError(f"Linear project update publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.api_key])}", status_code=response.status_code)
        body = response_json(response, LinearProjectUpdatePublishError, "Linear project update publish failed: response was not valid JSON")
        if body.get("errors"):
            raise LinearProjectUpdatePublishError(f"Linear project update publish failed: {response_preview(response, secrets=[self.api_key])}", status_code=response.status_code)
        update = (((body.get("data") or {}).get("projectUpdateCreate") or {}).get("projectUpdate") or {})
        return LinearProjectUpdatePublishResult(response.status_code, optional_text(update.get("id")), optional_text(update.get("url")), False, payload)


LinearProjectUpdatesPublisher = LinearProjectUpdatePublisher


def _graphql_request(project_id: str, body: str, update_title: str) -> dict[str, Any]:
    return {
        "query": "mutation ProjectUpdateCreate($input: ProjectUpdateCreateInput!) { projectUpdateCreate(input: $input) { success projectUpdate { id url } } }",
        "variables": {"input": {"projectId": project_id, "body": body, "health": "onTrack", "title": update_title}},
    }

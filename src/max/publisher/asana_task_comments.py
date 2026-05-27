"""Asana task comment publisher."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, required_text, required_url, response_json, response_preview

DEFAULT_API_URL = "https://app.asana.com/api/1.0"


class AsanaTaskCommentPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class AsanaTaskCommentPublishResult:
    status_code: int | None
    story_gid: str | None
    dry_run: bool
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class AsanaTaskCommentPublisher:
    def __init__(self, *, task_gid: str | None = None, access_token: str | None = None, api_url: str = DEFAULT_API_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.task_gid = optional_text(task_gid)
        self.access_token = optional_text(access_token)
        self.api_url = required_url(api_url, "Asana api_url must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> AsanaTaskCommentPublisher:
        return cls(task_gid=kwargs.get("task_gid") or os.getenv("ASANA_TASK_GID"), access_token=kwargs.get("access_token") or os.getenv("ASANA_ACCESS_TOKEN"), api_url=kwargs.get("api_url") or os.getenv("ASANA_API_URL", DEFAULT_API_URL), timeout=kwargs.get("timeout", DEFAULT_TIMEOUT_SECONDS), client=kwargs.get("client"))

    def endpoint(self, task_gid: str) -> str:
        return f"{self.api_url}/tasks/{task_gid}/stories"

    def build_comment_payload(self, *, text: str | None = None, body: str | None = None, task_gid: str | None = None, is_pinned: bool | None = None) -> dict[str, Any]:
        try:
            resolved_task = required_text(optional_text(task_gid) or self.task_gid, "Asana task_gid is required")
            comment = required_text(optional_text(text) or optional_text(body), "Asana comment text is required")
        except ValueError as exc:
            raise AsanaTaskCommentPublishError(str(exc)) from exc
        data: dict[str, Any] = {"text": comment}
        if is_pinned is not None:
            data["is_pinned"] = bool(is_pinned)
        return {"endpoint": self.endpoint(resolved_task), "task_gid": resolved_task, "payload": {"data": data}}

    def publish(self, *, text: str | None = None, body: str | None = None, dry_run: bool = True, task_gid: str | None = None, is_pinned: bool | None = None) -> AsanaTaskCommentPublishResult:
        payload = self.build_comment_payload(text=text, body=body, task_gid=task_gid, is_pinned=is_pinned)
        if dry_run:
            return AsanaTaskCommentPublishResult(None, None, True, payload)
        if not self.access_token:
            raise AsanaTaskCommentPublishError("ASANA_ACCESS_TOKEN is required for live Asana task comment publishing; use dry_run to preview")
        client = self._client or httpx.Client(timeout=self.timeout)
        close_client = self._client is None
        try:
            response = client.post(payload["endpoint"], json=payload["payload"], headers={"Authorization": f"Bearer {self.access_token}"}, timeout=self.timeout)
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            return AsanaTaskCommentPublishResult(response.status_code, None, False, {**payload, "error": response_preview(response, secrets=[self.access_token])})
        body_json = response_json(response, AsanaTaskCommentPublishError, "Asana task comment response was not valid JSON")
        data = body_json.get("data") if isinstance(body_json.get("data"), dict) else body_json
        return AsanaTaskCommentPublishResult(response.status_code, optional_text(data.get("gid")), False, payload, body_json)

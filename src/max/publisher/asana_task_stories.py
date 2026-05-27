"""Asana task story publisher."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


DEFAULT_ASANA_API_URL = "https://app.asana.com/api/1.0"
DEFAULT_TIMEOUT_SECONDS = 10.0


class AsanaTaskStoryPublishError(RuntimeError):
    """Raised when an Asana task story cannot be published."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class AsanaTaskStoryPublishResult:
    status_code: int | None
    task_gid: str
    story_gid: str | None
    dry_run: bool
    payload: dict[str, Any]


class AsanaTaskStoryPublisher:
    """Build and optionally post a story/comment to an Asana task."""

    def __init__(
        self,
        *,
        task_gid: str | None = None,
        token: str | None = None,
        api_url: str = DEFAULT_ASANA_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.task_gid = _optional_text(task_gid)
        self.token = _optional_text(token)
        self.api_url = _required_url(api_url)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        task_gid: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> "AsanaTaskStoryPublisher":
        return cls(
            task_gid=task_gid or os.getenv("ASANA_TASK_GID"),
            token=token or os.getenv("ASANA_TOKEN"),
            api_url=api_url or os.getenv("ASANA_API_URL", DEFAULT_ASANA_API_URL),
            timeout=timeout,
            client=client,
        )

    def story_endpoint(self, *, task_gid: str | None = None) -> str:
        return f"{self.api_url}/tasks/{self._task_gid(task_gid)}/stories"

    def build_payload(
        self,
        *,
        task_gid: str | None = None,
        text: str | None = None,
        html_text: str | None = None,
    ) -> dict[str, Any]:
        resolved_task_gid = self._task_gid(task_gid)
        data: dict[str, str] = {}
        if _optional_text(text):
            data["text"] = _optional_text(text) or ""
        if _optional_text(html_text):
            data["html_text"] = _optional_text(html_text) or ""
        if not data:
            raise AsanaTaskStoryPublishError("Asana story requires text or html_text")
        return {"task_gid": resolved_task_gid, "data": data}

    def publish(
        self,
        *,
        task_gid: str | None = None,
        text: str | None = None,
        html_text: str | None = None,
        token: str | None = None,
        dry_run: bool = True,
    ) -> AsanaTaskStoryPublishResult:
        payload = self.build_payload(task_gid=task_gid, text=text, html_text=html_text)
        endpoint = self.story_endpoint(task_gid=payload["task_gid"])
        request_json = {"data": payload["data"]}
        auth_token = _optional_text(token) or self.token

        if dry_run:
            return AsanaTaskStoryPublishResult(
                status_code=None,
                task_gid=payload["task_gid"],
                story_gid=None,
                dry_run=True,
                payload={
                    **payload,
                    "request": {
                        "method": "POST",
                        "url": endpoint,
                        "headers": {"Authorization": f"Bearer {auth_token}"} if auth_token else {},
                        "json": request_json,
                    },
                },
            )

        if not auth_token:
            raise AsanaTaskStoryPublishError("ASANA_TOKEN is required for live Asana story publishing; use dry_run to preview")

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(
                endpoint,
                json=request_json,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {auth_token}",
                    "User-Agent": "max-asana-task-stories-publisher/1",
                },
                timeout=self.timeout,
            )
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise AsanaTaskStoryPublishError(
                f"Asana task story publish failed with HTTP {response.status_code}: {response.text[:500]}",
                status_code=response.status_code,
            )
        body = _json_response(response)
        story_gid = _optional_text(_dict_value(body, "data").get("gid"))
        return AsanaTaskStoryPublishResult(
            status_code=response.status_code,
            task_gid=payload["task_gid"],
            story_gid=story_gid,
            dry_run=False,
            payload={**payload, "metadata": {"asana_story_gid": story_gid}},
        )

    def _task_gid(self, task_gid: str | None = None) -> str:
        return _required_text(task_gid or self.task_gid, "Asana task_gid is required")


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _required_text(value: object, message: str) -> str:
    text = _optional_text(value)
    if not text:
        raise AsanaTaskStoryPublishError(message)
    return text


def _required_url(value: object) -> str:
    text = _required_text(value, "Asana API URL is required").rstrip("/")
    if not text.startswith(("http://", "https://")):
        raise AsanaTaskStoryPublishError("Asana API URL must start with http:// or https://")
    return text


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise AsanaTaskStoryPublishError("Asana task story publish failed: response was not valid JSON", status_code=response.status_code) from exc
    return body if isinstance(body, dict) else {}

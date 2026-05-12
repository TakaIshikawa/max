"""Asana project status update publisher."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


DEFAULT_ASANA_API_URL = "https://app.asana.com/api/1.0"
DEFAULT_TIMEOUT_SECONDS = 10.0


class AsanaProjectStatusUpdatePublishError(RuntimeError):
    """Raised when an Asana project status update cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class AsanaProjectStatusUpdatePayload:
    """Asana project status update payload."""

    project_gid: str
    title: str
    text: str
    color: str
    html_text: str | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "parent": self.project_gid,
            "title": self.title,
            "text": self.text,
            "color": self.color,
        }
        if self.html_text:
            data["html_text"] = self.html_text
        return {"data": data, "metadata": self.metadata}

    def to_request(self) -> dict[str, Any]:
        return {"data": self.to_dict()["data"]}


@dataclass(frozen=True)
class AsanaProjectStatusUpdatePublishResult:
    """Summary of an Asana project status update publish or dry run."""

    status_code: int | None
    project_gid: str
    status_update_gid: str | None
    title: str
    permalink: str | None
    dry_run: bool
    payload: dict[str, Any]


class AsanaProjectStatusUpdatePublisher:
    """Build and optionally create Asana project status updates."""

    def __init__(
        self,
        project_gid: str,
        *,
        access_token: str | None = None,
        api_url: str = DEFAULT_ASANA_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.project_gid = _required_text(project_gid, "Asana project_gid is required")
        self.access_token = _optional_text(access_token)
        self.api_url = _required_text(api_url, "Asana api_url is required").rstrip("/")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        project_gid: str | None = None,
        access_token: str | None = None,
        api_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> AsanaProjectStatusUpdatePublisher:
        resolved_project_gid = project_gid or os.getenv("ASANA_PROJECT_GID")
        if not resolved_project_gid:
            raise AsanaProjectStatusUpdatePublishError(
                "Asana project_gid is required; pass project_gid or set ASANA_PROJECT_GID"
            )
        return cls(
            resolved_project_gid,
            access_token=access_token or os.getenv("ASANA_ACCESS_TOKEN"),
            api_url=api_url or os.getenv("ASANA_API_URL", DEFAULT_ASANA_API_URL),
            timeout=timeout,
            client=client,
        )

    @property
    def status_updates_endpoint(self) -> str:
        return f"{self.api_url}/projects/{self.project_gid}/project_statuses"

    def build_status_update_payload(
        self,
        *,
        title: str,
        text: str,
        color: str = "green",
        html_text: str | None = None,
    ) -> AsanaProjectStatusUpdatePayload:
        resolved_title = _required_text(title, "Asana status update title is required")
        resolved_text = _required_text(text, "Asana status update text is required")
        resolved_color = _required_text(color, "Asana status update color is required")
        return AsanaProjectStatusUpdatePayload(
            project_gid=self.project_gid,
            title=resolved_title,
            text=resolved_text,
            color=resolved_color,
            html_text=_optional_text(html_text),
            metadata={
                "publisher": "max.asana_project_status_updates",
                "project_gid": self.project_gid,
            },
        )

    def publish(
        self,
        *,
        title: str,
        text: str,
        color: str = "green",
        html_text: str | None = None,
        dry_run: bool = True,
    ) -> AsanaProjectStatusUpdatePublishResult:
        payload_obj = self.build_status_update_payload(
            title=title,
            text=text,
            color=color,
            html_text=html_text,
        )
        payload = payload_obj.to_dict()
        if dry_run:
            return AsanaProjectStatusUpdatePublishResult(
                None,
                self.project_gid,
                None,
                payload_obj.title,
                None,
                True,
                payload,
            )
        if not self.access_token:
            raise AsanaProjectStatusUpdatePublishError(
                "ASANA_ACCESS_TOKEN is required for live Asana project status update publishing; use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.status_updates_endpoint,
                    json=payload_obj.to_request(),
                    headers={
                        "Authorization": f"Bearer {self.access_token}",
                        "Content-Type": "application/json",
                        "User-Agent": "max-asana-project-status-updates-publisher/1",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise AsanaProjectStatusUpdatePublishError(
                    f"Asana project status update publish failed for {self.status_updates_endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise AsanaProjectStatusUpdatePublishError(
                f"Asana project status update publish failed with HTTP {response.status_code}: {_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        status_update_gid = _optional_text(data.get("gid"))
        if not status_update_gid:
            raise AsanaProjectStatusUpdatePublishError(
                "Asana project status update publish failed: response did not include status update gid",
                status_code=response.status_code,
            )
        return AsanaProjectStatusUpdatePublishResult(
            response.status_code,
            self.project_gid,
            status_update_gid,
            _optional_text(data.get("title")) or payload_obj.title,
            _optional_text(data.get("permalink_url")),
            False,
            payload,
        )


AsanaProjectStatusUpdatesPublisher = AsanaProjectStatusUpdatePublisher


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise AsanaProjectStatusUpdatePublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    return text if len(text) <= limit else text[:limit] + "..."


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise AsanaProjectStatusUpdatePublishError(
            "Asana project status update publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    return body if isinstance(body, dict) else {}

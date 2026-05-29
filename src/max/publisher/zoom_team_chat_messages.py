"""Zoom Team Chat message publisher for generated TactSpec previews."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, markdown_summary, metadata, optional_text, required_text, required_url, response_json, response_preview, validate_tact_spec

DEFAULT_API_URL = "https://api.zoom.us/v2"


class ZoomTeamChatMessagePublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ZoomTeamChatMessagePublishResult:
    status_code: int | None
    recipient_id: str
    message_id: str | None
    dry_run: bool
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class ZoomTeamChatMessagePublisher:
    def __init__(self, *, access_token: str | None = None, recipient_id: str | None = None, api_url: str = DEFAULT_API_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.access_token = optional_text(access_token)
        self.recipient_id = optional_text(recipient_id)
        self.api_url = required_url(api_url, "Zoom api_url must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> ZoomTeamChatMessagePublisher:
        return cls(
            access_token=kwargs.get("access_token") or os.getenv("ZOOM_ACCESS_TOKEN"),
            recipient_id=kwargs.get("recipient_id") or os.getenv("ZOOM_CHAT_RECIPIENT_ID"),
            api_url=kwargs.get("api_url") or os.getenv("ZOOM_API_URL", DEFAULT_API_URL),
            timeout=kwargs.get("timeout", DEFAULT_TIMEOUT_SECONDS),
            client=kwargs.get("client"),
        )

    @property
    def endpoint(self) -> str:
        return f"{self.api_url}/chat/users/me/messages"

    def build_message_payload(self, tact_spec: dict[str, Any], *, recipient_id: str | None = None) -> dict[str, Any]:
        try:
            validate_tact_spec(tact_spec, label="Zoom Team Chat message")
            resolved_recipient = required_text(optional_text(recipient_id) or self.recipient_id, "ZOOM_CHAT_RECIPIENT_ID is required for Zoom Team Chat publishing")
        except ValueError as exc:
            raise ZoomTeamChatMessagePublishError(str(exc)) from exc
        meta = metadata(tact_spec, publisher="max.zoom_team_chat_messages")
        message = {"robot_jid": resolved_recipient, "to_jid": resolved_recipient, "content": {"head": {"text": "Max TactSpec summary"}, "body": [{"type": "message", "text": markdown_summary(tact_spec, meta)}]}}
        return {"endpoint": self.endpoint, "recipient_id": resolved_recipient, "message": message, "metadata": meta}

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True, recipient_id: str | None = None) -> ZoomTeamChatMessagePublishResult:
        payload = self.build_message_payload(tact_spec, recipient_id=recipient_id)
        if dry_run:
            return ZoomTeamChatMessagePublishResult(None, payload["recipient_id"], None, True, payload)
        if not self.access_token:
            raise ZoomTeamChatMessagePublishError("ZOOM_ACCESS_TOKEN is required for live Zoom Team Chat publishing; use dry_run to preview")
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.endpoint, json=payload["message"], headers={"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json", "User-Agent": "max-zoom-team-chat-messages-publisher/1"}, timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise ZoomTeamChatMessagePublishError(f"Zoom Team Chat publish failed: {str(exc).replace(self.access_token, '[REDACTED]') if self.access_token else exc}") from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise ZoomTeamChatMessagePublishError(f"Zoom Team Chat publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.access_token])}", status_code=response.status_code)
        body = response_json(response, ZoomTeamChatMessagePublishError, "Zoom Team Chat publish failed: response was not valid JSON")
        return ZoomTeamChatMessagePublishResult(response.status_code, payload["recipient_id"], optional_text(body.get("id") or body.get("message_id")), False, payload, body)


ZoomTeamChatMessagesPublisher = ZoomTeamChatMessagePublisher

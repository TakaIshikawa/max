"""Webex space message publisher for Max buildable units."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, redact_text, required_text, required_url, response_json, response_preview
from max.publisher.stripe_customer_notes import _RETRYABLE_STATUS_CODES, _unit_fields

DEFAULT_API_URL = "https://webexapis.com"


class WebexSpaceMessagePublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class WebexSpaceMessagePublishResult:
    status_code: int | None
    message_id: str | None
    web_url: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class WebexSpaceMessagePublisher:
    def __init__(self, *, access_token: str | None = None, room_id: str | None = None, api_url: str = DEFAULT_API_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS, max_retries: int = 2, client: httpx.Client | None = None) -> None:
        self.access_token = optional_text(access_token)
        self.room_id = optional_text(room_id)
        self.api_url = required_url(api_url, "Webex api_url must be an absolute http(s) URL")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> WebexSpaceMessagePublisher:
        return cls(access_token=kwargs.pop("access_token", None) or os.getenv("WEBEX_ACCESS_TOKEN"), room_id=kwargs.pop("room_id", None) or os.getenv("WEBEX_ROOM_ID"), api_url=kwargs.pop("api_url", None) or os.getenv("WEBEX_API_URL", DEFAULT_API_URL), **kwargs)

    @property
    def messages_endpoint(self) -> str:
        return f"{self.api_url}/v1/messages"

    def build_message_payload(self, unit: dict[str, Any]) -> dict[str, Any]:
        try:
            room_id = required_text(self.room_id, "WEBEX_ROOM_ID is required for Webex space message publishing")
        except ValueError as exc:
            raise WebexSpaceMessagePublishError(str(exc), token=self.access_token) from exc
        fields = _unit_fields(unit)
        markdown = "\n".join([
            f"### [Max] {fields['title']}",
            "",
            f"**Idea ID:** {fields['idea_id']}",
            f"**Status:** {fields['status']}",
            f"**Score:** {fields['score']}",
            "",
            f"**Problem**\n{fields['problem']}",
            "",
            f"**Solution**\n{fields['solution']}",
        ])
        return {"roomId": room_id, "markdown": markdown, "metadata": {"publisher": "max.webex_space_messages", "idea_id": fields["idea_id"], "status": fields["status"], "score": fields["score"]}}

    def publish(self, unit: dict[str, Any], *, dry_run: bool = True) -> WebexSpaceMessagePublishResult:
        payload = self.build_message_payload(unit)
        if dry_run:
            return WebexSpaceMessagePublishResult(None, None, None, True, self.messages_endpoint, payload)
        if not self.access_token:
            raise WebexSpaceMessagePublishError("WEBEX_ACCESS_TOKEN is required for live Webex space message publishing; use dry_run to preview")
        response = self._post_with_retries(payload)
        body = response_json(response, WebexSpaceMessagePublishError, "Webex space message publish failed: response was not valid JSON")
        return WebexSpaceMessagePublishResult(response.status_code, optional_text(body.get("id")), optional_text(body.get("webUrl")), False, self.messages_endpoint, payload, body)

    def _post_with_retries(self, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            last_response: httpx.Response | None = None
            for attempt in range(self.max_retries + 1):
                response = client.post(self.messages_endpoint, json={k: v for k, v in payload.items() if k != "metadata"}, headers=self._headers(), timeout=self.timeout)
                last_response = response
                if response.status_code not in _RETRYABLE_STATUS_CODES or attempt >= self.max_retries:
                    break
            assert last_response is not None
            if not 200 <= last_response.status_code < 300:
                raise WebexSpaceMessagePublishError(f"Webex space message publish failed with HTTP {last_response.status_code}: {response_preview(last_response, secrets=[self.access_token])}", status_code=last_response.status_code, token=self.access_token)
            return last_response
        finally:
            if close_client:
                client.close()

    def _headers(self) -> dict[str, str]:
        assert self.access_token is not None
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json", "User-Agent": "max-webex-space-messages-publisher/1"}


WebexSpaceMessagesPublisher = WebexSpaceMessagePublisher

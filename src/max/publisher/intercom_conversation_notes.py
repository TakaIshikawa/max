"""Intercom conversation note publisher for generated TactSpec previews."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import (
    DEFAULT_TIMEOUT_SECONDS,
    markdown_summary,
    metadata,
    optional_text,
    quote_path,
    redact_text,
    required_text,
    required_url,
    response_json,
    response_preview,
    source_id,
    title,
    validate_tact_spec,
)


DEFAULT_API_URL = "https://api.intercom.io"


class IntercomConversationNotePublishError(RuntimeError):
    """Raised when an Intercom note publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class IntercomConversationNotePayload:
    """Intercom conversation reply payload plus Max metadata."""

    conversation_id: str
    body: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "message_type": "note",
            "type": "admin",
            "body": self.body,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class IntercomConversationNotePublishResult:
    """Summary of an Intercom publish or dry run."""

    status_code: int | None
    conversation_id: str | None
    note_id: str | None
    dry_run: bool
    payload: dict[str, Any]


class IntercomConversationNotePublisher:
    """Build and optionally create Intercom conversation notes."""

    def __init__(
        self,
        *,
        conversation_id: str | None = None,
        access_token: str | None = None,
        api_url: str = DEFAULT_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.conversation_id = optional_text(conversation_id)
        self.access_token = optional_text(access_token)
        self.api_url = required_url(api_url, "Intercom api_url must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        conversation_id: str | None = None,
        access_token: str | None = None,
        api_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> IntercomConversationNotePublisher:
        return cls(
            conversation_id=conversation_id or os.getenv("INTERCOM_CONVERSATION_ID"),
            access_token=access_token or os.getenv("INTERCOM_ACCESS_TOKEN"),
            api_url=api_url or os.getenv("INTERCOM_API_URL", DEFAULT_API_URL),
            timeout=timeout,
            client=client,
        )

    @property
    def reply_endpoint(self) -> str:
        conversation_id = required_text(
            self.conversation_id,
            "Intercom conversation_id is required; pass conversation_id or set INTERCOM_CONVERSATION_ID",
        )
        return f"{self.api_url}/conversations/{quote_path(conversation_id)}/reply"

    def build_note_payload(self, tact_spec: dict[str, Any], *, conversation_id: str | None = None) -> IntercomConversationNotePayload:
        try:
            validate_tact_spec(tact_spec, label="Intercom conversation note")
            resolved_conversation_id = optional_text(conversation_id) or self.conversation_id
            resolved_conversation_id = required_text(
                resolved_conversation_id,
                "Intercom conversation_id is required; pass conversation_id or set INTERCOM_CONVERSATION_ID",
            )
        except ValueError as exc:
            raise IntercomConversationNotePublishError(str(exc), token=self.access_token) from exc
        note_metadata = metadata(tact_spec, publisher="max.intercom_conversation_notes")
        return IntercomConversationNotePayload(
            conversation_id=resolved_conversation_id,
            body=markdown_summary(tact_spec, note_metadata),
            metadata=note_metadata,
        )

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True, conversation_id: str | None = None) -> IntercomConversationNotePublishResult:
        payload = self.build_note_payload(tact_spec, conversation_id=conversation_id).to_dict()
        if dry_run:
            return IntercomConversationNotePublishResult(None, payload["conversation_id"], None, True, payload)
        if not self.access_token:
            raise IntercomConversationNotePublishError(
                "INTERCOM_ACCESS_TOKEN is required for live Intercom conversation note publishing; use dry_run to preview"
            )
        request_json = _request_payload(payload)
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.reply_endpoint, json=request_json, headers=self._headers(), timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise IntercomConversationNotePublishError(
                f"Intercom conversation note publish failed for {self.reply_endpoint}: {exc}",
                token=self.access_token,
            ) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise IntercomConversationNotePublishError(
                f"Intercom conversation note publish failed with HTTP {response.status_code}: "
                f"{response_preview(response, secrets=[self.access_token])}",
                status_code=response.status_code,
                token=self.access_token,
            )
        body = response_json(
            response,
            IntercomConversationNotePublishError,
            "Intercom conversation note publish failed: response was not valid JSON",
        )
        conversation_id = optional_text(body.get("id")) or payload["conversation_id"]
        note_id = _note_id(body)
        return IntercomConversationNotePublishResult(response.status_code, conversation_id, note_id, False, {**payload, "request": request_json})

    def _headers(self) -> dict[str, str]:
        assert self.access_token is not None
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Intercom-Version": "2.11",
            "User-Agent": "max-intercom-conversation-notes-publisher/1",
        }


IntercomConversationNotesPublisher = IntercomConversationNotePublisher


def _request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {"message_type": "note", "type": "admin", "body": payload["body"]}


def _note_id(body: dict[str, Any]) -> str | None:
    for key in ("note", "conversation_message", "conversation_part"):
        value = body.get(key)
        if isinstance(value, dict) and value.get("id") is not None:
            return str(value["id"])
    parts = body.get("conversation_parts")
    if isinstance(parts, dict):
        for item in parts.get("conversation_parts") or []:
            if isinstance(item, dict) and item.get("id") is not None:
                return str(item["id"])
    if body.get("id") is not None and body.get("type") == "note":
        return str(body["id"])
    return None

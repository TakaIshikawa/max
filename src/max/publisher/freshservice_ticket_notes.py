"""Freshservice ticket note publisher for Max buildable units."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, redact_text, required_text, required_url, response_json, response_preview
from max.publisher.stripe_customer_notes import _RETRYABLE_STATUS_CODES, _unit_fields


class FreshserviceTicketNotePublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, api_key: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[api_key, _basic_token(api_key)]))
        self.status_code = status_code


@dataclass(frozen=True)
class FreshserviceTicketNotePayload:
    ticket_id: str
    body: str
    private: bool
    metadata: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {"ticket_id": self.ticket_id, "body": self.body, "private": self.private, "metadata": self.metadata}

    def to_request_json(self) -> dict[str, Any]:
        return {"body": self.body, "private": self.private}


@dataclass(frozen=True)
class FreshserviceTicketNotePublishResult:
    status_code: int | None
    note_id: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]


class FreshserviceTicketNotePublisher:
    def __init__(
        self,
        *,
        ticket_id: str | None = None,
        api_key: str | None = None,
        domain: str | None = None,
        api_url: str | None = None,
        private: bool = True,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self.ticket_id = optional_text(ticket_id)
        self.api_key = optional_text(api_key)
        self.domain = optional_text(domain)
        self.api_url = required_url(api_url or _api_url_from_domain(self.domain), "Freshservice api_url must be an absolute http(s) URL")
        self.private = private
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> FreshserviceTicketNotePublisher:
        return cls(
            ticket_id=kwargs.pop("ticket_id", None) or os.getenv("FRESHSERVICE_TICKET_ID"),
            api_key=kwargs.pop("api_key", None) or os.getenv("FRESHSERVICE_API_KEY"),
            domain=kwargs.pop("domain", None) or os.getenv("FRESHSERVICE_DOMAIN"),
            api_url=kwargs.pop("api_url", None) or os.getenv("FRESHSERVICE_API_URL"),
            **kwargs,
        )

    def notes_endpoint(self, ticket_id: str | None = None) -> str:
        resolved = required_text(optional_text(ticket_id) or self.ticket_id, "Freshservice ticket_id is required; pass ticket_id or set FRESHSERVICE_TICKET_ID")
        return f"{self.api_url}/api/v2/tickets/{quote(resolved, safe='')}/notes"

    def build_note_payload(self, unit: dict[str, Any], *, ticket_id: str | None = None, private: bool | None = None) -> FreshserviceTicketNotePayload:
        resolved = required_text(optional_text(ticket_id) or self.ticket_id, "Freshservice ticket_id is required; pass ticket_id or set FRESHSERVICE_TICKET_ID")
        fields = _unit_fields(unit)
        metadata = {"publisher": "max.freshservice_ticket_notes", "idea_id": fields["idea_id"], "status": fields["status"], "category": fields["category"], "score": fields["score"]}
        return FreshserviceTicketNotePayload(resolved, _note_body(fields), self.private if private is None else private, metadata)

    def publish(self, unit: dict[str, Any], *, dry_run: bool = True, ticket_id: str | None = None, private: bool | None = None) -> FreshserviceTicketNotePublishResult:
        payload = self.build_note_payload(unit, ticket_id=ticket_id, private=private)
        endpoint = self.notes_endpoint(payload.ticket_id)
        payload_dict = payload.to_dict()
        if dry_run:
            return FreshserviceTicketNotePublishResult(None, None, True, endpoint, payload_dict)
        if not self.api_key:
            raise FreshserviceTicketNotePublishError("FRESHSERVICE_API_KEY is required for live Freshservice ticket note publishing; use dry_run to preview")
        response = self._post_with_retries(endpoint, payload.to_request_json())
        body = response_json(response, FreshserviceTicketNotePublishError, "Freshservice ticket note publish failed: response was not valid JSON")
        note = body.get("note") if isinstance(body.get("note"), dict) else body
        return FreshserviceTicketNotePublishResult(response.status_code, optional_text(note.get("id")) if isinstance(note, dict) else None, False, endpoint, payload_dict)

    def _post_with_retries(self, endpoint: str, request_json: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response: httpx.Response | None = None
            for attempt in range(self.max_retries + 1):
                response = client.post(endpoint, json=request_json, headers=self._headers(), timeout=self.timeout)
                if response.status_code not in _RETRYABLE_STATUS_CODES or attempt >= self.max_retries:
                    break
            assert response is not None
            if not 200 <= response.status_code < 300:
                raise FreshserviceTicketNotePublishError(
                    f"Freshservice ticket note publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.api_key])}",
                    status_code=response.status_code,
                    api_key=self.api_key,
                )
            return response
        finally:
            if close_client:
                client.close()

    def _headers(self) -> dict[str, str]:
        assert self.api_key is not None
        return {"Accept": "application/json", "Authorization": f"Basic {_basic_token(self.api_key)}", "Content-Type": "application/json", "User-Agent": "max-freshservice-ticket-notes-publisher/1"}


FreshserviceTicketNotesPublisher = FreshserviceTicketNotePublisher


def _api_url_from_domain(domain: str | None) -> str:
    if not domain:
        return "https://example.freshservice.com"
    if domain.startswith("http://") or domain.startswith("https://"):
        return domain
    host = domain if "." in domain else f"{domain}.freshservice.com"
    return f"https://{host}"


def _basic_token(api_key: str | None) -> str | None:
    if not api_key:
        return None
    return base64.b64encode(f"{api_key}:X".encode("utf-8")).decode("ascii")


def _note_body(fields: dict[str, str]) -> str:
    return "\n".join(
        [
            fields["title"],
            f"Status: {fields['status']}",
            f"Category: {fields['category']}",
            f"Problem: {fields['problem']}",
            f"Solution: {fields['solution']}",
            f"Idea ID: {fields['idea_id']}",
            f"Score: {fields['score']}",
        ]
    )

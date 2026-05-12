"""Zendesk ticket internal note publisher for Max buildable units."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

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
    validate_tact_spec,
)


DEFAULT_API_URL = "https://{subdomain}.zendesk.com"
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class ZendeskTicketNotePublishError(RuntimeError):
    """Raised when a Zendesk ticket note publish cannot be completed."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        secrets: list[str | None] | None = None,
    ) -> None:
        super().__init__(redact_text(message, secrets=secrets))
        self.status_code = status_code


@dataclass(frozen=True)
class ZendeskTicketNotePayload:
    """Zendesk ticket comment payload plus Max metadata."""

    ticket_id: str
    body: str
    public: bool
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "body": self.body,
            "public": self.public,
            "metadata": self.metadata,
        }

    def to_request(self) -> dict[str, Any]:
        return {"ticket": {"comment": {"body": self.body, "public": self.public}}}


@dataclass(frozen=True)
class ZendeskTicketNotePublishResult:
    """Summary of a Zendesk ticket note publish or dry run."""

    status_code: int | None
    ticket_id: str
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class ZendeskTicketNotePublisher:
    """Build and optionally append private notes to existing Zendesk tickets."""

    def __init__(
        self,
        subdomain: str | None = None,
        *,
        api_url: str | None = None,
        ticket_id: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        bearer_token: str | None = None,
        note_body: str | None = None,
        public: bool = False,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_url = _zendesk_api_url(subdomain=subdomain, api_url=api_url)
        self.ticket_id = optional_text(ticket_id)
        self.email = optional_text(email)
        self.api_token = optional_text(api_token)
        self.bearer_token = optional_text(bearer_token)
        self.note_body = optional_text(note_body)
        self.public = bool(public)
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        subdomain: str | None = None,
        api_url: str | None = None,
        ticket_id: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        bearer_token: str | None = None,
        note_body: str | None = None,
        public: bool | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> ZendeskTicketNotePublisher:
        return cls(
            subdomain=subdomain or os.getenv("ZENDESK_SUBDOMAIN"),
            api_url=api_url or os.getenv("ZENDESK_API_URL") or os.getenv("ZENDESK_BASE_URL"),
            ticket_id=ticket_id or os.getenv("ZENDESK_TICKET_ID"),
            email=email or os.getenv("ZENDESK_EMAIL"),
            api_token=api_token or os.getenv("ZENDESK_API_TOKEN"),
            bearer_token=bearer_token or os.getenv("ZENDESK_BEARER_TOKEN"),
            note_body=note_body or os.getenv("ZENDESK_NOTE_BODY"),
            public=_env_bool("ZENDESK_NOTE_PUBLIC", default=False) if public is None else public,
            timeout=timeout,
            max_retries=max_retries,
            client=client,
        )

    def ticket_endpoint(self, ticket_id: str | None = None) -> str:
        resolved = _required_ticket_id(optional_text(ticket_id) or self.ticket_id)
        return f"{self.api_url}/api/v2/tickets/{quote_path(resolved)}.json"

    def build_note_payload(
        self,
        unit: dict[str, Any],
        *,
        ticket_id: str | None = None,
        note_body: str | None = None,
        public: bool | None = None,
    ) -> ZendeskTicketNotePayload:
        try:
            validate_tact_spec(unit, label="Zendesk ticket note")
            resolved_ticket_id = _required_ticket_id(optional_text(ticket_id) or self.ticket_id)
        except ValueError as exc:
            raise ZendeskTicketNotePublishError(str(exc), secrets=self._secrets()) from exc
        note_metadata = metadata(
            unit,
            publisher="max.zendesk_ticket_notes",
            extra={"zendesk_ticket_id": resolved_ticket_id},
        )
        body = optional_text(note_body) or self.note_body or markdown_summary(unit, note_metadata)
        return ZendeskTicketNotePayload(
            ticket_id=resolved_ticket_id,
            body=body,
            public=self.public if public is None else bool(public),
            metadata=note_metadata,
        )

    def publish(
        self,
        unit: dict[str, Any],
        *,
        dry_run: bool = True,
        ticket_id: str | None = None,
        note_body: str | None = None,
        public: bool | None = None,
    ) -> ZendeskTicketNotePublishResult:
        payload = self.build_note_payload(
            unit,
            ticket_id=ticket_id,
            note_body=note_body,
            public=public,
        )
        endpoint = self.ticket_endpoint(payload.ticket_id)
        payload_dict = payload.to_dict()
        if dry_run:
            return ZendeskTicketNotePublishResult(None, payload.ticket_id, True, endpoint, payload_dict)

        self._validate_live_auth()
        response = self._put_with_retries(endpoint, payload.to_request())
        body = response_json(
            response,
            ZendeskTicketNotePublishError,
            "Zendesk ticket note publish failed: response was not valid JSON",
        )
        return ZendeskTicketNotePublishResult(
            response.status_code,
            payload.ticket_id,
            False,
            endpoint,
            payload_dict,
            body,
        )

    def _put_with_retries(self, endpoint: str, request_json: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            last_response: httpx.Response | None = None
            for attempt in range(self.max_retries + 1):
                try:
                    response = client.put(
                        endpoint,
                        json=request_json,
                        headers=self._headers(),
                        timeout=self.timeout,
                    )
                except (httpx.RequestError, httpx.TimeoutException) as exc:
                    if attempt >= self.max_retries:
                        raise ZendeskTicketNotePublishError(
                            f"Zendesk ticket note publish failed for {endpoint}: {exc}",
                            secrets=self._secrets(),
                        ) from exc
                    continue
                last_response = response
                if response.status_code not in _RETRYABLE_STATUS_CODES or attempt >= self.max_retries:
                    break
            assert last_response is not None
            if not 200 <= last_response.status_code < 300:
                raise ZendeskTicketNotePublishError(
                    f"Zendesk ticket note publish failed with HTTP {last_response.status_code}: "
                    f"{response_preview(last_response, secrets=self._secrets())}",
                    status_code=last_response.status_code,
                    secrets=self._secrets(),
                )
            return last_response
        finally:
            if close_client:
                client.close()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "max-zendesk-ticket-notes-publisher/1",
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
            return headers
        assert self.email is not None and self.api_token is not None
        credentials = f"{self.email}/token:{self.api_token}".encode("utf-8")
        headers["Authorization"] = f"Basic {base64.b64encode(credentials).decode('ascii')}"
        return headers

    def _validate_live_auth(self) -> None:
        if self.bearer_token:
            return
        if self.email and self.api_token:
            return
        raise ZendeskTicketNotePublishError(
            "ZENDESK_EMAIL and ZENDESK_API_TOKEN, or ZENDESK_BEARER_TOKEN, are required "
            "for live Zendesk ticket note publishing; use dry_run to preview",
            secrets=self._secrets(),
        )

    def _secrets(self) -> list[str | None]:
        return [self.api_token, self.bearer_token]


ZendeskTicketNotesPublisher = ZendeskTicketNotePublisher


def _zendesk_api_url(*, subdomain: str | None, api_url: str | None) -> str:
    if api_url:
        raw = optional_text(api_url)
        if raw and not raw.startswith(("http://", "https://")):
            raw = f"https://{raw}"
        try:
            return required_url(raw, "Zendesk api_url must be an absolute http(s) URL")
        except ValueError as exc:
            raise ZendeskTicketNotePublishError(str(exc)) from exc

    try:
        raw_subdomain = required_text(
            subdomain,
            "Zendesk subdomain or api_url is required; pass subdomain/api_url "
            "or set ZENDESK_SUBDOMAIN/ZENDESK_API_URL",
        ).strip().rstrip("/")
    except ValueError as exc:
        raise ZendeskTicketNotePublishError(str(exc)) from exc
    if "://" in raw_subdomain:
        parts = urlsplit(raw_subdomain)
        raw_subdomain = parts.netloc or parts.path
    domain = raw_subdomain if "." in raw_subdomain else f"{raw_subdomain}.zendesk.com"
    if "/" in domain or not domain:
        raise ZendeskTicketNotePublishError("Zendesk subdomain must be a subdomain, domain, or api_url")
    return f"https://{domain.lower()}"


def _required_ticket_id(value: str | None) -> str:
    try:
        return required_text(value, "Zendesk ticket_id is required; pass ticket_id or set ZENDESK_TICKET_ID")
    except ValueError as exc:
        raise ZendeskTicketNotePublishError(str(exc)) from exc


def _env_bool(name: str, *, default: bool) -> bool:
    value = optional_text(os.getenv(name))
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}

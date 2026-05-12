"""Calendly invitee note publisher for Max buildable units."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, redact_text, required_text, required_url, response_json, response_preview
from max.publisher.stripe_customer_notes import _RETRYABLE_STATUS_CODES, _unit_fields

DEFAULT_API_URL = "https://api.calendly.com"


class CalendlyInviteeNotePublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class CalendlyInviteeNotePayload:
    invitee_uri: str
    note: str
    metadata: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {"invitee_uri": self.invitee_uri, "note": self.note, "metadata": self.metadata}

    def to_request_json(self) -> dict[str, Any]:
        return {"note": self.note}


@dataclass(frozen=True)
class CalendlyInviteeNotePublishResult:
    status_code: int | None
    note_uri: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]


class CalendlyInviteeNotePublisher:
    def __init__(
        self,
        *,
        invitee_uuid: str | None = None,
        invitee_uri: str | None = None,
        token: str | None = None,
        api_url: str = DEFAULT_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self.invitee_uuid = optional_text(invitee_uuid)
        self.invitee_uri = optional_text(invitee_uri)
        self.token = optional_text(token)
        self.api_url = required_url(api_url, "Calendly api_url must be an absolute http(s) URL")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> CalendlyInviteeNotePublisher:
        return cls(
            invitee_uuid=kwargs.pop("invitee_uuid", None) or os.getenv("CALENDLY_INVITEE_UUID"),
            invitee_uri=kwargs.pop("invitee_uri", None) or os.getenv("CALENDLY_INVITEE_URI"),
            token=kwargs.pop("token", None) or os.getenv("CALENDLY_API_TOKEN"),
            api_url=kwargs.pop("api_url", None) or os.getenv("CALENDLY_API_URL", DEFAULT_API_URL),
            **kwargs,
        )

    def invitee_notes_endpoint(self) -> str:
        return f"{self._normalized_invitee_uri()}/notes"

    def build_note_payload(self, unit: dict[str, Any]) -> CalendlyInviteeNotePayload:
        fields = _unit_fields(unit)
        metadata = {"publisher": "max.calendly_invitee_notes", "idea_id": fields["idea_id"], "status": fields["status"], "category": fields["category"], "score": fields["score"]}
        note = _note_text(fields, unit)
        return CalendlyInviteeNotePayload(self._normalized_invitee_uri(), note, metadata)

    def publish(self, unit: dict[str, Any], *, dry_run: bool = True) -> CalendlyInviteeNotePublishResult:
        payload = self.build_note_payload(unit)
        endpoint = self.invitee_notes_endpoint()
        payload_dict = payload.to_dict()
        if dry_run:
            return CalendlyInviteeNotePublishResult(None, None, True, endpoint, payload_dict)
        if not self.token:
            raise CalendlyInviteeNotePublishError("CALENDLY_API_TOKEN is required for live Calendly invitee note publishing; use dry_run to preview")
        response = self._post_with_retries(endpoint, payload.to_request_json())
        body = response_json(response, CalendlyInviteeNotePublishError, "Calendly invitee note publish failed: response was not valid JSON")
        return CalendlyInviteeNotePublishResult(response.status_code, optional_text(body.get("uri")) or optional_text(body.get("resource", {}).get("uri") if isinstance(body.get("resource"), dict) else None), False, endpoint, payload_dict)

    def _normalized_invitee_uri(self) -> str:
        invitee_uri = optional_text(self.invitee_uri)
        if invitee_uri:
            parts = urlsplit(invitee_uri)
            path = parts.path.rstrip("/") if parts.scheme and parts.netloc else invitee_uri.rstrip("/")
            return f"{self.api_url}{path}" if path.startswith("/") else f"{self.api_url}/invitees/{quote(path, safe='')}"
        invitee_uuid = required_text(self.invitee_uuid, "Calendly invitee_uuid or invitee_uri is required; pass one or set CALENDLY_INVITEE_UUID/CALENDLY_INVITEE_URI")
        return f"{self.api_url}/invitees/{quote(invitee_uuid, safe='')}"

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
                raise CalendlyInviteeNotePublishError(
                    f"Calendly invitee note publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.token])}",
                    status_code=response.status_code,
                    token=self.token,
                )
            return response
        finally:
            if close_client:
                client.close()

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {"Accept": "application/json", "Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "User-Agent": "max-calendly-invitee-notes-publisher/1"}


CalendlyInviteeNotesPublisher = CalendlyInviteeNotePublisher


def _note_text(fields: dict[str, str], unit: dict[str, Any]) -> str:
    execution = unit.get("execution") if isinstance(unit.get("execution"), dict) else {}
    evidence = unit.get("evidence") if isinstance(unit.get("evidence"), dict) else {}
    links = unit.get("evidence_links") or evidence.get("links") or []
    link_text = ", ".join(str(link).strip() for link in links if str(link).strip()) if isinstance(links, list) else optional_text(links)
    return "\n".join(
        [
            fields["title"],
            f"Problem: {fields['problem']}",
            f"Solution: {fields['solution']}",
            f"Validation plan: {optional_text(execution.get('validation_plan')) or optional_text(unit.get('validation_plan')) or 'Not specified'}",
            f"Evidence links: {link_text or 'None'}",
            f"Idea ID: {fields['idea_id']}",
            f"Status: {fields['status']}",
            f"Score: {fields['score']}",
        ]
    )

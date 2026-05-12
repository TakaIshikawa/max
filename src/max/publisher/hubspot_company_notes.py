"""HubSpot company note publisher for Max buildable units."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, quote_path, redact_text, required_text, required_url, response_json, response_preview
from max.publisher.stripe_customer_notes import _RETRYABLE_STATUS_CODES, _unit_fields

DEFAULT_API_URL = "https://api.hubapi.com"
HUBSPOT_COMPANY_NOTE_ASSOCIATION_TYPE_ID = 190


class HubSpotCompanyNotePublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class HubSpotCompanyNotePayload:
    company_id: str
    properties: dict[str, str]
    associations: list[dict[str, Any]]
    metadata: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "company_id": self.company_id,
            "properties": self.properties,
            "associations": self.associations,
            "metadata": self.metadata,
        }

    def to_request_json(self) -> dict[str, Any]:
        return {"properties": self.properties, "associations": self.associations}


@dataclass(frozen=True)
class HubSpotCompanyNotePublishResult:
    status_code: int | None
    note_id: str | None
    company_id: str
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]


class HubSpotCompanyNotePublisher:
    def __init__(
        self,
        *,
        company_id: str | None = None,
        token: str | None = None,
        api_url: str = DEFAULT_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        note_title: str | None = None,
        note_body: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.company_id = optional_text(company_id)
        self.token = optional_text(token)
        self.api_url = required_url(api_url, "HubSpot api_url must be an absolute http(s) URL")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.note_title = optional_text(note_title)
        self.note_body = optional_text(note_body)
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> HubSpotCompanyNotePublisher:
        return cls(
            company_id=kwargs.pop("company_id", None) or os.getenv("HUBSPOT_COMPANY_ID"),
            token=kwargs.pop("token", None) or os.getenv("HUBSPOT_ACCESS_TOKEN"),
            api_url=kwargs.pop("api_url", None) or os.getenv("HUBSPOT_API_URL", DEFAULT_API_URL),
            **kwargs,
        )

    @property
    def notes_endpoint(self) -> str:
        return f"{self.api_url}/crm/v3/objects/notes"

    def build_note_payload(self, unit: dict[str, Any], *, company_id: str | None = None) -> HubSpotCompanyNotePayload:
        resolved = required_text(optional_text(company_id) or self.company_id, "HubSpot company_id is required; pass company_id or set HUBSPOT_COMPANY_ID")
        fields = _unit_fields(unit)
        title = self.note_title or fields["title"]
        body = self.note_body or _note_body(fields)
        metadata = {
            "publisher": "max.hubspot_company_notes",
            "idea_id": fields["idea_id"],
            "status": fields["status"],
            "category": fields["category"],
            "score": fields["score"],
        }
        return HubSpotCompanyNotePayload(
            company_id=resolved,
            properties={"hs_note_body": f"{title}\n\n{body}"},
            associations=[
                {
                    "to": {"id": resolved},
                    "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": HUBSPOT_COMPANY_NOTE_ASSOCIATION_TYPE_ID}],
                }
            ],
            metadata=metadata,
        )

    def publish(self, unit: dict[str, Any], *, dry_run: bool = True, company_id: str | None = None) -> HubSpotCompanyNotePublishResult:
        payload = self.build_note_payload(unit, company_id=company_id)
        payload_dict = payload.to_dict()
        if dry_run:
            return HubSpotCompanyNotePublishResult(None, None, payload.company_id, True, self.notes_endpoint, payload_dict)
        if not self.token:
            raise HubSpotCompanyNotePublishError("HUBSPOT_ACCESS_TOKEN is required for live HubSpot company note publishing; use dry_run to preview")
        response = self._post_with_retries(payload.to_request_json())
        body = response_json(response, HubSpotCompanyNotePublishError, "HubSpot company note publish failed: response was not valid JSON")
        return HubSpotCompanyNotePublishResult(response.status_code, optional_text(body.get("id")), payload.company_id, False, self.notes_endpoint, payload_dict)

    def _post_with_retries(self, request_json: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response: httpx.Response | None = None
            for attempt in range(self.max_retries + 1):
                response = client.post(self.notes_endpoint, json=request_json, headers=self._headers(), timeout=self.timeout)
                if response.status_code not in _RETRYABLE_STATUS_CODES or attempt >= self.max_retries:
                    break
            assert response is not None
            if not 200 <= response.status_code < 300:
                raise HubSpotCompanyNotePublishError(
                    f"HubSpot company note publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.token])}",
                    status_code=response.status_code,
                    token=self.token,
                )
            return response
        finally:
            if close_client:
                client.close()

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {"Accept": "application/json", "Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "User-Agent": "max-hubspot-company-notes-publisher/1"}


HubSpotCompanyNotesPublisher = HubSpotCompanyNotePublisher


def _note_body(fields: dict[str, str]) -> str:
    return "\n".join(
        [
            f"Status: {fields['status']}",
            f"Category: {fields['category']}",
            f"Idea ID: {fields['idea_id']}",
            f"Score: {fields['score']}",
            f"Problem: {fields['problem']}",
            f"Solution: {fields['solution']}",
        ]
    )

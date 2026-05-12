"""HubSpot contact note publisher for Max summaries."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._summary_payloads import summary_markdown, summary_metadata
from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, redact_text, required_text, required_url, response_json, response_preview

DEFAULT_HUBSPOT_API_URL = "https://api.hubapi.com"


class HubSpotContactNotePublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class HubSpotContactNotePublishResult:
    status_code: int | None
    note_id: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class HubSpotContactNotePublisher:
    def __init__(self, *, contact_id: str | None = None, access_token: str | None = None, api_url: str = DEFAULT_HUBSPOT_API_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.contact_id = optional_text(contact_id)
        self.access_token = optional_text(access_token)
        self.api_url = required_url(api_url, "HubSpot API URL must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> HubSpotContactNotePublisher:
        return cls(contact_id=kwargs.pop("contact_id", None) or os.getenv("HUBSPOT_CONTACT_ID"), access_token=kwargs.pop("access_token", None) or os.getenv("HUBSPOT_ACCESS_TOKEN"), api_url=kwargs.pop("api_url", None) or os.getenv("HUBSPOT_API_URL", DEFAULT_HUBSPOT_API_URL), **kwargs)

    @property
    def endpoint(self) -> str:
        return f"{self.api_url}/crm/v3/objects/notes"

    def build_note_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        contact_id = required_text(self.contact_id, "HUBSPOT_CONTACT_ID is required for HubSpot contact note publishing")
        return {
            "contact_id": contact_id,
            "properties": {"hs_note_body": summary_markdown(payload)},
            "associations": [{"to": {"id": contact_id}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}]}],
            "metadata": summary_metadata(payload, publisher="max.hubspot_contact_notes"),
        }

    def publish(self, payload: dict[str, Any], *, dry_run: bool = True) -> HubSpotContactNotePublishResult:
        request_payload = self.build_note_payload(payload)
        if dry_run:
            return HubSpotContactNotePublishResult(None, None, True, self.endpoint, request_payload)
        if not self.access_token:
            raise HubSpotContactNotePublishError("HUBSPOT_ACCESS_TOKEN is required for live HubSpot contact note publishing; use dry_run to preview")
        response = self._post(request_payload)
        body = response_json(response, HubSpotContactNotePublishError, "HubSpot contact note publish failed: response was not valid JSON")
        return HubSpotContactNotePublishResult(response.status_code, _text(body.get("id")), False, self.endpoint, request_payload, body)

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise HubSpotContactNotePublishError(f"HubSpot contact note publish failed for {self.endpoint}: {exc}", token=self.access_token) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise HubSpotContactNotePublishError(f"HubSpot contact note publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.access_token])}", status_code=response.status_code, token=self.access_token)
        return response

    def _headers(self) -> dict[str, str]:
        assert self.access_token is not None
        return {"Accept": "application/json", "Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json", "User-Agent": "max-hubspot-contact-notes-publisher/1"}


def _text(value: object) -> str | None:
    return str(value) if value else None

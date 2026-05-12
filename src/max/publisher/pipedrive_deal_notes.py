"""Pipedrive deal note publisher for generated TactSpec previews."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, html_summary, metadata, optional_text, required_text, required_url, response_json, response_preview, validate_tact_spec

DEFAULT_API_URL = "https://api.pipedrive.com"


class PipedriveDealNotePublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class PipedriveDealNotePayload:
    deal_id: str
    content: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"deal_id": self.deal_id, "content": self.content, "metadata": self.metadata}


@dataclass(frozen=True)
class PipedriveDealNotePublishResult:
    status_code: int | None
    note_id: str | None
    deal_id: str
    dry_run: bool
    payload: dict[str, Any]


class PipedriveDealNotePublisher:
    def __init__(self, *, deal_id: str | None = None, api_token: str | None = None, api_url: str = DEFAULT_API_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.deal_id = optional_text(deal_id)
        self.api_token = optional_text(api_token)
        self.api_url = required_url(api_url, "Pipedrive api_url must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, *, deal_id: str | None = None, api_token: str | None = None, api_url: str | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> PipedriveDealNotePublisher:
        return cls(deal_id=deal_id or os.getenv("PIPEDRIVE_DEAL_ID"), api_token=api_token or os.getenv("PIPEDRIVE_API_TOKEN"), api_url=api_url or os.getenv("PIPEDRIVE_API_URL", DEFAULT_API_URL), timeout=timeout, client=client)

    @property
    def notes_endpoint(self) -> str:
        return f"{self.api_url}/v1/notes"

    def build_note_payload(self, tact_spec: dict[str, Any], *, deal_id: str | None = None) -> PipedriveDealNotePayload:
        try:
            validate_tact_spec(tact_spec, label="Pipedrive deal note")
            resolved_deal_id = required_text(optional_text(deal_id) or self.deal_id, "PIPEDRIVE_DEAL_ID is required for Pipedrive deal note publishing")
        except ValueError as exc:
            raise PipedriveDealNotePublishError(str(exc)) from exc
        meta = metadata(tact_spec, publisher="max.pipedrive_deal_notes", extra={"deal_id": resolved_deal_id})
        return PipedriveDealNotePayload(resolved_deal_id, html_summary(tact_spec, meta), meta)

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True, deal_id: str | None = None) -> PipedriveDealNotePublishResult:
        payload = self.build_note_payload(tact_spec, deal_id=deal_id).to_dict()
        if dry_run:
            return PipedriveDealNotePublishResult(None, None, payload["deal_id"], True, payload)
        if not self.api_token:
            raise PipedriveDealNotePublishError("PIPEDRIVE_API_TOKEN is required for live Pipedrive deal note publishing; use dry_run to preview")
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.notes_endpoint, params={"api_token": self.api_token}, json={"deal_id": payload["deal_id"], "content": payload["content"]}, headers={"Accept": "application/json", "User-Agent": "max-pipedrive-deal-notes-publisher/1"}, timeout=self.timeout)
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise PipedriveDealNotePublishError(f"Pipedrive deal note publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.api_token])}", status_code=response.status_code)
        body = response_json(response, PipedriveDealNotePublishError, "Pipedrive deal note publish failed: response was not valid JSON")
        data = body.get("data") if isinstance(body.get("data"), dict) else body
        return PipedriveDealNotePublishResult(response.status_code, optional_text(data.get("id")), payload["deal_id"], False, payload)


PipedriveDealNotesPublisher = PipedriveDealNotePublisher

"""Zendesk ticket tag publisher."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, metadata, optional_text, required_text, required_url, response_json, response_preview, tag_value, validate_tact_spec


class ZendeskTicketTagPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ZendeskTicketTagPublishResult:
    status_code: int | None
    ticket_id: str
    dry_run: bool
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class ZendeskTicketTagPublisher:
    def __init__(self, *, ticket_id: str | None = None, subdomain: str | None = None, base_url: str | None = None, email: str | None = None, api_token: str | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.ticket_id = optional_text(ticket_id)
        self.base_url = required_url(base_url or f"https://{required_text(subdomain, 'ZENDESK_SUBDOMAIN or ZENDESK_BASE_URL is required')}.zendesk.com", "Zendesk base_url must be an absolute http(s) URL")
        self.email = optional_text(email)
        self.api_token = optional_text(api_token)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> ZendeskTicketTagPublisher:
        return cls(ticket_id=kwargs.get("ticket_id") or os.getenv("ZENDESK_TICKET_ID"), subdomain=kwargs.get("subdomain") or os.getenv("ZENDESK_SUBDOMAIN"), base_url=kwargs.get("base_url") or os.getenv("ZENDESK_BASE_URL"), email=kwargs.get("email") or os.getenv("ZENDESK_EMAIL"), api_token=kwargs.get("api_token") or os.getenv("ZENDESK_API_TOKEN"), timeout=kwargs.get("timeout", DEFAULT_TIMEOUT_SECONDS), client=kwargs.get("client"))

    def endpoint(self, ticket_id: str) -> str:
        return f"{self.base_url}/api/v2/tickets/{ticket_id}.json"

    def build_tags_payload(self, tact_spec: dict[str, Any], *, tags: list[str] | None = None, ticket_id: str | None = None) -> dict[str, Any]:
        try:
            validate_tact_spec(tact_spec, label="Zendesk ticket tags")
            resolved_ticket = required_text(optional_text(ticket_id) or self.ticket_id, "ZENDESK_TICKET_ID is required for Zendesk ticket tag publishing")
        except ValueError as exc:
            raise ZendeskTicketTagPublishError(str(exc)) from exc
        meta = metadata(tact_spec, publisher="max.zendesk_ticket_tags")
        derived = [tag_value(meta.get("source_type"), prefix="max"), tag_value(meta.get("source_id"), prefix="source")]
        normalized = sorted({tag for tag in [tag_value(v) for v in (tags or [])] + derived if tag})
        return {"endpoint": self.endpoint(resolved_ticket), "ticket_id": resolved_ticket, "payload": {"ticket": {"tags": normalized}}, "metadata": meta}

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True, tags: list[str] | None = None) -> ZendeskTicketTagPublishResult:
        built = self.build_tags_payload(tact_spec, tags=tags)
        if dry_run:
            return ZendeskTicketTagPublishResult(None, built["ticket_id"], True, built)
        if not (self.email and self.api_token):
            raise ZendeskTicketTagPublishError("ZENDESK_EMAIL and ZENDESK_API_TOKEN are required for live Zendesk ticket tag publishing; use dry_run to preview")
        client = self._client or httpx.Client(timeout=self.timeout)
        close_client = self._client is None
        try:
            response = client.put(built["endpoint"], json=built["payload"], auth=(f"{self.email}/token", self.api_token), timeout=self.timeout)
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise ZendeskTicketTagPublishError(f"Zendesk ticket tag publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.api_token])}", status_code=response.status_code)
        return ZendeskTicketTagPublishResult(response.status_code, built["ticket_id"], False, built, response_json(response, ZendeskTicketTagPublishError, "Zendesk ticket tag response was not valid JSON"))

"""HubSpot ticket publisher for Max summaries."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._summary_payloads import summary_markdown, summary_metadata, summary_title
from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, required_url, response_json, response_preview

DEFAULT_HUBSPOT_API_URL = "https://api.hubapi.com"


class HubSpotTicketPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(message.replace(token, "[REDACTED]") if token else message)
        self.status_code = status_code


@dataclass(frozen=True)
class HubSpotTicketPublishResult:
    status_code: int | None
    ticket_id: str | None
    archived: bool | None
    dry_run: bool
    endpoint: str
    headers: dict[str, str]
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class HubSpotTicketPublisher:
    def __init__(
        self,
        *,
        access_token: str | None = None,
        pipeline: str | None = None,
        pipeline_stage: str | None = None,
        owner_id: str | None = None,
        priority: str | None = None,
        category: str | None = None,
        subject: str | None = None,
        api_url: str = DEFAULT_HUBSPOT_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.access_token = optional_text(access_token)
        self.pipeline = optional_text(pipeline)
        self.pipeline_stage = optional_text(pipeline_stage)
        self.owner_id = optional_text(owner_id)
        self.priority = optional_text(priority)
        self.category = optional_text(category)
        self.subject = optional_text(subject)
        self.api_url = required_url(api_url, "HubSpot API URL must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> HubSpotTicketPublisher:
        return cls(
            access_token=kwargs.pop("access_token", None) or os.getenv("HUBSPOT_ACCESS_TOKEN"),
            pipeline=kwargs.pop("pipeline", None) or os.getenv("HUBSPOT_TICKET_PIPELINE"),
            pipeline_stage=kwargs.pop("pipeline_stage", None) or os.getenv("HUBSPOT_TICKET_PIPELINE_STAGE"),
            owner_id=kwargs.pop("owner_id", None) or os.getenv("HUBSPOT_OWNER_ID"),
            priority=kwargs.pop("priority", None) or os.getenv("HUBSPOT_TICKET_PRIORITY"),
            category=kwargs.pop("category", None) or os.getenv("HUBSPOT_TICKET_CATEGORY"),
            api_url=kwargs.pop("api_url", None) or os.getenv("HUBSPOT_API_URL", DEFAULT_HUBSPOT_API_URL),
            **kwargs,
        )

    @property
    def endpoint(self) -> str:
        return f"{self.api_url}/crm/v3/objects/tickets"

    def build_ticket_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        metadata = summary_metadata(payload, publisher="max.hubspot_tickets")
        properties: dict[str, str] = {
            "subject": self.subject or summary_title(payload),
            "content": summary_markdown(payload),
        }
        optional_properties = {
            "hs_pipeline": self.pipeline,
            "hs_pipeline_stage": self.pipeline_stage,
            "hubspot_owner_id": self.owner_id,
            "hs_ticket_priority": self.priority,
            "hs_ticket_category": self.category,
            "max_source_type": _text(metadata.get("source_type")),
            "max_source_id": _text(metadata.get("source_id")),
            "max_idea_id": _text(metadata.get("idea_id")),
            "max_design_brief_id": _text(metadata.get("design_brief_id")),
        }
        properties.update({key: value for key, value in optional_properties.items() if value})
        return {"properties": properties, "metadata": metadata}

    def publish(self, payload: dict[str, Any], *, dry_run: bool = True) -> HubSpotTicketPublishResult:
        request_payload = self.build_ticket_payload(payload)
        if dry_run:
            return HubSpotTicketPublishResult(None, None, None, True, self.endpoint, self._preview_headers(), request_payload)
        if not self.access_token:
            raise HubSpotTicketPublishError("HUBSPOT_ACCESS_TOKEN is required for live HubSpot ticket publishing; use dry_run to preview")
        response = self._post(request_payload)
        body = response_json(response, HubSpotTicketPublishError, "HubSpot ticket publish failed: response was not valid JSON")
        return HubSpotTicketPublishResult(response.status_code, _text(body.get("id")), body.get("archived") if isinstance(body.get("archived"), bool) else None, False, self.endpoint, self._headers(), request_payload, body)

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise HubSpotTicketPublishError(f"HubSpot ticket publish failed for {self.endpoint}: {exc}", token=self.access_token) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise HubSpotTicketPublishError(f"HubSpot ticket publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.access_token])}", status_code=response.status_code, token=self.access_token)
        return response

    def _headers(self) -> dict[str, str]:
        assert self.access_token is not None
        return {"Accept": "application/json", "Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json", "User-Agent": "max-hubspot-tickets-publisher/1"}

    def _preview_headers(self) -> dict[str, str]:
        return {"Accept": "application/json", "Authorization": "Bearer [REDACTED]", "Content-Type": "application/json", "User-Agent": "max-hubspot-tickets-publisher/1"}


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None

"""Statuspage incident publisher."""

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
    validate_tact_spec,
)

DEFAULT_API_URL = "https://api.statuspage.io"
DEFAULT_STATUS = "investigating"
DEFAULT_IMPACT = "minor"


class StatuspageIncidentPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, secrets: list[str | None] | None = None) -> None:
        super().__init__(redact_text(message, secrets=secrets))
        self.status_code = status_code


@dataclass(frozen=True)
class StatuspageIncidentPayload:
    page_id: str
    name: str
    status: str
    impact: str
    body: str
    component_ids: list[str]
    components: dict[str, str]
    scheduled_for: str | None
    scheduled_until: str | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "name": self.name,
            "status": self.status,
            "impact": self.impact,
            "body": self.body,
            "component_ids": self.component_ids,
            "components": self.components,
            "scheduled_for": self.scheduled_for,
            "scheduled_until": self.scheduled_until,
            "metadata": self.metadata,
        }

    def to_request(self) -> dict[str, Any]:
        incident: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "impact_override": self.impact,
            "body": self.body,
        }
        if self.component_ids:
            incident["component_ids"] = self.component_ids
        if self.components:
            incident["components"] = self.components
        if self.scheduled_for:
            incident["scheduled_for"] = self.scheduled_for
        if self.scheduled_until:
            incident["scheduled_until"] = self.scheduled_until
        return {"incident": incident}


@dataclass(frozen=True)
class StatuspageIncidentPublishResult:
    status_code: int | None
    page_id: str
    incident_id: str | None
    incident_url: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class StatuspageIncidentPublisher:
    def __init__(
        self,
        *,
        page_id: str | None = None,
        api_key: str | None = None,
        api_url: str = DEFAULT_API_URL,
        status: str = DEFAULT_STATUS,
        impact: str = DEFAULT_IMPACT,
        body: str | None = None,
        component_ids: list[str] | None = None,
        components: dict[str, str] | None = None,
        scheduled_for: str | None = None,
        scheduled_until: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self.page_id = optional_text(page_id)
        self.api_key = optional_text(api_key)
        self.api_url = required_url(api_url, "Statuspage api_url must be an absolute http(s) URL")
        self.status = optional_text(status) or DEFAULT_STATUS
        self.impact = optional_text(impact) or DEFAULT_IMPACT
        self.body = optional_text(body)
        self.component_ids = component_ids or []
        self.components = components or {}
        self.scheduled_for = optional_text(scheduled_for)
        self.scheduled_until = optional_text(scheduled_until)
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> StatuspageIncidentPublisher:
        return cls(
            page_id=kwargs.pop("page_id", None) or os.getenv("STATUSPAGE_PAGE_ID"),
            api_key=kwargs.pop("api_key", None) or os.getenv("STATUSPAGE_API_KEY"),
            api_url=kwargs.pop("api_url", None) or os.getenv("STATUSPAGE_API_URL", DEFAULT_API_URL),
            status=kwargs.pop("status", None) or os.getenv("STATUSPAGE_INCIDENT_STATUS") or DEFAULT_STATUS,
            impact=kwargs.pop("impact", None) or os.getenv("STATUSPAGE_INCIDENT_IMPACT") or DEFAULT_IMPACT,
            **kwargs,
        )

    def incidents_endpoint(self, *, page_id: str | None = None) -> str:
        return f"{self.api_url}/v1/pages/{quote_path(_required_page_id(optional_text(page_id) or self.page_id))}/incidents"

    def build_incident_payload(
        self,
        tact_spec: dict[str, Any],
        *,
        page_id: str | None = None,
        name: str | None = None,
        status: str | None = None,
        impact: str | None = None,
        body: str | None = None,
        component_ids: list[str] | None = None,
        components: dict[str, str] | None = None,
        scheduled_for: str | None = None,
        scheduled_until: str | None = None,
    ) -> StatuspageIncidentPayload:
        try:
            validate_tact_spec(tact_spec, label="Statuspage incident")
            resolved_page_id = _required_page_id(optional_text(page_id) or self.page_id)
        except ValueError as exc:
            raise StatuspageIncidentPublishError(str(exc), secrets=self._secrets()) from exc
        incident_metadata = metadata(tact_spec, publisher="max.statuspage_incidents", extra={"statuspage_page_id": resolved_page_id})
        project = tact_spec.get("project") if isinstance(tact_spec.get("project"), dict) else {}
        incident_name = required_text(optional_text(name) or optional_text(project.get("title")), "Statuspage incident name is required")
        return StatuspageIncidentPayload(
            page_id=resolved_page_id,
            name=incident_name,
            status=optional_text(status) or self.status,
            impact=optional_text(impact) or self.impact,
            body=optional_text(body) or self.body or markdown_summary(tact_spec, incident_metadata),
            component_ids=component_ids if component_ids is not None else self.component_ids,
            components=components if components is not None else self.components,
            scheduled_for=optional_text(scheduled_for) or self.scheduled_for,
            scheduled_until=optional_text(scheduled_until) or self.scheduled_until,
            metadata=incident_metadata,
        )

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True, **kwargs: Any) -> StatuspageIncidentPublishResult:
        payload = self.build_incident_payload(tact_spec, **kwargs)
        endpoint = self.incidents_endpoint(page_id=payload.page_id)
        payload_dict = payload.to_dict()
        if dry_run:
            return StatuspageIncidentPublishResult(None, payload.page_id, None, None, True, endpoint, payload_dict)
        if not self.api_key:
            raise StatuspageIncidentPublishError("STATUSPAGE_API_KEY is required for live Statuspage incident publishing; use dry_run to preview", secrets=self._secrets())
        response = self._post_with_retries(endpoint, payload.to_request())
        response_body = response_json(response, StatuspageIncidentPublishError, "Statuspage incident publish failed: response was not valid JSON")
        incident = response_body.get("incident") if isinstance(response_body.get("incident"), dict) else response_body
        incident_id = optional_text(incident.get("id")) if isinstance(incident, dict) else None
        incident_url = optional_text(incident.get("shortlink")) or optional_text(incident.get("postmortem_body_last_updated_at")) if isinstance(incident, dict) else None
        if isinstance(incident, dict):
            incident_url = optional_text(incident.get("shortlink")) or optional_text(incident.get("url")) or optional_text(incident.get("public_url"))
        return StatuspageIncidentPublishResult(response.status_code, payload.page_id, incident_id, incident_url, False, endpoint, payload_dict, response_body)

    def _post_with_retries(self, endpoint: str, request_json: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response: httpx.Response | None = None
            for attempt in range(self.max_retries + 1):
                try:
                    response = client.post(endpoint, json=request_json, headers=self._headers(), timeout=self.timeout)
                except (httpx.RequestError, httpx.TimeoutException) as exc:
                    if attempt >= self.max_retries:
                        raise StatuspageIncidentPublishError(f"Statuspage incident publish failed for {endpoint}: {exc}", secrets=self._secrets()) from exc
                    continue
                if response.status_code not in {429, 500, 502, 503, 504} or attempt >= self.max_retries:
                    break
            assert response is not None
            if not 200 <= response.status_code < 300:
                raise StatuspageIncidentPublishError(
                    f"Statuspage incident publish failed with HTTP {response.status_code}: {response_preview(response, secrets=self._secrets())}",
                    status_code=response.status_code,
                    secrets=self._secrets(),
                )
            return response
        finally:
            if close_client:
                client.close()

    def _headers(self) -> dict[str, str]:
        assert self.api_key is not None
        return {"Accept": "application/json", "Authorization": f"OAuth {self.api_key}", "Content-Type": "application/json", "User-Agent": "max-statuspage-incidents-publisher/1"}

    def _secrets(self) -> list[str | None]:
        return [self.api_key]


StatuspageIncidentsPublisher = StatuspageIncidentPublisher


def _required_page_id(value: str | None) -> str:
    return required_text(value, "Statuspage page_id is required; pass page_id or set STATUSPAGE_PAGE_ID")

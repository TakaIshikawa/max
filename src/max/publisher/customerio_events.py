"""Customer.io event publisher for Max buildable units."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, redact_text, required_text, required_url, response_json, response_preview
from max.publisher.stripe_customer_notes import _RETRYABLE_STATUS_CODES, _unit_fields

DEFAULT_API_URL = "https://track.customer.io"


class CustomerIOEventPublishError(RuntimeError):
    """Raised when a Customer.io event publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None, site_id: str | None = None, api_key: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[site_id, api_key, _basic_token(site_id, api_key)]))
        self.status_code = status_code


@dataclass(frozen=True)
class CustomerIOEventPayload:
    customer_id: str
    event_name: str
    timestamp: int
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "name": self.event_name,
            "timestamp": self.timestamp,
            "data": self.data,
        }

    def to_request_json(self) -> dict[str, Any]:
        return {"name": self.event_name, "timestamp": self.timestamp, "data": self.data}


@dataclass(frozen=True)
class CustomerIOEventPublishResult:
    status_code: int | None
    customer_id: str
    event_name: str
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    event_id: str | None = None


class CustomerIOEventPublisher:
    """Build and optionally send Max idea lifecycle events to Customer.io."""

    def __init__(
        self,
        *,
        site_id: str | None = None,
        api_key: str | None = None,
        customer_id: str | None = None,
        event_name: str | None = None,
        api_url: str = DEFAULT_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self.site_id = optional_text(site_id)
        self.api_key = optional_text(api_key)
        self.customer_id = optional_text(customer_id)
        self.event_name = optional_text(event_name) or "max.idea.lifecycle"
        self.api_url = required_url(api_url, "Customer.io api_url must be an absolute http(s) URL")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> CustomerIOEventPublisher:
        return cls(
            site_id=kwargs.pop("site_id", None) or os.getenv("CUSTOMERIO_SITE_ID"),
            api_key=kwargs.pop("api_key", None) or os.getenv("CUSTOMERIO_API_KEY"),
            customer_id=kwargs.pop("customer_id", None) or os.getenv("CUSTOMERIO_CUSTOMER_ID"),
            event_name=kwargs.pop("event_name", None) or os.getenv("CUSTOMERIO_EVENT_NAME"),
            api_url=kwargs.pop("api_url", None) or os.getenv("CUSTOMERIO_API_URL", DEFAULT_API_URL),
            **kwargs,
        )

    def events_endpoint(self, customer_id: str | None = None) -> str:
        resolved = required_text(optional_text(customer_id) or self.customer_id, "Customer.io customer_id is required; pass customer_id or set CUSTOMERIO_CUSTOMER_ID")
        return f"{self.api_url}/api/v1/customers/{quote(resolved, safe='')}/events"

    def build_event_payload(
        self,
        unit: dict[str, Any],
        *,
        customer_id: str | None = None,
        event_name: str | None = None,
        timestamp: int | None = None,
    ) -> CustomerIOEventPayload:
        try:
            resolved_customer_id = required_text(optional_text(customer_id) or self.customer_id, "Customer.io customer_id is required; pass customer_id or set CUSTOMERIO_CUSTOMER_ID")
            resolved_event_name = required_text(optional_text(event_name) or self.event_name, "Customer.io event_name is required")
        except ValueError as exc:
            raise CustomerIOEventPublishError(str(exc), site_id=self.site_id, api_key=self.api_key) from exc
        fields = _unit_fields(unit)
        data = {
            "max_category": fields["category"],
            "max_idea_id": fields["idea_id"],
            "max_problem": fields["problem"],
            "max_score": fields["score"],
            "max_solution": fields["solution"],
            "max_status": fields["status"],
            "max_title": fields["title"],
            "publisher": "max.customerio_events",
        }
        return CustomerIOEventPayload(resolved_customer_id, resolved_event_name, _event_timestamp(unit, timestamp), data)

    def publish(
        self,
        unit: dict[str, Any],
        *,
        dry_run: bool = True,
        customer_id: str | None = None,
        event_name: str | None = None,
        timestamp: int | None = None,
    ) -> CustomerIOEventPublishResult:
        payload = self.build_event_payload(unit, customer_id=customer_id, event_name=event_name, timestamp=timestamp)
        endpoint = self.events_endpoint(payload.customer_id)
        payload_dict = payload.to_dict()
        if dry_run:
            return CustomerIOEventPublishResult(
                None,
                payload.customer_id,
                payload.event_name,
                True,
                endpoint,
                payload_dict,
                {"method": "POST", "headers": self._redacted_headers()},
            )
        if not self.site_id or not self.api_key:
            raise CustomerIOEventPublishError("CUSTOMERIO_SITE_ID and CUSTOMERIO_API_KEY are required for live Customer.io event publishing; use dry_run to preview", site_id=self.site_id, api_key=self.api_key)
        response = self._post_with_retries(endpoint, payload.to_request_json())
        body = response_json(response, CustomerIOEventPublishError, "Customer.io event publish failed: response was not valid JSON")
        event_id = optional_text(body.get("event_id")) or optional_text(body.get("id"))
        return CustomerIOEventPublishResult(response.status_code, payload.customer_id, payload.event_name, False, endpoint, payload_dict, response=body, event_id=event_id)

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
                        raise CustomerIOEventPublishError(f"Customer.io event publish failed for {endpoint}: {exc}", site_id=self.site_id, api_key=self.api_key) from exc
                    continue
                if response.status_code not in _RETRYABLE_STATUS_CODES or attempt >= self.max_retries:
                    break
            assert response is not None
            if not 200 <= response.status_code < 300:
                raise CustomerIOEventPublishError(
                    f"Customer.io event publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.site_id, self.api_key])}",
                    status_code=response.status_code,
                    site_id=self.site_id,
                    api_key=self.api_key,
                )
            return response
        finally:
            if close_client:
                client.close()

    def _headers(self) -> dict[str, str]:
        if not self.site_id or not self.api_key:
            raise CustomerIOEventPublishError("CUSTOMERIO_SITE_ID and CUSTOMERIO_API_KEY are required for Customer.io authorization", site_id=self.site_id, api_key=self.api_key)
        return {
            "Accept": "application/json",
            "Authorization": f"Basic {_basic_token(self.site_id, self.api_key)}",
            "Content-Type": "application/json",
            "User-Agent": "max-customerio-events-publisher/1",
        }

    def _redacted_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "max-customerio-events-publisher/1"}
        if self.site_id and self.api_key:
            headers["Authorization"] = "Basic [REDACTED]"
        return headers


CustomerIOEventsPublisher = CustomerIOEventPublisher
CustomerIoEventPublisher = CustomerIOEventPublisher


def _basic_token(site_id: str | None, api_key: str | None) -> str | None:
    if not site_id or not api_key:
        return None
    return base64.b64encode(f"{site_id}:{api_key}".encode("utf-8")).decode("ascii")


def _event_timestamp(unit: dict[str, Any], explicit: int | None) -> int:
    if explicit is not None:
        return int(explicit)
    source = unit.get("source") if isinstance(unit.get("source"), dict) else {}
    for value in (unit.get("timestamp"), unit.get("created_at"), source.get("timestamp"), source.get("created_at")):
        parsed = _parse_timestamp(value)
        if parsed is not None:
            return parsed
    return 0


def _parse_timestamp(value: object) -> int | None:
    if isinstance(value, int | float):
        return int(value)
    text = optional_text(value)
    if not text:
        return None
    if text.isdigit():
        return int(text)
    try:
        normalized = text.replace("Z", "+00:00")
        return int(datetime.fromisoformat(normalized).astimezone(timezone.utc).timestamp())
    except ValueError:
        return None

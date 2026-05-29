"""PagerDuty Events API v2 change event publisher."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, markdown_summary, metadata, optional_text, required_text, required_url, response_json, response_preview, title, validate_tact_spec

DEFAULT_EVENTS_API_URL = "https://events.pagerduty.com/v2/change/enqueue"


class PagerDutyChangeEventPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class PagerDutyChangeEventPublishResult:
    status_code: int | None
    dedup_key: str | None
    dry_run: bool
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class PagerDutyChangeEventPublisher:
    def __init__(self, *, routing_key: str | None = None, api_url: str = DEFAULT_EVENTS_API_URL, source: str = "max", timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.routing_key = optional_text(routing_key)
        self.api_url = required_url(api_url, "PagerDuty api_url must be an absolute http(s) URL")
        self.source = required_text(source, "PagerDuty source is required")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> PagerDutyChangeEventPublisher:
        return cls(routing_key=kwargs.get("routing_key") or os.getenv("PAGERDUTY_ROUTING_KEY"), api_url=kwargs.get("api_url") or os.getenv("PAGERDUTY_EVENTS_API_URL", DEFAULT_EVENTS_API_URL), source=kwargs.get("source") or os.getenv("PAGERDUTY_CHANGE_SOURCE", "max"), timeout=kwargs.get("timeout", DEFAULT_TIMEOUT_SECONDS), client=kwargs.get("client"))

    def build_change_event_payload(self, tact_spec: dict[str, Any], *, links: list[dict[str, str]] | None = None, custom_details: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            validate_tact_spec(tact_spec, label="PagerDuty change event")
        except ValueError as exc:
            raise PagerDutyChangeEventPublishError(str(exc)) from exc
        meta = metadata(tact_spec, publisher="max.pagerduty_change_events")
        event = {"routing_key": self.routing_key, "payload": {"summary": title(tact_spec), "source": self.source, "timestamp": None, "custom_details": {"summary": markdown_summary(tact_spec, meta), **(custom_details or {})}}, "links": links or []}
        return {"endpoint": self.api_url, "change_event": event, "metadata": meta}

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True, links: list[dict[str, str]] | None = None, custom_details: dict[str, Any] | None = None) -> PagerDutyChangeEventPublishResult:
        payload = self.build_change_event_payload(tact_spec, links=links, custom_details=custom_details)
        if dry_run:
            return PagerDutyChangeEventPublishResult(None, None, True, payload)
        if not self.routing_key:
            raise PagerDutyChangeEventPublishError("PAGERDUTY_ROUTING_KEY is required for live PagerDuty change event publishing; use dry_run to preview")
        event = {**payload["change_event"], "routing_key": self.routing_key}
        client = self._client or httpx.Client(timeout=self.timeout)
        close_client = self._client is None
        try:
            response = client.post(self.api_url, json=event, timeout=self.timeout)
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise PagerDutyChangeEventPublishError(f"PagerDuty change event publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.routing_key])}", status_code=response.status_code)
        body = response_json(response, PagerDutyChangeEventPublishError, "PagerDuty change event response was not valid JSON")
        return PagerDutyChangeEventPublishResult(response.status_code, optional_text(body.get("dedup_key")), False, payload, body)

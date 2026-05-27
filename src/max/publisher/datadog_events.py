"""Datadog event publisher for generated TactSpec previews."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, markdown_summary, metadata, optional_text, required_text, required_url, response_json, response_preview, tag_value, title, validate_tact_spec

ALERT_TYPES = {"error", "warning", "info", "success"}


class DatadogEventPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class DatadogEventPublishResult:
    status_code: int | None
    event_id: str | None
    dry_run: bool
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class DatadogEventPublisher:
    def __init__(self, *, api_key: str | None = None, site: str = "datadoghq.com", api_url: str | None = None, alert_type: str = "info", timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        if alert_type not in ALERT_TYPES:
            raise DatadogEventPublishError("Datadog alert_type must be one of error, warning, info, success")
        self.api_key = optional_text(api_key)
        self.site = required_text(site, "DATADOG_SITE is required")
        self.api_url = required_url(api_url or f"https://api.{self.site}/api/v1", "Datadog api_url must be an absolute http(s) URL")
        self.alert_type = alert_type
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> DatadogEventPublisher:
        return cls(api_key=kwargs.get("api_key") or os.getenv("DATADOG_API_KEY"), site=kwargs.get("site") or os.getenv("DATADOG_SITE", "datadoghq.com"), api_url=kwargs.get("api_url") or os.getenv("DATADOG_API_URL"), alert_type=kwargs.get("alert_type") or os.getenv("DATADOG_ALERT_TYPE", "info"), timeout=kwargs.get("timeout", DEFAULT_TIMEOUT_SECONDS), client=kwargs.get("client"))

    @property
    def endpoint(self) -> str:
        return f"{self.api_url}/events"

    def build_event_payload(self, tact_spec: dict[str, Any], *, tags: list[str] | None = None) -> dict[str, Any]:
        try:
            validate_tact_spec(tact_spec, label="Datadog event")
        except ValueError as exc:
            raise DatadogEventPublishError(str(exc)) from exc
        meta = metadata(tact_spec, publisher="max.datadog_events")
        normalized_tags = sorted({tag for tag in [tag_value(v) for v in (tags or [])] if tag})
        payload = {"title": title(tact_spec), "text": markdown_summary(tact_spec, meta), "alert_type": self.alert_type, "tags": normalized_tags, "aggregation_key": meta.get("source_id") or "max-tactspec", "source_type_name": "max"}
        return {"endpoint": self.endpoint, "event": payload, "metadata": meta}

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True, tags: list[str] | None = None) -> DatadogEventPublishResult:
        payload = self.build_event_payload(tact_spec, tags=tags)
        if dry_run:
            return DatadogEventPublishResult(None, None, True, payload)
        if not self.api_key:
            raise DatadogEventPublishError("DATADOG_API_KEY is required for live Datadog event publishing; use dry_run to preview")
        client = self._client or httpx.Client(timeout=self.timeout)
        close_client = self._client is None
        try:
            response = client.post(self.endpoint, json=payload["event"], headers={"DD-API-KEY": self.api_key}, timeout=self.timeout)
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise DatadogEventPublishError(f"Datadog event publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.api_key])}", status_code=response.status_code)
        body = response_json(response, DatadogEventPublishError, "Datadog event response was not valid JSON")
        return DatadogEventPublishResult(response.status_code, optional_text(body.get("id") or body.get("event_id")), False, payload, body)

"""ServiceNow change request publisher."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, markdown_summary, metadata, optional_text, required_text, required_url, response_json, response_preview, title, validate_tact_spec


class ServiceNowChangeRequestPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ServiceNowChangeRequestPublishResult:
    status_code: int | None
    sys_id: str | None
    number: str | None
    dry_run: bool
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class ServiceNowChangeRequestPublisher:
    def __init__(self, *, instance_url: str | None = None, username: str | None = None, password: str | None = None, category: str = "software", risk: str = "moderate", impact: str = "medium", assignment_group: str | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.instance_url = required_url(instance_url or "https://servicenow.example.invalid", "ServiceNow instance_url must be an absolute http(s) URL")
        self.username = optional_text(username)
        self.password = optional_text(password)
        self.category = category
        self.risk = risk
        self.impact = impact
        self.assignment_group = optional_text(assignment_group)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> ServiceNowChangeRequestPublisher:
        return cls(instance_url=kwargs.get("instance_url") or os.getenv("SERVICENOW_INSTANCE_URL"), username=kwargs.get("username") or os.getenv("SERVICENOW_USERNAME"), password=kwargs.get("password") or os.getenv("SERVICENOW_PASSWORD"), category=kwargs.get("category") or os.getenv("SERVICENOW_CHANGE_CATEGORY", "software"), risk=kwargs.get("risk") or os.getenv("SERVICENOW_CHANGE_RISK", "moderate"), impact=kwargs.get("impact") or os.getenv("SERVICENOW_CHANGE_IMPACT", "medium"), assignment_group=kwargs.get("assignment_group") or os.getenv("SERVICENOW_ASSIGNMENT_GROUP"), timeout=kwargs.get("timeout", DEFAULT_TIMEOUT_SECONDS), client=kwargs.get("client"))

    @property
    def endpoint(self) -> str:
        return f"{self.instance_url}/api/now/table/change_request"

    def build_change_request_payload(self, tact_spec: dict[str, Any]) -> dict[str, Any]:
        try:
            validate_tact_spec(tact_spec, label="ServiceNow change request")
        except ValueError as exc:
            raise ServiceNowChangeRequestPublishError(str(exc)) from exc
        meta = metadata(tact_spec, publisher="max.servicenow_change_requests")
        record = {"short_description": title(tact_spec), "description": markdown_summary(tact_spec, meta), "category": self.category, "risk": self.risk, "impact": self.impact}
        if self.assignment_group:
            record["assignment_group"] = self.assignment_group
        return {"endpoint": self.endpoint, "change_request": record, "metadata": meta}

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True) -> ServiceNowChangeRequestPublishResult:
        payload = self.build_change_request_payload(tact_spec)
        if dry_run:
            return ServiceNowChangeRequestPublishResult(None, None, None, True, payload)
        if not (self.username and self.password):
            raise ServiceNowChangeRequestPublishError("SERVICENOW_USERNAME and SERVICENOW_PASSWORD are required for live ServiceNow change request publishing; use dry_run to preview")
        client = self._client or httpx.Client(timeout=self.timeout)
        close_client = self._client is None
        try:
            response = client.post(self.endpoint, json=payload["change_request"], auth=(self.username, self.password), timeout=self.timeout)
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise ServiceNowChangeRequestPublishError(f"ServiceNow change request publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.password])}", status_code=response.status_code)
        body = response_json(response, ServiceNowChangeRequestPublishError, "ServiceNow change request response was not valid JSON")
        result = body.get("result") if isinstance(body.get("result"), dict) else body
        return ServiceNowChangeRequestPublishResult(response.status_code, optional_text(result.get("sys_id")), optional_text(result.get("number")), False, payload, body)

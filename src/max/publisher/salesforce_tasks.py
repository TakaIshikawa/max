"""Salesforce Task publisher for Max summaries."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._summary_payloads import summary_markdown, summary_metadata, summary_title
from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, redact_text, required_url, response_json, response_preview

DEFAULT_API_VERSION = "v60.0"
DEFAULT_TASK_STATUS = "Not Started"
DEFAULT_TASK_PRIORITY = "Normal"


class SalesforceTaskPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class SalesforceTaskPublishResult:
    status_code: int | None
    task_id: str | None
    task_url: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class SalesforceTaskPublisher:
    def __init__(self, *, instance_url: str | None = None, access_token: str | None = None, api_version: str = DEFAULT_API_VERSION, status: str = DEFAULT_TASK_STATUS, priority: str = DEFAULT_TASK_PRIORITY, owner_id: str | None = None, what_id: str | None = None, who_id: str | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.instance_url = required_url(instance_url, "Salesforce instance URL must be an absolute http(s) URL") if optional_text(instance_url) else None
        self.access_token = optional_text(access_token)
        self.api_version = optional_text(api_version) or DEFAULT_API_VERSION
        self.status = optional_text(status) or DEFAULT_TASK_STATUS
        self.priority = optional_text(priority) or DEFAULT_TASK_PRIORITY
        self.owner_id = optional_text(owner_id)
        self.what_id = optional_text(what_id)
        self.who_id = optional_text(who_id)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> SalesforceTaskPublisher:
        return cls(
            instance_url=kwargs.pop("instance_url", None) or os.getenv("SALESFORCE_INSTANCE_URL"),
            access_token=kwargs.pop("access_token", None) or os.getenv("SALESFORCE_ACCESS_TOKEN"),
            api_version=kwargs.pop("api_version", None) or os.getenv("SALESFORCE_API_VERSION", DEFAULT_API_VERSION),
            status=kwargs.pop("status", None) or os.getenv("SALESFORCE_TASK_STATUS", DEFAULT_TASK_STATUS),
            priority=kwargs.pop("priority", None) or os.getenv("SALESFORCE_TASK_PRIORITY", DEFAULT_TASK_PRIORITY),
            owner_id=kwargs.pop("owner_id", None) or os.getenv("SALESFORCE_TASK_OWNER_ID"),
            what_id=kwargs.pop("what_id", None) or os.getenv("SALESFORCE_TASK_WHAT_ID"),
            who_id=kwargs.pop("who_id", None) or os.getenv("SALESFORCE_TASK_WHO_ID"),
            **kwargs,
        )

    @property
    def endpoint(self) -> str:
        prefix = self.instance_url or ""
        return f"{prefix}/services/data/{self.api_version}/sobjects/Task"

    def build_task_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        request: dict[str, Any] = {"Subject": f"Max follow-up: {summary_title(payload)}"[:255], "Description": summary_markdown(payload), "Status": self.status, "Priority": self.priority, "metadata": summary_metadata(payload, publisher="max.salesforce_tasks")}
        for key, value in {"OwnerId": self.owner_id, "WhatId": self.what_id, "WhoId": self.who_id}.items():
            if value:
                request[key] = value
        return request

    def publish(self, payload: dict[str, Any], *, dry_run: bool = True) -> SalesforceTaskPublishResult:
        request_payload = self.build_task_payload(payload)
        if dry_run:
            return SalesforceTaskPublishResult(None, None, None, True, self.endpoint, request_payload)
        if not self.instance_url or not self.access_token:
            raise SalesforceTaskPublishError("SALESFORCE_INSTANCE_URL and SALESFORCE_ACCESS_TOKEN are required for live Salesforce Task publishing; use dry_run to preview")
        response = self._post(request_payload)
        body = response_json(response, SalesforceTaskPublishError, "Salesforce Task publish failed: response was not valid JSON")
        task_id = _text(body.get("id"))
        return SalesforceTaskPublishResult(response.status_code, task_id, f"{self.instance_url}/{task_id}" if task_id else None, False, self.endpoint, request_payload, body)

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.endpoint, json={k: v for k, v in payload.items() if k != "metadata"}, headers=self._headers(), timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise SalesforceTaskPublishError(f"Salesforce Task publish failed for {self.endpoint}: {exc}", token=self.access_token) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise SalesforceTaskPublishError(f"Salesforce Task publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.access_token])}", status_code=response.status_code, token=self.access_token)
        return response

    def _headers(self) -> dict[str, str]:
        assert self.access_token is not None
        return {"Accept": "application/json", "Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json", "User-Agent": "max-salesforce-tasks-publisher/1"}


def _text(value: object) -> str | None:
    return str(value) if value else None

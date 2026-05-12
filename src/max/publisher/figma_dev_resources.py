"""Figma dev resource publisher for Max summaries."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._summary_payloads import summary_metadata, summary_title
from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, quote_path, redact_text, required_text, required_url, response_json, response_preview

DEFAULT_FIGMA_API_URL = "https://api.figma.com"


class FigmaDevResourcePublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class FigmaDevResourcePublishResult:
    status_code: int | None
    resource_id: str | None
    resource_url: str | None
    dry_run: bool
    endpoint: str
    headers: dict[str, str]
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class FigmaDevResourcePublisher:
    def __init__(self, *, access_token: str | None = None, file_key: str | None = None, node_id: str | None = None, resource_name: str | None = None, resource_url: str | None = None, api_url: str = DEFAULT_FIGMA_API_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.access_token = optional_text(access_token)
        self.file_key = optional_text(file_key)
        self.node_id = optional_text(node_id)
        self.resource_name = optional_text(resource_name)
        self.resource_url = optional_text(resource_url)
        self.api_url = required_url(api_url, "Figma API URL must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> FigmaDevResourcePublisher:
        return cls(
            access_token=kwargs.pop("access_token", None) or os.getenv("FIGMA_ACCESS_TOKEN"),
            file_key=kwargs.pop("file_key", None) or os.getenv("FIGMA_FILE_KEY"),
            node_id=kwargs.pop("node_id", None) or os.getenv("FIGMA_NODE_ID"),
            resource_name=kwargs.pop("resource_name", None) or os.getenv("FIGMA_DEV_RESOURCE_NAME"),
            resource_url=kwargs.pop("resource_url", None) or os.getenv("FIGMA_DEV_RESOURCE_URL"),
            api_url=kwargs.pop("api_url", None) or os.getenv("FIGMA_API_URL", DEFAULT_FIGMA_API_URL),
            **kwargs,
        )

    @property
    def endpoint(self) -> str:
        file_key = required_text(self.file_key, "FIGMA_FILE_KEY is required for Figma dev resource publishing")
        return f"{self.api_url}/v1/files/{quote_path(file_key)}/dev_resources"

    def build_resource_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        resource_url = required_url(self.resource_url, "FIGMA_DEV_RESOURCE_URL is required for Figma dev resource publishing and must be an absolute http(s) URL")
        resource: dict[str, Any] = {
            "name": self.resource_name or f"Max summary: {summary_title(payload)}",
            "url": resource_url,
            "metadata": summary_metadata(payload, publisher="max.figma_dev_resources"),
        }
        if self.node_id:
            resource["node_id"] = self.node_id
        return {"dev_resources": [resource]}

    def publish(self, payload: dict[str, Any], *, dry_run: bool = True) -> FigmaDevResourcePublishResult:
        request_payload = self.build_resource_payload(payload)
        endpoint = self.endpoint
        if dry_run:
            return FigmaDevResourcePublishResult(None, None, self.resource_url, True, endpoint, self._headers(redacted=True), request_payload)
        if not self.access_token:
            raise FigmaDevResourcePublishError("FIGMA_ACCESS_TOKEN is required for live Figma dev resource publishing; use dry_run to preview")
        response = self._post(endpoint, request_payload)
        body = response_json(response, FigmaDevResourcePublishError, "Figma dev resource publish failed: response was not valid JSON")
        return FigmaDevResourcePublishResult(response.status_code, _resource_id(body), _resource_url(body) or self.resource_url, False, endpoint, self._headers(redacted=True), request_payload, body)

    def _post(self, endpoint: str, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise FigmaDevResourcePublishError(f"Figma dev resource publish failed for {endpoint}: {exc}", token=self.access_token) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise FigmaDevResourcePublishError(f"Figma dev resource publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.access_token])}", status_code=response.status_code, token=self.access_token)
        return response

    def _headers(self, *, redacted: bool = False) -> dict[str, str]:
        token = "[REDACTED]" if redacted and self.access_token else self.access_token
        headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "max-figma-dev-resources-publisher/1"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers


FigmaDevResourcesPublisher = FigmaDevResourcePublisher


def publish_figma_dev_resource(payload: dict[str, Any], **kwargs: Any) -> FigmaDevResourcePublishResult:
    return FigmaDevResourcePublisher.from_env(**{key: value for key, value in kwargs.items() if key != "dry_run"}).publish(payload, dry_run=kwargs.get("dry_run", True))


def _first_resource(body: dict[str, Any]) -> dict[str, Any]:
    resources = body.get("dev_resources")
    if isinstance(resources, list) and resources and isinstance(resources[0], dict):
        return resources[0]
    resource = body.get("dev_resource")
    if isinstance(resource, dict):
        return resource
    return body


def _resource_id(body: dict[str, Any]) -> str | None:
    value = _first_resource(body).get("id")
    return str(value) if value else None


def _resource_url(body: dict[str, Any]) -> str | None:
    value = _first_resource(body).get("url")
    return str(value) if value else None

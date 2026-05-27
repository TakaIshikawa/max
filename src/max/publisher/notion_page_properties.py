"""Notion page property updater for generated TactSpec readiness."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, dict_value, optional_text, redact_text, required_text, required_url, response_json, response_preview, title, validate_tact_spec

DEFAULT_NOTION_API_URL = "https://api.notion.com/v1"
DEFAULT_NOTION_VERSION = "2022-06-28"
DEFAULT_PROPERTY_NAMES = {
    "title": "Name",
    "status": "Status",
    "idea_id": "Idea ID",
    "generated_url": "Generated URL",
}


class NotionPagePropertiesPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class NotionPagePropertiesPayload:
    page_id: str
    properties: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"page_id": self.page_id, "properties": self.properties, "metadata": self.metadata}


@dataclass(frozen=True)
class NotionPagePropertiesPublishResult:
    status_code: int | None
    page_id: str | None
    page_url: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class NotionPagePropertiesPublisher:
    def __init__(
        self,
        *,
        token: str | None = None,
        page_id: str | None = None,
        property_names: dict[str, str] | None = None,
        api_url: str = DEFAULT_NOTION_API_URL,
        notion_version: str = DEFAULT_NOTION_VERSION,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.token = optional_text(token)
        self.page_id = optional_text(page_id)
        self.property_names = _property_names(property_names)
        self.api_url = required_url(api_url, "Notion API URL must be an absolute http(s) URL")
        self.notion_version = optional_text(notion_version) or DEFAULT_NOTION_VERSION
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> NotionPagePropertiesPublisher:
        return cls(
            token=kwargs.pop("token", None) or os.getenv("NOTION_TOKEN"),
            page_id=kwargs.pop("page_id", None) or os.getenv("NOTION_PAGE_ID"),
            api_url=kwargs.pop("api_url", None) or os.getenv("NOTION_API_URL", DEFAULT_NOTION_API_URL),
            notion_version=kwargs.pop("notion_version", None) or os.getenv("NOTION_VERSION", DEFAULT_NOTION_VERSION),
            **kwargs,
        )

    @property
    def endpoint(self) -> str:
        page_id = required_text(self.page_id, "NOTION_PAGE_ID is required for Notion page properties publishing")
        return f"{self.api_url}/pages/{quote(page_id, safe='')}"

    def build_properties_payload(self, tact_spec: dict[str, Any], *, generated_url: str | None = None) -> NotionPagePropertiesPayload:
        try:
            validate_tact_spec(tact_spec, label="Notion page properties")
            page_id = required_text(self.page_id, "NOTION_PAGE_ID is required for Notion page properties publishing")
        except ValueError as exc:
            raise NotionPagePropertiesPublishError(str(exc)) from exc

        source = dict_value(tact_spec, "source")
        evaluation = dict_value(tact_spec, "evaluation")
        status = optional_text(evaluation.get("recommendation")) or optional_text(source.get("status")) or "ready"
        idea_id = optional_text(source.get("idea_id")) or optional_text(source.get("design_brief_id"))
        url = optional_text(generated_url)

        properties: dict[str, Any] = {
            self.property_names["title"]: {"title": [_rich_text(title(tact_spec))]},
            self.property_names["status"]: {"select": {"name": status}},
        }
        if idea_id:
            properties[self.property_names["idea_id"]] = {"rich_text": [_rich_text(idea_id)]}
        if url:
            properties[self.property_names["generated_url"]] = {"url": url}

        metadata = {
            "publisher": "max.notion_page_properties",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type") or "idea",
            "idea_id": source.get("idea_id"),
            "design_brief_id": source.get("design_brief_id"),
            "schema_version": tact_spec.get("schema_version"),
            "page_id": page_id,
        }
        return NotionPagePropertiesPayload(page_id, properties, metadata)

    def publish(self, tact_spec: dict[str, Any], *, generated_url: str | None = None, dry_run: bool = True) -> NotionPagePropertiesPublishResult:
        payload = self.build_properties_payload(tact_spec, generated_url=generated_url).to_dict()
        endpoint = self.endpoint
        request_payload = {"properties": payload["properties"]}
        if dry_run:
            return NotionPagePropertiesPublishResult(None, None, None, True, endpoint, payload)
        if not self.token:
            raise NotionPagePropertiesPublishError("NOTION_TOKEN is required for live Notion page properties publishing; use dry_run to preview")
        response = self._patch(endpoint, request_payload)
        body = response_json(response, NotionPagePropertiesPublishError, "Notion page properties publish failed: response was not valid JSON")
        return NotionPagePropertiesPublishResult(response.status_code, optional_text(body.get("id")), optional_text(body.get("url")), False, endpoint, payload, body)

    def _patch(self, endpoint: str, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.patch(endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise NotionPagePropertiesPublishError(f"Notion page properties publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.token])}", status_code=response.status_code, token=self.token)
        return response

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {"Accept": "application/json", "Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "Notion-Version": self.notion_version, "User-Agent": "max-notion-page-properties-publisher/1"}


def _property_names(overrides: dict[str, str] | None) -> dict[str, str]:
    names = dict(DEFAULT_PROPERTY_NAMES)
    for key, value in (overrides or {}).items():
        if key in names and optional_text(value):
            names[key] = str(value).strip()
    return names


def _rich_text(content: str) -> dict[str, Any]:
    return {"type": "text", "text": {"content": content[:2000]}}

"""Notion page comment publisher for Max summaries."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._summary_payloads import summary_markdown
from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, redact_text, required_text, required_url, response_json, response_preview

DEFAULT_NOTION_API_URL = "https://api.notion.com/v1"
DEFAULT_NOTION_VERSION = "2022-06-28"


class NotionPageCommentPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class NotionPageCommentPublishResult:
    status_code: int | None
    comment_id: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class NotionPageCommentPublisher:
    def __init__(self, *, token: str | None = None, page_id: str | None = None, api_url: str = DEFAULT_NOTION_API_URL, notion_version: str = DEFAULT_NOTION_VERSION, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.token = optional_text(token)
        self.page_id = optional_text(page_id)
        self.api_url = required_url(api_url, "Notion API URL must be an absolute http(s) URL")
        self.notion_version = optional_text(notion_version) or DEFAULT_NOTION_VERSION
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> NotionPageCommentPublisher:
        return cls(token=kwargs.pop("token", None) or os.getenv("NOTION_TOKEN"), page_id=kwargs.pop("page_id", None) or os.getenv("NOTION_PAGE_ID"), api_url=kwargs.pop("api_url", None) or os.getenv("NOTION_API_URL", DEFAULT_NOTION_API_URL), notion_version=kwargs.pop("notion_version", None) or os.getenv("NOTION_VERSION", DEFAULT_NOTION_VERSION), **kwargs)

    @property
    def endpoint(self) -> str:
        return f"{self.api_url}/comments"

    def build_comment_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        page_id = required_text(self.page_id, "NOTION_PAGE_ID is required for Notion page comment publishing")
        return {"parent": {"page_id": page_id}, "rich_text": [{"type": "text", "text": {"content": chunk}} for chunk in _chunks(summary_markdown(payload), 1900)]}

    def publish(self, payload: dict[str, Any], *, dry_run: bool = True) -> NotionPageCommentPublishResult:
        request_payload = self.build_comment_payload(payload)
        if dry_run:
            return NotionPageCommentPublishResult(None, None, True, self.endpoint, request_payload)
        if not self.token:
            raise NotionPageCommentPublishError("NOTION_TOKEN is required for live Notion page comment publishing; use dry_run to preview")
        response = self._post(request_payload)
        body = response_json(response, NotionPageCommentPublishError, "Notion page comment publish failed: response was not valid JSON")
        return NotionPageCommentPublishResult(response.status_code, _text(body.get("id")), False, self.endpoint, request_payload, body)

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise NotionPageCommentPublishError(f"Notion page comment publish failed for {self.endpoint}: {exc}", token=self.token) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise NotionPageCommentPublishError(f"Notion page comment publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.token])}", status_code=response.status_code, token=self.token)
        return response

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {"Accept": "application/json", "Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "Notion-Version": self.notion_version, "User-Agent": "max-notion-page-comments-publisher/1"}


def _chunks(text: str, size: int) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)] or [""]


def _text(value: object) -> str | None:
    return str(value) if value else None

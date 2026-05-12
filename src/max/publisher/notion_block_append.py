"""Notion block append publisher for generated TactSpec previews."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, dict_value, join_list, metadata, optional_text, redact_text, required_text, required_url, response_json, response_preview, score_text, text_or_placeholder, title, validate_tact_spec

DEFAULT_NOTION_API_URL = "https://api.notion.com/v1"
DEFAULT_NOTION_VERSION = "2022-06-28"


class NotionBlockAppendPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class NotionBlockAppendPublishResult:
    status_code: int | None
    block_id: str
    appended_block_ids: list[str]
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class NotionBlockAppendPublisher:
    def __init__(self, *, token: str | None = None, block_id: str | None = None, api_url: str = DEFAULT_NOTION_API_URL, notion_version: str = DEFAULT_NOTION_VERSION, heading_level: int = 2, include_metadata: bool = True, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.token = optional_text(token)
        self.block_id = optional_text(block_id)
        self.api_url = required_url(api_url, "Notion API URL must be an absolute http(s) URL")
        self.notion_version = optional_text(notion_version) or DEFAULT_NOTION_VERSION
        self.heading_level = _heading_level(heading_level)
        self.include_metadata = include_metadata
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> NotionBlockAppendPublisher:
        return cls(token=kwargs.pop("token", None) or os.getenv("NOTION_TOKEN"), block_id=kwargs.pop("block_id", None) or os.getenv("NOTION_BLOCK_ID") or os.getenv("NOTION_PAGE_ID"), api_url=kwargs.pop("api_url", None) or os.getenv("NOTION_API_URL", DEFAULT_NOTION_API_URL), notion_version=kwargs.pop("notion_version", None) or os.getenv("NOTION_VERSION", DEFAULT_NOTION_VERSION), **kwargs)

    @property
    def endpoint(self) -> str:
        block_id = required_text(self.block_id, "NOTION_BLOCK_ID is required for Notion block append publishing")
        return f"{self.api_url}/blocks/{block_id}/children"

    def build_payload(self, tact_spec: dict[str, Any]) -> dict[str, Any]:
        try:
            validate_tact_spec(tact_spec, label="Notion block append")
        except ValueError as exc:
            raise NotionBlockAppendPublishError(str(exc), token=self.token) from exc
        meta = metadata(tact_spec, publisher="max.notion_block_append")
        project = dict_value(tact_spec, "project")
        evidence = dict_value(tact_spec, "evidence")
        quality = dict_value(tact_spec, "quality")
        evaluation = dict_value(tact_spec, "evaluation")
        children = [
            _heading_block(self.heading_level, title(tact_spec)),
            _paragraph_block(text_or_placeholder(project.get("summary"))),
            _bulleted_block(f"Evidence: {text_or_placeholder(evidence.get('rationale'))}"),
            _bulleted_block(f"Insights: {join_list(evidence.get('insight_ids'))}"),
            _bulleted_block(f"Risk tags: {join_list(quality.get('rejection_tags'))}"),
            _bulleted_block(f"Recommendation: {text_or_placeholder(evaluation.get('recommendation'))}; score {score_text(evaluation.get('overall_score'))}"),
        ]
        if self.include_metadata:
            children.append(_code_block(_json_dumps(meta), language="json"))
        return {"children": children}

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True) -> NotionBlockAppendPublishResult:
        block_id = required_text(self.block_id, "NOTION_BLOCK_ID is required for Notion block append publishing")
        payload = self.build_payload(tact_spec)
        if dry_run:
            return NotionBlockAppendPublishResult(None, block_id, [], True, self.endpoint, payload)
        if not self.token:
            raise NotionBlockAppendPublishError("NOTION_TOKEN is required for live Notion block append publishing; use dry_run to preview")
        response = self._patch(payload)
        body = response_json(response, NotionBlockAppendPublishError, "Notion block append publish failed: response was not valid JSON")
        return NotionBlockAppendPublishResult(response.status_code, block_id, _appended_ids(body), False, self.endpoint, payload, body)

    def _patch(self, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.patch(self.endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise NotionBlockAppendPublishError(f"Notion block append publish failed for {self.endpoint}: {exc}", token=self.token) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise NotionBlockAppendPublishError(f"Notion block append publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.token])}", status_code=response.status_code, token=self.token)
        return response

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {"Accept": "application/json", "Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "Notion-Version": self.notion_version, "User-Agent": "max-notion-block-append-publisher/1"}


NotionBlockAppendPublisherAlias = NotionBlockAppendPublisher


def _heading_level(value: int) -> int:
    if value not in {1, 2, 3}:
        raise NotionBlockAppendPublishError("Notion heading_level must be 1, 2, or 3")
    return value


def _rich_text(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": text[:1900]}}]


def _heading_block(level: int, text: str) -> dict[str, Any]:
    key = f"heading_{level}"
    return {"object": "block", "type": key, key: {"rich_text": _rich_text(text)}}


def _paragraph_block(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich_text(text)}}


def _bulleted_block(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _rich_text(text)}}


def _code_block(text: str, *, language: str) -> dict[str, Any]:
    return {"object": "block", "type": "code", "code": {"rich_text": _rich_text(text), "language": language}}


def _appended_ids(body: dict[str, Any]) -> list[str]:
    results = body.get("results")
    if not isinstance(results, list):
        return []
    return [str(item["id"]) for item in results if isinstance(item, dict) and item.get("id")]


def _json_dumps(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, indent=2, sort_keys=True)

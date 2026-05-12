"""Figma file comment publisher for Max ideas and design briefs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._summary_payloads import summary_markdown, summary_metadata
from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, quote_path, redact_text, required_text, required_url, response_json, response_preview

DEFAULT_FIGMA_API_URL = "https://api.figma.com"


class FigmaFileCommentPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class FigmaFileCommentPublishResult:
    status_code: int | None
    comment_id: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class FigmaFileCommentPublisher:
    def __init__(self, *, access_token: str | None = None, file_key: str | None = None, comment_node_id: str | None = None, api_url: str = DEFAULT_FIGMA_API_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.access_token = optional_text(access_token)
        self.file_key = optional_text(file_key)
        self.comment_node_id = optional_text(comment_node_id)
        self.api_url = required_url(api_url, "Figma API URL must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> FigmaFileCommentPublisher:
        return cls(
            access_token=kwargs.pop("access_token", None) or os.getenv("FIGMA_ACCESS_TOKEN"),
            file_key=kwargs.pop("file_key", None) or os.getenv("FIGMA_FILE_KEY"),
            comment_node_id=kwargs.pop("comment_node_id", None) or os.getenv("FIGMA_COMMENT_NODE_ID"),
            api_url=kwargs.pop("api_url", None) or os.getenv("FIGMA_API_URL", DEFAULT_FIGMA_API_URL),
            **kwargs,
        )

    @property
    def endpoint(self) -> str:
        file_key = required_text(self.file_key, "FIGMA_FILE_KEY is required for Figma comment publishing")
        return f"{self.api_url}/v1/files/{quote_path(file_key)}/comments"

    def build_comment_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        request: dict[str, Any] = {"message": summary_markdown(payload), "metadata": summary_metadata(payload, publisher="max.figma_file_comments")}
        if self.comment_node_id:
            request["client_meta"] = {"node_id": self.comment_node_id}
        return request

    def publish(self, payload: dict[str, Any], *, dry_run: bool = True) -> FigmaFileCommentPublishResult:
        request_payload = self.build_comment_payload(payload)
        endpoint = self.endpoint
        if dry_run:
            return FigmaFileCommentPublishResult(None, None, True, endpoint, request_payload)
        if not self.access_token:
            raise FigmaFileCommentPublishError("FIGMA_ACCESS_TOKEN is required for live Figma comment publishing; use dry_run to preview")
        response = self._post(endpoint, request_payload)
        body = response_json(response, FigmaFileCommentPublishError, "Figma comment publish failed: response was not valid JSON")
        return FigmaFileCommentPublishResult(response.status_code, _comment_id(body), False, endpoint, request_payload, body)

    def _post(self, endpoint: str, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise FigmaFileCommentPublishError(f"Figma comment publish failed for {endpoint}: {exc}", token=self.access_token) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise FigmaFileCommentPublishError(f"Figma comment publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.access_token])}", status_code=response.status_code, token=self.access_token)
        return response

    def _headers(self) -> dict[str, str]:
        assert self.access_token is not None
        return {"Accept": "application/json", "Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json", "User-Agent": "max-figma-file-comments-publisher/1"}


def publish_figma_file_comment(payload: dict[str, Any], **kwargs: Any) -> FigmaFileCommentPublishResult:
    return FigmaFileCommentPublisher.from_env(**{key: value for key, value in kwargs.items() if key != "dry_run"}).publish(payload, dry_run=kwargs.get("dry_run", True))


def _comment_id(body: dict[str, Any]) -> str | None:
    comment = body.get("comment") if isinstance(body.get("comment"), dict) else {}
    value = body.get("id") or comment.get("id")
    return str(value) if value else None

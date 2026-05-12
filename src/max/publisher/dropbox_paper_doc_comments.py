"""Dropbox Paper document comment publisher for Max summaries."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._summary_payloads import summary_markdown, summary_metadata
from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, quote_path, redact_text, required_text, required_url, response_json, response_preview

DEFAULT_DROPBOX_API_URL = "https://api.dropboxapi.com/2"


class DropboxPaperDocCommentPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class DropboxPaperDocCommentPublishResult:
    status_code: int | None
    comment_id: str | None
    comment_url: str | None
    dry_run: bool
    endpoint: str
    headers: dict[str, str]
    payload: dict[str, Any]
    markdown: str
    response: dict[str, Any] | None = None


class DropboxPaperDocCommentPublisher:
    def __init__(self, *, access_token: str | None = None, doc_id: str | None = None, api_url: str = DEFAULT_DROPBOX_API_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.access_token = optional_text(access_token)
        self.doc_id = optional_text(doc_id)
        self.api_url = required_url(api_url, "Dropbox API URL must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> DropboxPaperDocCommentPublisher:
        return cls(
            access_token=kwargs.pop("access_token", None) or os.getenv("DROPBOX_ACCESS_TOKEN"),
            doc_id=kwargs.pop("doc_id", None) or os.getenv("DROPBOX_PAPER_DOC_ID"),
            api_url=kwargs.pop("api_url", None) or os.getenv("DROPBOX_API_URL", DEFAULT_DROPBOX_API_URL),
            **kwargs,
        )

    @property
    def endpoint(self) -> str:
        doc_id = required_text(self.doc_id, "DROPBOX_PAPER_DOC_ID is required for Dropbox Paper comment publishing")
        return f"{self.api_url}/paper/docs/{quote_path(doc_id)}/comments"

    def build_comment_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"doc_id": self.doc_id, "comment": {"text": summary_markdown(payload), "format": "markdown"}, "metadata": summary_metadata(payload, publisher="max.dropbox_paper_doc_comments")}

    def publish(self, payload: dict[str, Any], *, dry_run: bool = True) -> DropboxPaperDocCommentPublishResult:
        request_payload = self.build_comment_payload(payload)
        endpoint = self.endpoint
        markdown = request_payload["comment"]["text"]
        if dry_run:
            return DropboxPaperDocCommentPublishResult(None, None, None, True, endpoint, self._headers(redacted=True), request_payload, markdown)
        if not self.access_token:
            raise DropboxPaperDocCommentPublishError("DROPBOX_ACCESS_TOKEN is required for live Dropbox Paper comment publishing; use dry_run to preview")
        response = self._post(endpoint, request_payload)
        body = response_json(response, DropboxPaperDocCommentPublishError, "Dropbox Paper comment publish failed: response was not valid JSON")
        return DropboxPaperDocCommentPublishResult(response.status_code, _first_text(body, "comment_id", "id"), _first_text(body, "url", "comment_url"), False, endpoint, self._headers(redacted=True), request_payload, markdown, body)

    def _post(self, endpoint: str, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise DropboxPaperDocCommentPublishError(f"Dropbox Paper comment publish failed for {endpoint}: {exc}", token=self.access_token) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise DropboxPaperDocCommentPublishError(f"Dropbox Paper comment publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.access_token])}", status_code=response.status_code, token=self.access_token)
        return response

    def _headers(self, *, redacted: bool = False) -> dict[str, str]:
        token = "[REDACTED]" if redacted and self.access_token else self.access_token
        headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "max-dropbox-paper-doc-comments-publisher/1"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers


DropboxPaperDocCommentsPublisher = DropboxPaperDocCommentPublisher


def publish_dropbox_paper_doc_comment(payload: dict[str, Any], **kwargs: Any) -> DropboxPaperDocCommentPublishResult:
    return DropboxPaperDocCommentPublisher.from_env(**{key: value for key, value in kwargs.items() if key != "dry_run"}).publish(payload, dry_run=kwargs.get("dry_run", True))


def _first_text(body: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = body.get(key)
        if value:
            return str(value)
    return None

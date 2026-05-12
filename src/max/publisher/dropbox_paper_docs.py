"""Dropbox Paper document publisher for Max summaries."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._summary_payloads import summary_markdown, summary_metadata, summary_title
from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, redact_text, required_url, response_json, response_preview

DEFAULT_DROPBOX_API_URL = "https://api.dropboxapi.com/2"


class DropboxPaperDocPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class DropboxPaperDocPublishResult:
    status_code: int | None
    document_id: str | None
    document_url: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class DropboxPaperDocPublisher:
    def __init__(self, *, access_token: str | None = None, api_url: str = DEFAULT_DROPBOX_API_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.access_token = optional_text(access_token)
        self.api_url = required_url(api_url, "Dropbox API URL must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> DropboxPaperDocPublisher:
        return cls(access_token=kwargs.pop("access_token", None) or os.getenv("DROPBOX_ACCESS_TOKEN"), api_url=kwargs.pop("api_url", None) or os.getenv("DROPBOX_API_URL", DEFAULT_DROPBOX_API_URL), **kwargs)

    @property
    def endpoint(self) -> str:
        return f"{self.api_url}/paper/docs/create"

    def build_document_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"title": summary_title(payload), "body": summary_markdown(payload), "format": "markdown", "metadata": summary_metadata(payload, publisher="max.dropbox_paper_docs")}

    def publish(self, payload: dict[str, Any], *, dry_run: bool = True) -> DropboxPaperDocPublishResult:
        request_payload = self.build_document_payload(payload)
        if dry_run:
            return DropboxPaperDocPublishResult(None, None, None, True, self.endpoint, request_payload)
        if not self.access_token:
            raise DropboxPaperDocPublishError("DROPBOX_ACCESS_TOKEN is required for live Dropbox Paper publishing; use dry_run to preview")
        response = self._post(request_payload)
        body = response_json(response, DropboxPaperDocPublishError, "Dropbox Paper publish failed: response was not valid JSON")
        return DropboxPaperDocPublishResult(response.status_code, _first_text(body, "doc_id", "id"), _first_text(body, "url", "document_url"), False, self.endpoint, request_payload, body)

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise DropboxPaperDocPublishError(f"Dropbox Paper publish failed for {self.endpoint}: {exc}", token=self.access_token) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise DropboxPaperDocPublishError(f"Dropbox Paper publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.access_token])}", status_code=response.status_code, token=self.access_token)
        return response

    def _headers(self) -> dict[str, str]:
        assert self.access_token is not None
        return {"Accept": "application/json", "Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json", "User-Agent": "max-dropbox-paper-docs-publisher/1"}


def _first_text(body: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = body.get(key)
        if value:
            return str(value)
    return None

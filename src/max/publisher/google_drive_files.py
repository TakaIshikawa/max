"""Google Drive Markdown file publisher for Max summaries."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._summary_payloads import deterministic_filename, summary_markdown, summary_metadata
from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, redact_text, required_url, response_json, response_preview

DEFAULT_GOOGLE_DRIVE_API_URL = "https://www.googleapis.com/drive/v3"


class GoogleDriveFilePublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class GoogleDriveFilePublishResult:
    status_code: int | None
    file_id: str | None
    web_view_link: str | None
    dry_run: bool
    endpoint: str
    headers: dict[str, str]
    metadata: dict[str, Any]
    content: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class GoogleDriveFilePublisher:
    def __init__(self, *, access_token: str | None = None, folder_id: str | None = None, api_url: str = DEFAULT_GOOGLE_DRIVE_API_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.access_token = optional_text(access_token)
        self.folder_id = optional_text(folder_id)
        self.api_url = required_url(api_url, "Google Drive API URL must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> GoogleDriveFilePublisher:
        return cls(access_token=kwargs.pop("access_token", None) or os.getenv("GOOGLE_DRIVE_ACCESS_TOKEN"), folder_id=kwargs.pop("folder_id", None) or os.getenv("GOOGLE_DRIVE_FOLDER_ID"), api_url=kwargs.pop("api_url", None) or os.getenv("GOOGLE_DRIVE_API_URL", DEFAULT_GOOGLE_DRIVE_API_URL), **kwargs)

    @property
    def endpoint(self) -> str:
        return f"{self.api_url}/files?uploadType=multipart&fields=id,webViewLink"

    def build_file_payload(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str, dict[str, Any]]:
        metadata: dict[str, Any] = {"name": deterministic_filename(payload), "mimeType": "text/markdown", "appProperties": summary_metadata(payload, publisher="max.google_drive_files")}
        if self.folder_id:
            metadata["parents"] = [self.folder_id]
        content = summary_markdown(payload)
        return metadata, content, {"metadata": metadata, "content": content}

    def publish(self, payload: dict[str, Any], *, dry_run: bool = True) -> GoogleDriveFilePublishResult:
        metadata, content, request_payload = self.build_file_payload(payload)
        headers = self._preview_headers() if dry_run else self._headers()
        if dry_run:
            return GoogleDriveFilePublishResult(None, None, None, True, self.endpoint, headers, metadata, content, request_payload)
        if not self.access_token:
            raise GoogleDriveFilePublishError("GOOGLE_DRIVE_ACCESS_TOKEN is required for live Google Drive publishing; use dry_run to preview")
        response = self._post(request_payload)
        body = response_json(response, GoogleDriveFilePublishError, "Google Drive publish failed: response was not valid JSON")
        return GoogleDriveFilePublishResult(response.status_code, _text(body.get("id")), _text(body.get("webViewLink")), False, self.endpoint, headers, metadata, content, request_payload, body)

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise GoogleDriveFilePublishError(f"Google Drive publish failed for {self.endpoint}: {exc}", token=self.access_token) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise GoogleDriveFilePublishError(f"Google Drive publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.access_token])}", status_code=response.status_code, token=self.access_token)
        return response

    def _preview_headers(self) -> dict[str, str]:
        return {"Accept": "application/json", "Authorization": "Bearer [REDACTED]", "Content-Type": "application/json", "User-Agent": "max-google-drive-files-publisher/1"}

    def _headers(self) -> dict[str, str]:
        if not self.access_token:
            return self._preview_headers()
        headers = self._preview_headers()
        headers["Authorization"] = f"Bearer {self.access_token}"
        return headers


def _text(value: object) -> str | None:
    return str(value) if value else None

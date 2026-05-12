"""Confluence Cloud page comment publisher."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_TIMEOUT_SECONDS = 10.0


class ConfluencePageCommentPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ConfluencePageCommentPayload:
    page_id: str
    body: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"page_id": self.page_id, "body": self.body, "metadata": self.metadata}

    def to_request(self) -> dict[str, Any]:
        return {
            "type": "comment",
            "container": {"type": "page", "id": self.page_id},
            "body": self.body,
        }


@dataclass(frozen=True)
class ConfluencePageCommentPublishResult:
    status_code: int | None
    page_id: str
    comment_id: str | None
    comment_url: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class ConfluencePageCommentPublisher:
    def __init__(
        self,
        site_url: str,
        *,
        page_id: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        bearer_token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.site_url = _required_url(site_url)
        self.page_id = _optional_text(page_id)
        self.email = _optional_text(email)
        self.api_token = _optional_text(api_token)
        self.bearer_token = _optional_text(bearer_token)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> ConfluencePageCommentPublisher:
        site_url = kwargs.pop("site_url", None) or os.getenv("CONFLUENCE_SITE_URL")
        if not site_url:
            raise ConfluencePageCommentPublishError("Confluence site_url is required; pass site_url or set CONFLUENCE_SITE_URL")
        return cls(
            site_url,
            page_id=kwargs.pop("page_id", None) or os.getenv("CONFLUENCE_PAGE_ID"),
            email=kwargs.pop("email", None) or os.getenv("CONFLUENCE_EMAIL"),
            api_token=kwargs.pop("api_token", None) or os.getenv("CONFLUENCE_API_TOKEN"),
            bearer_token=kwargs.pop("bearer_token", None) or os.getenv("CONFLUENCE_BEARER_TOKEN"),
            **kwargs,
        )

    @property
    def comment_endpoint(self) -> str:
        return f"{self.site_url}/wiki/rest/api/content"

    def build_comment_payload(
        self,
        *,
        page_id: str | None = None,
        body: str | dict[str, Any] | None = None,
        representation: str = "storage",
        metadata: dict[str, Any] | None = None,
    ) -> ConfluencePageCommentPayload:
        resolved_page_id = _required_text(_optional_text(page_id) or self.page_id, "Confluence page_id is required; pass page_id or set CONFLUENCE_PAGE_ID")
        resolved_body = _body_payload(body, representation=representation)
        return ConfluencePageCommentPayload(
            page_id=resolved_page_id,
            body=resolved_body,
            metadata={"publisher": "max.confluence_page_comments", "confluence_page_id": resolved_page_id, **(metadata or {})},
        )

    async def publish(
        self,
        *,
        page_id: str | None = None,
        body: str | dict[str, Any] | None = None,
        representation: str = "storage",
        metadata: dict[str, Any] | None = None,
        dry_run: bool = True,
    ) -> ConfluencePageCommentPublishResult:
        payload = self.build_comment_payload(page_id=page_id, body=body, representation=representation, metadata=metadata)
        payload_dict = payload.to_dict()
        if dry_run:
            return ConfluencePageCommentPublishResult(None, payload.page_id, None, None, True, self.comment_endpoint, payload_dict)
        if not self._has_auth:
            raise ConfluencePageCommentPublishError("Confluence email/api_token or bearer_token is required for live page comment publishing; use dry_run to preview")
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        try:
            try:
                response = await client.post(self.comment_endpoint, json=payload.to_request(), headers=self._headers(), timeout=self.timeout)
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise ConfluencePageCommentPublishError(f"Confluence page comment publish failed for {self.comment_endpoint}: {exc}") from exc
        finally:
            if close_client:
                await client.aclose()
        if not 200 <= response.status_code < 300:
            raise ConfluencePageCommentPublishError(
                f"Confluence page comment publish failed with HTTP {response.status_code}: {_response_body_preview(response)}",
                status_code=response.status_code,
            )
        body_json = _json_response(response)
        comment_id = _optional_text(body_json.get("id"))
        if not comment_id:
            raise ConfluencePageCommentPublishError("Confluence page comment publish failed: response did not include comment id", status_code=response.status_code)
        return ConfluencePageCommentPublishResult(
            response.status_code,
            payload.page_id,
            comment_id,
            _page_url(self.site_url, body_json),
            False,
            self.comment_endpoint,
            payload_dict,
            body_json,
        )

    @property
    def _has_auth(self) -> bool:
        return bool(self.bearer_token or (self.email and self.api_token))

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "max-confluence-page-comments-publisher/1"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        else:
            assert self.email is not None and self.api_token is not None
            credentials = f"{self.email}:{self.api_token}".encode("utf-8")
            headers["Authorization"] = f"Basic {base64.b64encode(credentials).decode('ascii')}"
        return headers


ConfluencePageCommentsPublisher = ConfluencePageCommentPublisher


def _body_payload(body: str | dict[str, Any] | None, *, representation: str) -> dict[str, Any]:
    if isinstance(body, dict):
        if not body:
            raise ConfluencePageCommentPublishError("Confluence comment body is required")
        return body
    text = _required_text(body, "Confluence comment body is required")
    return {representation: {"value": text, "representation": representation}}


def _page_url(site_url: str, response_body: dict[str, Any]) -> str | None:
    links = response_body.get("_links") if isinstance(response_body.get("_links"), dict) else {}
    for key in ("webui", "tinyui", "self"):
        link = _optional_text(links.get(key))
        if link:
            return f"{site_url}{link}" if link.startswith("/") else link
    return None


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise ConfluencePageCommentPublishError("Confluence page comment publish failed: response was not valid JSON", status_code=response.status_code) from exc
    if not isinstance(data, dict):
        raise ConfluencePageCommentPublishError("Confluence page comment publish failed: response JSON was not an object", status_code=response.status_code)
    return data


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    return text if len(text) <= limit else text[:limit] + "..."


def _required_url(value: str) -> str:
    text = _required_text(value, "Confluence site_url is required")
    if not text.startswith(("http://", "https://")):
        raise ConfluencePageCommentPublishError("Confluence site_url must start with http:// or https://")
    return text.rstrip("/")


def _required_text(value: object, message: str) -> str:
    text = _optional_text(value)
    if not text:
        raise ConfluencePageCommentPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None

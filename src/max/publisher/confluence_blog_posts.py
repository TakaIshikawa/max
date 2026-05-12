"""Confluence Cloud blog post publisher."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, required_text, required_url, response_json

DEFAULT_API_PATH = "/wiki/rest/api/content"


class ConfluenceBlogPostPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ConfluenceBlogPostPublishResult:
    status_code: int | None
    blog_post_id: str | None
    blog_post_url: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class ConfluenceBlogPostPublisher:
    def __init__(self, *, site_url: str | None = None, space_key: str | None = None, space_id: str | None = None, email: str | None = None, api_token: str | None = None, bearer_token: str | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.site_url = required_url(site_url, "Confluence site_url must be an absolute http(s) URL")
        self.space_key = optional_text(space_key)
        self.space_id = optional_text(space_id)
        self.email = optional_text(email)
        self.api_token = optional_text(api_token)
        self.bearer_token = optional_text(bearer_token)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> ConfluenceBlogPostPublisher:
        return cls(site_url=kwargs.pop("site_url", None) or os.getenv("CONFLUENCE_SITE_URL"), space_key=kwargs.pop("space_key", None) or os.getenv("CONFLUENCE_SPACE_KEY"), space_id=kwargs.pop("space_id", None) or os.getenv("CONFLUENCE_SPACE_ID"), email=kwargs.pop("email", None) or os.getenv("CONFLUENCE_EMAIL"), api_token=kwargs.pop("api_token", None) or os.getenv("CONFLUENCE_API_TOKEN"), bearer_token=kwargs.pop("bearer_token", None) or os.getenv("CONFLUENCE_BEARER_TOKEN"), **kwargs)

    @property
    def blog_endpoint(self) -> str:
        return f"{self.site_url}{DEFAULT_API_PATH}"

    def build_blog_post_payload(self, *, title: str, body: str, status: str | None = None, labels: list[str] | None = None) -> dict[str, Any]:
        space: dict[str, str] = {}
        if self.space_id:
            space["id"] = self.space_id
        else:
            space["key"] = required_text(self.space_key, "CONFLUENCE_SPACE_KEY or CONFLUENCE_SPACE_ID is required for Confluence blog post publishing")
        payload: dict[str, Any] = {"type": "blogpost", "title": required_text(title, "Confluence blog post title is required"), "space": space, "body": {"storage": {"value": body, "representation": "storage"}}, "metadata": {"publisher": "max.confluence_blog_posts", "labels": labels or []}}
        if status:
            payload["status"] = status
        if labels:
            payload["metadata"]["labels"] = labels
        return payload

    def publish(self, *, title: str, body: str, dry_run: bool = True, status: str | None = None, labels: list[str] | None = None) -> ConfluenceBlogPostPublishResult:
        payload = self.build_blog_post_payload(title=title, body=body, status=status, labels=labels)
        if dry_run:
            return ConfluenceBlogPostPublishResult(None, None, None, True, self.blog_endpoint, payload)
        if not (self.bearer_token or (self.email and self.api_token)):
            raise ConfluenceBlogPostPublishError("Confluence email/api_token or bearer_token is required for live blog post publishing; use dry_run to preview")
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.blog_endpoint, json=_request(payload), headers=self._headers(), timeout=self.timeout)
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise ConfluenceBlogPostPublishError(f"Confluence blog post publish failed with HTTP {response.status_code}: {response.text[:500]}", status_code=response.status_code)
        data = response_json(response, ConfluenceBlogPostPublishError, "Confluence blog post publish failed: response was not valid JSON")
        post_id = optional_text(data.get("id"))
        url = _page_url(self.site_url, data)
        return ConfluenceBlogPostPublishResult(response.status_code, post_id, url, False, self.blog_endpoint, payload, data)

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "max-confluence-blog-posts-publisher/1"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        else:
            assert self.email is not None and self.api_token is not None
            headers["Authorization"] = "Basic " + base64.b64encode(f"{self.email}:{self.api_token}".encode()).decode("ascii")
        return headers


ConfluenceBlogPostsPublisher = ConfluenceBlogPostPublisher


def _request(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload[key] for key in ["type", "title", "space", "body"] if key in payload} | ({"status": payload["status"]} if payload.get("status") else {})


def _page_url(site_url: str, response_body: dict[str, Any]) -> str | None:
    links = response_body.get("_links") if isinstance(response_body.get("_links"), dict) else {}
    webui = links.get("webui")
    if webui:
        return f"{site_url}{webui}" if str(webui).startswith("/") else str(webui)
    return None

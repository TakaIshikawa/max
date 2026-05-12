"""Zendesk Help Center article publisher for Max summaries."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from max.publisher._summary_payloads import summary_markdown, summary_metadata, summary_title
from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, required_text, response_json, response_preview


class ZendeskHelpCenterArticlePublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, api_token: str | None = None) -> None:
        super().__init__(message.replace(api_token, "[REDACTED]") if api_token else message)
        self.status_code = status_code


@dataclass(frozen=True)
class ZendeskHelpCenterArticlePublishResult:
    status_code: int | None
    article_id: str | None
    article_url: str | None
    dry_run: bool
    endpoint: str
    headers: dict[str, str]
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class ZendeskHelpCenterArticlePublisher:
    def __init__(
        self,
        *,
        subdomain: str | None = None,
        api_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        section_id: str | int,
        locale: str = "en-us",
        permission_group_id: str | int | None = None,
        user_segment_id: str | int | None = None,
        title: str | None = None,
        draft: bool = True,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_url = _zendesk_api_url(subdomain=subdomain, api_url=api_url)
        self.email = optional_text(email)
        self.api_token = optional_text(api_token)
        self.section_id = required_text(section_id, "Zendesk section_id is required")
        self.locale = required_text(locale, "Zendesk locale is required")
        self.permission_group_id = optional_text(permission_group_id)
        self.user_segment_id = optional_text(user_segment_id)
        self.title = optional_text(title)
        self.draft = bool(draft)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> ZendeskHelpCenterArticlePublisher:
        return cls(
            subdomain=kwargs.pop("subdomain", None) or os.getenv("ZENDESK_SUBDOMAIN"),
            api_url=kwargs.pop("api_url", None) or os.getenv("ZENDESK_API_URL") or os.getenv("ZENDESK_BASE_URL"),
            email=kwargs.pop("email", None) or os.getenv("ZENDESK_EMAIL"),
            api_token=kwargs.pop("api_token", None) or os.getenv("ZENDESK_API_TOKEN"),
            section_id=kwargs.pop("section_id", None) or os.getenv("ZENDESK_SECTION_ID"),
            locale=kwargs.pop("locale", None) or os.getenv("ZENDESK_LOCALE", "en-us"),
            **kwargs,
        )

    @property
    def endpoint(self) -> str:
        return f"{self.api_url}/api/v2/help_center/{self.locale}/sections/{self.section_id}/articles.json"

    def build_article_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        article: dict[str, Any] = {
            "title": self.title or summary_title(payload),
            "body": summary_markdown(payload),
            "locale": self.locale,
            "draft": self.draft,
        }
        if self.permission_group_id:
            article["permission_group_id"] = self.permission_group_id
        if self.user_segment_id:
            article["user_segment_id"] = self.user_segment_id
        return {"article": article, "metadata": summary_metadata(payload, publisher="max.zendesk_help_center_articles")}

    def publish(self, payload: dict[str, Any], *, dry_run: bool = True) -> ZendeskHelpCenterArticlePublishResult:
        request_payload = self.build_article_payload(payload)
        if dry_run:
            return ZendeskHelpCenterArticlePublishResult(None, None, None, True, self.endpoint, self._preview_headers(), request_payload)
        if not self.email or not self.api_token:
            raise ZendeskHelpCenterArticlePublishError("ZENDESK_EMAIL and ZENDESK_API_TOKEN are required for live Zendesk Help Center article publishing; use dry_run to preview")
        response = self._post(request_payload)
        body = response_json(response, ZendeskHelpCenterArticlePublishError, "Zendesk Help Center article publish failed: response was not valid JSON")
        article = body.get("article") if isinstance(body.get("article"), dict) else body
        return ZendeskHelpCenterArticlePublishResult(response.status_code, _text(article.get("id")), _text(article.get("html_url")), False, self.endpoint, self._headers(), request_payload, body)

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise ZendeskHelpCenterArticlePublishError(f"Zendesk Help Center article publish failed for {self.endpoint}: {exc}", api_token=self.api_token) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise ZendeskHelpCenterArticlePublishError(f"Zendesk Help Center article publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.api_token])}", status_code=response.status_code, api_token=self.api_token)
        return response

    def _headers(self) -> dict[str, str]:
        assert self.email is not None and self.api_token is not None
        credentials = f"{self.email}/token:{self.api_token}".encode()
        return {"Accept": "application/json", "Authorization": f"Basic {base64.b64encode(credentials).decode('ascii')}", "Content-Type": "application/json", "User-Agent": "max-zendesk-help-center-articles-publisher/1"}

    def _preview_headers(self) -> dict[str, str]:
        return {"Accept": "application/json", "Authorization": "Basic [REDACTED]", "Content-Type": "application/json", "User-Agent": "max-zendesk-help-center-articles-publisher/1"}


def _zendesk_api_url(*, subdomain: str | None, api_url: str | None) -> str:
    raw = optional_text(api_url)
    if raw:
        if not raw.startswith(("http://", "https://")):
            raw = f"https://{raw}"
        parts = urlsplit(raw)
        if not parts.netloc or any(ch.isspace() for ch in parts.netloc):
            raise ZendeskHelpCenterArticlePublishError("Zendesk api_url must be an absolute URL")
        return raw.rstrip("/")
    sub = required_text(subdomain, "Zendesk subdomain or api_url is required").strip()
    if "://" in sub:
        parts = urlsplit(sub)
        sub = parts.netloc or parts.path
    domain = sub if "." in sub else f"{sub}.zendesk.com"
    if "/" in domain:
        raise ZendeskHelpCenterArticlePublishError("Zendesk subdomain must be a subdomain, domain, or api_url")
    return f"https://{domain.lower()}"


def _text(value: object) -> str | None:
    return str(value) if value is not None else None

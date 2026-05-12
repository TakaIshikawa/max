"""Mailchimp campaign draft publisher for generated TactSpec previews."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, markdown_summary, metadata, optional_text, required_text, required_url, response_json, response_preview, title, validate_tact_spec

DEFAULT_FROM_NAME = "Max"
DEFAULT_REPLY_TO = "noreply@example.com"


class MailchimpCampaignDraftPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class MailchimpCampaignDraftPayload:
    list_id: str
    campaign: dict[str, Any]
    content: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"list_id": self.list_id, "campaign": self.campaign, "content": self.content, "metadata": self.metadata}


@dataclass(frozen=True)
class MailchimpCampaignDraftPublishResult:
    status_code: int | None
    campaign_id: str | None
    web_id: str | None
    dry_run: bool
    payload: dict[str, Any]


class MailchimpCampaignDraftPublisher:
    def __init__(self, *, server_prefix: str | None = None, list_id: str | None = None, api_key: str | None = None, api_url: str | None = None, subject_prefix: str = "[Max]", timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.server_prefix = optional_text(server_prefix)
        self.list_id = optional_text(list_id)
        self.api_key = optional_text(api_key)
        self.api_url = required_url(api_url or self._api_url_from_prefix(self.server_prefix), "Mailchimp api_url must be an absolute http(s) URL")
        self.subject_prefix = optional_text(subject_prefix) or "[Max]"
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, *, server_prefix: str | None = None, list_id: str | None = None, api_key: str | None = None, api_url: str | None = None, subject_prefix: str | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> MailchimpCampaignDraftPublisher:
        key = api_key or os.getenv("MAILCHIMP_API_KEY")
        prefix = server_prefix or os.getenv("MAILCHIMP_SERVER_PREFIX") or _prefix_from_key(key)
        return cls(server_prefix=prefix, list_id=list_id or os.getenv("MAILCHIMP_LIST_ID"), api_key=key, api_url=api_url or os.getenv("MAILCHIMP_API_URL"), subject_prefix=subject_prefix or os.getenv("MAILCHIMP_SUBJECT_PREFIX", "[Max]"), timeout=timeout, client=client)

    @property
    def campaigns_endpoint(self) -> str:
        return f"{self.api_url}/3.0/campaigns"

    def build_campaign_payload(self, tact_spec: dict[str, Any]) -> MailchimpCampaignDraftPayload:
        try:
            validate_tact_spec(tact_spec, label="Mailchimp campaign draft")
            list_id = required_text(self.list_id, "MAILCHIMP_LIST_ID is required for Mailchimp campaign draft publishing")
        except ValueError as exc:
            raise MailchimpCampaignDraftPublishError(str(exc)) from exc
        meta = metadata(tact_spec, publisher="max.mailchimp_campaign_drafts")
        subject = f"{self.subject_prefix} {title(tact_spec)}"[:150]
        campaign = {
            "type": "regular",
            "recipients": {"list_id": list_id},
            "settings": {
                "subject_line": subject,
                "title": subject,
                "from_name": DEFAULT_FROM_NAME,
                "reply_to": DEFAULT_REPLY_TO,
            },
        }
        content = {"plain_text": markdown_summary(tact_spec, meta)}
        return MailchimpCampaignDraftPayload(list_id, campaign, content, meta)

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True) -> MailchimpCampaignDraftPublishResult:
        payload = self.build_campaign_payload(tact_spec).to_dict()
        if dry_run:
            return MailchimpCampaignDraftPublishResult(None, None, None, True, payload)
        if not self.api_key:
            raise MailchimpCampaignDraftPublishError("MAILCHIMP_API_KEY is required for live Mailchimp campaign draft publishing; use dry_run to preview")
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.campaigns_endpoint, json=payload["campaign"], headers=self._headers(), timeout=self.timeout)
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise MailchimpCampaignDraftPublishError(f"Mailchimp campaign draft publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.api_key])}", status_code=response.status_code)
        body = response_json(response, MailchimpCampaignDraftPublishError, "Mailchimp campaign draft publish failed: response was not valid JSON")
        return MailchimpCampaignDraftPublishResult(response.status_code, optional_text(body.get("id")), optional_text(body.get("web_id")), False, payload)

    def _headers(self) -> dict[str, str]:
        assert self.api_key is not None
        token = base64.b64encode(f"anystring:{self.api_key}".encode()).decode("ascii")
        return {"Accept": "application/json", "Authorization": f"Basic {token}", "Content-Type": "application/json", "User-Agent": "max-mailchimp-campaign-drafts-publisher/1"}

    @staticmethod
    def _api_url_from_prefix(prefix: str | None) -> str:
        if not prefix:
            return "https://us1.api.mailchimp.com"
        return f"https://{prefix}.api.mailchimp.com"


MailchimpCampaignDraftsPublisher = MailchimpCampaignDraftPublisher


def _prefix_from_key(api_key: str | None) -> str | None:
    if api_key and "-" in api_key:
        return api_key.rsplit("-", 1)[1]
    return None

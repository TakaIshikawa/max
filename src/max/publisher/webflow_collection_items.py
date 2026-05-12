"""Webflow collection item publisher for Max ideas and design briefs."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, dict_value, join_list, optional_text, redact_text, required_text, required_url, score_text, source_id, text_or_placeholder, title

DEFAULT_API_URL = "https://api.webflow.com/v2"
DEFAULT_API_VERSION = "2.0.0"


class WebflowCollectionItemPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class WebflowCollectionItemPublishResult:
    status_code: int | None
    item_id: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class WebflowCollectionItemPublisher:
    def __init__(
        self,
        *,
        site_id: str | None = None,
        collection_id: str | None = None,
        access_token: str | None = None,
        api_version: str = DEFAULT_API_VERSION,
        api_url: str = DEFAULT_API_URL,
        is_draft: bool = False,
        is_archived: bool = False,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.site_id = optional_text(site_id)
        self.collection_id = optional_text(collection_id)
        self.access_token = optional_text(access_token)
        self.api_version = optional_text(api_version) or DEFAULT_API_VERSION
        self.api_url = required_url(api_url, "Webflow api_url must be an absolute http(s) URL")
        self.is_draft = is_draft
        self.is_archived = is_archived
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> WebflowCollectionItemPublisher:
        return cls(
            site_id=kwargs.pop("site_id", None) or os.getenv("WEBFLOW_SITE_ID"),
            collection_id=kwargs.pop("collection_id", None) or os.getenv("WEBFLOW_COLLECTION_ID"),
            access_token=kwargs.pop("access_token", None) or os.getenv("WEBFLOW_ACCESS_TOKEN"),
            api_version=kwargs.pop("api_version", None) or os.getenv("WEBFLOW_API_VERSION", DEFAULT_API_VERSION),
            api_url=kwargs.pop("api_url", None) or os.getenv("WEBFLOW_API_URL", DEFAULT_API_URL),
            **kwargs,
        )

    @property
    def endpoint(self) -> str:
        site_id = required_text(self.site_id, "WEBFLOW_SITE_ID is required for Webflow collection item publishing")
        collection_id = required_text(self.collection_id, "WEBFLOW_COLLECTION_ID is required for Webflow collection item publishing")
        return f"{self.api_url}/sites/{quote(site_id, safe='')}/collections/{quote(collection_id, safe='')}/items"

    def build_item_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"isDraft": self.is_draft, "isArchived": self.is_archived, "fieldData": _field_data(payload)}

    def publish(self, payload: dict[str, Any], *, dry_run: bool = True) -> WebflowCollectionItemPublishResult:
        endpoint = self.endpoint
        item_payload = self.build_item_payload(payload)
        if dry_run:
            return WebflowCollectionItemPublishResult(None, None, True, endpoint, item_payload)
        if not self.access_token:
            raise WebflowCollectionItemPublishError("WEBFLOW_ACCESS_TOKEN is required for live Webflow collection item publishing; use dry_run to preview")
        response = self._post(item_payload)
        try:
            body = response.json()
        except ValueError:
            body = {}
        return WebflowCollectionItemPublishResult(response.status_code, optional_text(body.get("id")) if isinstance(body, dict) else None, False, endpoint, item_payload, body if isinstance(body, dict) else {})

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise WebflowCollectionItemPublishError(f"Webflow collection item publish failed with HTTP {response.status_code}: {redact_text(response.text, secrets=[self.access_token])}", status_code=response.status_code, token=self.access_token)
        return response

    def _headers(self) -> dict[str, str]:
        assert self.access_token is not None
        return {"Accept": "application/json", "Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json", "User-Agent": "max-webflow-collection-items-publisher/1", "Webflow-Version": self.api_version}


WebflowCollectionItemsPublisher = WebflowCollectionItemPublisher


def publish_webflow_collection_item(payload: dict[str, Any], **kwargs: Any) -> WebflowCollectionItemPublishResult:
    publisher = WebflowCollectionItemPublisher.from_env(**{key: value for key, value in kwargs.items() if key != "dry_run"})
    return publisher.publish(payload, dry_run=kwargs.get("dry_run", True))


def _field_data(payload: dict[str, Any]) -> dict[str, Any]:
    if "design_brief" in payload:
        brief = dict_value(payload, "design_brief")
        name = optional_text(brief.get("title")) or optional_text(brief.get("id")) or "Max design brief"
        return {
            "name": name,
            "slug": slugify(f"{optional_text(brief.get('id')) or ''}-{name}"),
            "readiness-score": score_text(brief.get("readiness_score")),
            "recommendation": text_or_placeholder(brief.get("recommendation")),
            "markdown-body": text_or_placeholder(brief.get("markdown") or brief.get("summary")),
            "source-idea-ids": join_list(brief.get("source_idea_ids")),
        }
    source = dict_value(payload, "source")
    project = dict_value(payload, "project")
    evaluation = dict_value(payload, "evaluation")
    name = title(payload, fallback="Max idea")
    source_identifier = source_id(source)
    return {
        "name": name,
        "slug": slugify(f"{source_identifier or ''}-{name}"),
        "summary": text_or_placeholder(project.get("summary")),
        "score": score_text(evaluation.get("overall_score")),
        "recommendation": text_or_placeholder(evaluation.get("recommendation")),
        "domain": text_or_placeholder(source.get("domain")),
        "source-id": text_or_placeholder(source_identifier),
    }


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "max-item"

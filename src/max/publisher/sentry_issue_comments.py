"""Sentry issue comment publisher for Max buildable units."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, join_list, optional_text, redact_text, required_text, required_url, response_json, response_preview
from max.publisher.stripe_customer_notes import _RETRYABLE_STATUS_CODES, _unit_fields

DEFAULT_API_URL = "https://sentry.io/api/0"


class SentryIssueCommentPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class SentryIssueCommentPayload:
    organization_slug: str
    issue_id: str
    text: str
    metadata: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {"organization_slug": self.organization_slug, "issue_id": self.issue_id, "text": self.text, "metadata": self.metadata}

    def to_request_json(self) -> dict[str, str]:
        return {"text": self.text}


@dataclass(frozen=True)
class SentryIssueCommentPublishResult:
    status_code: int | None
    comment_id: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]


class SentryIssueCommentPublisher:
    def __init__(
        self,
        *,
        organization_slug: str | None = None,
        issue_id: str | None = None,
        token: str | None = None,
        api_url: str = DEFAULT_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self.organization_slug = optional_text(organization_slug)
        self.issue_id = optional_text(issue_id)
        self.token = optional_text(token)
        self.api_url = required_url(api_url, "Sentry api_url must be an absolute http(s) URL")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> SentryIssueCommentPublisher:
        return cls(
            organization_slug=kwargs.pop("organization_slug", None) or os.getenv("SENTRY_ORG"),
            issue_id=kwargs.pop("issue_id", None) or os.getenv("SENTRY_ISSUE_ID"),
            token=kwargs.pop("token", None) or os.getenv("SENTRY_AUTH_TOKEN"),
            api_url=kwargs.pop("api_url", None) or os.getenv("SENTRY_API_URL", DEFAULT_API_URL),
            **kwargs,
        )

    def comments_endpoint(self, *, organization_slug: str | None = None, issue_id: str | None = None) -> str:
        org = required_text(optional_text(organization_slug) or self.organization_slug, "Sentry organization_slug is required; pass organization_slug or set SENTRY_ORG")
        issue = required_text(optional_text(issue_id) or self.issue_id, "Sentry issue_id is required; pass issue_id or set SENTRY_ISSUE_ID")
        return f"{self.api_url}/organizations/{quote(org, safe='')}/issues/{quote(issue, safe='')}/comments/"

    def build_comment_payload(self, unit: dict[str, Any], *, organization_slug: str | None = None, issue_id: str | None = None) -> SentryIssueCommentPayload:
        org = required_text(optional_text(organization_slug) or self.organization_slug, "Sentry organization_slug is required; pass organization_slug or set SENTRY_ORG")
        issue = required_text(optional_text(issue_id) or self.issue_id, "Sentry issue_id is required; pass issue_id or set SENTRY_ISSUE_ID")
        fields = _unit_fields(unit)
        metadata = {"publisher": "max.sentry_issue_comments", "idea_id": fields["idea_id"], "status": fields["status"], "category": fields["category"], "score": fields["score"]}
        return SentryIssueCommentPayload(org, issue, _comment_body(fields, unit), metadata)

    def publish(self, unit: dict[str, Any], *, dry_run: bool = True) -> SentryIssueCommentPublishResult:
        payload = self.build_comment_payload(unit)
        endpoint = self.comments_endpoint(organization_slug=payload.organization_slug, issue_id=payload.issue_id)
        payload_dict = payload.to_dict()
        if dry_run:
            return SentryIssueCommentPublishResult(None, None, True, endpoint, payload_dict)
        if not self.token:
            raise SentryIssueCommentPublishError("SENTRY_AUTH_TOKEN is required for live Sentry issue comment publishing; use dry_run to preview")
        response = self._post_with_retries(endpoint, payload.to_request_json())
        body = response_json(response, SentryIssueCommentPublishError, "Sentry issue comment publish failed: response was not valid JSON")
        return SentryIssueCommentPublishResult(response.status_code, optional_text(body.get("id")), False, endpoint, payload_dict)

    def _post_with_retries(self, endpoint: str, request_json: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response: httpx.Response | None = None
            for attempt in range(self.max_retries + 1):
                response = client.post(endpoint, json=request_json, headers=self._headers(), timeout=self.timeout)
                if response.status_code not in _RETRYABLE_STATUS_CODES or attempt >= self.max_retries:
                    break
            assert response is not None
            if not 200 <= response.status_code < 300:
                raise SentryIssueCommentPublishError(
                    f"Sentry issue comment publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.token])}",
                    status_code=response.status_code,
                    token=self.token,
                )
            return response
        finally:
            if close_client:
                client.close()

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {"Accept": "application/json", "Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "User-Agent": "max-sentry-issue-comments-publisher/1"}


SentryIssueCommentsPublisher = SentryIssueCommentPublisher


def _comment_body(fields: dict[str, str], unit: dict[str, Any]) -> str:
    execution = unit.get("execution") if isinstance(unit.get("execution"), dict) else {}
    evidence = unit.get("evidence") if isinstance(unit.get("evidence"), dict) else {}
    links = unit.get("evidence_links") or evidence.get("links") or []
    return "\n".join(
        [
            f"## Max idea: {fields['title']}",
            "",
            f"- Category: {fields['category']}",
            f"- Idea ID: {fields['idea_id']}",
            f"- Score: {fields['score']}",
            f"- Problem: {fields['problem']}",
            f"- Solution: {fields['solution']}",
            f"- Validation plan: {optional_text(execution.get('validation_plan')) or optional_text(unit.get('validation_plan')) or 'Not specified'}",
            f"- Evidence links: {join_list(links)}",
        ]
    )

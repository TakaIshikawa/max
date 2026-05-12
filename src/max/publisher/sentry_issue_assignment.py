"""Sentry issue assignment publisher."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from max.publisher._tact_spec_publish import (
    DEFAULT_TIMEOUT_SECONDS,
    optional_text,
    redact_text,
    required_text,
    required_url,
    response_json,
    response_preview,
)

DEFAULT_API_URL = "https://sentry.io/api/0"


class SentryIssueAssignmentPublishError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        token: str | None = None,
    ) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class SentryIssueAssignmentPayload:
    issue_id: str
    assignee: str
    status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {"issue_id": self.issue_id, "assignedTo": self.assignee}
        if self.status is not None:
            payload["status"] = self.status
        return payload

    def to_request_json(self) -> dict[str, str]:
        payload = {"assignedTo": self.assignee}
        if self.status is not None:
            payload["status"] = self.status
        return payload


@dataclass(frozen=True)
class SentryIssueAssignmentPublishResult:
    status_code: int | None
    issue_id: str
    assigned_to: str
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class SentryIssueAssignmentPublisher:
    def __init__(
        self,
        *,
        issue_id: str | None = None,
        assignee: str | None = None,
        status: str | None = None,
        token: str | None = None,
        api_url: str = DEFAULT_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.issue_id = optional_text(issue_id)
        self.assignee = optional_text(assignee)
        self.status = optional_text(status)
        self.token = optional_text(token)
        self.api_url = required_url(api_url, "Sentry api_url must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> SentryIssueAssignmentPublisher:
        return cls(
            issue_id=kwargs.pop("issue_id", None) or os.getenv("SENTRY_ISSUE_ID"),
            assignee=kwargs.pop("assignee", None) or os.getenv("SENTRY_ASSIGNEE"),
            status=kwargs.pop("status", None) or os.getenv("SENTRY_ISSUE_STATUS"),
            token=kwargs.pop("token", None) or os.getenv("SENTRY_AUTH_TOKEN"),
            api_url=kwargs.pop("api_url", None) or os.getenv("SENTRY_API_URL", DEFAULT_API_URL),
            **kwargs,
        )

    def issue_endpoint(self, *, issue_id: str | None = None) -> str:
        issue = required_text(
            optional_text(issue_id) or self.issue_id,
            "Sentry issue_id is required; pass issue_id or set SENTRY_ISSUE_ID",
        )
        return f"{self.api_url}/issues/{quote(issue, safe='')}/"

    def build_assignment_payload(
        self,
        *,
        issue_id: str | None = None,
        assignee: str | None = None,
        status: str | None = None,
    ) -> SentryIssueAssignmentPayload:
        issue = required_text(
            optional_text(issue_id) or self.issue_id,
            "Sentry issue_id is required; pass issue_id or set SENTRY_ISSUE_ID",
        )
        assigned_to = required_text(
            optional_text(assignee) or self.assignee,
            "Sentry assignee is required; pass assignee or set SENTRY_ASSIGNEE",
        )
        return SentryIssueAssignmentPayload(
            issue_id=issue,
            assignee=assigned_to,
            status=optional_text(status) or self.status,
        )

    def publish(
        self,
        *,
        dry_run: bool = True,
        issue_id: str | None = None,
        assignee: str | None = None,
        status: str | None = None,
    ) -> SentryIssueAssignmentPublishResult:
        payload = self.build_assignment_payload(
            issue_id=issue_id,
            assignee=assignee,
            status=status,
        )
        endpoint = self.issue_endpoint(issue_id=payload.issue_id)
        payload_dict = payload.to_dict()
        if dry_run:
            return SentryIssueAssignmentPublishResult(
                None, payload.issue_id, payload.assignee, True, endpoint, payload_dict
            )
        if not self.token:
            raise SentryIssueAssignmentPublishError(
                "SENTRY_AUTH_TOKEN is required for live Sentry issue assignment publishing; use dry_run to preview",
                token=self.token,
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.put(
                endpoint,
                json=payload.to_request_json(),
                headers=self._headers(),
                timeout=self.timeout,
            )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise SentryIssueAssignmentPublishError(
                f"Sentry issue assignment publish failed for {endpoint}: {exc}",
                token=self.token,
            ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise SentryIssueAssignmentPublishError(
                f"Sentry issue assignment publish failed with HTTP {response.status_code}: "
                f"{response_preview(response, secrets=[self.token])}",
                status_code=response.status_code,
                token=self.token,
            )
        response_body = response_json(
            response,
            SentryIssueAssignmentPublishError,
            "Sentry issue assignment publish failed: response was not valid JSON",
        )
        return SentryIssueAssignmentPublishResult(
            response.status_code,
            payload.issue_id,
            payload.assignee,
            False,
            endpoint,
            payload_dict,
            response_body,
        )

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "max-sentry-issue-assignment-publisher/1",
        }


SentryIssueAssignmentsPublisher = SentryIssueAssignmentPublisher

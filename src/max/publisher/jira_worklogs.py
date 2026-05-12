"""Jira Cloud worklog publisher for Max validation and planning summaries."""

from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from max.publisher.jira_issues import _adf_document

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_TIME_SPENT_SECONDS = 1800


class JiraWorklogPublishError(RuntimeError):
    """Raised when a Jira worklog publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None, secrets: list[str | None] | None = None) -> None:
        super().__init__(_redact_text(message, secrets=secrets))
        self.status_code = status_code


@dataclass(frozen=True)
class JiraWorklogPublishResult:
    """Summary of a Jira worklog publish or dry run."""

    status_code: int | None
    issue_key: str
    worklog_id: str | None
    worklog_url: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]


class JiraWorklogPublisher:
    """Build and optionally create Jira worklog entries from Max payloads."""

    def __init__(
        self,
        base_url: str,
        *,
        issue_key: str | None = None,
        account_id: str | None = None,
        started: str | None = None,
        time_spent_seconds: int = DEFAULT_TIME_SPENT_SECONDS,
        auth_email: str | None = None,
        api_token: str | None = None,
        bearer_token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = _required_url(base_url)
        self.issue_key = _optional_text(issue_key)
        self.account_id = _optional_text(account_id)
        self.started = _optional_text(started)
        self.time_spent_seconds = int(time_spent_seconds)
        self.auth_email = _optional_text(auth_email)
        self.api_token = _optional_text(api_token)
        self.bearer_token = _optional_text(bearer_token)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        base_url: str | None = None,
        issue_key: str | None = None,
        account_id: str | None = None,
        started: str | None = None,
        time_spent_seconds: int | None = None,
        auth_email: str | None = None,
        api_token: str | None = None,
        bearer_token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> JiraWorklogPublisher:
        resolved_base_url = base_url or os.getenv("JIRA_SITE_URL") or os.getenv("JIRA_BASE_URL")
        if not resolved_base_url:
            raise JiraWorklogPublishError("Jira base_url is required; pass base_url or set JIRA_SITE_URL")
        return cls(
            resolved_base_url,
            issue_key=issue_key or os.getenv("JIRA_ISSUE_KEY"),
            account_id=account_id or os.getenv("JIRA_ACCOUNT_ID"),
            started=started or os.getenv("JIRA_WORKLOG_STARTED"),
            time_spent_seconds=time_spent_seconds or int(os.getenv("JIRA_WORKLOG_TIME_SPENT_SECONDS", str(DEFAULT_TIME_SPENT_SECONDS))),
            auth_email=auth_email or os.getenv("JIRA_EMAIL"),
            api_token=api_token or os.getenv("JIRA_API_TOKEN"),
            bearer_token=bearer_token or os.getenv("JIRA_BEARER_TOKEN"),
            timeout=timeout,
            client=client,
        )

    def worklog_endpoint(self, issue_key: str | None = None) -> str:
        resolved = self._resolve_issue_key(issue_key)
        return f"{self.base_url}/rest/api/3/issue/{quote(resolved)}/worklog"

    def build_worklog_payload(
        self,
        payload: dict[str, Any] | str,
        *,
        issue_key: str | None = None,
        started: str | None = None,
        time_spent_seconds: int | None = None,
    ) -> dict[str, Any]:
        resolved_issue_key = self._resolve_issue_key(issue_key)
        seconds = int(time_spent_seconds if time_spent_seconds is not None else self.time_spent_seconds)
        if seconds <= 0:
            raise JiraWorklogPublishError("Jira worklog time_spent_seconds must be positive", secrets=self._secrets)
        rendered = _render_comment(payload)
        worklog = {
            "issue_key": resolved_issue_key,
            "timeSpentSeconds": seconds,
            "started": _started_text(started or self.started),
            "comment": rendered,
            "metadata": _metadata(payload, issue_key=resolved_issue_key, account_id=self.account_id),
        }
        return worklog

    def publish(
        self,
        payload: dict[str, Any] | str,
        *,
        dry_run: bool = True,
        issue_key: str | None = None,
        started: str | None = None,
        time_spent_seconds: int | None = None,
    ) -> JiraWorklogPublishResult:
        worklog = self.build_worklog_payload(
            payload,
            issue_key=issue_key,
            started=started,
            time_spent_seconds=time_spent_seconds,
        )
        endpoint = self.worklog_endpoint(worklog["issue_key"])
        if dry_run:
            return JiraWorklogPublishResult(None, worklog["issue_key"], None, None, True, endpoint, worklog)
        if not self._has_auth:
            raise JiraWorklogPublishError(
                "Jira auth_email/api_token or bearer_token is required for live Jira worklog publishing; use dry_run to preview",
                secrets=self._secrets,
            )
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(
                endpoint,
                json=_jira_worklog_request(worklog),
                headers=self._headers(),
                timeout=self.timeout,
            )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise JiraWorklogPublishError(f"Jira worklog publish failed for {endpoint}: {exc}", secrets=self._secrets) from exc
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise JiraWorklogPublishError(
                f"Jira worklog publish failed with HTTP {response.status_code}: {_response_body_preview(response, secrets=self._secrets)}",
                status_code=response.status_code,
                secrets=self._secrets,
            )
        body = _json_response(response, secrets=self._secrets)
        worklog_id = _optional_text(body.get("id"))
        worklog_url = _optional_text(body.get("self")) or (f"{endpoint}/{worklog_id}" if worklog_id else None)
        return JiraWorklogPublishResult(response.status_code, worklog["issue_key"], worklog_id, worklog_url, False, endpoint, worklog)

    @property
    def _has_auth(self) -> bool:
        return bool(self.bearer_token or (self.auth_email and self.api_token))

    @property
    def _secrets(self) -> list[str | None]:
        return [self.bearer_token, self.api_token]

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "max-jira-worklogs-publisher/1",
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        else:
            assert self.auth_email is not None and self.api_token is not None
            credentials = f"{self.auth_email}:{self.api_token}".encode("utf-8")
            headers["Authorization"] = f"Basic {base64.b64encode(credentials).decode('ascii')}"
        return headers

    def _resolve_issue_key(self, issue_key: str | None = None) -> str:
        return _required_text(issue_key or self.issue_key, "Jira issue_key is required; pass issue_key or set JIRA_ISSUE_KEY")


def publish_jira_worklog(
    payload: dict[str, Any] | str,
    *,
    base_url: str | None = None,
    issue_key: str | None = None,
    account_id: str | None = None,
    started: str | None = None,
    time_spent_seconds: int | None = None,
    auth_email: str | None = None,
    api_token: str | None = None,
    bearer_token: str | None = None,
    dry_run: bool = True,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    client: httpx.Client | None = None,
) -> JiraWorklogPublishResult:
    """Create a Jira worklog entry from a Max payload."""
    return JiraWorklogPublisher.from_env(
        base_url=base_url,
        issue_key=issue_key,
        account_id=account_id,
        started=started,
        time_spent_seconds=time_spent_seconds,
        auth_email=auth_email,
        api_token=api_token,
        bearer_token=bearer_token,
        timeout=timeout,
        client=client,
    ).publish(payload, dry_run=dry_run)


def _jira_worklog_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "timeSpentSeconds": payload["timeSpentSeconds"],
        "started": payload["started"],
        "comment": _adf_document(payload["comment"]),
    }


def _render_comment(payload: dict[str, Any] | str) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if _is_design_brief_payload(payload):
        brief = _dict_value(payload, "design_brief")
        return "\n".join(
            [
                f"## {_text(brief.get('title'), brief.get('id'), 'Design brief')}",
                _text(brief.get("summary"), brief.get("merged_product_concept"), "No summary provided."),
                f"Brief ID: {_text(brief.get('id'), 'Not specified')}",
                f"Readiness: {_score_text(brief.get('readiness_score'))}",
                f"Recommendation: {_text(brief.get('recommendation') or brief.get('status_recommendation'), 'Not specified')}",
                f"Source ideas: {_comma_list(_string_list(brief.get('source_idea_ids')))}",
            ]
        )
    source = _dict_value(payload, "source")
    project = _dict_value(payload, "project")
    execution = _dict_value(payload, "execution")
    evaluation = _dict_value(payload, "evaluation")
    return "\n".join(
        [
            f"## {_text(project.get('title'), source.get('idea_id'), 'Max idea')}",
            _text(project.get("summary"), "No summary provided."),
            f"Idea ID: {_text(source.get('idea_id'), 'Not specified')}",
            f"Score: {_score_text(evaluation.get('overall_score'))}",
            f"Recommendation: {_text(evaluation.get('recommendation'), 'Not specified')}",
            f"Validation: {_text(execution.get('validation_plan'), 'Not specified')}",
        ]
    )


def _metadata(payload: dict[str, Any] | str, *, issue_key: str, account_id: str | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"publisher": "max.jira_worklogs", "source_type": "text", "issue_key": issue_key, "account_id": account_id}
    source = _dict_value(payload, "source")
    brief = _dict_value(payload, "design_brief")
    return {
        "publisher": "max.jira_worklogs",
        "source_system": source.get("system", "max"),
        "source_type": "design_brief" if brief else source.get("type", "idea"),
        "idea_id": source.get("idea_id"),
        "design_brief_id": brief.get("id") or source.get("design_brief_id"),
        "issue_key": issue_key,
        "account_id": account_id,
    }


def _started_text(value: str | None) -> str:
    if value:
        return value
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000%z")


def _is_design_brief_payload(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("design_brief"), dict)


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _string_list(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    return [_text(item, "") for item in items if _text(item, "")]


def _comma_list(items: list[str]) -> str:
    return ", ".join(items) if items else "None"


def _text(*values: object) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _required_text(value: object, message: str) -> str:
    text = _text(value)
    if not text:
        raise JiraWorklogPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = _text(value)
    return text or None


def _score_text(value: object) -> str:
    if isinstance(value, int | float):
        return f"{value:.1f}"
    return _text(value, "Not specified")


def _required_url(value: object) -> str:
    raw = _required_text(value, "Jira base_url is required").rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise JiraWorklogPublishError("Jira base_url must be an absolute http(s) URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _json_response(response: httpx.Response, *, secrets: list[str | None]) -> dict[str, Any]:
    if not response.content:
        return {}
    try:
        body = response.json()
    except ValueError as exc:
        raise JiraWorklogPublishError("Jira worklog response was not valid JSON", status_code=response.status_code, secrets=secrets) from exc
    return body if isinstance(body, dict) else {}


def _response_body_preview(response: httpx.Response, *, secrets: list[str | None], limit: int = 500) -> str:
    text = _redact_text(response.text.strip(), secrets=secrets)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _redact_text(text: str, *, secrets: list[str | None] | None = None) -> str:
    redacted = text
    for secret in secrets or []:
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    return re.sub(r"(?i)\b(token|password|authorization|client_secret)\b([=:]\s*)[^&\s,'\"}]+", r"\1\2<redacted>", redacted)

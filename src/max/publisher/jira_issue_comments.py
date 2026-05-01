"""Jira Cloud issue comment publisher for generated specs and design briefs."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from max.publisher.jira_issues import _adf_document


DEFAULT_TIMEOUT_SECONDS = 10.0


class JiraIssueCommentPublishError(RuntimeError):
    """Raised when a Jira issue comment publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class JiraIssueCommentPayload:
    """Jira issue comment payload plus Max-specific metadata."""

    body: str
    issue_key: str
    metadata: dict[str, Any]
    visibility_type: str | None = None
    visibility_value: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable issue comment payload."""
        payload: dict[str, Any] = {
            "body": self.body,
            "issue_key": self.issue_key,
            "metadata": self.metadata,
        }
        if self.visibility_type and self.visibility_value:
            payload["visibility"] = {
                "type": self.visibility_type,
                "value": self.visibility_value,
            }
        return payload


@dataclass(frozen=True)
class JiraIssueCommentPublishResult:
    """Summary of a Jira issue comment publish or dry run."""

    status_code: int | None
    issue_key: str
    comment_id: str | None
    comment_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class JiraIssueCommentPublisher:
    """Build and optionally append generated artifacts to existing Jira issues."""

    def __init__(
        self,
        base_url: str,
        *,
        issue_key: str | None = None,
        auth_email: str | None = None,
        api_token: str | None = None,
        bearer_token: str | None = None,
        visibility_type: str | None = None,
        visibility_value: str | None = None,
        artifact_title: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = _required_url(base_url)
        self.issue_key = _optional_text(issue_key)
        self.auth_email = _optional_text(auth_email)
        self.api_token = _optional_text(api_token)
        self.bearer_token = _optional_text(bearer_token)
        self.visibility_type = _optional_text(visibility_type)
        self.visibility_value = _optional_text(visibility_value)
        self.artifact_title = _optional_text(artifact_title)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        base_url: str | None = None,
        issue_key: str | None = None,
        auth_email: str | None = None,
        api_token: str | None = None,
        bearer_token: str | None = None,
        visibility_type: str | None = None,
        visibility_value: str | None = None,
        artifact_title: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> JiraIssueCommentPublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_base_url = base_url or os.getenv("JIRA_SITE_URL") or os.getenv("JIRA_BASE_URL")
        if not resolved_base_url:
            raise JiraIssueCommentPublishError(
                "Jira base_url is required; pass base_url or set JIRA_SITE_URL"
            )
        return cls(
            resolved_base_url,
            issue_key=issue_key or os.getenv("JIRA_ISSUE_KEY"),
            auth_email=auth_email or os.getenv("JIRA_EMAIL"),
            api_token=api_token or os.getenv("JIRA_API_TOKEN"),
            bearer_token=bearer_token or os.getenv("JIRA_BEARER_TOKEN"),
            visibility_type=visibility_type or os.getenv("JIRA_COMMENT_VISIBILITY_TYPE"),
            visibility_value=visibility_value or os.getenv("JIRA_COMMENT_VISIBILITY_VALUE"),
            artifact_title=artifact_title or os.getenv("JIRA_ARTIFACT_TITLE"),
            timeout=timeout,
            client=client,
        )

    def comment_endpoint(self, issue_key: str | None = None) -> str:
        """Return the Jira REST endpoint used for issue comment creation."""
        resolved_issue_key = self._resolve_issue_key(issue_key)
        return f"{self.base_url}/rest/api/3/issue/{resolved_issue_key}/comment"

    def build_comment_payload(
        self,
        artifact: dict[str, Any] | str,
        *,
        issue_key: str | None = None,
        body: str | None = None,
        markdown: str | None = None,
        artifact_title: str | None = None,
    ) -> JiraIssueCommentPayload:
        """Convert generated text or an artifact dictionary into a Jira comment payload."""
        resolved_issue_key = self._resolve_issue_key(issue_key)
        rendered_body = _comment_body(
            artifact,
            body=body,
            markdown=markdown,
            artifact_title=artifact_title or self.artifact_title,
        )
        metadata = _metadata(artifact, issue_key=resolved_issue_key)
        return JiraIssueCommentPayload(
            body=rendered_body,
            issue_key=resolved_issue_key,
            metadata=metadata,
            visibility_type=self.visibility_type,
            visibility_value=self.visibility_value,
        )

    def publish(
        self,
        artifact: dict[str, Any] | str,
        *,
        dry_run: bool = True,
        issue_key: str | None = None,
        body: str | None = None,
        markdown: str | None = None,
        artifact_title: str | None = None,
    ) -> JiraIssueCommentPublishResult:
        """Build the comment payload and optionally append it to a Jira issue."""
        payload = self.build_comment_payload(
            artifact,
            issue_key=issue_key,
            body=body,
            markdown=markdown,
            artifact_title=artifact_title,
        ).to_dict()
        return self.publish_comment_payload(payload, dry_run=dry_run)

    def publish_comment_payload(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> JiraIssueCommentPublishResult:
        """Publish a caller-rendered Jira issue comment payload."""
        issue_key = _required_text(
            payload.get("issue_key") or self.issue_key,
            "Jira issue_key is required; pass issue_key or set JIRA_ISSUE_KEY",
        )
        comment_payload = {
            **payload,
            "issue_key": issue_key,
            "metadata": payload.get("metadata") or {},
        }
        if dry_run:
            return JiraIssueCommentPublishResult(
                status_code=None,
                issue_key=issue_key,
                comment_id=None,
                comment_url=None,
                dry_run=True,
                payload=comment_payload,
            )

        if not self._has_auth:
            raise JiraIssueCommentPublishError(
                "Jira auth_email/api_token or bearer_token is required for live Jira issue "
                "comment publishing; use dry_run to preview"
            )

        endpoint = self.comment_endpoint(issue_key)
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    endpoint,
                    json=_jira_comment_request(comment_payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise JiraIssueCommentPublishError(
                    f"Jira issue comment publish failed for {endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise JiraIssueCommentPublishError(
                f"Jira issue comment publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        comment_id = body.get("id")
        if not comment_id:
            raise JiraIssueCommentPublishError(
                "Jira issue comment publish failed: response did not include created comment id",
                status_code=response.status_code,
            )

        comment_url = self.comment_url(issue_key, str(comment_id))
        return JiraIssueCommentPublishResult(
            status_code=response.status_code,
            issue_key=issue_key,
            comment_id=str(comment_id),
            comment_url=comment_url,
            dry_run=False,
            payload={
                **comment_payload,
                "metadata": {
                    **comment_payload["metadata"],
                    "jira_issue_comment_id": str(comment_id),
                    "jira_issue_comment_url": comment_url,
                },
            },
        )

    def comment_url(self, issue_key: str, comment_id: str) -> str:
        """Return a browsable Jira URL focused on the created comment."""
        return f"{self.base_url}/browse/{issue_key}?focusedCommentId={comment_id}"

    @property
    def _has_auth(self) -> bool:
        return bool(self.bearer_token or (self.auth_email and self.api_token))

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "max-jira-issue-comments-publisher/1",
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        else:
            assert self.auth_email is not None and self.api_token is not None
            credentials = f"{self.auth_email}:{self.api_token}".encode("utf-8")
            headers["Authorization"] = f"Basic {base64.b64encode(credentials).decode('ascii')}"
        return headers

    def _resolve_issue_key(self, issue_key: str | None = None) -> str:
        return _required_text(
            issue_key or self.issue_key,
            "Jira issue_key is required; pass issue_key or set JIRA_ISSUE_KEY",
        )


JiraIssueCommentsPublisher = JiraIssueCommentPublisher


def _jira_comment_request(payload: dict[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {"body": _adf_document(payload["body"])}
    visibility = payload.get("visibility")
    if isinstance(visibility, dict) and visibility.get("type") and visibility.get("value"):
        request["visibility"] = {
            "type": str(visibility["type"]),
            "value": str(visibility["value"]),
        }
    return request


def _comment_body(
    artifact: dict[str, Any] | str,
    *,
    body: str | None,
    markdown: str | None,
    artifact_title: str | None,
) -> str:
    explicit = _optional_text(body) or _optional_text(markdown)
    if explicit:
        return explicit
    if isinstance(artifact, str):
        return artifact.strip()
    title = _optional_text(artifact_title) or _artifact_title(artifact)
    return "\n".join([f"## {title}", "", _artifact_summary(artifact)])


def _artifact_title(artifact: dict[str, Any]) -> str:
    project = _dict_value(artifact, "project")
    source = _dict_value(artifact, "source")
    return _text_or_placeholder(
        project.get("title")
        or artifact.get("title")
        or source.get("idea_id")
        or "Generated Artifact"
    )


def _artifact_summary(artifact: dict[str, Any]) -> str:
    project = _dict_value(artifact, "project")
    source = _dict_value(artifact, "source")
    lines = [
        _text_or_placeholder(project.get("summary") or artifact.get("summary")),
        "",
        "### Source",
        f"- Idea ID: {_text_or_placeholder(source.get('idea_id'))}",
        f"- Kind: {_text_or_placeholder(artifact.get('kind'))}",
        f"- Schema: {_text_or_placeholder(artifact.get('schema_version'))}",
    ]
    return "\n".join(lines)


def _metadata(artifact: dict[str, Any] | str, *, issue_key: str) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        return {
            "publisher": "max.jira_issue_comments",
            "source_system": "max",
            "source_type": "text",
            "issue_key": issue_key,
        }
    source = _dict_value(artifact, "source")
    return {
        "publisher": "max.jira_issue_comments",
        "source_system": source.get("system", "max"),
        "source_type": source.get("type", "artifact"),
        "idea_id": source.get("idea_id"),
        "schema_version": artifact.get("schema_version"),
        "kind": artifact.get("kind"),
        "issue_key": issue_key,
    }


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise JiraIssueCommentPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _text_or_placeholder(value: object) -> str:
    text = str(value).strip() if value else ""
    return text or "Not specified"


def _required_url(value: object) -> str:
    raw = _required_text(value, "Jira base_url is required").rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise JiraIssueCommentPublishError("Jira base_url must be an absolute http(s) URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise JiraIssueCommentPublishError(
            "Jira issue comment publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    return body if isinstance(body, dict) else {}

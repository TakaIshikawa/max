"""Linear issue comment publisher for generated artifacts and review notes."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from max.publisher.linear_issues import DEFAULT_LINEAR_GRAPHQL_URL, DEFAULT_TIMEOUT_SECONDS


class LinearIssueCommentPublishError(RuntimeError):
    """Raised when a Linear issue comment publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class LinearIssueCommentPayload:
    """Linear issue comment payload plus Max-specific metadata."""

    body: str
    issue_id: str | None
    issue_key: str | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable issue comment payload preview."""
        payload: dict[str, Any] = {
            "body": self.body,
            "metadata": self.metadata,
        }
        if self.issue_id:
            payload["issue_id"] = self.issue_id
        if self.issue_key:
            payload["issue_key"] = self.issue_key
        return payload


@dataclass(frozen=True)
class LinearIssueCommentPublishResult:
    """Summary of a Linear issue comment publish or dry run."""

    status_code: int | None
    issue_id: str | None
    issue_key: str | None
    comment_id: str | None
    comment_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class LinearIssueCommentPublisher:
    """Build and optionally append generated artifacts to existing Linear issues."""

    def __init__(
        self,
        *,
        issue_id: str | None = None,
        issue_key: str | None = None,
        api_key: str | None = None,
        api_url: str = DEFAULT_LINEAR_GRAPHQL_URL,
        artifact_title: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.issue_id = _optional_text(issue_id)
        self.issue_key = _optional_text(issue_key)
        self.api_key = _optional_text(api_key)
        self.api_url = _required_url(api_url)
        self.artifact_title = _optional_text(artifact_title)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        issue_id: str | None = None,
        issue_key: str | None = None,
        api_key: str | None = None,
        api_url: str | None = None,
        artifact_title: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> LinearIssueCommentPublisher:
        """Create a publisher using API values first, then environment variables."""
        return cls(
            issue_id=issue_id or os.getenv("LINEAR_ISSUE_ID"),
            issue_key=issue_key or os.getenv("LINEAR_ISSUE_KEY"),
            api_key=api_key or os.getenv("LINEAR_API_KEY"),
            api_url=api_url or os.getenv("LINEAR_API_URL", DEFAULT_LINEAR_GRAPHQL_URL),
            artifact_title=artifact_title or os.getenv("LINEAR_ARTIFACT_TITLE"),
            timeout=timeout,
            client=client,
        )

    @property
    def graphql_endpoint(self) -> str:
        """Return the Linear GraphQL endpoint used for comment creation."""
        return self.api_url

    @property
    def has_auth(self) -> bool:
        """Return whether live Linear issue comment publishing has credentials."""
        return bool(self.api_key)

    def build_comment_payload(
        self,
        artifact: dict[str, Any] | str,
        *,
        issue_id: str | None = None,
        issue_key: str | None = None,
        body: str | None = None,
        markdown: str | None = None,
        artifact_title: str | None = None,
    ) -> LinearIssueCommentPayload:
        """Convert generated text or an artifact dictionary into a Linear comment payload."""
        resolved_issue_id = _optional_text(issue_id) or self.issue_id
        resolved_issue_key = _optional_text(issue_key) or self.issue_key
        _resolve_issue_identifier(resolved_issue_id, resolved_issue_key)
        return LinearIssueCommentPayload(
            body=_comment_body(
                artifact,
                body=body,
                markdown=markdown,
                artifact_title=artifact_title or self.artifact_title,
            ),
            issue_id=resolved_issue_id,
            issue_key=resolved_issue_key,
            metadata=_metadata(
                artifact,
                issue_id=resolved_issue_id,
                issue_key=resolved_issue_key,
            ),
        )

    def publish(
        self,
        artifact: dict[str, Any] | str,
        *,
        dry_run: bool = True,
        issue_id: str | None = None,
        issue_key: str | None = None,
        body: str | None = None,
        markdown: str | None = None,
        artifact_title: str | None = None,
    ) -> LinearIssueCommentPublishResult:
        """Build the comment payload and optionally append it to a Linear issue."""
        payload = self.build_comment_payload(
            artifact,
            issue_id=issue_id,
            issue_key=issue_key,
            body=body,
            markdown=markdown,
            artifact_title=artifact_title,
        ).to_dict()
        return self.publish_comment(payload, dry_run=dry_run)

    def publish_comment(
        self,
        payload: LinearIssueCommentPayload | dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> LinearIssueCommentPublishResult:
        """Publish a caller-rendered Linear issue comment payload."""
        payload_dict = payload.to_dict() if isinstance(payload, LinearIssueCommentPayload) else dict(payload)
        issue_id = _optional_text(payload_dict.get("issue_id")) or self.issue_id
        issue_key = _optional_text(payload_dict.get("issue_key")) or self.issue_key
        issue_identifier = _resolve_issue_identifier(issue_id, issue_key)
        comment_payload = {
            **payload_dict,
            "body": _required_text(payload_dict.get("body"), "Linear comment body is required"),
            "metadata": payload_dict.get("metadata") or {},
        }
        if issue_id:
            comment_payload["issue_id"] = issue_id
        if issue_key:
            comment_payload["issue_key"] = issue_key
        request_json = _graphql_request(comment_payload)

        if dry_run:
            return LinearIssueCommentPublishResult(
                status_code=None,
                issue_id=issue_id,
                issue_key=issue_key,
                comment_id=None,
                comment_url=None,
                dry_run=True,
                payload={
                    **comment_payload,
                    "request": {
                        "method": "POST",
                        "url": self.graphql_endpoint,
                        "json": request_json,
                    },
                },
            )

        if not self.has_auth:
            raise LinearIssueCommentPublishError(
                "LINEAR_API_KEY is required for live Linear issue comment publishing; "
                "use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.graphql_endpoint,
                    json=request_json,
                    headers={
                        "Authorization": self.api_key,
                        "Content-Type": "application/json",
                        "User-Agent": "max-linear-issue-comments-publisher/1",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise LinearIssueCommentPublishError(
                    f"Linear issue comment publish failed for {self.graphql_endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise LinearIssueCommentPublishError(
                f"Linear issue comment publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response, self.api_key)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        errors = body.get("errors")
        if isinstance(errors, list) and errors:
            raise LinearIssueCommentPublishError(
                "Linear issue comment publish failed: "
                f"{_graphql_errors_preview(errors, self.api_key)}",
                status_code=response.status_code,
            )

        comment = _comment_from_response(body)
        if not comment:
            raise LinearIssueCommentPublishError(
                "Linear issue comment publish failed: response did not include created comment",
                status_code=response.status_code,
            )

        comment_id = str(comment["id"])
        comment_url = _optional_text(comment.get("url"))
        issue = comment.get("issue") if isinstance(comment.get("issue"), dict) else {}
        response_issue_id = _optional_text(issue.get("id")) or issue_id
        response_issue_key = _optional_text(issue.get("identifier")) or issue_key
        return LinearIssueCommentPublishResult(
            status_code=response.status_code,
            issue_id=response_issue_id,
            issue_key=response_issue_key,
            comment_id=comment_id,
            comment_url=comment_url,
            dry_run=False,
            payload={
                **comment_payload,
                "issue_id": response_issue_id,
                "issue_key": response_issue_key,
                "metadata": {
                    **comment_payload["metadata"],
                    "linear_issue_id": response_issue_id,
                    "linear_issue_identifier": response_issue_key,
                    "linear_issue_comment_id": comment_id,
                    "linear_issue_comment_url": comment_url,
                    "linear_issue_identifier_input": issue_identifier,
                },
            },
        )


LinearIssueCommentsPublisher = LinearIssueCommentPublisher


COMMENT_CREATE_MUTATION = """
mutation MaxCommentCreate($input: CommentCreateInput!) {
  commentCreate(input: $input) {
    success
    comment {
      id
      url
      issue {
        id
        identifier
        url
      }
    }
  }
}
""".strip()


def build_comment_payload(
    artifact: dict[str, Any] | str,
    *,
    issue_id: str | None = None,
    issue_key: str | None = None,
    body: str | None = None,
    markdown: str | None = None,
    artifact_title: str | None = None,
) -> LinearIssueCommentPayload:
    """Build a Linear issue comment payload without constructing a publisher."""
    return LinearIssueCommentPublisher(
        issue_id=issue_id,
        issue_key=issue_key,
        artifact_title=artifact_title,
    ).build_comment_payload(artifact, body=body, markdown=markdown)


def publish_comment(
    payload: LinearIssueCommentPayload | dict[str, Any],
    *,
    dry_run: bool = True,
    api_key: str | None = None,
    api_url: str = DEFAULT_LINEAR_GRAPHQL_URL,
    client: httpx.Client | None = None,
) -> LinearIssueCommentPublishResult:
    """Publish a prebuilt Linear issue comment payload."""
    return LinearIssueCommentPublisher(
        api_key=api_key,
        api_url=api_url,
        client=client,
    ).publish_comment(payload, dry_run=dry_run)


def _graphql_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "query": COMMENT_CREATE_MUTATION,
        "variables": {
            "input": {
                "issueId": _resolve_issue_identifier(
                    _optional_text(payload.get("issue_id")),
                    _optional_text(payload.get("issue_key")),
                ),
                "body": _required_text(payload.get("body"), "Linear comment body is required"),
            }
        },
    }


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
        return _required_text(artifact, "Linear comment body is required")
    title = _optional_text(artifact_title) or _artifact_title(artifact)
    return "\n".join([f"## {title}", "", _artifact_summary(artifact)])


def _artifact_title(artifact: dict[str, Any]) -> str:
    project = _dict_value(artifact, "project")
    source = _dict_value(artifact, "source")
    return _text_or_placeholder(
        project.get("title")
        or artifact.get("title")
        or source.get("idea_id")
        or source.get("design_brief_id")
        or "Generated Artifact"
    )


def _artifact_summary(artifact: dict[str, Any]) -> str:
    project = _dict_value(artifact, "project")
    source = _dict_value(artifact, "source")
    summary = project.get("summary") or artifact.get("summary")
    lines = [
        _text_or_placeholder(summary),
        "",
        f"- Kind: {_text_or_placeholder(artifact.get('kind'))}",
        f"- Schema version: {_text_or_placeholder(artifact.get('schema_version'))}",
    ]
    if source.get("idea_id"):
        lines.append(f"- Idea ID: {source['idea_id']}")
    if source.get("design_brief_id"):
        lines.append(f"- Design brief ID: {source['design_brief_id']}")
    return "\n".join(lines)


def _metadata(
    artifact: dict[str, Any] | str,
    *,
    issue_id: str | None,
    issue_key: str | None,
) -> dict[str, Any]:
    base = {
        "publisher": "max.linear_issue_comments",
        "issue_id": issue_id,
        "issue_key": issue_key,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if not isinstance(artifact, dict):
        return {
            **base,
            "source_system": "max",
            "source_type": "text",
        }
    source = _dict_value(artifact, "source")
    return {
        **base,
        "source_system": source.get("system", "max"),
        "source_type": source.get("type", "artifact"),
        "idea_id": source.get("idea_id"),
        "design_brief_id": source.get("design_brief_id"),
        "schema_version": artifact.get("schema_version"),
        "kind": artifact.get("kind"),
    }


def _resolve_issue_identifier(issue_id: str | None, issue_key: str | None) -> str:
    return _required_text(
        issue_id or issue_key,
        "Linear issue_id or issue_key is required; pass one or set LINEAR_ISSUE_ID "
        "or LINEAR_ISSUE_KEY",
    )


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise LinearIssueCommentPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _text_or_placeholder(value: object) -> str:
    text = str(value).strip() if value else ""
    return text or "Not specified"


def _required_url(value: object) -> str:
    url = _required_text(value, "Linear api_url is required").rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise LinearIssueCommentPublishError("Linear api_url must be an absolute http(s) URL")
    return url


def _response_body_preview(
    response: httpx.Response,
    api_key: str | None,
    *,
    limit: int = 500,
) -> str:
    text = _redact_text(response.text.strip(), api_key)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise LinearIssueCommentPublishError(
            "Linear issue comment publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    return body if isinstance(body, dict) else {}


def _graphql_errors_preview(errors: list[Any], api_key: str | None) -> str:
    messages: list[str] = []
    for error in errors:
        if isinstance(error, dict) and error.get("message"):
            messages.append(str(error["message"]))
        elif error:
            messages.append(str(error))
    return _redact_text("; ".join(messages) or "unknown GraphQL error", api_key)


def _comment_from_response(body: dict[str, Any]) -> dict[str, Any] | None:
    data = body.get("data")
    if not isinstance(data, dict):
        return None
    result = data.get("commentCreate")
    if not isinstance(result, dict) or result.get("success") is False:
        return None
    comment = result.get("comment")
    if not isinstance(comment, dict) or not comment.get("id"):
        return None
    return comment


def _redact_text(text: str, api_key: str | None) -> str:
    secret = _optional_text(api_key)
    if not secret:
        return text
    return text.replace(secret, "[REDACTED]")

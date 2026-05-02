"""Bitbucket Cloud issue comment publisher for generated artifacts and review notes."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx


DEFAULT_BITBUCKET_API_URL = "https://api.bitbucket.org/2.0"
DEFAULT_TIMEOUT_SECONDS = 10.0


class BitbucketIssueCommentPublishError(RuntimeError):
    """Raised when a Bitbucket issue comment publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class BitbucketIssueCommentPayload:
    """Bitbucket issue comment payload plus Max-specific metadata."""

    body: str
    workspace: str
    repository: str
    issue_id: int
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable issue comment payload."""
        return {
            "body": self.body,
            "workspace": self.workspace,
            "repository": self.repository,
            "issue_id": self.issue_id,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class BitbucketIssueCommentPublishResult:
    """Summary of a Bitbucket issue comment publish or dry run."""

    status_code: int | None
    workspace: str
    repository: str
    issue_id: int
    comment_id: str | None
    comment_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class BitbucketIssueCommentPublisher:
    """Build and optionally append generated artifacts to existing Bitbucket issues."""

    def __init__(
        self,
        workspace: str,
        repository: str,
        *,
        issue_id: int | str | None = None,
        username: str | None = None,
        app_password: str | None = None,
        api_url: str = DEFAULT_BITBUCKET_API_URL,
        artifact_title: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.workspace = _required_slug(workspace, "Bitbucket workspace is required")
        self.repository = _required_slug(repository, "Bitbucket repository is required")
        self.issue_id = _issue_id(issue_id) if issue_id is not None else None
        self.username = _optional_text(username)
        self.app_password = _optional_text(app_password)
        self.api_url = _required_url(api_url)
        self.artifact_title = _optional_text(artifact_title)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        workspace: str | None = None,
        repository: str | None = None,
        issue_id: int | str | None = None,
        username: str | None = None,
        app_password: str | None = None,
        api_url: str | None = None,
        artifact_title: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> BitbucketIssueCommentPublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_workspace = workspace or os.getenv("BITBUCKET_WORKSPACE")
        if not resolved_workspace:
            raise BitbucketIssueCommentPublishError(
                "Bitbucket workspace is required; pass workspace or set BITBUCKET_WORKSPACE"
            )
        resolved_repository = repository or os.getenv("BITBUCKET_REPOSITORY")
        if not resolved_repository:
            raise BitbucketIssueCommentPublishError(
                "Bitbucket repository is required; pass repository or set BITBUCKET_REPOSITORY"
            )
        return cls(
            resolved_workspace,
            resolved_repository,
            issue_id=issue_id or os.getenv("BITBUCKET_ISSUE_ID"),
            username=username or os.getenv("BITBUCKET_USERNAME"),
            app_password=app_password or os.getenv("BITBUCKET_APP_PASSWORD"),
            api_url=api_url
            or os.getenv("BITBUCKET_API_URL")
            or os.getenv("BITBUCKET_BASE_URL")
            or DEFAULT_BITBUCKET_API_URL,
            artifact_title=artifact_title or os.getenv("BITBUCKET_ARTIFACT_TITLE"),
            timeout=timeout,
            client=client,
        )

    def comment_endpoint(self, issue_id: int | str | None = None) -> str:
        """Return the Bitbucket REST endpoint used for issue comment creation."""
        resolved_issue_id = self._resolve_issue_id(issue_id)
        workspace = quote(self.workspace, safe="")
        repository = quote(self.repository, safe="")
        return (
            f"{self.api_url}/repositories/{workspace}/{repository}"
            f"/issues/{resolved_issue_id}/comments"
        )

    def build_comment_payload(
        self,
        artifact: dict[str, Any] | str,
        *,
        issue_id: int | str | None = None,
        body: str | None = None,
        markdown: str | None = None,
        artifact_title: str | None = None,
    ) -> BitbucketIssueCommentPayload:
        """Convert generated text or an artifact dictionary into a Bitbucket comment payload."""
        resolved_issue_id = self._resolve_issue_id(issue_id)
        rendered_body = _comment_body(
            artifact,
            body=body,
            markdown=markdown,
            artifact_title=artifact_title or self.artifact_title,
        )
        return BitbucketIssueCommentPayload(
            body=rendered_body,
            workspace=self.workspace,
            repository=self.repository,
            issue_id=resolved_issue_id,
            metadata=_metadata(
                artifact,
                workspace=self.workspace,
                repository=self.repository,
                issue_id=resolved_issue_id,
            ),
        )

    def publish(
        self,
        artifact: dict[str, Any] | str,
        *,
        dry_run: bool = True,
        issue_id: int | str | None = None,
        body: str | None = None,
        markdown: str | None = None,
        artifact_title: str | None = None,
    ) -> BitbucketIssueCommentPublishResult:
        """Build the comment payload and optionally append it to a Bitbucket issue."""
        payload = self.build_comment_payload(
            artifact,
            issue_id=issue_id,
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
    ) -> BitbucketIssueCommentPublishResult:
        """Publish a caller-rendered Bitbucket issue comment payload."""
        issue_id = _issue_id(payload.get("issue_id") or self.issue_id)
        comment_payload = {
            **payload,
            "workspace": self.workspace,
            "repository": self.repository,
            "issue_id": issue_id,
            "metadata": payload.get("metadata") or {},
        }
        if dry_run:
            return BitbucketIssueCommentPublishResult(
                status_code=None,
                workspace=self.workspace,
                repository=self.repository,
                issue_id=issue_id,
                comment_id=None,
                comment_url=None,
                dry_run=True,
                payload=comment_payload,
            )

        if not self._has_auth:
            raise BitbucketIssueCommentPublishError(
                "BITBUCKET_USERNAME and BITBUCKET_APP_PASSWORD are required for live "
                "Bitbucket issue comment publishing; use dry_run to preview"
            )

        endpoint = self.comment_endpoint(issue_id)
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    endpoint,
                    json=_bitbucket_comment_request(comment_payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise BitbucketIssueCommentPublishError(
                    f"Bitbucket issue comment publish failed for {endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise BitbucketIssueCommentPublishError(
                f"Bitbucket issue comment publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        comment_id = _comment_id(body)
        comment_url = _comment_url(body)
        if not comment_id:
            raise BitbucketIssueCommentPublishError(
                "Bitbucket issue comment publish failed: response did not include comment id",
                status_code=response.status_code,
            )

        return BitbucketIssueCommentPublishResult(
            status_code=response.status_code,
            workspace=self.workspace,
            repository=self.repository,
            issue_id=issue_id,
            comment_id=comment_id,
            comment_url=comment_url,
            dry_run=False,
            payload={
                **comment_payload,
                "metadata": {
                    **comment_payload["metadata"],
                    "bitbucket_issue_comment_id": comment_id,
                    "bitbucket_issue_comment_url": comment_url,
                },
            },
        )

    @property
    def _has_auth(self) -> bool:
        return bool(self.username and self.app_password)

    def _headers(self) -> dict[str, str]:
        assert self.username is not None and self.app_password is not None
        credentials = f"{self.username}:{self.app_password}".encode("utf-8")
        return {
            "Accept": "application/json",
            "Authorization": f"Basic {base64.b64encode(credentials).decode('ascii')}",
            "Content-Type": "application/json",
            "User-Agent": "max-bitbucket-issue-comments-publisher/1",
        }

    def _resolve_issue_id(self, issue_id: int | str | None = None) -> int:
        resolved = issue_id if issue_id is not None else self.issue_id
        return _issue_id(resolved)


BitbucketIssueCommentsPublisher = BitbucketIssueCommentPublisher


def _bitbucket_comment_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {"content": {"raw": payload["body"]}}


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
    problem = _dict_value(artifact, "problem")
    solution = _dict_value(artifact, "solution")
    execution = _dict_value(artifact, "execution")
    evidence = _dict_value(artifact, "evidence")
    source = _dict_value(artifact, "source")
    evaluation = artifact.get("evaluation") if isinstance(artifact.get("evaluation"), dict) else {}
    lines = [
        _text_or_placeholder(project.get("summary") or artifact.get("summary")),
        "",
        "### Source",
        f"- Idea ID: {_text_or_placeholder(source.get('idea_id'))}",
        f"- Status: {_text_or_placeholder(source.get('status'))}",
        f"- Kind: {_text_or_placeholder(artifact.get('kind'))}",
        f"- Schema: {_text_or_placeholder(artifact.get('schema_version'))}",
        "",
        "### Problem",
        _text_or_placeholder(problem.get("statement")),
        "",
        "### Solution",
        _text_or_placeholder(solution.get("approach")),
        "",
        "### MVP Scope",
    ]
    lines.extend(_bullet_list(execution.get("mvp_scope")))
    lines.extend(
        [
            "",
            "### Evidence",
            f"- Rationale: {_text_or_placeholder(evidence.get('rationale'))}",
            f"- Insights: {', '.join(evidence.get('insight_ids') or []) or 'None'}",
            f"- Signals: {', '.join(evidence.get('signal_ids') or []) or 'None'}",
            "",
            "### Evaluation",
            f"- Recommendation: {_text_or_placeholder(evaluation.get('recommendation'))}",
            f"- Overall score: {_score_text(evaluation.get('overall_score'))}",
            "",
            "### Artifact Preview",
            "```json",
            json.dumps(artifact, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _metadata(
    artifact: dict[str, Any] | str,
    *,
    workspace: str,
    repository: str,
    issue_id: int,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "publisher": "max.bitbucket_issue_comments",
        "workspace": workspace,
        "repository": repository,
        "issue_id": issue_id,
    }
    if not isinstance(artifact, dict):
        return {
            **metadata,
            "source_system": "max",
            "source_type": "text",
        }
    source = _dict_value(artifact, "source")
    return {
        **metadata,
        "source_system": source.get("system", "max"),
        "source_type": source.get("type", "artifact"),
        "idea_id": source.get("idea_id"),
        "design_brief_id": source.get("design_brief_id"),
        "schema_version": artifact.get("schema_version"),
        "kind": artifact.get("kind"),
    }


def _bullet_list(items: object) -> list[str]:
    if not isinstance(items, list) or not items:
        return ["- None"]
    return [f"- {item}" for item in items if item] or ["- None"]


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise BitbucketIssueCommentPublishError(message)
    return text


def _required_slug(value: object, message: str) -> str:
    text = _required_text(value, message)
    if "/" in text:
        raise BitbucketIssueCommentPublishError(f"{message}; use the slug without a slash")
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _text_or_placeholder(value: object) -> str:
    text = str(value).strip() if value else ""
    return text or "Not specified"


def _score_text(value: object) -> str:
    if isinstance(value, int | float):
        return f"{value:.1f}"
    return _text_or_placeholder(value)


def _required_url(value: object) -> str:
    raw = _required_text(value, "Bitbucket api_url is required").rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise BitbucketIssueCommentPublishError(
            "Bitbucket api_url must be an absolute http(s) URL"
        )
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _issue_id(value: object) -> int:
    try:
        issue_id = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise BitbucketIssueCommentPublishError(
            "Bitbucket issue_id is required and must be a positive integer"
        ) from exc
    if issue_id < 1:
        raise BitbucketIssueCommentPublishError(
            "Bitbucket issue_id is required and must be a positive integer"
        )
    return issue_id


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise BitbucketIssueCommentPublishError(
            "Bitbucket issue comment publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    return body if isinstance(body, dict) else {}


def _comment_id(body: dict[str, Any]) -> str | None:
    comment_id = body.get("id")
    return str(comment_id) if comment_id else None


def _comment_url(body: dict[str, Any]) -> str | None:
    links = body.get("links")
    if isinstance(links, dict):
        html = links.get("html")
        if isinstance(html, dict) and html.get("href"):
            return str(html["href"])
    return None

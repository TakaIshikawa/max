"""GitHub issue comment publisher for generated specs and review artifacts."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx


DEFAULT_GITHUB_API_URL = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS = 10.0


class GitHubIssueCommentPublishError(RuntimeError):
    """Raised when a GitHub issue comment publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubIssueCommentPayload:
    """GitHub issue comment payload plus Max-specific metadata."""

    body: str
    repository: str
    issue_number: int
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable issue comment payload."""
        return {
            "body": self.body,
            "repository": self.repository,
            "issue_number": self.issue_number,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class GitHubIssueCommentPublishResult:
    """Summary of a GitHub issue comment publish or dry run."""

    status_code: int | None
    repository: str
    issue_number: int
    comment_id: str | None
    comment_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class GitHubIssueCommentPublisher:
    """Build and optionally append generated artifacts to existing GitHub issues."""

    def __init__(
        self,
        repository: str,
        *,
        issue_number: int | str | None = None,
        token: str | None = None,
        api_url: str = DEFAULT_GITHUB_API_URL,
        artifact_title: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.repository = _validate_repository(repository)
        self.issue_number = (
            _validate_issue_number(issue_number) if issue_number is not None else None
        )
        self.token = token
        self.api_url = api_url.rstrip("/")
        self.artifact_title = _optional_text(artifact_title)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        repository: str | None = None,
        issue_number: int | str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        artifact_title: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> GitHubIssueCommentPublisher:
        """Create a publisher using CLI values first, then environment variables."""
        resolved_repository = repository or os.getenv("GITHUB_REPOSITORY")
        if not resolved_repository:
            raise GitHubIssueCommentPublishError(
                "GitHub repository is required; pass --github-repository or set GITHUB_REPOSITORY"
            )
        return cls(
            resolved_repository,
            issue_number=issue_number or os.getenv("GITHUB_ISSUE_NUMBER"),
            token=token or os.getenv("GITHUB_TOKEN"),
            api_url=api_url or os.getenv("GITHUB_API_URL", DEFAULT_GITHUB_API_URL),
            artifact_title=artifact_title or os.getenv("GITHUB_ARTIFACT_TITLE"),
            timeout=timeout,
            client=client,
        )

    def comment_endpoint(self, issue_number: int | str | None = None) -> str:
        """Return the GitHub API endpoint used for issue comment creation."""
        resolved_issue_number = self._resolve_issue_number(issue_number)
        return f"{self.api_url}/repos/{self.repository}/issues/{resolved_issue_number}/comments"

    def build_comment_payload(
        self,
        artifact: dict[str, Any],
        *,
        issue_number: int | str | None = None,
        artifact_title: str | None = None,
    ) -> GitHubIssueCommentPayload:
        """Convert a generated spec or review artifact into a GitHub comment payload."""
        resolved_issue_number = self._resolve_issue_number(issue_number)
        title = _comment_title(artifact, artifact_title or self.artifact_title)
        source = _dict_value(artifact, "source")
        metadata = {
            "publisher": "max.github_issue_comments",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "artifact"),
            "idea_id": source.get("idea_id"),
            "schema_version": artifact.get("schema_version"),
            "kind": artifact.get("kind"),
            "repository": self.repository,
            "issue_number": resolved_issue_number,
            "artifact_title": title,
        }
        return GitHubIssueCommentPayload(
            body=_comment_body(artifact, title=title),
            repository=self.repository,
            issue_number=resolved_issue_number,
            metadata=metadata,
        )

    def publish(
        self,
        artifact: dict[str, Any],
        *,
        dry_run: bool = True,
        issue_number: int | str | None = None,
        artifact_title: str | None = None,
    ) -> GitHubIssueCommentPublishResult:
        """Build the comment payload and optionally append it to a GitHub issue."""
        payload = self.build_comment_payload(
            artifact,
            issue_number=issue_number,
            artifact_title=artifact_title,
        ).to_dict()
        return self.publish_comment_payload(payload, dry_run=dry_run)

    def publish_comment_payload(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> GitHubIssueCommentPublishResult:
        """Publish a pre-rendered GitHub issue comment payload."""
        issue_number = _validate_issue_number(payload.get("issue_number"))
        if dry_run:
            return GitHubIssueCommentPublishResult(
                status_code=None,
                repository=self.repository,
                issue_number=issue_number,
                comment_id=None,
                comment_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self.token:
            raise GitHubIssueCommentPublishError(
                "GITHUB_TOKEN is required for live GitHub issue comment publishing; "
                "use --dry-run to preview"
            )

        endpoint = self.comment_endpoint(issue_number)
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    endpoint,
                    json={"body": payload["body"]},
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                        "User-Agent": "max-github-issue-comments-publisher/1",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise GitHubIssueCommentPublishError(
                    f"GitHub issue comment publish failed for {endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise GitHubIssueCommentPublishError(
                f"GitHub issue comment publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        comment_id = _comment_id(response)
        comment_url = _comment_url(response)
        return GitHubIssueCommentPublishResult(
            status_code=response.status_code,
            repository=self.repository,
            issue_number=issue_number,
            comment_id=comment_id,
            comment_url=comment_url,
            dry_run=False,
            payload={
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "github_issue_comment_id": comment_id,
                    "github_issue_comment_url": comment_url,
                },
            },
        )

    def _resolve_issue_number(self, issue_number: int | str | None = None) -> int:
        resolved = issue_number if issue_number is not None else self.issue_number
        if resolved is None:
            raise GitHubIssueCommentPublishError(
                "GitHub issue number is required; pass issue_number or set GITHUB_ISSUE_NUMBER"
            )
        return _validate_issue_number(resolved)


GitHubIssueCommentsPublisher = GitHubIssueCommentPublisher


def _comment_title(artifact: dict[str, Any], explicit_title: str | None) -> str:
    if explicit_title:
        return explicit_title
    project = _dict_value(artifact, "project")
    source = _dict_value(artifact, "source")
    return _text_or_placeholder(
        project.get("title")
        or artifact.get("title")
        or source.get("idea_id")
        or "Generated Artifact"
    )


def _comment_body(artifact: dict[str, Any], *, title: str) -> str:
    project = _dict_value(artifact, "project")
    problem = _dict_value(artifact, "problem")
    solution = _dict_value(artifact, "solution")
    execution = _dict_value(artifact, "execution")
    evidence = _dict_value(artifact, "evidence")
    source = _dict_value(artifact, "source")
    evaluation = artifact.get("evaluation") if isinstance(artifact.get("evaluation"), dict) else {}

    lines = [
        f"## {title}",
        "",
        _text_or_placeholder(project.get("summary") or artifact.get("summary")),
        "",
        "### Source",
        f"- Idea ID: {_text_or_placeholder(source.get('idea_id'))}",
        f"- Status: {_text_or_placeholder(source.get('status'))}",
        f"- Domain: {_text_or_placeholder(source.get('domain'))}",
        f"- Category: {_text_or_placeholder(source.get('category'))}",
        "",
        "### Problem",
        _text_or_placeholder(problem.get("statement")),
        "",
        "### Solution",
        _text_or_placeholder(solution.get("approach")),
        "",
        "### Execution",
        f"- Target users: {_text_or_placeholder(project.get('target_users'))}",
        f"- Specific user: {_text_or_placeholder(project.get('specific_user'))}",
        f"- Buyer: {_text_or_placeholder(project.get('buyer'))}",
        f"- Workflow context: {_text_or_placeholder(project.get('workflow_context'))}",
        "",
        "### MVP Scope",
    ]
    lines.extend(_bullet_list(execution.get("mvp_scope")))
    lines.extend(
        [
            "",
            "### Validation",
            _text_or_placeholder(execution.get("validation_plan")),
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


def _bullet_list(items: object) -> list[str]:
    if not isinstance(items, list) or not items:
        return ["- None"]
    return [f"- {item}" for item in items if item] or ["- None"]


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


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


def _validate_repository(repository: str) -> str:
    value = repository.strip()
    if value.count("/") != 1 or any(not part for part in value.split("/", 1)):
        raise GitHubIssueCommentPublishError(
            "GitHub repository must be in owner/repo format"
        )
    return value


def _validate_issue_number(issue_number: object) -> int:
    try:
        value = int(str(issue_number).strip())
    except (TypeError, ValueError) as exc:
        raise GitHubIssueCommentPublishError(
            "GitHub issue number must be a positive integer"
        ) from exc
    if value < 1:
        raise GitHubIssueCommentPublishError("GitHub issue number must be a positive integer")
    return value


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _comment_id(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        comment_id = body.get("id")
        return str(comment_id) if comment_id else None
    return None


def _comment_url(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        url = body.get("html_url")
        return str(url) if url else None
    return None

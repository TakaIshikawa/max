"""GitHub pull request review publisher for generated specs and design briefs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx


DEFAULT_GITHUB_API_URL = "https://api.github.com"
DEFAULT_REVIEW_EVENT = "COMMENT"
DEFAULT_TIMEOUT_SECONDS = 10.0


class GitHubPullRequestReviewCommentPublishError(RuntimeError):
    """Raised when a GitHub pull request review publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubPullRequestReviewCommentPayload:
    """GitHub pull request review payload plus Max-specific metadata."""

    owner: str
    repo: str
    repository: str
    pull_number: int
    body: str
    event: str
    comments: list[dict[str, Any]]
    metadata: dict[str, Any]
    commit_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable pull request review payload."""
        payload: dict[str, Any] = {
            "owner": self.owner,
            "repo": self.repo,
            "repository": self.repository,
            "pull_number": self.pull_number,
            "body": self.body,
            "event": self.event,
            "comments": self.comments,
            "metadata": self.metadata,
        }
        if self.commit_id:
            payload["commit_id"] = self.commit_id
        return payload


@dataclass(frozen=True)
class GitHubPullRequestReviewCommentPublishResult:
    """Summary of a GitHub pull request review publish or dry run."""

    status_code: int | None
    owner: str
    repo: str
    repository: str
    pull_number: int
    review_id: str | None
    review_state: str | None
    review_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class GitHubPullRequestReviewCommentPublisher:
    """Create comment-only GitHub pull request reviews from Max artifacts."""

    def __init__(
        self,
        repository: str | None,
        *,
        pull_number: int | str | None = None,
        token: str | None = None,
        api_url: str = DEFAULT_GITHUB_API_URL,
        review_body: str | None = None,
        event: str = DEFAULT_REVIEW_EVENT,
        commit_id: str | None = None,
        comments: list[dict[str, Any]] | None = None,
        artifact_title: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.repository = _validate_repository(repository)
        self.owner, self.repo = self.repository.split("/", 1)
        self.pull_number = (
            _validate_pull_number(pull_number) if pull_number is not None else None
        )
        self.token = _optional_text(token)
        self.api_url = api_url.rstrip("/")
        self.review_body = _optional_text(review_body)
        self.event = _validate_event(event)
        self.commit_id = _optional_text(commit_id)
        self.comments = _comments_value(comments)
        self.artifact_title = _optional_text(artifact_title)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        repository: str | None = None,
        pull_number: int | str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        review_body: str | None = None,
        event: str | None = None,
        commit_id: str | None = None,
        comments: list[dict[str, Any]] | None = None,
        artifact_title: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> GitHubPullRequestReviewCommentPublisher:
        """Create a publisher using CLI values first, then environment variables."""
        resolved_repository = repository or os.getenv("GITHUB_REPOSITORY")
        if not resolved_repository:
            raise GitHubPullRequestReviewCommentPublishError(
                "GitHub repository is required; pass repository or set GITHUB_REPOSITORY"
            )
        return cls(
            resolved_repository,
            pull_number=pull_number or os.getenv("GITHUB_PULL_NUMBER"),
            token=token or os.getenv("GITHUB_TOKEN"),
            api_url=api_url or os.getenv("GITHUB_API_URL", DEFAULT_GITHUB_API_URL),
            review_body=review_body or os.getenv("GITHUB_PULL_REQUEST_REVIEW_BODY"),
            event=event or os.getenv("GITHUB_PULL_REQUEST_REVIEW_EVENT", DEFAULT_REVIEW_EVENT),
            commit_id=commit_id or os.getenv("GITHUB_PULL_REQUEST_COMMIT_ID"),
            comments=comments,
            artifact_title=artifact_title or os.getenv("GITHUB_ARTIFACT_TITLE"),
            timeout=timeout,
            client=client,
        )

    def review_endpoint(self, pull_number: int | str | None = None) -> str:
        """Return the GitHub API endpoint used for pull request review creation."""
        resolved_pull_number = self._resolve_pull_number(pull_number)
        return (
            f"{self.api_url}/repos/{self.owner}/{self.repo}/pulls/"
            f"{resolved_pull_number}/reviews"
        )

    def build_review_payload(
        self,
        artifact: dict[str, Any],
        *,
        pull_number: int | str | None = None,
        review_body: str | None = None,
        event: str | None = None,
        commit_id: str | None = None,
        comments: list[dict[str, Any]] | None = None,
        artifact_title: str | None = None,
    ) -> GitHubPullRequestReviewCommentPayload:
        """Convert a generated spec or review artifact into a GitHub review payload."""
        resolved_pull_number = self._resolve_pull_number(pull_number)
        title = _review_title(artifact, artifact_title or self.artifact_title)
        source = _dict_value(artifact, "source")
        resolved_event = _validate_event(event or self.event)
        metadata = {
            "publisher": "max.github_pull_request_review_comments",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "artifact"),
            "idea_id": source.get("idea_id"),
            "design_brief_id": source.get("design_brief_id"),
            "schema_version": artifact.get("schema_version"),
            "kind": artifact.get("kind"),
            "repository": self.repository,
            "pull_number": resolved_pull_number,
            "artifact_title": title,
        }
        return GitHubPullRequestReviewCommentPayload(
            owner=self.owner,
            repo=self.repo,
            repository=self.repository,
            pull_number=resolved_pull_number,
            body=(
                _required_text(review_body, "GitHub pull request review body is required")
                if review_body is not None
                else self.review_body or _review_body(artifact, title=title)
            ),
            event=resolved_event,
            commit_id=_optional_text(commit_id) or self.commit_id,
            comments=_comments_value(comments) if comments is not None else list(self.comments),
            metadata=metadata,
        )

    def publish(
        self,
        artifact: dict[str, Any],
        *,
        dry_run: bool = True,
        pull_number: int | str | None = None,
        review_body: str | None = None,
        event: str | None = None,
        commit_id: str | None = None,
        comments: list[dict[str, Any]] | None = None,
        artifact_title: str | None = None,
    ) -> GitHubPullRequestReviewCommentPublishResult:
        """Build the review payload and optionally create it on a GitHub pull request."""
        payload = self.build_review_payload(
            artifact,
            pull_number=pull_number,
            review_body=review_body,
            event=event,
            commit_id=commit_id,
            comments=comments,
            artifact_title=artifact_title,
        ).to_dict()
        return self.publish_review_payload(payload, dry_run=dry_run)

    def build_design_brief_payload(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str | None = None,
        pull_number: int | str | None = None,
        review_body: str | None = None,
        event: str | None = None,
        commit_id: str | None = None,
        comments: list[dict[str, Any]] | None = None,
        title: str | None = None,
    ) -> GitHubPullRequestReviewCommentPayload:
        """Convert a persisted design brief into a GitHub pull request review payload."""
        resolved_pull_number = self._resolve_pull_number(pull_number)
        brief = _brief_payload(design_brief)
        brief_id = brief.get("id")
        resolved_title = _text_or_placeholder(title or brief.get("title") or brief_id)
        metadata = {
            "publisher": "max.github_pull_request_review_comments",
            "source_system": "max",
            "source_type": "design_brief",
            "design_brief_id": brief_id,
            "domain": brief.get("domain"),
            "theme": brief.get("theme"),
            "lead_idea_id": brief.get("lead_idea_id"),
            "source_idea_ids": _source_idea_ids(brief.get("source_idea_ids")),
            "repository": self.repository,
            "pull_number": resolved_pull_number,
            "artifact_title": resolved_title,
        }
        return GitHubPullRequestReviewCommentPayload(
            owner=self.owner,
            repo=self.repo,
            repository=self.repository,
            pull_number=resolved_pull_number,
            body=(
                _required_text(review_body, "GitHub pull request review body is required")
                if review_body is not None
                else self.review_body
                or _design_brief_body(brief, markdown=markdown, title=resolved_title)
            ),
            event=_validate_event(event or self.event),
            commit_id=_optional_text(commit_id) or self.commit_id,
            comments=_comments_value(comments) if comments is not None else list(self.comments),
            metadata=metadata,
        )

    def publish_design_brief(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str | None = None,
        dry_run: bool = True,
        pull_number: int | str | None = None,
        review_body: str | None = None,
        event: str | None = None,
        commit_id: str | None = None,
        comments: list[dict[str, Any]] | None = None,
        title: str | None = None,
    ) -> GitHubPullRequestReviewCommentPublishResult:
        """Build the design brief review payload and optionally publish it."""
        payload = self.build_design_brief_payload(
            design_brief,
            markdown=markdown,
            pull_number=pull_number,
            review_body=review_body,
            event=event,
            commit_id=commit_id,
            comments=comments,
            title=title,
        ).to_dict()
        return self.publish_review_payload(payload, dry_run=dry_run)

    def publish_review_payload(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> GitHubPullRequestReviewCommentPublishResult:
        """Publish a pre-rendered GitHub pull request review payload."""
        pull_number = _validate_pull_number(payload.get("pull_number"))
        if dry_run:
            return GitHubPullRequestReviewCommentPublishResult(
                status_code=None,
                owner=self.owner,
                repo=self.repo,
                repository=self.repository,
                pull_number=pull_number,
                review_id=None,
                review_state=None,
                review_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self.token:
            raise GitHubPullRequestReviewCommentPublishError(
                "GITHUB_TOKEN is required for live GitHub pull request review publishing; "
                "use dry_run to preview"
            )

        endpoint = self.review_endpoint(pull_number)
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    endpoint,
                    json=_github_review_request_payload(payload),
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                        "User-Agent": "max-github-pull-request-review-comments-publisher/1",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise GitHubPullRequestReviewCommentPublishError(
                    f"GitHub pull request review publish failed for {endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise GitHubPullRequestReviewCommentPublishError(
                f"GitHub pull request review publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        review_id = _review_id(response)
        review_state = _review_state(response)
        review_url = _review_url(response)
        return GitHubPullRequestReviewCommentPublishResult(
            status_code=response.status_code,
            owner=self.owner,
            repo=self.repo,
            repository=self.repository,
            pull_number=pull_number,
            review_id=review_id,
            review_state=review_state,
            review_url=review_url,
            dry_run=False,
            payload={
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "github_pull_request_review_id": review_id,
                    "github_pull_request_review_state": review_state,
                    "github_pull_request_review_url": review_url,
                },
            },
        )

    def _resolve_pull_number(self, pull_number: int | str | None = None) -> int:
        resolved = pull_number if pull_number is not None else self.pull_number
        if resolved is None:
            raise GitHubPullRequestReviewCommentPublishError(
                "GitHub pull number is required; pass pull_number or set GITHUB_PULL_NUMBER"
            )
        return _validate_pull_number(resolved)


GitHubPullRequestReviewCommentsPublisher = GitHubPullRequestReviewCommentPublisher


def _review_title(artifact: dict[str, Any], explicit_title: str | None) -> str:
    if explicit_title:
        return explicit_title
    project = _dict_value(artifact, "project")
    source = _dict_value(artifact, "source")
    return _text_or_placeholder(
        project.get("title")
        or artifact.get("title")
        or source.get("design_brief_id")
        or source.get("idea_id")
        or "Generated Artifact"
    )


def _review_body(artifact: dict[str, Any], *, title: str) -> str:
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
        f"- Design brief ID: {_text_or_placeholder(source.get('design_brief_id'))}",
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


def _design_brief_body(
    design_brief: dict[str, Any],
    *,
    markdown: str | None,
    title: str,
) -> str:
    lines = [
        f"## {title}",
        "",
        _text_or_placeholder(
            design_brief.get("merged_product_concept")
            or design_brief.get("summary")
            or design_brief.get("problem")
        ),
        "",
        "### Source",
        f"- Design brief ID: {_text_or_placeholder(design_brief.get('id'))}",
        f"- Lead idea ID: {_text_or_placeholder(design_brief.get('lead_idea_id'))}",
        f"- Source idea IDs: {', '.join(_source_idea_ids(design_brief.get('source_idea_ids'))) or 'None'}",
        f"- Domain: {_text_or_placeholder(design_brief.get('domain'))}",
        f"- Theme: {_text_or_placeholder(design_brief.get('theme'))}",
        "",
        "### Readiness",
        f"- Status: {_text_or_placeholder(design_brief.get('design_status'))}",
        f"- Score: {_score_text(design_brief.get('readiness_score'))}",
        "",
        "### Validation",
        _text_or_placeholder(design_brief.get("validation_plan")),
    ]
    if markdown:
        lines.extend(["", "### Design Brief", markdown.strip(), ""])
    return "\n".join(lines)


def _github_review_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    request_payload: dict[str, Any] = {
        "body": _required_text(payload.get("body"), "GitHub pull request review body is required"),
        "event": _validate_event(payload.get("event")),
    }
    if payload.get("commit_id"):
        request_payload["commit_id"] = payload["commit_id"]
    comments = _comments_value(payload.get("comments"))
    if comments:
        request_payload["comments"] = comments
    return request_payload


def _brief_payload(design_brief: dict[str, Any]) -> dict[str, Any]:
    nested = design_brief.get("design_brief")
    return nested if isinstance(nested, dict) else design_brief


def _bullet_list(items: object) -> list[str]:
    if not isinstance(items, list) or not items:
        return ["- None"]
    return [f"- {item}" for item in items if item] or ["- None"]


def _comments_value(comments: object) -> list[dict[str, Any]]:
    if comments is None:
        return []
    if not isinstance(comments, list):
        raise GitHubPullRequestReviewCommentPublishError(
            "GitHub pull request review comments must be a list"
        )
    normalized: list[dict[str, Any]] = []
    for comment in comments:
        if not isinstance(comment, dict):
            raise GitHubPullRequestReviewCommentPublishError(
                "GitHub pull request review comments must contain objects"
            )
        body = _required_text(
            comment.get("body"),
            "GitHub pull request review inline comment body is required",
        )
        normalized.append({**comment, "body": body})
    return normalized


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise GitHubPullRequestReviewCommentPublishError(message)
    return text


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _score_text(value: object) -> str:
    if isinstance(value, int | float):
        return f"{value:.1f}"
    return _text_or_placeholder(value)


def _source_idea_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    unique: list[str] = []
    for item in value:
        text = str(item).strip() if item else ""
        if text and text not in unique:
            unique.append(text)
    return unique


def _text_or_placeholder(value: object) -> str:
    text = str(value).strip() if value else ""
    return text or "Not specified"


def _validate_event(event: object) -> str:
    value = _required_text(event, "GitHub pull request review event is required").upper()
    if value != DEFAULT_REVIEW_EVENT:
        raise GitHubPullRequestReviewCommentPublishError(
            "GitHub pull request review event must be COMMENT"
        )
    return value


def _validate_pull_number(pull_number: object) -> int:
    try:
        value = int(str(pull_number).strip())
    except (TypeError, ValueError) as exc:
        raise GitHubPullRequestReviewCommentPublishError(
            "GitHub pull number must be a positive integer"
        ) from exc
    if value < 1:
        raise GitHubPullRequestReviewCommentPublishError(
            "GitHub pull number must be a positive integer"
        )
    return value


def _validate_repository(repository: str | None) -> str:
    value = repository.strip() if repository else ""
    if value.count("/") != 1 or any(not part for part in value.split("/", 1)):
        raise GitHubPullRequestReviewCommentPublishError(
            "GitHub repository must be in owner/repo format"
        )
    return value


def _review_id(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        review_id = body.get("id")
        return str(review_id) if review_id else None
    return None


def _review_state(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        state = body.get("state")
        return str(state) if state else None
    return None


def _review_url(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        url = body.get("html_url")
        return str(url) if url else None
    return None

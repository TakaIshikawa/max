"""GitHub Issues publisher for generated TactSpecs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


DEFAULT_GITHUB_API_URL = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS = 10.0


class GitHubIssuePublishError(RuntimeError):
    """Raised when a GitHub issue publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubIssuePayload:
    """GitHub issue creation payload plus Max-specific metadata."""

    title: str
    body: str
    labels: list[str]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable issue payload."""
        return {
            "title": self.title,
            "body": self.body,
            "labels": self.labels,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class GitHubIssuePublishResult:
    """Summary of a GitHub issue publish or dry run."""

    status_code: int | None
    repository: str
    issue_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class GitHubIssuePublisher:
    """Build and optionally create GitHub issues from TactSpec payloads."""

    def __init__(
        self,
        repository: str,
        *,
        token: str | None = None,
        api_url: str = DEFAULT_GITHUB_API_URL,
        labels: list[str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.repository = _validate_repository(repository)
        self.token = token
        self.api_url = api_url.rstrip("/")
        self.labels = labels or []
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        repository: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        labels: list[str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> GitHubIssuePublisher:
        """Create a publisher using CLI values first, then environment variables."""
        resolved_repository = repository or os.getenv("GITHUB_REPOSITORY")
        if not resolved_repository:
            raise GitHubIssuePublishError(
                "GitHub repository is required; pass --github-repository or set GITHUB_REPOSITORY"
            )
        return cls(
            resolved_repository,
            token=token or os.getenv("GITHUB_TOKEN"),
            api_url=api_url or os.getenv("GITHUB_API_URL", DEFAULT_GITHUB_API_URL),
            labels=labels,
            timeout=timeout,
            client=client,
        )

    @property
    def issue_endpoint(self) -> str:
        """Return the GitHub API endpoint used for issue creation."""
        return f"{self.api_url}/repos/{self.repository}/issues"

    def build_issue_payload(self, tact_spec: dict[str, Any]) -> GitHubIssuePayload:
        """Convert a generated TactSpec preview into a GitHub issue payload."""
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")
        quality = _dict_value(tact_spec, "quality")
        evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}

        title = _issue_title(project.get("title"), source.get("idea_id"))
        labels = _merge_labels(
            _issue_labels(source=source, quality=quality, evaluation=evaluation),
            self.labels,
        )
        metadata = {
            "publisher": "max.github_issues",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "idea"),
            "idea_id": source.get("idea_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "repository": self.repository,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        return GitHubIssuePayload(
            title=title,
            body=_issue_body(tact_spec),
            labels=labels,
            metadata=metadata,
        )

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True) -> GitHubIssuePublishResult:
        """Build the issue payload and optionally create it in GitHub."""
        payload = self.build_issue_payload(tact_spec).to_dict()
        if dry_run:
            return GitHubIssuePublishResult(
                status_code=None,
                repository=self.repository,
                issue_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self.token:
            raise GitHubIssuePublishError(
                "GITHUB_TOKEN is required for live GitHub issue publishing; use --dry-run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.issue_endpoint,
                    json={
                        "title": payload["title"],
                        "body": payload["body"],
                        "labels": payload["labels"],
                    },
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                        "User-Agent": "max-github-issues-publisher/1",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise GitHubIssuePublishError(
                    f"GitHub issue publish failed for {self.issue_endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise GitHubIssuePublishError(
                f"GitHub issue publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        issue_url = _issue_url(response)
        return GitHubIssuePublishResult(
            status_code=response.status_code,
            repository=self.repository,
            issue_url=issue_url,
            dry_run=False,
            payload={
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "github_issue_url": issue_url,
                    "github_issue_number": _issue_number(response),
                },
            },
        )


GitHubIssuesPublisher = GitHubIssuePublisher


def _issue_title(title: object, idea_id: object) -> str:
    base = str(title).strip() if title else str(idea_id or "Generated TactSpec").strip()
    return f"[Max] {base}"


def _issue_body(tact_spec: dict[str, Any]) -> str:
    project = _dict_value(tact_spec, "project")
    problem = _dict_value(tact_spec, "problem")
    solution = _dict_value(tact_spec, "solution")
    execution = _dict_value(tact_spec, "execution")
    evidence = _dict_value(tact_spec, "evidence")
    source = _dict_value(tact_spec, "source")
    evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}

    lines = [
        f"# {project.get('title') or source.get('idea_id') or 'Generated TactSpec'}",
        "",
        project.get("summary") or "",
        "",
        "## Source",
        f"- Idea ID: {source.get('idea_id', '')}",
        f"- Status: {source.get('status', '')}",
        f"- Domain: {source.get('domain', '')}",
        f"- Category: {source.get('category', '')}",
        "",
        "## Problem",
        _text_or_placeholder(problem.get("statement")),
        "",
        "## Solution",
        _text_or_placeholder(solution.get("approach")),
        "",
        "## Execution",
        f"- Target users: {_text_or_placeholder(project.get('target_users'))}",
        f"- Specific user: {_text_or_placeholder(project.get('specific_user'))}",
        f"- Buyer: {_text_or_placeholder(project.get('buyer'))}",
        f"- Workflow context: {_text_or_placeholder(project.get('workflow_context'))}",
        "",
        "## MVP Scope",
    ]
    lines.extend(_bullet_list(execution.get("mvp_scope")))
    lines.extend(
        [
            "",
            "## Validation",
            _text_or_placeholder(execution.get("validation_plan")),
            "",
            "## Evidence",
            f"- Rationale: {_text_or_placeholder(evidence.get('rationale'))}",
            f"- Insights: {', '.join(evidence.get('insight_ids') or []) or 'None'}",
            f"- Signals: {', '.join(evidence.get('signal_ids') or []) or 'None'}",
            "",
            "## Evaluation",
            f"- Recommendation: {_text_or_placeholder(evaluation.get('recommendation'))}",
            f"- Overall score: {_score_text(evaluation.get('overall_score'))}",
            "",
            "## TactSpec Preview",
            "```json",
            json.dumps(tact_spec, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _issue_labels(
    *,
    source: dict[str, Any],
    quality: dict[str, Any],
    evaluation: dict[str, Any],
) -> list[str]:
    labels = [
        "max",
        "tact-spec",
        "idea",
        _label_value(source.get("category")),
        _label_value(source.get("domain")),
        _label_value(source.get("status")),
        _label_value(evaluation.get("recommendation"), prefix="recommendation"),
    ]
    labels.extend(_label_value(tag, prefix="quality") for tag in quality.get("rejection_tags") or [])

    unique: list[str] = []
    for label in labels:
        if label and label not in unique:
            unique.append(label)
    return unique


def _merge_labels(labels: list[str], extra_labels: list[str]) -> list[str]:
    merged = list(labels)
    for label in extra_labels:
        safe = _label_value(label)
        if safe and safe not in merged:
            merged.append(safe)
    return merged


def _label_value(value: object, *, prefix: str | None = None) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower().replace("_", "-").replace(" ", "-")
    safe = "".join(ch for ch in text if ch.isalnum() or ch in "-./")
    if not safe:
        return ""
    label = f"{prefix}:{safe}" if prefix else safe
    return label[:50]


def _bullet_list(items: object) -> list[str]:
    if not isinstance(items, list) or not items:
        return ["- None"]
    return [f"- {item}" for item in items if item] or ["- None"]


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


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
        raise GitHubIssuePublishError(
            "GitHub repository must be in owner/repo format"
        )
    return value


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _issue_url(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        url = body.get("html_url")
        return str(url) if url else None
    return None


def _issue_number(response: httpx.Response) -> int | None:
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict) and isinstance(body.get("number"), int):
        return body["number"]
    return None

"""GitHub Projects v2 draft item publisher for generated TactSpecs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx


DEFAULT_GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
DEFAULT_TIMEOUT_SECONDS = 10.0


class GitHubProjectPublishError(RuntimeError):
    """Raised when a GitHub Project item publish cannot be completed."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        attempts: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.attempts = attempts or []


@dataclass(frozen=True)
class GitHubProjectItemPayload:
    """GitHub Project v2 draft item payload plus Max-specific metadata."""

    project_id: str
    title: str
    body: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable draft item payload."""
        return {
            "project_id": self.project_id,
            "title": self.title,
            "body": self.body,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class GitHubProjectItemPublishResult:
    """Summary of a GitHub Project item publish or dry run."""

    status_code: int | None
    project_id: str
    item_id: str | None
    item_url: str | None
    dry_run: bool
    payload: dict[str, Any]
    attempts: list[dict[str, Any]]


class GitHubProjectItemPublisher:
    """Build and optionally create GitHub Projects v2 draft items from TactSpecs."""

    def __init__(
        self,
        project_id: str,
        *,
        token: str | None = None,
        api_url: str = DEFAULT_GITHUB_GRAPHQL_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.project_id = _required_text(project_id, "GitHub project_id is required")
        self.token = token
        self.api_url = _required_text(api_url, "GitHub GraphQL api_url is required").rstrip("/")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        project_id: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> GitHubProjectItemPublisher:
        """Create a publisher using explicit values first, then environment variables."""
        resolved_project_id = project_id or os.getenv("GITHUB_PROJECT_ID")
        if not resolved_project_id:
            raise GitHubProjectPublishError(
                "GitHub project_id is required; pass project_id or set GITHUB_PROJECT_ID"
            )
        return cls(
            resolved_project_id,
            token=token or os.getenv("GITHUB_TOKEN"),
            api_url=api_url or os.getenv("GITHUB_GRAPHQL_URL", DEFAULT_GITHUB_GRAPHQL_URL),
            timeout=timeout,
            client=client,
        )

    @property
    def graphql_endpoint(self) -> str:
        """Return the GitHub GraphQL endpoint used for draft item creation."""
        return self.api_url

    def build_project_item_payload(self, tact_spec: dict[str, Any]) -> GitHubProjectItemPayload:
        """Convert a generated TactSpec preview into a Project v2 draft item payload."""
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")
        metadata = {
            "publisher": "max.github_projects",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "idea"),
            "idea_id": source.get("idea_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "project_id": self.project_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return GitHubProjectItemPayload(
            project_id=self.project_id,
            title=_item_title(project.get("title"), source.get("idea_id")),
            body=_item_body(tact_spec),
            metadata=metadata,
        )

    def publish(
        self,
        tact_spec: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> GitHubProjectItemPublishResult:
        """Build the draft item payload and optionally create it in GitHub Projects."""
        return self.publish_payload(
            self.build_project_item_payload(tact_spec),
            dry_run=dry_run,
        )

    def publish_payload(
        self,
        payload: GitHubProjectItemPayload | dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> GitHubProjectItemPublishResult:
        """Create a GitHub Projects v2 draft item from a prebuilt payload."""
        payload_dict = payload.to_dict() if isinstance(payload, GitHubProjectItemPayload) else dict(payload)
        if dry_run:
            return GitHubProjectItemPublishResult(
                status_code=None,
                project_id=self.project_id,
                item_id=None,
                item_url=None,
                dry_run=True,
                payload=payload_dict,
                attempts=[],
            )

        if not self.token:
            raise GitHubProjectPublishError(
                "GITHUB_TOKEN is required for live GitHub Project publishing; use dry_run to preview"
            )

        attempts: list[dict[str, Any]] = []
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.graphql_endpoint,
                    json=_graphql_request(payload_dict),
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                        "User-Agent": "max-github-projects-publisher/1",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                attempts.append(_attempt(self.graphql_endpoint, error=str(exc)))
                raise GitHubProjectPublishError(
                    _redact(
                        f"GitHub Project publish failed for {redact_url(self.graphql_endpoint)}: {exc}",
                        self.token,
                    ),
                    attempts=attempts,
                ) from exc
        finally:
            if close_client:
                client.close()

        attempts.append(_attempt(self.graphql_endpoint, status_code=response.status_code))

        if not 200 <= response.status_code < 300:
            raise GitHubProjectPublishError(
                _redact(
                    f"GitHub Project publish failed with HTTP {response.status_code}: "
                    f"{_response_body_preview(response)}",
                    self.token,
                ),
                status_code=response.status_code,
                attempts=attempts,
            )

        body = _json_response(response, token=self.token, attempts=attempts)
        errors = body.get("errors")
        if isinstance(errors, list) and errors:
            raise GitHubProjectPublishError(
                _redact(
                    f"GitHub Project publish failed: {_graphql_errors_preview(errors)}",
                    self.token,
                ),
                status_code=response.status_code,
                attempts=attempts,
            )

        item = _project_item_from_response(body)
        if not item:
            raise GitHubProjectPublishError(
                "GitHub Project publish failed: response did not include created project item",
                status_code=response.status_code,
                attempts=attempts,
            )

        item_id = _optional_string(item.get("id"))
        item_url = _project_item_url(item)
        return GitHubProjectItemPublishResult(
            status_code=response.status_code,
            project_id=self.project_id,
            item_id=item_id,
            item_url=item_url,
            dry_run=False,
            payload={
                **payload_dict,
                "metadata": {
                    **payload_dict["metadata"],
                    "github_project_id": self.project_id,
                    "github_project_item_id": item_id,
                    "github_project_item_url": item_url,
                },
            },
            attempts=attempts,
        )


GitHubProjectPublisher = GitHubProjectItemPublisher
GitHubProjectsPublisher = GitHubProjectItemPublisher
GitHubProjectPayload = GitHubProjectItemPayload
GitHubProjectPublishResult = GitHubProjectItemPublishResult


ADD_PROJECT_V2_DRAFT_ISSUE_MUTATION = """
mutation MaxProjectV2DraftIssueCreate($input: AddProjectV2DraftIssueInput!) {
  addProjectV2DraftIssue(input: $input) {
    projectItem {
      id
      content {
        ... on DraftIssue {
          id
          title
          body
        }
      }
    }
  }
}
""".strip()


def _graphql_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "query": ADD_PROJECT_V2_DRAFT_ISSUE_MUTATION,
        "variables": {
            "input": {
                "projectId": payload["project_id"],
                "title": payload["title"],
                "body": payload["body"],
            }
        },
    }


def _item_title(title: object, idea_id: object) -> str:
    base = str(title).strip() if title else str(idea_id or "Generated TactSpec").strip()
    return f"[Max] {base}"


def _item_body(tact_spec: dict[str, Any]) -> str:
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
        _text_or_placeholder(project.get("summary")),
        "",
        "## Source",
        f"- Idea ID: {_text_or_placeholder(source.get('idea_id'))}",
        f"- Status: {_text_or_placeholder(source.get('status'))}",
        f"- Domain: {_text_or_placeholder(source.get('domain'))}",
        f"- Category: {_text_or_placeholder(source.get('category'))}",
        "",
        "## Problem",
        _text_or_placeholder(problem.get("statement")),
        "",
        "## Solution",
        _text_or_placeholder(solution.get("approach")),
        "",
        "## Evaluation",
        f"- Recommendation: {_text_or_placeholder(evaluation.get('recommendation'))}",
        f"- Overall score: {_score_text(evaluation.get('overall_score'))}",
        "",
        "## Validation Plan",
        _text_or_placeholder(execution.get("validation_plan")),
        "",
        "## MVP Scope",
    ]
    lines.extend(_bullet_list(execution.get("mvp_scope")))
    lines.extend(
        [
            "",
            "## Evidence",
            f"- Rationale: {_text_or_placeholder(evidence.get('rationale'))}",
            f"- Insights: {', '.join(evidence.get('insight_ids') or []) or 'None'}",
            f"- Signals: {', '.join(evidence.get('signal_ids') or []) or 'None'}",
            f"- Source ideas: {', '.join(evidence.get('source_idea_ids') or []) or 'None'}",
            "",
            "## TactSpec Preview",
            "```json",
            json.dumps(tact_spec, indent=2, sort_keys=True),
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


def _text_or_placeholder(value: object) -> str:
    text = str(value).strip() if value else ""
    return text or "Not specified"


def _score_text(value: object) -> str:
    if isinstance(value, int | float):
        return f"{value:.1f}"
    return _text_or_placeholder(value)


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise GitHubProjectPublishError(message)
    return text


def _optional_string(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(
    response: httpx.Response,
    *,
    token: str | None,
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise GitHubProjectPublishError(
            _redact("GitHub Project publish failed: response was not valid JSON", token),
            status_code=response.status_code,
            attempts=attempts,
        ) from exc
    return body if isinstance(body, dict) else {}


def _graphql_errors_preview(errors: list[Any]) -> str:
    messages: list[str] = []
    for error in errors:
        if isinstance(error, dict) and error.get("message"):
            messages.append(str(error["message"]))
        elif error:
            messages.append(str(error))
    return "; ".join(messages) or "unknown GraphQL error"


def _project_item_from_response(body: dict[str, Any]) -> dict[str, Any] | None:
    data = body.get("data")
    if not isinstance(data, dict):
        return None
    result = data.get("addProjectV2DraftIssue")
    if not isinstance(result, dict):
        return None
    item = result.get("projectItem")
    return item if isinstance(item, dict) else None


def _project_item_url(item: dict[str, Any]) -> str | None:
    for candidate in (item.get("url"), item.get("resourcePath")):
        text = _optional_string(candidate)
        if text:
            return text
    content = item.get("content")
    if isinstance(content, dict):
        return _optional_string(content.get("url"))
    return None


def _attempt(
    endpoint: str,
    *,
    status_code: int | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    attempt: dict[str, Any] = {
        "method": "POST",
        "url": redact_url(endpoint),
        "status_code": status_code,
    }
    if error:
        attempt["error"] = error
    return attempt


def redact_url(url: str) -> str:
    """Redact credentials, query strings, and fragments from a URL."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "[redacted]"
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    netloc = f"***@{host}" if parts.username or parts.password else host
    query = "[redacted]" if parts.query else ""
    fragment = "[redacted]" if parts.fragment else ""
    return urlunsplit((parts.scheme, netloc, parts.path, query, fragment))


def _redact(message: str, token: str | None) -> str:
    if token:
        message = message.replace(token, "[redacted]")
    return message

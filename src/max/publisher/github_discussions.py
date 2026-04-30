"""GitHub Discussions publisher for generated idea and design briefs."""

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


class GitHubDiscussionPublishError(RuntimeError):
    """Raised when a GitHub Discussion publish cannot be completed."""

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
class GitHubDiscussionPayload:
    """GitHub Discussion creation payload plus Max-specific metadata."""

    owner: str
    repo: str
    category_id: str
    title: str
    body: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable discussion payload."""
        return {
            "owner": self.owner,
            "repo": self.repo,
            "category_id": self.category_id,
            "title": self.title,
            "body": self.body,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class GitHubDiscussionPublishResult:
    """Summary of a GitHub Discussion publish or dry run."""

    status_code: int | None
    repository: str
    discussion_id: str | None
    discussion_url: str | None
    dry_run: bool
    payload: dict[str, Any]
    attempts: list[dict[str, Any]]


class GitHubDiscussionPublisher:
    """Build and optionally create GitHub Discussions from Max briefs."""

    def __init__(
        self,
        owner: str,
        repo: str,
        category_id: str,
        *,
        token: str | None = None,
        graphql_endpoint: str = DEFAULT_GITHUB_GRAPHQL_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.owner = _required_text(owner, "GitHub discussion owner is required")
        self.repo = _required_text(repo, "GitHub discussion repo is required")
        self.category_id = _required_text(category_id, "GitHub discussion category_id is required")
        self.token = token
        self.graphql_endpoint = _required_text(
            graphql_endpoint,
            "GitHub GraphQL endpoint is required",
        ).rstrip("/")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        owner: str | None = None,
        repo: str | None = None,
        category_id: str | None = None,
        token: str | None = None,
        graphql_endpoint: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> GitHubDiscussionPublisher:
        """Create a publisher using explicit values first, then environment variables."""
        env_owner, env_repo = _repository_parts(os.getenv("GITHUB_REPOSITORY"))
        resolved_owner = owner or os.getenv("GITHUB_DISCUSSION_OWNER") or env_owner
        resolved_repo = repo or os.getenv("GITHUB_DISCUSSION_REPO") or env_repo
        resolved_category_id = category_id or os.getenv("GITHUB_DISCUSSION_CATEGORY_ID")
        if not resolved_owner:
            raise GitHubDiscussionPublishError(
                "GitHub discussion owner is required; pass owner or set GITHUB_DISCUSSION_OWNER"
            )
        if not resolved_repo:
            raise GitHubDiscussionPublishError(
                "GitHub discussion repo is required; pass repo or set GITHUB_DISCUSSION_REPO"
            )
        if not resolved_category_id:
            raise GitHubDiscussionPublishError(
                "GitHub discussion category_id is required; pass category_id or set "
                "GITHUB_DISCUSSION_CATEGORY_ID"
            )
        return cls(
            resolved_owner,
            resolved_repo,
            resolved_category_id,
            token=token or os.getenv("GITHUB_TOKEN"),
            graphql_endpoint=graphql_endpoint
            or os.getenv("GITHUB_GRAPHQL_URL", DEFAULT_GITHUB_GRAPHQL_URL),
            timeout=timeout,
            client=client,
        )

    @property
    def repository(self) -> str:
        """Return the owner/repo repository slug."""
        return f"{self.owner}/{self.repo}"

    def build_discussion_payload(self, tact_spec: dict[str, Any]) -> GitHubDiscussionPayload:
        """Convert a generated TactSpec preview into a GitHub Discussion payload."""
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")
        metadata = {
            "publisher": "max.github_discussions",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "idea"),
            "idea_id": source.get("idea_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "repository": self.repository,
            "category_id": self.category_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return GitHubDiscussionPayload(
            owner=self.owner,
            repo=self.repo,
            category_id=self.category_id,
            title=_discussion_title(project.get("title"), source.get("idea_id")),
            body=_discussion_body(tact_spec),
            metadata=metadata,
        )

    def build_design_brief_payload(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str,
    ) -> GitHubDiscussionPayload:
        """Convert a persisted design brief Markdown export into a Discussion payload."""
        brief_id = design_brief.get("id")
        title = design_brief.get("title") or brief_id or "Design Brief"
        metadata = {
            "publisher": "max.github_discussions",
            "source_system": "max",
            "source_type": "design_brief",
            "design_brief_id": brief_id,
            "domain": design_brief.get("domain"),
            "theme": design_brief.get("theme"),
            "lead_idea_id": design_brief.get("lead_idea_id"),
            "source_idea_ids": _source_idea_ids(design_brief.get("source_idea_ids")),
            "repository": self.repository,
            "category_id": self.category_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return GitHubDiscussionPayload(
            owner=self.owner,
            repo=self.repo,
            category_id=self.category_id,
            title=f"[Max] {str(title).strip()}",
            body=markdown,
            metadata=metadata,
        )

    def build_create_discussion_request(
        self,
        payload: GitHubDiscussionPayload | dict[str, Any],
        *,
        repository_id: str,
    ) -> dict[str, Any]:
        """Build the GitHub GraphQL createDiscussion request body."""
        payload_dict = payload.to_dict() if isinstance(payload, GitHubDiscussionPayload) else dict(payload)
        return _create_discussion_request(payload_dict, repository_id=repository_id)

    def publish(
        self,
        tact_spec: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> GitHubDiscussionPublishResult:
        """Build the discussion payload and optionally create it in GitHub."""
        return self.publish_payload(self.build_discussion_payload(tact_spec), dry_run=dry_run)

    def publish_design_brief(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str,
        dry_run: bool = True,
    ) -> GitHubDiscussionPublishResult:
        """Build the design brief discussion payload and optionally create it in GitHub."""
        return self.publish_payload(
            self.build_design_brief_payload(design_brief, markdown=markdown),
            dry_run=dry_run,
        )

    def publish_payload(
        self,
        payload: GitHubDiscussionPayload | dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> GitHubDiscussionPublishResult:
        """Create a GitHub Discussion from a prebuilt payload."""
        payload_dict = payload.to_dict() if isinstance(payload, GitHubDiscussionPayload) else dict(payload)
        if dry_run:
            return GitHubDiscussionPublishResult(
                status_code=None,
                repository=self.repository,
                discussion_id=None,
                discussion_url=None,
                dry_run=True,
                payload=payload_dict,
                attempts=[],
            )

        if not self.token:
            raise GitHubDiscussionPublishError(
                "GITHUB_TOKEN is required for live GitHub Discussion publishing; use dry_run to preview"
            )

        attempts: list[dict[str, Any]] = []
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            repository_id, lookup_status_code = self._repository_id(client, attempts)
            response = self._post_graphql(
                client,
                _create_discussion_request(payload_dict, repository_id=repository_id),
                attempts,
            )
        finally:
            if close_client:
                client.close()

        body = _json_response(response, token=self.token, attempts=attempts)
        errors = body.get("errors")
        if isinstance(errors, list) and errors:
            raise GitHubDiscussionPublishError(
                _redact(
                    f"GitHub Discussion publish failed: {_graphql_errors_preview(errors)}",
                    self.token,
                ),
                status_code=response.status_code,
                attempts=attempts,
            )

        discussion = _discussion_from_response(body)
        if not discussion:
            raise GitHubDiscussionPublishError(
                "GitHub Discussion publish failed: response did not include created discussion",
                status_code=response.status_code,
                attempts=attempts,
            )

        discussion_id = _optional_string(discussion.get("id"))
        discussion_url = _optional_string(discussion.get("url"))
        return GitHubDiscussionPublishResult(
            status_code=response.status_code or lookup_status_code,
            repository=self.repository,
            discussion_id=discussion_id,
            discussion_url=discussion_url,
            dry_run=False,
            payload={
                **payload_dict,
                "metadata": {
                    **payload_dict["metadata"],
                    "github_discussion_id": discussion_id,
                    "github_discussion_url": discussion_url,
                    "github_repository_id": repository_id,
                },
            },
            attempts=attempts,
        )

    def _repository_id(
        self,
        client: httpx.Client,
        attempts: list[dict[str, Any]],
    ) -> tuple[str, int]:
        response = self._post_graphql(
            client,
            _repository_id_request(owner=self.owner, repo=self.repo),
            attempts,
        )
        body = _json_response(response, token=self.token, attempts=attempts)
        errors = body.get("errors")
        if isinstance(errors, list) and errors:
            raise GitHubDiscussionPublishError(
                _redact(
                    f"GitHub repository lookup failed: {_graphql_errors_preview(errors)}",
                    self.token,
                ),
                status_code=response.status_code,
                attempts=attempts,
            )
        repository = body.get("data", {}).get("repository") if isinstance(body.get("data"), dict) else None
        repository_id = _optional_string(repository.get("id")) if isinstance(repository, dict) else None
        if not repository_id:
            raise GitHubDiscussionPublishError(
                f"GitHub repository lookup failed: repository {self.repository} was not found",
                status_code=response.status_code,
                attempts=attempts,
            )
        return repository_id, response.status_code

    def _post_graphql(
        self,
        client: httpx.Client,
        request_body: dict[str, Any],
        attempts: list[dict[str, Any]],
    ) -> httpx.Response:
        try:
            response = client.post(
                self.graphql_endpoint,
                json=request_body,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                    "User-Agent": "max-github-discussions-publisher/1",
                },
                timeout=self.timeout,
            )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            attempts.append(_attempt(self.graphql_endpoint, error=str(exc)))
            raise GitHubDiscussionPublishError(
                _redact(
                    f"GitHub Discussion publish failed for {redact_url(self.graphql_endpoint)}: {exc}",
                    self.token,
                ),
                attempts=attempts,
            ) from exc

        attempts.append(_attempt(self.graphql_endpoint, status_code=response.status_code))
        if not 200 <= response.status_code < 300:
            raise GitHubDiscussionPublishError(
                _redact(
                    f"GitHub Discussion publish failed with HTTP {response.status_code}: "
                    f"{_response_body_preview(response)}",
                    self.token,
                ),
                status_code=response.status_code,
                attempts=attempts,
            )
        return response


GitHubDiscussionsPublisher = GitHubDiscussionPublisher


REPOSITORY_ID_QUERY = """
query MaxDiscussionRepository($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    id
  }
}
""".strip()


CREATE_DISCUSSION_MUTATION = """
mutation MaxCreateDiscussion($input: CreateDiscussionInput!) {
  createDiscussion(input: $input) {
    discussion {
      id
      url
      title
    }
  }
}
""".strip()


def _repository_id_request(*, owner: str, repo: str) -> dict[str, Any]:
    return {
        "query": REPOSITORY_ID_QUERY,
        "variables": {
            "owner": owner,
            "name": repo,
        },
    }


def _create_discussion_request(payload: dict[str, Any], *, repository_id: str) -> dict[str, Any]:
    return {
        "query": CREATE_DISCUSSION_MUTATION,
        "variables": {
            "input": {
                "repositoryId": repository_id,
                "categoryId": payload["category_id"],
                "title": payload["title"],
                "body": payload["body"],
            }
        },
    }


def _discussion_title(title: object, idea_id: object) -> str:
    base = str(title).strip() if title else str(idea_id or "Generated Idea").strip()
    return f"[Max] {base}"


def _discussion_body(tact_spec: dict[str, Any]) -> str:
    project = _dict_value(tact_spec, "project")
    problem = _dict_value(tact_spec, "problem")
    solution = _dict_value(tact_spec, "solution")
    execution = _dict_value(tact_spec, "execution")
    evidence = _dict_value(tact_spec, "evidence")
    source = _dict_value(tact_spec, "source")
    evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}

    lines = [
        f"# {project.get('title') or source.get('idea_id') or 'Generated Idea'}",
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


def _source_idea_ids(value: object) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list | tuple | set):
        return []

    values: list[str] = []
    for candidate in value:
        text = candidate.strip() if isinstance(candidate, str) else ""
        if text and text not in values:
            values.append(text)
    return values


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise GitHubDiscussionPublishError(message)
    return text


def _optional_string(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _repository_parts(repository: str | None) -> tuple[str | None, str | None]:
    if not repository or "/" not in repository:
        return None, None
    owner, repo = repository.split("/", 1)
    owner = owner.strip()
    repo = repo.strip()
    return (owner or None, repo or None)


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
        raise GitHubDiscussionPublishError(
            _redact("GitHub Discussion publish failed: response was not valid JSON", token),
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


def _discussion_from_response(body: dict[str, Any]) -> dict[str, Any] | None:
    data = body.get("data")
    if not isinstance(data, dict):
        return None
    result = data.get("createDiscussion")
    if not isinstance(result, dict):
        return None
    discussion = result.get("discussion")
    return discussion if isinstance(discussion, dict) else None


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

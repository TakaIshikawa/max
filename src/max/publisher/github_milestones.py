"""GitHub Milestones publisher for design briefs."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx


DEFAULT_GITHUB_API_URL = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 2
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
SECRET_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "client_secret",
    "key",
    "password",
    "secret",
    "sig",
    "signature",
    "token",
}


class GitHubMilestonePublishError(RuntimeError):
    """Raised when a GitHub milestone publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(_redact_text(message))
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubMilestonePayload:
    """GitHub milestone creation payload plus Max-specific metadata."""

    title: str
    description: str
    state: str
    due_on: str | None
    labels: list[str]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable milestone payload preview."""
        payload: dict[str, Any] = {
            "title": self.title,
            "description": self.description,
            "state": self.state,
            "labels": self.labels,
            "metadata": self.metadata,
        }
        if self.due_on:
            payload["due_on"] = self.due_on
        return payload


@dataclass(frozen=True)
class GitHubMilestonePublishResult:
    """Summary of a GitHub milestone publish or dry run."""

    status_code: int | None
    repository: str
    milestone_number: int | None
    milestone_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class GitHubMilestonePublisher:
    """Build and optionally create GitHub repository milestones from design briefs."""

    def __init__(
        self,
        repository: str,
        *,
        token: str | None = None,
        api_url: str = DEFAULT_GITHUB_API_URL,
        labels: list[str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = 0.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.repository = _validate_repository(repository)
        self.token = _optional_text(token)
        self.api_url = _required_text(api_url, "GitHub api_url is required").rstrip("/")
        self.labels = labels or []
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_backoff = max(0.0, retry_backoff)
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
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.Client | None = None,
    ) -> GitHubMilestonePublisher:
        """Create a publisher using explicit values first, then environment variables."""
        resolved_repository = repository or os.getenv("GITHUB_REPOSITORY")
        if not resolved_repository:
            raise GitHubMilestonePublishError(
                "GitHub repository is required; pass repository or set GITHUB_REPOSITORY"
            )
        return cls(
            resolved_repository,
            token=token or os.getenv("GITHUB_TOKEN"),
            api_url=api_url or os.getenv("GITHUB_API_URL", DEFAULT_GITHUB_API_URL),
            labels=labels,
            timeout=timeout,
            max_retries=max_retries,
            client=client,
        )

    @property
    def milestone_endpoint(self) -> str:
        """Return the GitHub API endpoint used for milestone creation."""
        return f"{self.api_url}/repos/{self.repository}/milestones"

    def build_design_brief_payload(
        self,
        design_brief: dict[str, Any],
        *,
        description: str,
        title: str | None = None,
        state: str = "open",
        due_on: str | None = None,
        include_source_ids: bool = False,
    ) -> GitHubMilestonePayload:
        """Convert a persisted design brief into a GitHub milestone payload."""
        brief_id = design_brief.get("id")
        milestone_title = _required_text(
            title or str(design_brief.get("title") or brief_id or "Design Brief"),
            "GitHub milestone title is required",
        )
        milestone_state = _validate_state(state)
        source_idea_ids = _source_idea_ids(design_brief.get("source_idea_ids"))
        metadata = {
            "publisher": "max.github_milestones",
            "source_system": "max",
            "source_type": "design_brief",
            "design_brief_id": brief_id,
            "domain": design_brief.get("domain"),
            "theme": design_brief.get("theme"),
            "lead_idea_id": design_brief.get("lead_idea_id"),
            "source_idea_ids": source_idea_ids,
            "repository": self.repository,
            "state": milestone_state,
            "due_on": due_on,
            "labels": list(self.labels),
            "include_source_ids": include_source_ids,
        }
        return GitHubMilestonePayload(
            title=milestone_title,
            description=description,
            state=milestone_state,
            due_on=_optional_text(due_on),
            labels=list(self.labels),
            metadata=metadata,
        )

    def publish_design_brief(
        self,
        design_brief: dict[str, Any],
        *,
        description: str,
        title: str | None = None,
        state: str = "open",
        due_on: str | None = None,
        include_source_ids: bool = False,
        dry_run: bool = True,
    ) -> GitHubMilestonePublishResult:
        """Build a design brief milestone payload and optionally create it in GitHub."""
        return self.publish_milestone_payload(
            self.build_design_brief_payload(
                design_brief,
                description=description,
                title=title,
                state=state,
                due_on=due_on,
                include_source_ids=include_source_ids,
            ).to_dict(),
            dry_run=dry_run,
        )

    def publish_milestone_payload(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> GitHubMilestonePublishResult:
        """Publish a caller-rendered GitHub milestone payload."""
        milestone_payload = {
            **payload,
            "state": _validate_state(str(payload.get("state") or "open")),
            "labels": _merge_labels(list(payload.get("labels") or []), self.labels),
            "metadata": {
                **(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}),
                "repository": self.repository,
            },
        }
        if dry_run:
            return GitHubMilestonePublishResult(
                status_code=None,
                repository=self.repository,
                milestone_number=None,
                milestone_url=None,
                dry_run=True,
                payload=milestone_payload,
            )

        if not self.token:
            raise GitHubMilestonePublishError(
                "GITHUB_TOKEN is required for live GitHub milestone publishing; use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = self._post_with_retries(client, milestone_payload)
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise GitHubMilestonePublishError(
                f"GitHub milestone publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        milestone_number = body.get("number") if isinstance(body.get("number"), int) else None
        milestone_url = str(body["html_url"]) if body.get("html_url") else None
        return GitHubMilestonePublishResult(
            status_code=response.status_code,
            repository=self.repository,
            milestone_number=milestone_number,
            milestone_url=milestone_url,
            dry_run=False,
            payload={
                **milestone_payload,
                "metadata": {
                    **milestone_payload["metadata"],
                    "github_milestone_number": milestone_number,
                    "github_milestone_url": milestone_url,
                },
            },
        )

    def _post_with_retries(
        self,
        client: httpx.Client,
        payload: dict[str, Any],
    ) -> httpx.Response:
        last_response: httpx.Response | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = client.post(
                    self.milestone_endpoint,
                    json=_github_milestone_request_payload(payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                message = _redact_text(str(exc))
                raise GitHubMilestonePublishError(
                    f"GitHub milestone publish failed for "
                    f"{_redact_url(self.milestone_endpoint)}: {message}"
                ) from exc

            last_response = response
            if response.status_code not in TRANSIENT_STATUS_CODES or attempt >= self.max_retries:
                return response
            if self.retry_backoff:
                time.sleep(self.retry_backoff * (attempt + 1))

        return last_response

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "max-github-milestones-publisher/1",
            "X-GitHub-Api-Version": "2022-11-28",
        }


GitHubMilestonesPublisher = GitHubMilestonePublisher


def _github_milestone_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    request_payload = {
        "title": payload["title"],
        "description": payload["description"],
        "state": payload.get("state") or "open",
    }
    if payload.get("due_on"):
        request_payload["due_on"] = payload["due_on"]
    return request_payload


def _validate_repository(repository: str) -> str:
    value = _required_text(repository, "GitHub repository is required")
    if value.count("/") != 1 or any(not part for part in value.split("/", 1)):
        raise GitHubMilestonePublishError("GitHub repository must be in owner/repo format")
    return value


def _validate_state(state: str) -> str:
    value = _required_text(state, "GitHub milestone state is required").lower()
    if value not in {"open", "closed"}:
        raise GitHubMilestonePublishError("GitHub milestone state must be open or closed")
    return value


def _merge_labels(labels: list[str], extra_labels: list[str]) -> list[str]:
    unique: list[str] = []
    for label in [*labels, *extra_labels]:
        value = _label_value(label)
        if value and value not in unique:
            unique.append(value)
    return unique


def _label_value(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower().replace("_", "-").replace(" ", "-")
    safe = "".join(ch for ch in text if ch.isalnum() or ch in "-./")
    return safe[:50]


def _source_idea_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise GitHubMilestonePublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    return _redact_text(_truncate(response.text.strip(), limit=limit))


def _truncate(text: str, *, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _redact_text(text: str) -> str:
    redacted = re.sub(
        r"(?i)(token|password|secret|api[_-]?key|authorization)=([^&\s]+)",
        r"\1=<redacted>",
        text,
    )
    redacted = re.sub(
        r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+",
        r"\1<redacted>",
        redacted,
    )
    for match in re.findall(r"https?://[^\s)>\"]+", redacted):
        redacted = redacted.replace(match, _redact_url(match))
    return redacted


def _redact_url(url: str) -> str:
    parts = urlsplit(url)
    query = urlencode(
        [
            (key, "<redacted>" if key.lower() in SECRET_QUERY_KEYS else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))

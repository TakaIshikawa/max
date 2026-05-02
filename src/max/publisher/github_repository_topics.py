"""GitHub repository topics publisher for Max ideas and design briefs."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx


DEFAULT_GITHUB_API_URL = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_GITHUB_REPOSITORY_TOPICS = 20
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


class GitHubRepositoryTopicPublishError(RuntimeError):
    """Raised when GitHub repository topics cannot be published."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(_redact_text(message))
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubRepositoryTopicPayload:
    """GitHub repository topic payload plus Max-specific metadata."""

    repository: str
    topics: list[str]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable repository topic payload preview."""
        return {
            "repository": self.repository,
            "topics": self.topics,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class GitHubRepositoryTopicPublishResult:
    """Summary of a GitHub repository topic publish or dry run."""

    status_code: int | None
    owner: str
    repo: str
    repository: str
    topics: list[str]
    api_url: str
    endpoint: str
    dry_run: bool
    payload: dict[str, Any]


class GitHubRepositoryTopicsPublisher:
    """Build and optionally replace GitHub repository topics."""

    def __init__(
        self,
        repository: str,
        *,
        token: str | None = None,
        api_url: str = DEFAULT_GITHUB_API_URL,
        topics: list[str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.repository = _validate_repository(repository)
        self.owner, self.repo = self.repository.split("/", 1)
        self.token = _optional_text(token)
        self.api_url = _required_text(api_url, "GitHub api_url is required").rstrip("/")
        self.topics = _merge_topics(topics or [])
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        repository: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        topics: list[str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> GitHubRepositoryTopicsPublisher:
        """Create a publisher using explicit values first, then environment variables."""
        resolved_repository = repository or os.getenv("GITHUB_REPOSITORY")
        if not resolved_repository:
            raise GitHubRepositoryTopicPublishError(
                "GitHub repository is required; pass repository or set GITHUB_REPOSITORY"
            )
        return cls(
            resolved_repository,
            token=token or os.getenv("GITHUB_TOKEN"),
            api_url=api_url or os.getenv("GITHUB_API_URL", DEFAULT_GITHUB_API_URL),
            topics=topics,
            timeout=timeout,
            client=client,
        )

    @property
    def topics_endpoint(self) -> str:
        """Return the GitHub API endpoint used for replacing repository topics."""
        return f"{self.api_url}/repos/{self.repository}/topics"

    def build_topic_payload(
        self,
        artifact: dict[str, Any],
        *,
        topics: list[str] | None = None,
    ) -> GitHubRepositoryTopicPayload:
        """Convert a Max idea or artifact into GitHub repository topics."""
        source = _dict_value(artifact, "source")
        quality = _dict_value(artifact, "quality")
        project = _dict_value(artifact, "project")
        evaluation = artifact.get("evaluation") if isinstance(artifact.get("evaluation"), dict) else {}
        generated_topics = _topics_from_artifact(
            source=source,
            quality=quality,
            project=project,
            evaluation=evaluation,
        )
        merged_topics = _merge_topics(generated_topics, self.topics, topics or [])
        metadata = {
            "publisher": "max.github_repository_topics",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "idea"),
            "idea_id": source.get("idea_id"),
            "schema_version": artifact.get("schema_version"),
            "kind": artifact.get("kind"),
            "repository": self.repository,
        }
        return GitHubRepositoryTopicPayload(
            repository=self.repository,
            topics=merged_topics,
            metadata=metadata,
        )

    def build_design_brief_payload(
        self,
        design_brief: dict[str, Any],
        *,
        topics: list[str] | None = None,
    ) -> GitHubRepositoryTopicPayload:
        """Convert a persisted design brief into GitHub repository topics."""
        brief = _design_brief_dict(design_brief)
        generated_topics = [
            "max",
            "design-brief",
            brief.get("domain"),
            brief.get("theme"),
            brief.get("design_status"),
        ]
        merged_topics = _merge_topics(generated_topics, self.topics, topics or [])
        metadata = {
            "publisher": "max.github_repository_topics",
            "source_system": "max",
            "source_type": "design_brief",
            "design_brief_id": brief.get("id"),
            "domain": brief.get("domain"),
            "theme": brief.get("theme"),
            "lead_idea_id": brief.get("lead_idea_id"),
            "source_idea_ids": _source_idea_ids(brief.get("source_idea_ids")),
            "repository": self.repository,
        }
        return GitHubRepositoryTopicPayload(
            repository=self.repository,
            topics=merged_topics,
            metadata=metadata,
        )

    def publish(
        self,
        artifact: dict[str, Any],
        *,
        dry_run: bool = True,
        topics: list[str] | None = None,
    ) -> GitHubRepositoryTopicPublishResult:
        """Build topics from a Max artifact and optionally apply them to GitHub."""
        return self.publish_topic_payload(
            self.build_topic_payload(artifact, topics=topics).to_dict(),
            dry_run=dry_run,
        )

    def publish_design_brief(
        self,
        design_brief: dict[str, Any],
        *,
        dry_run: bool = True,
        topics: list[str] | None = None,
    ) -> GitHubRepositoryTopicPublishResult:
        """Build topics from a design brief and optionally apply them to GitHub."""
        return self.publish_topic_payload(
            self.build_design_brief_payload(design_brief, topics=topics).to_dict(),
            dry_run=dry_run,
        )

    def publish_topics(
        self,
        topics: list[str],
        *,
        dry_run: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> GitHubRepositoryTopicPublishResult:
        """Publish caller-supplied repository topics."""
        return self.publish_topic_payload(
            {
                "repository": self.repository,
                "topics": topics,
                "metadata": metadata or {},
            },
            dry_run=dry_run,
        )

    def publish_topic_payload(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> GitHubRepositoryTopicPublishResult:
        """Publish a caller-rendered GitHub repository topic payload."""
        topics = _merge_topics(list(payload.get("topics") or []), self.topics)
        _validate_topics(topics)
        publish_payload = {
            **payload,
            "repository": self.repository,
            "topics": topics,
            "metadata": {
                **(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}),
                "repository": self.repository,
            },
        }
        endpoint = self.topics_endpoint
        if dry_run:
            return self._result(
                status_code=None,
                topics=topics,
                endpoint=endpoint,
                dry_run=True,
                payload=publish_payload,
            )

        if not self.token:
            raise GitHubRepositoryTopicPublishError(
                "GITHUB_TOKEN is required for live GitHub repository topic publishing; use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.put(
                    endpoint,
                    json=_github_repository_topics_request_payload(publish_payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise GitHubRepositoryTopicPublishError(
                    f"GitHub repository topic publish failed for {_redact_url(endpoint)}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise GitHubRepositoryTopicPublishError(
                f"GitHub repository topic publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        return self._result(
            status_code=response.status_code,
            topics=topics,
            endpoint=endpoint,
            dry_run=False,
            payload={
                **publish_payload,
                "metadata": {
                    **publish_payload["metadata"],
                    "github_repository_topics": topics,
                    "github_repository_topics_endpoint": endpoint,
                },
            },
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "max-github-repository-topics-publisher/1",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _result(
        self,
        *,
        status_code: int | None,
        topics: list[str],
        endpoint: str,
        dry_run: bool,
        payload: dict[str, Any],
    ) -> GitHubRepositoryTopicPublishResult:
        return GitHubRepositoryTopicPublishResult(
            status_code=status_code,
            owner=self.owner,
            repo=self.repo,
            repository=self.repository,
            topics=topics,
            api_url=self.api_url,
            endpoint=endpoint,
            dry_run=dry_run,
            payload=payload,
        )


GitHubRepositoryTopicPublisher = GitHubRepositoryTopicsPublisher


def _github_repository_topics_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {"names": list(payload["topics"])}


def _topics_from_artifact(
    *,
    source: dict[str, Any],
    quality: dict[str, Any],
    project: dict[str, Any],
    evaluation: dict[str, Any],
) -> list[object]:
    topics: list[object] = [
        "max",
        "tact-spec",
        source.get("type") or "idea",
        source.get("category"),
        source.get("domain"),
        source.get("status"),
        project.get("title"),
        evaluation.get("recommendation"),
    ]
    topics.extend(quality.get("rejection_tags") or [])
    return topics


def _merge_topics(*topic_groups: list[object]) -> list[str]:
    unique: list[str] = []
    for topic_group in topic_groups:
        for topic in topic_group:
            value = _topic_value(topic)
            if value and value not in unique:
                unique.append(value)
    return unique


def _topic_value(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower().replace("_", "-")
    text = re.sub(r"\s+", "-", text)
    safe = "".join(ch for ch in text if ch.isalnum() or ch == "-").strip("-")
    safe = re.sub(r"-{2,}", "-", safe)
    if not safe:
        return ""
    return safe[:50]


def _validate_topics(topics: list[str]) -> None:
    if not topics:
        raise GitHubRepositoryTopicPublishError(
            "At least one GitHub repository topic is required"
        )
    if len(topics) > MAX_GITHUB_REPOSITORY_TOPICS:
        raise GitHubRepositoryTopicPublishError(
            f"GitHub repositories support at most {MAX_GITHUB_REPOSITORY_TOPICS} topics"
        )


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _design_brief_dict(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("design_brief")
    return nested if isinstance(nested, dict) else payload


def _source_idea_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    unique: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in unique:
            unique.append(text)
    return unique


def _validate_repository(repository: str) -> str:
    value = _required_text(repository, "GitHub repository is required")
    if value.count("/") != 1 or any(not part for part in value.split("/", 1)):
        raise GitHubRepositoryTopicPublishError(
            "GitHub repository must be in owner/repo format"
        )
    return value


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise GitHubRepositoryTopicPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = _redact_text(response.text.strip())
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

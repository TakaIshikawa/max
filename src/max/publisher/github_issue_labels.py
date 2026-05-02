"""GitHub issue label publisher for Max ideas and design briefs."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx


DEFAULT_GITHUB_API_URL = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS = 10.0
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


class GitHubIssueLabelPublishError(RuntimeError):
    """Raised when a GitHub issue label publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(_redact_text(message))
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubIssueLabelPayload:
    """GitHub issue label payload plus Max-specific metadata."""

    repository: str
    issue_number: int
    labels: list[str]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable issue label payload preview."""
        return {
            "repository": self.repository,
            "issue_number": self.issue_number,
            "labels": self.labels,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class GitHubIssueLabelPublishResult:
    """Summary of a GitHub issue label publish or dry run."""

    status_code: int | None
    owner: str
    repo: str
    repository: str
    issue_number: int
    labels: list[str]
    api_url: str
    endpoint: str
    dry_run: bool
    payload: dict[str, Any]


class GitHubIssueLabelsPublisher:
    """Build and optionally apply labels to existing GitHub issues."""

    def __init__(
        self,
        repository: str,
        *,
        issue_number: int | str | None = None,
        token: str | None = None,
        api_url: str = DEFAULT_GITHUB_API_URL,
        labels: list[str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.repository = _validate_repository(repository)
        self.owner, self.repo = self.repository.split("/", 1)
        self.issue_number = (
            _validate_issue_number(issue_number) if issue_number is not None else None
        )
        self.token = _optional_text(token)
        self.api_url = _required_text(api_url, "GitHub api_url is required").rstrip("/")
        self.labels = _merge_labels(labels or [])
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
        labels: list[str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> GitHubIssueLabelsPublisher:
        """Create a publisher using explicit values first, then environment variables."""
        resolved_repository = repository or os.getenv("GITHUB_REPOSITORY")
        if not resolved_repository:
            raise GitHubIssueLabelPublishError(
                "GitHub repository is required; pass repository or set GITHUB_REPOSITORY"
            )
        return cls(
            resolved_repository,
            issue_number=issue_number or os.getenv("GITHUB_ISSUE_NUMBER"),
            token=token or os.getenv("GITHUB_TOKEN"),
            api_url=api_url or os.getenv("GITHUB_API_URL", DEFAULT_GITHUB_API_URL),
            labels=labels,
            timeout=timeout,
            client=client,
        )

    def labels_endpoint(self, issue_number: int | str | None = None) -> str:
        """Return the GitHub API endpoint used for adding issue labels."""
        resolved_issue_number = self._resolve_issue_number(issue_number)
        return f"{self.api_url}/repos/{self.repository}/issues/{resolved_issue_number}/labels"

    def build_label_payload(
        self,
        artifact: dict[str, Any],
        *,
        issue_number: int | str | None = None,
        labels: list[str] | None = None,
    ) -> GitHubIssueLabelPayload:
        """Convert a Max idea or artifact into labels for an existing issue."""
        resolved_issue_number = self._resolve_issue_number(issue_number)
        source = _dict_value(artifact, "source")
        quality = _dict_value(artifact, "quality")
        evaluation = artifact.get("evaluation") if isinstance(artifact.get("evaluation"), dict) else {}
        generated_labels = _labels_from_artifact(
            source=source,
            quality=quality,
            evaluation=evaluation,
        )
        merged_labels = _merge_labels(generated_labels, self.labels, labels or [])
        metadata = {
            "publisher": "max.github_issue_labels",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "idea"),
            "idea_id": source.get("idea_id"),
            "schema_version": artifact.get("schema_version"),
            "kind": artifact.get("kind"),
            "repository": self.repository,
            "issue_number": resolved_issue_number,
        }
        return GitHubIssueLabelPayload(
            repository=self.repository,
            issue_number=resolved_issue_number,
            labels=merged_labels,
            metadata=metadata,
        )

    def build_design_brief_payload(
        self,
        design_brief: dict[str, Any],
        *,
        issue_number: int | str | None = None,
        labels: list[str] | None = None,
    ) -> GitHubIssueLabelPayload:
        """Convert a persisted design brief into labels for an existing issue."""
        resolved_issue_number = self._resolve_issue_number(issue_number)
        brief = _design_brief_dict(design_brief)
        brief_id = brief.get("id")
        generated_labels = [
            "max",
            "design-brief",
            _label_value(brief.get("domain")),
            _label_value(brief.get("theme")),
            _label_value(brief.get("design_status"), prefix="status"),
        ]
        merged_labels = _merge_labels(generated_labels, self.labels, labels or [])
        metadata = {
            "publisher": "max.github_issue_labels",
            "source_system": "max",
            "source_type": "design_brief",
            "design_brief_id": brief_id,
            "domain": brief.get("domain"),
            "theme": brief.get("theme"),
            "lead_idea_id": brief.get("lead_idea_id"),
            "source_idea_ids": _source_idea_ids(brief.get("source_idea_ids")),
            "repository": self.repository,
            "issue_number": resolved_issue_number,
        }
        return GitHubIssueLabelPayload(
            repository=self.repository,
            issue_number=resolved_issue_number,
            labels=merged_labels,
            metadata=metadata,
        )

    def publish(
        self,
        artifact: dict[str, Any],
        *,
        dry_run: bool = True,
        issue_number: int | str | None = None,
        labels: list[str] | None = None,
    ) -> GitHubIssueLabelPublishResult:
        """Build labels from a Max artifact and optionally apply them to GitHub."""
        return self.publish_label_payload(
            self.build_label_payload(
                artifact,
                issue_number=issue_number,
                labels=labels,
            ).to_dict(),
            dry_run=dry_run,
        )

    def publish_design_brief(
        self,
        design_brief: dict[str, Any],
        *,
        dry_run: bool = True,
        issue_number: int | str | None = None,
        labels: list[str] | None = None,
    ) -> GitHubIssueLabelPublishResult:
        """Build labels from a design brief and optionally apply them to GitHub."""
        return self.publish_label_payload(
            self.build_design_brief_payload(
                design_brief,
                issue_number=issue_number,
                labels=labels,
            ).to_dict(),
            dry_run=dry_run,
        )

    def publish_label_payload(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> GitHubIssueLabelPublishResult:
        """Publish a caller-rendered GitHub issue label payload."""
        issue_number = _validate_issue_number(payload.get("issue_number"))
        labels = _merge_labels(list(payload.get("labels") or []), self.labels)
        if not labels:
            raise GitHubIssueLabelPublishError("At least one GitHub issue label is required")
        publish_payload = {
            **payload,
            "repository": self.repository,
            "issue_number": issue_number,
            "labels": labels,
            "metadata": {
                **(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}),
                "repository": self.repository,
                "issue_number": issue_number,
            },
        }
        endpoint = self.labels_endpoint(issue_number)
        if dry_run:
            return self._result(
                status_code=None,
                issue_number=issue_number,
                labels=labels,
                endpoint=endpoint,
                dry_run=True,
                payload=publish_payload,
            )

        if not self.token:
            raise GitHubIssueLabelPublishError(
                "GITHUB_TOKEN is required for live GitHub issue label publishing; use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    endpoint,
                    json=_github_issue_labels_request_payload(publish_payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise GitHubIssueLabelPublishError(
                    f"GitHub issue label publish failed for {_redact_url(endpoint)}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise GitHubIssueLabelPublishError(
                f"GitHub issue label publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        return self._result(
            status_code=response.status_code,
            issue_number=issue_number,
            labels=labels,
            endpoint=endpoint,
            dry_run=False,
            payload={
                **publish_payload,
                "metadata": {
                    **publish_payload["metadata"],
                    "github_issue_labels": labels,
                    "github_issue_labels_endpoint": endpoint,
                },
            },
        )

    def _resolve_issue_number(self, issue_number: int | str | None = None) -> int:
        resolved = issue_number if issue_number is not None else self.issue_number
        if resolved is None:
            raise GitHubIssueLabelPublishError(
                "GitHub issue number is required; pass issue_number or set GITHUB_ISSUE_NUMBER"
            )
        return _validate_issue_number(resolved)

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "max-github-issue-labels-publisher/1",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _result(
        self,
        *,
        status_code: int | None,
        issue_number: int,
        labels: list[str],
        endpoint: str,
        dry_run: bool,
        payload: dict[str, Any],
    ) -> GitHubIssueLabelPublishResult:
        return GitHubIssueLabelPublishResult(
            status_code=status_code,
            owner=self.owner,
            repo=self.repo,
            repository=self.repository,
            issue_number=issue_number,
            labels=labels,
            api_url=self.api_url,
            endpoint=endpoint,
            dry_run=dry_run,
            payload=payload,
        )


GitHubIssueLabelPublisher = GitHubIssueLabelsPublisher


def _github_issue_labels_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {"labels": list(payload["labels"])}


def _labels_from_artifact(
    *,
    source: dict[str, Any],
    quality: dict[str, Any],
    evaluation: dict[str, Any],
) -> list[str]:
    labels = [
        "max",
        "tact-spec",
        _label_value(source.get("type") or "idea"),
        _label_value(source.get("category")),
        _label_value(source.get("domain")),
        _label_value(source.get("status")),
        _label_value(evaluation.get("recommendation"), prefix="recommendation"),
    ]
    labels.extend(_label_value(tag, prefix="quality") for tag in quality.get("rejection_tags") or [])
    return labels


def _merge_labels(*label_groups: list[str]) -> list[str]:
    unique: list[str] = []
    for label_group in label_groups:
        for label in label_group:
            value = _label_value(label)
            if value and value not in unique:
                unique.append(value)
    return unique


def _label_value(value: object, *, prefix: str | None = None) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower().replace("_", "-").replace(" ", "-")
    safe = "".join(ch for ch in text if ch.isalnum() or ch in "-./:")
    if not safe:
        return ""
    label = f"{prefix}:{safe}" if prefix else safe
    return label[:50]


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
        raise GitHubIssueLabelPublishError("GitHub repository must be in owner/repo format")
    return value


def _validate_issue_number(issue_number: object) -> int:
    try:
        value = int(str(issue_number).strip())
    except (TypeError, ValueError) as exc:
        raise GitHubIssueLabelPublishError(
            "GitHub issue number must be a positive integer"
        ) from exc
    if value < 1:
        raise GitHubIssueLabelPublishError("GitHub issue number must be a positive integer")
    return value


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise GitHubIssueLabelPublishError(message)
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

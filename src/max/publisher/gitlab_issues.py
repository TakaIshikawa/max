"""GitLab issue publisher for approved ideas."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import httpx

from max.types.buildable_unit import BuildableUnit


DEFAULT_GITLAB_BASE_URL = "https://gitlab.com"
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
    "private_token",
    "secret",
    "sig",
    "signature",
    "token",
}


class GitLabIssuePublishError(RuntimeError):
    """Raised when a GitLab issue publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(_redact_text(message))
        self.status_code = status_code


@dataclass(frozen=True)
class GitLabIssuePayload:
    """GitLab issue creation payload plus Max-specific metadata."""

    title: str
    description: str
    project: str
    labels: list[str]
    assignee_ids: list[int]
    confidential: bool
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable issue payload preview."""
        return {
            "title": self.title,
            "description": self.description,
            "project": self.project,
            "labels": self.labels,
            "assignee_ids": self.assignee_ids,
            "confidential": self.confidential,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class GitLabIssuePublishResult:
    """Summary of a GitLab issue publish or dry run."""

    status_code: int | None
    project: str
    issue_id: int | None
    issue_iid: int | None
    issue_url: str | None
    attempts: int
    dry_run: bool
    payload: dict[str, Any]


class GitLabIssuePublisher:
    """Build and optionally create GitLab issues from approved ideas."""

    def __init__(
        self,
        project: str,
        *,
        token: str | None = None,
        base_url: str = DEFAULT_GITLAB_BASE_URL,
        labels: list[str] | None = None,
        assignee_ids: list[int] | None = None,
        confidential: bool = False,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = 0.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.project = _required_text(project, "GitLab project ID/path is required")
        self.token = _optional_text(token)
        self.base_url = _required_url(base_url)
        self.labels = labels or []
        self.assignee_ids = assignee_ids or []
        self.confidential = confidential
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_backoff = max(0.0, retry_backoff)
        self._client = client
        self.last_attempts = 0

    @classmethod
    def from_env(
        cls,
        *,
        project: str | None = None,
        project_id: str | None = None,
        project_path: str | None = None,
        token: str | None = None,
        base_url: str | None = None,
        labels: list[str] | None = None,
        assignee_ids: list[int] | None = None,
        confidential: bool = False,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.Client | None = None,
    ) -> GitLabIssuePublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_project = (
            project
            or project_id
            or project_path
            or os.getenv("GITLAB_PROJECT_ID")
            or os.getenv("GITLAB_PROJECT_PATH")
            or os.getenv("GITLAB_PROJECT")
        )
        if not resolved_project:
            raise GitLabIssuePublishError(
                "GitLab project ID/path is required; pass project_id/project_path or "
                "set GITLAB_PROJECT_ID or GITLAB_PROJECT_PATH"
            )
        return cls(
            resolved_project,
            token=token or os.getenv("GITLAB_TOKEN"),
            base_url=base_url or os.getenv("GITLAB_BASE_URL", DEFAULT_GITLAB_BASE_URL),
            labels=labels,
            assignee_ids=assignee_ids,
            confidential=confidential,
            timeout=timeout,
            max_retries=max_retries,
            client=client,
        )

    @property
    def issue_endpoint(self) -> str:
        """Return the GitLab REST endpoint used for issue creation."""
        return f"{self.base_url}/api/v4/projects/{quote(self.project, safe='')}/issues"

    def build_issue_payload(
        self,
        idea_or_spec: BuildableUnit | dict[str, Any],
        spec_preview: dict[str, Any] | None = None,
        *,
        title: str | None = None,
        labels: list[str] | None = None,
        assignee_ids: list[int] | None = None,
        confidential: bool | None = None,
    ) -> GitLabIssuePayload:
        """Convert a BuildableUnit or generated TactSpec preview into a GitLab issue payload."""
        tact_spec = _coerce_tact_spec(idea_or_spec, spec_preview)
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")
        quality = _dict_value(tact_spec, "quality")
        evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}
        resolved_confidential = self.confidential if confidential is None else confidential

        metadata = {
            "publisher": "max.gitlab_issues",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "idea"),
            "idea_id": source.get("idea_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "project": self.project,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        return GitLabIssuePayload(
            title=_issue_title(title or project.get("title"), source.get("idea_id")),
            description=_issue_description(tact_spec),
            project=self.project,
            labels=_merge_labels(
                _issue_labels(source=source, quality=quality, evaluation=evaluation),
                [*(self.labels), *(labels or [])],
            ),
            assignee_ids=assignee_ids if assignee_ids is not None else self.assignee_ids,
            confidential=resolved_confidential,
            metadata=metadata,
        )

    def publish(
        self,
        idea_or_spec: BuildableUnit | dict[str, Any],
        *,
        spec_preview: dict[str, Any] | None = None,
        title: str | None = None,
        labels: list[str] | None = None,
        assignee_ids: list[int] | None = None,
        confidential: bool | None = None,
        dry_run: bool = True,
    ) -> GitLabIssuePublishResult:
        """Build the issue payload and optionally create it in GitLab."""
        payload = self.build_issue_payload(
            idea_or_spec,
            spec_preview,
            title=title,
            labels=labels,
            assignee_ids=assignee_ids,
            confidential=confidential,
        ).to_dict()
        if dry_run:
            self.last_attempts = 0
            return GitLabIssuePublishResult(
                status_code=None,
                project=self.project,
                issue_id=None,
                issue_iid=None,
                issue_url=None,
                attempts=0,
                dry_run=True,
                payload=payload,
            )

        if not self.token:
            raise GitLabIssuePublishError(
                "GITLAB_TOKEN is required for live GitLab issue publishing; use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = self._post_with_retries(client, payload)
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise GitLabIssuePublishError(
                f"GitLab issue publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        issue_id = _int_or_none(body.get("id"))
        issue_iid = _int_or_none(body.get("iid"))
        issue_url = _optional_text(body.get("web_url"))
        if issue_id is None or issue_iid is None or not issue_url:
            raise GitLabIssuePublishError(
                "GitLab issue publish failed: response did not include issue id, iid, and web_url",
                status_code=response.status_code,
            )

        return GitLabIssuePublishResult(
            status_code=response.status_code,
            project=self.project,
            issue_id=issue_id,
            issue_iid=issue_iid,
            issue_url=issue_url,
            attempts=self.last_attempts,
            dry_run=False,
            payload={
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "gitlab_issue_id": issue_id,
                    "gitlab_issue_iid": issue_iid,
                    "gitlab_issue_url": issue_url,
                    "gitlab_attempts": self.last_attempts,
                },
            },
        )

    def _post_with_retries(
        self,
        client: httpx.Client,
        payload: dict[str, Any],
    ) -> httpx.Response:
        last_response: httpx.Response | None = None
        self.last_attempts = 0
        for attempt in range(self.max_retries + 1):
            self.last_attempts += 1
            try:
                response = client.post(
                    self.issue_endpoint,
                    json=_gitlab_issue_request(payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                message = _redact_text(str(exc))
                raise GitLabIssuePublishError(
                    f"GitLab issue publish failed for {_redact_url(self.issue_endpoint)}: {message}"
                ) from exc

            last_response = response
            if response.status_code not in TRANSIENT_STATUS_CODES or attempt >= self.max_retries:
                return response
            if self.retry_backoff:
                time.sleep(self.retry_backoff * (attempt + 1))

        return last_response

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "max-gitlab-issues-publisher/1",
        }


GitLabIssuesPublisher = GitLabIssuePublisher


def _gitlab_issue_request(payload: dict[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {
        "title": payload["title"],
        "description": payload["description"],
        "confidential": payload["confidential"],
    }
    if payload.get("labels"):
        request["labels"] = ",".join(payload["labels"])
    if payload.get("assignee_ids"):
        request["assignee_ids"] = payload["assignee_ids"]
    return request


def _coerce_tact_spec(
    idea_or_spec: BuildableUnit | dict[str, Any],
    spec_preview: dict[str, Any] | None,
) -> dict[str, Any]:
    if spec_preview is not None:
        return spec_preview
    if isinstance(idea_or_spec, BuildableUnit):
        return {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {
                "system": "max",
                "type": "idea",
                "idea_id": idea_or_spec.id,
                "status": idea_or_spec.status,
                "domain": idea_or_spec.domain,
                "category": idea_or_spec.category,
                "created_at": idea_or_spec.created_at.isoformat(),
                "updated_at": idea_or_spec.updated_at.isoformat(),
            },
            "project": {
                "title": idea_or_spec.title,
                "summary": idea_or_spec.one_liner,
                "target_users": idea_or_spec.target_users,
                "specific_user": idea_or_spec.specific_user,
                "buyer": idea_or_spec.buyer,
                "workflow_context": idea_or_spec.workflow_context,
            },
            "problem": {"statement": idea_or_spec.problem},
            "solution": {"approach": idea_or_spec.solution},
            "execution": {
                "mvp_scope": [idea_or_spec.value_proposition],
                "validation_plan": idea_or_spec.validation_plan,
            },
            "evidence": {
                "rationale": idea_or_spec.evidence_rationale,
                "insight_ids": idea_or_spec.inspiring_insights,
                "signal_ids": idea_or_spec.evidence_signals,
                "source_idea_ids": idea_or_spec.source_idea_ids,
            },
            "quality": {
                "quality_score": idea_or_spec.quality_score,
                "novelty_score": idea_or_spec.novelty_score,
                "usefulness_score": idea_or_spec.usefulness_score,
                "rejection_tags": idea_or_spec.rejection_tags,
            },
        }
    return idea_or_spec


def _issue_title(title: object, idea_id: object) -> str:
    base = str(title).strip() if title else str(idea_id or "Generated TactSpec").strip()
    return f"[Max] {base}"[:255]


def _issue_description(tact_spec: dict[str, Any]) -> str:
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
        "## Idea",
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
        "## Evidence Links",
        f"- Rationale: {_text_or_placeholder(evidence.get('rationale'))}",
        f"- Insights: {', '.join(evidence.get('insight_ids') or []) or 'None'}",
        f"- Signals: {', '.join(evidence.get('signal_ids') or []) or 'None'}",
        f"- Source ideas: {', '.join(evidence.get('source_idea_ids') or []) or 'None'}",
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
    return _unique(labels)


def _merge_labels(labels: list[str], extra_labels: list[str]) -> list[str]:
    return _unique([*labels, *(_label_value(label) for label in extra_labels)])


def _unique(labels: list[str]) -> list[str]:
    unique: list[str] = []
    for label in labels:
        if label and label not in unique:
            unique.append(label)
    return unique


def _label_value(value: object, *, prefix: str | None = None) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower().replace("_", "-").replace(" ", "-")
    safe = "".join(ch for ch in text if ch.isalnum() or ch in "-.")
    if not safe:
        return ""
    label = f"{prefix}-{safe}" if prefix else safe
    return label[:255]


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
        raise GitLabIssuePublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _required_url(value: object) -> str:
    raw = _required_text(value, "GitLab base_url is required").rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise GitLabIssuePublishError("GitLab base_url must be an absolute http(s) URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = _redact_text(response.text.strip())
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise GitLabIssuePublishError(
            "GitLab issue publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    return body if isinstance(body, dict) else {}


def _redact_text(text: str) -> str:
    redacted = re.sub(
        r"(?i)\b(token|api_token|password|private_token|secret|authorization)\b([=:]\s*)[^&\s,'\"}]+",
        r"\1\2<redacted>",
        text,
    )
    return _redact_url(redacted)


def _redact_url(text: str) -> str:
    words = text.split()
    return " ".join(_redact_url_word(word) for word in words)


def _redact_url_word(word: str) -> str:
    try:
        parts = urlsplit(word)
    except ValueError:
        return word
    if not parts.scheme or not parts.netloc:
        return word
    query = urlencode(
        [
            (key, "<redacted>" if key.lower() in SECRET_QUERY_KEYS else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
    )
    netloc = parts.hostname or ""
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))

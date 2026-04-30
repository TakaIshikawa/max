"""Bitbucket Cloud issue publisher for approved ideas."""

from __future__ import annotations

import base64
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


DEFAULT_BITBUCKET_API_URL = "https://api.bitbucket.org/2.0"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 2
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
BITBUCKET_ISSUE_KINDS = {"bug", "enhancement", "proposal", "task"}
BITBUCKET_ISSUE_PRIORITIES = {"trivial", "minor", "major", "critical", "blocker"}
SECRET_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "app_password",
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


class BitbucketIssuePublishError(RuntimeError):
    """Raised when a Bitbucket issue publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(_redact_text(message))
        self.status_code = status_code


@dataclass(frozen=True)
class BitbucketIssuePayload:
    """Bitbucket issue creation payload plus Max-specific metadata."""

    title: str
    content: str
    workspace: str
    repository: str
    kind: str
    priority: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable issue payload preview."""
        return {
            "title": self.title,
            "content": self.content,
            "workspace": self.workspace,
            "repository": self.repository,
            "kind": self.kind,
            "priority": self.priority,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class BitbucketIssuePublishResult:
    """Summary of a Bitbucket issue publish or dry run."""

    status_code: int | None
    workspace: str
    repository: str
    issue_id: int | None
    issue_url: str | None
    attempts: int
    dry_run: bool
    payload: dict[str, Any]


class BitbucketIssuePublisher:
    """Build and optionally create Bitbucket Cloud issues from approved ideas."""

    def __init__(
        self,
        workspace: str,
        repository: str,
        *,
        username: str | None = None,
        app_password: str | None = None,
        api_url: str = DEFAULT_BITBUCKET_API_URL,
        issue_kind: str | None = None,
        priority: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = 0.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.workspace = _required_slug(workspace, "Bitbucket workspace is required")
        self.repository = _required_slug(repository, "Bitbucket repository is required")
        self.username = _optional_text(username)
        self.app_password = _optional_text(app_password)
        self.api_url = _required_url(api_url)
        self.issue_kind = _optional_issue_kind(issue_kind)
        self.priority = _optional_priority(priority)
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_backoff = max(0.0, retry_backoff)
        self._client = client
        self.last_attempts = 0

    @classmethod
    def from_env(
        cls,
        *,
        workspace: str | None = None,
        repository: str | None = None,
        username: str | None = None,
        app_password: str | None = None,
        api_url: str | None = None,
        issue_kind: str | None = None,
        priority: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.Client | None = None,
    ) -> BitbucketIssuePublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_workspace = workspace or os.getenv("BITBUCKET_WORKSPACE")
        if not resolved_workspace:
            raise BitbucketIssuePublishError(
                "Bitbucket workspace is required; pass workspace or set BITBUCKET_WORKSPACE"
            )
        resolved_repository = repository or os.getenv("BITBUCKET_REPOSITORY")
        if not resolved_repository:
            raise BitbucketIssuePublishError(
                "Bitbucket repository is required; pass repository or set BITBUCKET_REPOSITORY"
            )
        return cls(
            resolved_workspace,
            resolved_repository,
            username=username or os.getenv("BITBUCKET_USERNAME"),
            app_password=app_password or os.getenv("BITBUCKET_APP_PASSWORD"),
            api_url=api_url or os.getenv("BITBUCKET_API_URL", DEFAULT_BITBUCKET_API_URL),
            issue_kind=issue_kind,
            priority=priority,
            timeout=timeout,
            max_retries=max_retries,
            client=client,
        )

    @property
    def issue_endpoint(self) -> str:
        """Return the Bitbucket Cloud REST endpoint used for issue creation."""
        workspace = quote(self.workspace, safe="")
        repository = quote(self.repository, safe="")
        return f"{self.api_url}/repositories/{workspace}/{repository}/issues"

    def build_issue_payload(
        self,
        idea_or_spec: BuildableUnit | dict[str, Any],
        spec_preview: dict[str, Any] | None = None,
        *,
        title: str | None = None,
        issue_kind: str | None = None,
        priority: str | None = None,
    ) -> BitbucketIssuePayload:
        """Convert a BuildableUnit or generated TactSpec preview into a Bitbucket issue payload."""
        tact_spec = _coerce_tact_spec(idea_or_spec, spec_preview)
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")
        quality = _dict_value(tact_spec, "quality")
        evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}
        resolved_kind = (
            _optional_issue_kind(issue_kind)
            or self.issue_kind
            or _mapped_issue_kind(tact_spec.get("kind"), source=source, project=project)
        )
        resolved_priority = (
            _optional_priority(priority)
            or self.priority
            or _mapped_priority(evaluation=evaluation, quality=quality)
        )

        metadata = {
            "publisher": "max.bitbucket_issues",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "idea"),
            "idea_id": source.get("idea_id"),
            "design_brief_id": source.get("design_brief_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "workspace": self.workspace,
            "repository": self.repository,
            "bitbucket_issue_kind": resolved_kind,
            "bitbucket_priority": resolved_priority,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        return BitbucketIssuePayload(
            title=_issue_title(title or project.get("title"), source.get("idea_id")),
            content=_issue_content(tact_spec),
            workspace=self.workspace,
            repository=self.repository,
            kind=resolved_kind,
            priority=resolved_priority,
            metadata=metadata,
        )

    def publish(
        self,
        idea_or_spec: BuildableUnit | dict[str, Any],
        *,
        spec_preview: dict[str, Any] | None = None,
        title: str | None = None,
        issue_kind: str | None = None,
        priority: str | None = None,
        dry_run: bool = True,
    ) -> BitbucketIssuePublishResult:
        """Build the issue payload and optionally create it in Bitbucket Cloud."""
        payload = self.build_issue_payload(
            idea_or_spec,
            spec_preview,
            title=title,
            issue_kind=issue_kind,
            priority=priority,
        ).to_dict()
        if dry_run:
            self.last_attempts = 0
            return BitbucketIssuePublishResult(
                status_code=None,
                workspace=self.workspace,
                repository=self.repository,
                issue_id=None,
                issue_url=None,
                attempts=0,
                dry_run=True,
                payload=payload,
            )

        if not self._has_auth:
            raise BitbucketIssuePublishError(
                "BITBUCKET_USERNAME and BITBUCKET_APP_PASSWORD are required for live "
                "Bitbucket issue publishing; use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = self._post_with_retries(client, payload)
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise BitbucketIssuePublishError(
                f"Bitbucket issue publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        issue_id = _int_or_none(body.get("id"))
        issue_url = _issue_url(body)
        if issue_id is None or not issue_url:
            raise BitbucketIssuePublishError(
                "Bitbucket issue publish failed: response did not include issue id and html link",
                status_code=response.status_code,
            )

        return BitbucketIssuePublishResult(
            status_code=response.status_code,
            workspace=self.workspace,
            repository=self.repository,
            issue_id=issue_id,
            issue_url=issue_url,
            attempts=self.last_attempts,
            dry_run=False,
            payload={
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "bitbucket_issue_id": issue_id,
                    "bitbucket_issue_url": issue_url,
                    "bitbucket_attempts": self.last_attempts,
                },
            },
        )

    @property
    def _has_auth(self) -> bool:
        return bool(self.username and self.app_password)

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
                    json=_bitbucket_issue_request(payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                message = _redact_text(str(exc))
                raise BitbucketIssuePublishError(
                    f"Bitbucket issue publish failed for {_redact_url(self.issue_endpoint)}: {message}"
                ) from exc

            last_response = response
            if response.status_code not in TRANSIENT_STATUS_CODES or attempt >= self.max_retries:
                return response
            if self.retry_backoff:
                time.sleep(self.retry_backoff * (attempt + 1))

        return last_response

    def _headers(self) -> dict[str, str]:
        assert self.username is not None and self.app_password is not None
        credentials = f"{self.username}:{self.app_password}".encode("utf-8")
        return {
            "Accept": "application/json",
            "Authorization": f"Basic {base64.b64encode(credentials).decode('ascii')}",
            "Content-Type": "application/json",
            "User-Agent": "max-bitbucket-issues-publisher/1",
        }


BitbucketIssuesPublisher = BitbucketIssuePublisher


def _bitbucket_issue_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": payload["title"],
        "content": {"raw": payload["content"]},
        "kind": payload["kind"],
        "priority": payload["priority"],
    }


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


def _issue_content(tact_spec: dict[str, Any]) -> str:
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
        f"- Design brief ID: {_text_or_placeholder(source.get('design_brief_id'))}",
        f"- Status: {_text_or_placeholder(source.get('status'))}",
        f"- Domain: {_text_or_placeholder(source.get('domain'))}",
        f"- Category: {_text_or_placeholder(source.get('category'))}",
        f"- Buyer: {_text_or_placeholder(project.get('buyer'))}",
        f"- Specific user: {_text_or_placeholder(project.get('specific_user'))}",
        f"- Workflow context: {_text_or_placeholder(project.get('workflow_context'))}",
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
    lines.extend(["", "## Risks"])
    lines.extend(_bullet_list(execution.get("risks")))
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


def _mapped_issue_kind(
    kind: object,
    *,
    source: dict[str, Any],
    project: dict[str, Any],
) -> str:
    text = " ".join(
        str(value).lower()
        for value in (
            kind,
            source.get("type"),
            source.get("category"),
            project.get("title"),
        )
        if value
    )
    if "bug" in text or "defect" in text:
        return "bug"
    if "task" in text or "chore" in text:
        return "task"
    if "proposal" in text or "idea" in text:
        return "proposal"
    return "enhancement"


def _mapped_priority(*, evaluation: dict[str, Any], quality: dict[str, Any]) -> str:
    score = _numeric_value(evaluation.get("overall_score"))
    if score is None:
        score = _numeric_value(quality.get("quality_score"))
        if score is not None and score <= 10:
            score *= 10
    if score is None:
        return "major"
    if score >= 95:
        return "blocker"
    if score >= 80:
        return "critical"
    if score >= 55:
        return "major"
    if score >= 30:
        return "minor"
    return "trivial"


def _optional_issue_kind(value: object) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    normalized = text.lower().replace("_", "-").strip()
    if normalized not in BITBUCKET_ISSUE_KINDS:
        raise BitbucketIssuePublishError(
            "Bitbucket issue kind must be one of: bug, enhancement, proposal, task"
        )
    return normalized


def _optional_priority(value: object) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    normalized = text.lower().replace("_", "-").strip()
    if normalized not in BITBUCKET_ISSUE_PRIORITIES:
        raise BitbucketIssuePublishError(
            "Bitbucket issue priority must be one of: trivial, minor, major, critical, blocker"
        )
    return normalized


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


def _numeric_value(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise BitbucketIssuePublishError(message)
    return text


def _required_slug(value: object, message: str) -> str:
    text = _required_text(value, message)
    if "/" in text:
        raise BitbucketIssuePublishError(f"{message}; use the slug without a slash")
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _required_url(value: object) -> str:
    raw = _required_text(value, "Bitbucket api_url is required").rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise BitbucketIssuePublishError("Bitbucket api_url must be an absolute http(s) URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _issue_url(body: dict[str, Any]) -> str | None:
    links = body.get("links")
    if not isinstance(links, dict):
        return None
    html = links.get("html")
    if not isinstance(html, dict):
        return None
    href = html.get("href")
    return str(href) if href else None


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = _redact_text(response.text.strip())
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise BitbucketIssuePublishError(
            "Bitbucket issue publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    return body if isinstance(body, dict) else {}


def _redact_text(text: str) -> str:
    redacted = re.sub(
        r"(?i)\b(token|api_token|app_password|password|private_token|secret|authorization)\b([=:]\s*)[^&\s,'\"}]+",
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

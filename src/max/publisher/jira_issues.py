"""Jira Cloud issue publisher for generated TactSpecs."""

from __future__ import annotations

import base64
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from max.types.buildable_unit import BuildableUnit


DEFAULT_JIRA_API_PATH = "/rest/api/3/issue"
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


class JiraIssuePublishError(RuntimeError):
    """Raised when a Jira issue publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(_redact_text(message))
        self.status_code = status_code


@dataclass(frozen=True)
class JiraIssuePayload:
    """Jira issue creation payload plus Max-specific metadata."""

    summary: str
    description: str
    project_key: str
    issue_type: str
    labels: list[str]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable issue payload preview."""
        return {
            "summary": self.summary,
            "description": self.description,
            "project_key": self.project_key,
            "issue_type": self.issue_type,
            "labels": self.labels,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class JiraIssuePublishResult:
    """Summary of a Jira issue publish or dry run."""

    status_code: int | None
    project_key: str
    issue_key: str | None
    issue_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class JiraIssuePublisher:
    """Build and optionally create Jira Cloud issues from approved ideas."""

    def __init__(
        self,
        site_url: str,
        project_key: str,
        *,
        email: str | None = None,
        api_token: str | None = None,
        bearer_token: str | None = None,
        issue_type: str = "Task",
        labels: list[str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = 0.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.site_url = _required_url(site_url)
        self.project_key = _required_text(project_key, "Jira project_key is required")
        self.email = _optional_text(email)
        self.api_token = _optional_text(api_token)
        self.bearer_token = _optional_text(bearer_token)
        self.issue_type = _optional_text(issue_type) or "Task"
        self.labels = labels or []
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_backoff = max(0.0, retry_backoff)
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        site_url: str | None = None,
        project_key: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        bearer_token: str | None = None,
        issue_type: str | None = None,
        labels: list[str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.Client | None = None,
    ) -> JiraIssuePublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_site_url = site_url or os.getenv("JIRA_SITE_URL")
        if not resolved_site_url:
            raise JiraIssuePublishError(
                "Jira site_url is required; pass site_url or set JIRA_SITE_URL"
            )
        resolved_project_key = project_key or os.getenv("JIRA_PROJECT_KEY")
        if not resolved_project_key:
            raise JiraIssuePublishError(
                "Jira project_key is required; pass project_key or set JIRA_PROJECT_KEY"
            )
        return cls(
            resolved_site_url,
            resolved_project_key,
            email=email or os.getenv("JIRA_EMAIL"),
            api_token=api_token or os.getenv("JIRA_API_TOKEN"),
            bearer_token=bearer_token or os.getenv("JIRA_BEARER_TOKEN"),
            issue_type=issue_type or os.getenv("JIRA_ISSUE_TYPE", "Task"),
            labels=labels,
            timeout=timeout,
            max_retries=max_retries,
            client=client,
        )

    @property
    def issue_endpoint(self) -> str:
        """Return the Jira REST endpoint used for issue creation."""
        return f"{self.site_url}{DEFAULT_JIRA_API_PATH}"

    def build_issue_payload(
        self,
        idea_or_spec: BuildableUnit | dict[str, Any],
        spec_preview: dict[str, Any] | None = None,
    ) -> JiraIssuePayload:
        """Convert a BuildableUnit or generated TactSpec preview into a Jira issue payload."""
        tact_spec = _coerce_tact_spec(idea_or_spec, spec_preview)
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")
        quality = _dict_value(tact_spec, "quality")
        evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}

        metadata = {
            "publisher": "max.jira_issues",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "idea"),
            "idea_id": source.get("idea_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "project_key": self.project_key,
            "issue_type": self.issue_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        return JiraIssuePayload(
            summary=_issue_summary(project.get("title"), source.get("idea_id")),
            description=_issue_description(tact_spec),
            project_key=self.project_key,
            issue_type=self.issue_type,
            labels=_merge_labels(
                _issue_labels(source=source, quality=quality, evaluation=evaluation),
                self.labels,
            ),
            metadata=metadata,
        )

    def publish(
        self,
        idea_or_spec: BuildableUnit | dict[str, Any],
        *,
        spec_preview: dict[str, Any] | None = None,
        dry_run: bool = True,
    ) -> JiraIssuePublishResult:
        """Build the issue payload and optionally create it in Jira Cloud."""
        payload = self.build_issue_payload(idea_or_spec, spec_preview).to_dict()
        if dry_run:
            return JiraIssuePublishResult(
                status_code=None,
                project_key=self.project_key,
                issue_key=None,
                issue_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self._has_auth:
            raise JiraIssuePublishError(
                "Jira email/api_token or bearer_token is required for live Jira issue publishing; "
                "use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = self._post_with_retries(client, payload)
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise JiraIssuePublishError(
                f"Jira issue publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        issue_key = body.get("key")
        if not issue_key:
            raise JiraIssuePublishError(
                "Jira issue publish failed: response did not include created issue key",
                status_code=response.status_code,
            )

        issue_url = self.issue_url(str(issue_key))
        return JiraIssuePublishResult(
            status_code=response.status_code,
            project_key=self.project_key,
            issue_key=str(issue_key),
            issue_url=issue_url,
            dry_run=False,
            payload={
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "jira_issue_id": body.get("id"),
                    "jira_issue_key": str(issue_key),
                    "jira_issue_url": issue_url,
                },
            },
        )

    @property
    def _has_auth(self) -> bool:
        return bool(self.bearer_token or (self.email and self.api_token))

    def issue_url(self, issue_key: str) -> str:
        """Return the Jira browse URL for an issue key."""
        return f"{self.site_url}/browse/{issue_key}"

    def _post_with_retries(
        self,
        client: httpx.Client,
        payload: dict[str, Any],
    ) -> httpx.Response:
        last_response: httpx.Response | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = client.post(
                    self.issue_endpoint,
                    json=_jira_issue_request(payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                message = _redact_text(str(exc))
                raise JiraIssuePublishError(
                    f"Jira issue publish failed for {_redact_url(self.issue_endpoint)}: {message}"
                ) from exc

            last_response = response
            if response.status_code not in TRANSIENT_STATUS_CODES or attempt >= self.max_retries:
                return response
            if self.retry_backoff:
                time.sleep(self.retry_backoff * (attempt + 1))

        return last_response

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "max-jira-issues-publisher/1",
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        else:
            assert self.email is not None and self.api_token is not None
            credentials = f"{self.email}:{self.api_token}".encode("utf-8")
            headers["Authorization"] = f"Basic {base64.b64encode(credentials).decode('ascii')}"
        return headers


JiraIssuesPublisher = JiraIssuePublisher


def _jira_issue_request(payload: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "project": {"key": payload["project_key"]},
        "issuetype": {"name": payload["issue_type"]},
        "summary": payload["summary"],
        "description": _adf_document(payload["description"]),
    }
    if payload.get("labels"):
        fields["labels"] = payload["labels"]
    return {"fields": fields}


def _adf_document(text: str) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    for line in text.splitlines():
        if line.startswith("# "):
            content.append(
                {
                    "type": "heading",
                    "attrs": {"level": 1},
                    "content": [{"type": "text", "text": line[2:]}],
                }
            )
        elif line.startswith("## "):
            content.append(
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": line[3:]}],
                }
            )
        elif line.startswith("- "):
            content.append(
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": line[2:]}],
                                }
                            ],
                        }
                    ],
                }
            )
        else:
            paragraph: dict[str, Any] = {"type": "paragraph"}
            if line:
                paragraph["content"] = [{"type": "text", "text": line}]
            content.append(paragraph)
    return {"type": "doc", "version": 1, "content": content or [{"type": "paragraph"}]}


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


def _issue_summary(title: object, idea_id: object) -> str:
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
        "## Evidence Chain",
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
        raise JiraIssuePublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _required_url(value: object) -> str:
    raw = _required_text(value, "Jira site_url is required").rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise JiraIssuePublishError("Jira site_url must be an absolute http(s) URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = _redact_text(response.text.strip())
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise JiraIssuePublishError(
            "Jira issue publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    return body if isinstance(body, dict) else {}


def _redact_text(text: str) -> str:
    redacted = re.sub(
        r"(?i)\b(token|api_token|password|secret|authorization)\b([=:]\s*)[^&\s,'\"}]+",
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

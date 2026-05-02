"""GitLab merge request publisher for generated specs and buildable units."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import httpx

from max.types.buildable_unit import BuildableUnit


DEFAULT_GITLAB_BASE_URL = "https://gitlab.com"
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
    "private_token",
    "secret",
    "sig",
    "signature",
    "token",
}


class GitLabMergeRequestPublishError(RuntimeError):
    """Raised when a GitLab merge request publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(_redact_text(message))
        self.status_code = status_code


@dataclass(frozen=True)
class GitLabMergeRequestPayload:
    """GitLab merge request creation payload plus Max-specific metadata."""

    project: str
    title: str
    source_branch: str
    target_branch: str
    description: str
    labels: list[str]
    assignee_ids: list[int]
    remove_source_branch: bool
    squash: bool | None
    draft: bool
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable merge request payload preview."""
        payload: dict[str, Any] = {
            "project": self.project,
            "title": self.title,
            "source_branch": self.source_branch,
            "target_branch": self.target_branch,
            "description": self.description,
            "labels": self.labels,
            "assignee_ids": self.assignee_ids,
            "remove_source_branch": self.remove_source_branch,
            "draft": self.draft,
            "metadata": self.metadata,
        }
        if self.squash is not None:
            payload["squash"] = self.squash
        return payload


@dataclass(frozen=True)
class GitLabMergeRequestPublishResult:
    """Summary of a GitLab merge request publish or dry run."""

    status_code: int | None
    project: str
    endpoint: str
    merge_request_id: int | None
    merge_request_iid: int | None
    merge_request_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class GitLabMergeRequestPublisher:
    """Build and optionally create GitLab merge requests from Max artifacts."""

    def __init__(
        self,
        project: str | None = None,
        *,
        project_id: str | None = None,
        project_path: str | None = None,
        token: str | None = None,
        base_url: str = DEFAULT_GITLAB_BASE_URL,
        source_branch: str | None = None,
        target_branch: str | None = None,
        title: str | None = None,
        description: str | None = None,
        labels: list[str] | None = None,
        assignee_ids: list[int] | None = None,
        remove_source_branch: bool = False,
        squash: bool | None = None,
        draft: bool = False,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.project = _required_text(
            project or project_id or project_path,
            "GitLab project ID/path is required",
        )
        self.token = _optional_text(token)
        self.base_url = _required_url(base_url)
        self.source_branch = _optional_text(source_branch)
        self.target_branch = _optional_text(target_branch)
        self.title = _optional_text(title)
        self.description = _optional_text(description)
        self.labels = labels or []
        self.assignee_ids = assignee_ids or []
        self.remove_source_branch = remove_source_branch
        self.squash = squash
        self.draft = draft
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        project: str | None = None,
        project_id: str | None = None,
        project_path: str | None = None,
        token: str | None = None,
        base_url: str | None = None,
        source_branch: str | None = None,
        target_branch: str | None = None,
        title: str | None = None,
        description: str | None = None,
        labels: list[str] | None = None,
        assignee_ids: list[int] | None = None,
        remove_source_branch: bool = False,
        squash: bool | None = None,
        draft: bool = False,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> GitLabMergeRequestPublisher:
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
            raise GitLabMergeRequestPublishError(
                "GitLab project ID/path is required; pass project_id/project_path or "
                "set GITLAB_PROJECT_ID or GITLAB_PROJECT_PATH"
            )
        return cls(
            resolved_project,
            token=token or os.getenv("GITLAB_TOKEN"),
            base_url=base_url or os.getenv("GITLAB_BASE_URL", DEFAULT_GITLAB_BASE_URL),
            source_branch=source_branch or os.getenv("GITLAB_MERGE_REQUEST_SOURCE_BRANCH"),
            target_branch=target_branch or os.getenv("GITLAB_MERGE_REQUEST_TARGET_BRANCH"),
            title=title or os.getenv("GITLAB_MERGE_REQUEST_TITLE"),
            description=description or os.getenv("GITLAB_MERGE_REQUEST_DESCRIPTION"),
            labels=labels,
            assignee_ids=assignee_ids,
            remove_source_branch=remove_source_branch,
            squash=squash,
            draft=draft,
            timeout=timeout,
            client=client,
        )

    @property
    def merge_request_endpoint(self) -> str:
        """Return the GitLab REST endpoint used for merge request creation."""
        return f"{self.base_url}/api/v4/projects/{quote(self.project, safe='')}/merge_requests"

    def build_merge_request_payload(
        self,
        artifact: BuildableUnit | dict[str, Any],
        *,
        source_branch: str | None = None,
        target_branch: str | None = None,
        title: str | None = None,
        description: str | None = None,
        labels: list[str] | None = None,
        assignee_ids: list[int] | None = None,
        remove_source_branch: bool | None = None,
        squash: bool | None = None,
        draft: bool | None = None,
    ) -> GitLabMergeRequestPayload:
        """Convert a BuildableUnit or generated artifact into a GitLab merge request payload."""
        source_artifact = _coerce_artifact(artifact)
        source = _dict_value(source_artifact, "source")
        quality = _dict_value(source_artifact, "quality")
        evaluation = (
            source_artifact.get("evaluation")
            if isinstance(source_artifact.get("evaluation"), dict)
            else {}
        )
        resolved_source_branch = _required_branch(
            source_branch or self.source_branch,
            "GitLab merge request source_branch is required",
        )
        resolved_target_branch = _required_branch(
            target_branch or self.target_branch,
            "GitLab merge request target_branch is required",
        )
        resolved_title = _merge_request_title(
            source_artifact,
            explicit_title=title or self.title,
            draft=self.draft if draft is None else draft,
        )
        resolved_description = (
            _required_text(description, "GitLab merge request description is required")
            if description is not None
            else self.description
            or _merge_request_description(source_artifact, title=resolved_title)
        )
        resolved_draft = self.draft if draft is None else draft
        resolved_squash = self.squash if squash is None else squash

        metadata = {
            "publisher": "max.gitlab_merge_requests",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "artifact"),
            "idea_id": source.get("idea_id"),
            "design_brief_id": source.get("design_brief_id"),
            "schema_version": source_artifact.get("schema_version"),
            "kind": source_artifact.get("kind"),
            "project": self.project,
            "source_branch": resolved_source_branch,
            "target_branch": resolved_target_branch,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        return GitLabMergeRequestPayload(
            project=self.project,
            title=resolved_title,
            source_branch=resolved_source_branch,
            target_branch=resolved_target_branch,
            description=resolved_description,
            labels=_merge_labels(
                _merge_request_labels(
                    source=source,
                    quality=quality,
                    evaluation=evaluation,
                ),
                [*(self.labels), *(labels or [])],
            ),
            assignee_ids=assignee_ids if assignee_ids is not None else self.assignee_ids,
            remove_source_branch=(
                self.remove_source_branch
                if remove_source_branch is None
                else remove_source_branch
            ),
            squash=resolved_squash,
            draft=resolved_draft,
            metadata=metadata,
        )

    def publish(
        self,
        artifact: BuildableUnit | dict[str, Any],
        *,
        dry_run: bool = True,
        source_branch: str | None = None,
        target_branch: str | None = None,
        title: str | None = None,
        description: str | None = None,
        labels: list[str] | None = None,
        assignee_ids: list[int] | None = None,
        remove_source_branch: bool | None = None,
        squash: bool | None = None,
        draft: bool | None = None,
    ) -> GitLabMergeRequestPublishResult:
        """Build the merge request payload and optionally create it in GitLab."""
        payload = self.build_merge_request_payload(
            artifact,
            source_branch=source_branch,
            target_branch=target_branch,
            title=title,
            description=description,
            labels=labels,
            assignee_ids=assignee_ids,
            remove_source_branch=remove_source_branch,
            squash=squash,
            draft=draft,
        ).to_dict()
        return self.publish_merge_request_payload(payload, dry_run=dry_run)

    def publish_merge_request_payload(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> GitLabMergeRequestPublishResult:
        """Publish a pre-rendered GitLab merge request payload."""
        payload = {
            **payload,
            "title": _required_text(
                payload.get("title"),
                "GitLab merge request title is required",
            ),
            "source_branch": _required_branch(
                payload.get("source_branch"),
                "GitLab merge request source_branch is required",
            ),
            "target_branch": _required_branch(
                payload.get("target_branch"),
                "GitLab merge request target_branch is required",
            ),
            "description": _required_text(
                payload.get("description"),
                "GitLab merge request description is required",
            ),
            "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        }
        if dry_run:
            return GitLabMergeRequestPublishResult(
                status_code=None,
                project=self.project,
                endpoint=self.merge_request_endpoint,
                merge_request_id=None,
                merge_request_iid=None,
                merge_request_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self.token:
            raise GitLabMergeRequestPublishError(
                "GITLAB_TOKEN is required for live GitLab merge request publishing; "
                "use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.merge_request_endpoint,
                    json=_gitlab_merge_request_request(payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                message = _redact_text(str(exc))
                raise GitLabMergeRequestPublishError(
                    "GitLab merge request publish failed for "
                    f"{_redact_url(self.merge_request_endpoint)}: {message}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise GitLabMergeRequestPublishError(
                f"GitLab merge request publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        merge_request_id = _int_or_none(body.get("id"))
        merge_request_iid = _int_or_none(body.get("iid"))
        merge_request_url = _optional_text(body.get("web_url"))
        if merge_request_id is None or merge_request_iid is None or not merge_request_url:
            raise GitLabMergeRequestPublishError(
                "GitLab merge request publish failed: response did not include "
                "merge request id, iid, and web_url",
                status_code=response.status_code,
            )

        return GitLabMergeRequestPublishResult(
            status_code=response.status_code,
            project=self.project,
            endpoint=self.merge_request_endpoint,
            merge_request_id=merge_request_id,
            merge_request_iid=merge_request_iid,
            merge_request_url=merge_request_url,
            dry_run=False,
            payload={
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "gitlab_merge_request_id": merge_request_id,
                    "gitlab_merge_request_iid": merge_request_iid,
                    "gitlab_merge_request_url": merge_request_url,
                },
            },
        )

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "max-gitlab-merge-requests-publisher/1",
        }


GitLabMergeRequestsPublisher = GitLabMergeRequestPublisher


def _gitlab_merge_request_request(payload: dict[str, Any]) -> dict[str, Any]:
    request_payload: dict[str, Any] = {
        "title": _required_text(
            payload.get("title"),
            "GitLab merge request title is required",
        ),
        "source_branch": _required_branch(
            payload.get("source_branch"),
            "GitLab merge request source_branch is required",
        ),
        "target_branch": _required_branch(
            payload.get("target_branch"),
            "GitLab merge request target_branch is required",
        ),
        "description": _required_text(
            payload.get("description"),
            "GitLab merge request description is required",
        ),
        "remove_source_branch": bool(payload.get("remove_source_branch")),
    }
    if payload.get("labels"):
        request_payload["labels"] = ",".join(str(label) for label in payload["labels"])
    if payload.get("assignee_ids"):
        request_payload["assignee_ids"] = payload["assignee_ids"]
    if "squash" in payload:
        request_payload["squash"] = bool(payload["squash"])
    if payload.get("draft"):
        request_payload["draft"] = True
    return request_payload


def _coerce_artifact(artifact: BuildableUnit | dict[str, Any]) -> dict[str, Any]:
    if isinstance(artifact, BuildableUnit):
        return {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {
                "system": "max",
                "type": "idea",
                "idea_id": artifact.id,
                "status": artifact.status,
                "domain": artifact.domain,
                "category": artifact.category,
                "created_at": artifact.created_at.isoformat(),
                "updated_at": artifact.updated_at.isoformat(),
            },
            "project": {
                "title": artifact.title,
                "summary": artifact.one_liner,
                "target_users": artifact.target_users,
                "specific_user": artifact.specific_user,
                "buyer": artifact.buyer,
                "workflow_context": artifact.workflow_context,
            },
            "problem": {"statement": artifact.problem},
            "solution": {"approach": artifact.solution},
            "execution": {
                "mvp_scope": [artifact.value_proposition],
                "validation_plan": artifact.validation_plan,
            },
            "evidence": {
                "rationale": artifact.evidence_rationale,
                "insight_ids": artifact.inspiring_insights,
                "signal_ids": artifact.evidence_signals,
                "source_idea_ids": artifact.source_idea_ids,
            },
            "quality": {
                "quality_score": artifact.quality_score,
                "novelty_score": artifact.novelty_score,
                "usefulness_score": artifact.usefulness_score,
                "rejection_tags": artifact.rejection_tags,
            },
        }
    return artifact


def _merge_request_title(
    artifact: dict[str, Any],
    *,
    explicit_title: str | None,
    draft: bool,
) -> str:
    if explicit_title:
        base = explicit_title
    else:
        project = _dict_value(artifact, "project")
        source = _dict_value(artifact, "source")
        base = _text_or_placeholder(
            project.get("title")
            or artifact.get("title")
            or source.get("design_brief_id")
            or source.get("idea_id")
            or "Generated Merge Request"
        )
    title = f"[Draft] {base}" if draft and not base.lower().startswith(("draft:", "[draft]")) else base
    return title[:255]


def _merge_request_description(artifact: dict[str, Any], *, title: str) -> str:
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


def _merge_request_labels(
    *,
    source: dict[str, Any],
    quality: dict[str, Any],
    evaluation: dict[str, Any],
) -> list[str]:
    labels = [
        "max",
        "merge-request",
        _label_value(source.get("type")),
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


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise GitLabMergeRequestPublishError(
            "GitLab merge request publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    if not isinstance(body, dict):
        raise GitLabMergeRequestPublishError(
            "GitLab merge request publish failed: response JSON was not an object",
            status_code=response.status_code,
        )
    return body


def _int_or_none(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise GitLabMergeRequestPublishError(message)
    return text


def _required_branch(value: object, message: str) -> str:
    branch = _required_text(value, message)
    if any(ch.isspace() for ch in branch):
        raise GitLabMergeRequestPublishError("GitLab merge request branch names cannot contain whitespace")
    return branch


def _required_url(value: object) -> str:
    raw = _required_text(value, "GitLab base_url is required").rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise GitLabMergeRequestPublishError(
            "GitLab base_url must be an absolute http(s) URL"
        )
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    return _redact_text(_truncate(response.text.strip(), limit=limit))


def _truncate(text: str, *, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _redact_text(text: str) -> str:
    redacted = re.sub(
        r"(?i)\b(token|api_token|password|private_token|secret|authorization)\b([=:]\s*)"
        r"[^&\s,'\"}]+",
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
    if parts.username:
        userinfo = parts.username
        if parts.password:
            userinfo = f"{userinfo}:<redacted>"
        netloc = f"{userinfo}@{netloc}"
    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


def _text_or_placeholder(value: object) -> str:
    text = str(value).strip() if value else ""
    return text or "Not specified"


def _score_text(value: object) -> str:
    if isinstance(value, int | float):
        return f"{value:.1f}"
    return _text_or_placeholder(value)

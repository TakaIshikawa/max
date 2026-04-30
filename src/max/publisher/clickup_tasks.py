"""ClickUp task publisher for generated TactSpecs."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from max.types.buildable_unit import BuildableUnit


DEFAULT_CLICKUP_API_URL = "https://api.clickup.com/api/v2"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 2
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class ClickUpTaskPublishError(RuntimeError):
    """Raised when a ClickUp task publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ClickUpTaskPayload:
    """ClickUp task creation payload plus Max-specific metadata."""

    name: str
    description: str
    list_id: str
    assignees: list[int]
    tags: list[str]
    priority: int | None
    due_date: int | str | None
    custom_fields: list[dict[str, Any]]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable ClickUp task payload preview."""
        payload: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "list_id": self.list_id,
            "assignees": self.assignees,
            "tags": self.tags,
            "custom_fields": self.custom_fields,
            "metadata": self.metadata,
        }
        if self.priority is not None:
            payload["priority"] = self.priority
        if self.due_date is not None:
            payload["due_date"] = self.due_date
        return payload


@dataclass(frozen=True)
class ClickUpTaskPublishResult:
    """Summary of a ClickUp task publish or dry run."""

    status_code: int | None
    list_id: str
    task_id: str | None
    task_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class ClickUpTaskPublisher:
    """Build and optionally create ClickUp tasks from approved ideas."""

    def __init__(
        self,
        list_id: str,
        *,
        api_token: str | None = None,
        api_url: str = DEFAULT_CLICKUP_API_URL,
        assignees: list[int] | None = None,
        tags: list[str] | None = None,
        priority: int | None = None,
        due_date: int | str | None = None,
        custom_fields: list[dict[str, Any]] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = 0.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.list_id = _required_text(list_id, "ClickUp list_id is required")
        self.api_token = _optional_text(api_token)
        self.api_url = _required_url(api_url)
        self.assignees = [_assignee_id(assignee) for assignee in assignees or []]
        self.tags = [_required_text(tag, "ClickUp tags must be non-empty") for tag in tags or []]
        self.priority = priority
        self.due_date = _optional_due_date(due_date)
        self.custom_fields = custom_fields or []
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_backoff = max(0.0, retry_backoff)
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        list_id: str | None = None,
        api_token: str | None = None,
        api_url: str | None = None,
        assignees: list[int] | None = None,
        tags: list[str] | None = None,
        priority: int | None = None,
        due_date: int | str | None = None,
        custom_fields: list[dict[str, Any]] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.Client | None = None,
    ) -> ClickUpTaskPublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_list_id = list_id or os.getenv("CLICKUP_LIST_ID")
        if not resolved_list_id:
            raise ClickUpTaskPublishError(
                "ClickUp list_id is required; pass list_id or set CLICKUP_LIST_ID"
            )
        return cls(
            resolved_list_id,
            api_token=api_token or os.getenv("CLICKUP_API_TOKEN"),
            api_url=api_url or os.getenv("CLICKUP_API_URL", DEFAULT_CLICKUP_API_URL),
            assignees=assignees if assignees is not None else _int_list_env("CLICKUP_ASSIGNEES"),
            tags=tags if tags is not None else _string_list_env("CLICKUP_TAGS"),
            priority=priority if priority is not None else _int_env("CLICKUP_PRIORITY"),
            due_date=due_date if due_date is not None else os.getenv("CLICKUP_DUE_DATE"),
            custom_fields=(
                custom_fields if custom_fields is not None else _custom_fields_env()
            ),
            timeout=timeout,
            max_retries=max_retries,
            client=client,
        )

    @property
    def task_endpoint(self) -> str:
        """Return the ClickUp REST endpoint used for task creation."""
        return f"{self.api_url}/list/{self.list_id}/task"

    @property
    def has_auth(self) -> bool:
        """Return whether live ClickUp task publishing has credentials."""
        return bool(self.api_token)

    def build_task_payload(
        self,
        idea_or_spec: BuildableUnit | dict[str, Any],
        spec_preview: dict[str, Any] | None = None,
    ) -> ClickUpTaskPayload:
        """Convert a BuildableUnit or generated TactSpec preview into a ClickUp task payload."""
        tact_spec = _coerce_tact_spec(idea_or_spec, spec_preview)
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")
        quality = _dict_value(tact_spec, "quality")
        evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}

        metadata = {
            "publisher": "max.clickup_tasks",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "idea"),
            "idea_id": source.get("idea_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "list_id": self.list_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        return ClickUpTaskPayload(
            name=_task_name(project.get("title"), source.get("idea_id")),
            description=_task_description(tact_spec, metadata),
            list_id=self.list_id,
            assignees=list(self.assignees),
            tags=_merge_tags(_task_tags(source=source, quality=quality, evaluation=evaluation), self.tags),
            priority=self.priority,
            due_date=self.due_date,
            custom_fields=list(self.custom_fields),
            metadata=metadata,
        )

    def publish(
        self,
        idea_or_spec: BuildableUnit | dict[str, Any],
        *,
        spec_preview: dict[str, Any] | None = None,
        dry_run: bool = True,
    ) -> ClickUpTaskPublishResult:
        """Build the task payload and optionally create it in ClickUp."""
        payload = self.build_task_payload(idea_or_spec, spec_preview).to_dict()
        if dry_run:
            return ClickUpTaskPublishResult(
                status_code=None,
                list_id=self.list_id,
                task_id=None,
                task_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self.has_auth:
            raise ClickUpTaskPublishError(
                "CLICKUP_API_TOKEN is required for live ClickUp task publishing; "
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
            raise ClickUpTaskPublishError(
                f"ClickUp task publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        task_id = body.get("id")
        if not task_id:
            raise ClickUpTaskPublishError(
                "ClickUp task publish failed: response did not include created task id",
                status_code=response.status_code,
            )

        task_url = body.get("url")
        return ClickUpTaskPublishResult(
            status_code=response.status_code,
            list_id=self.list_id,
            task_id=str(task_id),
            task_url=str(task_url) if task_url else None,
            dry_run=False,
            payload={
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "clickup_task_id": str(task_id),
                    "clickup_task_url": str(task_url) if task_url else None,
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
                    self.task_endpoint,
                    json=_clickup_task_request(payload),
                    headers={
                        "Authorization": self.api_token or "",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "User-Agent": "max-clickup-tasks-publisher/1",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise ClickUpTaskPublishError(
                    f"ClickUp task publish failed for {self.task_endpoint}: {exc}"
                ) from exc

            last_response = response
            if response.status_code not in TRANSIENT_STATUS_CODES or attempt >= self.max_retries:
                return response
            if self.retry_backoff:
                time.sleep(self.retry_backoff * (attempt + 1))

        return last_response


ClickUpTasksPublisher = ClickUpTaskPublisher


def _clickup_task_request(payload: dict[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {
        "name": payload["name"],
        "description": payload["description"],
    }
    if payload.get("assignees"):
        request["assignees"] = payload["assignees"]
    if payload.get("tags"):
        request["tags"] = payload["tags"]
    if payload.get("priority") is not None:
        request["priority"] = payload["priority"]
    if payload.get("due_date") is not None:
        request["due_date"] = payload["due_date"]
    if payload.get("custom_fields"):
        request["custom_fields"] = payload["custom_fields"]
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


def _task_name(title: object, idea_id: object) -> str:
    base = str(title).strip() if title else str(idea_id or "Generated TactSpec").strip()
    return f"[Max] {base}"[:255]


def _task_description(tact_spec: dict[str, Any], metadata: dict[str, Any]) -> str:
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
            "## Max Metadata",
            "```json",
            json.dumps(metadata, indent=2, sort_keys=True),
            "```",
            "",
            "## TactSpec Preview",
            "```json",
            json.dumps(tact_spec, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _task_tags(
    *,
    source: dict[str, Any],
    quality: dict[str, Any],
    evaluation: dict[str, Any],
) -> list[str]:
    tags = [
        "max",
        "tact-spec",
        _tag_value(source.get("type")) or "idea",
        _tag_value(source.get("category")),
        _tag_value(source.get("domain")),
        _tag_value(source.get("status")),
        _tag_value(evaluation.get("recommendation"), prefix="recommendation"),
    ]
    tags.extend(_tag_value(tag, prefix="quality") for tag in quality.get("rejection_tags") or [])
    return _unique(tags)


def _merge_tags(tags: list[str], extra_tags: list[str]) -> list[str]:
    return _unique([*tags, *(_tag_value(tag) for tag in extra_tags)])


def _unique(tags: list[str]) -> list[str]:
    unique: list[str] = []
    for tag in tags:
        if tag and tag not in unique:
            unique.append(tag)
    return unique


def _tag_value(value: object, *, prefix: str | None = None) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower().replace("_", "-").replace(" ", "-")
    safe = "".join(ch for ch in text if ch.isalnum() or ch in "-.")
    if not safe:
        return ""
    tag = f"{prefix}-{safe}" if prefix else safe
    return tag[:255]


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
        raise ClickUpTaskPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _required_url(value: object) -> str:
    raw = _required_text(value, "ClickUp api_url is required").rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ClickUpTaskPublishError("ClickUp api_url must be an absolute http(s) URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _assignee_id(value: object) -> int:
    try:
        assignee = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ClickUpTaskPublishError("ClickUp assignees must be integer user IDs") from exc
    if assignee < 0:
        raise ClickUpTaskPublishError("ClickUp assignees must be non-negative user IDs")
    return assignee


def _optional_due_date(value: object) -> int | str | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    return int(text) if text.isdigit() else text


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise ClickUpTaskPublishError(
            "ClickUp task publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    return body if isinstance(body, dict) else {}


def _string_list_env(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def _int_list_env(name: str) -> list[int]:
    return [_assignee_id(item) for item in _string_list_env(name)]


def _int_env(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ClickUpTaskPublishError(f"{name} must be an integer") from exc


def _custom_fields_env() -> list[dict[str, Any]]:
    value = os.getenv("CLICKUP_CUSTOM_FIELDS")
    if value is None or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except ValueError as exc:
        raise ClickUpTaskPublishError("CLICKUP_CUSTOM_FIELDS must be valid JSON") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
        raise ClickUpTaskPublishError("CLICKUP_CUSTOM_FIELDS must be a JSON array of objects")
    return parsed

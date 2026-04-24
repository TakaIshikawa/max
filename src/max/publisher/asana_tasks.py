"""Asana task publisher for generated TactSpecs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx


DEFAULT_ASANA_API_URL = "https://app.asana.com/api/1.0"
DEFAULT_TIMEOUT_SECONDS = 10.0


class AsanaTaskPublishError(RuntimeError):
    """Raised when an Asana task publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class AsanaTaskPayload:
    """Asana task creation payload plus Max-specific metadata."""

    name: str
    notes: str
    workspace_gid: str
    project_gid: str | None
    section_gid: str | None
    assignee_gid: str | None
    tags: list[str]
    due_on: str | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON payload sent to Asana's create-task endpoint."""
        data: dict[str, Any] = {
            "name": self.name,
            "notes": self.notes,
            "workspace": self.workspace_gid,
        }
        if self.section_gid:
            if not self.project_gid:
                raise AsanaTaskPublishError(
                    "Asana project_gid is required when section_gid is provided"
                )
            data["memberships"] = [{"project": self.project_gid, "section": self.section_gid}]
        elif self.project_gid:
            data["projects"] = [self.project_gid]
        if self.assignee_gid:
            data["assignee"] = self.assignee_gid
        if self.tags:
            data["tags"] = self.tags
        if self.due_on:
            data["due_on"] = self.due_on
        return {"data": data}


@dataclass(frozen=True)
class AsanaTaskPublishResult:
    """Summary of an Asana task publish or dry run."""

    status_code: int | None
    workspace_gid: str
    task_gid: str | None
    task_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class AsanaTaskPublisher:
    """Build and optionally create Asana tasks from TactSpec payloads."""

    def __init__(
        self,
        workspace_gid: str,
        *,
        access_token: str | None = None,
        api_url: str = DEFAULT_ASANA_API_URL,
        project_gid: str | None = None,
        section_gid: str | None = None,
        assignee_gid: str | None = None,
        tags: list[str] | None = None,
        due_on: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.workspace_gid = _required_text(workspace_gid, "Asana workspace_gid is required")
        self.access_token = _optional_text(access_token)
        self.api_url = _required_text(api_url, "Asana api_url is required").rstrip("/")
        self.project_gid = _optional_text(project_gid)
        self.section_gid = _optional_text(section_gid)
        self.assignee_gid = _optional_text(assignee_gid)
        self.tags = [_required_text(tag, "Asana tags must be non-empty") for tag in tags or []]
        self.due_on = _optional_text(due_on)
        self.timeout = timeout
        self._client = client
        if self.section_gid and not self.project_gid:
            raise AsanaTaskPublishError("Asana project_gid is required when section_gid is provided")

    @classmethod
    def from_env(
        cls,
        *,
        workspace_gid: str | None = None,
        access_token: str | None = None,
        api_url: str | None = None,
        project_gid: str | None = None,
        section_gid: str | None = None,
        assignee_gid: str | None = None,
        tags: list[str] | None = None,
        due_on: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> AsanaTaskPublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_workspace_gid = workspace_gid or os.getenv("ASANA_WORKSPACE_GID")
        if not resolved_workspace_gid:
            raise AsanaTaskPublishError(
                "Asana workspace_gid is required; pass workspace_gid or set ASANA_WORKSPACE_GID"
            )
        return cls(
            resolved_workspace_gid,
            access_token=access_token or os.getenv("ASANA_ACCESS_TOKEN"),
            api_url=api_url or os.getenv("ASANA_API_URL", DEFAULT_ASANA_API_URL),
            project_gid=project_gid or os.getenv("ASANA_PROJECT_GID"),
            section_gid=section_gid or os.getenv("ASANA_SECTION_GID"),
            assignee_gid=assignee_gid or os.getenv("ASANA_ASSIGNEE_GID"),
            tags=tags,
            due_on=due_on,
            timeout=timeout,
            client=client,
        )

    @property
    def task_endpoint(self) -> str:
        """Return the Asana REST endpoint used for task creation."""
        return f"{self.api_url}/tasks"

    def build_task_payload(self, tact_spec: dict[str, Any]) -> AsanaTaskPayload:
        """Convert a generated TactSpec preview into an Asana task payload."""
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")

        metadata = {
            "publisher": "max.asana_tasks",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "idea"),
            "idea_id": source.get("idea_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "workspace_gid": self.workspace_gid,
            "project_gid": self.project_gid,
            "source_created_at": source.get("created_at"),
            "source_updated_at": source.get("updated_at"),
        }

        return AsanaTaskPayload(
            name=_task_name(project.get("title"), source.get("idea_id")),
            notes=_task_notes(tact_spec),
            workspace_gid=self.workspace_gid,
            project_gid=self.project_gid,
            section_gid=self.section_gid,
            assignee_gid=self.assignee_gid,
            tags=list(self.tags),
            due_on=self.due_on,
            metadata=metadata,
        )

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True) -> AsanaTaskPublishResult:
        """Build the task payload and optionally create it in Asana."""
        payload = self.build_task_payload(tact_spec).to_dict()
        if dry_run:
            return AsanaTaskPublishResult(
                status_code=None,
                workspace_gid=self.workspace_gid,
                task_gid=None,
                task_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self.access_token:
            raise AsanaTaskPublishError(
                "ASANA_ACCESS_TOKEN is required for live Asana task publishing; "
                "use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.task_endpoint,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.access_token}",
                        "Content-Type": "application/json",
                        "User-Agent": "max-asana-tasks-publisher/1",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise AsanaTaskPublishError(
                    f"Asana task publish failed for {self.task_endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise AsanaTaskPublishError(
                f"Asana task publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        task = body.get("data") if isinstance(body.get("data"), dict) else {}
        task_gid = task.get("gid")
        if not task_gid:
            raise AsanaTaskPublishError(
                "Asana task publish failed: response did not include created task gid",
                status_code=response.status_code,
            )

        task_url = task.get("permalink_url")
        return AsanaTaskPublishResult(
            status_code=response.status_code,
            workspace_gid=self.workspace_gid,
            task_gid=str(task_gid),
            task_url=str(task_url) if task_url else None,
            dry_run=False,
            payload=payload,
        )


AsanaTasksPublisher = AsanaTaskPublisher


def _task_name(title: object, idea_id: object) -> str:
    base = str(title).strip() if title else str(idea_id or "Generated TactSpec").strip()
    return f"[Max] {base}"


def _task_notes(tact_spec: dict[str, Any]) -> str:
    project = _dict_value(tact_spec, "project")
    problem = _dict_value(tact_spec, "problem")
    solution = _dict_value(tact_spec, "solution")
    execution = _dict_value(tact_spec, "execution")
    evidence = _dict_value(tact_spec, "evidence")
    source = _dict_value(tact_spec, "source")
    evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}

    lines = [
        f"{project.get('title') or source.get('idea_id') or 'Generated TactSpec'}",
        "",
        _text_or_placeholder(project.get("summary")),
        "",
        "Idea",
        f"- Idea ID: {_text_or_placeholder(source.get('idea_id'))}",
        f"- Status: {_text_or_placeholder(source.get('status'))}",
        f"- Domain: {_text_or_placeholder(source.get('domain'))}",
        f"- Category: {_text_or_placeholder(source.get('category'))}",
        "",
        "Problem",
        _text_or_placeholder(problem.get("statement")),
        "",
        "Solution",
        _text_or_placeholder(solution.get("approach")),
        "",
        "Evaluation",
        f"- Recommendation: {_text_or_placeholder(evaluation.get('recommendation'))}",
        f"- Overall score: {_score_text(evaluation.get('overall_score'))}",
    ]
    lines.extend(_dimension_lines(evaluation.get("dimensions")))
    lines.extend(
        [
            "",
            "Evidence Chain",
            f"- Rationale: {_text_or_placeholder(evidence.get('rationale'))}",
            f"- Insights: {', '.join(evidence.get('insight_ids') or []) or 'None'}",
            f"- Signals: {', '.join(evidence.get('signal_ids') or []) or 'None'}",
            f"- Source ideas: {', '.join(evidence.get('source_idea_ids') or []) or 'None'}",
            "",
            "Validation Plan",
            _text_or_placeholder(execution.get("validation_plan")),
            "",
            "MVP Scope",
        ]
    )
    lines.extend(_bullet_list(execution.get("mvp_scope")))
    lines.extend(
        [
            "",
            "TactSpec Preview",
            json.dumps(tact_spec, indent=2, sort_keys=True),
            "",
        ]
    )
    return "\n".join(lines)


def _dimension_lines(dimensions: object) -> list[str]:
    if not isinstance(dimensions, dict) or not dimensions:
        return []
    lines = ["", "Evaluation Dimensions"]
    for name, value in dimensions.items():
        if not isinstance(value, dict):
            continue
        score = _score_text(value.get("value"))
        confidence = _score_text(value.get("confidence"))
        reasoning = _text_or_placeholder(value.get("reasoning"))
        lines.append(f"- {name.replace('_', ' ').title()}: {score} (confidence {confidence}) - {reasoning}")
    return lines


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
        raise AsanaTaskPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise AsanaTaskPublishError(
            "Asana task publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    return body if isinstance(body, dict) else {}

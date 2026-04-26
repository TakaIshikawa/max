"""Microsoft Planner task publisher for generated TactSpecs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


DEFAULT_MICROSOFT_GRAPH_API_URL = "https://graph.microsoft.com/v1.0"
DEFAULT_TIMEOUT_SECONDS = 10.0


class MicrosoftPlannerTaskPublishError(RuntimeError):
    """Raised when a Microsoft Planner task publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class MicrosoftPlannerTaskPayload:
    """Microsoft Planner task creation payload plus Max-specific metadata."""

    plan_id: str
    bucket_id: str
    title: str
    assignments: dict[str, dict[str, str]]
    details: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON payload sent to Microsoft Graph."""
        payload: dict[str, Any] = {
            "planId": self.plan_id,
            "bucketId": self.bucket_id,
            "title": self.title,
            "details": self.details,
            "metadata": self.metadata,
        }
        if self.assignments:
            payload["assignments"] = self.assignments
        return payload


@dataclass(frozen=True)
class MicrosoftPlannerTaskPublishResult:
    """Summary of a Microsoft Planner task publish or dry run."""

    status_code: int | None
    plan_id: str
    bucket_id: str
    task_id: str | None
    task_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class MicrosoftPlannerTaskPublisher:
    """Build and optionally create Microsoft Planner tasks from TactSpec payloads."""

    def __init__(
        self,
        plan_id: str,
        bucket_id: str,
        *,
        access_token: str | None = None,
        api_url: str = DEFAULT_MICROSOFT_GRAPH_API_URL,
        assignee_user_id: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.plan_id = _required_text(plan_id, "Microsoft Planner plan_id is required")
        self.bucket_id = _required_text(bucket_id, "Microsoft Planner bucket_id is required")
        self.access_token = _optional_text(access_token)
        self.api_url = _required_text(api_url, "Microsoft Graph api_url is required").rstrip("/")
        self.assignee_user_id = _optional_text(assignee_user_id)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        plan_id: str | None = None,
        bucket_id: str | None = None,
        access_token: str | None = None,
        api_url: str | None = None,
        assignee_user_id: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> MicrosoftPlannerTaskPublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_plan_id = plan_id or os.getenv("MS_PLANNER_PLAN_ID")
        if not resolved_plan_id:
            raise MicrosoftPlannerTaskPublishError(
                "Microsoft Planner plan_id is required; pass plan_id or set MS_PLANNER_PLAN_ID"
            )
        resolved_bucket_id = bucket_id or os.getenv("MS_PLANNER_BUCKET_ID")
        if not resolved_bucket_id:
            raise MicrosoftPlannerTaskPublishError(
                "Microsoft Planner bucket_id is required; pass bucket_id or set MS_PLANNER_BUCKET_ID"
            )
        return cls(
            resolved_plan_id,
            resolved_bucket_id,
            access_token=access_token or os.getenv("MS_PLANNER_ACCESS_TOKEN"),
            api_url=api_url or os.getenv("MS_GRAPH_API_URL", DEFAULT_MICROSOFT_GRAPH_API_URL),
            assignee_user_id=assignee_user_id or os.getenv("MS_PLANNER_ASSIGNEE_USER_ID"),
            timeout=timeout,
            client=client,
        )

    @property
    def task_endpoint(self) -> str:
        """Return the Microsoft Graph endpoint used for Planner task creation."""
        return f"{self.api_url}/planner/tasks"

    @property
    def has_auth(self) -> bool:
        """Return whether live Microsoft Planner publishing has credentials."""
        return bool(self.access_token)

    def build_task_payload(self, tact_spec: dict[str, Any]) -> MicrosoftPlannerTaskPayload:
        """Convert a generated TactSpec preview into a Microsoft Planner task payload."""
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")

        metadata = {
            "publisher": "max.microsoft_planner_tasks",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "idea"),
            "idea_id": source.get("idea_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "plan_id": self.plan_id,
            "bucket_id": self.bucket_id,
            "source_created_at": source.get("created_at"),
            "source_updated_at": source.get("updated_at"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        return MicrosoftPlannerTaskPayload(
            plan_id=self.plan_id,
            bucket_id=self.bucket_id,
            title=_task_title(project.get("title"), source.get("idea_id")),
            assignments=_assignments(self.assignee_user_id),
            details=_task_details(tact_spec, metadata),
            metadata=metadata,
        )

    def publish(
        self,
        tact_spec: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> MicrosoftPlannerTaskPublishResult:
        """Build the task payload and optionally create it in Microsoft Planner."""
        payload = self.build_task_payload(tact_spec).to_dict()
        if dry_run:
            return MicrosoftPlannerTaskPublishResult(
                status_code=None,
                plan_id=self.plan_id,
                bucket_id=self.bucket_id,
                task_id=None,
                task_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self.access_token:
            raise MicrosoftPlannerTaskPublishError(
                "MS_PLANNER_ACCESS_TOKEN is required for live Microsoft Planner task publishing; "
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
                        "User-Agent": "max-microsoft-planner-tasks-publisher/1",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise MicrosoftPlannerTaskPublishError(
                    f"Microsoft Planner task publish failed for {self.task_endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise MicrosoftPlannerTaskPublishError(
                f"Microsoft Planner task publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        task_id = body.get("id")
        if not task_id:
            raise MicrosoftPlannerTaskPublishError(
                "Microsoft Planner task publish failed: response did not include created task id",
                status_code=response.status_code,
            )

        task_url = body.get("webUrl")
        return MicrosoftPlannerTaskPublishResult(
            status_code=response.status_code,
            plan_id=self.plan_id,
            bucket_id=self.bucket_id,
            task_id=str(task_id),
            task_url=str(task_url) if task_url else None,
            dry_run=False,
            payload=payload,
        )


MicrosoftPlannerTasksPublisher = MicrosoftPlannerTaskPublisher


def _task_title(title: object, idea_id: object) -> str:
    base = str(title).strip() if title else str(idea_id or "Generated TactSpec").strip()
    return base


def _assignments(assignee_user_id: str | None) -> dict[str, dict[str, str]]:
    if not assignee_user_id:
        return {}
    return {assignee_user_id: {"@odata.type": "microsoft.graph.plannerAssignment"}}


def _task_details(tact_spec: dict[str, Any], metadata: dict[str, Any]) -> str:
    project = _dict_value(tact_spec, "project")
    problem = _dict_value(tact_spec, "problem")
    solution = _dict_value(tact_spec, "solution")
    execution = _dict_value(tact_spec, "execution")
    evidence = _dict_value(tact_spec, "evidence")
    source = _dict_value(tact_spec, "source")
    evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}
    evidence_links = _evidence_links(evidence)

    lines = [
        "Max Metadata",
        f"- Idea ID: {_text_or_placeholder(source.get('idea_id'))}",
        f"- Status: {_text_or_placeholder(source.get('status'))}",
        f"- Domain: {_text_or_placeholder(source.get('domain'))}",
        f"- Category: {_text_or_placeholder(source.get('category'))}",
        f"- Publisher: {metadata['publisher']}",
        "",
        "Summary",
        _text_or_placeholder(project.get("summary")),
        "",
        "Problem",
        _text_or_placeholder(problem.get("statement")),
        "",
        "Solution",
        _text_or_placeholder(solution.get("approach")),
        "",
        "Validation Plan",
        _text_or_placeholder(execution.get("validation_plan")),
        "",
        "Evidence",
        f"- Rationale: {_text_or_placeholder(evidence.get('rationale'))}",
        f"- Insights: {', '.join(evidence.get('insight_ids') or []) or 'None'}",
        f"- Signals: {', '.join(evidence.get('signal_ids') or []) or 'None'}",
        f"- Source ideas: {', '.join(evidence.get('source_idea_ids') or []) or 'None'}",
    ]
    if evidence_links:
        lines.extend(["", "Evidence Links"])
        lines.extend(f"- {link}" for link in evidence_links)
    lines.extend(
        [
            "",
            "Evaluation",
            f"- Recommendation: {_text_or_placeholder(evaluation.get('recommendation'))}",
            f"- Overall score: {_score_text(evaluation.get('overall_score'))}",
            "",
            "TactSpec Preview",
            json.dumps(tact_spec, indent=2, sort_keys=True),
        ]
    )
    return "\n".join(lines)


def _evidence_links(evidence: dict[str, Any]) -> list[str]:
    links: list[str] = []
    for candidate in evidence.get("links") or []:
        text = str(candidate).strip()
        if text and text not in links:
            links.append(text)
    return links


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
        raise MicrosoftPlannerTaskPublishError(message)
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
        raise MicrosoftPlannerTaskPublishError(
            "Microsoft Planner task publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    return body if isinstance(body, dict) else {}

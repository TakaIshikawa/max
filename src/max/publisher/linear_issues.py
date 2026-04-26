"""Linear issue publisher for generated TactSpecs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


DEFAULT_LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
DEFAULT_TIMEOUT_SECONDS = 10.0


class LinearIssuePublishError(RuntimeError):
    """Raised when a Linear issue publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class LinearIssuePayload:
    """Linear issue creation payload plus Max-specific metadata."""

    title: str
    description: str
    team_id: str
    project_id: str | None
    label_ids: list[str]
    priority: int | None
    metadata: dict[str, Any]
    assignee_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable issue payload."""
        payload: dict[str, Any] = {
            "title": self.title,
            "description": self.description,
            "team_id": self.team_id,
            "label_ids": self.label_ids,
            "metadata": self.metadata,
        }
        if self.project_id:
            payload["project_id"] = self.project_id
        if self.priority is not None:
            payload["priority"] = self.priority
        if self.assignee_id:
            payload["assignee_id"] = self.assignee_id
        return payload


@dataclass(frozen=True)
class LinearIssuePublishResult:
    """Summary of a Linear issue publish or dry run."""

    status_code: int | None
    team_id: str
    issue_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class LinearIssuePublisher:
    """Build and optionally create Linear issues from TactSpec payloads."""

    def __init__(
        self,
        team_id: str,
        *,
        api_key: str | None = None,
        api_url: str = DEFAULT_LINEAR_GRAPHQL_URL,
        project_id: str | None = None,
        labels: list[str] | None = None,
        priority: int | None = None,
        assignee_id: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.team_id = _required_text(team_id, "Linear team_id is required")
        self.api_key = api_key
        self.api_url = api_url.rstrip("/")
        self.project_id = _optional_text(project_id)
        self.labels = labels or []
        self.priority = priority
        self.assignee_id = _optional_text(assignee_id)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        team_id: str | None = None,
        api_key: str | None = None,
        api_url: str | None = None,
        project_id: str | None = None,
        labels: list[str] | None = None,
        priority: int | None = None,
        assignee_id: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> LinearIssuePublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_team_id = team_id or os.getenv("LINEAR_TEAM_ID")
        if not resolved_team_id:
            raise LinearIssuePublishError(
                "Linear team_id is required; pass team_id or set LINEAR_TEAM_ID"
            )
        return cls(
            resolved_team_id,
            api_key=api_key or os.getenv("LINEAR_API_KEY"),
            api_url=api_url or os.getenv("LINEAR_API_URL", DEFAULT_LINEAR_GRAPHQL_URL),
            project_id=project_id or os.getenv("LINEAR_PROJECT_ID"),
            labels=labels,
            priority=priority,
            assignee_id=assignee_id,
            timeout=timeout,
            client=client,
        )

    @property
    def graphql_endpoint(self) -> str:
        """Return the Linear GraphQL endpoint used for issue creation."""
        return self.api_url

    def build_issue_payload(self, tact_spec: dict[str, Any]) -> LinearIssuePayload:
        """Convert a generated TactSpec preview into a Linear issue payload."""
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")

        metadata = {
            "publisher": "max.linear_issues",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "idea"),
            "idea_id": source.get("idea_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "team_id": self.team_id,
            "project_id": self.project_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        return LinearIssuePayload(
            title=_issue_title(project.get("title"), source.get("idea_id")),
            description=_issue_description(tact_spec),
            team_id=self.team_id,
            project_id=self.project_id,
            label_ids=list(self.labels),
            priority=self.priority,
            metadata=metadata,
            assignee_id=self.assignee_id,
        )

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True) -> LinearIssuePublishResult:
        """Build the issue payload and optionally create it in Linear."""
        payload = self.build_issue_payload(tact_spec).to_dict()
        return self.publish_payload(payload, dry_run=dry_run)

    def publish_payload(
        self,
        payload: LinearIssuePayload | dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> LinearIssuePublishResult:
        """Create a Linear issue from a prebuilt payload."""
        payload_dict = payload.to_dict() if isinstance(payload, LinearIssuePayload) else dict(payload)
        if dry_run:
            return LinearIssuePublishResult(
                status_code=None,
                team_id=self.team_id,
                issue_url=None,
                dry_run=True,
                payload=payload_dict,
            )

        if not self.api_key:
            raise LinearIssuePublishError(
                "LINEAR_API_KEY is required for live Linear issue publishing; use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.graphql_endpoint,
                    json=_graphql_request(payload_dict),
                    headers={
                        "Authorization": self.api_key,
                        "Content-Type": "application/json",
                        "User-Agent": "max-linear-issues-publisher/1",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise LinearIssuePublishError(
                    f"Linear issue publish failed for {self.graphql_endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise LinearIssuePublishError(
                f"Linear issue publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        errors = body.get("errors")
        if isinstance(errors, list) and errors:
            raise LinearIssuePublishError(
                f"Linear issue publish failed: {_graphql_errors_preview(errors)}",
                status_code=response.status_code,
            )

        issue = _issue_from_response(body)
        if not issue:
            raise LinearIssuePublishError(
                "Linear issue publish failed: response did not include created issue",
                status_code=response.status_code,
            )

        issue_url = issue.get("url")
        issue_identifier = issue.get("identifier")
        return LinearIssuePublishResult(
            status_code=response.status_code,
            team_id=self.team_id,
            issue_url=str(issue_url) if issue_url else None,
            dry_run=False,
            payload={
                **payload_dict,
                "metadata": {
                    **payload_dict["metadata"],
                    "linear_issue_url": issue_url,
                    "linear_issue_id": issue.get("id"),
                    "linear_issue_identifier": issue_identifier,
                },
            },
        )


LinearIssuesPublisher = LinearIssuePublisher


ISSUE_CREATE_MUTATION = """
mutation MaxIssueCreate($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue {
      id
      identifier
      url
    }
  }
}
""".strip()


def _graphql_request(payload: dict[str, Any]) -> dict[str, Any]:
    input_payload: dict[str, Any] = {
        "teamId": payload["team_id"],
        "title": payload["title"],
        "description": payload["description"],
    }
    if payload.get("project_id"):
        input_payload["projectId"] = payload["project_id"]
    if payload.get("label_ids"):
        input_payload["labelIds"] = payload["label_ids"]
    if payload.get("priority") is not None:
        input_payload["priority"] = payload["priority"]
    if payload.get("assignee_id"):
        input_payload["assigneeId"] = payload["assignee_id"]
    return {"query": ISSUE_CREATE_MUTATION, "variables": {"input": input_payload}}


def _issue_title(title: object, idea_id: object) -> str:
    base = str(title).strip() if title else str(idea_id or "Generated TactSpec").strip()
    return f"[Max] {base}"


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
    ]
    lines.extend(_dimension_lines(evaluation.get("dimensions")))
    lines.extend(
        [
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
    )
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


def _dimension_lines(dimensions: object) -> list[str]:
    if not isinstance(dimensions, dict) or not dimensions:
        return []
    lines = ["", "### Evaluation Dimensions"]
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
        raise LinearIssuePublishError(message)
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
        raise LinearIssuePublishError(
            "Linear issue publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    return body if isinstance(body, dict) else {}


def _graphql_errors_preview(errors: list[Any]) -> str:
    messages: list[str] = []
    for error in errors:
        if isinstance(error, dict) and error.get("message"):
            messages.append(str(error["message"]))
        elif error:
            messages.append(str(error))
    return "; ".join(messages) or "unknown GraphQL error"


def _issue_from_response(body: dict[str, Any]) -> dict[str, Any] | None:
    data = body.get("data")
    if not isinstance(data, dict):
        return None
    result = data.get("issueCreate")
    if not isinstance(result, dict) or result.get("success") is False:
        return None
    issue = result.get("issue")
    return issue if isinstance(issue, dict) else None

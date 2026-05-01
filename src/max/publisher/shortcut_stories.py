"""Shortcut story publisher for generated TactSpecs."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from max.types.buildable_unit import BuildableUnit


DEFAULT_SHORTCUT_API_URL = "https://api.app.shortcut.com/api/v3"
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
VALID_STORY_TYPES = {"feature", "bug", "chore"}


class ShortcutStoryPublishError(RuntimeError):
    """Raised when a Shortcut story publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(_redact_text(message))
        self.status_code = status_code


@dataclass(frozen=True)
class ShortcutStoryPayload:
    """Shortcut story creation payload plus Max-specific metadata."""

    name: str
    description: str
    story_type: str
    labels: list[str]
    workflow_state_id: int | None
    epic_id: int | None
    owner_ids: list[str]
    estimate: int | None
    deadline: str | None
    iteration_id: int | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable Shortcut story payload preview."""
        payload: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "story_type": self.story_type,
            "labels": self.labels,
            "owner_ids": self.owner_ids,
            "metadata": self.metadata,
        }
        if self.workflow_state_id is not None:
            payload["workflow_state_id"] = self.workflow_state_id
        if self.epic_id is not None:
            payload["epic_id"] = self.epic_id
        if self.estimate is not None:
            payload["estimate"] = self.estimate
        if self.deadline:
            payload["deadline"] = self.deadline
        if self.iteration_id is not None:
            payload["iteration_id"] = self.iteration_id
        return payload


@dataclass(frozen=True)
class ShortcutStoryPublishResult:
    """Summary of a Shortcut story publish or dry run."""

    status_code: int | None
    story_id: int | None
    story_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class ShortcutStoryPublisher:
    """Build and optionally create Shortcut stories from TactSpec payloads."""

    def __init__(
        self,
        *,
        api_token: str | None = None,
        api_url: str = DEFAULT_SHORTCUT_API_URL,
        workflow_state_id: int | str | None = None,
        epic_id: int | str | None = None,
        labels: list[str] | None = None,
        owner_ids: list[str] | None = None,
        story_type: str = "feature",
        estimate: int | str | None = None,
        deadline: str | None = None,
        iteration_id: int | str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_token = _optional_text(api_token)
        self.api_url = _required_url(api_url)
        self.workflow_state_id = _optional_int(workflow_state_id, "workflow_state_id")
        self.epic_id = _optional_int(epic_id, "epic_id")
        self.labels = [_label_value(label) for label in labels or [] if _label_value(label)]
        self.owner_ids = [
            _required_text(owner_id, "Shortcut owner_ids must be non-empty")
            for owner_id in owner_ids or []
        ]
        self.story_type = _story_type(story_type)
        self.estimate = _optional_int(estimate, "estimate")
        self.deadline = _optional_text(deadline)
        self.iteration_id = _optional_int(iteration_id, "iteration_id")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        api_token: str | None = None,
        api_url: str | None = None,
        workflow_state_id: int | str | None = None,
        epic_id: int | str | None = None,
        labels: list[str] | None = None,
        owner_ids: list[str] | None = None,
        story_type: str | None = None,
        estimate: int | str | None = None,
        deadline: str | None = None,
        iteration_id: int | str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> ShortcutStoryPublisher:
        """Create a publisher using API values first, then environment variables."""
        return cls(
            api_token=api_token or os.getenv("SHORTCUT_API_TOKEN"),
            api_url=api_url or os.getenv("SHORTCUT_API_URL", DEFAULT_SHORTCUT_API_URL),
            workflow_state_id=(
                workflow_state_id
                if workflow_state_id is not None
                else os.getenv("SHORTCUT_WORKFLOW_STATE_ID")
            ),
            epic_id=epic_id if epic_id is not None else os.getenv("SHORTCUT_EPIC_ID"),
            labels=labels if labels is not None else _string_list_env("SHORTCUT_LABELS"),
            owner_ids=(
                owner_ids if owner_ids is not None else _string_list_env("SHORTCUT_OWNER_IDS")
            ),
            story_type=story_type or os.getenv("SHORTCUT_STORY_TYPE", "feature"),
            estimate=estimate if estimate is not None else os.getenv("SHORTCUT_ESTIMATE"),
            deadline=deadline if deadline is not None else os.getenv("SHORTCUT_DEADLINE"),
            iteration_id=(
                iteration_id if iteration_id is not None else os.getenv("SHORTCUT_ITERATION_ID")
            ),
            timeout=timeout,
            client=client,
        )

    @property
    def story_endpoint(self) -> str:
        """Return the Shortcut REST endpoint used for story creation."""
        return f"{self.api_url}/stories"

    @property
    def has_auth(self) -> bool:
        """Return whether live Shortcut story publishing has credentials."""
        return bool(self.api_token)

    def build_story_payload(
        self,
        idea_or_spec: BuildableUnit | dict[str, Any],
        spec_preview: dict[str, Any] | None = None,
    ) -> ShortcutStoryPayload:
        """Convert a BuildableUnit or generated TactSpec preview into a Shortcut story payload."""
        tact_spec = _coerce_tact_spec(idea_or_spec, spec_preview)
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")
        quality = _dict_value(tact_spec, "quality")
        evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}

        metadata = {
            "publisher": "max.shortcut_stories",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "idea"),
            "idea_id": source.get("idea_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "workflow_state_id": self.workflow_state_id,
            "epic_id": self.epic_id,
            "story_type": self.story_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        return ShortcutStoryPayload(
            name=_story_name(project.get("title"), source.get("idea_id")),
            description=_story_description(tact_spec),
            story_type=self.story_type,
            labels=_merge_labels(
                _story_labels(source=source, quality=quality, evaluation=evaluation),
                self.labels,
            ),
            workflow_state_id=self.workflow_state_id,
            epic_id=self.epic_id,
            owner_ids=list(self.owner_ids),
            estimate=self.estimate,
            deadline=self.deadline,
            iteration_id=self.iteration_id,
            metadata=metadata,
        )

    def publish(
        self,
        idea_or_spec: BuildableUnit | dict[str, Any],
        *,
        spec_preview: dict[str, Any] | None = None,
        dry_run: bool = True,
    ) -> ShortcutStoryPublishResult:
        """Build the story payload and optionally create it in Shortcut."""
        payload = self.build_story_payload(idea_or_spec, spec_preview).to_dict()
        return self.publish_payload(payload, dry_run=dry_run)

    def publish_payload(
        self,
        payload: ShortcutStoryPayload | dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> ShortcutStoryPublishResult:
        """Create a Shortcut story from a prebuilt payload."""
        payload_dict = payload.to_dict() if isinstance(payload, ShortcutStoryPayload) else dict(payload)
        if dry_run:
            return ShortcutStoryPublishResult(
                status_code=None,
                story_id=None,
                story_url=None,
                dry_run=True,
                payload=payload_dict,
            )

        if not self.has_auth:
            raise ShortcutStoryPublishError(
                "SHORTCUT_API_TOKEN is required for live Shortcut story publishing; "
                "use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.story_endpoint,
                    json=_shortcut_story_request(payload_dict),
                    headers={
                        "Shortcut-Token": self.api_token or "",
                        "Content-Type": "application/json",
                        "User-Agent": "max-shortcut-stories-publisher/1",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                message = _redact_text(str(exc))
                raise ShortcutStoryPublishError(
                    f"Shortcut story publish failed for {_redact_url(self.story_endpoint)}: {message}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise ShortcutStoryPublishError(
                f"Shortcut story publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        story_id = _optional_int(body.get("id"), "story id")
        app_url = body.get("app_url") or body.get("url")
        if story_id is None and not app_url:
            raise ShortcutStoryPublishError(
                "Shortcut story publish failed: response did not include created story id or URL",
                status_code=response.status_code,
            )

        return ShortcutStoryPublishResult(
            status_code=response.status_code,
            story_id=story_id,
            story_url=str(app_url) if app_url else None,
            dry_run=False,
            payload={
                **payload_dict,
                "metadata": {
                    **(payload_dict.get("metadata") or {}),
                    "shortcut_story_id": story_id,
                    "shortcut_story_url": str(app_url) if app_url else None,
                },
            },
        )


ShortcutStoriesPublisher = ShortcutStoryPublisher


def _shortcut_story_request(payload: dict[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {
        "name": payload["name"],
        "description": payload["description"],
        "story_type": payload["story_type"],
    }
    if payload.get("labels"):
        request["labels"] = [{"name": label} for label in payload["labels"]]
    if payload.get("owner_ids"):
        request["owner_ids"] = payload["owner_ids"]
    if payload.get("workflow_state_id") is not None:
        request["workflow_state_id"] = payload["workflow_state_id"]
    if payload.get("epic_id") is not None:
        request["epic_id"] = payload["epic_id"]
    if payload.get("estimate") is not None:
        request["estimate"] = payload["estimate"]
    if payload.get("deadline"):
        request["deadline"] = payload["deadline"]
    if payload.get("iteration_id") is not None:
        request["iteration_id"] = payload["iteration_id"]
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


def _story_name(title: object, idea_id: object) -> str:
    base = str(title).strip() if title else str(idea_id or "Generated TactSpec").strip()
    return f"[Max] {base}"[:512]


def _story_description(tact_spec: dict[str, Any]) -> str:
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


def _story_labels(
    *,
    source: dict[str, Any],
    quality: dict[str, Any],
    evaluation: dict[str, Any],
) -> list[str]:
    labels = [
        "max",
        "tact-spec",
        _label_value(source.get("type")) or "idea",
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
    return label[:128]


def _story_type(value: object) -> str:
    story_type = _required_text(value, "Shortcut story_type is required").lower()
    if story_type not in VALID_STORY_TYPES:
        allowed = ", ".join(sorted(VALID_STORY_TYPES))
        raise ShortcutStoryPublishError(f"Shortcut story_type must be one of: {allowed}")
    return story_type


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
        raise ShortcutStoryPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _optional_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError as exc:
        raise ShortcutStoryPublishError(f"Shortcut {field_name} must be an integer") from exc


def _required_url(value: object) -> str:
    raw = _required_text(value, "Shortcut api_url is required").rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ShortcutStoryPublishError("Shortcut api_url must be an absolute http(s) URL")
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
        raise ShortcutStoryPublishError(
            "Shortcut story publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    return body if isinstance(body, dict) else {}


def _string_list_env(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


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

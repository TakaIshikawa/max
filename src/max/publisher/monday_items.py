"""Monday.com item publisher for generated TactSpecs."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from max.types.buildable_unit import BuildableUnit


DEFAULT_MONDAY_API_URL = "https://api.monday.com/v2"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 2
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
REDACTED = "[redacted]"

CREATE_ITEM_MUTATION = """
mutation CreateMaxIdeaItem(
  $board_id: ID!
  $group_id: String
  $item_name: String!
  $column_values: JSON
) {
  create_item(
    board_id: $board_id
    group_id: $group_id
    item_name: $item_name
    column_values: $column_values
  ) {
    id
    name
    url
  }
}
""".strip()


class MondayItemPublishError(RuntimeError):
    """Raised when a Monday.com item publish cannot be completed."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        api_token: str | None = None,
    ) -> None:
        super().__init__(_redact_text(message, api_token=api_token))
        self.status_code = status_code


@dataclass(frozen=True)
class MondayItemPayload:
    """Monday.com create-item GraphQL payload plus Max-specific metadata."""

    board_id: str
    group_id: str | None
    item_name: str
    column_values: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON payload sent to Monday.com's GraphQL endpoint."""
        variables: dict[str, Any] = {
            "board_id": self.board_id,
            "item_name": self.item_name,
            "column_values": json.dumps(self.column_values, sort_keys=True),
        }
        if self.group_id:
            variables["group_id"] = self.group_id
        return {
            "query": CREATE_ITEM_MUTATION,
            "variables": variables,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class MondayItemPublishResult:
    """Summary of a Monday.com item publish or dry run."""

    status_code: int | None
    board_id: str
    group_id: str | None
    item_id: str | None
    item_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class MondayItemPublisher:
    """Build and optionally create Monday.com items from approved ideas."""

    def __init__(
        self,
        board_id: str,
        *,
        api_token: str | None = None,
        group_id: str | None = None,
        item_name: str | None = None,
        column_values: dict[str, Any] | None = None,
        api_url: str = DEFAULT_MONDAY_API_URL,
        dry_run: bool = True,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = 0.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.board_id = _required_text(board_id, "Monday board_id is required")
        self.api_token = _optional_text(api_token)
        self.group_id = _optional_text(group_id)
        self.item_name = _optional_text(item_name)
        self.column_values = dict(column_values or {})
        self.api_url = _required_url(api_url)
        self.dry_run = dry_run
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_backoff = max(0.0, retry_backoff)
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        board_id: str | None = None,
        api_token: str | None = None,
        group_id: str | None = None,
        item_name: str | None = None,
        column_values: dict[str, Any] | None = None,
        api_url: str | None = None,
        dry_run: bool = True,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.Client | None = None,
    ) -> MondayItemPublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_board_id = board_id or os.getenv("MONDAY_BOARD_ID")
        if not resolved_board_id:
            raise MondayItemPublishError(
                "Monday board_id is required; pass board_id or set MONDAY_BOARD_ID"
            )
        return cls(
            resolved_board_id,
            api_token=api_token or os.getenv("MONDAY_API_TOKEN"),
            group_id=group_id or os.getenv("MONDAY_GROUP_ID"),
            item_name=item_name,
            column_values=column_values,
            api_url=api_url or os.getenv("MONDAY_API_URL", DEFAULT_MONDAY_API_URL),
            dry_run=dry_run,
            timeout=timeout,
            max_retries=max_retries,
            client=client,
        )

    @property
    def item_endpoint(self) -> str:
        """Return the Monday.com GraphQL endpoint used for item creation."""
        return self.api_url

    @property
    def has_auth(self) -> bool:
        """Return whether live Monday.com item publishing has credentials."""
        return bool(self.api_token)

    def build_item_payload(
        self,
        idea_or_spec: BuildableUnit | dict[str, Any],
        spec_preview: dict[str, Any] | None = None,
    ) -> MondayItemPayload:
        """Convert a BuildableUnit or generated TactSpec preview into a Monday.com item."""
        tact_spec = _coerce_tact_spec(idea_or_spec, spec_preview)
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")
        evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}

        metadata = {
            "publisher": "max.monday_items",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "idea"),
            "idea_id": source.get("idea_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "board_id": self.board_id,
            "group_id": self.group_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        column_values = {
            **_default_column_values(tact_spec),
            **self.column_values,
        }

        return MondayItemPayload(
            board_id=self.board_id,
            group_id=self.group_id,
            item_name=self.item_name or _item_name(project.get("title"), source.get("idea_id")),
            column_values=column_values,
            metadata=metadata,
        )

    def publish(
        self,
        idea_or_spec: BuildableUnit | dict[str, Any],
        *,
        spec_preview: dict[str, Any] | None = None,
        dry_run: bool | None = None,
    ) -> MondayItemPublishResult:
        """Build the item payload and optionally create it in Monday.com."""
        dry_run = self.dry_run if dry_run is None else dry_run
        payload = self.build_item_payload(idea_or_spec, spec_preview).to_dict()
        if dry_run:
            return MondayItemPublishResult(
                status_code=None,
                board_id=self.board_id,
                group_id=self.group_id,
                item_id=None,
                item_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self.has_auth:
            raise MondayItemPublishError(
                "MONDAY_API_TOKEN is required for live Monday.com item publishing; "
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
            raise MondayItemPublishError(
                f"Monday.com item publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response, api_token=self.api_token)}",
                status_code=response.status_code,
                api_token=self.api_token,
            )

        body = _json_response(response, api_token=self.api_token)
        errors = body.get("errors")
        if errors:
            raise MondayItemPublishError(
                f"Monday.com item publish failed with GraphQL errors: {errors}",
                status_code=response.status_code,
                api_token=self.api_token,
            )

        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        item = data.get("create_item") if isinstance(data.get("create_item"), dict) else {}
        item_id = item.get("id")
        if not item_id:
            raise MondayItemPublishError(
                "Monday.com item publish failed: response did not include created item id",
                status_code=response.status_code,
                api_token=self.api_token,
            )

        item_url = item.get("url")
        return MondayItemPublishResult(
            status_code=response.status_code,
            board_id=self.board_id,
            group_id=self.group_id,
            item_id=str(item_id),
            item_url=str(item_url) if item_url else None,
            dry_run=False,
            payload={
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "monday_item_id": str(item_id),
                    "monday_item_url": str(item_url) if item_url else None,
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
                    self.item_endpoint,
                    json=_monday_item_request(payload),
                    headers={
                        "Authorization": self.api_token or "",
                        "API-Version": "2023-10",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "User-Agent": "max-monday-items-publisher/1",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise MondayItemPublishError(
                    f"Monday.com item publish failed for {self.item_endpoint}: {exc}",
                    api_token=self.api_token,
                ) from exc

            last_response = response
            if response.status_code not in TRANSIENT_STATUS_CODES or attempt >= self.max_retries:
                return response
            if self.retry_backoff:
                time.sleep(self.retry_backoff * (attempt + 1))

        return last_response


MondayItemsPublisher = MondayItemPublisher


def _monday_item_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "query": payload["query"],
        "variables": payload["variables"],
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


def _default_column_values(tact_spec: dict[str, Any]) -> dict[str, Any]:
    problem = _dict_value(tact_spec, "problem")
    solution = _dict_value(tact_spec, "solution")
    execution = _dict_value(tact_spec, "execution")
    source = _dict_value(tact_spec, "source")
    evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}

    return {
        "problem": _text_or_placeholder(problem.get("statement")),
        "solution": _text_or_placeholder(solution.get("approach")),
        "recommendation": _text_or_placeholder(evaluation.get("recommendation")),
        "score": _score_value(evaluation.get("overall_score")),
        "validation_plan": _text_or_placeholder(execution.get("validation_plan")),
        "source_idea_id": _text_or_placeholder(source.get("idea_id")),
    }


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _item_name(title: object, idea_id: object) -> str:
    base = str(title).strip() if title else str(idea_id or "Generated TactSpec").strip()
    return f"[Max] {base}"[:255]


def _text_or_placeholder(value: object) -> str:
    text = str(value).strip() if value else ""
    return text or "Not specified"


def _score_value(value: object) -> float | str:
    if isinstance(value, int | float):
        return float(value)
    return _text_or_placeholder(value)


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise MondayItemPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _required_url(value: object) -> str:
    raw = _required_text(value, "Monday api_url is required").rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise MondayItemPublishError("Monday api_url must be an absolute http(s) URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _response_body_preview(
    response: httpx.Response,
    *,
    api_token: str | None = None,
    limit: int = 500,
) -> str:
    text = _redact_text(response.text.strip(), api_token=api_token)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response, *, api_token: str | None = None) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise MondayItemPublishError(
            "Monday.com item publish failed: response was not valid JSON",
            status_code=response.status_code,
            api_token=api_token,
        ) from exc
    return body if isinstance(body, dict) else {}


def _redact_text(text: str, *, api_token: str | None = None) -> str:
    redacted = text
    token = _optional_text(api_token)
    if token:
        redacted = redacted.replace(token, REDACTED)
    redacted = re.sub(
        r"(?i)\b(token|api_token|password|secret|authorization)\b([=:]\s*)[^&\s,'\"}]+",
        rf"\1\2{REDACTED}",
        redacted,
    )
    redacted = re.sub(r"(?i)(bearer\s+)[^\s,;)}\]]+", rf"\1{REDACTED}", redacted)
    return redacted

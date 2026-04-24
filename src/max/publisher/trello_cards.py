"""Trello card publisher for generated TactSpecs."""

from __future__ import annotations

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


DEFAULT_TRELLO_API_URL = "https://api.trello.com/1"
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


class TrelloCardPublishError(RuntimeError):
    """Raised when a Trello card publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(_redact_text(message))
        self.status_code = status_code


@dataclass(frozen=True)
class TrelloCardPayload:
    """Trello card creation payload plus Max-specific metadata."""

    name: str
    desc: str
    list_id: str
    labels: list[str]
    due: str | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable Trello card payload preview."""
        payload: dict[str, Any] = {
            "name": self.name,
            "desc": self.desc,
            "idList": self.list_id,
            "labels": self.labels,
            "metadata": self.metadata,
        }
        if self.due:
            payload["due"] = self.due
        return payload


@dataclass(frozen=True)
class TrelloCardPublishResult:
    """Summary of a Trello card publish or dry run."""

    status_code: int | None
    list_id: str
    card_id: str | None
    card_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class TrelloCardPublisher:
    """Build and optionally create Trello cards from approved ideas."""

    def __init__(
        self,
        list_id: str,
        *,
        key: str | None = None,
        token: str | None = None,
        api_url: str = DEFAULT_TRELLO_API_URL,
        labels: list[str] | None = None,
        due: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = 0.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.list_id = _required_text(list_id, "Trello list_id is required")
        self.key = _optional_text(key)
        self.token = _optional_text(token)
        self.api_url = _required_url(api_url)
        self.labels = [_required_text(label, "Trello labels must be non-empty") for label in labels or []]
        self.due = _optional_text(due)
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_backoff = max(0.0, retry_backoff)
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        list_id: str | None = None,
        key: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        labels: list[str] | None = None,
        due: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.Client | None = None,
    ) -> TrelloCardPublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_list_id = list_id or os.getenv("TRELLO_LIST_ID")
        if not resolved_list_id:
            raise TrelloCardPublishError(
                "Trello list_id is required; pass list_id or set TRELLO_LIST_ID"
            )
        return cls(
            resolved_list_id,
            key=key or os.getenv("TRELLO_KEY"),
            token=token or os.getenv("TRELLO_TOKEN"),
            api_url=api_url or os.getenv("TRELLO_API_URL", DEFAULT_TRELLO_API_URL),
            labels=labels,
            due=due,
            timeout=timeout,
            max_retries=max_retries,
            client=client,
        )

    @property
    def card_endpoint(self) -> str:
        """Return the Trello REST endpoint used for card creation."""
        return f"{self.api_url}/cards"

    @property
    def has_auth(self) -> bool:
        """Return whether live Trello card publishing has credentials."""
        return bool(self.key and self.token)

    def build_card_payload(
        self,
        idea_or_spec: BuildableUnit | dict[str, Any],
        spec_preview: dict[str, Any] | None = None,
    ) -> TrelloCardPayload:
        """Convert a BuildableUnit or generated TactSpec preview into a Trello card payload."""
        tact_spec = _coerce_tact_spec(idea_or_spec, spec_preview)
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")
        quality = _dict_value(tact_spec, "quality")
        evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}

        metadata = {
            "publisher": "max.trello_cards",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "idea"),
            "idea_id": source.get("idea_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "list_id": self.list_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        return TrelloCardPayload(
            name=_card_name(project.get("title"), source.get("idea_id")),
            desc=_card_description(tact_spec, metadata),
            list_id=self.list_id,
            labels=_merge_labels(
                _card_labels(source=source, quality=quality, evaluation=evaluation),
                self.labels,
            ),
            due=self.due,
            metadata=metadata,
        )

    def publish(
        self,
        idea_or_spec: BuildableUnit | dict[str, Any],
        *,
        spec_preview: dict[str, Any] | None = None,
        dry_run: bool = True,
    ) -> TrelloCardPublishResult:
        """Build the card payload and optionally create it in Trello."""
        payload = self.build_card_payload(idea_or_spec, spec_preview).to_dict()
        if dry_run:
            return TrelloCardPublishResult(
                status_code=None,
                list_id=self.list_id,
                card_id=None,
                card_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self.has_auth:
            raise TrelloCardPublishError(
                "TRELLO_KEY and TRELLO_TOKEN are required for live Trello card publishing; "
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
            raise TrelloCardPublishError(
                f"Trello card publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        card_id = body.get("id")
        if not card_id:
            raise TrelloCardPublishError(
                "Trello card publish failed: response did not include created card id",
                status_code=response.status_code,
            )

        card_url = body.get("url") or body.get("shortUrl")
        return TrelloCardPublishResult(
            status_code=response.status_code,
            list_id=self.list_id,
            card_id=str(card_id),
            card_url=str(card_url) if card_url else None,
            dry_run=False,
            payload={
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "trello_card_id": str(card_id),
                    "trello_card_url": str(card_url) if card_url else None,
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
                    self.card_endpoint,
                    params={"key": self.key, "token": self.token},
                    json=_trello_card_request(payload),
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "User-Agent": "max-trello-cards-publisher/1",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                message = _redact_text(str(exc))
                raise TrelloCardPublishError(
                    f"Trello card publish failed for {_redact_url(self.card_endpoint)}: {message}"
                ) from exc

            last_response = response
            if response.status_code not in TRANSIENT_STATUS_CODES or attempt >= self.max_retries:
                return response
            if self.retry_backoff:
                time.sleep(self.retry_backoff * (attempt + 1))

        return last_response


TrelloCardsPublisher = TrelloCardPublisher


def _trello_card_request(payload: dict[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {
        "name": payload["name"],
        "desc": payload["desc"],
        "idList": payload["idList"],
    }
    if payload.get("labels"):
        request["idLabels"] = ",".join(payload["labels"])
    if payload.get("due"):
        request["due"] = payload["due"]
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


def _card_name(title: object, idea_id: object) -> str:
    base = str(title).strip() if title else str(idea_id or "Generated TactSpec").strip()
    return f"[Max] {base}"[:16384]


def _card_description(tact_spec: dict[str, Any], metadata: dict[str, Any]) -> str:
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


def _card_labels(
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
    return label[:16384]


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
        raise TrelloCardPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _required_url(value: object) -> str:
    raw = _required_text(value, "Trello api_url is required").rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise TrelloCardPublishError("Trello api_url must be an absolute http(s) URL")
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
        raise TrelloCardPublishError(
            "Trello card publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    return body if isinstance(body, dict) else {}


def _redact_text(text: str) -> str:
    redacted = re.sub(
        r"(?i)\b(token|api_token|password|secret|authorization|key)\b([=:]\s*)[^&\s,'\"}]+",
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

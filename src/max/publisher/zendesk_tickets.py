"""Zendesk ticket publisher for approved ideas and generated TactSpecs."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx

from max.types.buildable_unit import BuildableUnit


DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_PRIORITY = "normal"


class ZendeskTicketPublishError(RuntimeError):
    """Raised when a Zendesk ticket publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ZendeskTicketPayload:
    """Zendesk ticket creation payload plus Max-specific metadata."""

    subject: str
    description: str
    priority: str
    tags: list[str]
    custom_fields: list[dict[str, Any]]
    metadata: dict[str, Any]
    requester_email: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable Zendesk ticket payload preview."""
        payload: dict[str, Any] = {
            "subject": self.subject,
            "description": self.description,
            "priority": self.priority,
            "tags": self.tags,
            "custom_fields": self.custom_fields,
            "metadata": self.metadata,
        }
        if self.requester_email:
            payload["requester_email"] = self.requester_email
        return payload


@dataclass(frozen=True)
class ZendeskTicketPublishResult:
    """Summary of a Zendesk ticket publish or dry run."""

    status_code: int | None
    ticket_id: str | None
    ticket_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class ZendeskTicketPublisher:
    """Build and optionally create Zendesk tickets from approved Max payloads."""

    def __init__(
        self,
        subdomain: str | None = None,
        *,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        requester_email: str | None = None,
        tags: list[str] | None = None,
        priority: str = DEFAULT_PRIORITY,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = _zendesk_base_url(subdomain=subdomain, base_url=base_url)
        self.email = _optional_text(email)
        self.api_token = _optional_text(api_token)
        self.requester_email = _optional_text(requester_email)
        self.tags = [_tag_value(tag) for tag in tags or [] if _tag_value(tag)]
        self.priority = _required_priority(priority)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        subdomain: str | None = None,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        requester_email: str | None = None,
        tags: list[str] | None = None,
        priority: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> ZendeskTicketPublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_subdomain = subdomain or os.getenv("ZENDESK_SUBDOMAIN")
        resolved_base_url = base_url or os.getenv("ZENDESK_BASE_URL")
        if not resolved_subdomain and not resolved_base_url:
            raise ZendeskTicketPublishError(
                "Zendesk subdomain or base_url is required; pass subdomain/base_url "
                "or set ZENDESK_SUBDOMAIN/ZENDESK_BASE_URL"
            )
        return cls(
            subdomain=resolved_subdomain,
            base_url=resolved_base_url,
            email=email or os.getenv("ZENDESK_EMAIL"),
            api_token=api_token or os.getenv("ZENDESK_API_TOKEN"),
            requester_email=requester_email or os.getenv("ZENDESK_REQUESTER_EMAIL"),
            tags=tags if tags is not None else _env_list("ZENDESK_TAGS"),
            priority=priority or os.getenv("ZENDESK_PRIORITY", DEFAULT_PRIORITY),
            timeout=timeout,
            client=client,
        )

    @property
    def tickets_endpoint(self) -> str:
        """Return the Zendesk REST endpoint used for ticket creation."""
        return f"{self.base_url}/api/v2/tickets.json"

    def build_ticket_payload(
        self,
        idea_or_spec: BuildableUnit | dict[str, Any],
        spec_preview: dict[str, Any] | None = None,
    ) -> ZendeskTicketPayload:
        """Convert a BuildableUnit or generated TactSpec preview into a ticket payload."""
        tact_spec = _coerce_tact_spec(idea_or_spec, spec_preview)
        _validate_tact_spec(tact_spec)
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")
        quality = _dict_value(tact_spec, "quality")
        evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}
        source_id = source.get("idea_id") or source.get("design_brief_id")

        metadata = {
            "publisher": "max.zendesk_tickets",
            "source_system": source.get("system", "max"),
            "source_type": source.get("type", "idea"),
            "source_id": source_id,
            "idea_id": source.get("idea_id"),
            "design_brief_id": source.get("design_brief_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "priority": self.priority,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        return ZendeskTicketPayload(
            subject=_ticket_subject(project.get("title"), source_id),
            description=_ticket_description(tact_spec, metadata),
            priority=self.priority,
            tags=_merge_tags(
                _ticket_tags(source=source, quality=quality, evaluation=evaluation),
                self.tags,
            ),
            custom_fields=_custom_fields(metadata),
            metadata=metadata,
            requester_email=self.requester_email,
        )

    def publish(
        self,
        idea_or_spec: BuildableUnit | dict[str, Any],
        *,
        spec_preview: dict[str, Any] | None = None,
        dry_run: bool = True,
    ) -> ZendeskTicketPublishResult:
        """Build the ticket payload and optionally create it in Zendesk."""
        payload = self.build_ticket_payload(idea_or_spec, spec_preview).to_dict()
        if dry_run:
            return ZendeskTicketPublishResult(
                status_code=None,
                ticket_id=None,
                ticket_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self.email or not self.api_token:
            raise ZendeskTicketPublishError(
                "ZENDESK_EMAIL and ZENDESK_API_TOKEN are required for live Zendesk "
                "ticket publishing; use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.tickets_endpoint,
                    json=_zendesk_ticket_request(payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise ZendeskTicketPublishError(
                    f"Zendesk ticket publish failed for {self.tickets_endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise ZendeskTicketPublishError(
                f"Zendesk ticket publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        ticket = body.get("ticket") if isinstance(body.get("ticket"), dict) else {}
        ticket_id = ticket.get("id") or body.get("id")
        if ticket_id is None:
            raise ZendeskTicketPublishError(
                "Zendesk ticket publish failed: response did not include created ticket id",
                status_code=response.status_code,
            )

        ticket_url = _ticket_url(self.base_url, ticket_id)
        return ZendeskTicketPublishResult(
            status_code=response.status_code,
            ticket_id=str(ticket_id),
            ticket_url=ticket_url,
            dry_run=False,
            payload={
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "zendesk_ticket_id": str(ticket_id),
                    "zendesk_ticket_url": ticket_url,
                },
            },
        )

    def _headers(self) -> dict[str, str]:
        assert self.email is not None and self.api_token is not None
        credentials = f"{self.email}/token:{self.api_token}".encode("utf-8")
        return {
            "Accept": "application/json",
            "Authorization": f"Basic {base64.b64encode(credentials).decode('ascii')}",
            "Content-Type": "application/json",
            "User-Agent": "max-zendesk-tickets-publisher/1",
        }


ZendeskTicketsPublisher = ZendeskTicketPublisher


def _zendesk_ticket_request(payload: dict[str, Any]) -> dict[str, Any]:
    ticket: dict[str, Any] = {
        "subject": payload["subject"],
        "comment": {"body": payload["description"]},
        "priority": payload["priority"],
        "tags": payload.get("tags") or [],
        "custom_fields": payload.get("custom_fields") or [],
    }
    if payload.get("requester_email"):
        ticket["requester"] = {"email": payload["requester_email"]}
    return {"ticket": ticket}


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


def _validate_tact_spec(tact_spec: dict[str, Any]) -> None:
    if not isinstance(tact_spec, dict):
        raise ZendeskTicketPublishError("Zendesk ticket publishing requires a TactSpec dict")
    project = _dict_value(tact_spec, "project")
    source = _dict_value(tact_spec, "source")
    if not _optional_text(project.get("title")) and not (
        _optional_text(source.get("idea_id")) or _optional_text(source.get("design_brief_id"))
    ):
        raise ZendeskTicketPublishError(
            "Zendesk ticket publishing requires project.title or a source id"
        )
    if not _optional_text(tact_spec.get("schema_version")):
        raise ZendeskTicketPublishError(
            "Zendesk ticket publishing requires schema_version in the TactSpec payload"
        )


def _ticket_subject(title: object, source_id: object) -> str:
    base = str(title).strip() if title else str(source_id or "Generated TactSpec").strip()
    return f"[Max] {base}"[:255]


def _ticket_description(tact_spec: dict[str, Any], metadata: dict[str, Any]) -> str:
    project = _dict_value(tact_spec, "project")
    problem = _dict_value(tact_spec, "problem")
    solution = _dict_value(tact_spec, "solution")
    execution = _dict_value(tact_spec, "execution")
    evidence = _dict_value(tact_spec, "evidence")
    source = _dict_value(tact_spec, "source")
    evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}

    lines = [
        f"# {project.get('title') or source.get('idea_id') or source.get('design_brief_id') or 'Generated TactSpec'}",
        "",
        _text_or_placeholder(project.get("summary")),
        "",
        "## Source",
        f"- Type: {_text_or_placeholder(source.get('type'))}",
        f"- Idea ID: {_text_or_placeholder(source.get('idea_id'))}",
        f"- Design brief ID: {_text_or_placeholder(source.get('design_brief_id'))}",
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
        ]
    )
    return "\n".join(lines)


def _ticket_tags(
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


def _custom_fields(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    fields = {
        "max_source_system": metadata.get("source_system"),
        "max_source_type": metadata.get("source_type"),
        "max_source_id": metadata.get("source_id"),
        "max_idea_id": metadata.get("idea_id"),
        "max_schema_version": metadata.get("schema_version"),
        "max_kind": metadata.get("kind"),
    }
    return [
        {"id": key, "value": value}
        for key, value in fields.items()
        if value is not None
    ]


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


def _zendesk_base_url(*, subdomain: str | None, base_url: str | None) -> str:
    if base_url:
        raw = _required_text(base_url, "Zendesk base_url is required").rstrip("/")
        if not raw.startswith(("http://", "https://")):
            raw = f"https://{raw}"
        parts = urlsplit(raw)
        if not parts.netloc:
            raise ZendeskTicketPublishError("Zendesk base_url must include a host")
        return raw.lower()

    raw_subdomain = _required_text(subdomain, "Zendesk subdomain is required").strip().rstrip("/")
    if "://" in raw_subdomain:
        parts = urlsplit(raw_subdomain)
        raw_subdomain = parts.netloc or parts.path
    domain = raw_subdomain if "." in raw_subdomain else f"{raw_subdomain}.zendesk.com"
    if "/" in domain or not domain:
        raise ZendeskTicketPublishError(
            "Zendesk subdomain must be a subdomain, domain, or base_url"
        )
    return f"https://{domain.lower()}"


def _required_priority(value: object) -> str:
    priority = _required_text(value, "Zendesk priority is required").lower()
    if priority not in {"low", "normal", "high", "urgent"}:
        raise ZendeskTicketPublishError(
            "Zendesk priority must be one of: low, normal, high, urgent"
        )
    return priority


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise ZendeskTicketPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _env_list(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def _ticket_url(base_url: str, ticket_id: object) -> str:
    return f"{base_url}/agent/tickets/{ticket_id}"


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise ZendeskTicketPublishError(
            "Zendesk ticket publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    return body if isinstance(body, dict) else {}

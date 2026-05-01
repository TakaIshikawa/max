"""Freshdesk ticket publisher for generated TactSpecs."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx


DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_PRIORITY = 2
DEFAULT_STATUS = 2


class FreshdeskTicketPublishError(RuntimeError):
    """Raised when a Freshdesk ticket publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class FreshdeskTicketPayload:
    """Freshdesk ticket creation payload plus Max-specific metadata."""

    subject: str
    description: str
    priority: int
    status: int
    tags: list[str]
    custom_fields: dict[str, Any]
    metadata: dict[str, Any]
    email: str | None = None
    product_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable Freshdesk ticket payload preview."""
        payload: dict[str, Any] = {
            "subject": self.subject,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "tags": self.tags,
            "custom_fields": self.custom_fields,
            "metadata": self.metadata,
        }
        if self.email:
            payload["email"] = self.email
        if self.product_id is not None:
            payload["product_id"] = self.product_id
        return payload


@dataclass(frozen=True)
class FreshdeskTicketPublishResult:
    """Summary of a Freshdesk ticket publish or dry run."""

    status_code: int | None
    ticket_id: str | None
    ticket_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class FreshdeskTicketPublisher:
    """Build and optionally create Freshdesk tickets from TactSpec previews."""

    def __init__(
        self,
        domain: str,
        *,
        api_key: str | None = None,
        requester_email: str | None = None,
        product_id: int | str | None = None,
        tags: list[str] | None = None,
        priority: int = DEFAULT_PRIORITY,
        status: int = DEFAULT_STATUS,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.domain = _required_domain(domain)
        self.api_key = _optional_text(api_key)
        self.requester_email = _optional_text(requester_email)
        self.product_id = _optional_int(product_id, "Freshdesk product_id must be an integer")
        self.tags = [_tag_value(tag) for tag in tags or [] if _tag_value(tag)]
        self.priority = _required_int(priority, "Freshdesk priority must be an integer")
        self.status = _required_int(status, "Freshdesk status must be an integer")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        domain: str | None = None,
        api_key: str | None = None,
        requester_email: str | None = None,
        product_id: int | str | None = None,
        tags: list[str] | None = None,
        priority: int | None = None,
        status: int | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> FreshdeskTicketPublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_domain = domain or os.getenv("FRESHDESK_DOMAIN")
        if not resolved_domain:
            raise FreshdeskTicketPublishError(
                "Freshdesk domain is required; pass domain or set FRESHDESK_DOMAIN"
            )
        resolved_tags = tags if tags is not None else _env_list("FRESHDESK_TAGS")
        return cls(
            resolved_domain,
            api_key=api_key or os.getenv("FRESHDESK_API_KEY"),
            requester_email=requester_email or os.getenv("FRESHDESK_REQUESTER_EMAIL"),
            product_id=product_id if product_id is not None else os.getenv("FRESHDESK_PRODUCT_ID"),
            tags=resolved_tags,
            priority=priority if priority is not None else _env_int("FRESHDESK_PRIORITY", DEFAULT_PRIORITY),
            status=status if status is not None else _env_int("FRESHDESK_STATUS", DEFAULT_STATUS),
            timeout=timeout,
            client=client,
        )

    @property
    def tickets_endpoint(self) -> str:
        """Return the Freshdesk REST endpoint used for ticket creation."""
        return f"https://{self.domain}/api/v2/tickets"

    def build_ticket_payload(self, tact_spec: dict[str, Any]) -> FreshdeskTicketPayload:
        """Convert a generated TactSpec preview into a Freshdesk ticket payload."""
        _validate_tact_spec(tact_spec)
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")
        quality = _dict_value(tact_spec, "quality")
        evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}

        source_type = str(source.get("type") or "idea")
        source_id = source.get("idea_id") or source.get("design_brief_id")
        metadata = {
            "publisher": "max.freshdesk_tickets",
            "source_system": source.get("system", "max"),
            "source_type": source_type,
            "source_id": source_id,
            "idea_id": source.get("idea_id"),
            "design_brief_id": source.get("design_brief_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "product_id": self.product_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        return FreshdeskTicketPayload(
            subject=_ticket_subject(project.get("title"), source_id),
            description=_ticket_description(tact_spec, metadata),
            priority=self.priority,
            status=self.status,
            tags=_merge_tags(
                _ticket_tags(source=source, quality=quality, evaluation=evaluation),
                self.tags,
            ),
            custom_fields=_custom_fields(metadata),
            metadata=metadata,
            email=self.requester_email,
            product_id=self.product_id,
        )

    def publish(
        self,
        tact_spec: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> FreshdeskTicketPublishResult:
        """Build the ticket payload and optionally create it in Freshdesk."""
        payload = self.build_ticket_payload(tact_spec).to_dict()
        if dry_run:
            return FreshdeskTicketPublishResult(
                status_code=None,
                ticket_id=None,
                ticket_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self.api_key:
            raise FreshdeskTicketPublishError(
                "FRESHDESK_API_KEY is required for live Freshdesk ticket publishing; "
                "use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.tickets_endpoint,
                    json=_freshdesk_ticket_request(payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise FreshdeskTicketPublishError(
                    f"Freshdesk ticket publish failed for {self.tickets_endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise FreshdeskTicketPublishError(
                f"Freshdesk ticket publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        ticket_id = body.get("id")
        if ticket_id is None:
            raise FreshdeskTicketPublishError(
                "Freshdesk ticket publish failed: response did not include created ticket id",
                status_code=response.status_code,
            )

        ticket_url = _ticket_url(self.domain, ticket_id)
        return FreshdeskTicketPublishResult(
            status_code=response.status_code,
            ticket_id=str(ticket_id),
            ticket_url=ticket_url,
            dry_run=False,
            payload={
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "freshdesk_ticket_id": str(ticket_id),
                    "freshdesk_ticket_url": ticket_url,
                },
            },
        )

    def _headers(self) -> dict[str, str]:
        assert self.api_key is not None
        credentials = f"{self.api_key}:X".encode("utf-8")
        return {
            "Accept": "application/json",
            "Authorization": f"Basic {base64.b64encode(credentials).decode('ascii')}",
            "Content-Type": "application/json",
            "User-Agent": "max-freshdesk-tickets-publisher/1",
        }


FreshdeskTicketsPublisher = FreshdeskTicketPublisher


def _freshdesk_ticket_request(payload: dict[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {
        "subject": payload["subject"],
        "description": payload["description"],
        "priority": payload["priority"],
        "status": payload["status"],
        "tags": payload.get("tags") or [],
        "custom_fields": payload.get("custom_fields") or {},
    }
    if payload.get("email"):
        request["email"] = payload["email"]
    if payload.get("product_id") is not None:
        request["product_id"] = payload["product_id"]
    return request


def _validate_tact_spec(tact_spec: dict[str, Any]) -> None:
    if not isinstance(tact_spec, dict):
        raise FreshdeskTicketPublishError("Freshdesk ticket publishing requires a TactSpec dict")
    project = _dict_value(tact_spec, "project")
    source = _dict_value(tact_spec, "source")
    if not _optional_text(project.get("title")) and not (
        _optional_text(source.get("idea_id")) or _optional_text(source.get("design_brief_id"))
    ):
        raise FreshdeskTicketPublishError(
            "Freshdesk ticket publishing requires project.title or a source id"
        )
    if not _optional_text(tact_spec.get("schema_version")):
        raise FreshdeskTicketPublishError(
            "Freshdesk ticket publishing requires schema_version in the TactSpec payload"
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


def _custom_fields(metadata: dict[str, Any]) -> dict[str, Any]:
    custom_fields = {
        "cf_max_source_system": metadata.get("source_system"),
        "cf_max_source_type": metadata.get("source_type"),
        "cf_max_source_id": metadata.get("source_id"),
        "cf_max_idea_id": metadata.get("idea_id"),
        "cf_max_schema_version": metadata.get("schema_version"),
        "cf_max_kind": metadata.get("kind"),
    }
    return {key: value for key, value in custom_fields.items() if value is not None}


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


def _required_domain(value: object) -> str:
    raw = _required_text(value, "Freshdesk domain is required").strip().rstrip("/")
    if "://" in raw:
        parts = urlsplit(raw)
        raw = parts.netloc or parts.path
    domain = raw.removesuffix(".freshdesk.com") + ".freshdesk.com" if "." not in raw else raw
    if "/" in domain or not domain:
        raise FreshdeskTicketPublishError("Freshdesk domain must be a domain name or subdomain")
    return domain.lower()


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise FreshdeskTicketPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _required_int(value: object, message: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise FreshdeskTicketPublishError(message) from exc


def _optional_int(value: object, message: str) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return _required_int(value, message)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return _required_int(value, f"{name} must be an integer")


def _env_list(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def _ticket_url(domain: str, ticket_id: object) -> str:
    return f"https://{domain}/a/tickets/{ticket_id}"


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise FreshdeskTicketPublishError(
            "Freshdesk ticket publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    return body if isinstance(body, dict) else {}


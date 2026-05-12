"""Freshdesk ticket reply publisher."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx


DEFAULT_TIMEOUT_SECONDS = 10.0


class FreshdeskTicketReplyPublishError(RuntimeError):
    """Raised when a Freshdesk ticket reply cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class FreshdeskTicketReplyPayload:
    """Freshdesk ticket reply payload plus Max-specific metadata."""

    ticket_id: str
    body: str
    from_email: str | None
    user_id: int | None
    cc_emails: list[str]
    attachments: list[dict[str, Any]]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ticket_id": self.ticket_id,
            "body": self.body,
            "cc_emails": self.cc_emails,
            "attachments": self.attachments,
            "metadata": self.metadata,
        }
        if self.from_email:
            payload["from_email"] = self.from_email
        if self.user_id is not None:
            payload["user_id"] = self.user_id
        return payload

    def to_request(self) -> dict[str, Any]:
        request: dict[str, Any] = {"body": self.body}
        if self.from_email:
            request["from_email"] = self.from_email
        if self.user_id is not None:
            request["user_id"] = self.user_id
        if self.cc_emails:
            request["cc_emails"] = self.cc_emails
        if self.attachments:
            request["attachments"] = self.attachments
        return request


@dataclass(frozen=True)
class FreshdeskTicketReplyPublishResult:
    """Summary of a Freshdesk ticket reply publish or dry run."""

    status_code: int | None
    ticket_id: str
    conversation_id: str | None
    body_preview: str
    dry_run: bool
    payload: dict[str, Any]


class FreshdeskTicketReplyPublisher:
    """Build and optionally post public replies to Freshdesk tickets."""

    def __init__(
        self,
        domain: str,
        *,
        ticket_id: str | int | None = None,
        api_key: str | None = None,
        from_email: str | None = None,
        user_id: str | int | None = None,
        cc_emails: list[str] | None = None,
        attachments: list[dict[str, Any]] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.domain = _required_domain(domain)
        self.ticket_id = _optional_text(ticket_id)
        self.api_key = _optional_text(api_key)
        self.from_email = _optional_text(from_email)
        self.user_id = _optional_int(user_id, "Freshdesk user_id must be an integer")
        self.cc_emails = [_required_text(email, "Freshdesk cc_emails must be non-empty") for email in cc_emails or []]
        self.attachments = [dict(item) for item in attachments or [] if isinstance(item, dict)]
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        domain: str | None = None,
        ticket_id: str | int | None = None,
        api_key: str | None = None,
        from_email: str | None = None,
        user_id: str | int | None = None,
        cc_emails: list[str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> FreshdeskTicketReplyPublisher:
        resolved_domain = domain or os.getenv("FRESHDESK_DOMAIN")
        if not resolved_domain:
            raise FreshdeskTicketReplyPublishError(
                "Freshdesk domain is required; pass domain or set FRESHDESK_DOMAIN"
            )
        return cls(
            resolved_domain,
            ticket_id=ticket_id or os.getenv("FRESHDESK_TICKET_ID"),
            api_key=api_key or os.getenv("FRESHDESK_API_KEY"),
            from_email=from_email or os.getenv("FRESHDESK_FROM_EMAIL"),
            user_id=user_id if user_id is not None else os.getenv("FRESHDESK_USER_ID"),
            cc_emails=cc_emails if cc_emails is not None else _env_list("FRESHDESK_CC_EMAILS"),
            timeout=timeout,
            client=client,
        )

    def reply_endpoint(self, ticket_id: str | None = None) -> str:
        resolved_ticket_id = _required_text(
            ticket_id or self.ticket_id,
            "Freshdesk ticket_id is required; pass ticket_id or set FRESHDESK_TICKET_ID",
        )
        return f"https://{self.domain}/api/v2/tickets/{resolved_ticket_id}/reply"

    def build_reply_payload(
        self,
        *,
        body: str,
        ticket_id: str | int | None = None,
        from_email: str | None = None,
        user_id: str | int | None = None,
        cc_emails: list[str] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> FreshdeskTicketReplyPayload:
        resolved_ticket_id = _required_text(
            ticket_id or self.ticket_id,
            "Freshdesk ticket_id is required; pass ticket_id or set FRESHDESK_TICKET_ID",
        )
        return FreshdeskTicketReplyPayload(
            ticket_id=resolved_ticket_id,
            body=_required_text(body, "Freshdesk reply body is required"),
            from_email=_optional_text(from_email) or self.from_email,
            user_id=_optional_int(user_id, "Freshdesk user_id must be an integer") if user_id is not None else self.user_id,
            cc_emails=[_required_text(email, "Freshdesk cc_emails must be non-empty") for email in (cc_emails if cc_emails is not None else self.cc_emails)],
            attachments=[dict(item) for item in (attachments if attachments is not None else self.attachments) if isinstance(item, dict)],
            metadata={
                "publisher": "max.freshdesk_ticket_replies",
                "freshdesk_ticket_id": resolved_ticket_id,
            },
        )

    def publish(
        self,
        *,
        body: str,
        ticket_id: str | int | None = None,
        dry_run: bool = True,
        from_email: str | None = None,
        user_id: str | int | None = None,
        cc_emails: list[str] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> FreshdeskTicketReplyPublishResult:
        payload_obj = self.build_reply_payload(
            body=body,
            ticket_id=ticket_id,
            from_email=from_email,
            user_id=user_id,
            cc_emails=cc_emails,
            attachments=attachments,
        )
        payload = payload_obj.to_dict()
        if dry_run:
            return FreshdeskTicketReplyPublishResult(
                None,
                payload_obj.ticket_id,
                None,
                _preview(payload_obj.body),
                True,
                payload,
            )
        if not self.api_key:
            raise FreshdeskTicketReplyPublishError(
                "FRESHDESK_API_KEY is required for live Freshdesk ticket reply publishing; use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.reply_endpoint(payload_obj.ticket_id),
                    json=payload_obj.to_request(),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise FreshdeskTicketReplyPublishError(
                    f"Freshdesk ticket reply publish failed for {self.reply_endpoint(payload_obj.ticket_id)}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise FreshdeskTicketReplyPublishError(
                f"Freshdesk ticket reply publish failed with HTTP {response.status_code}: {_response_body_preview(response)}",
                status_code=response.status_code,
            )

        response_body = _json_response(response)
        conversation_id = _optional_text(response_body.get("id"))
        return FreshdeskTicketReplyPublishResult(
            response.status_code,
            payload_obj.ticket_id,
            conversation_id,
            _preview(payload_obj.body),
            False,
            {
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "freshdesk_conversation_id": conversation_id,
                    "api_status": response.status_code,
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
            "User-Agent": "max-freshdesk-ticket-replies-publisher/1",
        }


FreshdeskTicketRepliesPublisher = FreshdeskTicketReplyPublisher


def _required_domain(value: object) -> str:
    raw = _required_text(value, "Freshdesk domain is required").strip().rstrip("/")
    if "://" in raw:
        parts = urlsplit(raw)
        raw = parts.netloc or parts.path
    domain = raw.removesuffix(".freshdesk.com") + ".freshdesk.com" if "." not in raw else raw
    if "/" in domain or not domain:
        raise FreshdeskTicketReplyPublishError("Freshdesk domain must be a domain name or subdomain")
    return domain.lower()


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise FreshdeskTicketReplyPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _optional_int(value: object, message: str) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise FreshdeskTicketReplyPublishError(message) from exc


def _env_list(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def _preview(value: str, *, limit: int = 120) -> str:
    text = value.strip()
    return text if len(text) <= limit else text[:limit] + "..."


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    return text if len(text) <= limit else text[:limit] + "..."


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise FreshdeskTicketReplyPublishError(
            "Freshdesk ticket reply publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    return body if isinstance(body, dict) else {}

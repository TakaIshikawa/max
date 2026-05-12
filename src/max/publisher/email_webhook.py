"""Email webhook publisher for generated Max payloads."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, dict_value, optional_text
from max.publisher.webhook import (
    DEFAULT_RETRIES,
    WebhookPublishError,
    WebhookPublisher,
)

DEFAULT_SUBJECT_TEMPLATE = "[Max] {title}"
DEFAULT_PAYLOAD_TYPE = "max-email"


class EmailWebhookPublishError(RuntimeError):
    """Raised when an email webhook publish fails."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class EmailWebhookPayload:
    """Normalized email payload sent to automation webhooks."""

    to: str
    subject: str
    body: dict[str, str]
    payload_type: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "to": self.to,
            "subject": self.subject,
            "body": self.body,
            "payload_type": self.payload_type,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class EmailWebhookPublishResult:
    """Summary of a successful email webhook publish."""

    status_code: int
    attempts: int
    url: str
    response_body: str
    payload: dict[str, Any]


class EmailWebhookPublisher:
    """POST email-shaped Max payloads to a generic webhook endpoint."""

    def __init__(
        self,
        url: str,
        *,
        recipient: str | None = None,
        subject_template: str = DEFAULT_SUBJECT_TEMPLATE,
        payload_type: str = DEFAULT_PAYLOAD_TYPE,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        retries: int = DEFAULT_RETRIES,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.url = _required_url(
            url,
            "Email webhook url must be an absolute http(s) URL",
        )
        self.recipient = optional_text(recipient)
        self.subject_template = optional_text(subject_template) or DEFAULT_SUBJECT_TEMPLATE
        self.payload_type = optional_text(payload_type) or DEFAULT_PAYLOAD_TYPE
        self.timeout = timeout
        self.retries = retries
        self._client = client
        self._sleep = sleep

    @classmethod
    def from_env(
        cls,
        *,
        url: str | None = None,
        recipient: str | None = None,
        subject_template: str | None = None,
        payload_type: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        retries: int = DEFAULT_RETRIES,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> EmailWebhookPublisher:
        return cls(
            url or os.getenv("MAX_EMAIL_WEBHOOK_URL", ""),
            recipient=recipient or os.getenv("MAX_EMAIL_WEBHOOK_RECIPIENT"),
            subject_template=(
                subject_template
                or os.getenv("MAX_EMAIL_WEBHOOK_SUBJECT_TEMPLATE")
                or DEFAULT_SUBJECT_TEMPLATE
            ),
            payload_type=(
                payload_type
                or os.getenv("MAX_EMAIL_WEBHOOK_PAYLOAD_TYPE")
                or DEFAULT_PAYLOAD_TYPE
            ),
            timeout=timeout,
            retries=retries,
            client=client,
            sleep=sleep,
        )

    @property
    def redacted_url(self) -> str:
        return WebhookPublisher(self.url).redacted_url

    def build_payload(
        self,
        source: dict[str, Any],
        *,
        recipient: str | None = None,
        subject_template: str | None = None,
        payload_type: str | None = None,
        text_body: str | None = None,
        markdown_body: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EmailWebhookPayload:
        if not isinstance(source, dict):
            raise EmailWebhookPublishError("Email webhook publishing requires a Max payload dict")

        to = optional_text(recipient) or self.recipient
        if not to:
            raise EmailWebhookPublishError("Email webhook recipient is required")

        normalized_payload_type = optional_text(payload_type) or self.payload_type
        body = _body_fields(source, text_body=text_body, markdown_body=markdown_body)
        if not body:
            raise EmailWebhookPublishError(
                "Email webhook publishing requires text_body or markdown_body"
            )

        meta = _metadata(source, normalized_payload_type, metadata)
        subject = _render_subject(
            optional_text(subject_template) or self.subject_template,
            source=source,
            payload_type=normalized_payload_type,
            metadata=meta,
        )
        if not subject:
            raise EmailWebhookPublishError("Email webhook subject must not be empty")

        return EmailWebhookPayload(
            to=to,
            subject=subject,
            body=body,
            payload_type=normalized_payload_type,
            metadata=meta,
        )

    def publish(
        self,
        source: dict[str, Any],
        *,
        recipient: str | None = None,
        subject_template: str | None = None,
        payload_type: str | None = None,
        text_body: str | None = None,
        markdown_body: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EmailWebhookPublishResult:
        payload = self.build_payload(
            source,
            recipient=recipient,
            subject_template=subject_template,
            payload_type=payload_type,
            text_body=text_body,
            markdown_body=markdown_body,
            metadata=metadata,
        ).to_dict()
        try:
            result = WebhookPublisher(
                self.url,
                timeout=self.timeout,
                retries=self.retries,
                client=self._client,
                sleep=self._sleep,
            ).publish(payload, payload_type=payload["payload_type"])
        except WebhookPublishError as exc:
            raise EmailWebhookPublishError(
                str(exc),
                status_code=exc.status_code,
            ) from exc

        return EmailWebhookPublishResult(
            status_code=result.status_code,
            attempts=result.attempts,
            url=result.url,
            response_body=result.response_body,
            payload=payload,
        )


EmailWebhooksPublisher = EmailWebhookPublisher


def publish_email_webhook(source: dict[str, Any], **kwargs: Any) -> EmailWebhookPublishResult:
    publisher = EmailWebhookPublisher.from_env(
        url=kwargs.pop("url", None),
        recipient=kwargs.pop("recipient", None),
        subject_template=kwargs.pop("subject_template", None),
        payload_type=kwargs.pop("payload_type", None),
        client=kwargs.pop("client", None),
    )
    return publisher.publish(source, **kwargs)


def _required_url(value: object, message: str) -> str:
    url = optional_text(value)
    if not url:
        raise EmailWebhookPublishError(message)
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise EmailWebhookPublishError(message)
    return url


def _body_fields(
    source: dict[str, Any],
    *,
    text_body: str | None,
    markdown_body: str | None,
) -> dict[str, str]:
    source_body = dict_value(source, "body")
    text = (
        optional_text(text_body)
        or optional_text(source.get("text"))
        or optional_text(source_body.get("text"))
    )
    markdown = (
        optional_text(markdown_body)
        or optional_text(source.get("markdown"))
        or optional_text(source_body.get("markdown"))
    )

    body: dict[str, str] = {}
    if text:
        body["text"] = text
    if markdown:
        body["markdown"] = markdown
    return body


def _metadata(
    source: dict[str, Any],
    payload_type: str,
    extra: dict[str, Any] | None,
) -> dict[str, Any]:
    source_meta = dict_value(source, "metadata")
    source_info = dict_value(source, "source")
    metadata = {
        "publisher": "max.email_webhook",
        "payload_type": payload_type,
        "schema_version": source.get("schema_version"),
        "kind": source.get("kind"),
        "source_id": source_info.get("design_brief_id") or source_info.get("idea_id"),
    }
    metadata.update(source_meta)
    if extra:
        metadata.update(extra)
    return metadata


def _render_subject(
    template: str,
    *,
    source: dict[str, Any],
    payload_type: str,
    metadata: dict[str, Any],
) -> str:
    context = _SafeFormatMap(
        {
            "title": _title(source),
            "payload_type": payload_type,
            "schema_version": source.get("schema_version") or "",
            "kind": source.get("kind") or "",
            "metadata": metadata,
        }
    )
    try:
        return template.format_map(context).strip()
    except (KeyError, AttributeError, IndexError, ValueError) as exc:
        raise EmailWebhookPublishError(f"Invalid email webhook subject template: {exc}") from exc


def _title(source: dict[str, Any]) -> str:
    project = dict_value(source, "project")
    source_info = dict_value(source, "source")
    return (
        optional_text(source.get("title"))
        or optional_text(project.get("title"))
        or optional_text(source_info.get("design_brief_id"))
        or optional_text(source_info.get("idea_id"))
        or "Generated Max Payload"
    )


class _SafeFormatMap(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return ""

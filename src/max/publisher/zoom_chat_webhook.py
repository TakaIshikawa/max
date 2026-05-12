"""Zoom Team Chat incoming-webhook publisher for Max ideas and design briefs."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx

DEFAULT_TIMEOUT_SECONDS = 10.0
ZOOM_CHAT_TEXT_LIMIT = 4096


class ZoomChatWebhookPublishError(RuntimeError):
    """Raised when a Zoom Team Chat webhook publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


ZoomChatWebhookPayload = dict[str, Any]


@dataclass(frozen=True)
class ZoomChatWebhookPublishResult:
    """Summary of a Zoom Team Chat webhook publish or dry run."""

    status_code: int | None
    url: str
    dry_run: bool
    payload: ZoomChatWebhookPayload
    response_body: str = ""
    response_headers: dict[str, str] = field(default_factory=dict)
    payload_preview: str = ""


class ZoomChatWebhookPublisher:
    """Build and optionally publish Zoom Team Chat incoming-webhook messages."""

    def __init__(
        self,
        webhook_url: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not webhook_url.strip():
            raise ZoomChatWebhookPublishError("Zoom Chat webhook URL is required")
        _validate_webhook_url(webhook_url)
        self.webhook_url = webhook_url
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        webhook_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> ZoomChatWebhookPublisher:
        """Create a publisher using explicit values first, then environment variables."""
        resolved_url = webhook_url or os.getenv("ZOOM_CHAT_WEBHOOK_URL")
        if not resolved_url:
            raise ZoomChatWebhookPublishError(
                "Zoom Chat webhook URL is required; pass webhook_url or set "
                "ZOOM_CHAT_WEBHOOK_URL"
            )
        return cls(resolved_url, timeout=timeout, client=client)

    @property
    def redacted_url(self) -> str:
        """Return the Zoom webhook URL with path, query, and fragment secrets redacted."""
        return redact_zoom_chat_webhook_url(self.webhook_url)

    def build_payload(self, payload: dict[str, Any]) -> ZoomChatWebhookPayload:
        """Convert a Max idea or design brief payload into Zoom-compatible JSON."""
        message = _design_brief_message(payload) if _is_design_brief_payload(payload) else _idea_message(payload)
        return {
            "content": {
                "head": {"text": message["title"]},
                "body": message["body"],
            },
            "metadata": message["metadata"],
        }

    def publish(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> ZoomChatWebhookPublishResult:
        """Build a Zoom payload and optionally post it to the webhook URL."""
        zoom_payload = self.build_payload(payload)
        payload_preview = _truncate(_preview_text(zoom_payload), 500)
        if dry_run:
            return ZoomChatWebhookPublishResult(
                status_code=None,
                url=self.redacted_url,
                dry_run=True,
                payload=zoom_payload,
                payload_preview=payload_preview,
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(
                self.webhook_url,
                json=zoom_payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "max-zoom-chat-webhook-publisher/1",
                    "X-Max-Published-At": datetime.now(timezone.utc).isoformat(),
                },
                timeout=self.timeout,
            )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise ZoomChatWebhookPublishError(
                f"Zoom Chat webhook publish failed for {self.redacted_url}: {_redact_text(str(exc), self.webhook_url)}"
            ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise ZoomChatWebhookPublishError(
                f"Zoom Chat webhook publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response, webhook_url=self.webhook_url)}",
                status_code=response.status_code,
            )

        return ZoomChatWebhookPublishResult(
            status_code=response.status_code,
            url=self.redacted_url,
            dry_run=False,
            payload=zoom_payload,
            response_body=_response_body_preview(response, webhook_url=self.webhook_url),
            response_headers=dict(response.headers),
            payload_preview=payload_preview,
        )


ZoomChatWebhooksPublisher = ZoomChatWebhookPublisher


def publish_zoom_chat_webhook(
    payload: dict[str, Any],
    *,
    webhook_url: str | None = None,
    dry_run: bool = True,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    client: httpx.Client | None = None,
) -> ZoomChatWebhookPublishResult:
    """Publish a Max payload to a Zoom Team Chat incoming webhook."""
    publisher = ZoomChatWebhookPublisher.from_env(
        webhook_url=webhook_url,
        timeout=timeout,
        client=client,
    )
    return publisher.publish(payload, dry_run=dry_run)


def _idea_message(payload: dict[str, Any]) -> dict[str, Any]:
    source = _dict_value(payload, "source")
    project = _dict_value(payload, "project")
    evidence = _dict_value(payload, "evidence")
    evaluation = _dict_value(payload, "evaluation")
    quality = _dict_value(payload, "quality")
    execution = _dict_value(payload, "execution")

    title = _text(project.get("title"), source.get("idea_id"), "Untitled idea")
    summary = _text(project.get("summary"), project.get("value_proposition"), "No summary provided.")
    insight_ids = _string_list(evidence.get("insight_ids"))
    signal_ids = _string_list(evidence.get("signal_ids"))
    source_idea_ids = _string_list(evidence.get("source_idea_ids"))
    metadata = {
        "publisher": "max.zoom_chat_webhook",
        "provider": "zoom_chat",
        "source_type": "idea",
        "idea_id": source.get("idea_id"),
        "status": source.get("status"),
        "domain": source.get("domain"),
        "category": source.get("category"),
        "overall_score": evaluation.get("overall_score"),
        "recommendation": evaluation.get("recommendation"),
        "quality_score": quality.get("quality_score"),
        "insight_ids": insight_ids,
        "signal_ids": signal_ids,
        "source_idea_ids": source_idea_ids,
    }
    fields = [
        ("Summary", summary),
        ("Score", _score_text(evaluation.get("overall_score"))),
        ("Recommendation", evaluation.get("recommendation")),
        ("Idea ID", source.get("idea_id")),
        ("Status", source.get("status")),
        ("Domain", source.get("domain")),
        ("Quality", _score_text(quality.get("quality_score"))),
        ("Evidence", _source_identifier_text(insight_ids, signal_ids, source_idea_ids)),
        ("Validation", execution.get("validation_plan")),
    ]
    return {"title": f"[Max] {title}", "body": _zoom_fields(fields), "metadata": metadata}


def _design_brief_message(payload: dict[str, Any]) -> dict[str, Any]:
    source = _dict_value(payload, "source")
    brief = _dict_value(payload, "design_brief")
    evidence_refs = _dict_value(payload, "evidence_refs")
    brief_id = _text(brief.get("id"), source.get("id"))
    title = _text(brief.get("title"), brief_id, "Untitled design brief")
    summary = _text(brief.get("summary"), brief.get("merged_product_concept"), "No concept provided.")
    source_idea_ids = _string_list(brief.get("source_idea_ids") or evidence_refs.get("source_idea_ids"))
    insight_ids = _string_list(evidence_refs.get("insight_ids"))
    signal_ids = _string_list(evidence_refs.get("signal_ids"))
    recommendation = brief.get("recommendation") or brief.get("status_recommendation")
    markdown_preview = _truncate(_text(brief.get("markdown"), payload.get("markdown")), 1200)
    metadata = {
        "publisher": "max.zoom_chat_webhook",
        "provider": "zoom_chat",
        "source_type": "design_brief",
        "design_brief_id": brief_id,
        "lead_idea_id": brief.get("lead_idea_id"),
        "status": brief.get("design_status"),
        "domain": brief.get("domain"),
        "readiness_score": brief.get("readiness_score"),
        "recommendation": recommendation,
        "source_idea_ids": source_idea_ids,
        "insight_ids": insight_ids,
        "signal_ids": signal_ids,
    }
    fields = [
        ("Summary", summary),
        ("Brief ID", brief_id),
        ("Readiness", _score_text(brief.get("readiness_score"))),
        ("Recommendation", recommendation),
        ("Source ideas", _comma_list(source_idea_ids)),
        ("Lead idea", brief.get("lead_idea_id")),
        ("Status", brief.get("design_status")),
        ("Evidence", _source_identifier_text(insight_ids, signal_ids, source_idea_ids)),
    ]
    if markdown_preview:
        fields.append(("Markdown preview", markdown_preview))
    return {"title": f"[Max] {title}", "body": _zoom_fields(fields), "metadata": metadata}


def _zoom_fields(fields: list[tuple[str, object]]) -> list[dict[str, Any]]:
    rendered = [
        {
            "type": "message",
            "text": f"*{label}:* {_text(value, 'Not specified')}",
        }
        for label, value in fields
        if _text(value, "")
    ]
    return rendered or [{"type": "message", "text": "No details provided."}]


def _preview_text(payload: ZoomChatWebhookPayload) -> str:
    content = _dict_value(payload, "content")
    head = _dict_value(content, "head")
    body = content.get("body") if isinstance(content.get("body"), list) else []
    lines = [_text(head.get("text"))]
    lines.extend(_text(item.get("text")) for item in body if isinstance(item, dict))
    return "\n".join(line for line in lines if line)


def _is_design_brief_payload(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("design_brief"), dict)


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _string_list(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    return [_text(item, "") for item in items if _text(item, "")]


def _source_identifier_text(
    insight_ids: list[str],
    signal_ids: list[str],
    source_idea_ids: list[str],
) -> str:
    return "; ".join(
        [
            f"insights={_comma_list(insight_ids)}",
            f"signals={_comma_list(signal_ids)}",
            f"source_ideas={_comma_list(source_idea_ids)}",
        ]
    )


def _comma_list(items: list[str]) -> str:
    return ", ".join(items) if items else "None"


def _text(*values: object) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _score_text(value: object) -> str:
    if isinstance(value, int | float):
        return f"{value:.1f}"
    return _text(value, "Not specified")


def _truncate(value: str, limit: int = ZOOM_CHAT_TEXT_LIMIT) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _validate_webhook_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ZoomChatWebhookPublishError("Zoom Chat webhook URL must be an absolute http(s) URL")


def _response_body_preview(
    response: httpx.Response,
    *,
    webhook_url: str,
    limit: int = 500,
) -> str:
    text = _redact_text(response.text.strip(), webhook_url)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _redact_text(text: str, webhook_url: str) -> str:
    redacted = text
    parts = urlsplit(webhook_url)
    if parts.query:
        redacted = redacted.replace(parts.query, "[redacted]")
        for query_part in parts.query.split("&"):
            if "=" in query_part:
                redacted = redacted.replace(query_part.split("=", 1)[1], "[redacted]")
    for path_part in parts.path.split("/"):
        if path_part and len(path_part) >= 8:
            redacted = redacted.replace(path_part, "[redacted]")
    return redacted


def redact_zoom_chat_webhook_url(url: str) -> str:
    """Redact Zoom webhook URL secrets while keeping the target recognizable."""
    parts = urlsplit(url)
    path_parts = parts.path.split("/")
    if path_parts and path_parts[-1]:
        path_parts[-1] = "[redacted]"
    netloc = parts.hostname or ""
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    if parts.username or parts.password:
        netloc = f"***@{netloc}"
    return urlunsplit(
        SplitResult(
            scheme=parts.scheme,
            netloc=netloc,
            path="/".join(path_parts),
            query="[redacted]" if parts.query else "",
            fragment="[redacted]" if parts.fragment else "",
        )
    )

"""Google Chat incoming-webhook publisher for Max ideas and design briefs."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import SplitResult, parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

DEFAULT_TIMEOUT_SECONDS = 10.0
GOOGLE_CHAT_TEXT_LIMIT = 4096


class GoogleChatWebhookPublishError(RuntimeError):
    """Raised when a Google Chat webhook publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


GoogleChatWebhookPayload = dict[str, Any]


@dataclass(frozen=True)
class GoogleChatWebhookPublishResult:
    """Summary of a Google Chat webhook publish or dry run."""

    status_code: int | None
    url: str
    dry_run: bool
    payload: GoogleChatWebhookPayload
    response_body: str = ""
    response_headers: dict[str, str] = field(default_factory=dict)
    payload_preview: str = ""


class GoogleChatWebhookPublisher:
    """Build and optionally publish Google Chat incoming-webhook messages."""

    def __init__(
        self,
        webhook_url: str,
        *,
        thread_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not webhook_url.strip():
            raise GoogleChatWebhookPublishError("Google Chat webhook URL is required")
        _validate_webhook_url(webhook_url)
        self.webhook_url = webhook_url
        self.thread_key = _clean_text(thread_key)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        webhook_url: str | None = None,
        thread_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> GoogleChatWebhookPublisher:
        """Create a publisher using explicit values first, then environment variables."""
        resolved_url = webhook_url or os.getenv("GOOGLE_CHAT_WEBHOOK_URL")
        if not resolved_url:
            raise GoogleChatWebhookPublishError(
                "Google Chat webhook URL is required; pass webhook_url or set "
                "GOOGLE_CHAT_WEBHOOK_URL"
            )
        return cls(
            resolved_url,
            thread_key=(
                thread_key
                or os.getenv("GOOGLE_CHAT_THREAD_KEY")
                or os.getenv("GOOGLE_CHAT_WEBHOOK_THREAD_KEY")
            ),
            timeout=timeout,
            client=client,
        )

    @property
    def redacted_url(self) -> str:
        """Return the Google Chat webhook URL with path and query secrets redacted."""
        return redact_google_chat_webhook_url(self.webhook_url)

    def build_payload(self, payload: dict[str, Any]) -> GoogleChatWebhookPayload:
        """Convert a Max idea or design brief payload into Google Chat webhook JSON."""
        if _is_design_brief_payload(payload):
            message = _design_brief_message(payload)
        else:
            message = _idea_message(payload)
        return {
            "text": message["text"],
            "cardsV2": [
                {
                    "cardId": message["metadata"]["source_type"],
                    "card": message["card"],
                }
            ],
            "metadata": message["metadata"],
        }

    def publish(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> GoogleChatWebhookPublishResult:
        """Build a Google Chat payload and optionally post it to the webhook URL."""
        chat_payload = self.build_payload(payload)
        payload_preview = _truncate(chat_payload["text"], 500)
        if dry_run:
            return GoogleChatWebhookPublishResult(
                status_code=None,
                url=self.redacted_url,
                dry_run=True,
                payload=chat_payload,
                payload_preview=payload_preview,
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        request_url = _url_with_thread_key(self.webhook_url, self.thread_key)
        try:
            response = client.post(
                request_url,
                json=chat_payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "max-google-chat-webhook-publisher/1",
                    "X-Max-Published-At": datetime.now(timezone.utc).isoformat(),
                },
                timeout=self.timeout,
            )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise GoogleChatWebhookPublishError(
                f"Google Chat webhook publish failed for {self.redacted_url}: {exc}"
            ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise GoogleChatWebhookPublishError(
                f"Google Chat webhook publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        return GoogleChatWebhookPublishResult(
            status_code=response.status_code,
            url=self.redacted_url,
            dry_run=False,
            payload=chat_payload,
            response_body=_response_body_preview(response),
            response_headers=dict(response.headers),
            payload_preview=payload_preview,
        )


GoogleChatWebhooksPublisher = GoogleChatWebhookPublisher


def publish_google_chat_webhook(
    payload: dict[str, Any],
    *,
    webhook_url: str | None = None,
    thread_key: str | None = None,
    dry_run: bool = True,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    client: httpx.Client | None = None,
) -> GoogleChatWebhookPublishResult:
    """Publish a Max payload to a Google Chat incoming webhook."""
    publisher = GoogleChatWebhookPublisher.from_env(
        webhook_url=webhook_url,
        thread_key=thread_key,
        timeout=timeout,
        client=client,
    )
    return publisher.publish(payload, dry_run=dry_run)


def _idea_message(payload: dict[str, Any]) -> dict[str, Any]:
    source = _dict_value(payload, "source")
    project = _dict_value(payload, "project")
    execution = _dict_value(payload, "execution")
    evidence = _dict_value(payload, "evidence")
    evaluation = _dict_value(payload, "evaluation")
    quality = _dict_value(payload, "quality")

    title = _text(project.get("title"), source.get("idea_id"), "Untitled idea")
    summary = _text(
        project.get("summary"),
        project.get("value_proposition"),
        "No summary provided.",
    )
    insight_ids = _string_list(evidence.get("insight_ids"))
    signal_ids = _string_list(evidence.get("signal_ids"))
    source_idea_ids = _string_list(evidence.get("source_idea_ids"))
    evidence_count = _evidence_count(evidence, insight_ids, signal_ids, source_idea_ids)
    metadata = {
        "publisher": "max.google_chat_webhook",
        "provider": "google_chat",
        "source_type": "idea",
        "idea_id": source.get("idea_id"),
        "status": source.get("status"),
        "domain": source.get("domain"),
        "category": source.get("category"),
        "evidence_count": evidence_count,
        "insight_ids": insight_ids,
        "signal_ids": signal_ids,
        "source_idea_ids": source_idea_ids,
    }
    text = _truncate(
        "\n".join(
            [
                f"[Max] {title}",
                summary,
                f"Recommendation: {_text(evaluation.get('recommendation'), 'Not specified')}",
                f"Validation: {_text(execution.get('validation_plan'), 'Not specified')}",
                f"Evidence count: {evidence_count}",
            ]
        ),
        GOOGLE_CHAT_TEXT_LIMIT,
    )
    card = _card(
        title=title,
        subtitle=_text(source.get("domain"), "Max idea"),
        summary=summary,
        fields=[
            ("Idea ID", source.get("idea_id")),
            ("Status", source.get("status")),
            ("Domain", source.get("domain")),
            ("Category", source.get("category")),
            ("Score", _score_text(evaluation.get("overall_score"))),
            ("Recommendation", evaluation.get("recommendation")),
            ("Quality", _score_text(quality.get("quality_score"))),
            ("Evidence count", evidence_count),
        ],
        validation_plan=execution.get("validation_plan"),
        source_identifiers=_source_identifier_text(
            insight_ids, signal_ids, source_idea_ids
        ),
    )
    return {"text": text, "card": card, "metadata": metadata}


def _design_brief_message(payload: dict[str, Any]) -> dict[str, Any]:
    source = _dict_value(payload, "source")
    brief = _dict_value(payload, "design_brief")
    evidence_refs = _dict_value(payload, "evidence_refs")
    brief_id = _text(brief.get("id"), source.get("id"))
    title = _text(brief.get("title"), brief_id, "Untitled design brief")
    summary = _text(
        brief.get("summary"),
        brief.get("merged_product_concept"),
        "No concept provided.",
    )
    source_idea_ids = _string_list(
        brief.get("source_idea_ids") or evidence_refs.get("source_idea_ids")
    )
    insight_ids = _string_list(evidence_refs.get("insight_ids"))
    signal_ids = _string_list(evidence_refs.get("signal_ids"))
    evidence_count = _evidence_count(evidence_refs, insight_ids, signal_ids, source_idea_ids)
    recommendation = brief.get("recommendation") or brief.get("status_recommendation")
    metadata = {
        "publisher": "max.google_chat_webhook",
        "provider": "google_chat",
        "source_type": "design_brief",
        "design_brief_id": brief_id,
        "lead_idea_id": brief.get("lead_idea_id"),
        "status": brief.get("design_status"),
        "domain": brief.get("domain"),
        "readiness_score": brief.get("readiness_score"),
        "evidence_count": evidence_count,
        "insight_ids": insight_ids,
        "signal_ids": signal_ids,
        "source_idea_ids": source_idea_ids,
    }
    text = _truncate(
        "\n".join(
            [
                f"[Max] {title}",
                summary,
                f"Recommendation: {_text(recommendation, 'Not specified')}",
                f"Validation: {_text(brief.get('validation_plan'), 'Not specified')}",
                f"Evidence count: {evidence_count}",
            ]
        ),
        GOOGLE_CHAT_TEXT_LIMIT,
    )
    card = _card(
        title=title,
        subtitle=_text(brief.get("domain"), "Max design brief"),
        summary=summary,
        fields=[
            ("Brief ID", brief_id),
            ("Status", brief.get("design_status")),
            ("Domain", brief.get("domain")),
            ("Theme", brief.get("theme")),
            ("Readiness", _score_text(brief.get("readiness_score"))),
            ("Lead idea", brief.get("lead_idea_id")),
            ("Recommendation", recommendation),
            ("Evidence count", evidence_count),
        ],
        validation_plan=brief.get("validation_plan"),
        source_identifiers=_source_identifier_text(
            insight_ids, signal_ids, source_idea_ids
        ),
    )
    return {"text": text, "card": card, "metadata": metadata}


def _card(
    *,
    title: str,
    subtitle: str,
    summary: str,
    fields: list[tuple[str, object]],
    validation_plan: object,
    source_identifiers: str,
) -> dict[str, Any]:
    return {
        "header": {
            "title": _truncate(title, 200),
            "subtitle": _truncate(subtitle, 200),
        },
        "sections": [
            {
                "widgets": [
                    {"textParagraph": {"text": _html_text(summary, "No summary provided.")}},
                    *_decorated_text_widgets(fields),
                ]
            },
            {
                "header": "Validation plan",
                "widgets": [
                    {
                        "textParagraph": {
                            "text": _html_text(validation_plan, "Not specified")
                        }
                    }
                ],
            },
            {
                "header": "Source metadata",
                "widgets": [{"textParagraph": {"text": _html_text(source_identifiers)}}],
            },
        ],
    }


def _decorated_text_widgets(fields: list[tuple[str, object]]) -> list[dict[str, Any]]:
    return [
        {
            "decoratedText": {
                "topLabel": label,
                "text": _html_text(value, "Not specified"),
            }
        }
        for label, value in fields
        if _text(value, "")
    ]


def _source_identifier_text(
    insight_ids: list[str],
    signal_ids: list[str],
    source_idea_ids: list[str],
) -> str:
    return "<br>".join(
        [
            f"Insights: {_comma_list(insight_ids)}",
            f"Signals: {_comma_list(signal_ids)}",
            f"Source ideas: {_comma_list(source_idea_ids)}",
        ]
    )


def _is_design_brief_payload(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("design_brief"), dict)


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _string_list(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    return [_text(item, "") for item in items if _text(item, "")]


def _comma_list(items: list[str]) -> str:
    return ", ".join(items) if items else "None"


def _evidence_count(
    evidence: dict[str, Any],
    insight_ids: list[str],
    signal_ids: list[str],
    source_idea_ids: list[str],
) -> int:
    explicit = evidence.get("evidence_count")
    if isinstance(explicit, int):
        return explicit
    return len(set(insight_ids + signal_ids + source_idea_ids))


def _text(*values: object) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _clean_text(value: object) -> str | None:
    text = _text(value)
    return text or None


def _score_text(value: object) -> str:
    if isinstance(value, int | float):
        return f"{value:.1f}"
    return _text(value, "Not specified")


def _html_text(*values: object) -> str:
    return _escape_html(_text(*values))


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _validate_webhook_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise GoogleChatWebhookPublishError(
            "Google Chat webhook URL must be an absolute http(s) URL"
        )


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _url_with_thread_key(url: str, thread_key: str | None) -> str:
    if not thread_key:
        return url
    parts = urlsplit(url)
    query_items = parse_qsl(parts.query, keep_blank_values=True)
    query_items.append(("threadKey", thread_key))
    return urlunsplit(
        SplitResult(
            scheme=parts.scheme,
            netloc=parts.netloc,
            path=parts.path,
            query=urlencode(query_items),
            fragment=parts.fragment,
        )
    )


def redact_google_chat_webhook_url(url: str) -> str:
    """Redact Google Chat webhook path and query secrets while keeping the target recognizable."""
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

"""Telegram Bot API publisher for Max ideas and design briefs."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

DEFAULT_TIMEOUT_SECONDS = 10.0
TELEGRAM_TEXT_LIMIT = 4096
TELEGRAM_API_BASE_URL = "https://api.telegram.org"


class TelegramWebhookPublishError(RuntimeError):
    """Raised when a Telegram webhook publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


TelegramWebhookPayload = dict[str, Any]


@dataclass(frozen=True)
class TelegramWebhookPublishResult:
    """Summary of a Telegram webhook publish or dry run."""

    status_code: int | None
    url: str
    dry_run: bool
    payload: TelegramWebhookPayload
    response_body: str = ""
    response_headers: dict[str, str] = field(default_factory=dict)
    payload_preview: str = ""


class TelegramWebhookPublisher:
    """Build and optionally publish Telegram Bot API sendMessage requests."""

    def __init__(
        self,
        chat_id: str,
        *,
        token: str | None = None,
        parse_mode: str | None = None,
        disable_web_page_preview: bool | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not _text(chat_id):
            raise TelegramWebhookPublishError("Telegram chat_id is required")
        resolved_token = _text(token, os.getenv("TELEGRAM_BOT_TOKEN"))
        if not resolved_token:
            raise TelegramWebhookPublishError(
                "Telegram bot token is required; pass token or set TELEGRAM_BOT_TOKEN"
            )
        self.chat_id = _text(chat_id)
        self.token = resolved_token
        self.parse_mode = _clean_text(parse_mode)
        self.disable_web_page_preview = disable_web_page_preview
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        chat_id: str | None = None,
        token: str | None = None,
        parse_mode: str | None = None,
        disable_web_page_preview: bool | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> TelegramWebhookPublisher:
        """Create a publisher using explicit values first, then environment variables."""
        resolved_chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        if not resolved_chat_id:
            raise TelegramWebhookPublishError(
                "Telegram chat_id is required; pass chat_id or set TELEGRAM_CHAT_ID"
            )
        return cls(
            resolved_chat_id,
            token=token or os.getenv("TELEGRAM_BOT_TOKEN"),
            parse_mode=parse_mode or os.getenv("TELEGRAM_PARSE_MODE"),
            disable_web_page_preview=disable_web_page_preview,
            timeout=timeout,
            client=client,
        )

    @property
    def url(self) -> str:
        """Return the Telegram Bot API sendMessage URL."""
        return f"{TELEGRAM_API_BASE_URL}/bot{self.token}/sendMessage"

    @property
    def redacted_url(self) -> str:
        """Return the Telegram Bot API URL with the bot token redacted."""
        return f"{TELEGRAM_API_BASE_URL}/bot[redacted]/sendMessage"

    def build_payload(self, payload: dict[str, Any]) -> TelegramWebhookPayload:
        """Convert a Max idea or design brief payload into Telegram sendMessage JSON."""
        if _is_design_brief_payload(payload):
            message = _design_brief_message(payload)
        else:
            message = _idea_message(payload)

        telegram_payload: TelegramWebhookPayload = {
            "chat_id": self.chat_id,
            "text": message["text"],
        }
        if self.parse_mode:
            telegram_payload["parse_mode"] = self.parse_mode
        if self.disable_web_page_preview is not None:
            telegram_payload["disable_web_page_preview"] = self.disable_web_page_preview
        telegram_payload["metadata"] = message["metadata"]
        return telegram_payload

    def publish(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> TelegramWebhookPublishResult:
        """Build a Telegram payload and optionally post it to the Bot API."""
        telegram_payload = self.build_payload(payload)
        payload_preview = _truncate(telegram_payload["text"], 500)
        if dry_run:
            return TelegramWebhookPublishResult(
                status_code=None,
                url=self.redacted_url,
                dry_run=True,
                payload=telegram_payload,
                payload_preview=payload_preview,
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(
                self.url,
                json=telegram_payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "max-telegram-webhook-publisher/1",
                    "X-Max-Published-At": datetime.now(timezone.utc).isoformat(),
                },
                timeout=self.timeout,
            )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise TelegramWebhookPublishError(
                f"Telegram webhook publish failed for {self.redacted_url}: {exc}"
            ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise TelegramWebhookPublishError(
                f"Telegram webhook publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        return TelegramWebhookPublishResult(
            status_code=response.status_code,
            url=self.redacted_url,
            dry_run=False,
            payload=telegram_payload,
            response_body=_response_body_preview(response),
            response_headers=dict(response.headers),
            payload_preview=payload_preview,
        )


TelegramWebhooksPublisher = TelegramWebhookPublisher


def publish_telegram_webhook(
    payload: dict[str, Any],
    *,
    chat_id: str | None = None,
    token: str | None = None,
    parse_mode: str | None = None,
    disable_web_page_preview: bool | None = None,
    dry_run: bool = True,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    client: httpx.Client | None = None,
) -> TelegramWebhookPublishResult:
    """Publish a Max payload to Telegram using the Bot API sendMessage endpoint."""
    publisher = TelegramWebhookPublisher.from_env(
        chat_id=chat_id,
        token=token,
        parse_mode=parse_mode,
        disable_web_page_preview=disable_web_page_preview,
        timeout=timeout,
        client=client,
    )
    return publisher.publish(payload, dry_run=dry_run)


def _idea_message(payload: dict[str, Any]) -> dict[str, Any]:
    source = _dict_value(payload, "source")
    project = _dict_value(payload, "project")
    problem = _dict_value(payload, "problem")
    solution = _dict_value(payload, "solution")
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
        "publisher": "max.telegram_webhook",
        "provider": "telegram",
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
    lines = [
        f"[Max] {title}",
        "",
        summary,
        "",
        _field_lines(
            [
                ("Idea ID", source.get("idea_id")),
                ("Status", source.get("status")),
                ("Domain", source.get("domain")),
                ("Category", source.get("category")),
                ("Score", _score_text(evaluation.get("overall_score"))),
                ("Recommendation", evaluation.get("recommendation")),
                ("Quality", _score_text(quality.get("quality_score"))),
                ("Evidence count", evidence_count),
            ]
        ),
        "",
        f"Problem: {_text(problem.get('statement'), 'Not specified')}",
        "",
        f"Solution: {_text(solution.get('approach'), 'Not specified')}",
        "",
        f"MVP Scope:\n{_list_text(execution.get('mvp_scope'))}",
        "",
        f"Validation: {_text(execution.get('validation_plan'), 'Not specified')}",
        "",
        f"Evidence: {_text(evidence.get('rationale'), 'Not specified')}",
        "",
        "Source identifiers:",
        _source_identifier_text(insight_ids, signal_ids, source_idea_ids),
    ]
    return {"text": _truncate("\n".join(lines), TELEGRAM_TEXT_LIMIT), "metadata": metadata}


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
        "publisher": "max.telegram_webhook",
        "provider": "telegram",
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
    lines = [
        f"[Max] {title}",
        "",
        summary,
        "",
        _field_lines(
            [
                ("Brief ID", brief_id),
                ("Status", brief.get("design_status")),
                ("Domain", brief.get("domain")),
                ("Theme", brief.get("theme")),
                ("Readiness", _score_text(brief.get("readiness_score"))),
                ("Lead idea", brief.get("lead_idea_id")),
                ("Recommendation", recommendation),
                ("Evidence count", evidence_count),
            ]
        ),
        "",
        f"Why now: {_text(brief.get('why_this_now'), 'Not specified')}",
        "",
        f"MVP Scope:\n{_list_text(brief.get('mvp_scope'))}",
        "",
        f"Validation: {_text(brief.get('validation_plan'), 'Not specified')}",
        "",
        "Source identifiers:",
        _source_identifier_text(insight_ids, signal_ids, source_idea_ids),
    ]
    markdown = _text(brief.get("markdown"))
    if markdown:
        lines.extend(["", "Rendered brief:", _truncate(markdown, 1200)])
    return {"text": _truncate("\n".join(lines), TELEGRAM_TEXT_LIMIT), "metadata": metadata}


def _field_lines(fields: list[tuple[str, object]]) -> str:
    return "\n".join(
        f"{label}: {_text(value, 'Not specified')}"
        for label, value in fields
        if _text(value, "")
    )


def _is_design_brief_payload(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("design_brief"), dict)


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _list_text(items: object) -> str:
    values = _string_list(items)
    return "\n".join(f"- {value}" for value in values) if values else "- None"


def _source_identifier_text(
    insight_ids: list[str],
    signal_ids: list[str],
    source_idea_ids: list[str],
) -> str:
    return "\n".join(
        [
            f"- Insights: {_comma_list(insight_ids)}",
            f"- Signals: {_comma_list(signal_ids)}",
            f"- Source ideas: {_comma_list(source_idea_ids)}",
        ]
    )


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


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."

"""Slack incoming-webhook publisher for Max ideas and design briefs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx

DEFAULT_TIMEOUT_SECONDS = 10.0


class SlackWebhookPublishError(RuntimeError):
    """Raised when a Slack webhook publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class SlackWebhookPublishResult:
    """Summary of a Slack webhook publish or dry run."""

    status_code: int | None
    url: str
    dry_run: bool
    payload: dict[str, Any]
    response_body: str = ""


class SlackWebhookPublisher:
    """Build and optionally publish Slack Block Kit messages."""

    def __init__(
        self,
        webhook_url: str,
        *,
        channel: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not webhook_url.strip():
            raise SlackWebhookPublishError("Slack webhook URL is required")
        self.webhook_url = webhook_url
        self.channel = _clean_text(channel)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        webhook_url: str | None = None,
        channel: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> SlackWebhookPublisher:
        """Create a publisher using explicit values first, then environment variables."""
        resolved_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        if not resolved_url:
            raise SlackWebhookPublishError(
                "Slack webhook URL is required; pass webhook_url or set SLACK_WEBHOOK_URL"
            )
        return cls(
            resolved_url,
            channel=channel or os.getenv("SLACK_WEBHOOK_CHANNEL"),
            timeout=timeout,
            client=client,
        )

    @property
    def redacted_url(self) -> str:
        """Return the Slack webhook URL with secrets redacted."""
        return redact_slack_webhook_url(self.webhook_url)

    def build_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Convert a Max idea or design brief payload into Slack Block Kit JSON."""
        if _is_design_brief_payload(payload):
            message = _design_brief_message(payload)
        else:
            message = _idea_message(payload)

        slack_payload: dict[str, Any] = {
            "text": message["text"],
            "blocks": message["blocks"],
            "metadata": {
                "event_type": "max_publication",
                "event_payload": message["metadata"],
            },
        }
        if self.channel:
            slack_payload["channel"] = self.channel
        return slack_payload

    def publish(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> SlackWebhookPublishResult:
        """Build a Slack payload and optionally post it to the webhook URL."""
        slack_payload = self.build_payload(payload)
        if dry_run:
            return SlackWebhookPublishResult(
                status_code=None,
                url=self.redacted_url,
                dry_run=True,
                payload=slack_payload,
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(
                self.webhook_url,
                json=slack_payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "max-slack-webhook-publisher/1",
                    "X-Max-Published-At": datetime.now(timezone.utc).isoformat(),
                },
                timeout=self.timeout,
            )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise SlackWebhookPublishError(
                f"Slack webhook publish failed for {self.redacted_url}: {exc}"
            ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise SlackWebhookPublishError(
                f"Slack webhook publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        return SlackWebhookPublishResult(
            status_code=response.status_code,
            url=self.redacted_url,
            dry_run=False,
            payload=slack_payload,
            response_body=_response_body_preview(response),
        )


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
    summary = _text(project.get("summary"), project.get("value_proposition"), "")
    metadata = {
        "publisher": "max.slack_webhook",
        "source_type": "idea",
        "idea_id": source.get("idea_id"),
        "status": source.get("status"),
        "domain": source.get("domain"),
        "category": source.get("category"),
    }
    blocks = [
        _header_block(title),
        _section_block(summary or "No summary provided."),
        _fields_block(
            [
                ("Idea ID", source.get("idea_id")),
                ("Status", source.get("status")),
                ("Domain", source.get("domain")),
                ("Category", source.get("category")),
                ("Score", _score_text(evaluation.get("overall_score"))),
                ("Recommendation", evaluation.get("recommendation")),
            ]
        ),
        _section_block(f"*Problem*\n{_text(problem.get('statement'), 'Not specified')}"),
        _section_block(f"*Solution*\n{_text(solution.get('approach'), 'Not specified')}"),
        _section_block(
            "*MVP Scope*\n" + _list_text(execution.get("mvp_scope"))
        ),
        _section_block(
            "*Validation*\n" + _text(execution.get("validation_plan"), "Not specified")
        ),
        _context_block(
            [
                f"Evidence: {_text(evidence.get('rationale'), 'Not specified')}",
                f"Quality: {_score_text(quality.get('quality_score'))}",
            ]
        ),
    ]
    return {"text": f"[Max] {title}", "blocks": blocks, "metadata": metadata}


def _design_brief_message(payload: dict[str, Any]) -> dict[str, Any]:
    source = _dict_value(payload, "source")
    brief = _dict_value(payload, "design_brief")
    title = _text(brief.get("title"), source.get("id"), "Untitled design brief")
    metadata = {
        "publisher": "max.slack_webhook",
        "source_type": "design_brief",
        "design_brief_id": brief.get("id") or source.get("id"),
        "lead_idea_id": brief.get("lead_idea_id"),
        "status": brief.get("design_status"),
        "domain": brief.get("domain"),
    }
    blocks = [
        _header_block(title),
        _section_block(_text(brief.get("merged_product_concept"), "No concept provided.")),
        _fields_block(
            [
                ("Brief ID", brief.get("id") or source.get("id")),
                ("Status", brief.get("design_status")),
                ("Domain", brief.get("domain")),
                ("Theme", brief.get("theme")),
                ("Readiness", _score_text(brief.get("readiness_score"))),
                ("Lead idea", brief.get("lead_idea_id")),
            ]
        ),
        _section_block(f"*Why now*\n{_text(brief.get('why_this_now'), 'Not specified')}"),
        _section_block("*MVP Scope*\n" + _list_text(brief.get("mvp_scope"))),
        _section_block("*Validation*\n" + _text(brief.get("validation_plan"), "Not specified")),
        _context_block([f"Source ideas: {', '.join(brief.get('source_idea_ids') or []) or 'None'}"]),
    ]
    return {"text": f"[Max] {title}", "blocks": blocks, "metadata": metadata}


def _header_block(text: object) -> dict[str, Any]:
    return {
        "type": "header",
        "text": {"type": "plain_text", "text": _truncate(_text(text, "Untitled"), 150)},
    }


def _section_block(markdown: object) -> dict[str, Any]:
    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": _truncate(_text(markdown, "Not specified"), 3000)},
    }


def _fields_block(fields: list[tuple[str, object]]) -> dict[str, Any]:
    return {
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": _truncate(f"*{label}*\n{_text(value, 'Not specified')}", 2000)}
            for label, value in fields
        ],
    }


def _context_block(items: list[object]) -> dict[str, Any]:
    return {
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": _truncate(_text(item, "Not specified"), 2000)}
            for item in items
            if _text(item, "")
        ],
    }


def _is_design_brief_payload(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("design_brief"), dict)


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _list_text(items: object) -> str:
    if not isinstance(items, list) or not items:
        return "- None"
    return "\n".join(f"- {_text(item, '')}" for item in items if _text(item, "")) or "- None"


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


def redact_slack_webhook_url(url: str) -> str:
    """Redact Slack webhook path secrets while keeping the target recognizable."""
    parts = urlsplit(url)
    path_parts = parts.path.split("/")
    if len(path_parts) > 1:
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

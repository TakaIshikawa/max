"""Cisco Webex incoming-webhook publisher for Max ideas and design briefs."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx

DEFAULT_TIMEOUT_SECONDS = 10.0
WEBEX_MARKDOWN_LIMIT = 7439


class WebexWebhookPublishError(RuntimeError):
    """Raised when a Webex webhook publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


WebexWebhookPayload = dict[str, Any]


@dataclass(frozen=True)
class WebexWebhookPublishResult:
    """Summary of a Webex webhook publish or dry run."""

    status_code: int | None
    url: str
    dry_run: bool
    payload: WebexWebhookPayload
    response_body: str = ""
    response_headers: dict[str, str] = field(default_factory=dict)
    payload_preview: str = ""


class WebexWebhookPublisher:
    """Build and optionally publish Webex incoming-webhook markdown messages."""

    def __init__(
        self,
        webhook_url: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not webhook_url.strip():
            raise WebexWebhookPublishError("Webex webhook URL is required")
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
    ) -> WebexWebhookPublisher:
        """Create a publisher using explicit values first, then environment variables."""
        resolved_url = webhook_url or os.getenv("MAX_WEBEX_WEBHOOK_URL")
        if not resolved_url:
            raise WebexWebhookPublishError(
                "Webex webhook URL is required; pass webhook_url or set "
                "MAX_WEBEX_WEBHOOK_URL"
            )
        return cls(resolved_url, timeout=timeout, client=client)

    @property
    def redacted_url(self) -> str:
        """Return the Webex webhook URL with path and query secrets redacted."""
        return redact_webex_webhook_url(self.webhook_url)

    def build_payload(self, payload: dict[str, Any]) -> WebexWebhookPayload:
        """Convert a Max idea or design brief payload into Webex webhook JSON."""
        if _is_design_brief_payload(payload):
            message = _design_brief_message(payload)
        else:
            message = _idea_message(payload)
        return {
            "markdown": message["markdown"],
            "metadata": message["metadata"],
        }

    def publish(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> WebexWebhookPublishResult:
        """Build a Webex payload and optionally post it to the webhook URL."""
        webex_payload = self.build_payload(payload)
        payload_preview = _truncate(webex_payload["markdown"], 500)
        if dry_run:
            return WebexWebhookPublishResult(
                status_code=None,
                url=self.redacted_url,
                dry_run=True,
                payload=webex_payload,
                payload_preview=payload_preview,
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(
                self.webhook_url,
                json=webex_payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "max-webex-webhook-publisher/1",
                    "X-Max-Published-At": datetime.now(timezone.utc).isoformat(),
                },
                timeout=self.timeout,
            )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise WebexWebhookPublishError(
                f"Webex webhook publish failed for {self.redacted_url}: {exc}"
            ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise WebexWebhookPublishError(
                f"Webex webhook publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        return WebexWebhookPublishResult(
            status_code=response.status_code,
            url=self.redacted_url,
            dry_run=False,
            payload=webex_payload,
            response_body=_response_body_preview(response),
            response_headers=dict(response.headers),
            payload_preview=payload_preview,
        )


WebexWebhooksPublisher = WebexWebhookPublisher


def publish_webex_webhook(
    payload: dict[str, Any],
    *,
    webhook_url: str | None = None,
    dry_run: bool = True,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    client: httpx.Client | None = None,
) -> WebexWebhookPublishResult:
    """Publish a Max payload to a Webex incoming webhook."""
    publisher = WebexWebhookPublisher.from_env(
        webhook_url=webhook_url,
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
        "publisher": "max.webex_webhook",
        "provider": "webex",
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
        f"### [Max] {title}",
        "",
        summary,
        "",
        _table(
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
        f"**Problem**\n{_text(problem.get('statement'), 'Not specified')}",
        "",
        f"**Solution**\n{_text(solution.get('approach'), 'Not specified')}",
        "",
        f"**MVP Scope**\n{_list_text(execution.get('mvp_scope'))}",
        "",
        f"**Validation**\n{_text(execution.get('validation_plan'), 'Not specified')}",
        "",
        f"**Evidence**\n{_text(evidence.get('rationale'), 'Not specified')}",
        "",
        "**Source identifiers**\n"
        f"{_source_identifier_text(insight_ids, signal_ids, source_idea_ids)}",
    ]
    return {"markdown": _truncate("\n".join(lines), WEBEX_MARKDOWN_LIMIT), "metadata": metadata}


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
    metadata = {
        "publisher": "max.webex_webhook",
        "provider": "webex",
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
        f"### [Max] {title}",
        "",
        summary,
        "",
        _table(
            [
                ("Brief ID", brief_id),
                ("Status", brief.get("design_status")),
                ("Domain", brief.get("domain")),
                ("Theme", brief.get("theme")),
                ("Readiness", _score_text(brief.get("readiness_score"))),
                ("Lead idea", brief.get("lead_idea_id")),
                (
                    "Recommendation",
                    brief.get("recommendation") or brief.get("status_recommendation"),
                ),
                ("Evidence count", evidence_count),
            ]
        ),
        "",
        f"**Why now**\n{_text(brief.get('why_this_now'), 'Not specified')}",
        "",
        f"**MVP Scope**\n{_list_text(brief.get('mvp_scope'))}",
        "",
        f"**Validation**\n{_text(brief.get('validation_plan'), 'Not specified')}",
        "",
        "**Source identifiers**\n"
        f"{_source_identifier_text(insight_ids, signal_ids, source_idea_ids)}",
    ]
    markdown = _text(brief.get("markdown"))
    if markdown:
        lines.extend(["", "**Rendered brief**", _truncate(markdown, 3000)])
    return {"markdown": _truncate("\n".join(lines), WEBEX_MARKDOWN_LIMIT), "metadata": metadata}


def _table(fields: list[tuple[str, object]]) -> str:
    rows = [
        f"| {_escape_table(label)} | {_escape_table(_text(value, 'Not specified'))} |"
        for label, value in fields
        if _text(value, "")
    ]
    if not rows:
        return ""
    return "| Field | Value |\n| --- | --- |\n" + "\n".join(rows)


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


def _score_text(value: object) -> str:
    if isinstance(value, int | float):
        return f"{value:.1f}"
    return _text(value, "Not specified")


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _validate_webhook_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise WebexWebhookPublishError(
            "Webex webhook URL must be an absolute http(s) URL"
        )


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def redact_webex_webhook_url(url: str) -> str:
    """Redact Webex webhook path secrets while keeping the target recognizable."""
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

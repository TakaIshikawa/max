"""Mattermost incoming-webhook publisher for Max ideas and design briefs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx

DEFAULT_TIMEOUT_SECONDS = 10.0


class MattermostWebhookPublishError(RuntimeError):
    """Raised when a Mattermost webhook publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


MattermostWebhookPayload = dict[str, Any]


@dataclass(frozen=True)
class MattermostWebhookPublishResult:
    """Summary of a Mattermost webhook publish or dry run."""

    status_code: int | None
    url: str
    dry_run: bool
    payload: MattermostWebhookPayload
    response_body: str = ""


class MattermostWebhookPublisher:
    """Build and optionally publish Mattermost incoming-webhook messages."""

    def __init__(
        self,
        webhook_url: str,
        *,
        channel: str | None = None,
        username: str | None = None,
        icon_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not webhook_url.strip():
            raise MattermostWebhookPublishError("Mattermost webhook URL is required")
        self.webhook_url = webhook_url
        self.channel = _clean_text(channel)
        self.username = _clean_text(username)
        self.icon_url = _clean_text(icon_url)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        webhook_url: str | None = None,
        channel: str | None = None,
        username: str | None = None,
        icon_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> MattermostWebhookPublisher:
        """Create a publisher using explicit values first, then environment variables."""
        resolved_url = webhook_url or os.getenv("MAX_MATTERMOST_WEBHOOK_URL")
        if not resolved_url:
            raise MattermostWebhookPublishError(
                "Mattermost webhook URL is required; pass webhook_url or set "
                "MAX_MATTERMOST_WEBHOOK_URL"
            )
        return cls(
            resolved_url,
            channel=channel or os.getenv("MAX_MATTERMOST_CHANNEL"),
            username=username or os.getenv("MAX_MATTERMOST_USERNAME"),
            icon_url=icon_url or os.getenv("MAX_MATTERMOST_ICON_URL"),
            timeout=timeout,
            client=client,
        )

    @property
    def redacted_url(self) -> str:
        """Return the Mattermost webhook URL with path and query secrets redacted."""
        return redact_mattermost_webhook_url(self.webhook_url)

    def build_payload(self, payload: dict[str, Any]) -> MattermostWebhookPayload:
        """Convert a Max idea or design brief payload into Mattermost webhook JSON."""
        if _is_design_brief_payload(payload):
            message = _design_brief_message(payload)
        else:
            message = _idea_message(payload)

        mattermost_payload: MattermostWebhookPayload = {
            "text": message["text"],
            "props": {
                "max": message["metadata"],
            },
        }
        if self.channel:
            mattermost_payload["channel"] = self.channel
        if self.username:
            mattermost_payload["username"] = self.username
        if self.icon_url:
            mattermost_payload["icon_url"] = self.icon_url
        return mattermost_payload

    def publish(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> MattermostWebhookPublishResult:
        """Build a Mattermost payload and optionally post it to the webhook URL."""
        mattermost_payload = self.build_payload(payload)
        if dry_run:
            return MattermostWebhookPublishResult(
                status_code=None,
                url=self.redacted_url,
                dry_run=True,
                payload=mattermost_payload,
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(
                self.webhook_url,
                json=mattermost_payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "max-mattermost-webhook-publisher/1",
                    "X-Max-Published-At": datetime.now(timezone.utc).isoformat(),
                },
                timeout=self.timeout,
            )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise MattermostWebhookPublishError(
                f"Mattermost webhook publish failed for {self.redacted_url}: {exc}"
            ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise MattermostWebhookPublishError(
                f"Mattermost webhook publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        return MattermostWebhookPublishResult(
            status_code=response.status_code,
            url=self.redacted_url,
            dry_run=False,
            payload=mattermost_payload,
            response_body=_response_body_preview(response),
        )


MattermostWebhooksPublisher = MattermostWebhookPublisher


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
    metadata = {
        "publisher": "max.mattermost_webhook",
        "provider": "mattermost",
        "source_type": "idea",
        "idea_id": source.get("idea_id"),
        "status": source.get("status"),
        "domain": source.get("domain"),
        "category": source.get("category"),
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
    ]
    return {"text": _truncate("\n".join(lines), 16000), "metadata": metadata}


def _design_brief_message(payload: dict[str, Any]) -> dict[str, Any]:
    source = _dict_value(payload, "source")
    brief = _dict_value(payload, "design_brief")
    brief_id = _text(brief.get("id"), source.get("id"))
    title = _text(brief.get("title"), brief_id, "Untitled design brief")
    summary = _text(
        brief.get("summary"),
        brief.get("merged_product_concept"),
        "No concept provided.",
    )
    metadata = {
        "publisher": "max.mattermost_webhook",
        "provider": "mattermost",
        "source_type": "design_brief",
        "design_brief_id": brief_id,
        "lead_idea_id": brief.get("lead_idea_id"),
        "status": brief.get("design_status"),
        "domain": brief.get("domain"),
        "readiness_score": brief.get("readiness_score"),
        "source_idea_ids": brief.get("source_idea_ids") or [],
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
                ("Buyer", brief.get("buyer")),
                ("User", brief.get("specific_user")),
                ("Workflow", brief.get("workflow_context")),
            ]
        ),
        "",
        f"**Why now**\n{_text(brief.get('why_this_now'), 'Not specified')}",
        "",
        f"**MVP Scope**\n{_list_text(brief.get('mvp_scope'))}",
        "",
        f"**Validation**\n{_text(brief.get('validation_plan'), 'Not specified')}",
        "",
        f"**Source ideas**\n{_comma_list(brief.get('source_idea_ids'))}",
    ]
    markdown = _text(brief.get("markdown"))
    if markdown:
        lines.extend(["", "**Rendered brief**", _truncate(markdown, 3000)])
    return {"text": _truncate("\n".join(lines), 16000), "metadata": metadata}


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
    if not isinstance(items, list) or not items:
        return "- None"
    return "\n".join(f"- {_text(item, '')}" for item in items if _text(item, "")) or "- None"


def _comma_list(items: object) -> str:
    if not isinstance(items, list) or not items:
        return "None"
    values = [_text(item, "") for item in items if _text(item, "")]
    return ", ".join(values) if values else "None"


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


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def redact_mattermost_webhook_url(url: str) -> str:
    """Redact Mattermost webhook path secrets while keeping the target recognizable."""
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

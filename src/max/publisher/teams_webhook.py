"""Microsoft Teams incoming-webhook publisher for Max ideas and design briefs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx

DEFAULT_TIMEOUT_SECONDS = 10.0


class TeamsWebhookPublishError(RuntimeError):
    """Raised when a Teams webhook publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class TeamsWebhookPublishResult:
    """Summary of a Teams webhook publish or dry run."""

    status_code: int | None
    url: str
    dry_run: bool
    payload: dict[str, Any]
    response_body: str = ""


class TeamsWebhookPublisher:
    """Build and optionally publish Teams MessageCard payloads."""

    def __init__(
        self,
        webhook_url: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not webhook_url.strip():
            raise TeamsWebhookPublishError("Teams webhook URL is required")
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
    ) -> TeamsWebhookPublisher:
        """Create a publisher using explicit values first, then environment variables."""
        resolved_url = webhook_url or os.getenv("TEAMS_WEBHOOK_URL")
        if not resolved_url:
            raise TeamsWebhookPublishError(
                "Teams webhook URL is required; pass webhook_url or set TEAMS_WEBHOOK_URL"
            )
        return cls(resolved_url, timeout=timeout, client=client)

    @property
    def redacted_url(self) -> str:
        """Return the Teams webhook URL with path credentials and query values redacted."""
        return _redact_teams_url(self.webhook_url)

    def build_payload(
        self,
        payload: dict[str, Any],
        *,
        title: str | None = None,
        include_evidence: bool = True,
    ) -> dict[str, Any]:
        """Convert a Max idea or design brief payload into a Teams MessageCard JSON document."""
        if _is_design_brief_payload(payload):
            return _design_brief_message_card(payload, title=title)
        return _idea_message_card(payload, title=title, include_evidence=include_evidence)

    def publish(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = True,
        title: str | None = None,
        include_evidence: bool = True,
    ) -> TeamsWebhookPublishResult:
        """Build a Teams payload and optionally post it to the webhook URL."""
        teams_payload = self.build_payload(
            payload,
            title=title,
            include_evidence=include_evidence,
        )
        if dry_run:
            return TeamsWebhookPublishResult(
                status_code=None,
                url=self.redacted_url,
                dry_run=True,
                payload=teams_payload,
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(
                self.webhook_url,
                json=teams_payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "max-teams-webhook-publisher/1",
                    "X-Max-Published-At": datetime.now(timezone.utc).isoformat(),
                },
                timeout=self.timeout,
            )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise TeamsWebhookPublishError(
                f"Teams webhook publish failed for {self.redacted_url}: {exc}"
            ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise TeamsWebhookPublishError(
                f"Teams webhook publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        return TeamsWebhookPublishResult(
            status_code=response.status_code,
            url=self.redacted_url,
            dry_run=False,
            payload=teams_payload,
            response_body=_response_body_preview(response),
        )


def _idea_message_card(
    payload: dict[str, Any],
    *,
    title: str | None,
    include_evidence: bool,
) -> dict[str, Any]:
    source = _dict_value(payload, "source")
    project = _dict_value(payload, "project")
    evaluation = _dict_value(payload, "evaluation")
    evidence = _dict_value(payload, "evidence")
    quality = _dict_value(payload, "quality")

    idea_id = source.get("idea_id")
    rendered_title = _text(title, project.get("title"), idea_id, "Untitled idea")
    one_liner = _text(
        project.get("summary"),
        project.get("value_proposition"),
        "No summary provided.",
    )
    facts = _facts(
        [
            ("Idea ID", idea_id),
            ("Status", source.get("status")),
            ("Domain", source.get("domain")),
            ("Category", source.get("category")),
            ("Score", _score_text(evaluation.get("overall_score"))),
            ("Recommendation", evaluation.get("recommendation")),
            ("Quality", _score_text(quality.get("quality_score"))),
        ]
    )
    sections = [
        {
            "activityTitle": rendered_title,
            "activitySubtitle": _text(source.get("domain"), "Max idea"),
            "text": one_liner,
            "facts": facts,
            "markdown": True,
        },
        {
            "title": "Metadata",
            "facts": _facts(
                [
                    ("Publisher", "max.teams_webhook"),
                    ("Provider", "teams"),
                    ("Schema", payload.get("schema_version")),
                    ("Kind", payload.get("kind")),
                    ("Created", source.get("created_at")),
                    ("Updated", source.get("updated_at")),
                ]
            ),
            "markdown": True,
        },
    ]
    if include_evidence:
        sections.append(
            {
                "title": "Evidence",
                "text": _text(evidence.get("rationale"), "No evidence rationale provided."),
                "facts": _facts(
                    [
                        ("Insights", _uri_list("insights", evidence.get("insight_ids"))),
                        ("Signals", _uri_list("signals", evidence.get("signal_ids"))),
                        ("Source ideas", _uri_list("ideas", evidence.get("source_idea_ids"))),
                    ]
                ),
                "markdown": True,
            }
        )

    card: dict[str, Any] = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": "2F80ED",
        "summary": f"[Max] {rendered_title}",
        "title": f"[Max] {rendered_title}",
        "text": one_liner,
        "sections": sections,
        "potentialAction": [
            {
                "@type": "OpenUri",
                "name": "Open idea",
                "targets": [{"os": "default", "uri": f"ideas://{_text(idea_id, '')}"}],
            }
        ],
        "metadata": {
            "publisher": "max.teams_webhook",
            "provider": "teams",
            "source_type": "idea",
            "idea_id": idea_id,
            "status": source.get("status"),
            "domain": source.get("domain"),
        },
    }
    return card


def _design_brief_message_card(
    payload: dict[str, Any],
    *,
    title: str | None,
) -> dict[str, Any]:
    source = _dict_value(payload, "source")
    brief = _dict_value(payload, "design_brief")

    brief_id = _text(brief.get("id"), source.get("id"))
    rendered_title = _text(title, brief.get("title"), brief_id, "Untitled design brief")
    summary = _text(
        brief.get("summary"),
        brief.get("merged_product_concept"),
        "No concept provided.",
    )
    sections = [
        {
            "activityTitle": rendered_title,
            "activitySubtitle": _text(brief.get("domain"), "Max design brief"),
            "text": summary,
            "facts": _facts(
                [
                    ("Brief ID", brief_id),
                    ("Status", brief.get("design_status")),
                    ("Domain", brief.get("domain")),
                    ("Theme", brief.get("theme")),
                    ("Readiness", _score_text(brief.get("readiness_score"))),
                    ("Lead idea", brief.get("lead_idea_id")),
                ]
            ),
            "markdown": True,
        },
        {
            "title": "Plan",
            "text": _text(brief.get("why_this_now"), "Not specified"),
            "facts": _facts(
                [
                    ("MVP Scope", _list_text(brief.get("mvp_scope"))),
                    ("Validation", brief.get("validation_plan")),
                    ("Source ideas", _comma_list(brief.get("source_idea_ids"))),
                ]
            ),
            "markdown": True,
        },
        {
            "title": "Metadata",
            "facts": _facts(
                [
                    ("Publisher", "max.teams_webhook"),
                    ("Provider", "teams"),
                    ("Schema", source.get("schema_version")),
                    ("Generated", source.get("generated_at")),
                ]
            ),
            "markdown": True,
        },
    ]
    markdown = _text(brief.get("markdown"))
    if markdown:
        sections.append(
            {
                "title": "Rendered brief",
                "text": _truncate(markdown, 3000),
                "markdown": True,
            }
        )

    return {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": "27AE60",
        "summary": f"[Max] {rendered_title}",
        "title": f"[Max] {rendered_title}",
        "text": summary,
        "sections": sections,
        "potentialAction": [
            {
                "@type": "OpenUri",
                "name": "Open design brief",
                "targets": [{"os": "default", "uri": f"design-briefs://{brief_id}"}],
            }
        ],
        "metadata": {
            "publisher": "max.teams_webhook",
            "provider": "teams",
            "source_type": "design_brief",
            "design_brief_id": brief_id,
            "lead_idea_id": brief.get("lead_idea_id"),
            "status": brief.get("design_status"),
            "domain": brief.get("domain"),
        },
    }


def _facts(facts: list[tuple[str, object]]) -> list[dict[str, str]]:
    return [
        {
            "name": _truncate(_text(name, "Not specified"), 80),
            "value": _truncate(_text(value, "Not specified"), 500),
        }
        for name, value in facts
        if _text(value, "")
    ]


def _is_design_brief_payload(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("design_brief"), dict)


def _uri_list(scheme: str, items: object) -> str:
    if not isinstance(items, list) or not items:
        return "None"
    values = [f"{scheme}://{_text(item, '')}" for item in items if _text(item, "")]
    return ", ".join(values) if values else "None"


def _comma_list(items: object) -> str:
    if not isinstance(items, list) or not items:
        return "None"
    values = [_text(item, "") for item in items if _text(item, "")]
    return ", ".join(values) if values else "None"


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _list_text(items: object) -> str:
    if not isinstance(items, list) or not items:
        return "None"
    values = [_text(item, "") for item in items if _text(item, "")]
    return "\n".join(f"- {value}" for value in values) if values else "None"


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


def _redact_teams_url(url: str) -> str:
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


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."

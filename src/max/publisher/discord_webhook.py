"""Discord webhook publisher for Max ideas and design briefs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx

DEFAULT_TIMEOUT_SECONDS = 10.0
DISCORD_EMBED_LIMIT = 6000


class DiscordWebhookPublishError(RuntimeError):
    """Raised when a Discord webhook publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class DiscordWebhookPublishResult:
    """Summary of a Discord webhook publish or dry run."""

    status_code: int | None
    url: str
    dry_run: bool
    payload: dict[str, Any]
    response_body: str = ""


class DiscordWebhookPublisher:
    """Build and optionally publish Discord webhook messages."""

    def __init__(
        self,
        webhook_url: str,
        *,
        username: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not webhook_url.strip():
            raise DiscordWebhookPublishError("Discord webhook URL is required")
        self.webhook_url = webhook_url
        self.username = _clean_text(username)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        webhook_url: str | None = None,
        username: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> DiscordWebhookPublisher:
        """Create a publisher using explicit values first, then environment variables."""
        resolved_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
        if not resolved_url:
            raise DiscordWebhookPublishError(
                "Discord webhook URL is required; pass webhook_url or set DISCORD_WEBHOOK_URL"
            )
        return cls(
            resolved_url,
            username=username or os.getenv("DISCORD_WEBHOOK_USERNAME"),
            timeout=timeout,
            client=client,
        )

    @property
    def redacted_url(self) -> str:
        """Return the Discord webhook URL with credentials and query values redacted."""
        return _redact_discord_url(self.webhook_url)

    def build_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Convert a Max idea or design brief payload into Discord webhook JSON."""
        if _is_design_brief_payload(payload):
            message = _design_brief_message(payload)
        else:
            message = _idea_message(payload)

        discord_payload: dict[str, Any] = {
            "content": message["content"],
            "embeds": [message["embed"]],
        }
        if self.username:
            discord_payload["username"] = self.username
        return discord_payload

    def publish(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> DiscordWebhookPublishResult:
        """Build a Discord payload and optionally post it to the webhook URL."""
        discord_payload = self.build_payload(payload)
        if dry_run:
            return DiscordWebhookPublishResult(
                status_code=None,
                url=self.redacted_url,
                dry_run=True,
                payload=discord_payload,
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(
                self.webhook_url,
                json=discord_payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "max-discord-webhook-publisher/1",
                    "X-Max-Published-At": datetime.now(timezone.utc).isoformat(),
                },
                timeout=self.timeout,
            )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise DiscordWebhookPublishError(
                f"Discord webhook publish failed for {self.redacted_url}: {exc}"
            ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise DiscordWebhookPublishError(
                f"Discord webhook publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        return DiscordWebhookPublishResult(
            status_code=response.status_code,
            url=self.redacted_url,
            dry_run=False,
            payload=discord_payload,
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
    summary = _text(project.get("summary"), project.get("value_proposition"), "No summary provided.")
    embed = {
        "title": _truncate(title, 256),
        "description": _truncate(summary, 4096),
        "color": 0x2F80ED,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fields": _fields(
            [
                ("Idea ID", source.get("idea_id"), True),
                ("Status", source.get("status"), True),
                ("Domain", source.get("domain"), True),
                ("Category", source.get("category"), True),
                ("Score", _score_text(evaluation.get("overall_score")), True),
                ("Recommendation", evaluation.get("recommendation"), True),
                ("Problem", problem.get("statement"), False),
                ("Solution", solution.get("approach"), False),
                ("MVP Scope", _list_text(execution.get("mvp_scope")), False),
                ("Validation", execution.get("validation_plan"), False),
                ("Evidence", evidence.get("rationale"), False),
                ("Quality", _score_text(quality.get("quality_score")), True),
            ]
        ),
        "footer": {"text": "max.discord_webhook | idea"},
    }
    return {"content": f"[Max] {title}", "embed": _fit_embed(embed)}


def _design_brief_message(payload: dict[str, Any]) -> dict[str, Any]:
    source = _dict_value(payload, "source")
    brief = _dict_value(payload, "design_brief")
    title = _text(brief.get("title"), source.get("id"), "Untitled design brief")
    embed = {
        "title": _truncate(title, 256),
        "description": _truncate(
            _text(brief.get("merged_product_concept"), "No concept provided."),
            4096,
        ),
        "color": 0x27AE60,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fields": _fields(
            [
                ("Brief ID", brief.get("id") or source.get("id"), True),
                ("Status", brief.get("design_status"), True),
                ("Domain", brief.get("domain"), True),
                ("Theme", brief.get("theme"), True),
                ("Readiness", _score_text(brief.get("readiness_score")), True),
                ("Lead idea", brief.get("lead_idea_id"), True),
                ("Why now", brief.get("why_this_now"), False),
                ("MVP Scope", _list_text(brief.get("mvp_scope")), False),
                ("Validation", brief.get("validation_plan"), False),
                ("Source ideas", ", ".join(brief.get("source_idea_ids") or []) or "None", False),
            ]
        ),
        "footer": {"text": "max.discord_webhook | design_brief"},
    }
    return {"content": f"[Max] {title}", "embed": _fit_embed(embed)}


def _fields(fields: list[tuple[str, object, bool]]) -> list[dict[str, Any]]:
    return [
        {
            "name": _truncate(_text(label, "Not specified"), 256),
            "value": _truncate(_text(value, "Not specified"), 1024),
            "inline": inline,
        }
        for label, value, inline in fields
        if _text(value, "")
    ][:25]


def _fit_embed(embed: dict[str, Any]) -> dict[str, Any]:
    """Keep generated embeds inside Discord's aggregate character budget."""
    while _embed_length(embed) > DISCORD_EMBED_LIMIT and embed.get("fields"):
        fields = embed["fields"]
        longest = max(range(len(fields)), key=lambda index: len(fields[index]["value"]))
        value = fields[longest]["value"]
        fields[longest]["value"] = _truncate(value, max(80, len(value) - 250))
    return embed


def _embed_length(embed: dict[str, Any]) -> int:
    total = len(embed.get("title", "")) + len(embed.get("description", ""))
    total += len((embed.get("footer") or {}).get("text", ""))
    total += sum(len(field.get("name", "")) + len(field.get("value", "")) for field in embed.get("fields", []))
    return total


def _is_design_brief_payload(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("design_brief"), dict)


def _redact_discord_url(url: str) -> str:
    parts = urlsplit(url)
    path_parts = parts.path.split("/")
    if len(path_parts) >= 5 and path_parts[-3:-1] == ["webhooks", path_parts[-2]]:
        path_parts[-1] = "[redacted]"
    elif path_parts:
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

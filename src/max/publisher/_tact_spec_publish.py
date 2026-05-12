"""Shared helpers for lightweight TactSpec outbound publishers."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx


DEFAULT_TIMEOUT_SECONDS = 10.0


def validate_tact_spec(tact_spec: dict[str, Any], *, label: str) -> None:
    if not isinstance(tact_spec, dict):
        raise ValueError(f"{label} publishing requires a TactSpec dict")
    if not optional_text(tact_spec.get("schema_version")):
        raise ValueError(f"{label} publishing requires schema_version in the TactSpec payload")
    project = dict_value(tact_spec, "project")
    source = dict_value(tact_spec, "source")
    if not optional_text(project.get("title")) and not (
        optional_text(source.get("idea_id")) or optional_text(source.get("design_brief_id"))
    ):
        raise ValueError(f"{label} publishing requires project.title or a source id")


def dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def required_text(value: object, message: str) -> str:
    text = optional_text(value)
    if not text:
        raise ValueError(message)
    return text


def required_url(value: object, message: str) -> str:
    url = required_text(value, message).rstrip("/")
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError(message)
    return url


def source_id(source: dict[str, Any]) -> str | None:
    return optional_text(source.get("design_brief_id")) or optional_text(source.get("idea_id"))


def title(tact_spec: dict[str, Any], *, fallback: str = "Generated TactSpec") -> str:
    project = dict_value(tact_spec, "project")
    source = dict_value(tact_spec, "source")
    return optional_text(project.get("title")) or source_id(source) or fallback


def metadata(tact_spec: dict[str, Any], *, publisher: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    source = dict_value(tact_spec, "source")
    data = {
        "publisher": publisher,
        "source_system": source.get("system", "max"),
        "source_type": source.get("type") or "idea",
        "source_id": source_id(source),
        "idea_id": source.get("idea_id"),
        "design_brief_id": source.get("design_brief_id"),
        "schema_version": tact_spec.get("schema_version"),
        "kind": tact_spec.get("kind"),
    }
    if extra:
        data.update(extra)
    return data


def markdown_summary(tact_spec: dict[str, Any], metadata: dict[str, Any]) -> str:
    project = dict_value(tact_spec, "project")
    source = dict_value(tact_spec, "source")
    evidence = dict_value(tact_spec, "evidence")
    quality = dict_value(tact_spec, "quality")
    evaluation = dict_value(tact_spec, "evaluation")
    execution = dict_value(tact_spec, "execution")
    lines = [
        f"# {title(tact_spec)}",
        "",
        text_or_placeholder(project.get("summary")),
        "",
        "## Source",
        f"- System: {text_or_placeholder(source.get('system'))}",
        f"- Type: {text_or_placeholder(source.get('type'))}",
        f"- Idea ID: {text_or_placeholder(source.get('idea_id'))}",
        f"- Design brief ID: {text_or_placeholder(source.get('design_brief_id'))}",
        f"- Status: {text_or_placeholder(source.get('status'))}",
        f"- Domain: {text_or_placeholder(source.get('domain'))}",
        f"- Category: {text_or_placeholder(source.get('category'))}",
        "",
        "## Evidence",
        f"- Rationale: {text_or_placeholder(evidence.get('rationale'))}",
        f"- Insights: {join_list(evidence.get('insight_ids'))}",
        f"- Signals: {join_list(evidence.get('signal_ids'))}",
        f"- Source ideas: {join_list(evidence.get('source_idea_ids'))}",
        "",
        "## Quality",
        f"- Quality score: {score_text(quality.get('quality_score'))}",
        f"- Novelty score: {score_text(quality.get('novelty_score'))}",
        f"- Usefulness score: {score_text(quality.get('usefulness_score'))}",
        f"- Rejection tags: {join_list(quality.get('rejection_tags'))}",
        "",
        "## Evaluation",
        f"- Recommendation: {text_or_placeholder(evaluation.get('recommendation'))}",
        f"- Overall score: {score_text(evaluation.get('overall_score'))}",
        "",
        "## Execution",
        f"- Validation plan: {text_or_placeholder(execution.get('validation_plan'))}",
        f"- MVP scope: {join_list(execution.get('mvp_scope'))}",
        "",
        "## Max Metadata",
        "```json",
        json.dumps(metadata, indent=2, sort_keys=True),
        "```",
    ]
    return "\n".join(lines)


def html_summary(tact_spec: dict[str, Any], metadata: dict[str, Any]) -> str:
    return "<br>".join(html.escape(line) for line in markdown_summary(tact_spec, metadata).splitlines())


def text_or_placeholder(value: object) -> str:
    return optional_text(value) or "Not specified"


def score_text(value: object) -> str:
    if isinstance(value, int | float):
        return f"{value:.1f}"
    return text_or_placeholder(value)


def join_list(value: object) -> str:
    if not isinstance(value, list):
        return "None"
    items = [str(item).strip() for item in value if str(item).strip()]
    return ", ".join(items) if items else "None"


def tag_value(value: object, *, prefix: str | None = None) -> str:
    text = optional_text(value)
    if not text:
        return ""
    safe = re.sub(r"[^a-z0-9.-]+", "-", text.lower().replace("_", "-")).strip("-")
    return f"{prefix}-{safe}" if prefix and safe else safe


def response_json(response: httpx.Response, error_cls: type[Exception], message: str) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise error_cls(message) from exc
    return body if isinstance(body, dict) else {}


def response_preview(response: httpx.Response, *, secrets: list[str | None] | None = None, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) > limit:
        text = text[:limit] + "..."
    return redact_text(text, secrets=secrets)


def redact_text(text: str, *, secrets: list[str | None] | None = None) -> str:
    redacted = text
    for secret in secrets or []:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    redacted = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", redacted)
    redacted = re.sub(r"Basic\s+[A-Za-z0-9._~+/=-]+", "Basic [REDACTED]", redacted)
    return redacted


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.query:
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "[REDACTED]", parts.fragment))


def quote_path(value: str) -> str:
    return quote(value, safe="")


def iso_datetime(value: datetime) -> str:
    return value.isoformat()


def add_minutes(value: datetime, minutes: int) -> datetime:
    return value + timedelta(minutes=minutes)

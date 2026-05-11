"""Pipeline run digest rendering for email-ready notifications."""

from __future__ import annotations

import html
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class PipelineDigest:
    """Structured summary of one Max pipeline run."""

    run_id: str
    timestamp: str
    signals_fetched: int
    insights_generated: int
    ideas_scored: int
    top_ideas: list[dict[str, Any]]
    errors: list[Any]
    duration_seconds: float


def build_pipeline_digest(run_summary: dict[str, Any]) -> PipelineDigest:
    """Extract pipeline run stats into a stable digest object."""
    summary = run_summary if isinstance(run_summary, dict) else {}
    stats = summary.get("stats") if isinstance(summary.get("stats"), dict) else {}
    counts = summary.get("counts") if isinstance(summary.get("counts"), dict) else {}

    return PipelineDigest(
        run_id=_text(summary.get("run_id"), summary.get("id"), "unknown"),
        timestamp=_text(
            summary.get("timestamp"),
            summary.get("completed_at"),
            summary.get("started_at"),
            datetime.now(timezone.utc).isoformat(),
        ),
        signals_fetched=_int_value(
            (summary, stats, counts),
            ("signals_fetched", "signals", "signal_count"),
        ),
        insights_generated=_int_value(
            (summary, stats, counts),
            ("insights_generated", "insights", "insight_count"),
        ),
        ideas_scored=_int_value(
            (summary, stats, counts),
            ("ideas_scored", "ideas", "idea_count"),
        ),
        top_ideas=_top_ideas(summary),
        errors=_errors(summary),
        duration_seconds=_float_value(
            (summary, stats, counts),
            ("duration_seconds", "duration", "elapsed_seconds"),
        ),
    )


def render_digest_text(digest: PipelineDigest) -> str:
    """Render a pipeline digest as plain text."""
    lines = [
        "Max Pipeline Digest",
        f"Run ID: {digest.run_id}",
        f"Timestamp: {digest.timestamp}",
        f"Signals fetched: {digest.signals_fetched}",
        f"Insights generated: {digest.insights_generated}",
        f"Ideas scored: {digest.ideas_scored}",
        f"Duration: {digest.duration_seconds:.1f}s",
        "",
        "Top ideas:",
    ]
    if digest.top_ideas:
        for idea in digest.top_ideas:
            lines.append(
                "- "
                f"{_text(idea.get('title'), 'Untitled idea')} "
                f"(score: {_score_text(idea.get('score'))}, "
                f"recommendation: {_text(idea.get('recommendation'), 'n/a')})"
            )
    else:
        lines.append("- No top ideas identified")

    lines.extend(["", "Errors:"])
    if digest.errors:
        lines.extend(f"- {_text(error, 'Unknown error')}" for error in digest.errors)
    else:
        lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def render_digest_html(digest: PipelineDigest) -> str:
    """Render a pipeline digest as a simple HTML email body."""
    rows = []
    for idea in digest.top_ideas:
        rows.append(
            "<tr>"
            f"<td>{html.escape(_text(idea.get('title'), 'Untitled idea'))}</td>"
            f"<td>{html.escape(_score_text(idea.get('score')))}</td>"
            f"<td>{html.escape(_text(idea.get('recommendation'), 'n/a'))}</td>"
            "</tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="3">No top ideas identified</td></tr>')

    error_items = "".join(
        f"<li>{html.escape(_text(error, 'Unknown error'))}</li>" for error in digest.errors
    ) or "<li>None</li>"

    return "\n".join(
        [
            "<!doctype html>",
            "<html>",
            "<body>",
            "<h1>Max Pipeline Digest</h1>",
            "<dl>",
            f"<dt>Run ID</dt><dd>{html.escape(digest.run_id)}</dd>",
            f"<dt>Timestamp</dt><dd>{html.escape(digest.timestamp)}</dd>",
            f"<dt>Signals fetched</dt><dd>{digest.signals_fetched}</dd>",
            f"<dt>Insights generated</dt><dd>{digest.insights_generated}</dd>",
            f"<dt>Ideas scored</dt><dd>{digest.ideas_scored}</dd>",
            f"<dt>Duration</dt><dd>{digest.duration_seconds:.1f}s</dd>",
            "</dl>",
            "<h2>Top Ideas</h2>",
            "<table>",
            "<thead><tr><th>Title</th><th>Score</th><th>Recommendation</th></tr></thead>",
            f"<tbody>{''.join(rows)}</tbody>",
            "</table>",
            "<h2>Errors</h2>",
            f"<ul>{error_items}</ul>",
            "</body>",
            "</html>",
        ]
    )


def render_digest_json(digest: PipelineDigest) -> str:
    """Render a pipeline digest as stable JSON."""
    return json.dumps(asdict(digest), indent=2, sort_keys=True, default=str)


def _top_ideas(summary: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = summary.get("top_ideas")
    if candidates is None:
        candidates = summary.get("ideas") or summary.get("evaluations")
    if not isinstance(candidates, list):
        return []

    ideas = [_idea_dict(item) for item in candidates]
    ideas = [idea for idea in ideas if idea]
    ideas.sort(key=lambda idea: _float(idea.get("score"), 0.0), reverse=True)
    return ideas[:5]


def _idea_dict(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    project = item.get("project") if isinstance(item.get("project"), dict) else {}
    evaluation = item.get("evaluation") if isinstance(item.get("evaluation"), dict) else {}
    title = _text(item.get("title"), project.get("title"), item.get("idea_id"), "Untitled idea")
    score = _first_present((item, evaluation), ("score", "overall_score", "quality_score"))
    recommendation = _text(
        item.get("recommendation"),
        evaluation.get("recommendation"),
        item.get("status"),
        "n/a",
    )
    return {"title": title, "score": _float(score, 0.0), "recommendation": recommendation}


def _errors(summary: dict[str, Any]) -> list[Any]:
    errors = summary.get("errors")
    if errors is None:
        errors = summary.get("error_summaries") or summary.get("failures")
    if isinstance(errors, list):
        return errors
    if errors:
        return [errors]
    return []


def _int_value(sources: tuple[dict[str, Any], ...], keys: tuple[str, ...]) -> int:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            if key in source:
                return int(max(_float(source.get(key), 0.0), 0.0))
    return 0


def _float_value(sources: tuple[dict[str, Any], ...], keys: tuple[str, ...]) -> float:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            if key in source:
                return max(_float(source.get(key), 0.0), 0.0)
    return 0.0


def _first_present(sources: tuple[dict[str, Any], ...], keys: tuple[str, ...]) -> Any:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            if source.get(key) not in (None, ""):
                return source.get(key)
    return None


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _score_text(value: Any) -> str:
    return f"{_float(value, 0.0):.1f}"


def _text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""

"""Beta feedback theme export report."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any, Iterable, Literal, TypedDict

SCHEMA_VERSION = "max.beta_feedback_theme_report.v1"
KIND = "max.beta_feedback_theme_report"
DEFAULT_GENERATED_AT = "2026-05-20T00:00:00+00:00"

Severity = Literal["critical", "high", "medium", "low", "unknown"]
Sentiment = Literal["negative", "neutral", "positive", "mixed", "unknown"]

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}
_SENTIMENTS = {"negative", "neutral", "positive", "mixed"}
_SEVERE = {"critical", "high"}


class BetaFeedbackThemeInput(TypedDict, total=False):
    account: str
    customer: str
    name: str
    segment: str
    theme: str
    topic: str
    feedback_theme: str
    sentiment: str
    severity: str
    blocker: bool | str
    owner: str
    submitted_at: str
    date: str
    feedback: str
    comment: str


def build_beta_feedback_theme_report(
    records: Iterable[BetaFeedbackThemeInput | dict[str, Any]],
    *,
    title: str = "Beta Feedback Theme Report",
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    rows = _normalize_records(records)
    summary = _summary(rows)
    theme_rows = _theme_rows(rows)
    segment_breakdown = _segment_breakdown(rows)
    blocker_themes = [row for row in theme_rows if row["blocker_count"] > 0]
    unowned_severe_feedback = _unowned_severe_feedback(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Beta Feedback Theme Report",
        "summary": summary,
        "theme_rows": theme_rows,
        "segment_breakdown": segment_breakdown,
        "blocker_themes": blocker_themes,
        "unowned_severe_feedback": unowned_severe_feedback,
        "recommended_actions": _recommended_actions(summary, blocker_themes, unowned_severe_feedback),
        "feedback_rows": rows,
    }


def render_beta_feedback_theme_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Beta Feedback Theme Report'}",
        "",
        f"Schema: `{report.get('schema_version', SCHEMA_VERSION)}`",
        f"Generated: {report.get('generated_at', DEFAULT_GENERATED_AT)}",
        "",
        "## Summary",
        "",
        f"- Feedback records: {summary.get('feedback_count', 0)}",
        f"- Themes: {summary.get('theme_count', 0)}",
        f"- Segments: {summary.get('segment_count', 0)}",
        f"- Blocker records: {summary.get('blocker_count', 0)}",
        f"- Unowned severe feedback: {summary.get('unowned_severe_count', 0)}",
        "",
        "## Themes",
        "",
    ]
    if report.get("theme_rows"):
        lines.extend(
            [
                "| Theme | Records | Blockers | Severe | Segments | Sentiment |",
                "|-------|---------|----------|--------|----------|-----------|",
            ]
        )
        for row in report["theme_rows"]:
            lines.append(
                f"| {_md(row['theme'])} | {row['feedback_count']} | {row['blocker_count']} | {row['severe_count']} | "
                f"{_md(', '.join(row['segments']))} | {_md(row['dominant_sentiment'])} |"
            )
    else:
        lines.append("- No beta feedback records were supplied.")

    lines.extend(["", "## Blocker Themes", ""])
    if report.get("blocker_themes"):
        for row in report["blocker_themes"]:
            lines.append(f"- {row['theme']}: {row['blocker_count']} blocker record(s), {row['severe_count']} severe")
    else:
        lines.append("- No blocker themes identified.")

    lines.extend(["", "## Recommended Actions", ""])
    actions = report.get("recommended_actions") or []
    if actions:
        for action in actions:
            lines.append(f"- {action}")
    else:
        lines.append("- No recommended actions.")
    return "\n".join(lines).rstrip() + "\n"


def render_beta_feedback_theme_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_records(records: Iterable[BetaFeedbackThemeInput | dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, raw in enumerate(records):
        theme = _theme(raw.get("theme") or raw.get("feedback_theme") or raw.get("topic"))
        severity = _severity(raw.get("severity"))
        owner = _text(raw.get("owner")) or "Unassigned"
        rows.append(
            {
                "account": _text(raw.get("account") or raw.get("customer") or raw.get("name") or "Unknown account"),
                "segment": _text(raw.get("segment") or "Unassigned segment"),
                "theme": theme,
                "sentiment": _sentiment(raw.get("sentiment")),
                "severity": severity,
                "blocker": _bool(raw.get("blocker")),
                "owner": owner,
                "submitted_at": _text(raw.get("submitted_at") or raw.get("date")),
                "feedback": _text(raw.get("feedback") or raw.get("comment")),
                "_input_order": index,
            }
        )
    rows.sort(
        key=lambda row: (
            not row["blocker"],
            _SEVERITY_ORDER[row["severity"]],
            row["theme"].lower(),
            row["segment"].lower(),
            row["account"].lower(),
            row["submitted_at"] or "9999-12-31",
            row["_input_order"],
        )
    )
    for row in rows:
        row.pop("_input_order", None)
    return rows


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "feedback_count": len(rows),
        "theme_count": len({row["theme"] for row in rows}),
        "segment_count": len({row["segment"] for row in rows}),
        "blocker_count": sum(1 for row in rows if row["blocker"]),
        "severe_count": sum(1 for row in rows if row["severity"] in _SEVERE),
        "unowned_severe_count": sum(1 for row in rows if row["severity"] in _SEVERE and row["owner"] == "Unassigned"),
    }


def _theme_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["theme"]].append(row)
    output = []
    for theme, items in grouped.items():
        sentiment_counts = Counter(row["sentiment"] for row in items)
        severity_counts = {severity: sum(1 for row in items if row["severity"] == severity) for severity in _SEVERITY_ORDER}
        output.append(
            {
                "theme": theme,
                "feedback_count": len(items),
                "blocker_count": sum(1 for row in items if row["blocker"]),
                "severe_count": sum(1 for row in items if row["severity"] in _SEVERE),
                "severity_counts": severity_counts,
                "sentiment_counts": {sentiment: sentiment_counts.get(sentiment, 0) for sentiment in ("negative", "neutral", "positive", "mixed", "unknown")},
                "dominant_sentiment": _dominant(sentiment_counts),
                "segments": sorted({row["segment"] for row in items}, key=str.lower),
                "owners": sorted({row["owner"] for row in items}, key=str.lower),
            }
        )
    output.sort(key=lambda row: (-row["blocker_count"], -row["severe_count"], -row["feedback_count"], row["theme"].lower()))
    return output


def _segment_breakdown(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["segment"]].append(row)
    output = []
    for segment, items in grouped.items():
        themes = Counter(row["theme"] for row in items)
        output.append(
            {
                "segment": segment,
                "feedback_count": len(items),
                "blocker_count": sum(1 for row in items if row["blocker"]),
                "severe_count": sum(1 for row in items if row["severity"] in _SEVERE),
                "themes": [{"theme": theme, "count": count} for theme, count in sorted(themes.items(), key=lambda item: (-item[1], item[0].lower()))],
            }
        )
    output.sort(key=lambda row: (-row["blocker_count"], -row["severe_count"], -row["feedback_count"], row["segment"].lower()))
    return output


def _unowned_severe_feedback(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = [
        {
            "account": row["account"],
            "segment": row["segment"],
            "theme": row["theme"],
            "severity": row["severity"],
            "blocker": row["blocker"],
            "submitted_at": row["submitted_at"],
        }
        for row in rows
        if row["severity"] in _SEVERE and row["owner"] == "Unassigned"
    ]
    output.sort(key=lambda row: (not row["blocker"], _SEVERITY_ORDER[row["severity"]], row["theme"].lower(), row["account"].lower()))
    return output


def _recommended_actions(summary: dict[str, Any], blocker_themes: list[dict[str, Any]], unowned: list[dict[str, Any]]) -> list[str]:
    actions = []
    if blocker_themes:
        top = blocker_themes[0]
        actions.append(f"Escalate blocker theme '{top['theme']}' with {top['blocker_count']} blocker record(s).")
    if unowned:
        actions.append(f"Assign owners for {len(unowned)} severe feedback record(s).")
    if summary.get("feedback_count", 0) and not actions:
        actions.append("Review top beta feedback themes with product and customer success owners.")
    return actions


def _theme(value: Any) -> str:
    text = _text(value)
    return text.title() if text else "Uncategorized"


def _severity(value: Any) -> Severity:
    text = _text(value).lower().replace("_", " ")
    if text in {"critical", "blocker", "p0", "sev0", "sev 0"}:
        return "critical"
    if text in {"high", "major", "p1", "sev1", "sev 1"}:
        return "high"
    if text in {"medium", "moderate", "p2", "sev2", "sev 2"}:
        return "medium"
    if text in {"low", "minor", "p3", "sev3", "sev 3"}:
        return "low"
    return "unknown"


def _sentiment(value: Any) -> Sentiment:
    text = _text(value).lower().replace("_", " ")
    return text if text in _SENTIMENTS else "unknown"  # type: ignore[return-value]


def _dominant(counts: Counter[str]) -> str:
    if not counts:
        return "unknown"
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    return text in {"1", "true", "yes", "y", "blocked", "blocker"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")

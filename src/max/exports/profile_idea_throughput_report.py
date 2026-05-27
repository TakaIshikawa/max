"""Profile idea throughput export report."""

from __future__ import annotations

import json
from typing import Any, Iterable


def build_profile_idea_throughput_report(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in records:
        profile = _text(raw.get("profile")) or "unknown-profile"
        window = _text(raw.get("window") or raw.get("window_label") or raw.get("period")) or _window(raw)
        row = groups.setdefault((profile, window), {"profile": profile, "window": window, "generated_count": 0, "evaluated_count": 0, "approved_count": 0, "published_count": 0})
        count = _int(raw.get("count") or 1)
        status = _text(raw.get("status") or raw.get("idea_status")).lower()
        if raw.get("generated_at") or raw.get("created_at") or status in {"generated", "evaluated", "approved", "published"}:
            row["generated_count"] += count
        if raw.get("evaluated_at") or status in {"evaluated", "approved", "published"}:
            row["evaluated_count"] += count
        if status in {"approved", "published"} or _bool(raw.get("approved")):
            row["approved_count"] += count
        if raw.get("published_at") or raw.get("publication_at") or status == "published":
            row["published_count"] += count
    rows = []
    for row in groups.values():
        approved = row["approved_count"]
        row["publish_rate"] = round(row["published_count"] / approved, 4) if approved else 0.0
        row["throughput_status"] = "publishing" if row["publish_rate"] >= 0.7 else "approval_backlog" if approved else "needs_generation"
        rows.append(row)
    rows.sort(key=lambda row: (row["profile"].lower(), row["window"].lower()))
    return rows


def render_profile_idea_throughput_report_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, indent=2, sort_keys=True, default=str) + "\n"


def render_profile_idea_throughput_report_markdown(rows: list[dict[str, Any]]) -> str:
    lines = ["# Profile Idea Throughput Report", "", "| Profile | Window | Generated | Evaluated | Approved | Published | Publish rate | Status |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    for row in rows:
        lines.append(f"| {row['profile']} | {row['window']} | {row['generated_count']} | {row['evaluated_count']} | {row['approved_count']} | {row['published_count']} | {row['publish_rate']} | {row['throughput_status']} |")
    return "\n".join(lines).rstrip() + "\n"


def _window(raw: dict[str, Any]) -> str:
    value = _text(raw.get("generated_at") or raw.get("created_at") or raw.get("evaluated_at") or raw.get("published_at"))
    return value[:10] if value else "unspecified"


def _bool(value: Any) -> bool:
    return str(value).lower() in {"1", "true", "yes"}


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

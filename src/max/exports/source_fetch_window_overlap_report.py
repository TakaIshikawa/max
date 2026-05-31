"""Source fetch window overlap export report."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def generate_source_fetch_window_overlap_report(fetch_windows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for index, item in enumerate(fetch_windows, start=1):
        row = _window(item, index)
        groups[(row["source"], row["profile"])].append(row)
    issue_rows = []
    summaries = []
    for (source, profile), windows in sorted(groups.items()):
        windows.sort(key=lambda row: (row["start_at"], row["end_at"], row["window_id"]))
        overlap_total = gap_total = 0
        for previous, current in zip(windows, windows[1:]):
            delta = round((_parse(current["start_at"]) - _parse(previous["end_at"])).total_seconds() / 60)
            if delta < 0:
                minutes = abs(delta)
                overlap_total += minutes
                issue_rows.append(_issue(source, profile, previous, current, "overlap", minutes, "critical"))
            elif delta > 0:
                gap_total += delta
                issue_rows.append(_issue(source, profile, previous, current, "gap", delta, "warn"))
        summaries.append({"source": source, "profile": profile, "window_count": len(windows), "overlap_minutes": overlap_total, "gap_minutes": gap_total, "recommended_checkpoint_correction": "Advance checkpoint to last non-overlapping end." if overlap_total else ("Backfill missing window before next fetch." if gap_total else "No correction required.")})
    issue_rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], row["source"], row["profile"], row["previous_window_id"], row["current_window_id"]))
    return {"schema_version": "max.source_fetch_window_overlap_report.v1", "kind": "max.source_fetch_window_overlap_report", "summary": {"group_count": len(summaries), "issue_count": len(issue_rows), "total_overlap_minutes": sum(row["overlap_minutes"] for row in summaries), "total_gap_minutes": sum(row["gap_minutes"] for row in summaries)}, "groups": summaries, "issue_rows": issue_rows}


def _issue(source: str, profile: str, previous: dict[str, Any], current: dict[str, Any], issue_type: str, minutes: int, severity: str) -> dict[str, Any]:
    return {"source": source, "profile": profile, "previous_window_id": previous["window_id"], "current_window_id": current["window_id"], "issue_type": issue_type, "minutes": minutes, "severity": severity, "recommended_checkpoint_correction": "Move current start to previous end." if issue_type == "overlap" else "Replay from previous end to current start."}


def _window(item: dict[str, Any], index: int) -> dict[str, Any]:
    return {"window_id": _text(item.get("window_id") or item.get("id")) or f"window-{index}", "source": _text(item.get("source")) or "unknown", "profile": _text(item.get("profile")) or "default", "start_at": _text(item.get("start_at") or item.get("from")), "end_at": _text(item.get("end_at") or item.get("to"))}


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

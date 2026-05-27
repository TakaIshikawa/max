"""Buildable unit readiness blocker export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

CRITICAL = {"missing_stack", "unclear_user", "missing_acceptance_criteria"}


def build_buildable_unit_readiness_blocker_report(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for raw in records:
        blockers = [_category(item) for item in _list(raw.get("blockers") or raw.get("issues") or raw.get("gaps"))]
        blockers = sorted({item for item in blockers if item})
        has_critical = any(item in CRITICAL for item in blockers)
        status = "critical" if has_critical else "warning" if blockers else "ready"
        rows.append({"unit_id": _text(raw.get("unit_id") or raw.get("id")) or "unknown-unit", "title": _text(raw.get("title")) or "Untitled unit", "blocker_categories": blockers, "blocker_count": len(blockers), "readiness_status": status, "next_action": _action(status)})
    rows.sort(key=lambda row: ({"critical": 0, "warning": 1, "ready": 2}[row["readiness_status"]], row["unit_id"].lower()))
    return rows


def render_buildable_unit_readiness_blocker_report_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, indent=2, sort_keys=True, default=str) + "\n"


def render_buildable_unit_readiness_blocker_report_markdown(rows: list[dict[str, Any]]) -> str:
    lines = ["# Buildable Unit Readiness Blocker Report", "", "| Unit | Title | Blockers | Count | Status | Next action |", "| --- | --- | --- | ---: | --- | --- |"]
    for row in rows:
        lines.append(f"| {row['unit_id']} | {row['title']} | {', '.join(row['blocker_categories']) or 'none'} | {row['blocker_count']} | {row['readiness_status']} | {row['next_action']} |")
    return "\n".join(lines).rstrip() + "\n"


def _category(value: Any) -> str:
    text = _text(value).lower().replace(" ", "_").replace("-", "_")
    return {"no_stack": "missing_stack", "weak_signal": "weak_evidence", "unknown_user": "unclear_user", "risky": "high_risk", "no_acceptance": "missing_acceptance_criteria"}.get(text, text)


def _action(status: str) -> str:
    return {"critical": "Resolve critical readiness blockers before build.", "warning": "Review blockers during planning.", "ready": "Proceed to implementation planning."}[status]


def _list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    return list(value) if isinstance(value, (list, tuple, set)) else [value]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

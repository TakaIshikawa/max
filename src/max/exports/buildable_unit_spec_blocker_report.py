"""Buildable unit spec blocker export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.buildable_unit_spec_blocker_report.v1"
KIND = "max.buildable_unit_spec_blocker_report"
_STATUS_ORDER = {"critical": 0, "blocked": 1, "clear": 2}


def generate_buildable_unit_spec_blocker_report(units: Iterable[dict[str, Any]], *, critical_blocked_units: int = 3) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"unit_count": 0, "blocked_units": 0, "ready_units": 0, "missing_spec_fields": 0, "unresolved_evidence_gaps": 0})
    for raw in units:
        if not isinstance(raw, dict):
            continue
        blocker = _text(raw.get("blocker_type") or raw.get("blocker") or raw.get("reason")) or ("none" if _ready(raw) else "unspecified")
        key = (_text(raw.get("profile") or raw.get("profile_id")) or "default", blocker)
        groups[key]["unit_count"] += 1
        if _ready(raw):
            groups[key]["ready_units"] += 1
        else:
            groups[key]["blocked_units"] += 1
        groups[key]["missing_spec_fields"] += _count(raw.get("missing_spec_fields") or raw.get("missing_fields"))
        groups[key]["unresolved_evidence_gaps"] += _count(raw.get("unresolved_evidence_gaps") or raw.get("evidence_gaps"))

    rows = []
    for (profile, blocker_type), totals in groups.items():
        blocked = totals["blocked_units"]
        rows.append({"profile": profile, "blocker_type": blocker_type, **totals, "status": "critical" if blocked >= critical_blocked_units else ("blocked" if blocked else "clear")})
    rows.sort(key=lambda row: (_STATUS_ORDER[row["status"]], -row["blocked_units"], row["profile"].casefold(), row["blocker_type"].casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": rows[0]["status"] if rows else "clear", "group_count": len(rows), "blocked_units": sum(row["blocked_units"] for row in rows), "ready_units": sum(row["ready_units"] for row in rows), "missing_spec_fields": sum(row["missing_spec_fields"] for row in rows), "unresolved_evidence_gaps": sum(row["unresolved_evidence_gaps"] for row in rows)}, "rows": rows}


def _ready(raw: dict[str, Any]) -> bool:
    status = _text(raw.get("status") or raw.get("readiness"))
    return bool(raw.get("ready")) or status in {"ready", "clear", "buildable"}


def _count(value: Any) -> int:
    if isinstance(value, (list, tuple, set, dict)):
        return len(value)
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().lower().split()) if value is not None else ""

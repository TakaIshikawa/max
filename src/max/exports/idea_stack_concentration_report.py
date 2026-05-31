"""Idea stack concentration export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.idea_stack_concentration_report.v1"
KIND = "max.idea_stack_concentration_report"
SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def generate_idea_stack_concentration_report(units: Iterable[dict[str, Any]], *, concentration_threshold: float = 0.5, critical_threshold: float = 0.75) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for unit in units:
        groups[(_text(unit.get("profile")) or "default", _text(unit.get("recommendation")) or "unspecified")].append(unit)
    rows = []
    for (profile, recommendation), items in groups.items():
        total = len(items)
        stack_units: dict[str, list[str]] = defaultdict(list)
        for index, unit in enumerate(items, start=1):
            unit_id = _text(unit.get("unit_id") or unit.get("id")) or f"unit-{index}"
            for stack in _items(unit.get("stack_tags") or unit.get("stacks") or unit.get("technology_stack")):
                stack_units[stack].append(unit_id)
        for stack, unit_ids in stack_units.items():
            share = len(unit_ids) / total if total else 0.0
            severity = "critical" if share >= critical_threshold else ("warn" if share >= concentration_threshold else "ok")
            rows.append({"profile": profile, "recommendation": recommendation, "stack": stack, "unit_count": len(unit_ids), "total_units": total, "share": round(share, 4), "affected_units": sorted(unit_ids), "severity": severity, "recommendation_text": "Diversify stack choices before adding more units." if severity != "ok" else "No action required."})
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], -row["share"], row["profile"], row["stack"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"row_count": len(rows), "concentrated_stack_count": sum(1 for row in rows if row["severity"] != "ok")}, "rows": rows}


def render_idea_stack_concentration_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_idea_stack_concentration_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Idea Stack Concentration Report", ""]
    for row in report.get("rows") or []:
        lines.append(f"- {row['profile']} / {row['recommendation']} / {row['stack']}: {row['unit_count']} ({row['share']}). {row['recommendation_text']}")
    return "\n".join(lines).rstrip() + "\n"


def _items(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, Iterable):
        parts = list(value)
    else:
        parts = []
    return sorted({_text(part) for part in parts if _text(part)})


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

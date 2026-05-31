"""Spec evidence trace gap export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

SCHEMA_VERSION = "max.spec_evidence_trace_gap_report.v1"
KIND = "max.spec_evidence_trace_gap_report"
SEVERITY_RANK = {"critical": 0, "warn": 1, "info": 2, "ok": 3}
GAP_HINTS = {
    "unit": "Attach the originating buildable unit or tact unit before release.",
    "insight": "Link the synthesized insight that justified the spec decision.",
    "signal": "Backfill source signal IDs so the insight chain is auditable.",
}


def generate_spec_evidence_trace_gap_report(specs: Iterable[dict[str, Any]], *, title: str = "Spec Evidence Trace Gap Report") -> dict[str, Any]:
    rows = []
    for index, spec in enumerate(specs, start=1):
        gaps = _gaps(spec)
        if not gaps:
            continue
        rows.append(_row(spec, index, gaps))
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], -row["missing_link_depth"], row["spec_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "Spec Evidence Trace Gap Report",
        "summary": {
            "gap_spec_count": len(rows),
            "critical_gap_count": sum(1 for row in rows if row["severity"] == "critical"),
            "missing_unit_count": sum(1 for row in rows if row["missing_unit_link"]),
            "missing_insight_count": sum(1 for row in rows if row["missing_insight_link"]),
            "missing_signal_count": sum(1 for row in rows if row["missing_signal_link"]),
        },
        "rows": rows,
    }


def render_spec_evidence_trace_gap_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_spec_evidence_trace_gap_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report.get('title') or 'Spec Evidence Trace Gap Report'}", "", f"Gap specs: {report.get('summary', {}).get('gap_spec_count', 0)}", ""]
    for row in report.get("rows") or []:
        lines.append(f"- {row['spec_id']} ({row['severity']}): missing {', '.join(row['missing_link_types'])}. {row['recommendation']}")
        for gap in row["missing_link_types"]:
            lines.append(f"  - {gap}: {GAP_HINTS[gap]}")
    return "\n".join(lines).rstrip() + "\n"


def _row(spec: dict[str, Any], index: int, gaps: list[str]) -> dict[str, Any]:
    status = _text(spec.get("status")).lower()
    released = status in {"approved", "published", "released"} or bool(spec.get("approved") or spec.get("published"))
    depth = len(gaps)
    severity = "critical" if released and depth >= 2 else ("warn" if released or depth >= 2 else "info")
    return {
        "spec_id": _text(spec.get("spec_id") or spec.get("id")) or f"spec-{index}",
        "title": _text(spec.get("title")) or "Untitled spec",
        "status": status or "draft",
        "missing_link_types": gaps,
        "missing_link_depth": depth,
        "missing_unit_link": "unit" in gaps,
        "missing_insight_link": "insight" in gaps,
        "missing_signal_link": "signal" in gaps,
        "severity": severity,
        "recommendation": "Block publication until evidence trace is complete." if severity == "critical" else "Backfill missing evidence links before approval.",
    }


def _gaps(spec: dict[str, Any]) -> list[str]:
    checks = (("unit", spec.get("unit_ids") or spec.get("units") or spec.get("unit_id")), ("insight", spec.get("insight_ids") or spec.get("insights") or spec.get("insight_id")), ("signal", spec.get("signal_ids") or spec.get("signals") or spec.get("source_signal_ids")))
    return [name for name, value in checks if not _items(value)]


def _items(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, Iterable):
        parts = list(value)
    else:
        parts = []
    return [_text(part) for part in parts if _text(part)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

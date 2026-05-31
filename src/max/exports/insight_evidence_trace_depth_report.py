"""Insight evidence trace depth export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

SCHEMA_VERSION = "max.insight_evidence_trace_depth_report.v1"
KIND = "max.insight_evidence_trace_depth_report"
SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def generate_insight_evidence_trace_depth_report(insights: Iterable[dict[str, Any]], *, min_depth: int = 2, min_source_count: int = 2) -> dict[str, Any]:
    rows = []
    for index, insight in enumerate(insights, start=1):
        depth = _int(insight.get("evidence_depth") or insight.get("depth"))
        signals = _items(insight.get("signal_ids") or insight.get("signals"))
        sources = _items(insight.get("source_ids") or insight.get("sources"))
        missing = _items(insight.get("missing_references") or insight.get("missing_upstream_references"))
        if not sources:
            sources = sorted({_text(signal).split(":")[0] for signal in signals if ":" in _text(signal)})
        shallow = depth < min_depth
        low_sources = len(sources) < min_source_count
        if not (missing or shallow or low_sources):
            severity = "ok"
        else:
            severity = "critical" if missing else "warn"
        rows.append({"insight_id": _text(insight.get("insight_id") or insight.get("id")) or f"insight-{index}", "profile": _text(insight.get("profile")) or "default", "evidence_depth": depth, "distinct_source_count": len(sources), "signal_count": len(signals), "missing_references": missing, "severity": severity, "remediation": "Restore missing upstream references." if missing else ("Add deeper or more diverse evidence." if severity == "warn" else "No action required.")})
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], row["evidence_depth"], row["distinct_source_count"], row["insight_id"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"insight_count": len(rows), "flagged_insight_count": sum(1 for row in rows if row["severity"] != "ok")}, "rows": rows}


def render_insight_evidence_trace_depth_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_insight_evidence_trace_depth_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Insight Evidence Trace Depth Report", ""]
    for row in report.get("rows") or []:
        lines.append(f"- {row['insight_id']}: depth {row['evidence_depth']}, sources {row['distinct_source_count']}, signals {row['signal_count']}, missing {', '.join(row['missing_references']) or '-'} ({row['severity']}). {row['remediation']}")
    return "\n".join(lines).rstrip() + "\n"


def _items(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, Iterable):
        parts = list(value)
    else:
        parts = []
    return sorted({_text(part) for part in parts if _text(part)})


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

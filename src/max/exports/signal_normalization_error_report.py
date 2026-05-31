"""Signal normalization error export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def generate_signal_normalization_error_report(normalization_events: Iterable[dict[str, Any]], *, critical_failure_count: int = 10) -> dict[str, Any]:
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in normalization_events:
        if not _failed(event):
            continue
        key = (_text(event.get("source")) or "unknown", _text(event.get("profile")) or "default", _text(event.get("field")) or "unknown", _text(event.get("error_type")) or "normalization_error")
        groups[key].append(event)
    rows = []
    for (source, profile, field, error_type), events in groups.items():
        ids = sorted({_text(event.get("signal_id") or event.get("id")) for event in events if _text(event.get("signal_id") or event.get("id"))})
        examples = []
        for event in sorted(events, key=lambda event: _text(event.get("message") or event.get("error"))):
            message = _text(event.get("message") or event.get("error"))
            if message and message not in examples:
                examples.append(message)
            if len(examples) == 3:
                break
        required = any(bool(event.get("required_field") or event.get("required")) for event in events)
        severity = "critical" if required or len(events) >= critical_failure_count else "warn"
        rows.append({"source": source, "profile": profile, "field": field, "error_type": error_type, "failure_count": len(events), "affected_signal_ids": ids[:20], "top_error_examples": examples, "severity": severity, "remediation": "Fix required-field normalization before publishing." if required else "Add parser guardrail or source-specific mapping."})
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], -row["failure_count"], row["source"], row["profile"], row["field"], row["error_type"]))
    return {"schema_version": "max.signal_normalization_error_report.v1", "kind": "max.signal_normalization_error_report", "summary": {"failure_group_count": len(rows), "critical_count": sum(1 for row in rows if row["severity"] == "critical"), "failure_count": sum(row["failure_count"] for row in rows)}, "rows": rows}


def _failed(event: dict[str, Any]) -> bool:
    status = _text(event.get("status")).lower()
    return bool(event.get("failed")) or status in {"failed", "error"} or bool(event.get("error_type"))


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

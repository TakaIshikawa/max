"""Source signal drop reason export report."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any, Mapping

SCHEMA_VERSION = "max.source_signal_drop_reason_report.v1"
KIND = "max.source_signal_drop_reason_report"


def build_source_signal_drop_reason_report(records: list[Mapping[str, Any]], *, generated_at: str = "2026-06-01T00:00:00+00:00") -> dict[str, Any]:
    dropped = []
    source_totals: dict[str, Counter[str]] = defaultdict(Counter)
    reason_totals: Counter[str] = Counter()
    accepted_count = 0
    for record in records:
        if not isinstance(record, Mapping):
            continue
        source = _text(record.get("source") or record.get("adapter")) or "unknown-source"
        status = _text(record.get("status")).lower()
        if status in {"accepted", "kept", "ok"}:
            accepted_count += 1
            source_totals[source]["accepted_count"] += 1
            continue
        if status != "dropped":
            source_totals[source]["seen_count"] += 1
            continue
        reason = _text(record.get("drop_reason")) or "unknown"
        row = {"source": source, "reason": reason, "signal_id": _text(record.get("signal_id") or record.get("id")) or "unknown-signal", "adapter": _text(record.get("adapter")) or source, "fetched_at": _text(record.get("fetched_at")), "profile": _text(record.get("profile")) or "unknown-profile"}
        dropped.append(row)
        source_totals[source]["dropped_count"] += 1
        reason_totals[reason] += 1
    dropped.sort(key=lambda row: (row["source"].lower(), row["reason"].lower(), row["signal_id"].lower()))
    source_rows = []
    for source, counts in source_totals.items():
        accepted = counts["accepted_count"]
        dropped_count = counts["dropped_count"]
        total = accepted + dropped_count + counts["seen_count"]
        source_rows.append({"source": source, "accepted_count": accepted, "dropped_count": dropped_count, "total_seen": total, "drop_rate": round(dropped_count / total, 4) if total else 0.0})
    source_rows.sort(key=lambda row: row["source"].lower())
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": generated_at, "summary": {"dropped_count": len(dropped), "accepted_count": accepted_count, "unknown_reason_count": reason_totals["unknown"]}, "source_totals": source_rows, "reason_totals": [{"reason": reason, "count": count} for reason, count in sorted(reason_totals.items(), key=lambda item: (-item[1], item[0].lower()))], "dropped_signals": dropped}


def render_source_signal_drop_reason_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_signal_drop_reason_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Source Signal Drop Reason Report", "", "## Dropped Signals", ""]
    lines.extend([f"- {row['source']} / {row['reason']} / {row['signal_id']}" for row in report.get("dropped_signals") or []] or ["- No dropped signals."])
    return "\n".join(lines).rstrip() + "\n"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

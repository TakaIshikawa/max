"""Source signal duplicate rate export report."""

from __future__ import annotations

from typing import Any, Mapping


def generate_source_signal_duplicate_rate_report(signals: list[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[str]] = {}
    for signal in signals:
        if not isinstance(signal, Mapping):
            continue
        source = _text(signal.get("source") or signal.get("source_adapter") or signal.get("adapter")) or "unknown"
        key = _text(signal.get("canonical_url") or signal.get("url") or signal.get("id") or signal.get("signal_id"))
        if not key:
            continue
        grouped.setdefault(source, []).append(key)
    rows = []
    for source, keys in grouped.items():
        total = len(keys)
        unique = len(set(keys))
        duplicate = total - unique
        rows.append({"source": source, "total_count": total, "unique_count": unique, "duplicate_count": duplicate, "duplicate_rate": round(duplicate / total, 4) if total else 0.0})
    rows.sort(key=lambda row: (-row["duplicate_rate"], -row["duplicate_count"], row["source"].lower()))
    return {"schema_version": "max.source_signal_duplicate_rate_report.v1", "kind": "max.source_signal_duplicate_rate_report", "summary": {"source_count": len(rows), "total_count": sum(row["total_count"] for row in rows), "duplicate_count": sum(row["duplicate_count"] for row in rows)}, "source_rows": rows}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

"""Signal source duplicate rate export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.signal_source_duplicate_rate_report.v1"
KIND = "max.signal_source_duplicate_rate_report"


def generate_signal_source_duplicate_rate_report(records: Iterable[dict[str, Any]], *, duplicate_rate_threshold: float = 0.25) -> dict[str, Any]:
    threshold = _ratio(duplicate_rate_threshold)
    groups: dict[str, dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        source = _text(raw.get("source") or raw.get("signal_source") or raw.get("source_adapter") or raw.get("adapter")) or "unknown-source"
        group = groups.setdefault(source, {"total_count": 0, "duplicate_count": 0, "keys": []})
        explicit_total = _int(raw.get("total_count") or raw.get("signal_count"))
        explicit_duplicates = _int(raw.get("duplicate_count") or raw.get("duplicates"))
        if explicit_total or explicit_duplicates:
            group["total_count"] += max(explicit_total, explicit_duplicates)
            group["duplicate_count"] += min(explicit_duplicates, max(explicit_total, explicit_duplicates))
            continue
        group["total_count"] += 1
        if _bool(raw.get("duplicate") if "duplicate" in raw else raw.get("is_duplicate")):
            group["duplicate_count"] += 1
            continue
        key = _text(raw.get("canonical_url") or raw.get("url") or raw.get("content_hash") or raw.get("id") or raw.get("signal_id"))
        if key:
            group["keys"].append(key)

    rows = []
    for source, group in groups.items():
        inferred_duplicates = _inferred_duplicate_count(group["keys"])
        duplicate_count = min(group["total_count"], group["duplicate_count"] + inferred_duplicates)
        total_count = group["total_count"]
        duplicate_rate = round(duplicate_count / total_count, 4) if total_count else 0.0
        rows.append(
            {
                "source": source,
                "total_count": total_count,
                "duplicate_count": duplicate_count,
                "duplicate_rate": duplicate_rate,
                "status": "high_duplicate_rate" if duplicate_rate > threshold else "ok",
            }
        )
    rows.sort(key=lambda row: (-row["duplicate_rate"], row["source"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "source_count": len(rows),
            "total_count": sum(row["total_count"] for row in rows),
            "duplicate_count": sum(row["duplicate_count"] for row in rows),
            "flagged_source_count": sum(1 for row in rows if row["status"] == "high_duplicate_rate"),
            "duplicate_rate_threshold": threshold,
        },
        "rows": rows,
    }


def _inferred_duplicate_count(keys: list[str]) -> int:
    counts: dict[str, int] = {}
    for key in keys:
        counts[key] = counts.get(key, 0) + 1
    return sum(count - 1 for count in counts.values())


def _ratio(value: Any) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.25


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "duplicate", "duplicated"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

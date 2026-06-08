"""Source adapter payload size export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.source_adapter_payload_size_report.v1"
KIND = "max.source_adapter_payload_size_report"

_STATUS_ORDER = {"oversized": 0, "warning": 1, "ok": 2}


def generate_source_adapter_payload_size_report(
    records: Iterable[dict[str, Any]], *, warning_bytes: int = 500_000, max_bytes: int = 1_000_000
) -> dict[str, Any]:
    warning = _int(warning_bytes)
    maximum = _int(max_bytes)
    groups: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"payload_count": 0, "total_bytes": 0, "max_bytes": 0})
    for raw in records:
        if not isinstance(raw, dict):
            continue
        key = (
            _text(raw.get("adapter") or raw.get("source_adapter") or raw.get("source")) or "unknown-adapter",
            _text(raw.get("profile") or raw.get("profile_id") or raw.get("source_profile")) or "default",
        )
        size = _payload_size(raw)
        groups[key]["payload_count"] += 1
        groups[key]["total_bytes"] += size
        groups[key]["max_bytes"] = max(groups[key]["max_bytes"], size)

    rows = []
    for (adapter, profile), totals in groups.items():
        avg_bytes = round(totals["total_bytes"] / totals["payload_count"], 2) if totals["payload_count"] else 0.0
        rows.append(
            {
                "adapter": adapter,
                "profile": profile,
                "payload_count": totals["payload_count"],
                "total_bytes": totals["total_bytes"],
                "avg_bytes": avg_bytes,
                "max_bytes": totals["max_bytes"],
                "status": _status(totals["max_bytes"], warning, maximum),
            }
        )

    rows.sort(key=lambda row: (_STATUS_ORDER[row["status"]], -row["max_bytes"], row["adapter"].casefold(), row["profile"].casefold()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "group_count": len(rows),
            "payload_count": sum(row["payload_count"] for row in rows),
            "total_bytes": sum(row["total_bytes"] for row in rows),
            "warning_bytes": warning,
            "max_bytes": maximum,
            "status": rows[0]["status"] if rows else "ok",
        },
        "rows": rows,
    }


def _status(size: int, warning: int, maximum: int) -> str:
    if maximum and size >= maximum:
        return "oversized"
    if warning and size >= warning:
        return "warning"
    return "ok"


def _payload_size(raw: dict[str, Any]) -> int:
    explicit = _int(raw.get("payload_bytes") or raw.get("size_bytes") or raw.get("bytes"))
    if explicit:
        return explicit
    payload = raw.get("payload")
    if isinstance(payload, bytes):
        return len(payload)
    if isinstance(payload, str):
        return len(payload.encode("utf-8"))
    return _int(raw.get("content_length"))


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

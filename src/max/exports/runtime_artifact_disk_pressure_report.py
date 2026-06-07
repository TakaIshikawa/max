"""Runtime artifact disk pressure export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.runtime_artifact_disk_pressure_report.v1"
KIND = "max.runtime_artifact_disk_pressure_report"


def generate_runtime_artifact_disk_pressure_report(records: Iterable[dict[str, Any]], *, max_bytes: int = 1_000_000_000, max_count: int = 1000) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    for raw in records:
        artifact_type = _text(raw.get("artifact_type") or raw.get("type")) or "unknown-artifact"
        row = groups.setdefault(artifact_type, {"artifact_type": artifact_type, "artifact_count": 0, "total_bytes": 0, "oldest_created_at": "", "newest_created_at": ""})
        count = _int(raw.get("artifact_count") or raw.get("count")) or 1
        row["artifact_count"] += count
        row["total_bytes"] += _int(raw.get("total_bytes") or raw.get("bytes") or raw.get("size_bytes"))
        created_at = _text(raw.get("created_at"))
        if created_at:
            row["oldest_created_at"] = min([value for value in [row["oldest_created_at"], created_at] if value]) if row["oldest_created_at"] else created_at
            row["newest_created_at"] = max(row["newest_created_at"], created_at)
    rows = []
    for row in groups.values():
        over_bytes = row["total_bytes"] > max_bytes
        over_count = row["artifact_count"] > max_count
        rows.append({**row, "status": "critical" if over_bytes and over_count else "warning" if over_bytes or over_count else "ok"})
    rows.sort(key=lambda row: ({"critical": 0, "warning": 1, "ok": 2}[row["status"]], row["artifact_type"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"artifact_type_count": len(rows), "warning_count": sum(1 for row in rows if row["status"] == "warning"), "critical_count": sum(1 for row in rows if row["status"] == "critical"), "max_bytes": max_bytes, "max_count": max_count}, "rows": rows}


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

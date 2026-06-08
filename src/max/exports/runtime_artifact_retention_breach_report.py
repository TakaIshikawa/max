"""Runtime artifact retention breach export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.runtime_artifact_retention_breach_report.v1"
KIND = "max.runtime_artifact_retention_breach_report"
_STATUS_ORDER = {"critical": 0, "breach": 1, "healthy": 2}


def generate_runtime_artifact_retention_breach_report(artifacts: Iterable[dict[str, Any]], *, critical_breach_count: int = 3) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"artifact_count": 0, "breach_count": 0, "expired_count": 0, "missing_count": 0, "oversized_count": 0})
    for raw in artifacts:
        if not isinstance(raw, dict):
            continue
        key = (_text(raw.get("artifact_type") or raw.get("artifact_kind") or raw.get("kind")) or "unknown-kind", _text(raw.get("profile") or raw.get("profile_id")) or "default")
        status = _text(raw.get("retention_status") or raw.get("status"))
        groups[key]["artifact_count"] += 1
        if status in {"expired", "missing", "oversized", "breach", "breached"} or raw.get("breach"):
            groups[key]["breach_count"] += 1
        if status == "expired":
            groups[key]["expired_count"] += 1
        if status == "missing":
            groups[key]["missing_count"] += 1
        if status == "oversized":
            groups[key]["oversized_count"] += 1
    rows = []
    for (artifact_type, profile), totals in groups.items():
        breach_count = totals["breach_count"]
        rows.append({"artifact_type": artifact_type, "profile": profile, **totals, "breach_rate": round(breach_count / totals["artifact_count"], 4) if totals["artifact_count"] else 0.0, "status": "critical" if breach_count >= critical_breach_count else ("breach" if breach_count else "healthy")})
    rows.sort(key=lambda row: (_STATUS_ORDER[row["status"]], -row["breach_count"], row["artifact_type"].casefold(), row["profile"].casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": rows[0]["status"] if rows else "healthy", "group_count": len(rows), "artifact_count": sum(row["artifact_count"] for row in rows), "breach_count": sum(row["breach_count"] for row in rows)}, "rows": rows}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().lower().split()) if value is not None else ""

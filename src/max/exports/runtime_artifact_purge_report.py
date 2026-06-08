"""Runtime artifact purge export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.runtime_artifact_purge_report.v1"
KIND = "max.runtime_artifact_purge_report"
_STATUS_ORDER = {"blocked": 0, "pending": 1, "clean": 2}


def generate_runtime_artifact_purge_report(artifacts: Iterable[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"artifact_count": 0, "eligible_count": 0, "retained_count": 0, "purged_count": 0, "blocked_purge_count": 0, "reclaimable_bytes": 0})
    for raw in artifacts:
        if not isinstance(raw, dict):
            continue
        key = (_text(raw.get("artifact_kind") or raw.get("kind") or raw.get("artifact_type")) or "unknown-kind", _text(raw.get("profile") or raw.get("profile_id")) or "default")
        group = groups[key]
        group["artifact_count"] += 1
        status = _text(raw.get("purge_status") or raw.get("status"))
        eligible = bool(raw.get("eligible") or raw.get("purge_eligible") or status in {"eligible", "pending", "purged", "blocked"})
        size = _int(raw.get("bytes") or raw.get("size_bytes") or raw.get("reclaimable_bytes"))
        if eligible:
            group["eligible_count"] += 1
        if status in {"retained", "keep"} or raw.get("retained"):
            group["retained_count"] += 1
        elif status == "purged" or raw.get("purged"):
            group["purged_count"] += 1
        elif status == "blocked" or raw.get("blocked"):
            group["blocked_purge_count"] += 1
        elif eligible:
            group["reclaimable_bytes"] += size
    rows = []
    for (artifact_kind, profile), totals in groups.items():
        rows.append({"artifact_kind": artifact_kind, "profile": profile, **totals, "status": "blocked" if totals["blocked_purge_count"] else ("pending" if totals["reclaimable_bytes"] or totals["eligible_count"] > totals["purged_count"] + totals["retained_count"] + totals["blocked_purge_count"] else "clean")})
    rows.sort(key=lambda row: (_STATUS_ORDER[row["status"]], row["artifact_kind"].casefold(), row["profile"].casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": rows[0]["status"] if rows else "clean", "group_count": len(rows), "eligible_count": sum(row["eligible_count"] for row in rows), "purged_count": sum(row["purged_count"] for row in rows), "blocked_purge_count": sum(row["blocked_purge_count"] for row in rows), "reclaimable_bytes": sum(row["reclaimable_bytes"] for row in rows)}, "rows": rows}


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().lower().split()) if value is not None else ""

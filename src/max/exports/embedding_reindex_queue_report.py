"""Embedding reindex queue export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.embedding_reindex_queue_report.v1"
KIND = "max.embedding_reindex_queue_report"


def generate_embedding_reindex_queue_report(records: Iterable[dict[str, Any]], *, urgent_age_hours: int = 24) -> dict[str, Any]:
    threshold = max(0, int(urgent_age_hours))
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        namespace = _text(raw.get("namespace") or raw.get("index") or raw.get("index_name")) or "default"
        item_type = _text(raw.get("item_type") or raw.get("type") or raw.get("entity_type")) or "unknown"
        group = groups.setdefault((namespace, item_type), {"queued": 0, "blocked": 0, "urgent": 0, "oldest_age": 0, "latest": ""})
        queued = _int(raw.get("queued_count") or raw.get("count") or raw.get("queued_items"))
        if queued == 0:
            queued = 1
        group["queued"] += queued
        blocked = _blocked(raw)
        urgent = _urgent(raw, threshold)
        if blocked:
            group["blocked"] += queued
        elif urgent:
            group["urgent"] += queued
        group["oldest_age"] = max(group["oldest_age"], _int(raw.get("age_hours") or raw.get("queued_age_hours")))
        queued_at = _text(raw.get("submitted_at") or raw.get("enqueued_at") or raw.get("queued_at") or raw.get("created_at"))
        if queued_at > group["latest"]:
            group["latest"] = queued_at

    rows = []
    for (namespace, item_type), group in groups.items():
        status = "blocked" if group["blocked"] else ("urgent" if group["urgent"] or group["oldest_age"] >= threshold else "queued")
        rows.append(
            {
                "namespace": namespace,
                "item_type": item_type,
                "queued_count": group["queued"],
                "blocked_count": group["blocked"],
                "urgent_count": group["urgent"],
                "oldest_age_hours": group["oldest_age"],
                "latest_queued_at": group["latest"] or None,
                "status": status,
            }
        )
    rows.sort(key=lambda row: ({"blocked": 0, "urgent": 1, "queued": 2}[row["status"]], row["namespace"].casefold(), row["item_type"].casefold()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "row_count": len(rows),
            "queued_count": sum(row["queued_count"] for row in rows),
            "blocked_count": sum(row["blocked_count"] for row in rows),
            "urgent_count": sum(row["urgent_count"] for row in rows),
            "urgent_age_hours": threshold,
        },
        "rows": rows,
    }


def _blocked(raw: dict[str, Any]) -> bool:
    if raw.get("blocked") is not None:
        return _bool(raw.get("blocked"))
    return bool(_text(raw.get("blocked_reason") or raw.get("blocker"))) or _items(raw.get("blocked_reasons") or raw.get("blockers")) > 0


def _urgent(raw: dict[str, Any], threshold: int) -> bool:
    priority = _text(raw.get("priority")).lower()
    return priority in {"urgent", "high"} or _int(raw.get("age_hours") or raw.get("queued_age_hours")) >= threshold


def _items(value: Any) -> int:
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, list | tuple | set):
        return len(value)
    return 0


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "blocked"}


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

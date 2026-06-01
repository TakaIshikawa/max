"""JSON API renderer for source adapter schema migration status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, parse_datetime, source_metadata, strings

SCHEMA_VERSION = "max.api.source_adapter_schema_migration_status.v1"
KIND = "max.api.source_adapter_schema_migration_status"
RANK = {"failed": 0, "blocked": 1, "rollback_required": 2, "pending": 3, "current": 4}


def source_adapter_schema_migration_status_to_json(payload: Mapping[str, Any], *, as_of: datetime | str | None = None) -> str:
    checked_at = parse_datetime(as_of) or parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    target = _text(payload.get("target_schema_version") or payload.get("current_schema_version") or payload.get("target_version"))
    rows = [_adapter(row, i, target) for i, row in enumerate(list_of_maps(payload.get("adapters") or payload.get("items") or payload.get("rows")), start=1)]
    rows = sorted(rows, key=lambda row: (RANK[row["status"]], row["adapter"].casefold()))
    counts = {name + "_count": sum(1 for row in rows if row["status"] == name) for name in RANK}
    required_bad = any(row["required"] and row["status"] in {"failed", "blocked"} for row in rows)
    status = "critical" if required_bad else ("warning" if any(counts[key] for key in ("failed_count", "blocked_count", "rollback_required_count", "pending_count")) else "healthy")
    migrated = sum(1 for row in rows if row["status"] == "current")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "as_of": _stamp(checked_at), "status": status, "summary": {"adapter_count": len(rows), "migration_percent": round((migrated / len(rows)) * 100, 2) if rows else 100.0, **counts}, "target_schema_version": target or None, "affected_adapters": [row for row in rows if row["status"] != "current"], "adapters": rows, "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _adapter(item: Mapping[str, Any], index: int, target: str) -> dict[str, Any]:
    explicit = _text(item.get("status") or item.get("migration_state")).casefold()
    current = _text(item.get("schema_version") or item.get("current_schema_version") or item.get("version"))
    blockers = strings(item.get("blockers"))
    failed = explicit == "failed" or bool(item.get("migration_failed"))
    blocked = explicit == "blocked" or bool(blockers)
    rollback = explicit == "rollback_required" or bool(item.get("rollback_required"))
    pending = explicit in {"pending", "pending_cutover"} or bool(item.get("pending_cutover")) or bool(target and current and current != target)
    status = "failed" if failed else ("blocked" if blocked else ("rollback_required" if rollback else ("pending" if pending else "current")))
    return {"adapter": _text(item.get("adapter") or item.get("adapter_id") or item.get("source")) or f"adapter-{index}", "source": _text(item.get("source")) or None, "current_schema_version": current or "unknown", "target_schema_version": _text(item.get("target_schema_version")) or target or None, "required": bool(item.get("required", True)), "blockers": blockers, "rollback_ready": bool(item.get("rollback_ready")), "migration_percent": max(0, min(100, int_or_zero(item.get("migration_percent") or (100 if status == "current" else 0)))), "status": status, "next_actions": _actions(status)}


def _actions(status: str) -> list[str]:
    return {"failed": ["inspect failed migration and rerun"], "blocked": ["clear migration blockers"], "rollback_required": ["validate rollback plan and restore prior schema"], "pending": ["complete schema migration cutover"], "current": ["continue monitoring"]}[status]


def _stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

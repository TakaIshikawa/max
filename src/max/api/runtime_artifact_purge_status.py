"""JSON API renderer for runtime artifact purge status."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.runtime_artifact_purge_status.v1"
KIND = "max.api.runtime_artifact_purge_status"


def runtime_artifact_purge_status_to_json(payload: Mapping[str, Any]) -> str:
    as_of = parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    rows = [_artifact(row, i, as_of) for i, row in enumerate(list_of_maps(payload.get("artifacts") or payload.get("purges") or payload.get("rows")), start=1)]
    expired = [row for row in rows if row["expired"]]
    failed = [row for row in rows if row["purge_state"] == "failed"]
    overdue = [row for row in rows if row["overdue"]]
    status = "critical" if failed else ("warning" if overdue else "healthy")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"artifact_count": len(rows), "expired_count": len(expired), "purge_failed_count": len(failed), "overdue_purge_count": len(overdue), "status": status}, "artifacts": rows, "overdue_artifacts": _group(overdue), "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _artifact(item: Mapping[str, Any], index: int, as_of: datetime) -> dict[str, Any]:
    retention = int_or_zero(item.get("retention_days") or 30)
    age = int_or_zero(item.get("age_days"))
    expires_at = parse_datetime(item.get("expires_at"))
    expired = (expires_at is not None and expires_at <= as_of) or (age > retention)
    state = _text(item.get("purge_state") or item.get("status") or ("pending" if expired else "retained")).casefold()
    overdue = expired and state in {"pending", "failed", "queued"}
    return {"artifact_id": _text(item.get("artifact_id") or item.get("id")) or f"artifact-{index}", "artifact_type": _text(item.get("artifact_type") or item.get("type")) or "unknown", "retention_days": retention, "age_days": age, "expires_at": item.get("expires_at"), "expired": expired, "purge_state": state, "overdue": overdue}


def _group(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["artifact_type"]].append(row)
    return [{"artifact_type": key, "overdue_count": len(items), "artifacts": sorted(items, key=lambda row: row["artifact_id"])} for key, items in sorted(grouped.items())]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

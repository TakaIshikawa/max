"""JSON API renderer for retention policy exception status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import datetime_to_string, int_or_zero, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.retention_policy_exception_status.v1"
KIND = "max.api.retention_policy_exception_status"
STATUS_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def retention_policy_exception_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    now = parse_datetime(as_of) if isinstance(as_of, str) else (as_of if isinstance(as_of, datetime) else None)
    exceptions = _exceptions(payload, now)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(exceptions), "exceptions": exceptions, "status_totals": _status_totals(exceptions), "metadata": source_metadata(payload, as_of=datetime_to_string(now) if isinstance(now, datetime) else as_of, exception_count=len(exceptions))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _exceptions(payload: Mapping[str, Any], as_of: datetime | None) -> list[dict[str, Any]]:
    source = payload.get("exceptions") if isinstance(payload.get("exceptions"), list) else payload.get("retention_exceptions")
    rows = [_exception(item, index, as_of) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["days_overdue"], row["artifact_type"], row["artifact_id"]))


def _exception(item: Mapping[str, Any], index: int, as_of: datetime | None) -> dict[str, Any]:
    approved_by = _text(item.get("approved_by") or item.get("approver"))
    days_overdue = max(0, int_or_zero(item.get("days_overdue"))) if item.get("days_overdue") is not None else _days_overdue(item.get("expires_at"), as_of)
    blockers = [] if approved_by else ["missing_approval"]
    status = _status(item.get("status"), days_overdue, blockers)
    return {"artifact_type": _text(item.get("artifact_type")) or "unknown-artifact", "artifact_id": _text(item.get("artifact_id") or item.get("id")) or f"artifact-{index}", "policy_id": _text(item.get("policy_id")) or "unknown-policy", "expires_at": datetime_to_string(parse_datetime(item.get("expires_at"))), "approved_by": approved_by or None, "reason": _text(item.get("reason")) or None, "days_overdue": days_overdue, "blockers": blockers, "status": status}


def _days_overdue(value: Any, as_of: datetime | None) -> int:
    expires = parse_datetime(value)
    if expires is None or as_of is None:
        return 0
    current = as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)
    return max((current.astimezone(timezone.utc) - expires).days, 0)


def _status(value: Any, days_overdue: int, blockers: list[str]) -> str:
    explicit = _bucket(value, "")
    if explicit in STATUS_RANK:
        return explicit
    if days_overdue >= 30:
        return "critical"
    if days_overdue > 0 or blockers:
        return "high"
    return "low"


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    return {"status": "critical" if counts["critical"] else ("high" if counts["high"] else ("medium" if counts["medium"] else "low")), "exception_count": len(rows), "expired_count": sum(1 for row in rows if row["days_overdue"] > 0), "missing_approval_count": sum(1 for row in rows if "missing_approval" in row["blockers"])}


def _status_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["status"] for row in rows)
    return [{"status": status, "exception_count": counts[status]} for status in ("critical", "high", "medium", "low")]


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

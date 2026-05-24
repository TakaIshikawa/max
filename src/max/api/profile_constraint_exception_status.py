"""JSON API renderer for profile constraint exception status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.profile_constraint_exception_status.v1"
KIND = "max.api.profile_constraint_exception_status"
STATUS_RANK = {"expired": 0, "pending_review": 1, "active": 2}


def profile_constraint_exception_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    exceptions = _exceptions(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(exceptions),
        "exceptions": exceptions,
        "profile_totals": _totals(exceptions, "profile"),
        "severity_totals": _totals(exceptions, "severity"),
        "review_required": [row for row in exceptions if row["review_required"]],
        "metadata": _metadata(payload, exceptions, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _exceptions(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("exceptions") if isinstance(payload.get("exceptions"), list) else payload.get("constraint_exceptions")
    rows = [_exception(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["profile"], row["constraint"], row["exception_id"]))
    return rows


def _exception(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    raw_status = _text(item.get("status")).lower().replace("-", "_")
    expires_at = item.get("expires_at") or item.get("expiration_at")
    review_required = _bool(item.get("review_required", item.get("pending_review")))
    status = raw_status if raw_status in STATUS_RANK else ("pending_review" if review_required else "active")
    return {
        "exception_id": _text(item.get("exception_id") or item.get("id")) or f"exception-{index}",
        "profile": _text(item.get("profile")) or "unknown-profile",
        "constraint": _text(item.get("constraint")) or "unknown-constraint",
        "status": status,
        "expires_at": expires_at,
        "owner": _text(item.get("owner")) or "unassigned",
        "reason": _text(item.get("reason")),
        "severity": _text(item.get("severity")).lower() or "medium",
        "review_required": review_required or status in {"expired", "pending_review"},
    }


def _summary(exceptions: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in exceptions)
    return {"exception_count": len(exceptions), "active_count": counts["active"], "expired_count": counts["expired"], "pending_review_count": counts["pending_review"], "review_required_count": sum(1 for row in exceptions if row["review_required"])}


def _totals(exceptions: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in exceptions:
        grouped[row[field]].append(row)
    return [{field: key, "exception_count": len(items), "review_required_count": sum(1 for item in items if item["review_required"])} for key, items in sorted(grouped.items())]


def _metadata(payload: Mapping[str, Any], exceptions: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "exception_count": len(exceptions)}


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pending_review"}
    return bool(value)


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

"""JSON API renderer for signal quarantine status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.signal_quarantine_status.v1"
KIND = "max.api.signal_quarantine_status"
STATUS_RANK = {"expired": 0, "escalated": 1, "pending_review": 2, "releasable": 3}


def signal_quarantine_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    signals = _signals(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(signals),
        "signals": signals,
        "escalated_signals": [row for row in signals if row["status"] in {"escalated", "expired"}],
        "reason_totals": _totals(signals, "reason"),
        "source_totals": _totals(signals, "source"),
        "metadata": _metadata(payload, signals, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _signals(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("quarantine") if isinstance(payload.get("quarantine"), list) else payload.get("signals")
    rows = [_signal(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["source"], row["signal_id"]))
    return rows


def _signal(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    severity = _severity(item.get("severity"))
    age_hours = _int(item.get("age_hours", item.get("age")))
    release_eligible = _bool(item.get("release_eligible", item.get("eligible")))
    status = _status(severity, age_hours, release_eligible)
    return {
        "signal_id": _text(item.get("signal_id") or item.get("id")) or f"signal-{index}",
        "source": _text(item.get("source")) or "unknown-source",
        "reason": _text(item.get("reason")) or "unspecified",
        "severity": severity,
        "age_hours": age_hours,
        "reviewer": _text(item.get("reviewer")) or "unassigned",
        "release_eligible": release_eligible,
        "status": status,
    }


def _status(severity: str, age_hours: int, release_eligible: bool) -> str:
    if age_hours >= 168:
        return "expired"
    if severity in {"critical", "high"} or age_hours >= 72:
        return "escalated"
    if release_eligible:
        return "releasable"
    return "pending_review"


def _summary(signals: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in signals)
    return {"signal_count": len(signals), "pending_review_count": counts["pending_review"], "releasable_count": counts["releasable"], "escalated_count": counts["escalated"], "expired_count": counts["expired"]}


def _totals(signals: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in signals:
        grouped[row[field]].append(row)
    return [{field: key, "signal_count": len(items), "escalated_count": sum(1 for item in items if item["status"] in {"escalated", "expired"})} for key, items in sorted(grouped.items())]


def _metadata(payload: Mapping[str, Any], signals: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "signal_count": len(signals)}


def _severity(value: Any) -> str:
    text = _text(value).lower()
    return text if text in {"critical", "high", "medium", "low"} else "medium"


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

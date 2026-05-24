"""JSON API renderer for profile drift alert status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.profile_drift_alert_status.v1"
KIND = "max.api.profile_drift_alert_status"
STATUS_RANK = {"alerting": 0, "watch": 1, "normal": 2, "acknowledged": 3}


def profile_drift_alert_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    alerts = _alerts(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(alerts),
        "alerts": alerts,
        "active_alerts": [row for row in alerts if row["status"] in {"alerting", "watch"}],
        "owner_totals": _totals(alerts, "owner"),
        "profile_totals": _totals(alerts, "profile"),
        "metadata": _metadata(payload, alerts, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _alerts(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("alerts") if isinstance(payload.get("alerts"), list) else payload.get("profile_drift")
    rows = [_alert(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["profile"], row["field"]))
    return rows


def _alert(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    drift_score = _float(item.get("drift_score", item.get("score")))
    threshold = _float(item.get("threshold", 1))
    acknowledged = _bool(item.get("acknowledged"))
    status = "acknowledged" if acknowledged else ("alerting" if threshold and drift_score >= threshold else ("watch" if threshold and drift_score >= threshold * 0.75 else "normal"))
    return {
        "profile": _text(item.get("profile")) or "unknown-profile",
        "field": _text(item.get("field")) or f"field-{index}",
        "baseline_value": _text(item.get("baseline_value", item.get("baseline"))),
        "observed_value": _text(item.get("observed_value", item.get("observed"))),
        "drift_score": drift_score,
        "threshold": threshold,
        "owner": _text(item.get("owner")) or "unknown-owner",
        "acknowledged": acknowledged,
        "status": status,
    }


def _summary(alerts: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in alerts)
    return {"alert_count": len(alerts), "normal_count": counts["normal"], "watch_count": counts["watch"], "alerting_count": counts["alerting"], "acknowledged_count": counts["acknowledged"]}


def _totals(alerts: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in alerts:
        grouped[row[field]].append(row)
    return [{field: key, "alert_count": len(items), "active_count": sum(1 for item in items if item["status"] in {"alerting", "watch"})} for key, items in sorted(grouped.items())]


def _metadata(payload: Mapping[str, Any], alerts: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "alert_count": len(alerts)}


def _float(value: Any) -> float:
    try:
        return round(max(0.0, float(value or 0)), 4)
    except (TypeError, ValueError):
        return 0.0


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

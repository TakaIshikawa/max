"""Publisher destination quota export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.publisher_destination_quota_report.v1"
KIND = "max.publisher_destination_quota_report"


def generate_publisher_destination_quota_report(records: Iterable[dict[str, Any]], *, quota_risk_threshold: float = 0.8) -> dict[str, Any]:
    threshold = _ratio(quota_risk_threshold)
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        provider = _text(raw.get("provider") or raw.get("publisher")) or "unknown-provider"
        destination = _text(raw.get("destination") or raw.get("channel") or raw.get("target")) or "unknown-destination"
        group = groups.setdefault((provider, destination), {"attempted": 0, "accepted": 0, "blocked": 0, "limit": None, "latest": ""})
        group["attempted"] += _int(raw.get("attempted_count") or raw.get("attempts"))
        group["accepted"] += _int(raw.get("accepted_count") or raw.get("accepted"))
        group["blocked"] += _int(raw.get("quota_blocked_count") or raw.get("rejected_count") or raw.get("blocked"))
        if not raw.get("attempted_count") and not raw.get("attempts"):
            group["attempted"] += 1
            outcome = _text(raw.get("outcome") or raw.get("status") or raw.get("result")).lower()
            if outcome in {"accepted", "sent", "success", "published"}:
                group["accepted"] += 1
            elif outcome in {"quota_blocked", "quota-blocked", "rate_limited", "rejected", "blocked"}:
                group["blocked"] += 1
        limit = _optional_int(raw.get("quota_limit") or raw.get("limit"))
        if limit is not None:
            group["limit"] = limit if group["limit"] is None else max(group["limit"], limit)
        event_at = _text(raw.get("event_at") or raw.get("created_at") or raw.get("timestamp"))
        if event_at > group["latest"]:
            group["latest"] = event_at
    rows = []
    for (provider, destination), group in groups.items():
        utilization = round(group["attempted"] / group["limit"], 4) if group["limit"] else None
        rows.append({"provider": provider, "destination": destination, "attempted_count": group["attempted"], "accepted_count": group["accepted"], "quota_blocked_count": group["blocked"], "quota_limit": group["limit"], "quota_utilization": utilization, "latest_event_at": group["latest"] or None, "status": "quota_risk" if utilization is not None and utilization >= threshold else "ok"})
    rows.sort(key=lambda row: (row["provider"].lower(), row["destination"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"row_count": len(rows), "quota_risk_count": sum(1 for row in rows if row["status"] == "quota_risk"), "quota_risk_threshold": threshold}, "rows": rows}


def _ratio(value: Any) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.8


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return _int(value)


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

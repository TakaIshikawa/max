"""JSON API renderer for signal payload redaction status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata, strings

SCHEMA_VERSION = "max.api.signal_payload_redaction_status.v1"
KIND = "max.api.signal_payload_redaction_status"
RANK = {"critical": 0, "warning": 1, "healthy": 2}


def signal_payload_redaction_status_to_json(payload: Mapping[str, Any]) -> str:
    current_policy = _text(payload.get("current_policy_version") or payload.get("policy_version") or "current")
    signals = [_signal(row, i, current_policy) for i, row in enumerate(list_of_maps(payload.get("signals") or payload.get("rows")), start=1)]
    status = "critical" if any(row["status"] == "critical" for row in signals) else ("warning" if any(row["status"] == "warning" for row in signals) else "healthy")
    redacted = sum(1 for row in signals if row["redacted"])
    coverage = round(redacted / len(signals), 4) if signals else 1.0
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "overall_status": status, "current_policy_version": current_policy, "total_signals": len(signals), "redacted_signal_count": redacted, "redaction_coverage": coverage, "failed_redaction_count": sum(row["failed_redaction_count"] for row in signals), "policy_drift_count": sum(1 for row in signals if row["policy_drift"]), "quarantine_recommendations": sorted([row for row in signals if row["quarantine_recommended"]], key=lambda row: row["signal_id"].casefold()), "signals": sorted(signals, key=lambda row: (RANK[row["status"]], row["signal_id"].casefold())), "recommended_action": _action(signals), "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _signal(item: Mapping[str, Any], index: int, current_policy: str) -> dict[str, Any]:
    fields = strings(item.get("unredacted_sensitive_fields") or item.get("sensitive_fields"))
    failed = int_or_zero(item.get("failed_redaction_count") or item.get("failure_count"))
    policy = _text(item.get("policy_version") or item.get("redaction_policy_version") or current_policy)
    drift = policy != current_policy
    redacted = bool(item.get("redacted", not fields and failed == 0))
    status = "critical" if fields else ("warning" if failed or drift or not redacted else "healthy")
    return {"signal_id": _text(item.get("signal_id") or item.get("id")) or f"signal-{index}", "source": _text(item.get("source")) or "unknown", "redacted": redacted, "policy_version": policy, "policy_drift": drift, "unredacted_sensitive_fields": fields, "failed_redaction_count": failed, "quarantine_recommended": bool(fields or failed), "status": status, "recommended_action": "quarantine signal and redact sensitive fields" if fields else ("retry failed redaction" if failed else ("update redaction policy version" if drift else "continue monitoring"))}


def _action(signals: list[Mapping[str, Any]]) -> str:
    if any(row["unredacted_sensitive_fields"] for row in signals):
        return "quarantine signals with unredacted sensitive fields"
    if any(row["failed_redaction_count"] for row in signals):
        return "retry failed redaction attempts"
    if any(row["policy_drift"] for row in signals):
        return "update stale redaction policy versions"
    return "continue monitoring"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

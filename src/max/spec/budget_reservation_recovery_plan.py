"""Generate deterministic budget reservation recovery plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, number, summary

SCHEMA_VERSION = "max.spec.budget_reservation_recovery_plan.v1"
KIND = "max.spec.budget_reservation_recovery_plan"


def generate_budget_reservation_recovery_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    reservations = _reservations(hints.get("reservations") or spec.get("reservations"))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, reservation_count=len(reservations), recovery_count=sum(1 for item in reservations if item["status"] != "healthy"), data_quality_risk_count=sum(len(item["data_quality_risks"]) for item in reservations)),
        "reservation_inventory": reservations,
        "recovery_actions": _recovery_actions(reservations),
        "guardrail_validation": _guardrail_validation(),
        "evidence_references": ctx["evidence_references"],
    }


def _reservations(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value if isinstance(value, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        reserved = _field_number(item, "reserved", "reserved_budget")
        used = _field_number(item, "used", "used_budget")
        limit = _field_number(item, "limit", "budget_limit", "available")
        risks = _risks(reserved, used, limit)
        reserved_value = float(reserved or 0.0)
        used_value = float(used or 0.0)
        limit_value = float(limit or 0.0)
        rows.append(
            {
                "id": compact(item.get("id") or item.get("reservation_id")) or f"BRR{index}",
                "stage": compact(item.get("stage")) or "unspecified",
                "profile": compact(item.get("profile")) or "default",
                "reserved": reserved_value,
                "used": used_value,
                "limit": limit_value,
                "utilization": round(used_value / reserved_value, 4) if reserved_value > 0 else 0.0,
                "status": _status(reserved_value, used_value, limit_value, risks),
                "data_quality_risks": risks,
            }
        )
    return sorted(rows, key=lambda row: (_status_rank(row["status"]), row["stage"].casefold(), row["profile"].casefold(), row["id"].casefold()))


def _recovery_actions(reservations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for item in reservations:
        if item["status"] == "healthy":
            continue
        if item["status"] == "over_reserved":
            action = "Release excess reserved budget to the shared pool and rebalance stage allocation."
        elif item["status"] == "exhausted":
            action = "Pause new work for the stage, release stale holds, and request approved replenishment."
        elif item["status"] == "near_exhausted":
            action = "Throttle stage intake and rebalance budget from lower-utilization reservations."
        else:
            action = "Correct missing or invalid budget fields before recovery decisions."
        actions.append({"id": f"BRA{len(actions) + 1}", "reservation_id": item["id"], "stage": item["stage"], "status": item["status"], "action": action})
    return actions


def _guardrail_validation() -> list[dict[str, str]]:
    return [
        {"id": "BRV1", "name": "released_budget_matches_pool_delta", "target": "released reservations increase shared pool by the same amount"},
        {"id": "BRV2", "name": "stage_budget_non_negative", "target": "no stage has negative reserved, used, or limit fields"},
        {"id": "BRV3", "name": "post_rebalance_utilization", "target": "recovered reservations return below exhaustion threshold"},
    ]


def _risks(reserved: float | None, used: float | None, limit: float | None) -> list[str]:
    risks: list[str] = []
    for name, value in (("reserved", reserved), ("used", used), ("limit", limit)):
        if value is None:
            risks.append(f"missing_{name}")
        elif value < 0:
            risks.append(f"negative_{name}")
    return risks


def _field_number(item: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in item:
            return number(item.get(key))
    return None


def _status(reserved: float, used: float, limit: float, risks: list[str]) -> str:
    if risks:
        return "data_quality_risk"
    if reserved > limit and limit > 0:
        return "over_reserved"
    if reserved <= 0 or used >= reserved:
        return "exhausted"
    if used / reserved >= 0.85:
        return "near_exhausted"
    return "healthy"


def _status_rank(value: str) -> int:
    return {"data_quality_risk": 0, "over_reserved": 1, "exhausted": 2, "near_exhausted": 3, "healthy": 4}.get(value, 5)


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("budget_reservation_recovery")
    return hints if isinstance(hints, dict) else {}

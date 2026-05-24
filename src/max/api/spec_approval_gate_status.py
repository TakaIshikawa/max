"""JSON API renderer for spec approval gate status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.spec_approval_gate_status.v1"
KIND = "max.api.spec_approval_gate_status"
STATE_RANK = {"blocked": 0, "warn": 1, "passed": 2}


def spec_approval_gate_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    now = _date(as_of) or _date(payload.get("as_of")) or datetime.now(timezone.utc)
    max_age_days = _int(payload.get("max_approval_age_days", payload.get("stale_after_days", 14)))
    gates = _gates(payload, now, max_age_days)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(gates),
        "gates": gates,
        "blocking_gates": [row for row in gates if row["state"] == "blocked"],
        "stale_approvals": [row for row in gates if row["stale"]],
        "owner_queues": _owner_queues(gates),
        "next_actions": _actions(gates),
        "metadata": _metadata(payload, gates, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _gates(payload: Mapping[str, Any], now: datetime, max_age_days: int) -> list[dict[str, Any]]:
    source = payload.get("gates") if isinstance(payload.get("gates"), list) else payload.get("approvals")
    rows = [_gate(item, index, now, max_age_days) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATE_RANK[row["state"]], row["owner"], row["gate"]))
    return rows


def _gate(item: Mapping[str, Any], index: int, now: datetime, max_age_days: int) -> dict[str, Any]:
    raw_state = _text(item.get("state") or item.get("status") or item.get("approved"))
    state = _state(raw_state)
    approved_at = _date(item.get("approved_at") or item.get("approval_timestamp"))
    age_days = (now - approved_at).days if approved_at else None
    stale = bool(state == "passed" and age_days is not None and age_days > max_age_days)
    if stale:
        state = "warn"
    return {
        "gate": _text(item.get("gate") or item.get("name")) or f"gate-{index}",
        "owner": _text(item.get("owner") or item.get("approver")) or "unassigned",
        "state": state,
        "reason": _text(item.get("reason") or item.get("blocking_reason")),
        "remediation_action": _text(item.get("remediation_action") or item.get("action")),
        "approved_at": approved_at.isoformat().replace("+00:00", "Z") if approved_at else None,
        "approval_age_days": age_days,
        "stale": stale,
    }


def _summary(gates: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["state"] for row in gates)
    overall = "ready"
    if counts["blocked"]:
        overall = "blocked"
    elif counts["warn"]:
        overall = "warning"
    return {"gate_count": len(gates), "overall_status": overall, "passed_count": counts["passed"], "blocked_count": counts["blocked"], "warn_count": counts["warn"]}


def _owner_queues(gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in gates:
        if row["state"] != "passed":
            grouped[row["owner"]].append(row)
    rows = [{"owner": owner, "gate_count": len(items), "gates": [item["gate"] for item in sorted(items, key=lambda row: row["gate"])]} for owner, items in grouped.items()]
    rows.sort(key=lambda row: row["owner"])
    return rows


def _actions(gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in gates:
        if row["state"] == "blocked":
            rows.append({"gate": row["gate"], "owner": row["owner"], "action": row["remediation_action"] or "Resolve blocking approval reason", "reason": row["reason"]})
        elif row["stale"]:
            rows.append({"gate": row["gate"], "owner": row["owner"], "action": "Refresh stale approval", "approval_age_days": row["approval_age_days"]})
    return rows


def _metadata(payload: Mapping[str, Any], gates: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "gate_count": len(gates)}


def _state(value: str) -> str:
    lowered = value.lower()
    if lowered in {"blocked", "block", "failed", "rejected", "false", "no"}:
        return "blocked"
    if lowered in {"warn", "warning", "pending", "needs_review"}:
        return "warn"
    return "passed"


def _date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

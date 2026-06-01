"""JSON API renderer for publication approval delegation status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.publication_approval_delegation_status.v1"
KIND = "max.api.publication_approval_delegation_status"
RANK = {"critical": 0, "warning": 1, "healthy": 2}


def publication_approval_delegation_status_to_json(payload: Mapping[str, Any]) -> str:
    as_of = parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    rows = [_publication(row, i, as_of) for i, row in enumerate(list_of_maps(payload.get("publications") or payload.get("rows")), start=1)]
    status = "critical" if any(row["status"] == "critical" for row in rows) else ("warning" if any(row["status"] == "warning" for row in rows) else "healthy")
    affected = [row for row in rows if row["status"] != "healthy"]
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "overall_status": status, "total_publications": len(rows), "blocked_publication_count": sum(row["blocked_publication_count"] for row in rows), "missing_delegate_count": sum(1 for row in rows if row["missing_delegate"]), "expired_delegate_count": sum(1 for row in rows if row["expired_delegate_window"]), "escalation_required_destinations": sorted({row["destination"] for row in rows if row["escalation_required"]}), "affected_publications": sorted(affected, key=lambda row: (RANK[row["status"]], row["destination"].casefold(), row["publication_id"].casefold())), "recommended_actions": _actions(rows), "publications": rows, "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _publication(item: Mapping[str, Any], index: int, as_of: datetime) -> dict[str, Any]:
    delegate = _text(item.get("delegate") or item.get("delegate_user") or item.get("delegated_approver"))
    expires = parse_datetime(item.get("delegate_expires_at") or item.get("expires_at"))
    blocked = int_or_zero(item.get("blocked_publication_count") or item.get("blocked_count") or (1 if item.get("blocked") else 0))
    missing = not delegate
    expired = bool(expires and expires < as_of)
    approver_blocked = bool(item.get("blocked_approver") or item.get("approver_blocked"))
    escalation = missing or expired or approver_blocked or blocked > 0
    status = "critical" if blocked > 0 and escalation else ("warning" if escalation else "healthy")
    return {"publication_id": _text(item.get("publication_id") or item.get("id")) or f"publication-{index}", "destination": _text(item.get("destination")) or "default", "delegate": delegate, "delegate_expires_at": item.get("delegate_expires_at") or item.get("expires_at"), "missing_delegate": missing, "expired_delegate_window": expired, "blocked_approver": approver_blocked, "blocked_publication_count": blocked, "escalation_required": escalation, "status": status, "recommended_action": "escalate blocked publication approval" if status == "critical" else ("refresh delegation coverage" if escalation else "continue monitoring")}


def _actions(rows: list[Mapping[str, Any]]) -> list[str]:
    actions = []
    if any(row["missing_delegate"] for row in rows):
        actions.append("assign missing publication delegates")
    if any(row["expired_delegate_window"] for row in rows):
        actions.append("renew expired delegation windows")
    if any(row["blocked_approver"] or row["blocked_publication_count"] for row in rows):
        actions.append("escalate blocked publication approvals")
    return actions or ["continue monitoring"]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

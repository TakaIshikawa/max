"""License utilization drift export report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.license_utilization_drift_report.v1"
KIND = "max.license_utilization_drift_report"

_ORDER = {"over_allocated": 0, "under_used": 1, "balanced": 2}


def build_license_utilization_drift_report_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_ORDER[row["drift_status"]], -abs(row["drift_seats"]), row["account"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "license_utilization_drift_report", "domain_filter": domain},
        "summary": _summary(rows),
        "account_rows": rows,
        "follow_up_actions": _actions(rows),
    }


def render_license_utilization_drift_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_license_utilization_drift_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# License Utilization Drift Report", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Account Drift", ""]
    if report.get("account_rows"):
        lines.extend(["| Account | Segment | Purchased | Assigned | Active | Drift | Status | Action |", "|---------|---------|-----------|----------|--------|-------|--------|--------|"])
        for row in report["account_rows"]:
            lines.append(f"| {_md(row['account'])} | {_md(row['segment'])} | {row['purchased_seats']} | {row['assigned_seats']} | {row['active_users']} | {row['drift_percentage']}% | {row['drift_status']} | {_md(row['recommended_action'])} |")
    else:
        lines.append("- No license utilization records found.")
    return "\n".join(lines).rstrip() + "\n"


def _row(unit: Any) -> dict[str, Any]:
    m = _metadata(unit)
    purchased = _int(m.get("purchased_seats") or m.get("licensed_seats"))
    assigned = _int(m.get("assigned_seats"))
    active = _int(m.get("active_users") or m.get("active_seats"))
    drift = assigned - active
    utilization = round((active / purchased) * 100, 1) if purchased else 0.0
    drift_pct = round((drift / purchased) * 100, 1) if purchased else 0.0
    status = "over_allocated" if purchased and assigned > purchased else ("under_used" if purchased and utilization < 50 else "balanced")
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "account": _text(m.get("account") or getattr(unit, "title", "Untitled")),
        "segment": _text(m.get("segment") or "unsegmented"),
        "purchased_seats": purchased,
        "assigned_seats": assigned,
        "active_users": active,
        "utilization_percentage": utilization,
        "drift_seats": drift,
        "drift_percentage": drift_pct,
        "drift_status": status,
        "recommended_action": _action(status),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "account_count": len(rows),
        "total_purchased_seats": sum(row["purchased_seats"] for row in rows),
        "total_assigned_seats": sum(row["assigned_seats"] for row in rows),
        "total_active_users": sum(row["active_users"] for row in rows),
        "status_counts": {status: sum(1 for row in rows if row["drift_status"] == status) for status in ("over_allocated", "under_used", "balanced")},
    }


def _actions(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Collect purchased, assigned, and active-user counts for each account."]
    actions = []
    if any(row["drift_status"] == "over_allocated" for row in rows):
        actions.append("Reconcile accounts with assigned seats above purchased entitlement.")
    if any(row["drift_status"] == "under_used" for row in rows):
        actions.append("Review under-used licenses for adoption outreach or renewal right-sizing.")
    return actions or ["Maintain current utilization monitoring cadence."]


def _action(status: str) -> str:
    return {"over_allocated": "Reduce assignments or expand contract entitlement.", "under_used": "Run adoption follow-up before renewal.", "balanced": "No follow-up required."}[status]


def _metadata(unit: Any) -> dict[str, Any]:
    return getattr(unit, "metadata", None) if isinstance(getattr(unit, "metadata", None), dict) else {}


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")

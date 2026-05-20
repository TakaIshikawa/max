"""Generate deterministic runbook freshness audit plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-runbook-freshness-audit-plan/v1"
KIND = "max.spec.runbook_freshness_audit_plan"
CRITICALITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def generate_runbook_freshness_audit_plan(spec_like: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    cadence = _audit_cadence(spec)
    rows = _runbook_rows(spec, cadence)
    overdue = [row for row in rows if row["status"] == "overdue"]
    actions = _update_actions(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "runbook_count": len(rows),
            "overdue_count": len(overdue),
            "critical_overdue_count": sum(1 for row in overdue if row["criticality"] == "critical"),
            "missing_owner_count": sum(1 for row in rows if row["owner"] == "runbook_owner"),
        },
        "runbook_rows": rows,
        "overdue_reviews": overdue,
        "update_actions": actions,
        "audit_cadence": cadence,
    }


def render_runbook_freshness_audit_plan_markdown(plan_or_spec: dict[str, Any] | None = None) -> str:
    plan = plan_or_spec if _is_plan(plan_or_spec) else generate_runbook_freshness_audit_plan(plan_or_spec)
    lines = ["# Runbook Freshness Audit Plan", "", f"Schema version: {plan['schema_version']}", "", "## Runbook Inventory", ""]
    for row in plan["runbook_rows"]:
        lines.append(f"- {row['id']}: {row['runbook']} owner={row['owner']} last_reviewed={row['last_reviewed']} status={row['status']} criticality={row['criticality']}")
    lines.extend(["", "## Overdue Reviews", ""])
    if plan["overdue_reviews"]:
        for row in plan["overdue_reviews"]:
            lines.append(f"- {row['id']}: {row['runbook']} due for review")
    else:
        lines.append("- No overdue reviews identified.")
    lines.extend(["", "## Update Actions", ""])
    for action in plan["update_actions"]:
        lines.append(f"- {action['runbook_id']}: {action['action']} owner={action['owner']}")
    cadence = plan["audit_cadence"]
    lines.extend(["", "## Audit Cadence", "", f"- Cadence days: {cadence['cadence_days']}", f"- Anchor date: {cadence['anchor_date']}", f"- Reviewer: {cadence['reviewer']}"])
    return "\n".join(lines).rstrip() + "\n"


def _runbook_rows(spec: dict[str, Any], cadence: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for index, raw in enumerate(_raw_runbooks(spec), start=1):
        last_reviewed = _text(raw.get("last_reviewed") or raw.get("reviewed_at")) or "review-date-required"
        criticality = _choice(raw.get("service_criticality") or raw.get("criticality"), set(CRITICALITY_ORDER), "medium")
        rows.append({"id": "", "runbook": _text(raw.get("runbook") or raw.get("name") or raw.get("title")) or f"runbook-{index}", "owner": _text(raw.get("owner")) or "runbook_owner", "last_reviewed": last_reviewed, "criticality": criticality, "incident_references": _values(raw.get("incident_references") or raw.get("incidents"), []), "status": "overdue" if _is_overdue(last_reviewed, cadence["anchor_date"], int(cadence["cadence_days"])) else "current", "update_action": _text(raw.get("update_action") or raw.get("action")) or "review and refresh operational steps"})
    if not rows:
        rows.append({"id": "", "runbook": "runbook-intake", "owner": "runbook_owner", "last_reviewed": "review-date-required", "criticality": "medium", "incident_references": [], "status": "overdue", "update_action": "review and refresh operational steps"})
    rows = sorted(rows, key=lambda row: (row["status"] != "overdue", CRITICALITY_ORDER[row["criticality"]], row["last_reviewed"], row["runbook"].casefold()))
    for index, row in enumerate(rows, start=1):
        row["id"] = f"RFA-{index:03d}"
    return rows


def _update_actions(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"runbook_id": row["id"], "runbook": row["runbook"], "owner": row["owner"], "action": row["update_action"]} for row in rows if row["status"] == "overdue" or row["incident_references"]]


def _audit_cadence(spec: dict[str, Any]) -> dict[str, Any]:
    cadence = _dict(_dict(spec.get("metadata")).get("audit_cadence") or spec.get("audit_cadence"))
    return {"cadence_days": _text(cadence.get("cadence_days") or cadence.get("days")) or "90", "anchor_date": _text(cadence.get("anchor_date")) or "2026-01-01", "reviewer": _text(cadence.get("reviewer")) or "runbook_owner"}


def _raw_runbooks(spec: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = _dict(spec.get("metadata"))
    plan = _dict(metadata.get("runbook_freshness_audit") or spec.get("runbook_freshness_audit"))
    candidates = plan.get("runbooks") or metadata.get("runbooks") or spec.get("runbooks")
    return [item for item in candidates if isinstance(item, dict)] if isinstance(candidates, list) else []


def _is_overdue(last_reviewed: str, anchor_date: str, cadence_days: int) -> bool:
    if last_reviewed == "review-date-required" or len(last_reviewed) < 10 or len(anchor_date) < 10:
        return True
    return _ordinal(anchor_date[:10]) - _ordinal(last_reviewed[:10]) > cadence_days


def _ordinal(date: str) -> int:
    year, month, day = (int(part) for part in date.split("-"))
    return year * 372 + month * 31 + day


def _is_plan(value: dict[str, Any] | None) -> bool:
    return isinstance(value, dict) and value.get("kind") == KIND and "runbook_rows" in value


def _choice(value: Any, allowed: set[str], fallback: str) -> str:
    text = _text(value).casefold()
    return text if text in allowed else fallback


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = value if isinstance(value, list) else [value]
    result = [_text(item) for item in values if _text(item)]
    return result or fallback


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""

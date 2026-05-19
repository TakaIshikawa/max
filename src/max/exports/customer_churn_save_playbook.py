"""Customer churn-save playbook export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.customer_churn_save_playbook.v1"
KIND = "max.customer_churn_save_playbook"

_RISK_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def build_customer_churn_save_playbook_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_RISK_ORDER[row["churn_risk"]], row["renewal_date"] or "9999-12-31", row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "customer_churn_save_playbook", "domain_filter": domain},
        "playbook_rows": rows,
        "summary": _summary(rows),
        "escalation_criteria": _escalation_criteria(rows),
        "recommended_next_actions": _recommendations(rows),
    }


def render_customer_churn_save_playbook_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_customer_churn_save_playbook_markdown(report: dict[str, Any]) -> str:
    lines = ["# Customer Churn-Save Playbook", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Save Plans", ""]
    if report.get("playbook_rows"):
        lines.extend(["| Idea | Account | Risk | Renewal | Drivers | Owner | Timing | Action |", "|------|---------|------|---------|---------|-------|--------|--------|"])
        for row in report["playbook_rows"]:
            lines.append(
                f"| {_md(row['title'])} | {_md(row['account_context']['account'])} | {row['churn_risk']} | "
                f"{_md(row['renewal_date'] or 'Unknown')} | {_md(', '.join(row['churn_drivers']) or 'None')} | "
                f"{_md(row['owner_assignment']['owner'])} | {_md(row['intervention_timing'])} | "
                f"{_md(row['intervention_actions'][0] if row['intervention_actions'] else 'Monitor account')} |"
            )
    else:
        lines.append("- No customer churn-save metadata available.")
    lines.extend(["", "## Recommended Next Actions", ""])
    lines.extend(f"- {item}" for item in report.get("recommended_next_actions", []))
    return "\n".join(lines).rstrip() + "\n"


def _row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    health = _score(metadata.get("account_health") or metadata.get("health_score"), 50)
    adoption_gaps = _list(metadata.get("adoption_gaps") or metadata.get("usage_gaps"))
    blockers = _list(metadata.get("blockers") or metadata.get("renewal_blockers"))
    stakeholder_notes = _list(metadata.get("stakeholder_notes") or metadata.get("notes"))
    renewal = _text(metadata.get("renewal_date") or metadata.get("renewal"))
    owner = _text(metadata.get("owner") or metadata.get("csm") or metadata.get("save_owner") or "Unassigned")
    risk_score = min(100, (100 - health) + len(adoption_gaps) * 10 + len(blockers) * 18 + _renewal_pressure(renewal))
    risk = _risk(risk_score)
    drivers = _drivers(health, adoption_gaps, blockers, stakeholder_notes)
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": _text(getattr(unit, "title", "")) or "Untitled",
        "account_context": {
            "account": _text(metadata.get("account") or metadata.get("customer") or metadata.get("segment") or "Unknown"),
            "health_score": health,
            "stakeholder_notes": stakeholder_notes,
        },
        "renewal_date": renewal,
        "churn_risk": risk,
        "risk_score": risk_score,
        "churn_drivers": drivers,
        "adoption_gaps": adoption_gaps,
        "blockers": blockers,
        "intervention_actions": _actions(risk, drivers, blockers),
        "owner_assignment": {"owner": owner, "role": _text(metadata.get("owner_role") or "customer success")},
        "intervention_timing": _timing(risk, renewal),
        "escalation_criteria": _row_escalation(risk, blockers),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "account_count": len(rows),
        "risk_counts": {risk: sum(1 for row in rows if row["churn_risk"] == risk) for risk in _RISK_ORDER},
        "blocked_account_count": sum(1 for row in rows if row["blockers"]),
    }


def _escalation_criteria(rows: list[dict[str, Any]]) -> list[str]:
    criteria = []
    if any(row["churn_risk"] in {"critical", "high"} for row in rows):
        criteria.append("Escalate high-risk renewals with unresolved save actions to executive sponsor review.")
    if any(row["owner_assignment"]["owner"] == "Unassigned" for row in rows):
        criteria.append("Escalate accounts without an assigned save owner.")
    return criteria or ["Escalate when account health drops below 50 or blockers remain open within 30 days of renewal."]


def _recommendations(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Capture account health, renewal date, adoption gaps, blockers, stakeholders, and save owner."]
    if any(row["churn_risk"] == "critical" for row in rows):
        return ["Run a same-week churn-save standup for critical accounts."]
    if any(row["blockers"] for row in rows):
        return ["Assign dated blocker-removal actions before renewal negotiation."]
    return ["Review churn-save plans weekly until renewal close."]


def _drivers(health: int, adoption_gaps: list[str], blockers: list[str], notes: list[str]) -> list[str]:
    drivers = []
    if health < 60:
        drivers.append("low account health")
    drivers.extend(adoption_gaps)
    drivers.extend(blockers)
    drivers.extend(notes[:2])
    return drivers


def _actions(risk: str, drivers: list[str], blockers: list[str]) -> list[str]:
    if blockers:
        return [f"Resolve blocker: {blockers[0]}", "Confirm renewal decision criteria with buyer."]
    if risk in {"critical", "high"}:
        return ["Schedule executive save call.", "Publish recovery plan with dates and owners."]
    if drivers:
        return [f"Close adoption gap: {drivers[0]}"]
    return ["Maintain renewal check-in cadence."]


def _row_escalation(risk: str, blockers: list[str]) -> str:
    if risk == "critical":
        return "Escalate if no executive save call is scheduled within five business days."
    if blockers:
        return "Escalate if blockers remain open at the next renewal checkpoint."
    return "Escalate if account health declines before renewal."


def _timing(risk: str, renewal: str) -> str:
    if risk in {"critical", "high"}:
        return "immediate"
    if renewal:
        return f"before renewal on {renewal}"
    return "next account review"


def _risk(score: int) -> str:
    if score >= 90:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def _renewal_pressure(value: str) -> int:
    if not value:
        return 0
    try:
        days = (datetime.fromisoformat(value[:10]).date() - datetime.now(timezone.utc).date()).days
    except ValueError:
        return 8
    if days <= 30:
        return 20
    if days <= 90:
        return 10
    return 0


def _score(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return round(max(0, min(100, float(str(value).rstrip("%")))))
    except ValueError:
        text = _text(value).lower()
        if any(word in text for word in ("healthy", "green", "strong")):
            return 85
        if any(word in text for word in ("at risk", "red", "poor", "low")):
            return 30
        return default


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    return [_text(item) for item in value if _text(item)] if isinstance(value, (list, tuple, set)) else [_text(value)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")

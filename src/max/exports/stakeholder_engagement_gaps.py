"""Stakeholder engagement gaps export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.stakeholder_engagement_gaps.v1"
KIND = "max.stakeholder_engagement_gaps"

_RISK_ORDER = {"high": 0, "medium": 1, "low": 2}


def build_stakeholder_engagement_gaps_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_engagement_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_RISK_ORDER[row["engagement_risk"]], -row["risk_score"], row["account"], row["idea_id"]))
    summary = _summary(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "stakeholder_engagement_gaps", "domain_filter": domain},
        "summary": summary,
        "engagement_rows": rows,
        "missing_roles": _missing_roles(rows),
        "recommended_actions": _recommended_actions(rows, summary),
    }


def render_stakeholder_engagement_gaps_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_stakeholder_engagement_gaps_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Stakeholder Engagement Gaps",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Accounts analyzed: {summary.get('account_count', 0)}",
        f"- High risk: {summary.get('risk_counts', {}).get('high', 0)}",
        f"- Medium risk: {summary.get('risk_counts', {}).get('medium', 0)}",
        f"- Low risk: {summary.get('risk_counts', {}).get('low', 0)}",
        "",
        "## Engagement Rows",
        "",
    ]
    if report.get("engagement_rows"):
        lines.extend(["| Account | Risk | Missing Roles | Last Touch | Champion | Sponsor | Action |", "|---------|------|---------------|------------|----------|---------|--------|"])
        for row in report["engagement_rows"]:
            lines.append(
                f"| {_md(row['account'])} | {row['engagement_risk']} | {_md(', '.join(row['missing_required_roles']) or 'None')} | "
                f"{row['last_touch_days']} | {_md(row['champion_status'])} | {_md(row['executive_sponsor'])} | {_md(row['recommended_action'])} |"
            )
    else:
        lines.append("- No stakeholder engagement records found.")
    lines.extend(["", "## Recommended Actions", ""])
    for action in report.get("recommended_actions", []):
        lines.append(f"- {action}")
    return "\n".join(lines).rstrip() + "\n"


def _engagement_row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    required = _lower_list(metadata.get("required_roles"))
    engaged = _lower_list(metadata.get("engaged_roles"))
    missing = sorted(role for role in required if role not in engaged)
    last_touch = int(_number(metadata.get("last_touch_days")) or 0)
    champion = _text(metadata.get("champion_status")).lower() or "unknown"
    sponsor = _text(metadata.get("executive_sponsor"))
    decision_owner = _text(metadata.get("decision_owner"))
    blockers = _list(metadata.get("blockers"))
    score = len(missing) * 20 + len(blockers) * 25
    if last_touch > 30:
        score += 25
    if champion in {"", "none", "absent", "missing", "unknown", "weak", "at risk"}:
        score += 20
    if not sponsor:
        score += 15
    if not decision_owner:
        score += 15
    risk = "high" if score >= 60 else "medium" if score >= 25 else "low"
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "account": _text(metadata.get("account") or getattr(unit, "title", "Untitled")),
        "stakeholders": _list(metadata.get("stakeholders")),
        "required_roles": required,
        "engaged_roles": engaged,
        "missing_required_roles": missing,
        "last_touch_days": last_touch,
        "champion_status": champion,
        "executive_sponsor": sponsor or "Unassigned",
        "decision_owner": decision_owner or "Unassigned",
        "blockers": blockers,
        "next_meeting_date": _text(metadata.get("next_meeting_date")) or None,
        "risk_score": round(score, 1),
        "engagement_risk": risk,
        "recommended_action": _recommended_action(risk, missing, blockers),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"account_count": len(rows), "risk_counts": {risk: sum(1 for row in rows if row["engagement_risk"] == risk) for risk in ("high", "medium", "low")}}


def _missing_roles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        for role in row["missing_required_roles"]:
            counts[role] = counts.get(role, 0) + 1
    return [{"role": role, "count": count} for role, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _recommended_actions(rows: list[dict[str, Any]], summary: dict[str, Any]) -> list[str]:
    if not rows:
        return ["Capture stakeholder roles, engagement dates, champion status, and blockers before account review."]
    actions = []
    if summary["risk_counts"]["high"]:
        actions.append("Escalate high-risk engagement gaps with account leadership.")
    if any(row["missing_required_roles"] for row in rows):
        actions.append("Map and engage missing required buying roles.")
    if not actions:
        actions.append("Maintain stakeholder touch cadence and sponsor coverage.")
    return actions


def _recommended_action(risk: str, missing: list[str], blockers: list[str]) -> str:
    if blockers:
        return "Resolve blockers and re-engage stakeholders."
    if missing:
        return "Identify and engage missing required roles."
    if risk == "medium":
        return "Refresh stakeholder touchpoints."
    return "No immediate engagement gap."


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _lower_list(value: Any) -> list[str]:
    return sorted({_text(item).lower() for item in _list(value) if _text(item)})


def _list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [text] if text else []


def _number(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")

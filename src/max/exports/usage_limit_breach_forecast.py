"""Usage limit breach forecast export."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.usage_limit_breach_forecast.v1"
KIND = "max.usage_limit_breach_forecast"

_RISK_ORDER = {"breached": 0, "imminent": 1, "watch": 2, "normal": 3}


def build_usage_limit_breach_forecast_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_forecast_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_RISK_ORDER[row["breach_risk"]], row["days_to_breach"] if row["days_to_breach"] is not None else 999999, row["account"], row["idea_id"]))
    summary = _summary(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "usage_limit_breach_forecast", "domain_filter": domain},
        "summary": summary,
        "forecast_rows": rows,
        "breach_risks": [row for row in rows if row["breach_risk"] in {"breached", "imminent"}],
        "recommended_actions": _recommended_actions(rows, summary),
    }


def render_usage_limit_breach_forecast_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_usage_limit_breach_forecast_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Usage Limit Breach Forecast",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Accounts analyzed: {summary.get('account_count', 0)}",
        f"- Breached: {summary.get('risk_counts', {}).get('breached', 0)}",
        f"- Imminent: {summary.get('risk_counts', {}).get('imminent', 0)}",
        f"- Watch: {summary.get('risk_counts', {}).get('watch', 0)}",
        f"- Normal: {summary.get('risk_counts', {}).get('normal', 0)}",
        "",
        "## Forecast Rows",
        "",
    ]
    if report.get("forecast_rows"):
        lines.extend(["| Account | Risk | Utilization | Days To Breach | Owner | Action |", "|---------|------|-------------|----------------|-------|--------|"])
        for row in report["forecast_rows"]:
            days = "" if row["days_to_breach"] is None else str(row["days_to_breach"])
            lines.append(f"| {_md(row['account'])} | {row['breach_risk']} | {row['utilization_percent']:.1f}% | {days} | {_md(row['alert_owner'])} | {_md(row['recommended_action'])} |")
    else:
        lines.append("- No usage limit records found.")
    lines.extend(["", "## Recommended Actions", ""])
    for action in report.get("recommended_actions", []):
        lines.append(f"- {action}")
    return "\n".join(lines).rstrip() + "\n"


def _forecast_row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    limit = _number(metadata.get("plan_limit"))
    usage = _number(metadata.get("current_usage"))
    growth = _number(metadata.get("usage_growth_rate"))
    window = _number(metadata.get("measurement_window_days")) or 30.0
    utilization = round((usage / limit) * 100, 1) if limit and usage is not None and limit > 0 else 0.0
    days_to_breach = _days_to_breach(limit, usage, growth, window)
    if limit and usage is not None and usage >= limit:
        risk = "breached"
    elif days_to_breach is not None and days_to_breach <= 30:
        risk = "imminent"
    elif utilization >= 75 or (days_to_breach is not None and days_to_breach <= 90):
        risk = "watch"
    else:
        risk = "normal"
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "account": _text(metadata.get("account") or getattr(unit, "title", "Untitled")),
        "plan_limit": limit,
        "current_usage": usage,
        "usage_growth_rate": growth,
        "measurement_window_days": window,
        "utilization_percent": utilization,
        "days_to_breach": days_to_breach,
        "breach_risk": risk,
        "overage_policy": _text(metadata.get("overage_policy")) or "unknown",
        "alert_owner": _text(metadata.get("alert_owner")) or "Unassigned",
        "renewal_date": _text(metadata.get("renewal_date")) or None,
        "mitigation_status": _text(metadata.get("mitigation_status")) or "unknown",
        "recommended_action": _recommended_action(risk),
    }


def _days_to_breach(limit: float | None, usage: float | None, growth: float | None, window: float) -> int | None:
    if not limit or usage is None or growth is None or growth <= 0 or window <= 0:
        return None
    if usage >= limit:
        return 0
    daily_growth = growth / window
    if daily_growth <= 0:
        return None
    return int(math.ceil((limit - usage) / daily_growth))


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "account_count": len(rows),
        "risk_counts": {risk: sum(1 for row in rows if row["breach_risk"] == risk) for risk in ("breached", "imminent", "watch", "normal")},
        "average_utilization_percent": round(sum(row["utilization_percent"] for row in rows) / len(rows), 1) if rows else 0.0,
    }


def _recommended_actions(rows: list[dict[str, Any]], summary: dict[str, Any]) -> list[str]:
    if not rows:
        return ["Capture plan limit, current usage, growth rate, and alert owner before usage forecasting."]
    actions = []
    if summary["risk_counts"]["breached"]:
        actions.append("Apply overage policy and assign immediate mitigation for breached accounts.")
    if summary["risk_counts"]["imminent"]:
        actions.append("Notify alert owners for accounts forecast to breach within 30 days.")
    if not actions:
        actions.append("Review watch accounts during renewal and capacity planning.")
    return actions


def _recommended_action(risk: str) -> str:
    if risk == "breached":
        return "Apply overage policy and remediate usage immediately."
    if risk == "imminent":
        return "Contact owner and plan mitigation before breach."
    if risk == "watch":
        return "Monitor growth and prepare limit adjustment."
    return "No immediate action required."


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _number(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")

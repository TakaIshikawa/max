"""Account health score export for customer success review."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.account_health_score.v1"
KIND = "max.account_health_score"

_STATUS_ORDER = {"at_risk": 0, "watchlist": 1, "healthy": 2}
_TREND_SCORES = {
    "strong_growth": 15.0,
    "growth": 10.0,
    "growing": 10.0,
    "up": 8.0,
    "flat": 0.0,
    "stable": 0.0,
    "mixed": -5.0,
    "declining": -15.0,
    "down": -15.0,
    "drop": -15.0,
}
_CHAMPION_SCORES = {
    "strong": 10.0,
    "active": 8.0,
    "identified": 4.0,
    "unknown": -8.0,
    "weak": -10.0,
    "lost": -20.0,
    "none": -15.0,
}


def build_account_health_score_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    """Build account health scores from buildable unit customer metadata."""
    units = store.get_buildable_units(limit=1000, domain=domain)
    rows = [_account_row(unit) for unit in units]
    rows.sort(key=lambda row: (_STATUS_ORDER[row["status_band"]], row["health_score"], row["account_name"].lower(), row["idea_id"]))
    summary = _summary(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "account_health_score",
            "domain_filter": domain,
            "score_range": {"min": 0, "max": 100},
            "status_bands": {"healthy": ">= 75", "watchlist": "50-74", "at_risk": "< 50"},
        },
        "accounts": rows,
        "summary": summary,
        "recommendations": _recommendations(rows, summary),
    }


def render_account_health_score_markdown(report: dict[str, Any]) -> str:
    """Render account health scores as Markdown."""
    summary = report.get("summary", {})
    lines = [
        "# Account Health Score",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Accounts reviewed: {summary.get('account_count', 0)}",
        f"- Average health score: {summary.get('average_health_score', 0.0):.1f}",
        f"- At-risk accounts: {summary.get('at_risk_count', 0)}",
        f"- Watchlist accounts: {summary.get('watchlist_count', 0)}",
        f"- Healthy accounts: {summary.get('healthy_count', 0)}",
        "",
        "## Status Table",
        "",
    ]
    if report.get("accounts"):
        lines.extend([
            "| Account | Idea | Score | Status | Drivers | Next Action |",
            "|---------|------|-------|--------|---------|-------------|",
        ])
        for row in report["accounts"]:
            lines.append(
                f"| {_md(row['account_name'])} | {_md(row['title'])} | {row['health_score']:.1f} | "
                f"{row['status_band']} | {_md(', '.join(row['drivers']) or 'None')} | {_md(row['next_action'])} |"
            )
    else:
        lines.append(
            "- No account metadata found. Add account_name, usage_trend, support tickets, "
            "NPS, renewal, champion, risk, and expansion signals to score health."
        )

    lines.extend(["", "## Recommended Next Actions", ""])
    for recommendation in report.get("recommendations", []):
        lines.append(f"- {recommendation}")
    return "\n".join(lines).rstrip() + "\n"


def render_account_health_score_json(report: dict[str, Any]) -> str:
    """Render account health scores as stable formatted JSON."""
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def _account_row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    score = 70.0
    drivers: list[str] = []

    trend = _string(metadata, ["usage_trend"], "flat").lower().replace(" ", "_")
    trend_delta = _TREND_SCORES.get(trend, 0.0)
    score += trend_delta
    if trend_delta:
        drivers.append(f"usage trend {'raised' if trend_delta > 0 else 'lowered'} score")

    tickets = _non_negative_int(_number(metadata, ["support_ticket_count", "open_support_tickets"], 0))
    ticket_delta = -min(tickets * 3.0, 24.0)
    score += ticket_delta
    if tickets:
        drivers.append(f"{tickets} support ticket(s) lowered score")

    nps = _number(metadata, ["nps_score", "nps"], None)
    if nps is None:
        score -= 5.0
        drivers.append("missing NPS lowered score")
    elif nps >= 50:
        score += 10.0
        drivers.append("high NPS raised score")
    elif nps >= 0:
        score += 2.0
        drivers.append("neutral NPS raised score")
    elif nps <= -20:
        score -= 18.0
        drivers.append("low NPS lowered score")
    else:
        score -= 8.0
        drivers.append("negative NPS lowered score")

    renewal_delta, renewal_driver = _renewal_delta(_lookup(metadata, "renewal_date"))
    score += renewal_delta
    if renewal_driver:
        drivers.append(renewal_driver)

    champion = _string(metadata, ["champion_status"], "unknown").lower().replace(" ", "_")
    champion_delta = _CHAMPION_SCORES.get(champion, -4.0)
    score += champion_delta
    if champion_delta:
        drivers.append(f"champion status {'raised' if champion_delta > 0 else 'lowered'} score")

    risks = _items(_lookup(metadata, "open_risks"))
    risk_delta = -min(len(risks) * 8.0, 32.0)
    score += risk_delta
    if risks:
        drivers.append(f"{len(risks)} open risk(s) lowered score")

    expansion = _non_negative_int(_number(metadata, ["expansion_signal_count", "expansion_signals"], 0))
    expansion_delta = min(expansion * 4.0, 16.0)
    score += expansion_delta
    if expansion:
        drivers.append(f"{expansion} expansion signal(s) raised score")

    health_score = round(_bounded(score), 1)
    status = _status_band(health_score)
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "domain": str(getattr(unit, "domain", "") or "general"),
        "account_name": _string(metadata, ["account_name", "customer_name"], "") or str(getattr(unit, "title", "Unknown account")),
        "health_score": health_score,
        "status_band": status,
        "drivers": drivers,
        "next_action": _next_action(status, drivers),
        "signals": {
            "usage_trend": trend,
            "support_ticket_count": tickets,
            "nps_score": nps,
            "renewal_date": _string(metadata, ["renewal_date"], ""),
            "champion_status": champion,
            "open_risk_count": len(risks),
            "expansion_signal_count": expansion,
        },
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "account_count": len(rows),
        "average_health_score": round(sum(row["health_score"] for row in rows) / len(rows), 1) if rows else 0.0,
        "at_risk_count": sum(1 for row in rows if row["status_band"] == "at_risk"),
        "watchlist_count": sum(1 for row in rows if row["status_band"] == "watchlist"),
        "healthy_count": sum(1 for row in rows if row["status_band"] == "healthy"),
    }


def _recommendations(rows: list[dict[str, Any]], summary: dict[str, Any]) -> list[str]:
    if not rows:
        return ["Add customer health metadata to buildable units before running the account health export."]
    recommendations: list[str] = []
    if summary["at_risk_count"]:
        recommendations.append("Create recovery plans for at-risk accounts and assign an owner for each open risk.")
    if summary["watchlist_count"]:
        recommendations.append("Review watchlist accounts in the next customer success forecast meeting.")
    if any(row["signals"]["expansion_signal_count"] > 0 and row["status_band"] == "healthy" for row in rows):
        recommendations.append("Route healthy accounts with expansion signals into expansion discovery.")
    return recommendations or ["Maintain current account health monitoring and refresh signals before renewal reviews."]


def _status_band(score: float) -> str:
    if score >= 75.0:
        return "healthy"
    if score >= 50.0:
        return "watchlist"
    return "at_risk"


def _next_action(status: str, drivers: list[str]) -> str:
    if status == "at_risk":
        return "Schedule executive recovery review and close the highest-impact risk."
    if status == "watchlist":
        return "Validate usage, champion coverage, and renewal blockers this week."
    if any("expansion" in driver for driver in drivers):
        return "Qualify expansion signal with champion and account owner."
    return "Continue monitoring and refresh health signals before the next review."


def _renewal_delta(value: Any) -> tuple[float, str]:
    if value in (None, ""):
        return -5.0, "missing renewal date lowered score"
    try:
        renewal = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return -5.0, "invalid renewal date lowered score"
    if renewal.tzinfo is None:
        renewal = renewal.replace(tzinfo=timezone.utc)
    days = (renewal - datetime.now(timezone.utc)).days
    if days < 0:
        return -18.0, "past renewal date lowered score"
    if days <= 30:
        return -12.0, "near-term renewal lowered score"
    if days <= 90:
        return -5.0, "upcoming renewal lowered score"
    return 3.0, "renewal runway raised score"


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _lookup(metadata: dict[str, Any], key: str) -> Any:
    if key in metadata:
        return metadata[key]
    for nested_key in ("account", "customer", "health", "success"):
        nested = metadata.get(nested_key)
        if isinstance(nested, dict) and key in nested:
            return nested[key]
    return None


def _string(metadata: dict[str, Any], keys: list[str], default: str) -> str:
    for key in keys:
        value = _lookup(metadata, key)
        if value not in (None, ""):
            return str(value).strip()
    return default


def _number(metadata: dict[str, Any], keys: list[str], default: float | None) -> float | None:
    for key in keys:
        value = _lookup(metadata, key)
        if value in (None, ""):
            continue
        try:
            return float(str(value).replace(",", "").replace("$", ""))
        except (TypeError, ValueError):
            return default
    return default


def _non_negative_int(value: float | None) -> int:
    if value is None:
        return 0
    return max(int(value), 0)


def _items(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if str(item).strip()]
    if isinstance(value, tuple | set):
        return [item for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    return [value]


def _bounded(value: float) -> float:
    return min(max(value, 0.0), 100.0)


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")

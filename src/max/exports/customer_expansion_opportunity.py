"""Customer expansion opportunity export for sales and success follow-up."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.customer_expansion_opportunity.v1"
KIND = "max.customer_expansion_opportunity"


def build_customer_expansion_opportunity_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    units = store.get_buildable_units(limit=1000, domain=domain)
    rows = [_row(unit) for unit in units]
    rows.sort(key=lambda row: (-row["readiness_score"], row["account_name"].lower(), row["idea_id"]))
    summary = _summary(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "customer_expansion_opportunity", "domain_filter": domain, "score_range": {"min": 0, "max": 100}},
        "opportunities": rows,
        "summary": summary,
        "recommendations": _recommendations(rows, summary),
    }


def render_customer_expansion_opportunity_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Customer Expansion Opportunity",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Accounts reviewed: {summary.get('account_count', 0)}",
        f"- Average readiness score: {summary.get('average_readiness_score', 0.0):.1f}",
        f"- High readiness accounts: {summary.get('high_readiness_count', 0)}",
        f"- Risk-downgraded accounts: {summary.get('risk_downgraded_count', 0)}",
        "",
        "## Opportunities",
        "",
    ]
    if report.get("opportunities"):
        lines.extend(["| Account | Plan | Score | Band | Seat Utilization | Drivers | Next Action |", "|---------|------|-------|------|------------------|---------|-------------|"])
        for row in report["opportunities"]:
            lines.append(
                f"| {_md(row['account_name'])} | {_md(row['plan_tier'])} | {row['readiness_score']:.1f} | {row['readiness_band']} | "
                f"{row['seat_utilization_pct']:.1f}% | {_md(', '.join(row['drivers']) or 'None')} | {_md(row['next_action'])} |"
            )
    else:
        lines.append("- No customer expansion metadata found. Add account, seat usage, signal, renewal, champion, risk, and requested feature fields.")
    lines.extend(["", "## Segment Rollup", ""])
    if summary.get("by_plan_tier"):
        lines.extend(["| Plan Tier | Accounts | Average Score | High Readiness |", "|-----------|----------|---------------|----------------|"])
        for row in summary["by_plan_tier"]:
            lines.append(f"| {_md(row['plan_tier'])} | {row['account_count']} | {row['average_readiness_score']:.1f} | {row['high_readiness_count']} |")
    else:
        lines.append("- No segment rollups available.")
    lines.extend(["", "## Recommendations", ""])
    for recommendation in report.get("recommendations", []):
        lines.append(f"- {recommendation}")
    return "\n".join(lines).rstrip() + "\n"


def render_customer_expansion_opportunity_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def _row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    seats_used = _int(_number(metadata, ["seats_used", "active_seats"], 0))
    seat_limit = _int(_number(metadata, ["seat_limit", "licensed_seats"], 0))
    utilization = round((seats_used / seat_limit) * 100.0, 1) if seat_limit > 0 else 0.0
    signals = _items(_lookup(metadata, "expansion_signals"))
    features = _items(_lookup(metadata, "requested_features"))
    risks = _items(_lookup(metadata, "open_risks"))
    trend = _string(metadata, ["usage_trend"], "flat").lower().replace(" ", "_")
    champion = _string(metadata, ["champion_status"], "unknown").lower().replace(" ", "_")

    score = 35.0
    drivers: list[str] = []
    if utilization >= 90:
        score += 25.0
        drivers.append("seat utilization raised score")
    elif utilization >= 70:
        score += 15.0
        drivers.append("moderate seat utilization raised score")
    elif seat_limit == 0:
        score -= 8.0
        drivers.append("missing seat limit lowered score")
    if trend in {"strong_growth", "growth", "growing", "up"}:
        score += 15.0
        drivers.append("growth trend raised score")
    elif trend in {"declining", "down", "drop"}:
        score -= 20.0
        drivers.append("declining usage lowered score")
    if signals:
        score += min(len(signals) * 8.0, 24.0)
        drivers.append(f"{len(signals)} expansion signal(s) raised score")
    if features:
        score += min(len(features) * 4.0, 12.0)
        drivers.append(f"{len(features)} requested feature(s) raised score")
    if champion in {"strong", "active"}:
        score += 12.0
        drivers.append("active champion raised score")
    elif champion in {"weak", "lost", "none", "unknown"}:
        score -= 10.0
        drivers.append("weak champion coverage lowered score")
    renewal_delta = _renewal_delta(_lookup(metadata, "renewal_date"))
    score += renewal_delta
    if renewal_delta > 0:
        drivers.append("renewal window raised score")
    elif renewal_delta < 0:
        drivers.append("renewal timing lowered score")
    if risks:
        score -= min(len(risks) * 12.0, 36.0)
        drivers.append(f"{len(risks)} open risk(s) lowered score")

    readiness_score = round(min(max(score, 0.0), 100.0), 1)
    band = _band(readiness_score)
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "domain": str(getattr(unit, "domain", "") or "general"),
        "account_name": _string(metadata, ["account_name", "customer_name"], "") or str(getattr(unit, "title", "Unknown account")),
        "plan_tier": _string(metadata, ["plan_tier", "customer_segment"], "unknown").lower(),
        "readiness_score": readiness_score,
        "readiness_band": band,
        "seat_utilization_pct": utilization,
        "risk_downgraded": bool(risks),
        "drivers": drivers,
        "next_action": _next_action(band, bool(risks)),
        "signals": {"seats_used": seats_used, "seat_limit": seat_limit, "usage_trend": trend, "expansion_signals": signals, "renewal_date": _string(metadata, ["renewal_date"], ""), "champion_status": champion, "open_risks": risks, "requested_features": features},
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["plan_tier"]].append(row)
    return {
        "account_count": len(rows),
        "average_readiness_score": round(sum(row["readiness_score"] for row in rows) / len(rows), 1) if rows else 0.0,
        "high_readiness_count": sum(1 for row in rows if row["readiness_band"] == "high"),
        "medium_readiness_count": sum(1 for row in rows if row["readiness_band"] == "medium"),
        "low_readiness_count": sum(1 for row in rows if row["readiness_band"] == "low"),
        "risk_downgraded_count": sum(1 for row in rows if row["risk_downgraded"]),
        "by_plan_tier": [{"plan_tier": tier, "account_count": len(items), "average_readiness_score": round(sum(item["readiness_score"] for item in items) / len(items), 1), "high_readiness_count": sum(1 for item in items if item["readiness_band"] == "high")} for tier, items in sorted(groups.items())],
    }


def _recommendations(rows: list[dict[str, Any]], summary: dict[str, Any]) -> list[str]:
    if not rows:
        return ["Add customer expansion metadata to buildable units before exporting expansion opportunities."]
    recommendations: list[str] = []
    if summary["high_readiness_count"]:
        recommendations.append("Route high-readiness accounts to sales or customer success for expansion discovery.")
    if summary["risk_downgraded_count"]:
        recommendations.append("Resolve open risks before committing expansion forecasts for downgraded accounts.")
    return recommendations or ["Refresh expansion signals and requested features before the next account planning review."]


def _band(score: float) -> str:
    if score >= 75:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def _next_action(band: str, risky: bool) -> str:
    if risky:
        return "Close account risks before expansion outreach."
    if band == "high":
        return "Schedule expansion discovery with the champion and account owner."
    if band == "medium":
        return "Validate seat need, feature demand, and renewal timing."
    return "Backfill account signals before prioritizing expansion."


def _renewal_delta(value: Any) -> float:
    if value in (None, ""):
        return -5.0
    try:
        renewal = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return -5.0
    if renewal.tzinfo is None:
        renewal = renewal.replace(tzinfo=timezone.utc)
    days = (renewal - datetime.now(timezone.utc)).days
    if days < 0:
        return -15.0
    if days <= 120:
        return 8.0
    return 2.0


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _lookup(metadata: dict[str, Any], key: str) -> Any:
    if key in metadata:
        return metadata[key]
    for nested_key in ("account", "customer", "expansion", "success"):
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


def _number(metadata: dict[str, Any], keys: list[str], default: float) -> float:
    for key in keys:
        value = _lookup(metadata, key)
        if value in (None, ""):
            continue
        try:
            return float(str(value).replace(",", "").replace("$", ""))
        except (TypeError, ValueError):
            return default
    return default


def _int(value: float) -> int:
    return max(int(value), 0)


def _items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple | set):
        return sorted(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    return [str(value).strip()]


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")

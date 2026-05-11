"""Feature sunset impact export."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.feature_sunset_impact.v1"
KIND = "max.feature_sunset_impact"
CSV_FIELDS = ("idea_id", "feature_name", "impact_score", "impact_band", "active_user_count", "revenue_at_risk", "dependent_account_count", "migration_status", "planned_sunset_date", "recommendation")
_BAND_ORDER = {"severe": 0, "high": 1, "medium": 2, "low": 3}


def build_feature_sunset_impact_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_BAND_ORDER[row["impact_band"]], -row["impact_score"], row["feature_name"].lower(), row["idea_id"]))
    summary = _summary(rows)
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": datetime.now(timezone.utc).isoformat(), "source": {"project": "max", "entity_type": "feature_sunset_impact", "domain_filter": domain}, "features": rows, "summary": summary, "recommendations": _recommendations(rows)}


def render_feature_sunset_impact_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_feature_sunset_impact_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in report.get("features", []):
        writer.writerow({field: row.get(field) for field in CSV_FIELDS})
    return output.getvalue()


def render_feature_sunset_impact_markdown(report: dict[str, Any]) -> str:
    lines = ["# Feature Sunset Impact", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Summary", "", f"- Features reviewed: {report.get('summary', {}).get('feature_count', 0)}", f"- Revenue at risk: ${report.get('summary', {}).get('revenue_at_risk', 0.0):,.0f}", "", "## Impact Table", ""]
    if report.get("features"):
        lines.extend(["| Feature | Score | Band | Users | Revenue At Risk | Migration | Recommendation |", "|---------|-------|------|-------|-----------------|-----------|----------------|"])
        for row in report["features"]:
            lines.append(f"| {_md(row['feature_name'])} | {row['impact_score']:.1f} | {row['impact_band']} | {row['active_user_count']} | ${row['revenue_at_risk']:,.0f} | {row['migration_status']} | {_md(row['recommendation'])} |")
    else:
        lines.append("- No feature sunset metadata found.")
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {item}" for item in report.get("recommendations", []))
    return "\n".join(lines).rstrip() + "\n"


def _row(unit: Any) -> dict[str, Any]:
    m = _metadata(unit)
    users = _int(m.get("active_user_count"))
    revenue = _float(m.get("revenue_at_risk"))
    accounts = _items(m.get("dependent_accounts"))
    tickets = _int(m.get("support_ticket_count"))
    compliance = _bool(m.get("compliance_dependency"))
    migration = str(m.get("migration_status") or "unknown").lower().replace(" ", "_")
    score = min(users / 100.0, 25.0) + min(revenue / 5000.0, 30.0) + min(len(accounts) * 6.0, 24.0) + min(tickets * 2.0, 12.0)
    if compliance:
        score += 20.0
    if migration in {"complete", "ready", "migrated"}:
        score -= 20.0
    elif migration in {"blocked", "not_started", "unknown"}:
        score += 10.0
    score = round(min(max(score, 0.0), 100.0), 1)
    band = "severe" if score >= 75 else "high" if score >= 55 else "medium" if score >= 30 else "low"
    return {"idea_id": str(getattr(unit, "id", "")), "title": str(getattr(unit, "title", "Untitled")), "domain": str(getattr(unit, "domain", "") or "general"), "feature_name": str(m.get("feature_name") or getattr(unit, "title", "Untitled feature")), "active_user_count": users, "revenue_at_risk": round(revenue, 2), "dependent_accounts": accounts, "dependent_account_count": len(accounts), "replacement_feature": str(m.get("replacement_feature") or ""), "migration_status": migration, "support_ticket_count": tickets, "compliance_dependency": compliance, "planned_sunset_date": str(m.get("planned_sunset_date") or ""), "impact_score": score, "impact_band": band, "recommendation": _recommendation(band, migration)}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"feature_count": len(rows), "revenue_at_risk": round(sum(row["revenue_at_risk"] for row in rows), 2), "band_counts": {band: sum(1 for row in rows if row["impact_band"] == band) for band in _BAND_ORDER}, "by_migration_status": [{"migration_status": status, "feature_count": len(items), "revenue_at_risk": round(sum(item["revenue_at_risk"] for item in items), 2)} for status, items in sorted(_groups(rows, "migration_status").items())]}


def _recommendations(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Add feature sunset metadata before exporting impact."]
    if any(row["impact_band"] in {"severe", "high"} for row in rows):
        return ["Create migration plans for high-impact sunset candidates before announcing retirement."]
    return ["Proceed with sunset review after confirming replacement coverage and support messaging."]


def _recommendation(band: str, migration: str) -> str:
    if band in {"severe", "high"}:
        return "Delay sunset until migration, support, and customer notices are ready."
    if migration in {"complete", "ready", "migrated"}:
        return "Proceed with controlled sunset communication."
    return "Confirm replacement path before setting sunset date."


def _groups(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    return groups


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _float(value: Any) -> float:
    try:
        return max(float(str(value or 0).replace(",", "").replace("$", "")), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    return int(_float(value))


def _bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    return []


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")

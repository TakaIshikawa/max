"""Feature entitlement revenue leakage export report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.feature_entitlement_revenue_leakage_report.v1"
KIND = "max.feature_entitlement_revenue_leakage_report"

_ORDER = {"high": 0, "medium": 1, "low": 2, "none": 3}


def build_feature_entitlement_revenue_leakage_report_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_ORDER[row["severity"]], -row["leakage_amount_usd"], row["account"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "feature_entitlement_revenue_leakage_report", "domain_filter": domain},
        "summary": _summary(rows),
        "account_rows": rows,
        "leakage_findings": [row for row in rows if row["uncontracted_features"]],
    }


def render_feature_entitlement_revenue_leakage_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_feature_entitlement_revenue_leakage_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Feature Entitlement Revenue Leakage Report", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Account Findings", ""]
    if report.get("account_rows"):
        lines.extend(["| Account | Severity | Leakage | Uncontracted Features | Remediation |", "|---------|----------|---------|-----------------------|-------------|"])
        for row in report["account_rows"]:
            lines.append(f"| {_md(row['account'])} | {row['severity']} | ${row['leakage_amount_usd']:,.0f} | {_md(', '.join(row['uncontracted_features']) or 'None')} | {_md(row['recommended_remediation'])} |")
    else:
        lines.append("- No entitlement records found.")
    return "\n".join(lines).rstrip() + "\n"


def _row(unit: Any) -> dict[str, Any]:
    m = _metadata(unit)
    contracted = set(_list(m.get("contracted_features")))
    entitled = set(_list(m.get("entitled_features") or m.get("enabled_features")))
    used = set(_list(m.get("used_features") or m.get("usage")))
    uncontracted = sorted((entitled | used) - contracted, key=str.lower)
    amount = _number(m.get("leakage_amount_usd") or m.get("estimated_leakage_usd"))
    if not amount:
        amount = float(len(uncontracted) * _number(m.get("feature_value_usd") or 1000))
    severity = _severity(amount, uncontracted)
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "account": _text(m.get("account") or getattr(unit, "title", "Untitled")),
        "contracted_features": sorted(contracted, key=str.lower),
        "entitled_features": sorted(entitled, key=str.lower),
        "used_features": sorted(used, key=str.lower),
        "uncontracted_features": uncontracted,
        "leakage_amount_usd": round(amount, 2),
        "severity": severity,
        "recommended_remediation": _remediation(severity),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"account_count": len(rows), "finding_count": sum(1 for row in rows if row["uncontracted_features"]), "total_leakage_amount_usd": round(sum(row["leakage_amount_usd"] for row in rows), 2), "severity_counts": {level: sum(1 for row in rows if row["severity"] == level) for level in ("high", "medium", "low", "none")}}


def _severity(amount: float, features: list[str]) -> str:
    if amount >= 50_000 or len(features) >= 3:
        return "high"
    if amount >= 10_000 or len(features) >= 2:
        return "medium"
    if amount > 0 or features:
        return "low"
    return "none"


def _remediation(severity: str) -> str:
    return "Escalate entitlement correction and commercial true-up." if severity == "high" else ("Review entitlement and update contract or access." if severity != "none" else "No remediation required.")


def _metadata(unit: Any) -> dict[str, Any]:
    return getattr(unit, "metadata", None) if isinstance(getattr(unit, "metadata", None), dict) else {}


def _list(value: Any) -> list[str]:
    if isinstance(value, dict):
        return sorted([_text(key) for key, enabled in value.items() if enabled and _text(key)], key=str.lower)
    if isinstance(value, str):
        return sorted({part.strip() for part in value.replace(";", ",").split(",") if part.strip()}, key=str.lower)
    if isinstance(value, (list, tuple, set)):
        return sorted({_text(item) for item in value if _text(item)}, key=str.lower)
    return []


def _number(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")

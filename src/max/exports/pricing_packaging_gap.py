"""Pricing packaging gap export."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.pricing_packaging_gap.v1"
KIND = "max.pricing_packaging_gap"
CSV_FIELDS = ("idea_id", "title", "plan_tier", "gap_type", "gap_score", "feature_value_score", "usage_count", "request_count", "revenue_impact", "recommendation")
_TYPE_ORDER = {"under_monetized": 0, "parity_risk": 1, "over_packaged": 2, "insufficient_signal": 3}


def build_pricing_packaging_gap_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_TYPE_ORDER[row["gap_type"]], -row["gap_score"], row["plan_tier"], row["idea_id"]))
    summary = _summary(rows)
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": datetime.now(timezone.utc).isoformat(), "source": {"project": "max", "entity_type": "pricing_packaging_gap", "domain_filter": domain}, "gaps": rows, "summary": summary, "recommendations": _recommendations(rows)}


def render_pricing_packaging_gap_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_pricing_packaging_gap_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in report.get("gaps", []):
        writer.writerow({field: row.get(field) for field in CSV_FIELDS})
    return output.getvalue()


def render_pricing_packaging_gap_markdown(report: dict[str, Any]) -> str:
    lines = ["# Pricing Packaging Gap", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Summary", "", f"- Rows reviewed: {report.get('summary', {}).get('gap_count', 0)}", "", "## Gaps", ""]
    if report.get("gaps"):
        lines.extend(["| Plan | Feature | Type | Score | Drivers | Recommendation |", "|------|---------|------|-------|---------|----------------|"])
        for row in report["gaps"]:
            lines.append(f"| {row['plan_tier']} | {_md(row['title'])} | {row['gap_type']} | {row['gap_score']:.1f} | {_md(', '.join(row['drivers']))} | {_md(row['recommendation'])} |")
    else:
        lines.append("- No pricing packaging metadata found.")
    lines.extend(["", "## Tier Rollup", ""])
    for item in report.get("summary", {}).get("by_plan_tier", []):
        lines.append(f"- {item['plan_tier']}: {item['gap_count']} gap(s), average score {item['average_gap_score']:.1f}")
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {item}" for item in report.get("recommendations", []))
    return "\n".join(lines).rstrip() + "\n"


def _row(unit: Any) -> dict[str, Any]:
    m = _metadata(unit)
    plan = str(m.get("plan_tier") or "unknown").lower()
    value = _float(m.get("feature_value_score"))
    usage = _int(m.get("usage_count"))
    requests = _int(m.get("request_count"))
    competitor = str(m.get("competitor_included_tier") or "").lower()
    wtp = _float(m.get("willingness_to_pay"))
    revenue = _float(m.get("revenue_impact"))
    churn = _float(m.get("churn_risk"))
    score = min(value, 100) * 0.35 + min(usage / 10, 20) + min(requests * 2, 20) + min(revenue / 5000, 20) + min(wtp / 1000, 10) + min(churn, 10)
    drivers: list[str] = []
    if value >= 70 and plan in {"free", "starter", "basic"}:
        gap_type = "under_monetized"
        drivers.append("high value in low tier")
    elif competitor and competitor in {"free", "starter", "basic"} and plan in {"enterprise", "premium"}:
        gap_type = "parity_risk"
        drivers.append("competitor includes feature in lower tier")
    elif value < 45 and plan in {"enterprise", "premium"}:
        gap_type = "over_packaged"
        drivers.append("low value feature packaged high")
    elif usage < 10 and requests < 3 and value < 40:
        gap_type = "insufficient_signal"
        drivers.append("low usage and demand signal")
    else:
        gap_type = "insufficient_signal"
        drivers.append("packaging signal needs validation")
    if revenue:
        drivers.append("revenue impact present")
    if churn:
        drivers.append("churn risk present")
    return {"idea_id": str(getattr(unit, "id", "")), "title": str(getattr(unit, "title", "Untitled")), "domain": str(getattr(unit, "domain", "") or "general"), "plan_tier": plan, "feature_value_score": round(value, 1), "usage_count": usage, "request_count": requests, "competitor_included_tier": competitor, "willingness_to_pay": round(wtp, 2), "revenue_impact": round(revenue, 2), "churn_risk": round(churn, 1), "packaging_notes": str(m.get("packaging_notes") or ""), "gap_type": gap_type, "gap_score": round(min(score, 100.0), 1), "drivers": drivers, "recommendation": _recommendation(gap_type)}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["plan_tier"]].append(row)
    return {"gap_count": len(rows), "type_counts": {kind: sum(1 for row in rows if row["gap_type"] == kind) for kind in _TYPE_ORDER}, "by_plan_tier": [{"plan_tier": tier, "gap_count": len(items), "average_gap_score": round(sum(item["gap_score"] for item in items) / len(items), 1)} for tier, items in sorted(groups.items())]}


def _recommendations(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Add pricing and packaging metadata before exporting gaps."]
    recs = []
    if any(row["gap_type"] == "under_monetized" for row in rows):
        recs.append("Review low-tier high-value features for packaging or expansion motions.")
    if any(row["gap_type"] == "parity_risk" for row in rows):
        recs.append("Compare competitor packaging before enforcing premium-only access.")
    return recs or ["Collect more demand, value, and willingness-to-pay signal before changing packaging."]


def _recommendation(gap_type: str) -> str:
    return {"under_monetized": "Evaluate tier move, usage limit, or paid add-on.", "over_packaged": "Consider moving feature down or bundling with adoption drivers.", "parity_risk": "Validate competitive parity before packaging change.", "insufficient_signal": "Collect more usage, demand, and willingness-to-pay evidence."}[gap_type]


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


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")

"""Revenue leakage diagnostic export for commercial operations review.

CSV rendering emits one row per leakage item. Monetary categories are included
when their clamped value is positive; contract gap notes are included as
zero-amount audit rows so downstream reviewers can see non-quantified leakage.
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.revenue_leakage_diagnostic.v1"
KIND = "max.revenue_leakage_diagnostic"

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "none": 4}
_CATEGORY_LABELS = {
    "discount_leakage": "Discount leakage",
    "unbilled_usage": "Unbilled usage",
    "support_credits": "Support credits",
    "churn_risk": "Churn risk",
    "payment_failures": "Payment failures",
    "contract_gaps": "Contract gaps",
}
_CSV_FIELDS = [
    "idea_id",
    "title",
    "segment",
    "severity",
    "category",
    "category_label",
    "amount_usd",
    "total_leakage_usd",
    "note",
]


def build_revenue_leakage_diagnostic_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    """Build a revenue leakage diagnostic from buildable unit metadata."""
    rows = [_build_unit_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_SEVERITY_ORDER[row["severity"]], -row["total_leakage_usd"], row["idea_id"]))

    category_totals = _category_totals(rows)
    summary = _summary(rows, category_totals)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "revenue_leakage_diagnostic",
            "domain_filter": domain,
            "severity_thresholds_usd": {
                "critical": 50_000,
                "high": 10_000,
                "medium": 1_000,
                "low": 0.01,
            },
            "csv_grain": "one row per leakage item; contract gap notes are zero-amount audit items",
        },
        "leakage_rows": rows,
        "category_totals": category_totals,
        "summary": summary,
        "recommendations": _recommendations(rows, category_totals),
    }


def render_revenue_leakage_diagnostic_markdown(report: dict[str, Any]) -> str:
    """Render a revenue leakage diagnostic as Markdown."""
    summary = report.get("summary", {})
    lines = [
        "# Revenue Leakage Diagnostic",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Units reviewed: {summary.get('unit_count', 0)}",
        f"- Affected units: {summary.get('affected_unit_count', 0)}",
        f"- Total leakage: ${summary.get('total_leakage_usd', 0.0):,.0f}",
        f"- Highest severity: {summary.get('highest_severity', 'none')}",
        "",
        "## Leakage Rows",
        "",
    ]

    if report.get("leakage_rows"):
        lines.extend([
            "| Idea | Segment | Severity | Total Leakage | Top Category | Contract Gaps |",
            "|------|---------|----------|---------------|--------------|---------------|",
        ])
        for row in report["leakage_rows"]:
            lines.append(
                f"| {row['title']} | {row['segment']} | {row['severity']} | "
                f"${row['total_leakage_usd']:,.0f} | {row['top_category_label']} | "
                f"{len(row['contract_gap_notes'])} |"
            )
    else:
        lines.append("- No buildable units available. Add revenue metadata such as unbilled usage, support credits, payment failures, or churn risk to diagnose leakage.")

    lines.extend([
        "",
        "## Category Totals",
        "",
        "| Category | Amount | Units |",
        "|----------|--------|-------|",
    ])
    for row in report.get("category_totals", []):
        lines.append(f"| {row['category_label']} | ${row['amount_usd']:,.0f} | {row['unit_count']} |")

    lines.extend(["", "## Recommendations", ""])
    for recommendation in report.get("recommendations", []):
        lines.append(f"- {recommendation}")

    return "\n".join(lines).rstrip() + "\n"


def render_revenue_leakage_diagnostic_json(report: dict[str, Any]) -> str:
    """Render a revenue leakage diagnostic as stable formatted JSON."""
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_revenue_leakage_diagnostic_csv(report: dict[str, Any]) -> str:
    """Render leakage items as CSV."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_CSV_FIELDS)
    writer.writeheader()
    for row in report.get("leakage_rows", []):
        for item in row.get("leakage_items", []):
            writer.writerow({
                "idea_id": row["idea_id"],
                "title": row["title"],
                "segment": row["segment"],
                "severity": row["severity"],
                "category": item["category"],
                "category_label": item["category_label"],
                "amount_usd": item["amount_usd"],
                "total_leakage_usd": row["total_leakage_usd"],
                "note": item["note"],
            })
    return output.getvalue()


def _build_unit_row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    annual_contract_value = _number_from_metadata(
        metadata,
        ["annual_contract_value_usd", "arr_usd", "annual_revenue_usd", "contract_value_usd", "revenue_usd"],
        0.0,
    )
    discount_rate = _rate_from_metadata(metadata, ["discount_rate"], 0.0)
    breakdown = {
        "discount_leakage": round(annual_contract_value * discount_rate, 2),
        "unbilled_usage": _money_from_metadata(metadata, ["unbilled_usage_usd"]),
        "support_credits": _money_from_metadata(metadata, ["support_credits_usd"]),
        "churn_risk": _money_from_metadata(metadata, ["churn_risk_usd"]),
        "payment_failures": _money_from_metadata(metadata, ["payment_failures_usd"]),
        "contract_gaps": 0.0,
    }
    notes = _list_from_metadata(metadata, ["contract_gap_notes", "contract_gaps"])
    items = _leakage_items(breakdown, notes)
    total = round(sum(amount for category, amount in breakdown.items() if category != "contract_gaps"), 2)
    top_category = _top_category(breakdown)
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "segment": _segment(unit, metadata),
        "severity": _severity(total),
        "total_leakage_usd": total,
        "category_breakdown": breakdown,
        "top_category": top_category,
        "top_category_label": _CATEGORY_LABELS[top_category] if top_category else "None",
        "contract_gap_notes": notes,
        "leakage_items": items,
    }


def _leakage_items(breakdown: dict[str, float], notes: list[str]) -> list[dict[str, Any]]:
    items = [
        {
            "category": category,
            "category_label": _CATEGORY_LABELS[category],
            "amount_usd": amount,
            "note": "",
        }
        for category, amount in breakdown.items()
        if category != "contract_gaps" and amount > 0
    ]
    for note in notes:
        items.append({
            "category": "contract_gaps",
            "category_label": _CATEGORY_LABELS["contract_gaps"],
            "amount_usd": 0.0,
            "note": note,
        })
    items.sort(key=lambda item: (-item["amount_usd"], item["category"], item["note"]))
    return items


def _category_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, float] = defaultdict(float)
    unit_counts: Counter[str] = Counter()
    note_counts: Counter[str] = Counter()
    for row in rows:
        for category, amount in row["category_breakdown"].items():
            totals[category] += amount
            if amount > 0:
                unit_counts[category] += 1
        if row["contract_gap_notes"]:
            unit_counts["contract_gaps"] += 1
            note_counts["contract_gaps"] += len(row["contract_gap_notes"])

    category_rows = [
        {
            "category": category,
            "category_label": _CATEGORY_LABELS[category],
            "amount_usd": round(totals[category], 2),
            "unit_count": unit_counts[category],
            "note_count": note_counts[category],
        }
        for category in _CATEGORY_LABELS
        if totals[category] > 0 or unit_counts[category] > 0
    ]
    category_rows.sort(key=lambda row: (-row["amount_usd"], row["category"]))
    return category_rows


def _summary(rows: list[dict[str, Any]], category_totals: list[dict[str, Any]]) -> dict[str, Any]:
    severity_counts = Counter(row["severity"] for row in rows)
    total = round(sum(row["total_leakage_usd"] for row in rows), 2)
    highest = "none"
    for severity in ("critical", "high", "medium", "low"):
        if severity_counts[severity]:
            highest = severity
            break
    return {
        "unit_count": len(rows),
        "affected_unit_count": sum(1 for row in rows if row["total_leakage_usd"] > 0 or row["contract_gap_notes"]),
        "total_leakage_usd": total,
        "average_leakage_usd": round(total / len(rows), 2) if rows else 0.0,
        "highest_severity": highest,
        "severity_counts": {severity: severity_counts.get(severity, 0) for severity in _SEVERITY_ORDER},
        "top_category": category_totals[0]["category"] if category_totals else None,
        "top_category_label": category_totals[0]["category_label"] if category_totals else None,
    }


def _recommendations(rows: list[dict[str, Any]], category_totals: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Add revenue leakage metadata to buildable units before running the diagnostic."]
    affected = [row for row in rows if row["total_leakage_usd"] > 0 or row["contract_gap_notes"]]
    if not affected:
        return ["No quantified leakage detected. Keep monitoring billing, credits, payment, churn, and contract gap metadata."]

    recommendations = []
    if category_totals:
        top = category_totals[0]
        recommendations.append(f"Prioritize {top['category_label'].lower()} remediation across {top['unit_count']} affected unit(s).")
    high_risk = [row for row in rows if row["severity"] in {"critical", "high"}]
    if high_risk:
        recommendations.append(f"Open executive review for {len(high_risk)} high-severity revenue leakage unit(s).")
    if any(row["contract_gap_notes"] for row in rows):
        recommendations.append("Convert contract gap notes into quantified owners, recovery amounts, and renewal actions.")
    return recommendations


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    if isinstance(metadata, dict):
        return metadata
    extra = getattr(unit, "extra", None)
    if isinstance(extra, dict):
        return extra
    return {}


def _money_from_metadata(metadata: dict[str, Any], keys: list[str]) -> float:
    return round(max(_number_from_metadata(metadata, keys, 0.0), 0.0), 2)


def _number_from_metadata(metadata: dict[str, Any], keys: list[str], default: float) -> float:
    for key in keys:
        if key in metadata:
            return _coerce_float(metadata[key], default)
    for nested_key in ("revenue", "financials", "billing", "commercial"):
        nested = metadata.get(nested_key)
        if isinstance(nested, dict):
            for key in keys:
                if key in nested:
                    return _coerce_float(nested[key], default)
    return default


def _string_from_metadata(metadata: dict[str, Any], keys: list[str], default: str) -> str:
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return str(value).strip()
    for nested_key in ("revenue", "financials", "billing", "commercial"):
        nested = metadata.get(nested_key)
        if isinstance(nested, dict):
            for key in keys:
                value = nested.get(key)
                if value not in (None, ""):
                    return str(value).strip()
    return default


def _list_from_metadata(metadata: dict[str, Any], keys: list[str]) -> list[str]:
    value: Any = None
    for key in keys:
        if key in metadata:
            value = metadata[key]
            break
    if value is None:
        for nested_key in ("revenue", "financials", "billing", "commercial"):
            nested = metadata.get(nested_key)
            if isinstance(nested, dict):
                for key in keys:
                    if key in nested:
                        value = nested[key]
                        break
            if value is not None:
                break
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _rate_from_metadata(metadata: dict[str, Any], keys: list[str], default: float) -> float:
    value = max(_number_from_metadata(metadata, keys, default), 0.0)
    if value > 1:
        value = value / 100
    return min(value, 1.0)


def _coerce_float(value: Any, default: float) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _segment(unit: Any, metadata: dict[str, Any]) -> str:
    explicit = _string_from_metadata(metadata, ["segment", "market_segment", "customer_segment"], "")
    return explicit or str(getattr(unit, "domain", "") or getattr(unit, "category", "") or "general")


def _severity(amount: float) -> str:
    if amount >= 50_000:
        return "critical"
    if amount >= 10_000:
        return "high"
    if amount >= 1_000:
        return "medium"
    if amount > 0:
        return "low"
    return "none"


def _top_category(breakdown: dict[str, float]) -> str | None:
    ranked = sorted(
        ((category, amount) for category, amount in breakdown.items() if category != "contract_gaps" and amount > 0),
        key=lambda item: (-item[1], item[0]),
    )
    return ranked[0][0] if ranked else None

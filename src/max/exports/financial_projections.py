"""Financial projections export for buildable units.

Generates lightweight ROI models, cost projections, and revenue estimates from
buildable unit metadata for investment and portfolio planning.
"""

from __future__ import annotations

import csv
import io
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.financial_projections.v1"
KIND = "max.financial_projections"

_DEFAULT_DEV_COST = 50_000.0
_DEFAULT_INFRA_COST = 1_000.0
_DEFAULT_MAINTENANCE_COST = 2_500.0
_DEFAULT_MONTHLY_REVENUE = 10_000.0

_PROJECTION_FIELDS = [
    "idea_id",
    "title",
    "estimated_dev_cost",
    "estimated_monthly_cost",
    "projected_monthly_revenue",
    "payback_months",
    "roi_12_month",
    "confidence",
]


def build_financial_projections(
    store: Store,
    domain: str | None = None,
) -> dict[str, Any]:
    """Build ROI projections for buildable units in the store."""
    units = store.get_buildable_units(limit=1000, domain=domain)

    projections: list[dict[str, Any]] = []
    groups: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "projection_count": 0,
            "estimated_dev_cost": 0.0,
            "estimated_monthly_cost": 0.0,
            "projected_monthly_revenue": 0.0,
            "net_12_month": 0.0,
        }
    )

    for unit in units:
        costs = _estimate_costs(unit)
        revenue = _estimate_monthly_revenue(unit)
        roi = _calculate_roi(costs, revenue)
        confidence = _estimate_confidence(unit, costs, revenue)
        projection = {
            "idea_id": str(getattr(unit, "id", "")),
            "title": str(getattr(unit, "title", "Untitled")),
            "estimated_dev_cost": costs["development_cost"],
            "estimated_monthly_cost": costs["monthly_cost"],
            "projected_monthly_revenue": round(revenue, 2),
            "payback_months": roi["payback_months"],
            "roi_12_month": roi["roi_12_month"],
            "confidence": confidence,
        }
        projections.append(projection)

        group_name = _group_name(unit)
        group = groups[group_name]
        group["projection_count"] += 1
        group["estimated_dev_cost"] += projection["estimated_dev_cost"]
        group["estimated_monthly_cost"] += projection["estimated_monthly_cost"]
        group["projected_monthly_revenue"] += projection["projected_monthly_revenue"]
        group["net_12_month"] += roi["net_profit"]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "financial_projections",
            "domain_filter": domain,
        },
        "projection_count": len(projections),
        "projections": projections,
        "portfolio_summary": _build_portfolio_summary(projections, groups),
    }


def render_financial_projections_markdown(report: dict[str, Any]) -> str:
    """Render a financial projections report as Markdown."""
    summary = report.get("portfolio_summary", {})
    lines = [
        "# Financial Projections",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        f"Total projections: {report.get('projection_count', 0)}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total development cost | ${summary.get('total_dev_cost', 0):,.0f} |",
        f"| Total monthly cost | ${summary.get('total_monthly_cost', 0):,.0f} |",
        f"| Projected monthly revenue | ${summary.get('total_monthly_revenue', 0):,.0f} |",
        f"| 12-month net profit | ${summary.get('net_profit_12_month', 0):,.0f} |",
        f"| Average 12-month ROI | {summary.get('average_roi_12_month', 0):.2f} |",
        "",
        "## Per-Idea Details",
        "",
        "| Idea | Dev Cost | Monthly Cost | Monthly Revenue | Payback | ROI | Confidence |",
        "|------|----------|--------------|-----------------|---------|-----|------------|",
    ]

    for projection in report.get("projections", []):
        payback = projection["payback_months"]
        payback_text = "n/a" if payback is None else f"{payback:.1f} mo"
        lines.append(
            f"| {projection['title']} | "
            f"${projection['estimated_dev_cost']:,.0f} | "
            f"${projection['estimated_monthly_cost']:,.0f} | "
            f"${projection['projected_monthly_revenue']:,.0f} | "
            f"{payback_text} | "
            f"{projection['roi_12_month']:.2f} | "
            f"{projection['confidence']} |"
        )

    lines.extend([
        "",
        "## Portfolio Totals",
        "",
        f"- Development cost: ${summary.get('total_dev_cost', 0):,.0f}",
        f"- Monthly operating cost: ${summary.get('total_monthly_cost', 0):,.0f}",
        f"- Monthly revenue: ${summary.get('total_monthly_revenue', 0):,.0f}",
        f"- Median payback: {_format_months(summary.get('median_payback_months'))}",
        "",
        "## Aggregation",
        "",
        "| Segment | Count | Dev Cost | Monthly Cost | Monthly Revenue | 12-Month Net |",
        "|---------|-------|----------|--------------|-----------------|--------------|",
    ])
    for segment in summary.get("by_segment", []):
        lines.append(
            f"| {segment['segment']} | {segment['projection_count']} | "
            f"${segment['estimated_dev_cost']:,.0f} | "
            f"${segment['estimated_monthly_cost']:,.0f} | "
            f"${segment['projected_monthly_revenue']:,.0f} | "
            f"${segment['net_12_month']:,.0f} |"
        )

    return "\n".join(lines).rstrip() + "\n"


def render_financial_projections_json(report: dict[str, Any]) -> str:
    """Render a financial projections report as formatted JSON."""
    return json.dumps(report, indent=2, default=str)


def render_financial_projections_csv(report: dict[str, Any]) -> str:
    """Render projection rows as CSV."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_PROJECTION_FIELDS)
    writer.writeheader()
    for projection in report.get("projections", []):
        writer.writerow({field: projection.get(field) for field in _PROJECTION_FIELDS})
    return output.getvalue()


def _estimate_costs(unit: Any) -> dict[str, float]:
    """Extract or default cost fields from buildable unit metadata."""
    metadata = _metadata(unit)
    development_cost = _number_from_metadata(
        metadata,
        ["development_cost", "dev_cost", "estimated_dev_cost", "build_cost"],
        _DEFAULT_DEV_COST,
    )
    infrastructure_cost = _number_from_metadata(
        metadata,
        ["infrastructure_cost", "infra_cost", "monthly_infrastructure_cost"],
        _DEFAULT_INFRA_COST,
    )
    maintenance_cost = _number_from_metadata(
        metadata,
        ["maintenance_cost", "monthly_maintenance_cost", "support_cost"],
        _DEFAULT_MAINTENANCE_COST,
    )
    monthly_cost = infrastructure_cost + maintenance_cost
    return {
        "development_cost": round(development_cost, 2),
        "infrastructure_cost": round(infrastructure_cost, 2),
        "maintenance_cost": round(maintenance_cost, 2),
        "monthly_cost": round(monthly_cost, 2),
    }


def _calculate_roi(
    costs: dict[str, float],
    revenue: float,
    months: int = 12,
) -> dict[str, float | None]:
    """Calculate simple payback and ROI over a projection horizon."""
    dev_cost = float(costs.get("development_cost", 0.0))
    monthly_cost = float(costs.get("monthly_cost", 0.0))
    monthly_profit = revenue - monthly_cost
    total_cost = dev_cost + (monthly_cost * months)
    total_revenue = revenue * months
    net_profit = total_revenue - total_cost
    payback_months = None
    if monthly_profit > 0:
        payback_months = round(dev_cost / monthly_profit, 2)
    roi = 0.0 if total_cost <= 0 else net_profit / total_cost
    return {
        "payback_months": payback_months,
        "roi_12_month": round(roi, 4),
        "net_profit": round(net_profit, 2),
        "monthly_profit": round(monthly_profit, 2),
    }


def _estimate_monthly_revenue(unit: Any) -> float:
    metadata = _metadata(unit)
    explicit = _number_from_metadata(
        metadata,
        [
            "projected_monthly_revenue",
            "monthly_revenue",
            "estimated_monthly_revenue",
            "revenue_estimate",
        ],
        math.nan,
    )
    if math.isfinite(explicit):
        return round(explicit, 2)

    signal_count = len(getattr(unit, "evidence_signals", []) or [])
    quality_score = _coerce_float(getattr(unit, "quality_score", 0.0), 0.0)
    usefulness_score = _coerce_float(getattr(unit, "usefulness_score", 0.0), 0.0)
    confidence_multiplier = 1.0 + min(max(quality_score + usefulness_score, 0.0), 2.0) * 0.25
    signal_multiplier = 1.0 + min(signal_count, 10) * 0.08
    return round(_DEFAULT_MONTHLY_REVENUE * confidence_multiplier * signal_multiplier, 2)


def _build_portfolio_summary(
    projections: list[dict[str, Any]],
    groups: dict[str, dict[str, float]],
) -> dict[str, Any]:
    total_dev = sum(p["estimated_dev_cost"] for p in projections)
    total_monthly_cost = sum(p["estimated_monthly_cost"] for p in projections)
    total_revenue = sum(p["projected_monthly_revenue"] for p in projections)
    roi_values = [p["roi_12_month"] for p in projections]
    paybacks = sorted(p["payback_months"] for p in projections if p["payback_months"] is not None)
    net_profit = sum(group["net_12_month"] for group in groups.values())
    return {
        "total_dev_cost": round(total_dev, 2),
        "total_monthly_cost": round(total_monthly_cost, 2),
        "total_monthly_revenue": round(total_revenue, 2),
        "net_profit_12_month": round(net_profit, 2),
        "average_roi_12_month": round(sum(roi_values) / len(roi_values), 4) if roi_values else 0.0,
        "median_payback_months": _median(paybacks),
        "by_segment": [
            {"segment": segment, **{k: round(v, 2) for k, v in values.items()}}
            for segment, values in sorted(groups.items())
        ],
    }


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    if isinstance(metadata, dict):
        return metadata
    extra = getattr(unit, "extra", None)
    if isinstance(extra, dict):
        return extra
    return {}


def _number_from_metadata(
    metadata: dict[str, Any],
    keys: list[str],
    default: float,
) -> float:
    for key in keys:
        if key in metadata:
            return _coerce_float(metadata[key], default)
    financials = metadata.get("financials")
    if isinstance(financials, dict):
        for key in keys:
            if key in financials:
                return _coerce_float(financials[key], default)
    return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _estimate_confidence(unit: Any, costs: dict[str, float], revenue: float) -> str:
    metadata = _metadata(unit)
    explicit = str(metadata.get("confidence", "")).lower()
    if explicit in {"low", "medium", "high"}:
        return explicit
    score = 0.0
    if costs["development_cost"] != _DEFAULT_DEV_COST:
        score += 0.25
    if revenue != _DEFAULT_MONTHLY_REVENUE:
        score += 0.25
    score += min(len(getattr(unit, "evidence_signals", []) or []), 5) * 0.08
    score += min(max(_coerce_float(getattr(unit, "quality_score", 0.0), 0.0), 0.0), 1.0) * 0.2
    if score >= 0.65:
        return "high"
    if score >= 0.3:
        return "medium"
    return "low"


def _group_name(unit: Any) -> str:
    return str(getattr(unit, "domain", "") or getattr(unit, "category", "") or "general")


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    midpoint = len(values) // 2
    if len(values) % 2:
        return values[midpoint]
    return round((values[midpoint - 1] + values[midpoint]) / 2, 2)


def _format_months(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.1f} months"

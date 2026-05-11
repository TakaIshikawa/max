"""Pricing sensitivity export for revenue scenario planning."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.pricing_sensitivity.v1"
KIND = "max.pricing_sensitivity"

_DEFAULT_BASE_PRICE = 49.0
_DEFAULT_TARGET_USERS = 1_000.0
_DEFAULT_CONVERSION_RATE = 0.05
_DEFAULT_CHURN_RATE = 0.03
_DEFAULT_EXPANSION_RATE = 0.02

_SCENARIO_ASSUMPTIONS = {
    "baseline": {
        "price_multiplier": 1.0,
        "conversion_multiplier": 1.0,
        "churn_multiplier": 1.0,
        "expansion_multiplier": 1.0,
    },
    "downside": {
        "price_multiplier": 0.9,
        "conversion_multiplier": 0.75,
        "churn_multiplier": 1.35,
        "expansion_multiplier": 0.5,
    },
    "upside": {
        "price_multiplier": 1.1,
        "conversion_multiplier": 1.25,
        "churn_multiplier": 0.75,
        "expansion_multiplier": 1.5,
    },
}

_SCENARIO_ORDER = {"baseline": 0, "downside": 1, "upside": 2}

_SCENARIO_FIELDS = [
    "idea_id",
    "title",
    "segment",
    "scenario",
    "base_price",
    "target_users",
    "conversion_rate",
    "converted_users",
    "churn_rate",
    "retained_users",
    "expansion_rate",
    "monthly_revenue",
    "annual_revenue",
    "confidence",
]


def build_pricing_sensitivity_report(
    store: Store,
    domain: str | None = None,
) -> dict[str, Any]:
    """Build price, conversion, and churn sensitivity scenarios for buildable units."""
    units = store.get_buildable_units(limit=1000, domain=domain)
    scenarios: list[dict[str, Any]] = []

    for unit in units:
        scenarios.extend(_build_unit_scenarios(unit))

    scenarios.sort(key=lambda row: (row["segment"], row["idea_id"], _SCENARIO_ORDER[row["scenario"]]))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "pricing_sensitivity",
            "domain_filter": domain,
            "defaults": {
                "base_price": _DEFAULT_BASE_PRICE,
                "target_users": _DEFAULT_TARGET_USERS,
                "conversion_rate": _DEFAULT_CONVERSION_RATE,
                "churn_rate": _DEFAULT_CHURN_RATE,
                "expansion_rate": _DEFAULT_EXPANSION_RATE,
            },
        },
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "portfolio_summary": _build_portfolio_summary(scenarios),
    }


def render_pricing_sensitivity_markdown(report: dict[str, Any]) -> str:
    """Render a pricing sensitivity report as Markdown."""
    summary = report.get("portfolio_summary", {})
    totals = summary.get("scenario_totals", [])
    lines = [
        "# Pricing Sensitivity",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        f"Total scenarios: {report.get('scenario_count', 0)}",
        "",
        "## Scenario Totals",
        "",
        "| Scenario | Units | Converted Users | Retained Users | Monthly Revenue | Annual Revenue |",
        "|----------|-------|-----------------|----------------|-----------------|----------------|",
    ]
    for total in totals:
        lines.append(
            f"| {total['scenario']} | {total['unit_count']} | "
            f"{total['converted_users']:,.0f} | {total['retained_users']:,.0f} | "
            f"${total['monthly_revenue']:,.0f} | ${total['annual_revenue']:,.0f} |"
        )

    lines.extend([
        "",
        "## Unit Scenarios",
        "",
    ])
    if report.get("scenarios"):
        lines.extend([
            "| Idea | Segment | Scenario | Price | Conversion | Churn | Expansion | Monthly Revenue | Confidence |",
            "|------|---------|----------|-------|------------|-------|-----------|-----------------|------------|",
        ])
        for scenario in report["scenarios"]:
            lines.append(
                f"| {scenario['title']} | {scenario['segment']} | {scenario['scenario']} | "
                f"${scenario['base_price']:,.2f} | {scenario['conversion_rate']:.1%} | "
                f"{scenario['churn_rate']:.1%} | {scenario['expansion_rate']:.1%} | "
                f"${scenario['monthly_revenue']:,.0f} | {scenario['confidence']} |"
            )
    else:
        lines.append("- No buildable units available. Add pricing metadata or buildable units to model revenue sensitivity.")

    lines.extend([
        "",
        "## Segment Rollup",
        "",
        "| Segment | Scenario | Units | Monthly Revenue | Annual Revenue |",
        "|---------|----------|-------|-----------------|----------------|",
    ])
    for row in summary.get("by_segment", []):
        lines.append(
            f"| {row['segment']} | {row['scenario']} | {row['unit_count']} | "
            f"${row['monthly_revenue']:,.0f} | ${row['annual_revenue']:,.0f} |"
        )

    return "\n".join(lines).rstrip() + "\n"


def render_pricing_sensitivity_json(report: dict[str, Any]) -> str:
    """Render a pricing sensitivity report as stable formatted JSON."""
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_pricing_sensitivity_csv(report: dict[str, Any]) -> str:
    """Render pricing sensitivity scenarios as CSV."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_SCENARIO_FIELDS)
    writer.writeheader()
    for scenario in report.get("scenarios", []):
        writer.writerow({field: scenario.get(field) for field in _SCENARIO_FIELDS})
    return output.getvalue()


def _build_unit_scenarios(unit: Any) -> list[dict[str, Any]]:
    metadata = _metadata(unit)
    base_price = _non_negative(_number_from_metadata(metadata, ["base_price", "price", "monthly_price"], _DEFAULT_BASE_PRICE))
    target_users = _non_negative(_number_from_metadata(metadata, ["target_users", "addressable_users", "users"], _DEFAULT_TARGET_USERS))
    conversion_rate = _rate_from_metadata(metadata, ["conversion_rate", "trial_conversion_rate"], _DEFAULT_CONVERSION_RATE)
    churn_rate = _rate_from_metadata(metadata, ["churn_rate", "monthly_churn_rate"], _DEFAULT_CHURN_RATE)
    expansion_rate = _rate_from_metadata(metadata, ["expansion_rate", "upsell_rate"], _DEFAULT_EXPANSION_RATE)
    confidence = _confidence(unit, metadata)
    segment = _segment(unit, metadata)

    rows: list[dict[str, Any]] = []
    for scenario_name in ("baseline", "downside", "upside"):
        assumptions = _SCENARIO_ASSUMPTIONS[scenario_name]
        scenario_price = base_price * assumptions["price_multiplier"]
        scenario_conversion = _bounded_rate(conversion_rate * assumptions["conversion_multiplier"])
        scenario_churn = _bounded_rate(churn_rate * assumptions["churn_multiplier"])
        scenario_expansion = _bounded_rate(expansion_rate * assumptions["expansion_multiplier"])
        converted_users = target_users * scenario_conversion
        retained_users = converted_users * (1 - scenario_churn)
        expanded_revenue_multiplier = 1 + scenario_expansion
        monthly_revenue = retained_users * scenario_price * expanded_revenue_multiplier
        rows.append({
            "idea_id": str(getattr(unit, "id", "")),
            "title": str(getattr(unit, "title", "Untitled")),
            "segment": segment,
            "scenario": scenario_name,
            "base_price": round(scenario_price, 2),
            "target_users": round(target_users, 2),
            "conversion_rate": round(scenario_conversion, 4),
            "converted_users": round(converted_users, 2),
            "churn_rate": round(scenario_churn, 4),
            "retained_users": round(retained_users, 2),
            "expansion_rate": round(scenario_expansion, 4),
            "monthly_revenue": round(monthly_revenue, 2),
            "annual_revenue": round(monthly_revenue * 12, 2),
            "confidence": confidence,
        })
    return rows


def _build_portfolio_summary(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "unit_count": len({row["idea_id"] for row in scenarios}),
        "scenario_totals": _rollups(scenarios, "scenario"),
        "by_segment": _rollups(scenarios, "segment", include_scenario=True),
        "baseline_monthly_revenue": _scenario_total(scenarios, "baseline", "monthly_revenue"),
        "downside_monthly_revenue": _scenario_total(scenarios, "downside", "monthly_revenue"),
        "upside_monthly_revenue": _scenario_total(scenarios, "upside", "monthly_revenue"),
    }


def _rollups(scenarios: list[dict[str, Any]], key: str, *, include_scenario: bool = False) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {
            "unit_count": 0,
            "converted_users": 0.0,
            "retained_users": 0.0,
            "monthly_revenue": 0.0,
            "annual_revenue": 0.0,
        }
    )
    for row in scenarios:
        group_key = (str(row[key]), row["scenario"] if include_scenario else "")
        group = groups[group_key]
        group["unit_count"] += 1
        group["converted_users"] += row["converted_users"]
        group["retained_users"] += row["retained_users"]
        group["monthly_revenue"] += row["monthly_revenue"]
        group["annual_revenue"] += row["annual_revenue"]

    rows: list[dict[str, Any]] = []
    for (name, scenario), values in sorted(groups.items(), key=lambda item: (item[0][0], _SCENARIO_ORDER.get(item[0][1], 0))):
        row = {
            key: name,
            "unit_count": int(values["unit_count"]),
            "converted_users": round(values["converted_users"], 2),
            "retained_users": round(values["retained_users"], 2),
            "monthly_revenue": round(values["monthly_revenue"], 2),
            "annual_revenue": round(values["annual_revenue"], 2),
        }
        if include_scenario:
            row["scenario"] = scenario
        rows.append(row)

    if key == "scenario":
        rows.sort(key=lambda row: _SCENARIO_ORDER.get(row["scenario"], 99))
    return rows


def _scenario_total(scenarios: list[dict[str, Any]], scenario: str, field: str) -> float:
    return round(sum(row[field] for row in scenarios if row["scenario"] == scenario), 2)


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    if isinstance(metadata, dict):
        return metadata
    extra = getattr(unit, "extra", None)
    if isinstance(extra, dict):
        return extra
    return {}


def _number_from_metadata(metadata: dict[str, Any], keys: list[str], default: float) -> float:
    for key in keys:
        if key in metadata:
            return _coerce_float(metadata[key], default)
    for nested_key in ("pricing", "financials", "revenue"):
        nested = metadata.get(nested_key)
        if isinstance(nested, dict):
            for key in keys:
                if key in nested:
                    return _coerce_float(nested[key], default)
    return default


def _string_from_metadata(metadata: dict[str, Any], keys: list[str], default: str) -> str:
    for key in keys:
        value = metadata.get(key)
        if value is not None and value != "":
            return str(value).strip()
    for nested_key in ("pricing", "financials", "revenue"):
        nested = metadata.get(nested_key)
        if isinstance(nested, dict):
            for key in keys:
                value = nested.get(key)
                if value is not None and value != "":
                    return str(value).strip()
    return default


def _rate_from_metadata(metadata: dict[str, Any], keys: list[str], default: float) -> float:
    value = _number_from_metadata(metadata, keys, default)
    if value > 1:
        value = value / 100
    return _bounded_rate(value)


def _coerce_float(value: Any, default: float) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _bounded_rate(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def _non_negative(value: float) -> float:
    return max(value, 0.0)


def _segment(unit: Any, metadata: dict[str, Any]) -> str:
    explicit = _string_from_metadata(metadata, ["segment", "market_segment"], "")
    return explicit or str(getattr(unit, "domain", "") or getattr(unit, "category", "") or "general")


def _confidence(unit: Any, metadata: dict[str, Any]) -> str:
    explicit = _string_from_metadata(metadata, ["confidence"], "").lower()
    if explicit in {"low", "medium", "high"}:
        return explicit

    explicit_fields = sum(
        1
        for key in ("base_price", "target_users", "conversion_rate", "churn_rate", "expansion_rate")
        if key in metadata
    )
    nested = metadata.get("pricing")
    if isinstance(nested, dict):
        explicit_fields += sum(
            1
            for key in ("base_price", "target_users", "conversion_rate", "churn_rate", "expansion_rate")
            if key in nested
        )
    evidence_count = len(getattr(unit, "evidence_signals", []) or [])
    quality_score = _bounded_rate(_coerce_float(getattr(unit, "quality_score", 0.0), 0.0))
    score = explicit_fields * 0.12 + min(evidence_count, 5) * 0.06 + quality_score * 0.2
    if score >= 0.65:
        return "high"
    if score >= 0.3:
        return "medium"
    return "low"

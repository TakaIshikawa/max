"""Pricing discount leakage report export."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.pricing_discount_leakage_report.v1"
KIND = "max.pricing_discount_leakage_report"

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "none": 3}


def build_pricing_discount_leakage_report_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_deal_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_SEVERITY_ORDER[row["leakage_level"]], -row["estimated_impact_usd"], row["segment"], row["idea_id"]))
    segments = _segments(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "pricing_discount_leakage_report", "domain_filter": domain},
        "summary": _summary(rows),
        "leakage_segments": segments,
        "deal_rows": rows,
        "recommendations": _recommendations(segments),
    }


def render_pricing_discount_leakage_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Pricing Discount Leakage Report", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Leakage Segments", ""]
    if report.get("leakage_segments"):
        lines.extend(["| Segment | Level | Impact | Evidence | Recommendation |", "|---------|-------|--------|----------|----------------|"])
        for row in report["leakage_segments"]:
            lines.append(f"| {_md(row['segment'])} | {row['leakage_level']} | ${row['estimated_impact_usd']:,.0f} | {row['evidence_count']} | {_md(row['remediation_recommendation'])} |")
    else:
        lines.append("- No discount leakage detected.")
    return "\n".join(lines).rstrip() + "\n"


def render_pricing_discount_leakage_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def _deal_row(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None) if isinstance(getattr(unit, "metadata", None), dict) else {}
    list_price = _number(metadata.get("list_price_usd") or metadata.get("annual_contract_value_usd") or metadata.get("arr_usd"))
    actual = _number(metadata.get("actual_price_usd") or metadata.get("net_revenue_usd") or metadata.get("contract_value_usd"))
    rate = _rate(metadata.get("discount_rate"))
    if list_price and actual:
        impact = max(0.0, list_price - actual)
        rate = impact / list_price if list_price else rate
    else:
        impact = max(0.0, list_price * rate)
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "segment": _text(metadata.get("segment") or metadata.get("buyer_segment") or "unknown"),
        "discount_rate": round(rate, 4),
        "estimated_impact_usd": round(impact, 2),
        "leakage_level": _level(rate, impact),
        "evidence_references": _list(metadata.get("evidence_references") or metadata.get("contract_notes") or metadata.get("invoice_ids")),
    }


def _segments(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["estimated_impact_usd"] > 0:
            grouped[row["segment"]].append(row)
    segments = []
    for segment, items in grouped.items():
        impact = round(sum(item["estimated_impact_usd"] for item in items), 2)
        max_rate = max(item["discount_rate"] for item in items)
        segments.append({
            "segment": segment,
            "leakage_level": _level(max_rate, impact),
            "estimated_impact_usd": impact,
            "evidence_count": sum(max(1, len(item["evidence_references"])) for item in items),
            "deal_count": len(items),
            "remediation_recommendation": _recommendation(_level(max_rate, impact), segment),
        })
    return sorted(segments, key=lambda row: (_SEVERITY_ORDER[row["leakage_level"]], -row["estimated_impact_usd"], row["segment"]))


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "deal_count": len(rows),
        "total_estimated_impact_usd": round(sum(row["estimated_impact_usd"] for row in rows), 2),
        "level_counts": {level: sum(1 for row in rows if row["leakage_level"] == level) for level in ("high", "medium", "low", "none")},
    }


def _recommendations(segments: list[dict[str, Any]]) -> list[str]:
    if not segments:
        return ["Keep discount evidence attached to pricing and contract records."]
    return [segments[0]["remediation_recommendation"]]


def _level(rate: float, impact: float) -> str:
    if rate >= 0.3 or impact >= 50_000:
        return "high"
    if rate >= 0.15 or impact >= 10_000:
        return "medium"
    if rate > 0 or impact > 0:
        return "low"
    return "none"


def _recommendation(level: str, segment: str) -> str:
    return f"{'Require approval controls for' if level == 'high' else 'Review'} {segment} discounting before renewal or close."


def _number(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _rate(value: Any) -> float:
    rate = _number(value)
    return rate / 100 if rate > 1 else rate


def _list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    return [_text(value)] if _text(value) else []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")

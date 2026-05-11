"""Sales pipeline forecast export for opportunity conversion planning."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.sales_pipeline_forecast.v1"
KIND = "max.sales_pipeline_forecast"

_DEFAULT_DEAL_SIZE = 25_000.0
_STAGE_PROBABILITIES = {
    "discovery": 0.2,
    "qualified": 0.35,
    "proposal": 0.55,
    "negotiation": 0.7,
    "closed_won": 1.0,
    "closed_lost": 0.0,
}
_STAGE_ORDER = {
    "discovery": 0,
    "qualified": 1,
    "proposal": 2,
    "negotiation": 3,
    "closed_won": 4,
    "closed_lost": 5,
}
_OPPORTUNITY_FIELDS = [
    "idea_id",
    "title",
    "stage",
    "deal_size",
    "probability",
    "expected_close_month",
    "weighted_value",
    "segment",
    "confidence",
]


def build_sales_pipeline_forecast(
    store: Store,
    domain: str | None = None,
) -> dict[str, Any]:
    """Build a sales pipeline forecast from buildable unit metadata."""
    units = store.get_buildable_units(limit=1000, domain=domain)
    generated_at = datetime.now(timezone.utc)
    opportunities = [_build_opportunity(unit, generated_at) for unit in units]
    opportunities.sort(
        key=lambda row: (
            row["expected_close_month"],
            _STAGE_ORDER.get(row["stage"], 99),
            row["segment"],
            row["idea_id"],
        )
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": generated_at.isoformat(),
        "source": {
            "project": "max",
            "entity_type": "sales_pipeline_forecast",
            "domain_filter": domain,
        },
        "opportunity_count": len(opportunities),
        "opportunities": opportunities,
        "pipeline_summary": _build_pipeline_summary(opportunities),
    }


def render_sales_pipeline_forecast_markdown(report: dict[str, Any]) -> str:
    """Render a sales pipeline forecast as Markdown."""
    summary = report.get("pipeline_summary", {})
    lines = [
        "# Sales Pipeline Forecast",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        f"Total opportunities: {report.get('opportunity_count', 0)}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total deal value | ${summary.get('total_deal_value', 0):,.0f} |",
        f"| Weighted pipeline value | ${summary.get('total_weighted_value', 0):,.0f} |",
        f"| Average probability | {summary.get('average_probability', 0.0):.1%} |",
        "",
        "## Opportunities",
        "",
    ]

    if report.get("opportunities"):
        lines.extend([
            "| Idea | Stage | Deal Size | Probability | Close Month | Weighted Value | Segment | Confidence |",
            "|------|-------|-----------|-------------|-------------|----------------|---------|------------|",
        ])
        for opportunity in report["opportunities"]:
            lines.append(
                f"| {opportunity['title']} | {opportunity['stage']} | "
                f"${opportunity['deal_size']:,.0f} | "
                f"{opportunity['probability']:.0%} | "
                f"{opportunity['expected_close_month']} | "
                f"${opportunity['weighted_value']:,.0f} | "
                f"{opportunity['segment']} | {opportunity['confidence']} |"
            )
    else:
        lines.append("- No opportunities available. Add buildable units or pipeline metadata to forecast conversion value.")

    lines.extend([
        "",
        "## Stage Rollup",
        "",
        "| Stage | Count | Deal Value | Weighted Value | Average Probability |",
        "|-------|-------|------------|----------------|---------------------|",
    ])
    for stage in summary.get("by_stage", []):
        lines.append(
            f"| {stage['stage']} | {stage['opportunity_count']} | "
            f"${stage['total_deal_value']:,.0f} | "
            f"${stage['total_weighted_value']:,.0f} | "
            f"{stage['average_probability']:.0%} |"
        )

    lines.extend([
        "",
        "## Segment Rollup",
        "",
        "| Segment | Count | Deal Value | Weighted Value | Average Probability |",
        "|---------|-------|------------|----------------|---------------------|",
    ])
    for segment in summary.get("by_segment", []):
        lines.append(
            f"| {segment['segment']} | {segment['opportunity_count']} | "
            f"${segment['total_deal_value']:,.0f} | "
            f"${segment['total_weighted_value']:,.0f} | "
            f"{segment['average_probability']:.0%} |"
        )

    return "\n".join(lines).rstrip() + "\n"


def render_sales_pipeline_forecast_json(report: dict[str, Any]) -> str:
    """Render a sales pipeline forecast as stable formatted JSON."""
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_sales_pipeline_forecast_csv(report: dict[str, Any]) -> str:
    """Render sales pipeline opportunities as CSV."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_OPPORTUNITY_FIELDS)
    writer.writeheader()
    for opportunity in report.get("opportunities", []):
        writer.writerow({field: opportunity.get(field) for field in _OPPORTUNITY_FIELDS})
    return output.getvalue()


def _build_opportunity(unit: Any, generated_at: datetime) -> dict[str, Any]:
    metadata = _metadata(unit)
    stage = _stage(unit, metadata)
    deal_size = _deal_size(unit, metadata)
    probability = _probability(metadata, stage)
    expected_close_month = _expected_close_month(metadata, stage, generated_at)
    weighted_value = round(deal_size * probability, 2)
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "stage": stage,
        "deal_size": deal_size,
        "probability": probability,
        "expected_close_month": expected_close_month,
        "weighted_value": weighted_value,
        "segment": _segment(unit, metadata),
        "confidence": _confidence(unit, metadata),
    }


def _build_pipeline_summary(opportunities: list[dict[str, Any]]) -> dict[str, Any]:
    total_deal_value = sum(row["deal_size"] for row in opportunities)
    total_weighted_value = sum(row["weighted_value"] for row in opportunities)
    average_probability = (
        sum(row["probability"] for row in opportunities) / len(opportunities)
        if opportunities
        else 0.0
    )
    return {
        "opportunity_count": len(opportunities),
        "total_deal_value": round(total_deal_value, 2),
        "total_weighted_value": round(total_weighted_value, 2),
        "average_probability": round(average_probability, 4),
        "by_stage": _rollups(opportunities, "stage"),
        "by_segment": _rollups(opportunities, "segment"),
    }


def _rollups(opportunities: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "opportunity_count": 0,
            "total_deal_value": 0.0,
            "total_weighted_value": 0.0,
            "probability_total": 0.0,
        }
    )
    for row in opportunities:
        group = groups[str(row[key])]
        group["opportunity_count"] += 1
        group["total_deal_value"] += row["deal_size"]
        group["total_weighted_value"] += row["weighted_value"]
        group["probability_total"] += row["probability"]

    def sort_key(item: tuple[str, dict[str, float]]) -> tuple[int, str]:
        name, _values = item
        if key == "stage":
            return (_STAGE_ORDER.get(name, 99), name)
        return (0, name)

    rows: list[dict[str, Any]] = []
    for name, values in sorted(groups.items(), key=sort_key):
        count = int(values["opportunity_count"])
        rows.append({
            key: name,
            "opportunity_count": count,
            "total_deal_value": round(values["total_deal_value"], 2),
            "total_weighted_value": round(values["total_weighted_value"], 2),
            "average_probability": round(values["probability_total"] / count, 4) if count else 0.0,
        })
    return rows


def _stage(unit: Any, metadata: dict[str, Any]) -> str:
    explicit = _string_from_metadata(metadata, ["sales_stage", "pipeline_stage"], "")
    if explicit:
        return _normalize_stage(explicit)

    quality_score = _bounded_score(getattr(unit, "quality_score", 0.0))
    usefulness_score = _bounded_score(getattr(unit, "usefulness_score", 0.0))
    evidence_count = len(getattr(unit, "evidence_signals", []) or [])
    score = (quality_score + usefulness_score) / 2 + min(evidence_count, 5) * 0.04
    if score >= 0.8:
        return "proposal"
    if score >= 0.5:
        return "qualified"
    return "discovery"


def _normalize_stage(value: Any) -> str:
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "prospecting": "discovery",
        "lead": "discovery",
        "qualification": "qualified",
        "qualified_lead": "qualified",
        "demo": "proposal",
        "evaluation": "proposal",
        "contracting": "negotiation",
        "procurement": "negotiation",
        "won": "closed_won",
        "lost": "closed_lost",
    }
    return aliases.get(normalized, normalized or "discovery")


def _deal_size(unit: Any, metadata: dict[str, Any]) -> float:
    explicit = _number_from_metadata(metadata, ["deal_size", "annual_contract_value", "acv"], float("nan"))
    if explicit == explicit:
        return round(max(explicit, 0.0), 2)

    quality_score = _bounded_score(getattr(unit, "quality_score", 0.0))
    usefulness_score = _bounded_score(getattr(unit, "usefulness_score", 0.0))
    evidence_count = len(getattr(unit, "evidence_signals", []) or [])
    score_multiplier = 1.0 + ((quality_score + usefulness_score) / 2) * 0.6
    evidence_multiplier = 1.0 + min(evidence_count, 5) * 0.08
    return round(_DEFAULT_DEAL_SIZE * score_multiplier * evidence_multiplier, 2)


def _probability(metadata: dict[str, Any], stage: str) -> float:
    explicit = _number_from_metadata(metadata, ["probability", "close_probability"], float("nan"))
    if explicit == explicit:
        if explicit > 1:
            explicit = explicit / 100
        return round(min(max(explicit, 0.0), 1.0), 4)
    return _STAGE_PROBABILITIES.get(stage, _STAGE_PROBABILITIES["discovery"])


def _expected_close_month(metadata: dict[str, Any], stage: str, generated_at: datetime) -> str:
    explicit = _string_from_metadata(metadata, ["expected_close_month", "close_month"], "")
    if explicit:
        return _normalize_month(explicit)

    offset = {
        "closed_won": 0,
        "negotiation": 1,
        "proposal": 2,
        "qualified": 3,
        "discovery": 4,
        "closed_lost": 6,
    }.get(stage, 4)
    return _add_months(generated_at, offset)


def _normalize_month(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 7:
        return stripped[:7]
    return stripped


def _add_months(value: datetime, offset: int) -> str:
    month_index = (value.year * 12 + value.month - 1) + offset
    year = month_index // 12
    month = month_index % 12 + 1
    return f"{year:04d}-{month:02d}"


def _segment(unit: Any, metadata: dict[str, Any]) -> str:
    explicit = _string_from_metadata(metadata, ["segment", "buyer_segment"], "")
    return explicit or str(getattr(unit, "domain", "") or getattr(unit, "category", "") or "general")


def _confidence(unit: Any, metadata: dict[str, Any]) -> str:
    explicit = str(metadata.get("confidence", "")).strip().lower()
    if explicit in {"low", "medium", "high"}:
        return explicit

    explicit_fields = sum(
        1
        for key in (
            "sales_stage",
            "pipeline_stage",
            "deal_size",
            "annual_contract_value",
            "probability",
            "close_month",
            "expected_close_month",
            "segment",
            "buyer_segment",
        )
        if key in metadata
    )
    evidence_count = len(getattr(unit, "evidence_signals", []) or [])
    score = explicit_fields * 0.12 + min(evidence_count, 5) * 0.08 + _bounded_score(getattr(unit, "quality_score", 0.0)) * 0.2
    if score >= 0.65:
        return "high"
    if score >= 0.3:
        return "medium"
    return "low"


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
    sales = metadata.get("sales")
    if isinstance(sales, dict):
        for key in keys:
            if key in sales:
                return _coerce_float(sales[key], default)
    return default


def _string_from_metadata(metadata: dict[str, Any], keys: list[str], default: str) -> str:
    for key in keys:
        value = metadata.get(key)
        if value is not None and value != "":
            return str(value).strip()
    sales = metadata.get("sales")
    if isinstance(sales, dict):
        for key in keys:
            value = sales.get(key)
            if value is not None and value != "":
                return str(value).strip()
    return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _bounded_score(value: Any) -> float:
    return min(max(_coerce_float(value, 0.0), 0.0), 1.0)

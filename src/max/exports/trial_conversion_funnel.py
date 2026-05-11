"""Trial conversion funnel export for product-led growth review."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.trial_conversion_funnel.v1"
KIND = "max.trial_conversion_funnel"

_STAGE_ORDER = {
    "signup": 0,
    "qualified": 1,
    "activated": 2,
    "converted": 3,
    "retained": 4,
}


def build_trial_conversion_funnel_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    """Build a trial conversion funnel report from buildable unit metadata."""
    units = store.get_buildable_units(limit=1000, domain=domain)
    rows = [_funnel_row(unit) for unit in units]
    rows.sort(key=lambda row: (row["segment"], _STAGE_ORDER.get(row["funnel_stage"], 99), row["idea_id"]))
    summary = _summary(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "trial_conversion_funnel",
            "domain_filter": domain,
            "stage_order": list(_STAGE_ORDER),
        },
        "funnel": rows,
        "summary": summary,
        "recommendations": _recommendations(rows, summary),
    }


def render_trial_conversion_funnel_markdown(report: dict[str, Any]) -> str:
    """Render a trial conversion funnel report as Markdown."""
    summary = report.get("summary", {})
    lines = [
        "# Trial Conversion Funnel",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Units reviewed: {summary.get('unit_count', 0)}",
        f"- Trials: {summary.get('trial_count', 0):,}",
        f"- Activations: {summary.get('activation_count', 0):,}",
        f"- Conversions: {summary.get('conversion_count', 0):,}",
        f"- Activation rate: {summary.get('activation_rate_pct', 0.0):.1f}%",
        f"- Conversion rate: {summary.get('conversion_rate_pct', 0.0):.1f}%",
        "",
        "## Funnel",
        "",
    ]
    if report.get("funnel"):
        lines.extend([
            "| Segment | Stage | Idea | Trials | Activations | Conversions | Activation Rate | Conversion Rate | Risk Notes |",
            "|---------|-------|------|--------|-------------|-------------|-----------------|-----------------|------------|",
        ])
        for row in report["funnel"]:
            lines.append(
                f"| {_md(row['segment'])} | {row['funnel_stage']} | {_md(row['title'])} | "
                f"{row['trial_count']} | {row['activation_count']} | {row['conversion_count']} | "
                f"{row['activation_rate_pct']:.1f}% | {row['conversion_rate_pct']:.1f}% | "
                f"{_md(', '.join(row['risk_notes']) or 'none')} |"
            )
    else:
        lines.append("- No buildable units available. Add trial funnel metadata before reviewing conversion.")

    lines.extend(["", "## Segment Rollup", ""])
    if summary.get("by_segment"):
        lines.extend(["| Segment | Trials | Activations | Conversions | Conversion Rate |", "|---------|--------|-------------|-------------|-----------------|"])
        for row in summary["by_segment"]:
            lines.append(
                f"| {_md(row['segment'])} | {row['trial_count']} | {row['activation_count']} | "
                f"{row['conversion_count']} | {row['conversion_rate_pct']:.1f}% |"
            )
    else:
        lines.append("- No segment rollups available.")

    lines.extend(["", "## Recommendations", ""])
    for recommendation in report.get("recommendations", []):
        lines.append(f"- {recommendation}")
    return "\n".join(lines).rstrip() + "\n"


def render_trial_conversion_funnel_json(report: dict[str, Any]) -> str:
    """Render a trial conversion funnel report as stable formatted JSON."""
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def _funnel_row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    trial_count = _non_negative_int(_number(metadata, ["trial_count", "trials"], 0))
    activation_count = _non_negative_int(_number(metadata, ["activation_count", "activated_trials", "activations"], 0))
    conversion_count = _non_negative_int(_number(metadata, ["conversion_count", "converted_trials", "conversions"], 0))
    stage = _stage(_string(metadata, ["funnel_stage", "trial_stage", "stage"], "signup"))
    segment = _string(metadata, ["segment", "customer_segment", "account_segment"], "unknown").lower() or "unknown"
    risk_notes = _items(_lookup(metadata, "risk_notes") or _lookup(metadata, "risks"))
    if trial_count == 0:
        risk_notes.append("missing trial denominator")
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "domain": str(getattr(unit, "domain", "") or "general"),
        "segment": segment,
        "funnel_stage": stage,
        "trial_count": trial_count,
        "activation_count": activation_count,
        "conversion_count": conversion_count,
        "activation_rate_pct": _percentage(activation_count, trial_count),
        "conversion_rate_pct": _percentage(conversion_count, trial_count),
        "risk_notes": sorted(set(risk_notes)),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    trial_count = sum(row["trial_count"] for row in rows)
    activation_count = sum(row["activation_count"] for row in rows)
    conversion_count = sum(row["conversion_count"] for row in rows)
    segment_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        segment_groups[row["segment"]].append(row)
    return {
        "unit_count": len(rows),
        "trial_count": trial_count,
        "activation_count": activation_count,
        "conversion_count": conversion_count,
        "activation_rate_pct": _percentage(activation_count, trial_count),
        "conversion_rate_pct": _percentage(conversion_count, trial_count),
        "zero_trial_unit_count": sum(1 for row in rows if row["trial_count"] == 0),
        "by_segment": [
            {
                "segment": segment,
                "unit_count": len(items),
                "trial_count": sum(item["trial_count"] for item in items),
                "activation_count": sum(item["activation_count"] for item in items),
                "conversion_count": sum(item["conversion_count"] for item in items),
                "conversion_rate_pct": _percentage(
                    sum(item["conversion_count"] for item in items),
                    sum(item["trial_count"] for item in items),
                ),
            }
            for segment, items in sorted(segment_groups.items())
        ],
    }


def _recommendations(rows: list[dict[str, Any]], summary: dict[str, Any]) -> list[str]:
    if not rows:
        return ["Add trial_count, activation_count, conversion_count, segment, and funnel_stage metadata before exporting the funnel."]
    recommendations: list[str] = []
    if summary["zero_trial_unit_count"]:
        recommendations.append("Backfill trial denominators for units with zero trial counts.")
    if summary["activation_rate_pct"] < 40.0 and summary["trial_count"] > 0:
        recommendations.append("Review onboarding and activation milestones for low activation throughput.")
    if summary["conversion_rate_pct"] < 20.0 and summary["trial_count"] > 0:
        recommendations.append("Inspect pricing, sales assist, and qualification gaps for low trial conversion.")
    risky = sum(1 for row in rows if row["risk_notes"])
    if risky:
        recommendations.append(f"Resolve risk notes on {risky} funnel row(s) before forecasting conversion gains.")
    return recommendations or ["Maintain trial funnel instrumentation and monitor segment-level conversion changes."]


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _lookup(metadata: dict[str, Any], key: str) -> Any:
    if key in metadata:
        return metadata[key]
    for nested_key in ("trial", "funnel", "growth", "metrics"):
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
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return default
    return default


def _non_negative_int(value: float) -> int:
    return max(int(value), 0)


def _items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    return [str(value).strip()]


def _stage(value: str) -> str:
    normalized = value.lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "sign_up": "signup",
        "trial": "signup",
        "trial_started": "signup",
        "qualified_trial": "qualified",
        "activation": "activated",
        "active": "activated",
        "paid": "converted",
        "conversion": "converted",
    }
    return aliases.get(normalized, normalized if normalized in _STAGE_ORDER else "signup")


def _percentage(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 1)


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
